// Copies browser runtime files that bundlers cannot emit into public/vendor/:
// DuckDB-wasm's WebAssembly engine and its web workers (queried for the hotspot CSV download).
import { copyFileSync, mkdirSync } from "node:fs";
import path from "node:path";

// the package does not export package.json, so locate it in node_modules directly
const dist = path.join(process.cwd(), "node_modules", "@duckdb", "duckdb-wasm", "dist");
const out = path.join(process.cwd(), "public", "vendor", "duckdb");
mkdirSync(out, { recursive: true });
for (const f of ["duckdb-mvp.wasm", "duckdb-eh.wasm", "duckdb-browser-mvp.worker.js", "duckdb-browser-eh.worker.js"]) {
  copyFileSync(path.join(dist, f), path.join(out, f));
}
console.log("copied DuckDB-wasm files to public/vendor/duckdb/");
