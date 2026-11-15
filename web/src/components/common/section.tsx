import { Info, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";

/** A titled block inside the side panel. */
export function Section({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-2.5", className)}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            {title && <h3 className="text-sm font-semibold tracking-tight">{title}</h3>}
            {description && <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Callout({
  tone = "info",
  children,
}: {
  tone?: "info" | "warn";
  children: React.ReactNode;
}) {
  const Icon = tone === "warn" ? TriangleAlert : Info;
  return (
    <div
      className={cn(
        "flex gap-2 rounded-lg border p-2.5 text-xs leading-relaxed",
        tone === "warn" ? "border-amber-500/30 bg-amber-500/10" : "border-sky-500/25 bg-sky-500/8",
      )}
    >
      <Icon className={cn("mt-0.5 size-3.5 shrink-0", tone === "warn" ? "text-amber-500" : "text-sky-500")} />
      <div>{children}</div>
    </div>
  );
}

/** Small caption under a chart. */
export function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] leading-relaxed text-muted-foreground">{children}</p>;
}

/** Large number with a label, for key figures. */
export function Stat({ label, value, sub, className }: { label: string; value: React.ReactNode; sub?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card/60 p-3", className)}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tracking-tight tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** Placeholder when a view has nothing for this area. */
export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">{children}</div>
  );
}
