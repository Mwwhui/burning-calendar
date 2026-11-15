export const MONTHS_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

export const MONTHS_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
] as const;

const intFmt = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });

/** 12,345 */
export function formatInt(x: number | null | undefined): string {
  return x === null || x === undefined || !Number.isFinite(x) ? "–" : intFmt.format(x);
}

/** Short number for small cells: 950, 1.3k, 12k, 1.2M. */
export function formatCompact(x: number | null | undefined): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "";
  const a = Math.abs(x);
  if (a < 1000) return String(Math.round(x));
  if (a < 10_000) return `${(x / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  if (a < 1_000_000) return `${Math.round(x / 1000)}k`;
  return `${(x / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
}

/** +24 % / −17 % (true minus sign). */
export function formatPct(x: number | null | undefined, digits = 0): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "–";
  const v = Math.abs(x).toFixed(digits);
  if (Number(v) === 0) return "0 %";
  return `${x > 0 ? "+" : "−"}${v} %`;
}

/** 1st, 2nd, 3rd, 4th, 11th, 21st */
export function ordinal(n: number): string {
  const s = n % 100;
  if (s >= 11 && s <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

/** "2026-03" -> "Mar 2026"; "2026" -> "2026" */
export function formatPeriod(period: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(period);
  if (!m) return period;
  return `${MONTHS_SHORT[Number(m[2]) - 1]} ${m[1]}`;
}

/** "Jan–Oct" (or "Jan" for one month) */
export function monthSpan(through: number): string {
  return through <= 1 ? "Jan" : `Jan–${MONTHS_SHORT[through - 1]}`;
}

/** "2026-11-11" -> "11 Nov 2026" */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS_SHORT[m - 1]} ${y}`;
}
