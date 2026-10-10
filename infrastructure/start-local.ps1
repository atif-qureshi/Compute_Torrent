param([ValidateSet('current', 'standalone')][string]$Stack = 'current')
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = if ($Stack -eq 'standalone') { Join-Path $Root 'docker\docker-compose.yml' } else { Join-Path $Root 'docker-compose.local.yml' }
if (-not (Test-Path -LiteralPath $ComposeFile)) { throw "Compose file is missing: $ComposeFile" }
docker compose --project-directory $Root -f $ComposeFile up --build -d
if ($LASTEXITCODE -ne 0) { throw "Local Compose stack failed to start (exit $LASTEXITCODE)." }
Write-Output 'Local ComputeTorrent stack is running. Open http://localhost:3000.'
