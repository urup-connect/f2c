import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    // The **workspace** root, one level up, not this application's directory.
    // `frontend/` holds the lockfile and the hoisted `node_modules` that both
    // applications share, so pinning this directory instead leaves Turbopack
    // unable to resolve `next` itself.
    //
    // Pinned rather than inferred for the original reason: a stray lockfile
    // further up the tree would otherwise make Turbopack infer the home
    // directory as the project root.
    root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
  },
};

export default nextConfig;
