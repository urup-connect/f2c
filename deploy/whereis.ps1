# What is running in QA, UAT and production -- read from the registry.
#
#     .\deploy\whereis.ps1
#     .\deploy\whereis.ps1 -Digests
#
# **The moving environment tags are the answer, and they are trustworthy.**
# `release.yml` and `promote.yml` each move `f2c/<artefact>:<env>` as the *last*
# step of a successful deployment, so the tag means "this is running here"
# rather than "somebody tried to put this here" -- deploy.md 6.4, and it is what
# the production ladder check reads. Every manifest also carries its commit as a
# `:<sha>` tag, so a digest resolves back to a commit without a trip to the
# portal.
#
# **This reads the registry and nothing else.** It does not query the container
# apps. A revision pinned to a digest cannot drift from the tag that named it,
# and the case the tag would miss -- somebody pinning an old revision by hand to
# roll back -- is a case where the person doing it knows what they did. If that
# ever needs to be authoritative, `az containerapp show --query
# properties.template.containers[0].image` per app is the query.
#
# Needs `az` to reach the registry's data plane, which is the one thing here
# that a TLS-intercepting proxy breaks. Where it cannot, the fallback prints
# what CI has *built* instead, clearly labelled, because a build history is not
# a deployment record.

param(
    # Defaults to the ACR_NAME repository variable, so there is nothing to keep
    # in step by hand.
    [string]$Registry,

    [ValidateSet("api", "club", "market")]
    [string[]]$Artefacts = @("api", "club", "market"),

    # Show the manifest digests as well as the commits.
    [switch]$Digests
)

$ErrorActionPreference = "Stop"

# The moving tags, which are named from `promote.yml`'s `to_env` and so are the
# GitHub environment names exactly: `prod`, not `production`.
$environments = @("qa", "uat", "prod")

function Invoke-Native {
    # Native commands whose stderr is noise -- `az acr manifest` is in preview
    # and says so on every call -- and whose failure is a return value rather
    # than an exception. Returns stdout, or $null on a non-zero exit.
    param([string]$Command, [string[]]$Arguments)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Command @Arguments 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return $output
    }
    catch {
        return $null
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Get-CommitLabel {
    # A commit is only describable if this clone has it. A promotion made from
    # someone else's branch, or before the last fetch, will not be.
    param([string]$Sha)
    if (-not $Sha) { return "" }
    $subject = Invoke-Native git @("log", "-1", "--format=%s", $Sha)
    if (-not $subject) { return "$($Sha.Substring(0,7))  (not in this clone)" }
    return "$($Sha.Substring(0,7))  $subject"
}

# ----------------------------------------------------------------- the registry
if (-not $Registry) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "  Pass -Registry, or install the GitHub CLI so the ACR_NAME" -ForegroundColor Red
        Write-Host "  repository variable can be read." -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    $Registry = Invoke-Native gh @("variable", "get", "ACR_NAME")
    if ($Registry) { $Registry = $Registry.Trim() }
}

