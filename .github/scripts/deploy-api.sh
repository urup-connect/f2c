#!/usr/bin/env bash
#
# Roll one API image out across the four container apps that run it.
#
# **The API is not one container app, and that is the thing this script exists
# to get right.** design/deploy.md 5.2 puts `api`, `worker`, `mail-worker` and
# `beat` all on the same image, chosen between by the first argument to
# `deploy/entrypoint.sh`. So "deploy the backend" is four `containerapp update`
# calls, not one, and a run that updates three of them has left a worker
# executing last week's code against this week's schema.
#
# **The order is a constraint, not a style.** Only the `api` container runs
# `migrate` -- the workers deliberately do not, because a second process racing
# the first through the same schema change on every deployment is worse than a
# slightly longer start-up. That makes the API the process that moves the
# schema, so it goes first and this script waits for its revision to provision
# before it touches a worker. A worker started against a schema that has not
# been applied yet is the overnight-wrong-writes failure 5.2 is written against.
#
# **It also means the migration is what can fail here.** Risk R-D3: Container
# Apps starts a new revision before retiring the old one, so a schema change has
# to be readable by the revision still serving traffic. When the wait below
# times out or the revision reports a failure, the migration is the first place
# to look, and the API's own log stream is where the entrypoint gate names which
# check it refused on.
#
# Shared with `promote.yml`, which runs it against UAT and production with the
# same digest that was proved in QA.
#
# Required in the environment:
#
#   IMAGE            a digest reference -- registry/f2c/api@sha256:...
#   RESOURCE_GROUP   the target environment's resource group
#   APP_API          container app names
#   APP_WORKER
#   APP_MAIL_WORKER
#   APP_BEAT
#
# Optional:
#
#   REVISION_TIMEOUT_SECONDS   how long to wait for the API revision (default 600)

set -euo pipefail

: "${IMAGE:?IMAGE is required -- a registry/repository@sha256:... reference}"
: "${RESOURCE_GROUP:?RESOURCE_GROUP is required}"
: "${APP_API:?APP_API is required}"
: "${APP_WORKER:?APP_WORKER is required}"
: "${APP_MAIL_WORKER:?APP_MAIL_WORKER is required}"
: "${APP_BEAT:?APP_BEAT is required}"

timeout_seconds="${REVISION_TIMEOUT_SECONDS:-600}"

# **A digest, and the script refuses anything else.** A tag is mutable on ACR
# Basic, so a revision pinned to `:qa` is a revision whose contents can change
# with no deployment and no record. Every promotion in this pipeline moves a
# digest; the environment tags are labels for humans.
case "$IMAGE" in
    *@sha256:*) ;;
    *)
        echo "IMAGE must be a digest reference, got: $IMAGE" >&2
        echo "A tag is mutable on Basic tier and cannot pin a revision." >&2
        exit 1
        ;;
esac

update() {
    local container_app="$1"
    echo "==> $container_app"
    az containerapp update \
        --name "$container_app" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$IMAGE" \
        --output none
}

# Wait for the container app's newest revision to finish provisioning.
#
# `az containerapp update` returns once the platform has accepted the revision,
# not once it is running, and the entrypoint gate on this image does real work
# before it serves anything: `check --deploy --fail-level WARNING`, then
# `migrate`. Returning before that has settled would report a green deployment
# for a revision that is about to fail its configuration check, and would then
# start the workers against an unmigrated schema.
wait_for_revision() {
    local container_app="$1"
    local deadline=$((SECONDS + timeout_seconds))
    local revision state health

    revision=$(az containerapp show \
        --name "$container_app" \
        --resource-group "$RESOURCE_GROUP" \
        --query 'properties.latestRevisionName' -o tsv)

    echo "    waiting on revision $revision"

    while [ "$SECONDS" -lt "$deadline" ]; do
        state=$(az containerapp revision show \
            --name "$container_app" \
            --resource-group "$RESOURCE_GROUP" \
            --revision "$revision" \
            --query 'properties.provisioningState' -o tsv)

        case "$state" in
            Provisioned)
                # Provisioned means the platform created it. Healthy means a
                # replica actually started, which is the part the entrypoint
                # gate decides. `healthState` is empty on a revision with no
                # ingress, so an empty value is not a failure.
                health=$(az containerapp revision show \
                    --name "$container_app" \
                    --resource-group "$RESOURCE_GROUP" \
                    --revision "$revision" \
                    --query 'properties.healthState' -o tsv)

                if [ "$health" = 'Unhealthy' ]; then
                    echo "    revision $revision is Unhealthy" >&2
                    echo "    the entrypoint gate names the failing check in the app's log stream:" >&2
                    echo "      az containerapp logs show -n $container_app -g $RESOURCE_GROUP --revision $revision" >&2
                    return 1
                fi

                echo "    $revision provisioned (health: ${health:-none})"
                return 0
                ;;
            Failed)
                echo "    revision $revision failed to provision" >&2
                echo "      az containerapp logs show -n $container_app -g $RESOURCE_GROUP --revision $revision" >&2
                return 1
                ;;
            *)
                echo "    $state"
                sleep 10
                ;;
        esac
    done

    echo "    revision $revision did not settle within ${timeout_seconds}s" >&2
    echo "    on this image that usually means the migration or the deployment check:" >&2
    echo "      az containerapp logs show -n $container_app -g $RESOURCE_GROUP --revision $revision" >&2
    return 1
}

echo "Rolling out $IMAGE"
echo "  resource group: $RESOURCE_GROUP"
echo

# The API first. It applies the migrations, and nothing else may start against a
# schema it has not moved yet.
update "$APP_API"
wait_for_revision "$APP_API"

# Then the three that serve no traffic. They run concurrently as far as the
# platform is concerned -- there is no ordering between them, only between them
# and the API above.
#
# `beat` is capped at one replica and this does not change that: an image update
# leaves the scale rules alone. The cap matters (two beats publish every job
# twice and the `ScheduledRun` history stops being readable) so it is worth
# knowing that nothing here touches it.
for container_app in "$APP_WORKER" "$APP_MAIL_WORKER" "$APP_BEAT"; do
    update "$container_app"
done

for container_app in "$APP_WORKER" "$APP_MAIL_WORKER" "$APP_BEAT"; do
    wait_for_revision "$container_app"
done

echo
echo "All four container apps are on $IMAGE"

# **`mail-worker` is on the authentication path and nothing else will say so
# when it is down.** The API answers normally, `/auth/otp/start` returns 200,
# and `EmailDispatch` rows pile up on `queued` while no member without a passkey
# can sign in -- 5.2. A rising `EmailDispatch.objects.pending()` count is the
# signal; watching `failed()` would show nothing at all.
echo
echo "Post-deploy check: EmailDispatch.objects.pending() should not be rising."
