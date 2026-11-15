import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Method",
  description: "How MODIS and VIIRS fire detections are merged into one consistent NOAA-20-equivalent record.",
};

const STEPS = [
  ["NOAA-20 VIIRS (2018–)", "Measured directly. This is the reference series: Suomi NPP stopped delivering data on 2 Nov 2026."],
  ["Suomi NPP VIIRS (2012–2018)", "Converted to NOAA-20 terms, calibrated where both satellites overlap (Apr 2018 – Oct 2026)."],
  ["NOAA-21 VIIRS", "Fills NOAA-20 outage gaps."],
  ["Aqua + Terra MODIS (2002–2012)", "Average of the Aqua and Terra conversions, calibrated 2012–2020, before their orbits drifted; chosen because it predicted held-back years best."],
  ["Terra MODIS alone (2000–2002)", "Before Aqua launched, Terra gets its own calibration step (Jul 2002 – Jun 2005)."],
];

export default function MethodPage() {
  return (
    <main className="flex-1 overflow-y-auto">
      <article className="mx-auto max-w-2xl space-y-6 px-4 py-10 text-[15px] leading-relaxed">
        <header className="space-y-2">
          <p className="text-sm text-muted-foreground">
            <Link href="/" className="underline">
              Map
            </Link>{" "}
            › Method
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">How the record is built</h1>
          <p className="text-muted-foreground">
            Five satellites have watched Asia&apos;s fires since 2000, each with a different eye. Counting their
            detections naively creates jumps whenever a satellite starts or stops. This record converts every older
            satellite into what NOAA-20 VIIRS would have seen, step by step, and says how sure each number is.
          </p>
        </header>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold">The unit: fire days</h2>
          <p>
            A <b>fire day</b> is one ~1 km grid cell with at least one fire detection on one local solar day. Counting
            cells instead of raw detections stops one large fire from counting many times, and makes satellites with
            different pixel sizes easier to compare. Gas flares and other industrial heat sources are masked out.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold">The conversion chain</h2>
          <ol className="space-y-2">
            {STEPS.map(([title, text], i) => (
              <li key={title} className="flex gap-3 rounded-lg border p-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-orange-500 text-xs font-semibold text-white">
                  {i + 1}
                </span>
                <span>
                  <b>{title}</b>
                  <br />
                  <span className="text-muted-foreground">{text}</span>
                </span>
              </li>
            ))}
          </ol>
          <p>
            Each step picks the simplest conversion that is not clearly worse, by leave-one-year-out error, and reports
            its error and drift. Converted months carry a likely range from those errors; measured months have none.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold">Reading the map</h2>
          <p>
            The <b>playback</b> spreads each period&apos;s harmonized total over the cells where that period&apos;s
            satellite saw fire, so the cells add up to the area&apos;s total and colours are comparable across years.
            In MODIS years, small fires are placed less precisely (1 km pixels instead of 375 m).
          </p>
          <p>
            <b>This year vs typical</b> compares the months so far with the same months of other recent years,
            using NOAA-20 only, so no conversion is involved.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-xl font-semibold">Data</h2>
          <p>
            Fire detections: NASA FIRMS (MODIS C6.1, VIIRS 375 m). Borders: geoBoundaries. ENSO years: NOAA ONI.
            The full method, tests and every decision are in the project repository.
          </p>
        </section>
      </article>
    </main>
  );
}
