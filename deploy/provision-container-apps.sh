#!/usr/bin/env bash
#
# Create the six container apps an environment runs, once, from nothing.
#
# **This script provisions; it does not deploy.** `release.yml` and `promote.yml`
# move images onto apps that already exist -- `az containerapp update` fails on
# an app that does not -- and that is the failure this script exists to stop
# happening. Run it once per environment, before the first release reaches it.
# It is idempotent: an app that already exists is reported and left alone, so a
# re-run after adding one app is safe.
#
# **The seven apps.** design/deploy.md 5.2 describes six; the seventh is Redis,
# and the reason it is here rather than in Azure is below. Four of them run the
# same API image and choose between behaviours with the first argument to
# `deploy/entrypoint.sh`; two are the storefronts.
#
#   f2c-redis               redis:7-alpine           internal TCP, port 6379, EXACTLY ONE REPLICA
#   f2c-api                 entrypoint serve         external ingress, port 8000
#   f2c-celery-worker       entrypoint worker        no ingress
#   f2c-celery-mail-worker  entrypoint mail-worker   no ingress
#   f2c-celery-beat         entrypoint beat          no ingress, EXACTLY ONE REPLICA
#   f2c-club                image default            external ingress, port 3000
#   f2c-market              image default            external ingress, port 3000
#
# **Why Redis is a container here and not Azure Managed Redis.** Two properties
# of Managed Redis that this application needs and cannot get:
#
#   * **A second logical database.** `f2c/queue.py` sets `BROKER_DB = 1` and
#     derives the broker from `DJANGO_REDIS_URL` with the path rewritten, so one
#     Redis serves the throttle counters on db 0 and the queue on db 1. Managed
#     Redis exposes one database per cluster. A plain Redis has sixteen.
#   * **A non-clustered endpoint.** The instance available here is
#     `OSSCluster`, and kombu's transport list is `redis`, `rediss` and
#     `sentinel` -- there is no Redis Cluster transport, so Celery cannot use a
#     clustered Redis as a broker at all.
#
# It also removes a third problem rather than solving it: Managed Redis here has
# `accessKeysAuthentication` disabled, and neither `f2c/cache.py` nor
# `f2c/queue.py` can present a Microsoft Entra token today.
#
# **No persistence, and that is a decision rather than an omission.**
# `--save "" --appendonly no`, matching `compose.yaml`. Container Apps offers
# ephemeral storage or Azure Files, and Azure Files is SMB: Redis AOF
# correctness depends on `fsync` semantics a network filesystem does not
# reliably provide, while ephemeral storage does not survive the replica
# replacement that platform maintenance performs. So a volume here buys
# fragility rather than durability.
#
# What is actually lost on a restart is bounded and already visible. The
# throttle counters are disposable -- losing them resets a rate limit window.
# The queue holds in-flight `deliver_email` messages, and that loss is a failure
# the application already accepts on purpose: `storefronts/tasks.py` sets
# `acks_late=False` so a worker killed mid-hand-over loses the send rather than
# delivering a second sign-in code, and `EmailDispatch.objects.pending()` is the
# query that surfaces it. The durable record is in MySQL.
#
# **`maxmemory-policy noeviction`, because one instance serves both.** A cache
# would want `allkeys-lru`; a broker must never evict, or queued tasks disappear
# under memory pressure with nothing to say so. One instance forces one policy
# and the broker's requirement is the one that cannot be relaxed -- so the
# throttle counters compete for the same memory, and `maxmemory` is a thing to
# watch rather than a thing to set and forget.
#
# The names are unprefixed. The resource group already carries the environment
# -- `rg-f2c-qa-weu` -- so `qa-f2c-api` in `rg-f2c-qa-weu` says it twice, and
# design/deploy-quickstart.md's `DJANGO_API_URL` assumes the unprefixed form.
# Whatever is chosen has to match the `CONTAINERAPP_*` GitHub variables for the
# same environment, because those are what the deployments read.
#
# **`beat` is capped at one replica and that is a correctness constraint.** Beat
# publishes on a timer with no coordination between instances, so two of it
# publishes every scheduled job twice and the `ScheduledRun` history stops being
# readable. `--min-replicas 1 --max-replicas 1`, and nothing in an image update
# changes it.
#
# **`api` is pinned to `--min-replicas 1`, and that is not a performance
# setting.** Scale-to-zero plus the four DNS lookups in `payfast_addresses`
# risks timing out an inbound Payfast notification, and a dropped notification
# is a member who paid and was not switched on -- C31.
#
# **Each app pulls with its own system-assigned identity**, granted `AcrPull` on
# the shared registry, so the registry's admin user can stay off. An admin user
# left enabled is a username and password that works from anywhere, for every
# repository in the registry, and outlives whoever last used it.
#
# Usage:
#
#     ENVIRONMENT=qa \
#     RESOURCE_GROUP=rg-f2c-qa-weu \
#     CONTAINERAPP_ENV=managedEnvironment-rgf2cqaweu-ad52 \
#     ACR_NAME=crf2cweu \
#     IMAGE_TAG=<the commit SHA release.yml pushed> \
#     VALUES_FILE=deploy/qa.values.env \
#         ./deploy/provision-container-apps.sh
#
#   DRY_RUN=1      print every mutating command instead of running it
#   FORCE=1        provision even though the data tier is incomplete. The API
#                  family will crashloop until MySQL, Redis and storage exist --
#                  the entrypoint gate refuses before it serves anything
#   SKIP_MARKET=1  five apps instead of six, for an environment where
#                  DEPLOY_MARKET is not 'true'
#
#   MYSQL_RESOURCE_GROUP    where the data tier actually lives, when it is not
#   STORAGE_RESOURCE_GROUP  this environment's own resource group. Each defaults
#                           to RESOURCE_GROUP; `-` skips that one check. These
#                           affect the preflight only -- the running application
#                           reaches MySQL by hostname and blob storage by
#                           account name, never by resource group. There is no
#                           REDIS_RESOURCE_GROUP: Redis is one of the apps this
#                           script creates.
#
# **The managed environment and its Log Analytics workspace are created if they
# are absent**, so a whole environment comes up from one command and UAT and
# production are the same command with different values. An environment that
# already exists is used as it stands.
#
# The values file holds Tables B, C, D and E from design/deploy-quickstart.md.
# It carries passwords and keys, so it is never committed --
# `deploy/values.env.template` is the copy to fill in.

