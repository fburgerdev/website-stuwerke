#!/usr/bin/env python3
"""Fetch menus from OpenMensa, classify dishes, aggregate per canteen and week.

Usage:
  update.py                 # refresh the last 2 weeks (daily run)
  update.py --weeks 8       # refresh the last 8 weeks
  update.py --backfill 24   # add one sample week per month for the last 24 months

Standard library only, so the GitHub Action needs no dependencies.
"""
import argparse, concurrent.futures as cf, datetime as dt, json, os, re, statistics, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from stuwerke_base import SW  # noqa: E402

API = "https://openmensa.org/api/v2"
WEEKLY = os.path.join(ROOT, "data", "weekly.json")
CANTEENS = os.path.join(ROOT, "data", "canteens.json")
UA = {"User-Agent": "plant-based-mensa-tracker (github.com/fburgerdev/website-stuwerke)"}

# Canteens that are not run by a Studierendenwerk (schools, daycare, company canteens, other countries)
EXCLUDE = re.compile(
    r"schule|gymnasi|lyc[ée]e|kita|kinder|\(österreich\)|luxemb|schweiz|italien|grund|internat|waldorf|"
    r"campus schnelsen|betriebs|\(mittag\)|werkstatt|caritas|catering|kolleg\b|bildungs(haus|zentrum)|"
    r"mensatreff|schulzent|schulen|HPT |FOSBOS|IGS |OBS |GMS |Montessori|hort\b|Sekundar|Medien- und Kultur|"
    r"Kubiz|Technologie- und Business|Kombüse|Brandt's|SCHULGENUSS|Zinzendorf|Bucerius", re.I)

# ---------- classification ----------
VEGAN_NOTE = re.compile(r"^(=\s*)?vegan\b|\(vegan\)|men[üu] ist vegan|veganes (gericht|men[üu])|^pflanzlich$|^rein pflanzlich|veggi,vegan|^vegan$", re.I)
VEGGIE_NOTE = re.compile(r"^(=\s*)?vegetarisch\b|^(=\s*)?vegetarian\b|men[üu] ist vegetarisch|vegetarisches (gericht|men[üu])|"
                         r"ohne fleisch|fleischlos|^veggie?\b|ovo-lacto|^veggi,", re.I)
MEAT_NOTE = re.compile(r"fleisch|gefl[üu]gel|schwein|\brind|\bfisch|\blamm|\bwild\b|\bkalb|\bpork|\bbeef|chicken|poultry|\bfish", re.I)
NOT_MEAT_NOTE = re.compile(r"ohne (schweine)?fleisch|fleischlos|gelatine|phosphat|milcheiwei", re.I)
OPTIONAL_VEGAN = re.compile(r"(auf wunsch|auf nachfrage|oder|wahlweise|auch als|optional|dazu)\W+(\w+\W+){0,2}vegan", re.I)
VEGAN_NAME = re.compile(r"\bvegane?[rsnm]?\b|\(vegan\)|\bplant[- ]based\b", re.I)
VEGGIE_NAME = re.compile(r"\bvegetarisch|\bveggie\b|\bvegetarian\b", re.I)
MEAT_NAME = re.compile(
    r"h[äa]hnchen|h[üu]hn|\bhuhn|pute|truthahn|\bente\b|gans\b|gefl[üu]gel|chicken|schwein|\brind|kalb|lamm|"
    r"schnitzel|bratwurst|currywurst|w[üu]rstchen|\bwurst|frikadelle|bulette|hackfleisch|hackb|\bhack\b|"
    r"gulasch|speck|schinken|salami|kassler|leberk[äa]se|d[öo]ner|gyros|cevapcici|steak|braten|roulade|"
    r"fisch|lachs|seelachs|forelle|thunfisch|garnele|shrimp|scampi|matjes|hering|kabeljau|scholle|pangasius|"
    r"\bbeef|\bpork|\bfish|salmon|\btuna|bacon|k[öo]ttbullar|krustenbraten|sauerbraten|rippchen|haxe|keule|\bwild", re.I)
# a meat word in the name does not count when the name also points to a plant-based version
PLANT_HINT = re.compile(r"gem[üu]se|soja|tofu|seitan|tempeh|linsen|kichererbse|erbsen|bohnen|pflanz|veg|falafel|jackfruit|sonnenblumen|pilz|champignon|k[äa]se|dinkel|gr[üu]nkern|hafer|lupine", re.I)
PLACEHOLDER = re.compile(r"kein angebot|tagesaushang|geschlossen|salatbuffet|salat-?theke|salatbar|mensahilfe|^pommes frites$|^information|feiertag|siehe aushang|pasta bar, t[äa]glich", re.I)
SIDE_CAT = re.compile(
    r"beilage|dessert|nachspeise|nachtisch|salat(bar|buffet|theke)|^salate?$|suppe|getr[äa]nk|backware|kuchen|geb[äa]ck|"
    r"\bobst|\bsides?\b|extras|zusatz|fr[üu]hst|snack|br[öo]tchen|kaffee|smoothie|bagel|croissant|s[üu][sß]e ecke|"
    r"vorspeise|dips?\b|so[sß]en|eis\b|cafeteria|laugen|belegt|^information|blondie|brownie|waffel|muffin|cookie|s[üu][sß]speise", re.I)


