#!/usr/bin/env bash
#
# Print the manifest digest of one tag in the container registry.
#
#     acr-digest.sh <registry name> <repository:tag>
#
# Exits 1 with nothing on stdout when the tag does not exist, which is how
# `promote.yml` tells "this commit was never built" from "this commit failed to
# build".
#
# **Why every deployment goes through this rather than naming a tag.** The
# registry is Basic tier -- design/deploy.md section 2, because geo-replication
# is Premium and there is one region -- and tag immutability is a Premium
# feature. So a tag on this registry can be moved, and a container app revision
# pinned to `:qa` is a revision whose contents can change with no deployment and
# no record of one. The environment tags this pipeline writes are labels for
# whoever is reading the registry; the digest is what runs.
#
# Two commands, because the Azure CLI moved this one. `az acr manifest
# show-metadata` is the current spelling and `az acr repository show` is the
# older one that still answers on installed CLIs. Trying both means a runner
# image update cannot break a deployment, which is the kind of failure that
# arrives on a Friday.

set -euo pipefail

registry="${1:?usage: acr-digest.sh <registry name> <repository:tag>}"
image="${2:?usage: acr-digest.sh <registry name> <repository:tag>}"

digest=$(az acr manifest show-metadata \
    --registry "$registry" \
    --name "$image" \
    --query digest -o tsv 2>/dev/null) || digest=''

if [ -z "$digest" ]; then
    digest=$(az acr repository show \
        --name "$registry" \
        --image "$image" \
        --query digest -o tsv 2>/dev/null) || digest=''
fi

if [ -z "$digest" ]; then
    echo "No digest for ${image} in ${registry}." >&2
    exit 1
fi

echo "$digest"
