# Burning Calendar — web app

Map-first web app for the harmonized burning activity record. Next.js 16 (App Router,
static export), MapLibre GL v5 + deck.gl 9, TanStack Query, Zustand, Tailwind CSS v4,
shadcn/ui and shadcn charts (Recharts). No server: every number comes from JSON files
exported by the Python package.

MapLibre is pinned to v5 because deck.gl 9.4's interleaved mode (fire drawn under the
basemap's place labels) does not work with MapLibre v6 yet.

## Run it

```bash
# 1. export the data (from the repository root)
python scripts/export_web.py                    # all areas, ~30-60 min
python scripts/export_web.py --countries MYS    # quick: groups + Malaysia only

# 2. start the app (from web/)
npm install
npm run dev          # http://localhost:3000
npm run build        # static site in out/
npm run preview      # serve out/
npm test             # unit tests (Vitest)
npm run typecheck
npm run lint
```

`public/data/`, `public/detections/` (exported data) and `public/vendor/` (DuckDB-wasm engine, copied by
`scripts/copy-vendor.mjs` before dev/build) are generated, not committed. `/report/?id=<area>` is the printable
PDF report.

## Structure

```
src/
  app/                          routing only
    layout.tsx                  root: fonts, providers, header
    providers.tsx               theme, TanStack Query, tooltips
    (explorer)/layout.tsx       map-first shell; the map stays mounted between areas
    (explorer)/[[...area]]/     one static page per area: /, /mys/, /mys/sarawak/, ...
    method/                     how the record is built
  features/                     one folder per feature (components, hooks, lib, tests)
    explorer/                   shell layout, map toolbar, UI store, current/own-area hooks
    map/                        MapLibre basemap + deck.gl layers (glow, heat, 3D, borders, drawing, events)
    playback/                   timeline bar, play ticker, frame indexing
    area-summary/               right panel with tabs: headline, metrics, fire brief
    calendar/ trends/ dates/    calendar heatmap (amount / unusual), cumulative + yearly, date ranges
    events/ outlook/ peat/      fire events, seasonal outlook, peat split
    checks/ method/ downloads/  official + GFED5 + ASMC, satellites and technical steps, CSV/GeoJSON
    sub-areas/ area-search/     ranked states / districts, Ctrl+K search
  components/ui/                shadcn/ui primitives (incl. chart)
  components/common/            panel sections, callouts, stats
  components/layout/            header, theme toggle
  lib/                          shared, framework-free code
    data/                       JSON types, URLs, query hooks, build-time reader
    analytics/                  ports of burncal maths (anomalies, season-to-date, date windows, own areas)
    area.ts format.ts colors.ts chart-colors.ts csv.ts
```

Dependencies point one way: `app/` → `features/` → `components/`, `lib/`. Features import
each other only through their components or hooks.

## Data contract

`scripts/export_web.py` writes, per area id (URL path, `_all` for Asia):

| file | content |
| --- | --- |
| `index.json` | area tree, bounding boxes, last data day, ENSO years |
| `area/<id>.json` | monthly series with likely range, yearly totals, headline numbers, notes, sub-area change |
| `frames/<id>.year.json`, `.month.json` | playback cells per period (columnar) |
| `geo/<id>.json` | simplified borders of the sub-areas |
| `detail/<id>.json` | raw satellites, conversion steps, seams, satellite differences, outlook, peat, checks |
| `events/<id>.json` | fire events (burning now, biggest this year / on record), size curve |
| `daily/<id>.json` | daily cell-days per satellite (date ranges) |
| `totals/<id>.json` | raw monthly fire days per sub-area and satellite |
| `cells/<iso>.json` | the country's harmonized monthly fire days per 0.1° cell (drawn areas) |
| `asmc.json` | ASMC haze review links per month |
| `recent/<iso>.json` | latest real detections (last 60 days) |
| `land/<id>.json`, `land/_concessions.json` | fire inside concessions per year and per licence; licence outlines |
| `../detections/<iso>/<year>.parquet` | cleaned detections for the hotspot CSV, queried in the browser with DuckDB-wasm (`scripts/export_points.py`) |
| `spots/<id>.json` | repeat burn spots (~2 km places by years with fire since 2012) |

Types: `src/lib/data/types.ts`. Change both sides together.

## Notes

- `scripts/fix-export-windows.mjs` (runs after `npm run build`) works around a Next.js 16
  static-export bug on Windows, which writes prefetch files into nested folders. It does
  nothing on Linux/macOS.
- Basemaps: CARTO Dark Matter / Positron (no API key; © OpenStreetMap contributors, © CARTO).
- Haze and smoke: NASA GIBS daily Deep Blue aerosol optical depth (VIIRS / MODIS) and OMPS UV aerosol index,
  recoloured in the browser from the GIBS colour tables (`src/lib/haze-colormaps.ts`) into a violet veil.
- Fire-event squares: `public/data/event-dots/<id>.json`, written by `scripts/build_event_dots.py`.
- Satellite photos: NASA GIBS WMTS (`src/lib/gibs.ts`, no API key, CORS-enabled): daily VIIRS / MODIS
  Corrected Reflectance true colour and 30 m HLS Landsat / Sentinel-2. For a fire, the photo bar finds days
  with a 30 m picture by fetching the zoom-12 tile over the fire for each day (empty tiles are under 5 KB).
