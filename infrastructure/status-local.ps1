param([ValidateSet('current', 'standalone')][string]$Stack = 'current')
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = if ($Stack -eq 'standalone') { Join-Path $Root 'docker\docker-compose.yml' } else { Join-Path $Root 'docker-compose.local.yml' }
docker compose --project-directory $Root -f $ComposeFile ps
if ($LASTEXITCODE -ne 0) { throw "Could not read local Compose status (exit $LASTEXITCODE)." }
