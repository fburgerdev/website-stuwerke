# Plant-based Mensa Tracker

How plant-based are Germany's university canteens? A self-updating map of all 57 Studierendenwerke.

- `pipeline/update.py` reads menus from [OpenMensa](https://openmensa.org), classifies main dishes and stores weekly counts in `data/weekly.json`.
- `pipeline/readers.py` reads menus straight from the websites of Studierendenwerke that have no working OpenMensa feed (23 readers so far). No AI involved. Their menus are stored per day in `data/daily.json`, so sources that only show today still add up to full weeks.
- Each reader runs as often as its source publishes ahead: `data/sources.json` records how far ahead menus were published and when the reader is due next (once the published days run out, at the latest after a week). A reader that failed is tried again every day, before the others. `python pipeline/update.py --all-readers` ignores the schedule; `--readers bonn,halle` runs single ones.
- `pipeline/tools/geocode.py` looks up positions for canteens whose source gives none (run by hand; results in `data/positions.json`).
- `data/peta.json` holds PETA Deutschland's 2026 canteen ranking as far as it could be read from their results page; it is shown as one line in a Studierendenwerk's details.
- Still without menu data: Siegen (its website blocks the address the readers were developed from, so no reader exists yet).
- `pipeline/tools/find_contacts.py` scans the 57 websites for published sustainability contacts and prints candidates to review by hand.
- `pipeline/build.py` turns those counts and the reference file `data/stuwerke.json` into `docs/data.json`.
- `docs/` is the static site (GitHub Pages). No build step, no dependencies.
- `.github/workflows/update.yml` runs both scripts every day and commits the result.

`data/stuwerke.json`, `data/umbrella.json` and `data/highlights.json` are curated by hand or by a research agent: universities served, published contacts, decisions and announcements, each with a source.

Run locally:

```
python pipeline/update.py --weeks 4
python pipeline/build.py
python -m http.server -d docs
```

The numbers show dishes offered, not dishes sold. See the Method section on the site.
