"""burncal: harmonize NASA FIRMS MODIS + VIIRS hotspots into one burning calendar.

Modules
-------
config     Settings, platform names, default harmonization chain
io         Load FIRMS CSVs (archive/API, SP/NRT) into one standard table; demo data
clean      Confidence, type and bounding-box filters
aggregate  Local solar dates, ~1 km cell-days, monthly counts per platform
harmonize  M0-M4 methods and the reference-filling chain with uncertainty bands
benchmark  Hold-out / leave-one-year-out scoring, seam, placebo and drift tests
calendar   Year x month grids, anomalies, season-to-date, plotting
pipeline   End-to-end run used by scripts and notebooks
"""

__version__ = "0.2.0"
