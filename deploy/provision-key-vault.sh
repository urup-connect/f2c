#!/usr/bin/env bash
#
# Create the Key Vault, the identity that reads it, and every grant either of
# them needs -- once per environment, before the container apps exist.
#
# **This is step 3 of design/deploy-quickstart.md, and it now has to run before
# step 5** rather than being a page of Portal clicks nobody can reproduce for
# UAT and production. It creates four things and grants five:
#
#   kv-f2c-<env>-weu    the vault. RBAC authorisation, purge protection on
#   id-f2c-<env>        one user-assigned managed identity, shared by all six
#                       container apps
#   log-<rg>            the Log Analytics workspace, if absent -- the same one
#                       provision-container-apps.sh would create, by the same
#                       name, so whichever runs first wins and the other reuses
#   AuditEvent          a diagnostic setting on the vault, into that workspace
#
#   Key Vault Secrets User          -> the identity, at vault scope
#   Key Vault Secrets Officer       -> whoever runs this, at vault scope
#   Storage Blob Data Contributor   -> the identity, on both storage accounts
#   AcrPull                         -> the identity, on the shared registry
#
# **Azure RBAC and not vault access policies, and the reason is the pipeline.**
# design/deploy.md 6.5 gives each environment's GitHub application registration
# `Contributor` on that environment's resource group. Under RBAC, `Contributor`
# carries no data-plane rights at all -- it cannot read a secret. Under access
# policies it can add itself to the policy list and then read everything, so the
# QA build job would hold the field encryption key. That is the whole of what D4
# and R-D2 exist to prevent, so the authorisation model is not a preference.
#
# **One user-assigned identity, not six system-assigned ones.** A system-assigned
# identity does not exist until its app does, so it cannot be granted anything
# before creation -- and a Key Vault reference set at creation time therefore
# fails. Six apps times two grants times three environments is thirty-six role
# assignments that have to be made in the gap between an app existing and
# working. One identity, created first, is one grant each and no gap.
#
# The cost is a single environment variable. `documents/storage.py` and
# `accounts/storage.py` call `DefaultAzureCredential()` with no client id, so a
# container carrying more than one identity cannot tell which to present:
# `AZURE_CLIENT_ID` is what disambiguates it, and provision-container-apps.sh
# sets it on the API family from this script's output. No code change.
#
# **Public endpoint, and that is forced rather than chosen.**
# provision-container-apps.sh creates the managed environment with no
# infrastructure subnet, so it is Consumption-only on a Microsoft-managed
# network: there is no subnet of ours for a private endpoint to terminate in and
# none for a service endpoint to come from. The apps' outbound addresses are
# readable but Azure does not contract to keep them stable, so an IP allow-list
# is an outage waiting for a platform-side change -- and Container Apps is not
# on the "trusted Microsoft services" list, so that checkbox does not help
# either.
#
# What protects the vault is that its data plane is Entra-authenticated. There
# is no anonymous read on a public Key Vault endpoint, and a leaked vault URI is
# worth nothing without a token for a principal holding Secrets User. The
# AuditEvent setting is the other half: every read of the field key becomes a
# queryable row, which is what Block 0 P4 asks for and part of what R-D2 says
# still has to be written down.
#
# The private posture is not a vault setting -- it is a VNet-integrated
# environment with workload profiles, a private endpoint and a
# `privatelink.vaultcore.azure.net` zone. An existing managed environment cannot
# be moved onto a VNet, so it is a re-create. design/deploy.md 8 D4.
#
# **Purge protection is irreversible, and it reserves the name.** Once on it
# cannot be turned off, and a vault deleted by mistake sits in the soft-deleted
# state for the full retention period with its name unusable by anything else.
# So the name is worth getting right first: 3-24 characters, globally unique
# across Azure, alphanumeric and hyphens. A soft-deleted vault of the same name
# is recovered rather than worked around -- this script does that.
#
# Usage:
#
#     ENVIRONMENT=qa \
#     RESOURCE_GROUP=rg-f2c-qa-weu \
#     ACR_NAME=crf2cweu \
#     VALUES_FILE=deploy/qa.values.env \
#         ./deploy/provision-key-vault.sh
#
#   DRY_RUN=1      print every mutating command instead of running it
#   VAULT_NAME     defaults to kv-f2c-<env>-weu
#   IDENTITY_NAME  defaults to id-f2c-<env>
#   LOCATION       defaults to westeurope
#   SKIP_SECRETS=1 create the vault and the grants, load no secret values --
#                  for an environment whose keys are not generated yet
#   ROTATE=1       write a new version of a secret that already has a value.
#                  Read the warning above the secrets section first
#
# It is idempotent. Everything that exists is reported and left as it stands,
# including the secret values: a re-run does not create a second version of a
# key, because a new version of DJANGO_FIELD_ENCRYPTION_KEY is not a harmless
# thing to do by accident.

