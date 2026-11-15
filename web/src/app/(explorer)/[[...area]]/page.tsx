import type { Metadata } from "next";

import { AreaPanel } from "@/features/area-summary/components/area-panel";
import { areaIdFromSegments, segmentsFromAreaId } from "@/lib/area";
import { readAreaIndex } from "@/lib/data/server";

/** Only the exported areas exist (static export). */
export const dynamicParams = false;

export async function generateStaticParams() {
  const index = await readAreaIndex();
  return index.areas.map((a) => ({ area: segmentsFromAreaId(a.id) }));
}

export async function generateMetadata({ params }: PageProps<"/[[...area]]">): Promise<Metadata> {
  const { area } = await params;
  const id = areaIdFromSegments(area);
  if (!id) return {};
  const index = await readAreaIndex();
  const meta = index.areas.find((a) => a.id === id);
  return meta
    ? {
        title: `${meta.name} fire calendar`,
        description: `Harmonized monthly fire activity for ${meta.name} since 2000, in NOAA-20 VIIRS terms.`,
      }
    : {};
}

export default function AreaPage() {
  return <AreaPanel />;
}
