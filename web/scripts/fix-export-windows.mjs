// Workaround for a Next.js 16 static-export bug on Windows: segment prefetch files
// should be flat files named "__next.<segment>.<segment>.txt", but on Windows the
// exporter splits the name on "\" too late and writes nested folders instead
// ("__next.(group)/$oc$area/__PAGE__.txt"), so client navigation gets 404s.
// This flattens those folders. It does nothing on Linux/macOS builds (e.g. CI, Vercel).
import { readdirSync, renameSync, rmSync, statSync } from "node:fs";
import path from "node:path";

if (process.platform !== "win32") process.exit(0);

const root = path.join(process.cwd(), "out");
let moved = 0;

function filesUnder(dir, prefix = "") {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    const rel = prefix ? `${prefix}.${name}` : name;
    return statSync(full).isDirectory() ? filesUnder(full, rel) : [[full, rel]];
  });
}

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (!statSync(full).isDirectory()) continue;
    if (name.startsWith("__next.")) {
      for (const [src, rel] of filesUnder(full)) {
        renameSync(src, path.join(dir, `${name}.${rel}`));
        moved++;
      }
      rmSync(full, { recursive: true, force: true });
    } else {
      walk(full);
    }
  }
}

walk(root);
console.log(`flattened ${moved} segment files in out/`);
