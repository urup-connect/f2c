#!/usr/bin/env bash
#
# One-time setup: the identity GitHub Actions uses to push to the registry and
# roll out container apps, and the GitHub variables the workflows read.
#
# Run it once per environment:
#
#     ENVIRONMENT=qa         ACR_NAME=... RESOURCE_GROUP=rg-f2c-qa-weu  ./azure-oidc-setup.sh
#     ENVIRONMENT=uat        ACR_NAME=... RESOURCE_GROUP=rg-f2c-uat-weu ./azure-oidc-setup.sh
#     ENVIRONMENT=prod       ACR_NAME=... RESOURCE_GROUP=rg-f2c-prod-weu ./azure-oidc-setup.sh
#
# **`prod`, not `production`.** ENVIRONMENT is written straight into the
# federated credential's subject below -- `:environment:${ENVIRONMENT}` -- so it
# has to be the GitHub environment's name exactly. A credential minted for
# `production` is one no job can ever use, because `promote.yml` declares
# `environment: prod` and GitHub presents the subject it declares.
#
# **No passwords anywhere, and that is the point.** The workflows authenticate
# with a federated credential: GitHub mints a short-lived OIDC token, Entra ID
# exchanges it for an access token, and nothing is stored in the repository. It
# is the same argument design/deploy.md section 2 makes for reaching blob storage
# with a managed identity rather than an account key -- a key is a thing that has
# to be rotated, copied between environments and kept out of screenshots.
#
# **One application registration per environment, and the reason is production.**
# A single registration with rights over all three resource groups would mean
# the QA build job holding write access to production. The GitHub environment
# approval would still gate the *workflow*, but the credential itself would not
# be limited, and a credential is worth what it can reach rather than what it is
# usually used for.
#
# The federated credential's subject is `environment:<name>`, so a token can
# only be minted by a job that declares `environment: <name>` -- which is what
# makes the reviewer requirement on UAT and production an enforced gate rather
# than a convention.
#
# Requires the Azure CLI signed in with rights to create app registrations and
# assign roles, and the GitHub CLI signed in with admin on the repository.

set -euo pipefail

# Git Bash rewrites any argument that looks like a Unix path into a Windows one,
# which turns an ARM scope such as `/subscriptions/<id>/resourceGroups/<rg>` into
# `C:/Program Files/Git/subscriptions/...`. The role assignment then fails on a
# scope nobody typed, and the message reads like a permissions problem. Both
# variables are inert anywhere other than MSYS.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

: "${ENVIRONMENT:?ENVIRONMENT is required -- qa, uat or prod}"
: "${ACR_NAME:?ACR_NAME is required -- the shared container registry}"
: "${RESOURCE_GROUP:?RESOURCE_GROUP is required -- the resource group for this environment}"

# **Restricted to the three names, because a typo here is silent.** ENVIRONMENT
# becomes the federated credential's subject, and a credential whose subject no
# workflow declares is not an error anywhere: this script succeeds, the app
# registration and the role assignments are correct, and the first promotion
# fails at `azure/login` with an assertion nobody can match to a cause. That is
# how `production` -- which is not what the environment is called -- survived in
# `promote.yml` until it was found by hand.
case "$ENVIRONMENT" in
    qa|uat|prod) ;;
    *)
        echo "ENVIRONMENT must be qa, uat or prod. Got: ${ENVIRONMENT}" >&2
        echo "It is written into the credential's subject and has to match the" >&2
        echo "GitHub environment name that promote.yml and release.yml declare." >&2
        exit 1
        ;;
esac

# Checked together and up front. Both are needed well before anything is
# created, and `gh` in particular is not installed by default on Windows -- a
# missing one used to surface as a `command not found` after the application
# registration already existed, leaving half a setup behind.
missing=
for tool in az gh; do
    command -v "$tool" >/dev/null 2>&1 || missing="${missing} ${tool}"
done

if [ -n "$missing" ]; then
    echo "Not on PATH:${missing}" >&2
    echo "  az -- https://aka.ms/installazurecli" >&2
    echo "  gh -- winget install --id GitHub.cli, then gh auth login" >&2
    exit 1
fi

REPOSITORY="${REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
APP_NAME="${APP_NAME:-f2c-gha-${ENVIRONMENT}}"

subscription_id=$(az account show --query id -o tsv)
tenant_id=$(az account show --query tenantId -o tsv)

