"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";
import { HazeBar } from "@/features/map/components/haze-bar";
import { PhotoBar } from "@/features/map/components/photo-bar";
import { RecentBar } from "@/features/playback/components/recent-bar";
import { TimelineBar } from "@/features/playback/components/timeline-bar";

import { useExplorer } from "../store";
import { usePanelWidth } from "../hooks/use-panel-width";
import { MapToolbar } from "./map-toolbar";
import { PanelResizer } from "./panel-resizer";

// MapLibre / deck.gl need the browser (WebGL), so the map is never rendered on the server.
const FireMap = dynamic(() => import("@/features/map/components/fire-map"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

/**
 * Map-first layout: the map fills the screen and stays mounted while the
 * user moves between areas; the page (area panel) is rendered on the right.
 */
export function ExplorerShell({ children }: { children: React.ReactNode }) {
  const layer = useExplorer((s) => s.layer);
  // side panel width (desktop): null = the default responsive width; remembered in this browser only
  const [width, resize] = usePanelWidth();
  return (
    <div className="flex min-h-0 flex-1 flex-col md:flex-row">
      <section aria-label="Map" className="relative h-[58dvh] shrink-0 md:h-auto md:flex-1">
        <FireMap />
        <MapToolbar />
        <PhotoBar />
        <HazeBar />
        {layer === "playback" && <TimelineBar />}
        {layer === "recent" && <RecentBar />}
      </section>
      <aside
        aria-label="Area details"
        style={width ? ({ "--panel-w": `${width}px` } as React.CSSProperties) : undefined}
        className={
          "relative min-h-0 border-t bg-background md:shrink-0 md:border-t-0 md:border-l " +
          (width ? "md:w-[var(--panel-w)]" : "md:w-[440px] lg:w-[480px]")
        }
      >
        <PanelResizer width={width ?? 480} onChange={resize} />
        <div className="h-full md:overflow-y-auto">{children}</div>
      </aside>
    </div>
  );
}
