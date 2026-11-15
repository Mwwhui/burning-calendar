"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * The panel's row of view tabs. When it is wider than the panel it scrolls sideways: arrow buttons and a
 * fade show there is more, the mouse wheel scrolls it, and the selected tab is kept in view.
 */
export function TabBar<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ left: false, right: false });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () =>
      setEdge({ left: el.scrollLeft > 2, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 });
    // vertical wheel -> sideways scroll (a mouse has no horizontal wheel)
    const wheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX) || el.scrollWidth <= el.clientWidth) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    const ro = new ResizeObserver(update);
    ro.observe(el);
    el.addEventListener("scroll", update, { passive: true });
    el.addEventListener("wheel", wheel, { passive: false });
    return () => {
      ro.disconnect();
      el.removeEventListener("scroll", update);
      el.removeEventListener("wheel", wheel);
    };
  }, []);

  // keep the selected tab visible (e.g. after "How it was converted and tested" opens Method)
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [value]);

  const page = (dir: 1 | -1) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.7, behavior: "smooth" });

  return (
    <div className="relative">
      <div ref={ref} role="tablist" aria-label="Views" className="no-scrollbar flex gap-0.5 overflow-x-auto scroll-smooth px-3 py-1.5">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={value === t.id}
            onClick={() => onChange(t.id)}
            className={cn(
              "shrink-0 rounded-md px-2.5 py-1 text-[13px] whitespace-nowrap transition-colors",
              value === t.id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <Arrow side="left" show={edge.left} onClick={() => page(-1)} />
      <Arrow side="right" show={edge.right} onClick={() => page(1)} />
    </div>
  );
}

function Arrow({ side, show, onClick }: { side: "left" | "right"; show: boolean; onClick: () => void }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <div
      aria-hidden={!show}
      className={cn(
        "pointer-events-none absolute inset-y-0 flex w-12 items-center transition-opacity",
        side === "left" ? "left-0 justify-start bg-gradient-to-r pl-1" : "right-0 justify-end bg-gradient-to-l pr-1",
        "from-background via-background/90 to-transparent",
        show ? "opacity-100" : "opacity-0",
      )}
    >
      <button
        type="button"
        tabIndex={-1}
        aria-label={side === "left" ? "Show earlier tabs" : "Show more tabs"}
        onClick={onClick}
        className={cn("grid size-6 place-items-center rounded-full border bg-background shadow-sm hover:bg-muted", show && "pointer-events-auto")}
      >
        <Icon className="size-3.5" />
      </button>
    </div>
  );
}
