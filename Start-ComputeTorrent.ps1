param(
    [switch]$WithPetals,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Missing .env. Copy .env.example to .env and set private passwords and tokens first.'
}

& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop is not running or this account cannot access its engine.'
}

$composeArgs = @('compose', '-f', 'docker-compose.local.yml')
if ($WithPetals) { $composeArgs += @('--profile', 'petals') }
$composeArgs += 'up'
if (-not $NoBuild) { $composeArgs += '--build' }
$composeArgs += '-d'

& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw 'ComputeTorrent containers failed to start. Check Docker Desktop and the build logs.' }

& docker compose -f docker-compose.local.yml ps
Write-Output ''
Write-Output 'Portal: http://127.0.0.1:3000'
Write-Output 'Docker Desktop group: computetorrent-mvp'
if (-not $WithPetals) {
    Write-Output 'Model Studio gateway: start with .\Start-ComputeTorrent.ps1 -WithPetals when its image is ready.'
}
