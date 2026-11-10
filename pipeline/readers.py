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


def get(url, data=None, timeout=40, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
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
VORDERPFALZ = {"310": ("Mensa Landau", "Landau"), "311": ("Mensa Landau Bürgerstraße", "Landau"), "320": ("Mensa Germersheim", "Germersheim"),
               "340": ("Mensa Ludwigshafen", "Ludwigshafen"), "330": ("Mensa Worms", "Worms")}


def vorderpfalz(start):
    out = []
    for cid, (name, city) in VORDERPFALZ.items():
        time.sleep(0.5)
        try:  # the page shows the canteen named in the visitor's settings cookie
            page = get("https://www.stw-vp.de/de/essen-und-trinken/speiseplaene", headers={"Cookie": 'user_settings={"mensa":"%s"}' % cid})
        except Exception:  # noqa: BLE001
            continue
        if cid != "310" and not re.search(r"dcl=[\d-]+,%s," % cid, page):
            continue  # the cookie was ignored and we got the default canteen again
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
        if days:
            out.append({"key": "vorderpfalz:landau" if cid == "310" else f"vorderpfalz:{cid}", "sw": "vorderpfalz", "name": name, "city": city, "pos": None, "days": days})
    return out


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
            time.sleep(6)  # this system blocks an address after a few dozen requests; go slowly
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


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


# ---------- Bonn: the website's own menu endpoint, one request per canteen and day ----------
BONN = {"1": ("Mensa Sankt Augustin", "Sankt Augustin"), "2": ("Mensa CAMPO", "Bonn"), "3": ("Mensa am Hofgarten", "Bonn"),
        "6": ("Venusberg Bistro", "Bonn"), "8": ("Casino ZEF/ZEI", "Bonn"), "21": ("Mensa Rabinstraße", "Bonn"), "22": ("Mensa Rheinbach", "Rheinbach")}


def bonn(start):
    out = []
    for cid, (name, city) in BONN.items():
        days, empty = [], 0
        for day in weekdays(start, 10):
            if day < dt.date.today():
                continue  # the endpoint only serves today and later
            time.sleep(0.4)
            try:
                page = get("https://www.studierendenwerk-bonn.de/?type=1732731666", data=urllib.parse.urlencode({
                    "tx_festwb_mealsajax[date]": day.isoformat(), "tx_festwb_mealsajax[canteen]": cid, "tx_festwb_mealsajax[language]": "0"}).encode())
            except Exception:  # noqa: BLE001
                page = ""
            meals = []
            for cat, block in re.findall(r"<h2>(.*?)</h2>(.*?)(?=<h2>|$)", page, re.S):
                for item in re.split(r'class="menus__result ', block)[1:]:
                    title = text((re.search(r"<h5>(.*?)</h5>", item, re.S) or [None, ""])[1])
                    if not title:
                        continue
                    icons = [t.lower() for t in re.findall(r'class="fi additive-\d+" title="([^"]*)"', item)]
                    notes = ["vegan"] if "vegan" in icons else ["vegetarisch"] if any("fleischlos" in t or "vegetar" in t for t in icons) else []
                    if any(re.search(r"geflügel|schwein|rind|fisch|lamm|wild", t) for t in icons):
                        notes.append("Fleisch")
                    price = euro((re.search(r"Stud\.\s*</th>\s*<td>(.*?)</td>", item, re.S) or [None, ""])[1])
                    meals.append({"name": title, "category": text(cat), "notes": notes, "prices": {"students": price}})
            if meals:
                days.append({"date": day.isoformat(), "meals": meals})
                empty = 0
            else:
                empty += 1
                if empty >= 3:
                    break
        if days:
            out.append({"key": f"bonn:{cid}", "sw": "bonn", "name": name, "city": city, "pos": None, "days": days})
    return out


# ---------- Dortmund: the website's own JSON API, two weeks at a time ----------
def dortmund(start):
    base = "https://www.stwdo.de/api/v2/speiseplan"
    cities = {"Soest": "Soest", "da Vinci": "Meschede", "Canape": "Iserlohn", "Snack it": "Hagen", "FernUni": "Hagen"}
    out = []
    for loc in json.loads(get(f"{base}/verbrauchsorte")):
        if "Kindertag" in loc["name"]:
            continue
        time.sleep(0.3)
        try:
            rows = json.loads(get(f"{base}/naechste-2-wochen?verbrauchsortnr={loc['id']}&limit=300"))
        except Exception:  # noqa: BLE001
            continue
        by_day = {}
        for r in rows:
            d, mth, y = r["PRODUKTIONSDATUM"].split(".")
            flags = set((r.get("FREIKENNZEICHEN") or "").replace(" ", "").split(","))
            notes = ["vegan"] if "N" in flags else ["vegetarisch"] if "V" in flags else []
            if flags & {"G", "S", "R", "F", "L", "W", "K"}:
                notes.append("Fleisch")
            lines = [re.sub(r"\s*\([\d,a-z ]+\)", "", r.get(f"AUSGABETEXTZEILE{i}") or "") for i in range(1, 4)]
            name = ", ".join(x for x in lines if x) or r["PRODUKTIONSBEZEICHNUNG"]
            by_day.setdefault(f"{y}-{mth}-{d}", []).append({"name": name, "category": r.get("PRODUKTIONSNAME") or "", "notes": notes,
                                                            "prices": {"students": r.get("VKPREISSTUD") or None}})
        if by_day:
            name = loc["name"].replace(" inklKalteKüche", "")
            out.append({"key": f"dortmund:{loc['id']}", "sw": "dortmund", "name": name, "city": next((c for k, c in cities.items() if k in name), "Dortmund"),
                        "pos": None, "days": [{"date": d, "meals": ms} for d, ms in sorted(by_day.items())]})
    return out


# ---------- Düsseldorf: the public menu displays linked from each canteen page (seven day pages each) ----------
def duesseldorf(start):
    index = get("https://www.stw-d.de/gastronomie/speiseplaene/")
    out = []
    for page_url in sorted(set(re.findall(r'href="(https://www\.stw-d\.de/gastronomie/speiseplaene/[a-z0-9-]+/)"', index))):
        slug = page_url.rstrip("/").split("/")[-1]
        time.sleep(0.3)
        try:
            page = get(page_url)
        except Exception:  # noqa: BLE001
            continue
        link = re.search(r'href="(https://mocca\.stw-d\.de/[^"]+/)Index\.html"', page)
        if not link:
            continue
        title = text((re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S) or [None, slug])[1])
        days = []
        for i in range(7):
            time.sleep(0.3)
            try:
                h = get(f"{link.group(1)}Site_{i}.html")
            except Exception:  # noqa: BLE001
                continue
            date = re.search(r"(\d\d)\.(\d\d)\.(\d{4})", text(h))
            if not date:
                continue
            meals = []
            for item in re.split(r'class="menuitem"', h)[1:]:
                cat = text((re.search(r'class="articledetailnamerow">(.*?)</tr>', item, re.S) or [None, ""])[1])
                name = text((re.search(r'<div class="container">(.*?)</div>\s*</div>', item, re.S) or [None, ""])[1])
                price = euro((re.search(r"Studierende:\s*([\d,]+)", item) or [None, ""])[1])
                if name:
                    meals.append({"name": name, "category": cat, "notes": [], "prices": {"students": price}})
            if meals:
                days.append({"date": f"{date.group(3)}-{date.group(2)}-{date.group(1)}", "meals": meals})
        if days:
            city = next((c for c in ("Krefeld", "Kamp-Lintfort", "Kleve", "Mönchengladbach") if c.lower().replace("ö", "oe") in slug), "Düsseldorf")
            out.append({"key": f"duesseldorf:{slug}", "sw": "duesseldorf", "name": title, "city": city, "pos": None, "days": days})
    return out


