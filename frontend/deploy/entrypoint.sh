#!/bin/sh
#
# The frontend containers' startup gate. Refuse, then serve.
#
# **This script exists because the four site variables stopped being build
# arguments.** `SITE_URL`, `APP_ENV`, `CDN_BASE_URL` and `SUPPORT_EMAIL` used to
# be baked in by `next build`, which meant a missing one failed the build,
# named the build argument, and never reached a registry. That is what made the
# image environment-specific and it is what design/deploy.md R-D4 removed:
# `lib/site.ts` now reads them during render, from the container's own
# environment.
#
# What that costs is the moment of failure. A module-load read died on the way
# up; a render-time read dies on the first request that needs the value -- and
# for `SUPPORT_EMAIL` that request is the blocked-membership screen, reached by
# somebody the club has already shut out and by nobody else. A container can
# therefore look healthy for weeks and be broken for the one person who needed
# it. `CDN_BASE_URL` has the same shape, one landing-page film later.
#
# So the gate moves here, in front of the server, which is where
# `deploy/entrypoint.sh` already puts the same property for Django: a
# misconfigured revision never becomes a running one, and Container Apps holds
# the previous revision serving traffic while the new one fails to start.
#
# **Presence only, deliberately.** `lib/site.ts` is where a value's *shape* is
# judged -- that SITE_URL is an origin and not a path, that CDN_BASE_URL is
# https outside local development, that SUPPORT_EMAIL could be an address -- and
# re-stating any of that in shell would be a second copy to keep in step, wrong
# in a different way the first time somebody changed one. Unset is the failure
# that actually happens, and it is the one a running application reports worst.
#
# `set -e` is what makes this a gate rather than a warning: without it the
# script would run on to the server it just refused.
set -eu

# The variables this image cannot serve without, set by the Dockerfile. Named
# there rather than here because the club reads four and the store reads two,
# and this script is shared.
for name in ${REQUIRED_ENV:-}; do
    # `printenv` rather than an `eval` on a name from the environment. It exits
    # non-zero when the variable is unset, which `set -e` would otherwise treat
    # as the script's own failure -- hence the fallback.
    value="$(printenv "$name" || true)"

    if [ -z "$value" ]; then
        missing="${missing:-} $name"
    fi
done

if [ -n "${missing:-}" ]; then
    echo "entrypoint: refusing to start." >&2
    for name in $missing; do
        echo "entrypoint: $name is not set, and this image is served from the" >&2
        echo "entrypoint:   container's environment rather than from its build." >&2
    done
    echo "entrypoint: set them on the container app -- see design/deploy-quickstart.md" >&2
    echo "entrypoint: tables D and E -- and deploy a new revision." >&2
    exit 1
fi

echo "entrypoint: configuration present, starting the Next.js server"
exec "$@"
