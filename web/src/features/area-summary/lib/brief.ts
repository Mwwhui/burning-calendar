import { formatInt, MONTHS_LONG, monthSpan, ordinal } from "@/lib/format";
import type { Summary } from "@/lib/data/types";

/**
 * Plain-language summary of an area, written from the exported numbers with
 * fixed templates (no AI, so every sentence can be traced to a number).
 */
export function fireBrief(name: string, s: Summary, unit: string, enso?: string, asia = true): string[] {
  const out: string[] = [];
  const span = monthSpan(s.throughMonth);
  if (s.thisYearToDate !== null) {
    let first = `${name} recorded ${formatInt(s.thisYearToDate)} ${unit} in ${span} ${s.thisYear}`;
    if (s.pctVsMedian !== null && Math.abs(s.pctVsMedian) >= 5) {
      const dir = s.pctVsMedian > 0 ? "above" : "below";
      first += `, ${Math.round(Math.abs(s.pctVsMedian))} % ${dir} the median year`;
    } else if (s.pctVsMedian !== null) {
      first += ", close to the median year";
    }
    first += ` — the ${ordinal(s.rank)} highest of ${s.nYears} years for these months.`;
    out.push(first);
  }
  if (s.peakShare !== null) {
    out.push(
      `Burning usually peaks in ${MONTHS_LONG[s.peakMonth - 1]}, which holds about ` +
        `${Math.round(s.peakShare * 100)} % of a typical year's fire.`,
    );
  }
  if (s.busiestYear !== null) {
    let b = `The busiest year on record was ${s.busiestYear} (${formatInt(s.busiestYearTotal)} ${unit}`;
    b += s.busiestYearEstimated ? ", partly estimated from older satellites)" : ")";
    if (s.busiestTies.length) {
      const ties = s.busiestTies.slice(0, 3).join(", ");
      b += `; within the uncertainty, ${ties} ${s.busiestTies.length === 1 ? "may" : "may also"} have been as busy`;
    }
    out.push(`${b}.`);
  }
  if (enso === "El Niño" && asia) {
    out.push(`${s.thisYear} is an El Niño year; these usually bring drier, more fire-prone seasons to Southeast Asia.`);
  } else if (enso === "El Niño") {
    out.push(`${s.thisYear} is an El Niño year; these usually bring more rain to northeast Argentina and the Pampas.`);
  } else if (enso === "La Niña" && !asia) {
    out.push(`${s.thisYear} is a La Niña year; these usually bring drier seasons to northeast Argentina and the Pampas.`);
  } else if (enso) {
    out.push(`${s.thisYear} is a ${enso} year.`);
  }
  return out;
}
