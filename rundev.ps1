# Run both halves of the stack for local development:
#   Django (ASGI, Uvicorn) on :8000 and Next.js on :3000.
#
#   .\rundev.ps1                  # both, in separate windows
#   .\rundev.ps1 -ApiOnly         # Django only
#   .\rundev.ps1 -WebOnly         # Next.js only
#
# Use localhost (not 127.0.0.1) in the browser. The session cookie is
# SameSite=Lax, so the frontend and API must share a hostname for it to be
# sent on API calls.

param(
    [switch]$ApiOnly,
    [switch]$WebOnly
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not $WebOnly) {
    Write-Host "Starting Django API on http://localhost:8000/ ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root'; & '.venv\Scripts\python.exe' -m uvicorn cultivatorscollective.asgi:application --host localhost --port 8000 --reload --reload-dir cultivatorscollective --reload-dir app/accounts --reload-dir app/authn --reload-dir app/common --reload-dir app/documents"
    )
}

if (-not $ApiOnly) {
    Write-Host "Starting Next.js frontend on http://localhost:3000/ ..." -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command",
        "Set-Location '$root\frontend'; npm run dev"
    )
}

Write-Host ""
Write-Host "  Frontend  http://localhost:3000/"
Write-Host "  API docs  http://localhost:8000/api/docs"
Write-Host "  Admin     http://localhost:8000/admin/"
