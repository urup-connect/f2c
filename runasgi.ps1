# Run the project through Uvicorn (ASGI) with autoreload.
# Django 6.1's built-in 'manage.py runserver' is WSGI-only, so use this for
# any work that depends on async views, async ORM calls, or streaming.
#
#   .\runasgi.ps1              # 127.0.0.1:8000
#   .\runasgi.ps1 -Port 8080   # different port
#   .\runasgi.ps1 -HostName 0.0.0.0   # reachable from the LAN

param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

& ".venv\Scripts\python.exe" -m uvicorn f2c.asgi:application `
    --host $HostName `
    --port $Port `
    --reload `
    --reload-dir f2c `
    --reload-dir app
