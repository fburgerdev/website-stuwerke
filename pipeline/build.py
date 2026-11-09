#!/usr/bin/env python3
"""Turn data/weekly.json + data/stuwerke.json into docs/data.json for the site."""
import datetime as dt, json, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
D = lambda *p: os.path.join(ROOT, *p)  # noqa: E731

STATES = {
    "BW": "Baden-Württemberg", "BY": "Bavaria", "BE": "Berlin", "BB": "Brandenburg", "HB": "Bremen", "HH": "Hamburg",
    "HE": "Hesse", "MV": "Mecklenburg-Vorpommern", "NI": "Lower Saxony", "NW": "North Rhine-Westphalia",
    "RP": "Rhineland-Palatinate", "SL": "Saarland", "SN": "Saxony", "ST": "Saxony-Anhalt", "SH": "Schleswig-Holstein", "TH": "Thuringia",
}
GEO_NAMES = {
    "Baden-Württemberg": "BW", "Bayern": "BY", "Berlin": "BE", "Brandenburg": "BB", "Bremen": "HB", "Hamburg": "HH", "Hessen": "HE",
    "Mecklenburg-Vorpommern": "MV", "Niedersachsen": "NI", "Nordrhein-Westfalen": "NW", "Rheinland-Pfalz": "RP", "Saarland": "SL",
    "Sachsen": "SN", "Sachsen-Anhalt": "ST", "Schleswig-Holstein": "SH", "Thüringen": "TH",
}
WINDOW_WEEKS = 4
MIN_DISHES = 30          # a Studierendenwerk needs this many main dishes in the window to get a number
W, H = 560, 760          # map canvas


def add(a, b):
    for k in ("n", "v", "g", "m", "u"):
        a[k] = a.get(k, 0) + b.get(k, 0)
    return a


def shares(c):
    n = c.get("n", 0)
    if not n:
        return None
    return {"n": n, "vegan": round(c["v"] / n, 4), "vegetarian": round(c["g"] / n, 4),
            "meat": round(c["m"] / n, 4), "unlabelled": round(c["u"] / n, 4)}


def quality(s):
    """good: vegan dishes are labelled and little is unlabelled. partial: labelled, but much is not. none: no usable labels."""
    if not s or s["n"] < MIN_DISHES or s["vegan"] < 0.02:
        return "none"
    return "good" if s["unlabelled"] <= 0.15 else "partial"


def project(lon, lat, box):
    lon0, lon1, lat0, lat1, k = box
    x = (lon - lon0) * k
    y = (lat1 - lat) * k / 0.6157  # cos(52°): keeps Germany's proportions
    return round(x, 1), round(y, 1)


def build_map():
    geo = json.load(open(D("pipeline", "geo", "bundeslaender.geo.json")))
    lon0, lon1, lat0, lat1 = 5.8, 15.1, 47.2, 55.1
    k = min(W / (lon1 - lon0), H * 0.6157 / (lat1 - lat0))
    box = (lon0, lon1, lat0, lat1, k)
    paths = {}
    for f in geo["features"]:
        code = GEO_NAMES[f["properties"]["name"]]
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = ""
        for poly in polys:
            ring = poly[0]
            if len(ring) < 12:
                continue  # drop tiny islands, they only add noise at this size
            pts = [project(x, y, box) for x, y in ring]
            d += "M" + "L".join(f"{x},{y}" for x, y in pts) + "Z"
        paths[code] = d
    return paths, box


