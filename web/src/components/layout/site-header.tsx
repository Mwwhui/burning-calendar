import { Flame } from "lucide-react";
import Link from "next/link";

import { AlertsBell } from "@/features/alerts/components/alerts-bell";
import { AreaSearch } from "@/features/area-search/components/area-search";
import { StudySwitch } from "@/features/area-search/components/study-switch";

import { ThemeToggle } from "./theme-toggle";

export function SiteHeader() {
  return (
    <header data-print-hide className="z-20 flex h-14 shrink-0 items-center gap-3 border-b bg-background/95 px-3 backdrop-blur sm:px-4">
      <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <span className="grid size-7 place-items-center rounded-md bg-gradient-to-br from-amber-400 to-red-600 text-white">
          <Flame className="size-4" />
        </span>
        <span className="hidden sm:inline">Burning Calendar</span>
        <span className="hidden text-xs font-normal text-muted-foreground lg:inline">
          · 26 years of fire, one consistent record
        </span>
      </Link>
      <StudySwitch />
      <div className="ml-auto flex min-w-0 flex-1 items-center justify-end gap-2">
        <AreaSearch />
        <Link
          href="/method/"
          className="hidden h-9 items-center rounded-md px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground sm:inline-flex"
        >
          Method
        </Link>
        <AlertsBell />
        <ThemeToggle />
      </div>
    </header>
  );
}
