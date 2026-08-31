import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
)

const nextConfig: NextConfig = {

  // **File watching inside a container, and it is only half a fix.** A bind
  // mount from a Windows or macOS host delivers no inotify events, so the dev
  // server starts, serves, and then never notices a saved file. Turbopack has
  // its own watcher and ignores `WATCHPACK_POLLING`, webpack's escape hatch;
  // `watchOptions.pollIntervalMs` is the one it reads -- see
  // `next/dist/server/dev/hot-reloader-turbopack.js`, which passes it straight
  // to the native watcher.
  //
  // **Measured on Docker Desktop for Windows, it did not help.** The container
  // sees the edited file and its new mtime, and Turbopack still does not
  // recompile; the log fills with `watch error ... NotFound` instead. So a
  // frontend edit under compose needs `docker compose restart club`, which
  // takes about a second. This is kept because it is the correct mechanism and
  // does work where the watcher does -- a Linux host, or WSL2-native files --
  // and because the next person to look at this should not have to rediscover
  // that `WATCHPACK_POLLING` is the wrong knob.
  //
  // Off unless asked for: polling costs CPU proportional to the tree, and
  // `npm run dev` on the host has working native events. `compose.yaml` sets
  // NEXT_WATCH_POLL_MS.
  ...(process.env.NEXT_WATCH_POLL_MS
    ? { watchOptions: { pollIntervalMs: Number(process.env.NEXT_WATCH_POLL_MS) } }
    : {}),
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
  // workspace, so the server lands at `.next/standalone/market/server.js`
  // and the shared `node_modules` at `.next/standalone/node_modules`.
  outputFileTracingRoot: workspaceRoot,
  turbopack: {
    // The **workspace** root, one level up, not this application's directory.
    // `frontend/` holds the lockfile and the hoisted `node_modules` both
    // applications share, so pinning this directory instead leaves Turbopack
    // unable to resolve `next` itself. The club's config says the same thing
    // for the same reason — the value is per-application and the reasoning is
    // not, which is one of the seams `packages/` will eventually cover.
    root: workspaceRoot,
  },
};

export default nextConfig;
