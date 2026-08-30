import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
)

const nextConfig: NextConfig = {
  reactCompiler: true,

  // Ships a self-contained server in `.next/standalone` -- only the files the
  // application actually reaches, traced from the entrypoints, rather than the
  // whole hoisted `node_modules`. That is what makes the runtime image small
  // enough to be worth building, and `server.js` in it is what the Dockerfile
  // beside this file runs.
  output: 'standalone',

  // **The workspace root, not this directory, and the build is wrong without
  // it.** The two applications share a hoisted `node_modules` one level up, so
  // tracing from here would follow symlinks out of the traced tree and leave
  // the standalone output missing the dependencies it lists. Pinned rather than
  // inferred for the same reason `turbopack.root` is: a stray lockfile further
  // up the tree would otherwise make Next infer the home directory.
  //
  // The consequence to know when writing the Dockerfile: the output mirrors the
  // workspace, so the server lands at `.next/standalone/club/server.js`
  // and the shared `node_modules` at `.next/standalone/node_modules`.
  outputFileTracingRoot: workspaceRoot,
  turbopack: {
    // The **workspace** root, one level up, not this application's directory.
    // `frontend/` holds the lockfile and the hoisted `node_modules` that both
    // applications share, so pinning this directory instead leaves Turbopack
    // unable to resolve `next` itself.
    //
    // Pinned rather than inferred for the original reason: a stray lockfile
    // further up the tree would otherwise make Turbopack infer the home
    // directory as the project root.
    root: workspaceRoot,
  },
};

export default nextConfig;
