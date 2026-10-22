# Compatibility build entrypoint. Provider releases are built from one source.
param(
    [switch]$SkipDependencies,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$CanonicalShell = (Resolve-Path (Join-Path $PSScriptRoot '..\..\08-provider-node\05-desktop-app-shell')).Path
& (Join-Path $CanonicalShell 'build_installer.ps1') @PSBoundParameters
if ($LASTEXITCODE -ne 0) { throw 'The canonical provider build failed.' }

$LegacyDist = Join-Path $PSScriptRoot 'dist'
New-Item -ItemType Directory -Force -Path $LegacyDist | Out-Null
foreach ($ArtifactName in @('ComputeTorrent_Seeder.exe', 'ComputeTorrent-Seeder-Installer.zip',
        'Install-ComputeTorrent.ps1', 'Uninstall-ComputeTorrent.ps1', 'README.txt', 'provider-release.json')) {
    Copy-Item -LiteralPath (Join-Path $CanonicalShell "dist\$ArtifactName") -Destination (Join-Path $LegacyDist $ArtifactName) -Force
}
# Retain the older archive name as an alias of the current release.
Copy-Item -LiteralPath (Join-Path $LegacyDist 'ComputeTorrent-Seeder-Installer.zip') -Destination (Join-Path $LegacyDist 'ComputeTorrent_Seeder.zip') -Force
Write-Output "Provider package built from $CanonicalShell and copied to $LegacyDist."
