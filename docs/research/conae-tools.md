# CONAE fire tools: what they are and how this project relates to them

The challenge was written by CONAE (Comisión Nacional de Actividades Espaciales, Argentina) and asks
participants to use its tools alongside FIRMS. Reviewed 12 Nov 2026 from the user manual
"Consultas Interactivas: Incendios" (CONAE_AQUA-TERRA-NOAA20_MODIS-VIIRS_FC_VISOR_ManualUsuarios_e02,
9 Aug 2024): https://catalogos5.conae.gov.ar/catalogofocos

## What the tool does

- **Hotspots ("focos de calor")** from Aqua and Terra MODIS (CONAE's own processing) and S-NPP / NOAA-20
  VIIRS (from FIRMS), near real time (within 3 hours).
- **Coverage: Argentina only until 2017 (MODIS) / Nov 2023 (VIIRS), then part of South America down
  to 5.7° S.** Southeast Asia is not covered, so its data cannot be used here.
- Query by satellite, dates and **confidence** (default 80 %).
- Area: **draw** a box (or type its corner coordinates) or pick **province / department**.
- Output: **Detalle** (every hotspot: satellite, instrument, lat/lon, brightness temperatures, FRP,
  confidence, scan/track; CSV) or **Totalizar** (counts for the whole period or per month, per province
  or department; CSV or shapefile). Up to 400,000 hotspots per query; download needs a free account.
- **Statistical charts** of the results.
- **Monthly burned area** per province and department from MODIS MCD64A1 (added in edition e02).
- Each satellite is reported separately: no harmonization between MODIS and VIIRS (the gap the
  challenge asks participants to close).

## How this project maps to it

| CONAE tool | This app |
|---|---|
| Satellite choice, each counted separately | All satellites joined into one comparable record (NOAA-20-equivalent), raw counts per satellite still downloadable |
| Dates | Sidebar dates; Selected dates tab compares them with the same dates in every year |
| Draw a box / coordinates | Own area: drawing (lasso/box), circle, box by coordinates |
| Province / department | Country → state/province → district (Malaysia) |
| Detalle (CSV) | Download → individual fire detections (CSV) |
| Totalizar per area and month (CSV / shapefile) | Download → totals per state/district and month (CSV) and map layer (GeoJSON) |
| Statistical charts | Calendar, yearly totals, this year vs past years, fire events |
| Monthly burned area (MCD64A1) | Checks tab: GFED5 burned area (MODIS-based) against the record |
| Confidence filter (default 80 %) | Fixed cleaning: MODIS confidence ≥ 30, VIIRS nominal/high (documented in decisions.md) |

## What could still be done

- Run this harmonization on Argentina with CONAE's hotspot downloads and compare with the CONAE
  province totals (needs a CONAE account; the method code is region-independent).
- Offer a shapefile in addition to GeoJSON for users whose GIS workflow expects it.
- Watch the CONAE tutorials listed on the challenge page and note any features not covered above.