set -euo pipefail

# ------------------------------------------------------------------- the inputs

: "${ENVIRONMENT:?ENVIRONMENT is required -- qa, uat or prod}"
: "${RESOURCE_GROUP:?RESOURCE_GROUP is required -- e.g. rg-f2c-qa-weu}"
: "${CONTAINERAPP_ENV:?CONTAINERAPP_ENV is required -- the managed environment name}"
: "${ACR_NAME:?ACR_NAME is required -- e.g. crf2cweu}"
: "${IMAGE_TAG:?IMAGE_TAG is required -- the commit SHA release.yml pushed}"
: "${VALUES_FILE:?VALUES_FILE is required -- see deploy/values.env.template}"

case "$ENVIRONMENT" in
    qa|uat|prod) ;;
    *)
        echo "ENVIRONMENT must be qa, uat or prod, got: $ENVIRONMENT" >&2
        echo "Note 'prod' and not 'production' -- DJANGO_ENV takes prod." >&2
        exit 1
        ;;
esac

if [ ! -r "$VALUES_FILE" ]; then
    echo "Cannot read VALUES_FILE: $VALUES_FILE" >&2
    echo "Copy deploy/values.env.template and fill it in." >&2
    exit 1
fi

# App names, overridable so an environment that already carries different ones
# does not have to be renamed to use this script.
APP_API="${APP_API:-f2c-api}"
APP_WORKER="${APP_WORKER:-f2c-celery-worker}"
APP_MAIL_WORKER="${APP_MAIL_WORKER:-f2c-celery-mail-worker}"
APP_BEAT="${APP_BEAT:-f2c-celery-beat}"
APP_CLUB="${APP_CLUB:-f2c-club}"
APP_MARKET="${APP_MARKET:-f2c-market}"
APP_REDIS="${APP_REDIS:-f2c-redis}"

REGISTRY="${ACR_NAME}.azurecr.io"

