import type { NextConfig } from "next";

/**
 * Static export: the app is plain HTML/JS plus the JSON files that
 * `python scripts/export_web.py` writes to public/data/. No server is needed,
 * so it can be hosted on GitHub Pages, Vercel or any static file host.
 */
const nextConfig: NextConfig = {
  output: "export",
  // React's dev-only Strict Mode mounts every component twice. The deck.gl overlay shares
  // MapLibre's WebGL context (interleaved mode) and luma.gl refuses to attach a second
  // device to it ("WebGL context already attached"), so the fire layers vanished in
  // `npm run dev`. Production builds never double-mount, so this only affects development.
  reactStrictMode: false,
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