echo "Repository:    $REPOSITORY"
echo "Environment:   $ENVIRONMENT"
echo "Subscription:  $subscription_id"
echo "Registry:      $ACR_NAME"
echo "Resource group: $RESOURCE_GROUP"
echo

# ---------------------------------------------------------- the app registration
app_id=$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)

if [ -z "$app_id" ]; then
    echo "==> Creating the application registration $APP_NAME"
    app_id=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
else
    echo "==> $APP_NAME already exists ($app_id)"
fi

if ! az ad sp show --id "$app_id" >/dev/null 2>&1; then
    echo "==> Creating the service principal"
    az ad sp create --id "$app_id" --output none
fi

sp_object_id=$(az ad sp show --id "$app_id" --query id -o tsv)

# ------------------------------------------------------ the federated credential
#
# The subject ties the credential to jobs that declare this environment. A job
# without `environment: <name>` cannot mint a token with it, however much
# repository access its author has.
#
# `<owner>@<owner id>/<repo>@<repo id>` rather than plain `<owner>/<repo>`: the
# subject GitHub presents carries the immutable numeric IDs alongside the names,
# so a credential holding the names alone is refused as AADSTS700213. The IDs
# are read from the API rather than typed, because they are the one part of the
# subject nobody can check by eye.
credential_name="github-${ENVIRONMENT}"

read -r owner_id repo_id <<<"$(gh api "repos/${REPOSITORY}" --jq '[.owner.id, .id] | @tsv')"
: "${owner_id:?could not read the owner ID of $REPOSITORY}"
: "${repo_id:?could not read the repository ID of $REPOSITORY}"

subject="repo:${REPOSITORY%%/*}@${owner_id}/${REPOSITORY##*/}@${repo_id}:environment:${ENVIRONMENT}"

credential_parameters=$(
    cat <<JSON
{
  "name": "${credential_name}",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "${subject}",
  "description": "GitHub Actions, ${ENVIRONMENT} environment",
  "audiences": ["api://AzureADTokenExchange"]
}
JSON
)

# The subject on record is compared, not merely the credential's existence. A
# repository transfer or a rename leaves a credential that is present and wrong,
# and a script skipping on presence alone reports success while every job that
# needs the credential keeps failing at `azure/login`. Correcting it in place is
# what makes this script worth re-running.
existing_subject=$(az ad app federated-credential show \
    --id "$app_id" \
    --federated-credential-id "$credential_name" \
    --query subject -o tsv 2>/dev/null || true)

if [ -z "$existing_subject" ]; then
    echo "==> Adding the federated credential $credential_name"
    echo "    subject: $subject"
    az ad app federated-credential create \
        --id "$app_id" \
        --parameters "$credential_parameters" \
        --output none
elif [ "$existing_subject" != "$subject" ]; then
    echo "==> Correcting the subject of $credential_name"
    echo "    was: $existing_subject"
    echo "    now: $subject"
    az ad app federated-credential update \
        --id "$app_id" \
        --federated-credential-id "$credential_name" \
        --parameters "$credential_parameters" \
        --output none
else
    echo "==> The federated credential $credential_name is already correct"
    echo "    subject: $subject"
fi

# --------------------------------------------------------------------- the roles
#
# `AcrPush` on the registry, because both `release.yml` and `promote.yml` push
# frontend images -- a promotion rebuilds them (risk R-D4). It includes pull.
registry_id=$(az acr show --name "$ACR_NAME" --query id -o tsv)

# Existence is checked before creating, rather than letting a failed create fall
# through to `|| echo "already assigned"`. That idiom cannot tell an assignment
# that is already there from one Azure refused, so an account without
# `User Access Administrator` reports a clean setup and the pipeline then fails
# much later at a `docker push`, with nothing pointing at a missing role.
assign_role() {
    local role="$1" scope="$2"

    if [ -n "$(az role assignment list \
            --assignee "$sp_object_id" \
            --role "$role" \
            --scope "$scope" \
            --query '[0].id' -o tsv)" ]; then
        echo "    already assigned"
        return
    fi

    az role assignment create \
        --assignee-object-id "$sp_object_id" \
        --assignee-principal-type ServicePrincipal \
        --role "$role" \
        --scope "$scope" \
        --output none
}

echo "==> AcrPush on $ACR_NAME"
assign_role AcrPush "$registry_id"