set -euo pipefail

# ------------------------------------------------------------------- the inputs

: "${ENVIRONMENT:?ENVIRONMENT is required -- qa, uat or prod}"
: "${RESOURCE_GROUP:?RESOURCE_GROUP is required -- e.g. rg-f2c-qa-weu}"
: "${ACR_NAME:?ACR_NAME is required -- e.g. crf2cweu}"
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

VAULT_NAME="${VAULT_NAME:-kv-f2c-${ENVIRONMENT}-weu}"
IDENTITY_NAME="${IDENTITY_NAME:-id-f2c-${ENVIRONMENT}}"
LOCATION="${LOCATION:-westeurope}"
LOG_WORKSPACE="${LOG_WORKSPACE:-log-${RESOURCE_GROUP}}"

# 90 days, the maximum. The floor is 7, and the difference between them is how
# long a deleted vault can still be recovered from -- R-D2 is that losing the
# field key destroys every stored identity number, so there is no argument here
# for a shorter window.
RETENTION_DAYS="${RETENTION_DAYS:-90}"

if [ ${#VAULT_NAME} -lt 3 ] || [ ${#VAULT_NAME} -gt 24 ]; then
    echo "VAULT_NAME must be 3-24 characters, got ${#VAULT_NAME}: $VAULT_NAME" >&2
    exit 1
fi

run() {
    if [ -n "${DRY_RUN:-}" ]; then
        printf '  [dry-run]'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

# shellcheck disable=SC1090
set -a
. "$VALUES_FILE"
set +a

# The two the vault holds. Container Apps and Key Vault both take lowercase,
# alphanumeric and dashes for a secret name, so the variable name is transposed
# rather than reused -- the same transposition provision-container-apps.sh
# makes, and the reference it builds depends on these matching.
VAULT_VARS=(DJANGO_FIELD_ENCRYPTION_KEY DJANGO_BLIND_INDEX_PEPPER)

secret_name_for() {
    printf '%s' "$1" | tr '[:upper:]_' '[:lower:]-'
}

echo
echo "Key Vault and identity for $ENVIRONMENT"
echo "  vault      $VAULT_NAME"
echo "  identity   $IDENTITY_NAME"
echo "  group      $RESOURCE_GROUP"
echo "  location   $LOCATION"
[ -n "${DRY_RUN:-}" ] && echo "  DRY_RUN    nothing will be created"

# ---------------------------------------------------------------- the workspace

# Created here only because the vault's audit log needs somewhere to land and
# this script runs before the one that would otherwise create it. Same name and
# same resource group, so provision-container-apps.sh finds it and reuses it.
echo
echo "Log Analytics workspace"
if az monitor log-analytics workspace show --workspace-name "$LOG_WORKSPACE" \
        --resource-group "$RESOURCE_GROUP" --output none 2>/dev/null; then
    echo "  $LOG_WORKSPACE ok"
else
    echo "  $LOG_WORKSPACE absent -- creating"
    run az monitor log-analytics workspace create \
        --workspace-name "$LOG_WORKSPACE" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
fi

# ----------------------------------------------------------------- the identity

echo
echo "User-assigned managed identity"
if az identity show --name "$IDENTITY_NAME" --resource-group "$RESOURCE_GROUP" \
        --output none 2>/dev/null; then
    echo "  $IDENTITY_NAME ok"
else
    echo "  $IDENTITY_NAME absent -- creating"
    run az identity create \
        --name "$IDENTITY_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
fi

if [ -n "${DRY_RUN:-}" ]; then
    identity_client_id="<identity-client-id>"
    identity_principal_id="<identity-principal-id>"
else
    identity_client_id=$(az identity show --name "$IDENTITY_NAME" \
        --resource-group "$RESOURCE_GROUP" --query clientId -o tsv)
    identity_principal_id=$(az identity show --name "$IDENTITY_NAME" \
        --resource-group "$RESOURCE_GROUP" --query principalId -o tsv)
fi

# -------------------------------------------------------------------- the vault

echo
echo "Key Vault"
if az keyvault show --name "$VAULT_NAME" --resource-group "$RESOURCE_GROUP" \
        --output none 2>/dev/null; then
    echo "  $VAULT_NAME ok"
elif az keyvault list-deleted --query "[?name=='${VAULT_NAME}'].name" -o tsv \
        2>/dev/null | grep -q .; then
    # Purge protection means the name is not available to anything else until
    # the retention window closes, so recovery is the only way forward -- and it
    # is also what you want, because the secret versions come back with it.
    echo "  $VAULT_NAME is soft-deleted -- recovering"
    run az keyvault recover --name "$VAULT_NAME" --output none
else
    echo "  $VAULT_NAME absent -- creating"
    run az keyvault create \
        --name "$VAULT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --sku standard \
        --enable-rbac-authorization true \
        --enable-purge-protection true \
        --retention-days "$RETENTION_DAYS" \
        --public-network-access Enabled \
        --output none
fi

if [ -n "${DRY_RUN:-}" ]; then
    vault_id="<vault-resource-id>"
    vault_uri="https://${VAULT_NAME}.vault.azure.net/"
else
    vault_id=$(az keyvault show --name "$VAULT_NAME" \
        --resource-group "$RESOURCE_GROUP" --query id -o tsv)
    vault_uri=$(az keyvault show --name "$VAULT_NAME" \
        --resource-group "$RESOURCE_GROUP" --query properties.vaultUri -o tsv)
fi

# **The audit log is the compensating control for the public endpoint**, so it
# is created with the vault rather than left as a thing to remember. AuditEvent
# is every data-plane operation: each read of the field key, and who made it.
echo
echo "Diagnostic setting"
if [ -n "${DRY_RUN:-}" ]; then
    echo "  [dry-run] AuditEvent -> $LOG_WORKSPACE"
elif az monitor diagnostic-settings show --name kv-audit \
        --resource "$vault_id" --output none 2>/dev/null; then
    echo "  kv-audit ok"
else
    echo "  kv-audit absent -- creating"
    workspace_id=$(az monitor log-analytics workspace show \
        --workspace-name "$LOG_WORKSPACE" --resource-group "$RESOURCE_GROUP" \
        --query id -o tsv)
    az monitor diagnostic-settings create \
        --name kv-audit \
        --resource "$vault_id" \
        --workspace "$workspace_id" \
        --logs '[{"category":"AuditEvent","enabled":true}]' \
        --output none
fi

# ------------------------------------------------------------------- the grants

# Role assignments are eventually consistent, and `create` fails on one that
# already exists -- so each is checked first, by role and scope rather than by
# name.
grant() {
    local principal="$1" role="$2" scope="$3" principal_type="${4:-ServicePrincipal}"

    if [ -n "${DRY_RUN:-}" ]; then
        echo "  [dry-run] $role on ${scope##*/}"
        return 0
    fi

    if az role assignment list --assignee "$principal" --role "$role" \
            --scope "$scope" --query '[].id' -o tsv 2>/dev/null | grep -q .; then
        echo "  $role on ${scope##*/} ok"
        return 0
    fi

    echo "  $role on ${scope##*/} -- granting"
    az role assignment create \
        --assignee-object-id "$principal" \
        --assignee-principal-type "$principal_type" \
        --role "$role" \
        --scope "$scope" \
        --output none
}

echo
echo "Role assignments"

# Read a secret value, and nothing else. Not Secrets Officer, not Administrator:
# the running application never writes a secret, never lists the vault and never
# purges one.
grant "$identity_principal_id" 'Key Vault Secrets User' "$vault_id"

# Whoever is running this, so the secret values below can be written -- and so
# there is a named human who can read the vault back in an incident. **This is
# the break-glass access R-D2 says has to be written down**, and one holder is
# not enough: add the second by hand, because a script cannot know who it is.
if [ -n "${DRY_RUN:-}" ]; then
    echo "  [dry-run] Key Vault Secrets Officer for the signed-in user"
else
    caller_id=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)
    if [ -n "$caller_id" ]; then
        grant "$caller_id" 'Key Vault Secrets Officer' "$vault_id" User
    else
        # A service principal ran this. It still needs the grant to write the
        # secrets, and `signed-in-user` does not answer for one.
        caller_id=$(az account show --query user.name -o tsv)
        grant "$caller_id" 'Key Vault Secrets Officer' "$vault_id"
    fi
fi

# Blob storage, on both accounts. design/deploy.md 2: no account key, no SAS and
# no connection string -- `DefaultAzureCredential` and a role assignment. This
# is the grant deploy-quickstart.md used to list as still-by-hand after step 5.
storage_accounts=$(printf '%s\n%s\n' \
    "${DJANGO_DOCUMENT_STORAGE_ACCOUNT:-}" "${DJANGO_AVATAR_STORAGE_ACCOUNT:-}" \
    | grep -v '^$' | sort -u)

if [ -z "$storage_accounts" ]; then
    echo "  no storage account named in $VALUES_FILE -- skipping blob grants" >&2
else
    while read -r account; do
        [ -z "$account" ] && continue
        if [ -n "${DRY_RUN:-}" ]; then
            account_id="<${account}-resource-id>"
        else
            account_id=$(az storage account show --name "$account" \
                --query id -o tsv 2>/dev/null || true)
            if [ -z "$account_id" ]; then
                echo "  storage account not found: $account" >&2
                echo "  Grant Storage Blob Data Contributor by hand once it exists." >&2
                continue
            fi
        fi
        grant "$identity_principal_id" 'Storage Blob Data Contributor' "$account_id"
    done <<< "$storage_accounts"
fi

# The registry, so the one identity every app already carries can also pull.
# One assignment where six system-assigned identities needed six, and it is what
# lets `az acr update --admin-enabled false` stay true.
if [ -n "${DRY_RUN:-}" ]; then
    acr_id="<registry-resource-id>"
else
    acr_id=$(az acr show --name "$ACR_NAME" --query id -o tsv)
fi
grant "$identity_principal_id" AcrPull "$acr_id"

# ------------------------------------------------------------------ the secrets

# **A re-run does not touch a secret that already has a value.** A second
# version of DJANGO_FIELD_ENCRYPTION_KEY is not a harmless artefact: the
# container app reference is unversioned, so the next revision would start
# encrypting under the new key while every existing row is still under the old
# one. ROTATE=1 is the deliberate path, and it is deliberate precisely because
# re-encrypting existing rows is the procedure R-D2 says is still unwritten.
echo
echo "Secrets"

if [ -n "${SKIP_SECRETS:-}" ]; then
    echo "  SKIP_SECRETS=1 -- vault and grants only"
else
    for name in "${VAULT_VARS[@]}"; do
        secret_name=$(secret_name_for "$name")
        value="${!name:-}"

        if [ -z "$value" ]; then
            echo "  $name is empty in $VALUES_FILE" >&2
            echo "  Generate it: python design/tools/generate_keys.py" >&2
            exit 1
        fi

        if [ -n "${DRY_RUN:-}" ]; then
            echo "  [dry-run] set $secret_name (value not printed)"
            continue
        fi

        if [ -z "${ROTATE:-}" ] && az keyvault secret show \
                --vault-name "$VAULT_NAME" --name "$secret_name" \
                --output none 2>/dev/null; then
            echo "  $secret_name already has a value -- left alone"
            continue
        fi

        # The Secrets Officer grant above may not have propagated yet, and this
        # is the one place in either script where a retry is worth having.
        for attempt in 1 2 3 4 5 6; do
            if az keyvault secret set --vault-name "$VAULT_NAME" \
                    --name "$secret_name" --value "$value" \
                    --output none 2>/dev/null; then
                echo "  $secret_name set"
                break
            fi
            if [ "$attempt" = 6 ]; then
                echo "  could not write $secret_name" >&2
                echo "  Key Vault Secrets Officer may not have propagated -- retry shortly." >&2
                exit 1
            fi
            sleep 10
        done
    done
fi

# -------------------------------------------------------------------- what next

echo
echo "Done."
echo
echo "  Vault           $vault_uri"
echo "  Identity        $IDENTITY_NAME"
echo "  Client id       $identity_client_id"
echo
echo "provision-container-apps.sh takes the identity by name, and sets"
echo "AZURE_CLIENT_ID on the API family from it:"
echo
echo "  \$env:USER_IDENTITY=\"$IDENTITY_NAME\""
echo
echo "The two keys are in the vault now, so **delete them from $VALUES_FILE**."
echo "The container apps reference the vault rather than holding a copy, and"
echo "that file is the only place left with both in plaintext."
echo
echo "Still by hand, and a script cannot do either:"
echo
echo "  * A second Key Vault Secrets Officer, so break-glass is not one person"
echo "  * The rotation and recovery drill R-D2 asks for. Re-encrypting existing"
echo "    rows under a new field key is the part that does not exist yet"