if (-not $Registry) {
    Write-Host ""
    Write-Host "  Could not determine the registry. Pass -Registry <name>." -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "Registry $Registry" -ForegroundColor Cyan

function Get-Manifests {
    # Two spellings, for the reason `.github/scripts/acr-digest.sh` gives: the
    # Azure CLI moved this command and the older one still answers on installed
    # CLIs, so trying both means a CLI update cannot break this script.
    param([string]$Repository)

    $query = "[].{digest:digest,tags:tags}"

    $json = Invoke-Native az @(
        "acr", "manifest", "list-metadata",
        "--registry", $Registry, "--name", $Repository,
        "--query", $query, "-o", "json"
    )

    if (-not $json) {
        $json = Invoke-Native az @(
            "acr", "repository", "show-manifests",
            "--name", $Registry, "--repository", $Repository,
            "--query", $query, "-o", "json"
        )
    }

    if (-not $json) { return $null }
    try { return ($json | ConvertFrom-Json) } catch { return $null }
}

# A single probe first, so an unreachable registry is reported once rather than
# once per artefact.
$probe = Get-Manifests "f2c/$($Artefacts[0])"

if ($null -eq $probe) {
    Write-Host ""
    Write-Host "  The registry did not answer." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    az acr manifest list-metadata --registry $Registry --name f2c/api" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  will say why. A certificate error there is TLS interception on this" -ForegroundColor DarkGray
    Write-Host "  network, not a problem with the registry, and it blocks every az" -ForegroundColor DarkGray
    Write-Host "  command rather than only this one." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Falling back to what CI has built. This is not a deployment record:" -ForegroundColor Yellow
    Write-Host "  an image can be built and never promoted." -ForegroundColor Yellow
    Write-Host ""

    foreach ($artefact in $Artefacts) {
        $pattern = if ($artefact -eq "api") { "^Build the API image$" } else { "^Build the $artefact image$" }
        $entries = @(Invoke-Native gh @(
                "run", "list", "--workflow", "release.yml", "--limit", "15",
                "--json", "databaseId,headSha", "-q", '.[] | "\(.databaseId) \(.headSha)"'
            ))

        $found = $null
        foreach ($entry in $entries) {
            $parts = $entry -split ' '
            $jobs = @(Invoke-Native gh @(
                    "run", "view", $parts[0], "--json", "jobs",
                    "-q", '.jobs[] | select(.conclusion == "success") | .name'
                ))
            foreach ($job in $jobs) {
                if ($job -match $pattern) { $found = $parts[1]; break }
            }
            if ($found) { break }
        }

        if ($found) {
            Write-Host ("  {0,-8} last built  {1}" -f $artefact, (Get-CommitLabel $found))
        }
        else {
            Write-Host ("  {0,-8} no successful build in the last 15 runs" -f $artefact) -ForegroundColor DarkGray
        }
    }

    Write-Host ""
    exit 2
}

# --------------------------------------------------------------------- the table
$rows = @()
$seen = @{}

foreach ($artefact in $Artefacts) {
    $repository = "f2c/$artefact"
    $manifests = if ($artefact -eq $Artefacts[0]) { $probe } else { Get-Manifests $repository }

    $row = [ordered]@{ Artefact = $artefact }

    if ($null -eq $manifests) {
        # A repository that does not exist yet -- the market storefront in an
        # environment that does not carry it, most likely. Not an error.
        foreach ($environment in $environments) {
            $row[$environment] = "--"
            if ($Digests) { $row["$environment digest"] = "--" }
        }
        $rows += [pscustomobject]$row
        continue
    }

    foreach ($environment in $environments) {
        $manifest = $manifests | Where-Object { $_.tags -contains $environment } | Select-Object -First 1

        if (-not $manifest) {
            $row[$environment] = "--"
            if ($Digests) { $row["$environment digest"] = "--" }
            continue
        }

        # The commit is whichever of this manifest's tags is a full SHA. There
        # is one image per artefact per commit, so there is exactly one.
        $shaTag = $manifest.tags | Where-Object { $_ -match '^[0-9a-f]{40}$' } | Select-Object -First 1

        if ($shaTag) {
            $row[$environment] = $shaTag.Substring(0, 7)
            $seen[$shaTag] = $true
        }
        else {
            # A digest with an environment tag and no commit tag. Possible if
            # the `:<sha>` tag was deleted from the registry.
            $row[$environment] = "?"
        }

        if ($Digests) { $row["$environment digest"] = $manifest.digest }
    }

    $rows += [pscustomobject]$row
}

Write-Host ""
$rows | Format-Table -AutoSize

if ($seen.Count -gt 0) {
    Write-Host "Commits" -ForegroundColor Cyan
    Write-Host ""
    foreach ($sha in $seen.Keys) {
        Write-Host "  $(Get-CommitLabel $sha)"
    }
    Write-Host ""
}

Write-Host "A digest is what each revision is pinned to; these tags are the label." -ForegroundColor DarkGray
Write-Host "Production takes what UAT is running -- promote.yml enforces it." -ForegroundColor DarkGray
Write-Host ""
