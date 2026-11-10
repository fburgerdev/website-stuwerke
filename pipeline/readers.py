"""Readers for Studierendenwerke that have no working OpenMensa feed.

Each reader fetches menus straight from the Studierendenwerk's own website or API, without any AI,
and returns canteens in one shared shape:

    {"key": "muenchen:mensa-arcisstr", "sw": "muenchen", "name": "...", "city": "...", "pos": [lat, lon] or None,
     "days": [{"date": "2026-11-10", "meals": [{"name", "category", "notes": [...], "prices": {"students": 2.5}}]}]}

A reader asks for everything that is published from the start date on, so menus posted in advance are picked up once
and simply overwritten on later runs. A reader that breaks returns nothing and is reported; the others carry on.
"""
import datetime as dt, html, json, re, time, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; plant-based-mensa-tracker; +https://github.com/fburgerdev/website-stuwerke)"}


def get(url, data=None, timeout=40):
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def euro(s):
    m = re.search(r"(\d+)[,.](\d\d)", s or "")
    return float(m.group(1) + "." + m.group(2)) if m else None


def weeks(start, n):
    monday = start - dt.timedelta(days=start.weekday())
    return [monday + dt.timedelta(weeks=i) for i in range(n)]


# ---------- München Oberbayern: TUM-Dev eat-api (static JSON, built from the Studierendenwerk's own menus) ----------
def muenchen(start):
    base = "https://tum-dev.github.io/eat-api"
    out = []
    for c in json.loads(get(f"{base}/enums/canteens.json")):
        cid = c["canteen_id"]
        if cid in ("mensa-straubing", "mensa-bildungscampus-heilbronn"):
            continue  # listed by the API but run by other Studierendenwerke
        days = []
        for wk in weeks(start, 3):
            y, w, _ = wk.isocalendar()
            try:
                data = json.loads(get(f"{base}/{cid}/{y}/{w:02d}.json"))
            except Exception:  # noqa: BLE001  (no file for that week yet)
                continue
            for d in data.get("days", []):
                meals = []
                for dish in d.get("dishes", []):
                    labels = set(dish.get("labels", []))
                    notes = []
                    if "VEGAN" in labels:
                        notes.append("vegan")
                    elif "VEGETARIAN" in labels:
                        notes.append("vegetarisch")
                    if labels & {"MEAT", "PORK", "BEEF", "VEAL", "POULTRY", "LAMB", "WILD_MEAT"}:
                        notes.append("Fleisch")
                    if "FISH" in labels:
                        notes.append("Fisch")
                    p = (dish.get("prices") or {}).get("students") or {}
                    meals.append({"name": dish["name"], "category": dish.get("dish_type") or "", "notes": notes,
                                  "prices": {"students": p.get("base_price") or None}})
                days.append({"date": d["date"], "meals": meals})
        loc = c.get("location") or {}
        city = (loc.get("address") or "").split(",")[-1].strip() or "München"
        out.append({"key": f"muenchen:{cid}", "sw": "muenchen", "name": c["name"], "city": city,
                    "pos": [loc["latitude"], loc["longitude"]] if loc.get("latitude") else None, "days": days})
    return out


# ---------- OstNiedersachsen: the Studierendenwerk's own public JSON API ----------
def ostniedersachsen(start):
    base = "https://sls.api.stw-on.de/v1"
    out = []
    end = start + dt.timedelta(days=20)
    for loc in json.loads(get(f"{base}/location")):
        if not loc.get("opening_hours"):
            continue
        try:
            data = json.loads(get(f"{base}/locations/{loc['id']}/menu/{start.isoformat()}/{end.isoformat()}"))
        except Exception:  # noqa: BLE001
            continue
        by_day = {}
        for m in data.get("meals", []):
            tags = m.get("tags") or {}
            notes = [t.get("name", "") for t in tags.get("categories", [])]
            by_day.setdefault(m["date"], []).append({
                "name": m["name"], "category": (m.get("lane") or {}).get("name", ""), "notes": notes,
                "prices": {"students": float(m["price"]["student"]) if (m.get("price") or {}).get("student") else None}})
        if by_day:
            out.append({"key": f"ostniedersachsen:{loc['id']}", "sw": "ostniedersachsen", "name": loc["name"],
                        "city": loc["address"]["city"], "pos": None,
                        "days": [{"date": d, "meals": ms} for d, ms in sorted(by_day.items())]})
    return out


# ---------- Bodensee (Seezeit): public XML export of its menu system ----------
SEEZEIT = {"mensa_giessberg": ("Mensa Gießberg", "Konstanz", [47.6906, 9.1886]), "mensa_htwg": ("Mensa HTWG", "Konstanz", [47.6672, 9.1722]),
           "mensa_friedrichshafen": ("Mensa Friedrichshafen", "Friedrichshafen", [47.6594, 9.4933]),
           "mensa_weingarten": ("Mensa Weingarten", "Weingarten", [47.8108, 9.6439]), "mensa_ravensburg": ("Mensa Ravensburg", "Ravensburg", [47.7836, 9.6131])}