# Pinned to the minor version, not `7` or `latest`. This process holds the queue
# every email passes through; the version it runs is not a thing to let a tag
# move underneath a restart. Same image `compose.yaml` uses, so local and
# deployed behaviour match. Pulled from Docker Hub -- it is the one app here that
# is not this project's own image, so it needs no registry identity.
REDIS_IMAGE="${REDIS_IMAGE:-redis:7.4-alpine}"
REDIS_PORT=6379

# The Log Analytics workspace the managed environment logs to, created with it.
LOG_WORKSPACE="${LOG_WORKSPACE:-log-${RESOURCE_GROUP}}"
LOCATION="${LOCATION:-westeurope}"

# Sizing. **Not specified in design/deploy.md**, so these are this script's
# defaults rather than a decision the documents made: the API carries uvicorn
# plus the migration pass, the rest are lighter. Container Apps accepts only
# certain CPU/memory pairs -- 0.5/1.0Gi, 1.0/2.0Gi, 2.0/4.0Gi.
API_CPU="${API_CPU:-1.0}"
API_MEMORY="${API_MEMORY:-2.0Gi}"
WORKER_CPU="${WORKER_CPU:-0.5}"
WORKER_MEMORY="${WORKER_MEMORY:-1.0Gi}"
FRONTEND_CPU="${FRONTEND_CPU:-0.5}"
FRONTEND_MEMORY="${FRONTEND_MEMORY:-1.0Gi}"

# Redis, and `maxmemory` is the setting to think about rather than the container
# size. It is set below the container's memory so that Redis refuses a write
# before the platform kills the process: with `noeviction`, hitting `maxmemory`
# returns an error to the writer, which surfaces as a failed enqueue somebody
# can see, where an OOM kill loses the whole queue silently.
REDIS_CPU="${REDIS_CPU:-0.5}"
REDIS_MEMORY="${REDIS_MEMORY:-1.0Gi}"
REDIS_MAXMEMORY="${REDIS_MAXMEMORY:-700mb}"

