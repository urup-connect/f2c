# The club container: Next.js standalone on Node, for Azure Container Apps.
#
# **Build this from `frontend/`, not from this directory:**
#
#     docker build -f club/Dockerfile -t f2c-club .
#
# The context is the workspace because that is where the lockfile and the
# hoisted `node_modules` live. `next.config.ts` pins `outputFileTracingRoot` to
# the same place, and the two have to agree or the traced output describes a
# tree the build cannot see.
#
# **There are no build arguments, and that is the point of this image.** Nothing
# about a deployment is baked in, so one image serves QA, UAT and Production and
# a promotion is a retag rather than a rebuild. That is design/deploy.md R-D4,
# closed.
#
# It closed in two steps, and the second one is why this file has shrunk.
# `NEXT_PUBLIC_DJANGO_API_URL` went first: `next build` inlined it into the
# browser bundle, which tied every image to one environment. It is now
# `DJANGO_API_PUBLIC_URL`, read at request time and written into the document by
# the root layout -- `lib/api-address.ts`, Block 0 P6 in design/todo.md. Then
# `SITE_URL`, `APP_ENV`, `CDN_BASE_URL` and `SUPPORT_EMAIL` followed the same
# route: `lib/site.ts` used to read them when the module was first loaded, which
# happens during `next build` because the build imports every module to analyse
# the route tree. It reads them during render now.
#
# **What the build no longer catches, the entrypoint does.** A missing build
# argument failed the build, named itself, and never reached a registry. A
# missing container setting would otherwise surface as a 500 on whichever page
# first needed the value -- for `SUPPORT_EMAIL` that is the blocked-membership
# screen, which only a member the club has already shut out ever reaches, so the
# container could look healthy for weeks. `deploy/entrypoint.sh` checks all four
# before starting the server instead, and the revision fails to come up. See
# `REQUIRED_ENV` in the runtime stage below.

# **The base image is pinned by digest, and the tag beside it is there to be
# read rather than resolved.** design/deploy.md R-D7.
#
# **The reason is weaker than it was, and worth restating rather than leaving to
# be misread.** This pin used to carry a promotion: under R-D4 a move to UAT or
# Production *rebuilt* the image, so the digest was what closed the gap between
# "the same commit" and "the same image" across three environments. With R-D4
# closed a promotion moves this exact image and rebuilds nothing, and that
# argument is gone with it. What remains is narrower and still real: `npm ci`
# makes the dependency tree reproducible from the committed lockfile, but
# `node:24-slim` is a floating tag, so an image rebuilt from an older commit
# would otherwise land on whatever operating system packages that tag points at
# on the day. The pin makes a rebuild reproducible over time rather than across
# environments.
#
# **One ARG rather than a digest on each of the three FROM lines below.** A
# digest copied three times is a digest that can be bumped twice, and a build
# stage on one Node with a runtime stage on another is the kind of difference
# that surfaces as something else entirely.
#
# node:24-slim as at 2 September 2026, which is Node 24.20.0. To bump it, take the
# *top-level* digest -- the multi-platform index, not one platform's manifest:
#
#     docker buildx imagetools inspect node:24-slim
#
# Keep it in step with `market/Dockerfile` and `../Dockerfile.dev`, which pin the same
# image and have nothing to tell them apart.
ARG NODE_IMAGE=node:24-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e

# ---------------------------------------------------------------- dependencies
FROM ${NODE_IMAGE} AS deps

WORKDIR /workspace

# Both workspace manifests, because `npm ci` resolves the whole workspace from
# one lockfile and fails on a member it cannot find. Copying only this
# application's manifest would work until the next time the lockfile changed.
COPY package.json package-lock.json ./
COPY club/package.json ./club/
COPY market/package.json ./market/

RUN npm ci


# ---------------------------------------------------------------------- build
FROM ${NODE_IMAGE} AS build

WORKDIR /workspace
COPY --from=deps /workspace/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY club/package.json ./club/
COPY market/package.json ./market/
COPY club ./club

# **Nothing environment-specific reaches this stage, and that is the property
# the whole change is for.** It is checkable rather than asserted: `next build`
# completes with `SITE_URL`, `APP_ENV`, `CDN_BASE_URL`, `SUPPORT_EMAIL` and both
# API addresses unset.
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build --workspace @f2c/club-web


# -------------------------------------------------------------------- runtime
FROM ${NODE_IMAGE} AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN useradd --create-home --uid 10001 next
WORKDIR /app

# The startup gate, copied above the build output so that a change to the
# application does not invalidate this layer. Shared with the other frontend
# image, which is why the variable names are in `REQUIRED_ENV` below rather
# than in the script.
COPY --chmod=0755 deploy/entrypoint.sh /usr/local/bin/entrypoint.sh

# **Three copies, and standalone needs all three.** The traced output carries
# the server and its dependencies but neither the static assets nor `public/`,
# so an image built from `standalone` alone starts, serves HTML, and renders
# every page with no styles and no scripts. The output mirrors the workspace,
# which is why the server sits under `club/` and `node_modules` does not.
COPY --from=build --chown=next:next /workspace/club/.next/standalone ./
COPY --from=build --chown=next:next /workspace/club/.next/static ./club/.next/static
COPY --from=build --chown=next:next /workspace/club/public ./club/public

USER next
EXPOSE 3000

# **Every setting this image reads, and all of them at runtime.** Nothing below
# is baked in; the container app supplies the lot.
#   SITE_URL, APP_ENV, CDN_BASE_URL, SUPPORT_EMAIL -- read by `lib/site.ts`
#   DJANGO_API_URL         -- how the Next.js server reaches Django (container network)
#   DJANGO_API_PUBLIC_URL  -- how the browser reaches Django (publicly resolvable)
# The last is rendered into the document by the root layout. It must sit inside
# the same registrable domain the browser uses for this app, or the request is
# cross-site and the SameSite=Lax session cookie is not sent -- conflict.md C30.

# What the entrypoint refuses to start without. **The two API addresses are
# deliberately absent from this list**, and the difference is how loudly each
# one fails. The root layout reads `DJANGO_API_PUBLIC_URL` on every page, so an
# unset one is a 500 on the first request anybody makes and a gate would tell
# nobody anything they were not about to learn. The names below are read by
# pages a deployment can serve for a long time without reaching.
ENV REQUIRED_ENV="SITE_URL APP_ENV CDN_BASE_URL SUPPORT_EMAIL"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["node", "club/server.js"]