def classify(meal):
    """Return 'v' (vegan), 'g' (vegetarian), 'm' (meat or fish) or 'u' (unlabelled)."""
    name = meal.get("name") or ""
    cat = meal.get("category") or ""
    notes = [n.strip() for n in (meal.get("notes") or []) if n and len(n) < 90]
    vegan = any(VEGAN_NOTE.search(n) for n in notes) or re.search(r"\bvegan", cat, re.I) and not re.search(r"vegetar", cat, re.I)
    if not vegan and VEGAN_NAME.search(name) and not OPTIONAL_VEGAN.search(name):
        vegan = True
    if vegan:
        return "v"
    if any(VEGGIE_NOTE.search(n) for n in notes) or re.search(r"vegetar|veggie", cat, re.I) or VEGGIE_NAME.search(name):
        return "g"
    if any(MEAT_NOTE.search(n) and not NOT_MEAT_NOTE.search(n) for n in notes) or re.search(r"fleisch|fisch|gefl[üu]gel", cat, re.I):
        return "m"
    if MEAT_NAME.search(name) and not PLANT_HINT.search(name):
        return "m"
    return "u"


def is_main(meal):
    cat = meal.get("category") or ""
    if SIDE_CAT.search(cat) or PLACEHOLDER.search(meal.get("name") or ""):
        return False
    price = (meal.get("prices") or {}).get("students")
    if price is not None and 0 < price < 1.3:
        return False
    return True


# ---------- fetching ----------
def get(url, tries=4):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(1.5 * (t + 1))
    print("failed:", url, err, file=sys.stderr)
    return None


def all_canteens():
    out, page = [], 1
    while True:
        d = get(f"{API}/canteens?page={page}&per_page=100")
        if not d:
            break
        out += d
        page += 1
    return out


def map_canteens(canteens):
    """Assign each OpenMensa canteen to a Studierendenwerk by city, skipping non-university canteens."""
    mapped = {}
    for c in canteens:
        text = f"{c['name']} {c['city']}"
        if EXCLUDE.search(text):
            continue
        for sid, _name, _state, _seat, _pos, cities in SW:
            if any(re.search(r"\b" + re.escape(city), c["city"]) or re.search(r"\b" + re.escape(city), c["name"]) for city in cities):
                mapped[str(c["id"])] = {"sw": sid, "name": c["name"], "city": c["city"], "pos": c.get("coordinates")}
                break
    return mapped


def monday(d):
    return d - dt.timedelta(days=d.weekday())


def week_record(days):
    """Aggregate one week of one canteen into counts and median student prices."""
    seen, counts, prices = set(), {"v": 0, "g": 0, "m": 0, "u": 0}, {"v": [], "g": [], "m": []}
    for day in days:
        if day.get("closed"):
            continue
        for meal in day.get("meals", []):
            if not is_main(meal):
                continue
            key = (day["date"], (meal.get("name") or "").strip().lower())
            if key in seen:
                continue
            seen.add(key)
            k = classify(meal)
            counts[k] += 1
            p = (meal.get("prices") or {}).get("students")
            if k in prices and p and 1.3 <= p < 15:
                prices[k].append(p)
    n = sum(counts.values())
    if n == 0:
        return None
    rec = {"n": n, **counts}
    for k, vals in prices.items():
        if len(vals) >= 3:
            rec["p" + k] = round(statistics.median(vals), 2)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=2)
    ap.add_argument("--backfill", type=int, default=0, help="months of history, one sample week per month")
    args = ap.parse_args()

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    weekly = json.load(open(WEEKLY)) if os.path.exists(WEEKLY) else {}
    mapped = map_canteens(all_canteens())
    if len(mapped) < 100:
        sys.exit("canteen list looks broken, aborting without changes")
    json.dump(mapped, open(CANTEENS, "w"), ensure_ascii=False, indent=0, sort_keys=True)

    today = dt.date.today()
    this_monday = monday(today)
    starts = [this_monday - dt.timedelta(weeks=i) for i in range(args.weeks)]
    if args.backfill:
        for m in range(1, args.backfill + 1):
            y, mo = today.year, today.month - m
            while mo <= 0:
                y, mo = y - 1, mo + 12
            # second full week of the month, avoids most holidays at month edges
            starts.append(monday(dt.date(y, mo, 8)) + dt.timedelta(weeks=1) if monday(dt.date(y, mo, 8)).month != mo else monday(dt.date(y, mo, 8)))
    starts = sorted(set(starts))
    jobs = [(cid, s) for cid in mapped for s in starts
            if args.backfill == 0 or s >= this_monday - dt.timedelta(weeks=args.weeks) or s.isoformat() not in weekly.get(cid, {})]
    print(f"{len(mapped)} canteens, {len(starts)} weeks, {len(jobs)} requests")

    def work(job):
        cid, s = job
        return cid, s, get(f"{API}/canteens/{cid}/meals?start={s.isoformat()}")

    done = 0
    with cf.ThreadPoolExecutor(6) as ex:
        for cid, s, days in ex.map(work, jobs):
            done += 1
            if days is None:
                continue
            days = [d for d in days if s.isoformat() <= d["date"] < (s + dt.timedelta(days=7)).isoformat()]
            rec = week_record(days)
            wk = weekly.setdefault(cid, {})
            if rec:
                wk[s.isoformat()] = rec
            elif s.isoformat() not in wk:
                wk[s.isoformat()] = None  # looked, nothing there: do not ask again in a backfill
            if done % 2000 == 0:
                print(done, "done", flush=True)
                json.dump(weekly, open(WEEKLY, "w"), separators=(",", ":"), sort_keys=True)
    json.dump(weekly, open(WEEKLY, "w"), separators=(",", ":"), sort_keys=True)
    print("weekly.json updated")


if __name__ == "__main__":
    main()
