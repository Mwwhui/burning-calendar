"use client";

/** Image downloads: the map with a title and credits, and any part of the page as PNG. */

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

export function downloadDataUrl(filename: string, dataUrl: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export interface MapImageText {
  title: string;
  subtitle: string;
  legend?: string;
  credit: string;
}

/** The map image framed with a title above and the legend line and credits below. */
export async function composeMapImage(mapDataUrl: string, t: MapImageText): Promise<string> {
  const img = await loadImage(mapDataUrl);
  const scale = Math.max(1, img.width / 1400);
  const pad = 24 * scale;
  const head = 78 * scale;
  const foot = 56 * scale;
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height + head + foot;
  const g = c.getContext("2d")!;
  g.fillStyle = "#ffffff";
  g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = "#111827";
  g.font = `600 ${26 * scale}px system-ui, sans-serif`;
  g.fillText(t.title, pad, 36 * scale);
  g.fillStyle = "#4b5563";
  g.font = `${16 * scale}px system-ui, sans-serif`;
  g.fillText(t.subtitle, pad, 62 * scale);
  g.drawImage(img, 0, head);
  g.fillStyle = "#374151";
  g.font = `${14 * scale}px system-ui, sans-serif`;
  if (t.legend) g.fillText(t.legend, pad, head + img.height + 24 * scale);
  g.fillStyle = "#6b7280";
  g.font = `${12 * scale}px system-ui, sans-serif`;
  g.fillText(t.credit, pad, head + img.height + 44 * scale);
  return c.toDataURL("image/png");
}

/** A DOM element as PNG (charts, calendar, panels). */
export async function elementToPng(el: HTMLElement, filter?: (node: HTMLElement) => boolean): Promise<string> {
  const { toPng } = await import("html-to-image");
  const bg = getComputedStyle(document.body).backgroundColor || "#ffffff";
  return toPng(el, {
    pixelRatio: 2,
    backgroundColor: bg,
    cacheBust: true,
    filter: filter ? (n) => !(n instanceof HTMLElement) || filter(n) : undefined,
  });
}