def main():
    weekly = json.load(open(D("data", "weekly.json")))
    canteens = json.load(open(D("data", "canteens.json")))
    ref = json.load(open(D("data", "stuwerke.json")))
    umbrella = json.load(open(D("data", "umbrella.json")))
    paths, box = build_map()

    today = dt.date.today()
    all_weeks = sorted({w for c in weekly.values() for w, r in c.items() if r})
    window = [w for w in all_weeks if w <= today.isoformat()][-WINDOW_WEEKS:]
    year_ago = [w for w in all_weeks
                if (today - dt.timedelta(days=400)).isoformat() <= w <= (today - dt.timedelta(days=330)).isoformat()]

    by_sw = {}
    for cid, info in canteens.items():
        by_sw.setdefault(info["sw"], []).append(cid)

    def agg(cids, weeks):
        tot = {}
        for cid in cids:
            for w in weeks:
                r = weekly.get(cid, {}).get(w)
                if r:
                    add(tot, r)
        return tot

    def price(cids, weeks, key):
        vals = [weekly[c][w][key] for c in cids for w in weeks if weekly.get(c, {}).get(w) and key in weekly[c][w]]
        return round(statistics.median(vals), 2) if len(vals) >= 3 else None

    out = []
    for s in ref:
        cids = by_sw.get(s["id"], [])
        cur = shares(agg(cids, window))
        q = quality(cur)
        rec = {k: s[k] for k in ("id", "name", "short", "state", "seat", "students", "cities", "website", "universities", "people", "milestones")}
        rec["universities_source"] = s.get("universities_source")
        rec["x"], rec["y"] = project(s["lon"], s["lat"], box)
        rec["quality"] = q
        rec["has_feed"] = bool(cur)
        if q != "none":
            rec["now"] = cur
            prev = shares(agg(cids, year_ago))
            if prev and quality(prev) != "none":
                rec["change"] = round(cur["vegan"] - prev["vegan"], 4)
            # monthly series: group every available week by month
            months = {}
            for w in all_weeks:
                months.setdefault(w[:7], []).append(w)
            series = []
            for mth in sorted(months):
                sh = shares(agg(cids, months[mth]))
                if sh and sh["n"] >= MIN_DISHES and sh["vegan"] >= 0.02:
                    series.append([mth, sh["vegan"], sh["vegetarian"]])
            rec["series"] = series
            pv, pm = price(cids, window, "pv"), price(cids, window, "pm")
            if pv and pm:
                rec["price"] = {"vegan": pv, "meat": pm}
            cl = []
            for cid in cids:
                sh = shares(agg([cid], window))
                if sh and sh["n"] >= 10:
                    cl.append({"name": canteens[cid]["name"], "n": sh["n"], "vegan": sh["vegan"], "vegetarian": sh["vegetarian"]})
            rec["canteens"] = sorted(cl, key=lambda c: -c["vegan"])
        out.append(rec)

    def weighted(items, field):
        # averages use only Studierendenwerke with well-labelled menus; a lower bound would drag them down
        items = [i for i in items if i["quality"] == "good"]
        tot = sum(i["students"] for i in items)
        return round(sum(i["now"][field] * i["students"] for i in items) / tot, 4) if tot else None

    def summary(items):
        covered = [i for i in items if i.get("now")]
        good = [i for i in items if i["quality"] == "good"]
        ch = [i for i in good if "change" in i]
        tot_ch = sum(i["students"] for i in ch)
        return {
            "count": len(items), "with_data": len(covered),
            "students": sum(i["students"] for i in items), "students_covered": sum(i["students"] for i in covered),
            "in_average": len(good), "students_in_average": sum(i["students"] for i in good),
            "vegan": weighted(items, "vegan"), "vegetarian": weighted(items, "vegetarian"),
            "meat": weighted(items, "meat"), "unlabelled": weighted(items, "unlabelled"),
            "change": round(sum(i["change"] * i["students"] for i in ch) / tot_ch, 4) if tot_ch else None,
        }

    states = []
    for code, name in STATES.items():
        items = [i for i in out if i["state"] == code]
        states.append({"code": code, "name": name, "path": paths[code], **summary(items),
                       "umbrella": [u["id"] for u in umbrella if code in u.get("states", [])]})

    # national monthly series, student-weighted over the Studierendenwerke that have that month
    months = sorted({p[0] for i in out for p in i.get("series", [])})
    nat = []
    for mth in months:
        pts = [(i["students"], p[1], p[2]) for i in out if i["quality"] == "good" for p in i.get("series", []) if p[0] == mth]
        tot = sum(p[0] for p in pts)
        if len(pts) >= 15:
            nat.append([mth, round(sum(p[0] * p[1] for p in pts) / tot, 4), round(sum(p[0] * p[2] for p in pts) / tot, 4), len(pts)])

    data = {
        "updated": today.isoformat(), "window": [window[0], window[-1]] if window else None,
        "national": {**summary(out), "series": nat}, "states": states, "stuwerke": out, "umbrella": umbrella,
        "map": {"w": W, "h": round((55.1 - 47.2) * box[4] / 0.6157)},
    }
    os.makedirs(D("docs"), exist_ok=True)
    json.dump(data, open(D("docs", "data.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    n = data["national"]
    print(f"in average {n['in_average']}; national vegan {n['vegan']:.1%}, vegetarian {n['vegetarian']:.1%}, {n['with_data']}/{n['count']} with data, change {n['change']}")


if __name__ == "__main__":
    sys.exit(main())
