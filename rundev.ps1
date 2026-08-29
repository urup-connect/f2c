# Run the stack for local development:
#   Django (ASGI, Uvicorn) on :8000, the club on :3000 and the store on :3001.
#
#   .\rundev.ps1                        # Django + the club, in separate windows
#   .\rundev.ps1 -Storefront market     # Django + the store
#   .\rundev.ps1 -Storefront both       # Django + both storefronts
#   .\rundev.ps1 -ApiOnly               # Django only
#   .\rundev.ps1 -WebOnly               # the storefront(s) only
#
# Use localhost (not 127.0.0.1) in the browser. The session cookie is
# SameSite=Lax, so the frontend and API must share a hostname for it to be
# sent on API calls -- and an IP address is not a valid WebAuthn Relying Party
# ID, so passkeys do not work there either.
#
# The default is the club rather than both, so the ordinary case still opens two
# windows instead of three.
#
# One thing to know when working on the store's /legal page: the storefront a
# request belongs to is resolved from the host Django sees, and both
# applications call it on localhost:8000. That host is unmapped, so it falls
# back to DJANGO_DEFAULT_STOREFRONT -- the club. Set that to `market` in .env
# while working on the store, or expect the club's documents to appear on it.

param(
    [switch]$ApiOnly,
    [switch]$WebOnly,
    [ValidateSet("club", "market", "both")]
    [string]$Storefront = "club"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Start-Storefront {
    param(
        [string]$Name,
        [string]$Directory,
        [int]$Port
    )

    Write-Host "Starting the $Name on http://localhost:$Port/ ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root\frontend\$Directory'; npm run dev"
    )
}

if (-not $WebOnly) {
    Write-Host "Starting Django API on http://localhost:8000/ ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root'; & '.venv\Scripts\python.exe' -m uvicorn f2c.asgi:application --host localhost --port 8000 --reload --reload-dir f2c --reload-dir app"
    )
}

if (-not $ApiOnly) {
    if ($Storefront -eq "club" -or $Storefront -eq "both") {
        Start-Storefront -Name "club" -Directory "club" -Port 3000
    }

    if ($Storefront -eq "market" -or $Storefront -eq "both") {
        # The port is set in frontend/market/package.json, not passed here, so
        # `npm run dev` in that directory behaves the same way on its own.
        Start-Storefront -Name "store" -Directory "market" -Port 3001
    }
}

Write-Host ""
if (-not $ApiOnly) {
    if ($Storefront -eq "club" -or $Storefront -eq "both") {
        Write-Host "  Club      http://localhost:3000/"
    }
    if ($Storefront -eq "market" -or $Storefront -eq "both") {
        Write-Host "  Store     http://localhost:3001/"
    }
}
Write-Host "  API docs  http://localhost:8000/api/docs"
Write-Host "  Admin     http://localhost:8000/admin/"
