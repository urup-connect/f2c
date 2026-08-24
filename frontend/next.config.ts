import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    // Pin the root: a stray lockfile further up the tree otherwise makes
    // Turbopack infer the home directory as the project root.
    root: path.dirname(fileURLToPath(import.meta.url)),
  },
};

export default nextConfig;
