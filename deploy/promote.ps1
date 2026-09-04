# Promote a release to UAT or production from the command line.
#
#     .\deploy\promote.ps1 -To uat
#     .\deploy\promote.ps1 -To uat -Sha 6bff916
#     .\deploy\promote.ps1 -To uat -Artefacts api
#     .\deploy\promote.ps1 -To prod -Artefacts api,club,market
#
# **This does not deploy anything itself. It dispatches `promote.yml`.** That is
# the point rather than a limitation: the workflow holds the environment
# approval gates, the OIDC credential, the `promote-<env>` concurrency lock and
# the audit trail, and every one of those is lost by a script that calls
# `az containerapp update` from a laptop. What this adds is the pre-flight --
# the ways a promotion is refused after you have gone to the Actions tab,
# checked here in a couple of seconds instead.
#
# **The pre-flight that matters is the artefact check.** `promote.yml` resolves
# `f2c/<artefact>:<sha>` in the registry, and `release.yml` only builds the
# artefacts a commit changed -- so promoting a commit that touched the API alone
# with `-Artefacts api,club` fails on the club, halfway, after the API has
# already rolled. There is nothing wrong with either workflow; the trap is that
# a SHA names three artefacts and only some of them exist at it. This script
# checks each one against the build jobs of that commit's release run and names
# the last commit that did build it.
#
# Nothing here talks to Azure. `gh` is the only dependency, which also means it
# works on a machine whose `az` cannot reach the registry -- see whereis.ps1.

param(
    [Parameter(Mandatory)]
    # The GitHub environment names, which are also `promote.yml`'s `to_env`
    # choices and the moving registry tags. `prod`, not `production` -- see the
    # note on `options:` in that workflow.
    [ValidateSet("uat", "prod")]
    [string]$To,

    # Defaults to HEAD. A short SHA is expanded; anything git can resolve works.
    [string]$Sha,

    # `promote.yml` defaults to api + club, and so does this. The market
    # storefront is optional per environment -- design/deploy.md D2 -- and the
    # workflow drops it where `DEPLOY_MARKET` is not `true`.
    [ValidateSet("api", "club", "market")]
    [string[]]$Artefacts = @("api", "club"),

    # Promote to production something UAT is not running. Recorded in the run.
    [switch]$SkipLadderCheck,

    [switch]$NoWatch,

    # Skip the confirmation. Production still refuses to be forced.
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Failure {
    param([string]$Message, [string[]]$Detail = @())
    Write-Host ""
    Write-Host "  $Message" -ForegroundColor Red
    foreach ($line in $Detail) { Write-Host "  $line" -ForegroundColor DarkGray }
    Write-Host ""
    exit 1
}

function Write-Step {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor DarkGray
}

# ----------------------------------------------------------------- the tooling
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Failure "The GitHub CLI is not on PATH." @(
        "winget install GitHub.cli, then gh auth login"
    )
}

gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Failure "The GitHub CLI is not signed in." @("gh auth login")
}

$repo = (gh repo view --json nameWithOwner -q .nameWithOwner).Trim()
$trunk = (gh repo view --json defaultBranchRef -q .defaultBranchRef.name).Trim()

Write-Host ""
Write-Host "Promoting to $To" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------ the commit
if (-not $Sha) { $Sha = "HEAD" }

$resolved = (git rev-parse --verify "$Sha^{commit}" 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $resolved) {
    Write-Failure "'$Sha' is not a commit this clone can resolve."
}
$Sha = $resolved.Trim()
$short = $Sha.Substring(0, 7)

$subject = (git log -1 --format=%s $Sha 2>$null)
Write-Step "commit    $short  $subject"

# On origin, because the registry only holds images for commits CI has seen. A
# promotion of an unpushed commit fails in `verify` on "couldn't find remote
# ref", which reads like a bad SHA rather than a forgotten push.
gh api "repos/$repo/commits/$Sha" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Failure "$short is not on origin." @("Push it first: git push")
}

