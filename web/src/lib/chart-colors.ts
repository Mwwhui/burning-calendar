/** Fixed chart colours (colourblind-safe pairs; the same in light and dark mode). */
export const C = {
  measured: "#e4572e",
  estimated: "#f4a259",
  highlight: "#c81d25",
  typical: "#94a3b8",
  other: "#64748b",
  peatOn: "#8c510a",
  peatOff: "#dfc27d",
  less: "#4393c3",
  more: "#b2182b",
  neutral: "#9ca3af",
  sat: {
    Terra: "#1b9e77",
    Aqua: "#7570b3",
    SNPP: "#e7298a",
    NOAA20: "#66a61e",
    NOAA21: "#e6ab02",
  } as Record<string, string>,
  rank: ["#e66101", "#fdb863", "#b2abd2"],
};

export const SAT_NAME: Record<string, string> = {
  Terra: "Terra (MODIS)",
  Aqua: "Aqua (MODIS)",
  SNPP: "Suomi NPP (VIIRS)",
  NOAA20: "NOAA-20 (VIIRS)",
  NOAA21: "NOAA-21 (VIIRS)",
};
