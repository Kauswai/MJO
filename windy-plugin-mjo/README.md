# windy-plugin-mjo — MJO phase & forecast for Windy.com

A [Windy.com](https://www.windy.com) plugin that shows the **Madden–Julian Oscillation (MJO)**:

- **Interactive Wheeler–Hendon phase diagram** (RMM1 × RMM2) with the 8 octants / phases,
  the weak‑MJO unit circle and the four region labels. You can
  - hover any point for date, phase, amplitude, RMM1/RMM2
  - click a day to select it (and move Windy's timeline to it for forecast days)
  - click an octant to highlight that phase's region on the main map
  - scroll to zoom, drag to pan, double‑click (or ⟲) to reset
- **Current position**: latest analysis (yesterday's daily mean) shown as the white
  "now" dot in the diagram, as the phase badge in the pane, and as the enhanced/suppressed
  convective envelopes along the equator on the **main Windy map**.
- **GEFS 31‑member ensemble forecast to +7 days**: member trajectories (orange), ensemble
  mean (yellow, numbered by forecast day), spread cloud, and per‑phase member probabilities.
  On the map: ensemble‑mean track of the envelope centre plus each member's position.
- **Follows Windy's timeline**: scrub the timeline and the map/diagram jump to that day.
- Optional overlay of the **official BoM RMM** series and of the **8 phase regions** on the map.

> Map positions are approximate. RMM only gives the phase angle, which is converted to the
> longitude of enhanced convection (phase 1 ≈ Africa, 2–3 Indian Ocean, 4–5 Maritime
> Continent, 6–7 West Pacific, 8 Western Hemisphere).

## How it works

```
┌──────────────── GitHub Actions (daily) ────────────────┐       ┌──── windy.com ────┐
│ pipeline/mjo_pipeline.py                               │       │ windy-plugin-mjo  │
│  • CPC blended OLR (NOAA PSL OPeNDAP)                   │       │  fetch mjo.json   │
│  • GEFS control analyses U850/U200 (AWS open data)     │──────▶│  phase diagram    │
│  • GEFS 31 members, 0–192 h, OLR/U850/U200 (AWS)       │ Pages │  map overlay      │
│  • WH04 RMM projection → mjo.json                      │ (CORS)│                   │
└────────────────────────────────────────────────────────┘       └───────────────────┘
```

No public service publishes ensemble RMM *numbers* (CPC, ECMWF and BoM only publish
plots), and the BoM file isn't readable from a browser (no CORS), so a small pipeline
computes the index itself:

1. 15°S–15°N means of OLR, U850 and U200 on 144 longitudes (2.5°)
2. anomalies relative to the 1991–2020 daily climatology (mean + 3 harmonics)
3. minus the mean of the previous 120 days (for forecast days this window
   includes the earlier forecast days; Gottschalck et al. 2010)
4. normalised and projected onto the two combined RMM EOFs
5. linearly calibrated to the official BoM RMM (`pipeline/calibrate.py`)

Latest OLR days not yet in CPC's record (~4‑day lag) are filled with the GEFS control's
0–24 h OLR, bias‑corrected over the previous 21 days; the same bias correction is
applied to the forecast OLR.

**Verification (4 Oct 2026 run):** over the 79 days overlapping the official BoM series,
the computed analysis has correlation 0.98 (RMM1) / 0.97 (RMM2), RMSE 0.17 / 0.13 and the
same phase on 94 % of days with amplitude > 1. Calibration period 2023–2025:
r = 0.97 / 0.98.

## Setup

### 1. Publish the data (GitHub Pages)

The workflows live at the repository root (`.github/workflows/`) and run inside
`windy-plugin-mjo/`.

1. The repository must be **public** (GitHub Pages on free accounts needs that).
2. *Settings → Pages → Build and deployment → Source: **GitHub Actions***.
3. *Actions → update-mjo-data → Run workflow* (it then runs daily at 06:40 and 13:40 UTC).
   The first run downloads ~1 GB from AWS (~5–10 min); later runs use the cache.
4. The data is then at <https://kauswai.github.io/MJO/mjo.json>, which is already the
   plugin's `DEFAULT_DATA_URL` ([src/mjo.ts](src/mjo.ts)). Users can change the URL in the
   plugin under *Data source*.

### 2. Develop the plugin

```bash
npm i
npm run data      # optional: build public/mjo.json locally (needs Python + pipeline/requirements.txt)
npm start         # serves https://localhost:9999/plugin.js (+ mjo.json)
```

Open <https://localhost:9999/plugin.js> once and accept the self‑signed certificate, then go
to <https://www.windy.com/developer-mode> and load `https://localhost:9999/plugin.js`.
Without a configured data URL the plugin falls back to `https://localhost:9999/mjo.json`.

On Windows use `npm run build:win` instead of `npm run build`.

### 3. Publish the plugin

Add a `WINDY_API_KEY` repository secret and run the **publish-plugin** workflow (or
see <https://docs.windy-plugins.com/>). Optionally add `src/screenshot.jpg` for the gallery.

## Pipeline files

| File | Purpose |
| --- | --- |
| `pipeline/mjo_pipeline.py` | daily job → `mjo.json` |
| `pipeline/calibrate.py` | fits `calibration.json` against BoM RMM (run once) |
| `pipeline/calibration.json` | fitted 2×2 matrix (EOF projections → RMM) |
| `../.github/workflows/update-mjo-data.yml` | schedule + GitHub Pages deploy |

```bash
pip install -r pipeline/requirements.txt
python pipeline/mjo_pipeline.py --out public/mjo.json --cache .cache
```

## Data sources & credits

- NOAA/NCEP **GEFS** via the [NOAA Open Data Dissemination program on AWS](https://registry.opendata.aws/noaa-gefs/)
- NOAA **CPC blended OLR** and NCEP/NCAR reanalysis climatology, from NOAA PSL
- RMM EOFs: [`pyMTDG`](https://github.com/MJO-Teleconnection-Diagnostics/pyMTDG) `MJO/ceof.nc`
  (downloaded at run time, not redistributed)
- Official RMM series: Australian Bureau of Meteorology
- Wheeler, M. C. & Hendon, H. H. (2004), *Mon. Wea. Rev.* 132, 1917–1932
- Gottschalck, J. et al. (2010), *BAMS* 91, 1247–1258

`mjo.json` format: `analysis.days[] {d, x: RMM1, y: RMM2}`, `bom.days[]` (same),
`forecast {init, dates[], memberNames[], members[member][day] = [RMM1, RMM2], mean[day]}`.