# ------------------------------------------------------------- the environment
# `promote.yml` declares `environment: ${{ inputs.to_env }}`, and GitHub creates
# an environment that does not exist rather than refusing -- with no variables
# and, more to the point, no required reviewers. So a target whose name does not
# match a configured environment does not fail safe: it fails *open* on the
# approval gate and then dies later on an unset variable. Checked here.
gh api "repos/$repo/environments/$To" *> $null
if ($LASTEXITCODE -ne 0) {
    $configured = (gh api "repos/$repo/environments" --jq '.environments[].name') -join ", "
    Write-Failure "There is no GitHub environment called '$To'." @(
        "Configured: $configured",
        "Dispatching anyway would not fail: GitHub creates the environment,",
        "with no variables and no required reviewers, so the approval gate",
        "would not apply and the run would die later on an unset variable.",
        "Create it in Settings > Environments, or fix promote.yml's choices."
    )
}

# --------------------------------------------------------------- the artefacts
# For each artefact asked for, did `release.yml` build an image at this commit?
# Any successful build counts, including one from an earlier run of the same
# commit: once a layer is pushed the tag stays in the registry.
function Get-BuildJobPattern {
    param([string]$Artefact)
    if ($Artefact -eq "api") { return "^Build the API image$" }
    return "^Build the $Artefact image$"
}

function Test-ArtefactBuilt {
    param([string]$Artefact, [string]$Commit)

    $runs = @(gh run list --workflow release.yml --commit $Commit `
            --limit 10 --json databaseId -q '.[].databaseId' 2>$null)
    if ($runs.Count -eq 0) { return $false }

    $pattern = Get-BuildJobPattern $Artefact
    foreach ($run in $runs) {
        $jobs = @(gh run view $run --json jobs `
                -q '.jobs[] | select(.conclusion == "success") | .name' 2>$null)
        foreach ($job in $jobs) {
            if ($job -match $pattern) { return $true }
        }
    }
    return $false
}

function Find-LastBuild {
    param([string]$Artefact)

    $entries = @(gh run list --workflow release.yml --limit 15 `
            --json databaseId,headSha -q '.[] | "\(.databaseId) \(.headSha)"' 2>$null)

    $pattern = Get-BuildJobPattern $Artefact
    foreach ($entry in $entries) {
        $parts = $entry -split ' '
        $jobs = @(gh run view $parts[0] --json jobs `
                -q '.jobs[] | select(.conclusion == "success") | .name' 2>$null)
        foreach ($job in $jobs) {
            if ($job -match $pattern) { return $parts[1] }
        }
    }
    return $null
}

Write-Step "checking each artefact has an image at this commit"
Write-Host ""

$missing = @()
foreach ($artefact in $Artefacts) {
    if (Test-ArtefactBuilt $artefact $Sha) {
        Write-Host "    built    $artefact" -ForegroundColor Green
    }
    else {
        Write-Host "    missing  $artefact" -ForegroundColor Yellow
        $missing += $artefact
    }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "  No image at $short for: $($missing -join ', ')" -ForegroundColor Red
    Write-Host ""
    Write-Host "  release.yml builds only what a commit changed, so a SHA does not" -ForegroundColor DarkGray
    Write-Host "  necessarily name all three artefacts. promote.yml would refuse" -ForegroundColor DarkGray
    Write-Host "  these -- after promoting whichever artefacts do exist." -ForegroundColor DarkGray
    Write-Host ""
    foreach ($artefact in $missing) {
        $last = Find-LastBuild $artefact
        if ($last) {
            $lastSubject = (git log -1 --format=%s $last 2>$null)
            if (-not $lastSubject) { $lastSubject = "(not in this clone)" }
            Write-Host "    $artefact last built at $($last.Substring(0,7))  $lastSubject" -ForegroundColor DarkGray
        }
        else {
            Write-Host "    $artefact has no successful build in the last 15 runs" -ForegroundColor DarkGray
        }
    }
    $keep = @($Artefacts | Where-Object { $missing -notcontains $_ })
    Write-Host ""
    if ($keep.Count -gt 0) {
        Write-Host "  Either drop it -- -Artefacts $($keep -join ',') -- or promote a" -ForegroundColor DarkGray
        Write-Host "  commit that has all of them." -ForegroundColor DarkGray
    }
    else {
        Write-Host "  Promote a commit that has been built." -ForegroundColor DarkGray
    }
    Write-Host ""
    exit 1
}

