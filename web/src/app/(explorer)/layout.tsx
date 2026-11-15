import { ExplorerShell } from "@/features/explorer/components/explorer-shell";

/** The map lives in this layout so it stays mounted while the area (page) changes. */
export default function ExplorerLayout({ children }: { children: React.ReactNode }) {
  return <ExplorerShell>{children}</ExplorerShell>;
}
