import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportView } from "@/features/report/components/report-view";

export const metadata: Metadata = { title: "Report" };

/** Printable report for one area: /report/?id=mys/sarawak (opened from the Data tab). */
export default function ReportPage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted-foreground">Loading…</p>}>
      <ReportView />
    </Suspense>
  );
}
