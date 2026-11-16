$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run python -m venv .venv and install requirements first. See README.md.' }
$apiRoot = Join-Path $projectRoot 'apps/api'
$webRoot = Join-Path $projectRoot 'apps/web'
$envFile = Join-Path $projectRoot '.env'
if (!(Test-Path -LiteralPath $envFile)) { throw 'Run scripts/setup-env.ps1 first.' }
$pg = ((Get-Content -LiteralPath $envFile | Where-Object { $_ -like 'POSTGRES_PASSWORD=*' }) -split '=', 2)[1]
if (!$pg) { throw 'POSTGRES_PASSWORD is missing in .env' }
# The database is the Compose one. compose.dev.yaml publishes it on 127.0.0.1 only; start it with:
#   docker compose -f compose.yaml -f compose.dev.yaml up -d postgres
$env:DATABASE_URL = "postgresql+psycopg://hub:$pg@127.0.0.1:5432/hub"
& $python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Cannot migrate: is the PostgreSQL container running? (docker compose -f compose.yaml -f compose.dev.yaml up -d postgres)' }
$apiProcess = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8100') -WorkingDirectory $apiRoot -WindowStyle Hidden -PassThru
Write-Host 'Open http://localhost:3009. Press Ctrl+C to stop.'
try { Set-Location -LiteralPath $webRoot; & npm.cmd run dev } finally { Stop-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue }
