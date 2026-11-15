import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import type { AreaIndex } from "./types";

/** Read the area index at build time (for generateStaticParams and page metadata). */
export async function readAreaIndex(): Promise<AreaIndex> {
  const file = path.join(process.cwd(), "public", "data", "index.json");
  return JSON.parse(await readFile(file, "utf-8")) as AreaIndex;
}