run() {
    if [ -n "${DRY_RUN:-}" ]; then
        printf '  [dry-run]'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

# ------------------------------------------------------------------- the values

# shellcheck disable=SC1090
set -a
. "$VALUES_FILE"
set +a

# Everything Table C says all four API apps take identically. A trimmed
# environment fails `check --deploy` at start-up rather than running degraded,
# which is why the list is long and why none of it is optional.
API_PLAIN_VARS=(
    DJANGO_ENV DJANGO_DEBUG DJANGO_ALLOWED_HOSTS DJANGO_BEHIND_PROXY
    DJANGO_CSRF_TRUSTED_ORIGINS DJANGO_CORS_ALLOWED_ORIGINS
    DJANGO_DB_HOST DJANGO_DB_PORT DJANGO_DB_NAME DJANGO_DB_USER DJANGO_DB_SSL_CA
    DJANGO_STOREFRONT_HOSTS DJANGO_DEFAULT_STOREFRONT
    DJANGO_WEBAUTHN_RP_ID DJANGO_WEBAUTHN_RP_IDS DJANGO_WEBAUTHN_RP_NAME
    DJANGO_WEBAUTHN_ORIGINS
    DJANGO_DEFAULT_FROM_EMAIL
    DJANGO_DOCUMENT_STORAGE_CONTAINER DJANGO_DOCUMENT_STORAGE_ACCOUNT
    DJANGO_AVATAR_STORAGE_CONTAINER DJANGO_AVATAR_STORAGE_ACCOUNT
    EMAIL_CC_HOST EMAIL_CC_PORT EMAIL_CC_USER EMAIL_CC_USE_TLS EMAIL_CC_FROM
    EMAIL_F2C_HOST EMAIL_F2C_PORT EMAIL_F2C_USER EMAIL_F2C_USE_TLS EMAIL_F2C_FROM
    EMAIL_DISPATCH_RETENTION_DAYS CAMPAIGN_TOUCH_RETENTION_DAYS
    DJANGO_PAYFAST_SANDBOX DJANGO_PAYFAST_RETURN_URL DJANGO_PAYFAST_CANCEL_URL
    DJANGO_PAYFAST_NOTIFY_URL
    DJANGO_MEMBERSHIP_CHECKOUT_URL DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT
    DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY
    DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES
    DJANGO_MEMBERSHIP_SUBSCRIPTION_ITEM_NAME
    DJANGO_MEMBERSHIP_SUBSCRIPTION_DESCRIPTION
)

# Held as container app secrets rather than plain environment variables, and
# referenced with `secretref:`. Table B.
#
# design/deploy.md 4 names Key Vault as where the two encryption keys belong --
# it gives versioning, soft delete and purge protection, which is most of what
# Block 0 P4 asks for. Container app secrets are the interim; moving them is a
# `--secret-volume` or a Key Vault reference on the same identity that already
# reaches blob storage, and it changes nothing else here.
# **`DJANGO_REDIS_URL` is not here, and no longer a secret.** It was, because on
# Azure Managed Redis the access key travels inside the URL. The Redis this
# script creates is reached over the managed environment's internal network with
# no credential in the URL at all, so there is nothing in it to protect -- and
# the script derives it below rather than asking for it, because it cannot be
# written down until the environment's domain is known.
API_SECRET_VARS=(
    DJANGO_SECRET_KEY DJANGO_FIELD_ENCRYPTION_KEY DJANGO_BLIND_INDEX_PEPPER
    DJANGO_DB_PASSWORD
    EMAIL_CC_PASSWORD EMAIL_F2C_PASSWORD
    DJANGO_PAYFAST_MERCHANT_ID DJANGO_PAYFAST_MERCHANT_KEY
    DJANGO_PAYFAST_PASSPHRASE
)

# `DJANGO_CDN_BASE_URL` is deliberately absent from both lists. Table C says
# blank unless the documents container is actually fronted, and a variable set
# to the empty string is not the same as one left unset.

# The club reads four site variables and the market two -- frontend/deploy/
# entrypoint.sh checks `REQUIRED_ENV`, which each Dockerfile sets. Both also
# take the two API addresses and a port.
CLUB_VARS=(
    DJANGO_API_URL DJANGO_API_PUBLIC_URL SITE_URL APP_ENV
    CDN_BASE_URL SUPPORT_EMAIL PORT
)
MARKET_VARS=(DJANGO_API_URL DJANGO_API_PUBLIC_URL SITE_URL APP_ENV PORT)

# The two storefronts read the same variable names with different values, so the
# values file carries the market's under a MARKET_ prefix and they are mapped on
# to the names the image reads at creation time.
MARKET_PREFIXED=(MARKET_DJANGO_API_PUBLIC_URL MARKET_SITE_URL)

# **The two the script sets itself, and they are not read from the values file.**
#
# `DJANGO_REDIS_URL` names the Redis app created below, at the managed
# environment's internal domain -- a value that does not exist until the
# environment does.
#
# `DJANGO_CACHE_ALLOW_PLAINTEXT` is the deliberate downgrade `f2c/cache.py`
# demands, and it is spelled as a permission precisely so that it reads as one
# wherever it appears. **The justification is that this Redis is reached only
# from inside the managed environment**: internal ingress publishes no public
# address, the hop never leaves Azure's network for the environment, and there
# is no access key in the URL that a plaintext connection could disclose --
# which is the loss `cache.py` refuses `redis://` to prevent. What it does not
# claim is that the hop crosses no network at all; it crosses a private one.
# Giving Redis its own certificate and keeping `rediss://` is the stricter
# option, and it costs a certificate to rotate in three environments.
#
# `f2c/queue.py` reads the same switch rather than one of its own, deliberately:
# a second switch could only fail by disagreeing with the first.
DERIVED_VARS=(DJANGO_REDIS_URL DJANGO_CACHE_ALLOW_PLAINTEXT)

required=("${API_PLAIN_VARS[@]}" "${API_SECRET_VARS[@]}" "${CLUB_VARS[@]}")
[ -n "${SKIP_MARKET:-}" ] || required+=("${MARKET_PREFIXED[@]}")

# A value in the file for either of these is a value that would be silently
# overridden, which is worse than being told.
for name in "${DERIVED_VARS[@]}"; do
    if [ -n "${!name:-}" ]; then
        echo "$name is set in $VALUES_FILE, and this script sets it." >&2
        echo "Remove it: the Redis URL names the app created below at the" >&2
        echo "managed environment's internal domain, which is not known until" >&2
        echo "the environment exists." >&2
        exit 1
    fi
done

missing=()
for name in "${required[@]}"; do
    [ -n "${!name:-}" ] || missing+=("$name")
done

if [ "${#missing[@]}" -gt 0 ]; then
    echo "Not set in $VALUES_FILE:" >&2
    printf '  %s\n' "${missing[@]}" >&2
    echo >&2
    echo "Every one of these is read at start-up. The containers refuse to" >&2
    echo "serve without them rather than running degraded -- Tables B to E of" >&2
    echo "design/deploy-quickstart.md, deploy/entrypoint.sh and" >&2
    echo "frontend/deploy/entrypoint.sh." >&2
    exit 1
fi

# ---------------------------------------------------------------- the preflight

echo "Preflight for $ENVIRONMENT in $RESOURCE_GROUP"

az group show --name "$RESOURCE_GROUP" --output none
echo "  resource group        ok"

acr_id=$(az acr show --name "$ACR_NAME" --query id -o tsv)
echo "  registry              ok"

# The managed environment, created if absent along with the workspace it logs
# to. `az containerapp env create` provisions a workspace on its own when none
# is named, but naming it puts the workspace in this environment's resource
# group with a predictable name rather than wherever the command decides.
if az containerapp env show --name "$CONTAINERAPP_ENV" \
        --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "  managed environment   ok"
else
    echo "  managed environment   absent -- creating"

    if ! az monitor log-analytics workspace show \
            --workspace-name "$LOG_WORKSPACE" \
            --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
        echo "    workspace $LOG_WORKSPACE"
        run az monitor log-analytics workspace create \
            --workspace-name "$LOG_WORKSPACE" \
            --resource-group "$RESOURCE_GROUP" \
            --location "$LOCATION" \
            --output none
    fi

    if [ -z "${DRY_RUN:-}" ]; then
        workspace_id=$(az monitor log-analytics workspace show \
            --workspace-name "$LOG_WORKSPACE" \
            --resource-group "$RESOURCE_GROUP" \
            --query customerId -o tsv)
        workspace_key=$(az monitor log-analytics workspace get-shared-keys \
            --workspace-name "$LOG_WORKSPACE" \
            --resource-group "$RESOURCE_GROUP" \
            --query primarySharedKey -o tsv)
    else
        workspace_id='<workspace-id>'
        workspace_key='<workspace-key>'
    fi

    echo "    environment $CONTAINERAPP_ENV"
    run az containerapp env create \
        --name "$CONTAINERAPP_ENV" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --logs-workspace-id "$workspace_id" \
        --logs-workspace-key "$workspace_key" \
        --output none
fi

# The internal domain every app in this environment is addressed at. This is
# what `DJANGO_REDIS_URL` is built from, and it does not exist until the
# environment does -- which is why the values file cannot carry it.
if [ -z "${DRY_RUN:-}" ]; then
    environment_domain=$(az containerapp env show \
        --name "$CONTAINERAPP_ENV" --resource-group "$RESOURCE_GROUP" \
        --query properties.defaultDomain -o tsv)
else
    environment_domain="${environment_domain:-<default-domain>}"
fi

# **Internal, so the host carries `.internal.`.** An app with internal ingress
# is reachable from inside the managed environment and has no public address at
# all, which is the whole basis for the plaintext decision above.
#
# `redis://` and not `rediss://`: Container Apps terminates TLS for HTTP
# ingress, not for the TCP ingress a Redis connection needs.
#
# Database 0. `f2c/queue.py` rewrites the path to `BROKER_DB` for the broker, so
# the queue lands on database 1 of the same instance -- which is the property a
# managed Redis could not provide.
DJANGO_REDIS_URL="redis://${APP_REDIS}.internal.${environment_domain}:${REDIS_PORT}/0"
DJANGO_CACHE_ALLOW_PLAINTEXT=true
echo "  redis url             $DJANGO_REDIS_URL"

# **The data tier, and this is the check worth having.** The API entrypoint runs
# `wait_for_database` and then `check --deploy --fail-level WARNING` before it
# serves anything, so apps created against an environment with no reachable
# MySQL do not start -- they crashloop, and four of the six do it at once.
# Better to refuse here than to hand somebody a red environment to debug.
#
# **The database, cache and storage account do not have to live in this
# environment's resource group**, and in this subscription they do not. Nothing
# in the running application knows or cares: the API reaches MySQL by the
# hostname in `DJANGO_DB_HOST`, Redis by the URL in `DJANGO_REDIS_URL` and blob
# storage by the account name in `DJANGO_*_STORAGE_ACCOUNT`. The three variables
# below are how this check is pointed at wherever they actually are, and `-`
# skips an individual check for a resource this script should not look for.
MYSQL_RESOURCE_GROUP="${MYSQL_RESOURCE_GROUP:-$RESOURCE_GROUP}"
STORAGE_RESOURCE_GROUP="${STORAGE_RESOURCE_GROUP:-$RESOURCE_GROUP}"

data_tier_missing=()

if [ "$MYSQL_RESOURCE_GROUP" != '-' ]; then
    az mysql flexible-server list --resource-group "$MYSQL_RESOURCE_GROUP" \
        --query '[].name' -o tsv 2>/dev/null | grep -q . \
        || data_tier_missing+=("Azure Database for MySQL Flexible Server 8.4 in $MYSQL_RESOURCE_GROUP")
fi

# **No Redis check.** It is one of the apps below, which is the point of the
# header: nothing outside this environment has to exist for the cache and the
# queue to work.

if [ "$STORAGE_RESOURCE_GROUP" != '-' ]; then
    az storage account list --resource-group "$STORAGE_RESOURCE_GROUP" \
        --query '[].name' -o tsv 2>/dev/null | grep -q . \
        || data_tier_missing+=("Storage account in $STORAGE_RESOURCE_GROUP")
fi

if [ "${#data_tier_missing[@]}" -gt 0 ]; then
    echo
    echo "  Not in $RESOURCE_GROUP:" >&2
    printf '    %s\n' "${data_tier_missing[@]}" >&2
    echo >&2
    echo "  The API image gates its own start-up on these: deploy/entrypoint.sh" >&2
    echo "  waits for the database and then runs check --deploy --fail-level" >&2
    echo "  WARNING. Creating the apps now gives four crashlooping containers." >&2
    echo >&2
    echo "  Provision the data tier first -- design/deploy.md section 2 -- or" >&2
    echo "  set FORCE=1 to create the apps anyway." >&2
    [ -n "${FORCE:-}" ] || exit 1
    echo "  FORCE=1: continuing." >&2
fi

# The digest, not the tag. A tag is mutable on this registry tier, so an app
# created against `:qa` is an app whose contents can change with no deployment
# and no record. `acr-digest.sh` is the resolution the deployments already use.
echo
echo "Resolving images at $IMAGE_TAG"
script_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

digest_for() {
    bash "${script_directory}/../.github/scripts/acr-digest.sh" \
        "$ACR_NAME" "f2c/${1}:${IMAGE_TAG}"
}

api_digest=$(digest_for api)
club_digest=$(digest_for club)
echo "  f2c/api@${api_digest}"
echo "  f2c/club@${club_digest}"
if [ -z "${SKIP_MARKET:-}" ]; then
    market_digest=$(digest_for market)
    echo "  f2c/market@${market_digest}"
fi

# ----------------------------------------------------------------- the creation

# Build the `--env-vars` arguments. Plain values as `NAME=value`, secrets as
# `NAME=secretref:<name>` against the secret names set alongside them --
# Container Apps secret names are lowercase, alphanumeric and dashes, so the
# variable name is transposed rather than reused.
api_env_arguments=()
for name in "${API_PLAIN_VARS[@]}" "${DERIVED_VARS[@]}"; do
    api_env_arguments+=("${name}=${!name}")
done

api_secret_arguments=()
for name in "${API_SECRET_VARS[@]}"; do
    secret_name=$(printf '%s' "$name" | tr '[:upper:]_' '[:lower:]-')
    api_secret_arguments+=("${secret_name}=${!name}")
    api_env_arguments+=("${name}=secretref:${secret_name}")
done

exists() {
    az containerapp show --name "$1" --resource-group "$RESOURCE_GROUP" \
        --output none 2>/dev/null
}

# Grant the app's own system-assigned identity `AcrPull`, then tell the app to
# use it. Both steps are needed: the grant alone leaves the app attempting an
# anonymous pull, and the assignment alone leaves it presenting an identity with
# no rights. Role assignments are eventually consistent, so a first revision can
# fail its pull and succeed on the platform's retry.
attach_registry() {
    local container_app="$1" principal

    if [ -n "${DRY_RUN:-}" ]; then
        echo "  [dry-run] grant AcrPull to $container_app and set registry identity"
        return 0
    fi

    principal=$(az containerapp show --name "$container_app" \
        --resource-group "$RESOURCE_GROUP" \
        --query identity.principalId -o tsv)

    if [ -z "$principal" ] || [ "$principal" = 'None' ]; then
        echo "    no system-assigned identity on $container_app" >&2
        return 1
    fi

    az role assignment create \
        --assignee-object-id "$principal" \
        --assignee-principal-type ServicePrincipal \
        --role AcrPull \
        --scope "$acr_id" \
        --output none

    az containerapp registry set \
        --name "$container_app" \
        --resource-group "$RESOURCE_GROUP" \
        --server "$REGISTRY" \
        --identity system \
        --output none
}

create_api_family_app() {
    local container_app="$1" mode="$2" min="$3" max="$4"
    local cpu="$WORKER_CPU" memory="$WORKER_MEMORY"
    local -a ingress_arguments=()

    if exists "$container_app"; then
        echo "  $container_app already exists -- left alone"
        return 0
    fi

    echo "  creating $container_app ($mode)"

    if [ "$mode" = 'serve' ]; then
        cpu="$API_CPU"
        memory="$API_MEMORY"
        # External, because the Payfast notification is an inbound request from
        # Payfast's own servers and `DJANGO_PAYFAST_NOTIFY_URL` has to be
        # internet-reachable. The custom domain and its certificate are a
        # separate step -- design/deploy-quickstart.md.
        ingress_arguments=(--ingress external --target-port 8000 --transport auto)
    fi
    # The other three get no ingress at all. They consume queues; nothing calls
    # them, and `healthState` is empty on a revision without ingress -- which is
    # why deploy-api.sh treats an empty value as success rather than a failure.

    run az containerapp create \
        --name "$container_app" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINERAPP_ENV" \
        --image "${REGISTRY}/f2c/api@${api_digest}" \
        --system-assigned \
        --min-replicas "$min" \
        --max-replicas "$max" \
        --cpu "$cpu" \
        --memory "$memory" \
        --command deploy/entrypoint.sh \
        --args "$mode" \
        --secrets "${api_secret_arguments[@]}" \
        --env-vars "${api_env_arguments[@]}" \
        "${ingress_arguments[@]}" \
        --output none

    attach_registry "$container_app"
}

create_frontend_app() {
    local container_app="$1" digest="$2" repository="$3"
    shift 3
    local -a variable_names=("$@")
    local -a env_arguments=()
    local name

    if exists "$container_app"; then
        echo "  $container_app already exists -- left alone"
        return 0
    fi

    echo "  creating $container_app"

    for name in "${variable_names[@]}"; do
        env_arguments+=("${name}=${!name}")
    done

    run az containerapp create \
        --name "$container_app" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINERAPP_ENV" \
        --image "${REGISTRY}/f2c/${repository}@${digest}" \
        --system-assigned \
        --ingress external \
        --target-port 3000 \
        --transport auto \
        --min-replicas 1 \
        --max-replicas 3 \
        --cpu "$FRONTEND_CPU" \
        --memory "$FRONTEND_MEMORY" \
        --env-vars "${env_arguments[@]}" \
        --output none

    attach_registry "$container_app"
}

create_redis_app() {
    if exists "$APP_REDIS"; then
        echo "  $APP_REDIS already exists -- left alone"
        return 0
    fi

    echo "  creating $APP_REDIS ($REDIS_IMAGE)"

    # **Exactly one replica, and this is a correctness constraint of the same
    # kind as beat's.** Two replicas behind one ingress address are two separate
    # empty Redis processes: connections would be balanced between them, so a
    # throttle counter incremented on one would be invisible to the other, and a
    # task published to one would be consumed by nobody if the worker connected
    # to the other. Nothing would report it. `--min-replicas 1 --max-replicas 1`
    # and no scale rule.
    #
    # **Internal TCP ingress.** `--transport tcp` because Redis is not HTTP, and
    # `--ingress internal` because nothing outside the environment has any
    # business reaching it -- there is no public address to reach. Internal TCP
    # ingress needs `--exposed-port`, and it is the same port so that the URL
    # derived above reads plainly.
    #
    # No registry arguments: this is a public image, not one of ours, so it
    # needs neither an identity nor an AcrPull grant.
    #
    # **`--save ''` is the documented way to remove every snapshot point, and
    # the empty element between two commas is the part to check on the first
    # run** -- `az` splits `--args` on commas and an empty value is the kind of
    # thing a CLI drops. If it does, the fallback is a bare `--save` with no
    # value, which redis-server also reads as empty.
    #
    # **Nothing breaks if it is dropped.** No volume is mounted, so a snapshot
    # would be written to the replica's own writable layer and vanish with it.
    # Getting this wrong costs a periodic fork and some CPU for a file nobody
    # will ever read; it does not make the data any more or less durable.
    run az containerapp create \
        --name "$APP_REDIS" \
        --resource-group "$RESOURCE_GROUP" \
        --environment "$CONTAINERAPP_ENV" \
        --image "$REDIS_IMAGE" \
        --ingress internal \
        --transport tcp \
        --target-port "$REDIS_PORT" \
        --exposed-port "$REDIS_PORT" \
        --min-replicas 1 \
        --max-replicas 1 \
        --cpu "$REDIS_CPU" \
        --memory "$REDIS_MEMORY" \
        --command redis-server \
        --args --save,'',--appendonly,no,--maxmemory,"$REDIS_MAXMEMORY",--maxmemory-policy,noeviction \
        --output none
}

echo
echo "Redis -- the cache on database 0, the queue on database 1"
create_redis_app

echo
echo "The API family -- four apps, one image"

# The API first. It is the process that applies the migrations -- the workers
# deliberately do not, because a second process racing the first through the
# same schema change on every deployment is worse than a slightly longer
# start-up -- and the entrypoint gate names each refused check in its log
# stream. deploy-api.sh keeps the same order on every deployment after this one.
create_api_family_app "$APP_API" serve 1 3
create_api_family_app "$APP_WORKER" worker 1 3
create_api_family_app "$APP_MAIL_WORKER" mail-worker 1 3

# One replica, minimum and maximum. See the header.
create_api_family_app "$APP_BEAT" beat 1 1

echo
echo "The storefronts"
create_frontend_app "$APP_CLUB" "$club_digest" club "${CLUB_VARS[@]}"

if [ -z "${SKIP_MARKET:-}" ]; then
    DJANGO_API_PUBLIC_URL="$MARKET_DJANGO_API_PUBLIC_URL"
    SITE_URL="$MARKET_SITE_URL"
    create_frontend_app "$APP_MARKET" "$market_digest" market "${MARKET_VARS[@]}"
else
    echo "  SKIP_MARKET: no market app"
fi

# ------------------------------------------------------------------- the report

echo
echo "Done. In $RESOURCE_GROUP:"
az containerapp list --resource-group "$RESOURCE_GROUP" \
    --query "[].{name:name, min:properties.template.scale.minReplicas, max:properties.template.scale.maxReplicas, fqdn:properties.configuration.ingress.fqdn, state:properties.provisioningState}" \
    --output table

cat <<'NEXT'

Next, and none of it is optional:

  * Set the six CONTAINERAPP_* GitHub variables for this environment to the
    names above. The deployments read those, and an unset one makes
    `az containerapp update --name ''` fail on a resource that does not exist
    rather than on a name nobody set. **There is no CONTAINERAPP_REDIS**, and
    that is deliberate: `release.yml` and `promote.yml` deploy this project's
    own images, and Redis is a pinned public one. It is created once here and
    updated only when somebody chooses to move the version.

  * Grant the API family's identities Storage Blob Data Contributor on the
    storage account -- design/deploy.md 4 uses managed identity for blob
    access, not account keys, and `DJANGO_DOCUMENT_STORAGE_ACCOUNT` names an
    account with no secret beside it for that reason.

  * Add the custom domains and their certificates, then check that
    DJANGO_ALLOWED_HOSTS, DJANGO_STOREFRONT_HOSTS and the Payfast notify URL
    name the hostnames that now resolve.

  * Re-run release.yml. From here on it deploys rather than fails.
NEXT
