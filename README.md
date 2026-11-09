# Plant-based Mensa Tracker

How plant-based are Germany's university canteens? A self-updating map of all 57 Studierendenwerke.

- `pipeline/update.py` reads menus from [OpenMensa](https://openmensa.org), classifies main dishes and stores weekly counts in `data/weekly.json`.
- `pipeline/build.py` turns those counts and the reference file `data/stuwerke.json` into `docs/data.json`.
- `docs/` is the static site (GitHub Pages). No build step, no dependencies.
- `.github/workflows/update.yml` runs both scripts every day and commits the result.

`data/stuwerke.json` and `data/umbrella.json` are curated by hand or by a research agent: universities served, published contacts, decisions and announcements, each with a source.

Run locally:

```
python pipeline/update.py --weeks 4
python pipeline/build.py
python -m http.server -d docs
```

The numbers show dishes offered, not dishes sold. See the Method section on the site.