# ---------- Essen-Duisburg: the website's menu grid, which only serves the current day ----------
def essen_duisburg(start):
    page = get("https://www.stw-edu.de/gastronomie/speisen/")
    opts = re.findall(r'<option[^>]*value="([a-z0-9-]+)"[^>]*>([^<]+)', page[page.find('id="mensaSelect"'):][:4000])
    today = dt.date.today().isoformat()
    out = []
    for slug, label in opts:
        time.sleep(0.4)
        try:
            data = json.loads(get(f"https://www.stw-edu.de/wp-json/az-speisen-grid/v1/items?slug={slug}&ort={slug}"))
        except Exception:  # noqa: BLE001
            continue
        meals = []
        for art in re.split(r'<article class="speisen-grid__item"', data.get("html") or "")[1:]:
            types = set(re.findall(r"mensa_type-([a-z-]+)", art))
            heads = [text(x) for x in re.findall(r'class="elementor-heading-title[^"]*"[^>]*>(.*?)</(?:h\d|span|div|p)>', art, re.S)]
            heads = [x for x in heads if x]
            if len(heads) < 2:
                continue
            notes = ["vegan"] if "vegan" in types else ["vegetarisch"] if "vegetarisch" in types else []
            if any(t.startswith("mit-") for t in types):
                notes.append("Fleisch")
            price = euro((re.search(r"Stud\.\s*([\d,]+)", text(art)) or [None, ""])[1])
            meals.append({"name": re.sub(r"\s*\([\w,]+\)", "", heads[1]), "category": heads[0], "notes": notes, "prices": {"students": price}})
        if meals:
            city = next((c for c in ("Duisburg", "Mülheim", "Bottrop") if c.lower().replace("ü", "ue") in slug), "Essen")
            out.append({"key": f"essen-duisburg:{slug}", "sw": "essen-duisburg", "name": html.unescape(label).strip(), "city": city, "pos": None,
                        "days": [{"date": today, "meals": meals}]})
    return out


