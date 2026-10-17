$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& docker compose -f docker-compose.local.yml --profile petals down
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the local ComputeTorrent stack.' }
Write-Output 'ComputeTorrent containers stopped. Database volumes were retained.'