# ------------------------------------------------------------------ the ladder
# Not re-implemented here. `promote.yml` reads `f2c/<artefact>:uat` in the
# registry, which is the only thing that knows what UAT is actually running --
# this script has no Azure credential and should not have one. Said out loud so
# that the check being server-side is not mistaken for the check being absent.
if ($To -eq "prod") {
    Write-Host ""
    if ($SkipLadderCheck) {
        Write-Host "  skip_ladder_check is set: production may receive a release" -ForegroundColor Yellow
        Write-Host "  UAT never ran. The run records it." -ForegroundColor Yellow
    }
    else {
        Write-Step "the ladder check runs in the workflow, against the :uat tag"
    }
}

# ------------------------------------------------------------------ confirmation
$wanted = @{ api = "false"; club = "false"; market = "false" }
foreach ($artefact in $Artefacts) { $wanted[$artefact] = "true" }

Write-Host ""
Write-Host "  target    $To"
Write-Host "  commit    $Sha"
Write-Host "  artefacts $($Artefacts -join ', ')"
if ($wanted["api"] -eq "true") {
    Write-Host "            the API carries worker, mail-worker and beat with it" -ForegroundColor DarkGray
}
Write-Host ""

if ($To -eq "prod") {
    # Typed, not a keypress, and `-Force` does not skip it. Production is the
    # one target where the cost of a wrong SHA is members' money.
    $answer = Read-Host "  Type PROD to promote, anything else to stop"
    if ($answer -ne "PROD") {
        Write-Host "  Stopped." -ForegroundColor Yellow
        exit 1
    }
}
elseif (-not $Force) {
    $answer = Read-Host "  Promote to $To? [y/N]"
    if ($answer -notmatch '^(y|yes)$') {
        Write-Host "  Stopped." -ForegroundColor Yellow
        exit 1
    }
}

# --------------------------------------------------------------------- dispatch
# `--ref` is trunk, never the promoted commit: `promote.yml` reads its
# deployment scripts from trunk on purpose, so that a fix to the roll-out order
# reaches the promotion of an older commit. Running the workflow *file* from an
# old ref would undo that.
Write-Host ""
Write-Step "dispatching promote.yml on $trunk"

$before = (gh run list --workflow promote.yml --limit 1 --json databaseId -q '.[0].databaseId' 2>$null)

gh workflow run promote.yml --ref $trunk `
    -f sha=$Sha `
    -f to_env=$To `
    -f api=$($wanted["api"]) `
    -f club=$($wanted["club"]) `
    -f market=$($wanted["market"]) `
    -f skip_ladder_check=$(if ($SkipLadderCheck) { "true" } else { "false" })

if ($LASTEXITCODE -ne 0) { Write-Failure "The dispatch was refused." }

# `gh workflow run` returns before the run is queued, so the id is not knowable
# immediately. Poll briefly for a run newer than the one that was newest before.
$runId = $null
foreach ($attempt in 1..15) {
    Start-Sleep -Seconds 2
    $candidate = (gh run list --workflow promote.yml --limit 1 --json databaseId -q '.[0].databaseId' 2>$null)
    if ($candidate -and $candidate -ne $before) {
        $runId = $candidate
        break
    }
}

if (-not $runId) {
    Write-Host "  Dispatched. The run had not appeared yet." -ForegroundColor Yellow
    Write-Host "  gh run list --workflow promote.yml" -ForegroundColor DarkGray
    exit 0
}

Write-Host "  run       https://github.com/$repo/actions/runs/$runId" -ForegroundColor Cyan
Write-Host ""

if ($NoWatch) { exit 0 }

# An approval gate holds the run at `waiting`, which `gh run watch` reports
# rather than hangs on. Ctrl+C here leaves the promotion running.
gh run watch $runId --exit-status
exit $LASTEXITCODE