# ---------- Paderborn: the website's own JSON API ----------
def paderborn(start):
    venues = json.loads(get("https://stwpb.de/wp-json/stwk-pb/v1/daily-highlights"))
    slugs = {v["venue_slug"]: v["venue_name"] for v in venues}
    for extra in ("mensa-forum", "mensa", "mensa-lippstadt", "mensa-hamm", "mensa-zm2", "grillcafe", "bona-vista", "picknick"):
        slugs.setdefault(extra, extra)
    out = []
    end = start + dt.timedelta(days=20)
    for slug, name in slugs.items():
        time.sleep(0.3)
        try:
            data = json.loads(get(f"https://stwpb.de/wp-json/stwk-pb/v1/meals?venue={slug}&start_date={start.isoformat()}&end_date={end.isoformat()}"))
        except Exception:  # noqa: BLE001
            continue
        by_day = {}
        for m in data.get("meals") or []:
            by_day.setdefault(m["date"], []).append({"name": html.unescape(m["title"]), "category": m.get("category") or "", "notes": [],
                                                    "prices": {"students": euro(m.get("price_students"))}})
        if by_day:
            city = "Lippstadt" if "lippstadt" in slug else "Hamm" if "hamm" in slug else "Paderborn"
            out.append({"key": f"paderborn:{slug}", "sw": "paderborn", "name": data.get("venue_name") or name, "city": city, "pos": None,
                        "days": [{"date": d, "meals": ms} for d, ms in sorted(by_day.items())]})
    return out