# `Contributor` scoped to this environment's resource group and nothing wider.
#
# It is broader than this pipeline needs -- the workflows only ever call
# `containerapp update` -- and narrowing it to a custom role carrying
# `Microsoft.App/containerApps/read` and `/write` is the obvious hardening step.
# Recorded here rather than done, because a custom role definition is a fourth
# thing to keep in step across three environments.
echo "==> Contributor on $RESOURCE_GROUP"
assign_role Contributor "/subscriptions/${subscription_id}/resourceGroups/${RESOURCE_GROUP}"

# ---------------------------------------------------------- the GitHub variables
#
# Variables rather than secrets. None of the three identifies a credential that
# can be used on its own: without the federated trust above, and without a job
# running in this repository under this environment, a client ID is not a way in.
# Keeping them readable means whoever is debugging a failed deployment can see
# which subscription it was aimed at.
echo
echo "==> Setting the GitHub environment variables for $ENVIRONMENT"

set_var() {
    gh variable set "$1" --env "$ENVIRONMENT" --repo "$REPOSITORY" --body "$2"
    echo "    $1"
}

set_var AZURE_CLIENT_ID "$app_id"
set_var AZURE_TENANT_ID "$tenant_id"
set_var AZURE_SUBSCRIPTION_ID "$subscription_id"
set_var AZURE_RESOURCE_GROUP "$RESOURCE_GROUP"

# The registry is shared by every environment -- design/deploy.md section 2 --
# so this one is repository-wide.
gh variable set ACR_NAME --repo "$REPOSITORY" --body "$ACR_NAME"
echo "    ACR_NAME (repository-wide)"

cat <<REMAINING

==> Done for $ENVIRONMENT.

Still to set for this environment, because only you know the values. These are
the container app names \`az containerapp create\` was given, and nothing else:
the workflows use them to address the apps, and every setting the apps
themselves read lives on the apps.

  gh variable set --env $ENVIRONMENT \\
      CONTAINERAPP_API          # f2c-api
      CONTAINERAPP_WORKER       # f2c-worker
      CONTAINERAPP_MAIL_WORKER  # f2c-mail-worker
      CONTAINERAPP_BEAT         # f2c-beat
      CONTAINERAPP_CLUB         # f2c-club
      CONTAINERAPP_MARKET       # f2c-market
      DEPLOY_MARKET             # 'true' to deploy the market storefront

APP_ENV, CLUB_SITE_URL, CLUB_CDN_BASE_URL, CLUB_SUPPORT_EMAIL and
MARKET_SITE_URL used to be on that list. They were build arguments, so the
workflow had to carry them from a GitHub variable into \`docker build\`. They are
container app environment variables now -- set on f2c-club and f2c-market as
SITE_URL, APP_ENV, CDN_BASE_URL and SUPPORT_EMAIL, per design/deploy-quickstart.md
tables D and E -- which is what makes one frontend image serve all three
environments (design/deploy.md R-D4). A frontend container missing any of them
refuses to start.

DEPLOY_MARKET gates the market storefront everywhere, which is decision D2 --
QA can skip it while the store is on the back burner. It saves a container app,
two DNS records and a certificate, and it saves none of the EMAIL_F2C_* entries:
the API refuses to start without a working market mailer whether the market
frontend is deployed or not.

Two things this script does not do:

  1. **Reviewers on UAT and production.** Set them in Settings > Environments.
     Without them, promote.yml deploys to production the moment somebody
     dispatches it, and the approval record is the audit trail that matters when
     R-D1 and R-D2 are written up.

  2. **Let the container apps pull.** Each app needs its own managed identity
     with AcrPull on the registry, which is separate from the push rights above:

       az containerapp identity assign -n <app> -g $RESOURCE_GROUP --system-assigned
       principal=\$(az containerapp show -n <app> -g $RESOURCE_GROUP \\
           --query identity.principalId -o tsv)
       az role assignment create --assignee-object-id "\$principal" \\
           --assignee-principal-type ServicePrincipal \\
           --role AcrPull --scope $registry_id
       az containerapp registry set -n <app> -g $RESOURCE_GROUP \\
           --server ${ACR_NAME}.azurecr.io --identity system

     Do that for all six, and turn the registry's admin user off:

       az acr update --name $ACR_NAME --admin-enabled false

REMAINING
