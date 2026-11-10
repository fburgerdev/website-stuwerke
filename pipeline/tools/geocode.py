"""Look up positions for canteens whose source gives none (run by hand, about one request a second).

Uses OpenStreetMap's Nominatim search. Results go to data/positions.json; a canteen that could not be
found is stored as null so it is not asked for again. update.py fills these positions in.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POS = os.path.join(ROOT, "data", "positions.json")
UA = {"User-Agent": "website-stuwerke (github.com/fburgerdev/website-stuwerke)"}


def search(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 3, "countrycodes": "de"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    canteens = json.load(open(os.path.join(ROOT, "data", "canteens.json")))
    known = json.load(open(POS)) if os.path.exists(POS) else {}
    todo = [(k, c) for k, c in canteens.items() if c.get("source") == "website" and not c.get("pos") and k not in known]
    print(len(todo), "canteens to look up")
    for key, c in todo:
        name = re.sub(r"\(.*?\)|[–-]\s*campus streetfood.*", "", c["name"]).strip()
        city = c.get("city") or ""
        hit = None
        for q in ([f"{name}, {city}"] if city.lower() in name.lower() else [f"{name}, {city}", f"{name} {city}"]):
            time.sleep(1.1)
            try:
                res = search(q)
            except Exception as e:  # noqa: BLE001
                print("  error", key, e)
                res = []
            res = [r for r in res if city.split(" ")[0].lower() in r.get("display_name", "").lower()
                   and r.get("class") in ("amenity", "building", "office", "shop", "tourism", "leisure", "place")
                   and r.get("addresstype") not in ("city", "town", "village", "suburb", "state", "county")]
            if res:
                hit = [round(float(res[0]["lat"]), 5), round(float(res[0]["lon"]), 5)]
                break
        known[key] = hit
        print(" ", key, c["name"], "->", hit)
        json.dump(known, open(POS, "w"), ensure_ascii=False, indent=0, sort_keys=True)


if __name__ == "__main__":
    main()