def post_json(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ---------- Chemnitz-Zwickau: the picture menu, which carries the diet icons the OpenMensa feed lacks ----------
CHEMNITZ = {"1479835489": ("Mensa Reichenhainer Straße", "Chemnitz"), "773823070": ("Mensa Straße der Nationen", "Chemnitz"),
            "4": ("Mensa am Ring", "Zwickau"), "3": ("Mensa Scheffelberg", "Zwickau"), "9": ("Mensa Glauchau", "Glauchau")}


def chemnitz_zwickau(start):
    out = []
    for plan, (name, city) in CHEMNITZ.items():
        days = []
        for day in weekdays(start, 10):
            time.sleep(0.3)
            try:
                page = get(f"https://bilderspeiseplan.swcz.de/plan.php?plan={plan}&jahr={day.year}&monat={day.month}&tag={day.day}")
            except Exception:  # noqa: BLE001
                continue
            meals = []
            for item in page.split("<!-- show_one_meal start -->")[1:]:
                item = item.split("<!-- show_one_meal end -->")[0]
                dish = re.sub(r"\s*\([\d,]+\)", "", text((re.search(r'<div class="meal">(.*?)</div>', item, re.S) or [None, ""])[1]))
                if not dish or dish.lower().startswith("kleine portion"):
                    continue
                icons = re.findall(r"images/inhaltsstoffe/([\w-]+)\.png", item)
                notes = ["vegan"] if "vegan" in icons else ["vegetarisch"] if "vegetarisch" in icons else []
                if any(re.match(r"schwein|rind|gefluegel|fisch|wild|lamm", i) for i in icons):
                    notes.append("Fleisch")
                price = re.search(r"S:\s*([\d.]+)", item)
                meals.append({"name": dish, "category": text((re.search(r'<div class="category">(.*?)</div>', item, re.S) or [None, ""])[1]),
                              "notes": notes, "prices": {"students": float(price.group(1)) if price else None}})
            if meals:
                days.append({"date": day.isoformat(), "meals": meals})
        if days:
            out.append({"key": f"chemnitz-zwickau:{plan}", "sw": "chemnitz-zwickau", "name": name, "city": city, "pos": None, "days": days})
    return out


# ---------- Oberfranken: the menu app's own endpoint, one request per canteen and day ----------
def oberfranken(start):
    symbols = {"54": "vegan", "53": "vegetarisch"}
    meat = {"56", "57", "58", "59", "60", "61", "62"}
    places = []
    for town in json.loads(get("https://sls.swo.bayern/api/locations")):
        locs = town["locations"]
        if isinstance(locs, list):
            places += [(x["name_normalized"], x["name"] if town["name"] in x["name"] else f"{x['name']} {town['name']}", town["name"]) for x in locs
                       if not re.search(r"salatbar|frischraum", x["name_normalized"])]
        else:
            places.append((town["name_normalized"], f"Mensa {town['name']}", town["name"]))
    out = []
    for slug, name, city in places:
        days, empty = [], 0
        for day in weekdays(start, 15):
            time.sleep(0.25)
            try:
                rows = post_json("https://sls.swo.bayern/api/meals", {"date": day.isoformat(), "location_name": slug, "categories": ["main"]})
            except Exception:  # noqa: BLE001
                rows = []
            meals = []
            for r in rows:
                ids = set((r.get("essenssymbole") or "").split(","))
                notes = [symbols[i] for i in ("54", "53") if i in ids][:1]
                if ids & meat:
                    notes.append("Fleisch")
                meals.append({"name": r["title"], "category": "Hauptgericht", "notes": notes, "prices": {"students": r.get("student")}})
            if meals:
                days.append({"date": day.isoformat(), "meals": meals})
                empty = 0
            else:
                empty += 1
                if empty >= 6:
                    break
        if days:
            out.append({"key": f"oberfranken:{slug}", "sw": "oberfranken", "name": name, "city": city, "pos": None, "days": days})
    return out


# ---------- Gießen: the website's own day view ----------
def giessen(start):
    page = get("https://www.stwgi.de/speiseplaene")
    out = []
    for city, block in re.findall(r'<optgroup label="([^"]+)">(.*?)</optgroup>', page, re.S):
        for rid, name in re.findall(r'<option value="(\d+)">([^<]+)</option>', block):
            days = []
            for day in weekdays(start, 5):
                time.sleep(0.4)
                try:
                    h = get("https://www.stwgi.de/xhr/speiseplan-wochentag.html", data=urllib.parse.urlencode({"resources_id": rid, "date": day.isoformat()}).encode())
                except Exception:  # noqa: BLE001
                    continue
                meals = []
                for group in h.split('splGroupWrapper')[1:]:
                    cat = text((re.search(r'<div class="splGroup[^"]*">\s*(?:<div class="pl-2">)?([^<]+)', group) or [None, ""])[1])
                    for row in group.split('rowMeal">')[1:]:
                        dish = re.sub(r"\s*\([\w,]+\)", "", text((re.search(r'<span style="font-weight:bold">(.*?)</span>', row, re.S) or [None, ""])[1]))
                        if not dish:
                            continue
                        icons = [i.lower() for i in re.findall(r"class='splIconMeal' alt='([^']*)'", row)]
                        notes = ["vegan"] if "vegan" in icons else ["vegetarisch"] if "vegetarisch" in icons else []
                        if any(re.match(r"rind|schwein|gefl|fisch|lamm|wild", i) for i in icons):
                            notes.append("Fleisch")
                        if "100 g" in text(row)[:400]:
                            continue  # sold by weight: buffets and soups, not dishes
                        if re.search(r"alle aufg|alle ausg|nachmittag|salatbar|information|topping", cat + " " + dish, re.I):
                            cat = "Beilagen"  # offered at every counter: sides, salads, desserts
                        meals.append({"name": dish, "category": cat, "notes": notes, "prices": {"students": euro((re.search(r"Euro\s*([\d,]+)", row) or [None, ""])[1])}})
                if meals:
                    days.append({"date": day.isoformat(), "meals": meals})
            if days:
                out.append({"key": f"giessen:{rid}", "sw": "giessen", "name": html.unescape(name).strip(), "city": city, "pos": None, "days": days})
    return out


# ---------- Koblenz: weekly tables on the website; only plant-based dishes carry a label ("Vegan:") ----------
def koblenz(start):
    pages = {"universitaet-koblenz": ("Mensa Universität Koblenz", "Koblenz"), "hsrmc-koblenz": ("Mensa Hochschule Koblenz", "Koblenz"),
             "hochschule-rac-remagen": ("Mensa RheinAhrCampus", "Remagen")}
    out, year = [], start.year
    for slug, (name, city) in pages.items():
        time.sleep(0.4)
        try:
            page = get(f"https://www.studierendenwerk-koblenz.de/de/essen/mensa/{slug}")
        except Exception:  # noqa: BLE001
            continue
        days = {}
        for table in re.findall(r'<table class="speiseplan kw.*?</table>', page, re.S):
            heads = dict(re.findall(r'<th scope="col" id="(\w+)">(.*?)</th>', table, re.S))
            for row in re.findall(r"<tr><th[^>]*scope=\"row\".*?</tr>", table, re.S):
                d = re.search(r'class="date">(\d+)\.(\d+)\.', row)
                if not d:
                    continue
                date = dt.date(year + (1 if int(d.group(2)) < start.month - 6 else 0), int(d.group(2)), int(d.group(1))).isoformat()
                for theke, cell in re.findall(r'<td headers="\w+ (\w+)">(.*?)</td>', row, re.S):
                    for part in cell.split("<hr>"):
                        dish = text(part.split("<br>")[0])
                        if len(dish) < 4:
                            continue
                        vegan = bool(re.match(r"vegan\s*:", dish, re.I))
                        days.setdefault(date, []).append({"name": re.sub(r"^vegan\s*:\s*", "", dish, flags=re.I), "category": text(heads.get(theke, "")),
                                                          "notes": ["vegan"] if vegan else [], "prices": {"students": None}})
        if days:
            out.append({"key": f"koblenz:{slug}", "sw": "koblenz", "name": name, "city": city, "pos": None,
                        "days": [{"date": d, "meals": ms} for d, ms in sorted(days.items())]})
    return out


# ---------- Göttingen: the website's cached day pages, one page for all canteens ----------
def goettingen(start):
    by = {}
    empty = 0
    for day in weekdays(start, 15):
        time.sleep(0.3)
        try:
            page = get(f"https://www.studierendenwerk-goettingen.de/fileadmin/templates/php/mensaspeiseplan/cached/de/{day.isoformat()}/alle.html")
        except Exception:  # noqa: BLE001
            page = ""
        found = False
        for table in re.findall(r'<table class="sp_tab">(.*?)</table>', page, re.S):
            name = text((re.search(r"<strong>(.*?)</strong>", table, re.S) or [None, ""])[1])
            meals = []
            for typ, bez, hin in re.findall(r'<td class="sp_typ">(.*?)</td><td class="sp_bez">(.*?)</td><td class="sp_hin">(.*?)</td>', table, re.S):
                dish = re.sub(r"\s*\([\w.,]+\)", "", text((re.search(r"<strong>(.*?)</strong>", bez, re.S) or [None, ""])[1]))
                if not dish:
                    continue
                icons = re.findall(r"/(\w+)\.png", hin)
                notes = ["vegan"] if "vegan" in icons else ["vegetarisch"] if "vegetarisch" in icons else []
                if "fleisch" in icons or "fisch" in icons:
                    notes.append("Fleisch")
                meals.append({"name": dish, "category": text(typ), "notes": notes, "prices": {"students": None}})
            if name and meals:
                by.setdefault(name, []).append({"date": day.isoformat(), "meals": meals})
                found = True
        empty = 0 if found else empty + 1
        if empty >= 4:
            break
    return [{"key": "goettingen:" + re.sub(r"\W+", "-", n.lower()).strip("-"), "sw": "goettingen", "name": n, "city": "Göttingen", "pos": None, "days": d}
            for n, d in by.items()]


# ---------- Bremen: the endpoint the website's own menu component calls (the page hands every visitor the key) ----------
def bremen(start):
    page = get("https://www.stw-bremen.de/de/essen-und-trinken/universitaet-bremen/uni-mensa")
    token = re.search(r'data-token="(\w+)"', page).group(1)
    api = re.search(r'data-apiurl="([^"]+)"', page).group(1)
    props = html.unescape(re.search(r'component-url="/_astro/Menu\.[^"]+"[^>]*props="([^"]*)"', page).group(1))
    places = dict((v, t) for t, v in re.findall(r'"title":\[0,"([^"]+)"\],"value":\[0,"(\d+)"\]', props))
    out = []
    for loc, name in places.items():
        days, empty = [], 0
        for day in weekdays(start, 10):
            time.sleep(0.3)
            req = urllib.request.Request(api, data=json.dumps({"action": "meals", "location": loc, "date": day.isoformat()}).encode(),
                                         headers={**UA, "Content-Type": "application/json", "X-Language": "de", "Authorization": "Bearer " + token})
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    rows = json.loads(r.read().decode("utf-8", "replace")).get("result") or []
            except Exception:  # noqa: BLE001
                rows = []
            meals = []
            for m in rows:
                adds = {a.strip() for a in (m.get("mealadds") or "").split(",")}
                notes = ["vegan"] if "VG" in adds else ["vegetarisch"] if "VT" in adds else []
                if adds & {"G", "R", "S", "F", "L", "W"}:
                    notes.append("Fleisch")
                title = ", ".join(i["label"].strip() for i in m.get("ingredients") or [] if i.get("label", "").strip()) or m.get("title") or ""
                cat = m.get("counter") or ""
                if cat == "KombinierBar" and not (m.get("kombicategory") or "").startswith("Hauptkomp"):
                    cat = "Beilagen"
                price = next((p["price"].strip() for p in m.get("prices") or [] if p.get("label") == "Studierende"), "")
                meals.append({"name": title, "category": cat, "notes": notes, "prices": {"students": float(price) if re.fullmatch(r"[\d.]+", price) else None}})
            if meals:
                days.append({"date": day.isoformat(), "meals": meals})
                empty = 0
            else:
                empty += 1
                if empty >= 4:
                    break
        if days:
            out.append({"key": f"bremen:{loc}", "sw": "bremen", "name": name, "city": "Bremerhaven" if "Bremerhaven" in name else "Bremen", "pos": None, "days": days})
    return out


# ---------- Halle: the menu form embedded in the website (meine-mensa.de), one request per day for all canteens ----------
def halle(start):
    import http.cookiejar
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = list(UA.items())
    url = "https://meine-mensa.de/speiseplan_iframe"
    page = opener.open(url, timeout=40).read().decode("utf-8", "replace")
    token = re.search(r'name="_token" value="([^"]+)"', page).group(1)
    places = dict(re.findall(r'name="location_ids\[\]"\s+value="(\d+)">\s*([^<]+?)\s*</div>', page))
    cities = {"Köthen": "Köthen", "Bernburg": "Bernburg", "Dessau": "Dessau", "Merseburg": "Merseburg"}
    by = {}
    for day in weekdays(start, 10):
        if day < dt.date.today() - dt.timedelta(days=dt.date.today().weekday()):
            continue
        time.sleep(0.5)
        form = [("_token", token), ("date", day.isoformat()), ("week", str(day.isocalendar()[1]))] + [("location_ids[]", i) for i in places]
        try:
            res = opener.open(url, data=urllib.parse.urlencode(form).encode(), timeout=60).read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        for block in re.split(r"<h5>\s*Speiseplan\s+", res)[1:]:
            name = text(block.split("</h5>")[0])
            meals = []
            for item in block.split("food-container")[1:]:
                dish = text((re.search(r'class="food_title">(.*?)</p>', item, re.S) or [None, ""])[1])
                if not dish:
                    continue
                icons = [i.lower() for i in re.findall(r'pikt_\w+?_128px\.png"\s+title="([^"]*)"', item)]
                notes = ["vegan"] if "vegan" in icons else ["vegetarisch"] if "vegetarisch" in icons else []
                if any(re.match(r"schwein|rind|gefl|fisch|wild|lamm", i) for i in icons):
                    notes.append("Fleisch")
                price = euro((re.search(r'prices mb-1"\s*>\s*([\d,]+)', item) or [None, ""])[1])
                meals.append({"name": dish, "category": "", "notes": notes, "prices": {"students": price}})
            if name and meals:
                by.setdefault(name, []).append({"date": day.isoformat(), "meals": meals})
    return [{"key": "halle:" + re.sub(r"\W+", "-", n.lower()).strip("-"), "sw": "halle", "name": n, "city": next((c for k, c in cities.items() if k in n), "Halle"),
             "pos": None, "days": d} for n, d in by.items()]


# ---------- Osnabrück: the menu embedded in the website, one request per canteen and day ----------
OSNABRUECK = {"7": ("Mensa Schlossgarten", "Osnabrück"), "1": ("Mensa am Westerberg", "Osnabrück"), "5": ("Bistro Caprivi", "Osnabrück"),
              "3": ("Mensa Haste", "Osnabrück"), "4": ("Mensa Vechta", "Vechta"), "9": ("Mensa Lingen", "Lingen")}


OSNABRUECK_MEAT = {"13", "14", "40", "43", "44"}  # pork, beef, poultry, fish, game in the page legend


def osnabrueck(start):
    out = []
    for loc, (name, city) in OSNABRUECK.items():
        days, empty = [], 0
        for day in weekdays(start, 10):
            if day < dt.date.today():
                continue
            time.sleep(0.4)
            try:
                page = get("https://sw-osnabrueck.maxmanager.xyz/inc/ajax-php_konnektor.inc.php",
                           data=urllib.parse.urlencode({"func": "make_spl", "locId": loc, "date": day.isoformat(), "lang": "de"}).encode())
            except Exception:  # noqa: BLE001
                page = ""
            meals = []
            for block in re.split(r'kategorietitel">', page)[1:]:
                cat = text(block.split("</div>")[0])
                for item in re.split(r'class="row artikel"', block)[1:]:
                    body = (re.search(r'class="artikeltext".*?<div style=\'display: inline-block[^>]*>(.*?)</div>', item, re.S) or [None, ""])[1]
                    dish = re.sub(r"\s*\([\w,]+\)", "", text(re.sub(r"<img[^>]*>", "", body)))
                    if not dish:
                        continue
                    icons = set(re.findall(r"assets/icons/(\d+)\.png[^>]*class='piktogramm'", item))
                    notes = ["vegan"] if "21" in icons else ["vegetarisch"] if "20" in icons else []
                    if icons & OSNABRUECK_MEAT:
                        notes.append("Fleisch")
                    price = euro((re.search(r"preisHeaderMobil\">[^<]*</span>\s*([\d,]+)", item) or [None, ""])[1])
                    meals.append({"name": dish, "category": cat, "notes": notes, "prices": {"students": price}})
            if meals:
                days.append({"date": day.isoformat(), "meals": meals})
                empty = 0
            else:
                empty += 1
                if empty >= 4:
                    break
        if days:
            out.append({"key": f"osnabrueck:{loc}", "sw": "osnabrueck", "name": name, "city": city, "pos": None, "days": days})
    return out


# ---------- Ost:Brandenburg: the menu app linked from the website (webspeiseplan), three weeks per site ----------
def ost_brandenburg(start):
    host = "https://mensatime.webspeiseplan.de"
    token = re.search(r'PROXY_TOKEN:"(\w+)"', get(f"{host}/index.js")).group(1)  # the app's own client key, the same for every visitor

    def q(model, loc=""):
        raw = get(f"{host}/index.php?token={token}&model={model}&location={loc}&languagetype=1", headers={"Referer": f"{host}/menu", "X-Requested-With": "XMLHttpRequest"})
        return json.loads(raw).get("content") or []

    cities = {10901: "Frankfurt (Oder)", 10902: "Eberswalde", 10903: "Cottbus"}
    out = []
    for loc in q("location"):
        time.sleep(0.4)
        features = {str(f["id"]): (f.get("name") or "").lower() for f in q("features", loc["id"])}
        cats = {c["id"]: c.get("name") or "" for c in q("mealCategory", loc["id"])}
        outlets = {o["id"]: o.get("name") or "" for o in q("outlet", loc["id"])}
        by = {}
        for plan in q("menu", loc["id"]):
            oid = plan["speiseplanAdvanced"].get("outletID")
            if "kita" in outlets.get(oid, "").lower():
                continue
            for g in plan.get("speiseplanGerichtData") or []:
                dish = g["speiseplanAdvancedGericht"]
                marks = [features.get(i.strip(), "") for i in (g.get("gerichtmerkmaleIds") or "").split(",")]
                notes = ["vegan"] if "vegan" in marks else ["vegetarisch"] if "vegetarisch" in marks else []
                if any(mk in ("rind", "schwein", "fisch", "geflügel", "lamm", "wild") for mk in marks):
                    notes.append("Fleisch")
                cat = cats.get(dish.get("gerichtkategorieID"), "")
                if re.search(r"komponente|hauptkompo|info|buffet", cat, re.I):
                    cat = "Beilagen"
                by.setdefault(oid, {}).setdefault(dish["datum"][:10], []).append(
                    {"name": dish.get("gerichtname") or "", "category": cat, "notes": notes,
                     "prices": {"students": (g.get("zusatzinformationen") or {}).get("mitarbeiterpreisDecimal2")}})
        for oid, days in by.items():
            name = outlets.get(oid) or f"Mensa {oid}"
            out.append({"key": f"ost-brandenburg:{oid}", "sw": "ost-brandenburg", "name": name,
                        "city": "Senftenberg" if "Senftenberg" in name else cities.get(loc["id"], loc["name"]), "pos": None,
                        "days": [{"date": d, "meals": ms} for d, ms in sorted(days.items())]})
    return out


READERS = {"muenchen": muenchen, "ostniedersachsen": ostniedersachsen, "bodensee": bodensee,
           "rostock-wismar": rostock_wismar, "vorderpfalz": vorderpfalz,
           "bonn": bonn, "dortmund": dortmund, "duesseldorf": duesseldorf, "essen-duisburg": essen_duisburg, "paderborn": paderborn,
           "chemnitz-zwickau": chemnitz_zwickau, "oberfranken": oberfranken, "giessen": giessen, "koblenz": koblenz, "goettingen": goettingen, "bremen": bremen, "halle": halle, "osnabrueck": osnabrueck, "ost-brandenburg": ost_brandenburg,
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
