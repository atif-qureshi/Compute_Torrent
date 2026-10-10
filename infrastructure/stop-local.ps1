param([ValidateSet('current', 'standalone')][string]$Stack = 'current')
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = if ($Stack -eq 'standalone') { Join-Path $Root 'docker\docker-compose.yml' } else { Join-Path $Root 'docker-compose.local.yml' }
docker compose --project-directory $Root -f $ComposeFile down
if ($LASTEXITCODE -ne 0) { throw "Local Compose stack failed to stop (exit $LASTEXITCODE)." }