SEEZEIT_ICONS = {"24": "vegan", "51": "vegetarisch", "45": "Schwein", "46": "Rind", "49": "Geflügel", "50": "Fisch"}


def bodensee(start):
    out = []
    for slug, (name, city, pos) in SEEZEIT.items():
        try:
            xml = get(f"https://www.max-manager.de/daten-extern/seezeit/xml/{slug}/speiseplan.xml")
        except Exception:  # noqa: BLE001
            continue
        days = []
        for ts, body in re.findall(r"<tag timestamp='(\d+)'>(.*?)</tag>", xml, re.S):
            date = dt.datetime.fromtimestamp(int(ts), dt.timezone(dt.timedelta(hours=2))).date().isoformat()
            meals = []
            for item in re.findall(r"<item language='de'>(.*?)</item>", body, re.S):
                f = lambda tag: html.unescape((re.search(rf"<{tag}>(.*?)</{tag}>", item, re.S) or [None, ""])[1]).strip()  # noqa: E731
                cat = f("category")
                if re.search(r"sättigung|gemüse|dessert|salat", cat, re.I):
                    continue
                notes = [SEEZEIT_ICONS[i.strip()] for i in f("icons").split(",") if i.strip() in SEEZEIT_ICONS]
                title = re.sub(r"\s*\([\d,a-z ]+\)", "", f("title"))
                meals.append({"name": title, "category": cat, "notes": notes, "prices": {"students": euro(f("preis1"))}})
            days.append({"date": date, "meals": meals})
        out.append({"key": f"bodensee:{slug}", "sw": "bodensee", "name": name, "city": city, "pos": pos, "days": days})
    return out


# ---------- Rostock-Wismar: one HTML page per day with every canteen on it ----------
def rostock_wismar(start):
    canteens = {}
    for i in range(12):
        day = start + dt.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        try:
            page = get(f"https://www.stw-rw.de/de/mensen-und-cafeterien/speiseplaene/{day.isoformat()}.html")
        except Exception:  # noqa: BLE001
            continue
        for name, block in re.findall(r'<dt class="mensenplan"[^>]*>\s*<p>(.*?)</p>.*?<dd>(.*?)</dd>', page, re.S):
            name = text(name)
            cat, meals = "", []
            for row in re.findall(r"<tr>(.*?)</tr>", block, re.S):
                if "col_theke" in row:
                    cat = text(row)
                    continue
                m = re.search(r'<td class="mensa_col_55">\s*<b>(.*?)</b>', row, re.S)
                if not m:
                    continue
                dish = text(m.group(1))
                price = euro((re.search(r"Stud\.:</span><br><b>(.*?)</b>", row) or [None, ""])[1])
                notes = ["vegan"] if re.search(r"\(vegan\)", dish, re.I) else ["vegetarisch"] if re.search(r"\(vegetarisch\)|\(veg\.?\)", dish, re.I) else []
                meals.append({"name": dish, "category": cat, "notes": notes, "prices": {"students": price}})
            if meals:
                city = "Wismar" if "Wismar" in name else "Rostock"
                c = canteens.setdefault(name, {"key": f"rostock-wismar:{name}", "sw": "rostock-wismar", "name": name, "city": city, "pos": None, "days": []})
                c["days"].append({"date": day.isoformat(), "meals": meals})
    return list(canteens.values())


# ---------- Vorderpfalz: menu page with one box per meal, labelled through CSS classes ----------
def vorderpfalz(start):
    page = get("https://www.stw-vp.de/de/essen-und-trinken/speiseplaene")
    days = []
    for date, block in re.findall(r'<div class="date-block[^"]*" data-mealdate="([\d-]+)">(.*?)(?=<div class="date-block|<div class="meal-links|$)', page, re.S):
        meals = []
        for box in re.findall(r'<div class="meal-desc">(.*?)<div class="meal-addinfo', block, re.S):
            main = re.search(r'<div class="meal-entry meal-main([^"]*)">(.*?)(?:<nobr>|<br|</div>)', box, re.S)
            if not main:
                continue
            cls, dish = main.group(1), text(main.group(2))
            notes = ["vegan"] if "is_vegan" in cls else ["vegetarisch"] if "is_veggy" in cls else []
            if re.search(r"has_(beef|pork|poultry|chicken|fish|lamb|game|meat)", cls):
                notes.append("Fleisch")
            head = text((re.search(r"<h2>(.*?)<span>", box, re.S) or [None, ""])[1])
            meals.append({"name": dish, "category": head, "notes": notes, "prices": {"students": None}})
        if meals:
            days.append({"date": date, "meals": meals})
    # the page serves the Landau canteen by default; the other four sites need a session and are not read yet
    return [{"key": "vorderpfalz:landau", "sw": "vorderpfalz", "name": "Mensa Landau", "city": "Landau", "pos": [49.2042, 8.1078], "days": days}] if days else []


