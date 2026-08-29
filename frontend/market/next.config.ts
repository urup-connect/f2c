import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    // The **workspace** root, one level up, not this application's directory.
    // `frontend/` holds the lockfile and the hoisted `node_modules` both
    // applications share, so pinning this directory instead leaves Turbopack
    // unable to resolve `next` itself. The club's config says the same thing
    // for the same reason — the value is per-application and the reasoning is
    // not, which is one of the seams `packages/` will eventually cover.
    root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
  },
};

export default nextConfig;
