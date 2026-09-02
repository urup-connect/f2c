# The produce market container: Next.js standalone on Node, for Azure Container Apps.
#
# **Build this from `frontend/`, not from this directory:**
#
#     docker build -f market/Dockerfile -t f2c-market \
#       --build-arg SITE_URL=https://f2c.co.za \
#       --build-arg APP_ENV=production \
#       .
#
# The context is the workspace because that is where the lockfile and the
# hoisted `node_modules` live. `next.config.ts` pins `outputFileTracingRoot` to
# the same place, and the two have to agree or the traced output describes a
# tree the build cannot see.
#
# **The API address is no longer among these, and that was the point.** It used
# to be a `NEXT_PUBLIC_` build argument, inlined into the browser bundle, which
# tied every image to one environment: a build could not be promoted from QA to
# Production, it had to be rebuilt. It is now `DJANGO_API_PUBLIC_URL`, read at
# request time and written into the document by the root layout -- see
# `lib/api-address.ts`. That is Block 0 P6 in design/todo.md, and it is closed.
#
# What remains build-time is `SITE_URL` and `APP_ENV`, which `lib/site.ts`
# evaluates when the module is first loaded. Those are still baked, so the image
# is still environment-specific until they move too -- but the address a member
# browser talks to is no longer one of them, and it was the one that mattered:
# SITE_URL is wrong in a way that shows up in a canonical tag, and the API
# address was wrong in a way that broke every request after sign-in.
#
# No `CDN_BASE_URL` here. The club reads it for the landing page's brand film;
# the market has no equivalent -- see `frontend/market/lib/site.ts`.

# **The base image is pinned by digest, and the tag beside it is there to be
# read rather than resolved.** design/deploy.md R-D7.
#
# A promotion to UAT or production does not move this image, it **rebuilds**
# it -- the build arguments below are baked in, so there is no other choice
# (R-D4). `npm ci` makes the dependency tree reproducible from the committed
# lockfile, but `node:24-slim` is a floating tag: republished between the QA
# build and the production build, it changes the operating system packages
# underneath an application whose own code and dependencies are identical.
# The digest is what closes the gap between "the same commit" and "the same
# image".
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
# Keep it in step with `club/Dockerfile` and `../Dockerfile.dev`, which pin the same
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
COPY market ./market

# Inlined into the bundle, or read during prerendering. See the note above.
ARG SITE_URL
ARG APP_ENV=production
ENV SITE_URL=$SITE_URL \
    APP_ENV=$APP_ENV \
    NEXT_TELEMETRY_DISABLED=1

# `lib/site.ts` throws on a missing SITE_URL during prerendering anyway; checking
# it here names the build argument rather than the variable, which is what the
# person running the build actually set.
RUN test -n "$SITE_URL" || { echo "SITE_URL build-arg is required" >&2; exit 1; }

RUN npm run build --workspace @f2c/market-web


# -------------------------------------------------------------------- runtime
FROM ${NODE_IMAGE} AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN useradd --create-home --uid 10001 next
WORKDIR /app

# **Three copies, and standalone needs all three.** The traced output carries
# the server and its dependencies but neither the static assets nor `public/`,
# so an image built from `standalone` alone starts, serves HTML, and renders
# every page with no styles and no scripts. The output mirrors the workspace,
# which is why the server sits under `market/` and `node_modules` does not.
COPY --from=build --chown=next:next /workspace/market/.next/standalone ./
COPY --from=build --chown=next:next /workspace/market/.next/static ./market/.next/static
COPY --from=build --chown=next:next /workspace/market/public ./market/public

USER next
EXPOSE 3000

# Two addresses, both read here at runtime and neither baked into the image:
#   DJANGO_API_URL         -- how the Next.js server reaches Django (container network)
#   DJANGO_API_PUBLIC_URL  -- how the browser reaches Django (publicly resolvable)
# The second is rendered into the document by the root layout. It must sit inside
# the same registrable domain the browser uses for this app, or the request is
# cross-site and the SameSite=Lax session cookie is not sent -- conflict.md C30.
CMD ["node", "market/server.js"]