# ---------- my-mensa.de: one menu system shared by several Studierendenwerke ----------
MYMENSA = {
    # sw id: (subdomain, vegan codes, vegetarian codes, meat/fish codes, default city, {slug fragment: city})
    "wuppertal": ("wuppertal", {"Vgn"}, {"Veg"}, {"G", "S", "R", "F"}, "Wuppertal", {}),
    "magdeburg": ("magdeburg", {"[veg]"}, {"[vgt]"}, {"[gef]", "[sch]", "[rin]", "[fis]"}, "Magdeburg",
                  {"halberstadt": "Halberstadt", "stendal": "Stendal", "wernigerode": "Wernigerode"}),
    "oldenburg": ("oldenburg", {"Vplus"}, {"V"}, {"G", "S", "R", "F", "L"}, "Oldenburg",
                  {"elsfleth": "Elsfleth", "emden": "Emden", "whv": "Wilhelmshaven"}),
    "freiberg": ("freiberg", {"VG"}, {"V"}, {"G", "S", "R", "F", "L", "W"}, "Freiberg", {"mittweida": "Mittweida"}),
}


def mymensa(sw):
    def reader(start):
        sub, vegan, veggie, meat, default_city, cities = MYMENSA[sw]
        base = f"https://{sub}.my-mensa.de"
        chooser = get(f"{base}/chooser.php?hyp=1&lang=de&mensa=all")
        slugs = sorted(set(re.findall(r"essen\.php\?[^\"#]*mensa=([a-z0-9_]+)", chooser)))
        out = []
        for slug in slugs:
            time.sleep(3)  # this system blocks fast readers; a handful of slow requests a day is enough
            try:
                page = get(f"{base}/essen.php?hyp=1&lang=de&mensa={slug}")
            except Exception:  # noqa: BLE001
                continue
            title = re.search(r'class="mensatitle[^"]*">(.*?)</h3>', page, re.S)
            parts = re.split(rf'id="{slug}_tag_(\d{{4}})(\d{{1,3}})"', page)
            days = []
            for i in range(1, len(parts) - 2, 3):
                date = (dt.date(int(parts[i]), 1, 1) + dt.timedelta(days=int(parts[i + 1]) - 1)).isoformat()
                cat, meals = "", []
                for li in re.findall(r"<li (.*?)</li>", parts[i + 2], re.S):
                    if "groupdivider" in li[:400]:
                        cat = text((re.search(r"<div[^>]*>(.*?)</div>", li, re.S) or [None, ""])[1])
                        continue
                    ref = re.search(r"ref='(\[.*?\])'", li)
                    if not ref or "conditional" not in li[:200]:
                        continue
                    codes = set(json.loads(ref.group(1)))
                    name = text((re.search(r"<h3[^>]*>(.*?)</h3>", li, re.S) or [None, ""])[1]).replace("\u00ad", "")
                    desc = text(re.sub(r"<sup.*?</sup>", "", (re.search(r'<p class="ct text2share">(.*?)</p>', li, re.S) or [None, ""])[1])).replace("\u00ad", "")
                    name = (name + " " + desc).strip()
                    if not name:
                        continue
                    notes = ["vegan"] if codes & vegan else ["vegetarisch"] if codes & veggie else []
                    if codes & meat:
                        notes.append("Fleisch")
                    price = euro((re.search(r'<p class="ct next text2share">(.*?)</p>', li, re.S) or [None, ""])[1])
                    meals.append({"name": name, "category": cat, "notes": notes, "prices": {"students": price}})
                if meals:
                    days.append({"date": date, "meals": meals})
            if days:
                city = next((c for frag, c in cities.items() if frag in slug), default_city)
                out.append({"key": f"{sw}:{slug}", "sw": sw, "name": text(title.group(1)) if title else slug, "city": city, "pos": None, "days": days})
        return out
    return reader


READERS = {"muenchen": muenchen, "ostniedersachsen": ostniedersachsen, "bodensee": bodensee,
           "rostock-wismar": rostock_wismar, "vorderpfalz": vorderpfalz,
           **{sw: mymensa(sw) for sw in MYMENSA}}


def run_all(start, only=None):
    """Run every reader; return (canteens, report). A failing reader never stops the others."""
    canteens, report = [], {}
    for name, fn in READERS.items():
        if only and name not in only:
            continue
        try:
            got = fn(start)
            dates = [d["date"] for c in got for d in c["days"] if d["meals"]]
            report[name] = {"ok": bool(dates), "canteens": len(got), "meals": sum(len(d["meals"]) for c in got for d in c["days"]),
                            "published_until": max(dates) if dates else None}
            canteens += got
        except Exception as e:  # noqa: BLE001
            report[name] = {"ok": False, "error": str(e)[:200]}
    return canteens, report


if __name__ == "__main__":
    import sys
    cs, rep = run_all(dt.date.today(), only=sys.argv[1:] or None)
    print(json.dumps(rep, indent=1))
