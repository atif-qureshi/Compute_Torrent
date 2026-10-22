# ComputeTorrent Seeder - Build Installer Script
param(
    [switch]$SkipDependencies,
    [switch]$Clean
)

Write-Output "🔨 Building ComputeTorrent Seeder Installer"
Write-Output "==========================================="
Write-Output ""

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$SyncPath = (Resolve-Path "..\04-webtorrent-sync").Path
$PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw "Python 3 must be installed on this build machine."
}
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    throw "Node.js must be installed on this build machine to bundle WebTorrent."
}
$nodeVersion = & node.exe --version
$nodeMajor = [int]([regex]::Match($nodeVersion, '^v?(\d+)').Groups[1].Value)
if ($nodeMajor -lt 22) {
    throw "Node.js 22 or newer is required by the bundled libp2p runtime. Found $nodeVersion."
}

if ($SkipDependencies) {
    Write-Output "Checking installed Python and Node.js dependencies..."
    $DependencyCheck = @'
import importlib.metadata as metadata
from pathlib import Path
from packaging.requirements import Requirement
for line in Path('requirements.txt').read_text(encoding='utf-8').splitlines():
    if not line.strip() or line.lstrip().startswith('#'):
        continue
    requirement = Requirement(line)
    installed = metadata.version(requirement.name)
    if installed not in requirement.specifier:
        raise RuntimeError(f'{requirement.name} {installed} does not satisfy {requirement.specifier}')
metadata.version('pyinstaller')
import customtkinter, PIL, pystray, psutil, websockets, PyInstaller
'@
    $DependencyCheck | & $PythonCommand.Source -
    if ($LASTEXITCODE -ne 0) { throw 'Installed Python dependencies are missing or incompatible. Run without -SkipDependencies.' }
    Push-Location $SyncPath
    try {
        npm ls --omit=dev --depth=0
        if ($LASTEXITCODE -ne 0) { throw 'Installed Node.js dependencies are missing or incompatible. Run without -SkipDependencies.' }
    } finally { Pop-Location }
} else {
    Write-Output "📦 Installing dependencies..."
    & $PythonCommand.Source -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) { throw "Could not install desktop application dependencies." }
    & $PythonCommand.Source -m pip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }
    Push-Location $SyncPath
    try {
        npm ci --omit=dev
        if ($LASTEXITCODE -ne 0) { throw "Could not install the locked WebTorrent helper dependencies." }
    } finally { Pop-Location }
}

# Build executable
Write-Output ""
Write-Output "🏗️ Building executable..."
$PyInstallerOptions = @('--noconfirm')
if ($Clean) { $PyInstallerOptions += '--clean' }
& $PythonCommand.Source -m PyInstaller seeder.spec @PyInstallerOptions
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to package the desktop application." }

Write-Output ""
if (Test-Path "dist\ComputeTorrent_Seeder.exe") {
    $DistPath = Join-Path $PSScriptRoot "dist"
    Copy-Item -Force (Join-Path $PSScriptRoot "Install-ComputeTorrent.ps1") (Join-Path $DistPath "Install-ComputeTorrent.ps1")
    Copy-Item -Force (Join-Path $PSScriptRoot "Uninstall-ComputeTorrent.ps1") (Join-Path $DistPath "Uninstall-ComputeTorrent.ps1")
    @'
ComputeTorrent Seeder

1. Install Docker Desktop and ensure it is running.
2. Right-click Install-ComputeTorrent.ps1 and choose Run with PowerShell.
3. Launch ComputeTorrent Seeder from the Start Menu.

Docker Desktop is a required provider prerequisite. Model weights are fetched
on demand from the configured WebTorrent network. Uninstall-ComputeTorrent.ps1
removes the application and shortcut while retaining the model cache.
'@ | Set-Content -Encoding UTF8 (Join-Path $DistPath "README.txt")
    $ReleaseJson = & $PythonCommand.Source -c 'import json, sys; from petals_control import provider_identity, runtime_digest; print(json.dumps(dict(provider_identity(), petals_protocol_version=1, cpu_runtime_digest=runtime_digest(), cuda_runtime_digest=runtime_digest(sys.argv[1]))))' cuda
    if ($LASTEXITCODE -ne 0) { throw "Could not generate provider release metadata." }
    $Release = $ReleaseJson | ConvertFrom-Json
    $Release | Add-Member -NotePropertyName built_at_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o'))
    $Release | Add-Member -NotePropertyName executable_sha256 -NotePropertyValue ((Get-FileHash -LiteralPath (Join-Path $DistPath 'ComputeTorrent_Seeder.exe') -Algorithm SHA256).Hash.ToLowerInvariant())
    $Release | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $DistPath 'provider-release.json')
    $Archive = Join-Path $DistPath "ComputeTorrent-Seeder-Installer.zip"
    if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
    Compress-Archive -Path (Join-Path $DistPath "ComputeTorrent_Seeder.exe"),
        (Join-Path $DistPath "Install-ComputeTorrent.ps1"),
        (Join-Path $DistPath "Uninstall-ComputeTorrent.ps1"),
        (Join-Path $DistPath "README.txt"),
        (Join-Path $DistPath "provider-release.json") -DestinationPath $Archive -CompressionLevel Optimal
    Copy-Item -LiteralPath $Archive -Destination (Join-Path $DistPath 'ComputeTorrent_Seeder.zip') -Force
    $LegacyShell = Join-Path $PSScriptRoot '..\..\desktop\05-desktop-app-shell'
    if (Test-Path -LiteralPath $LegacyShell) {
        $LegacyDist = Join-Path $LegacyShell 'dist'
        New-Item -ItemType Directory -Force -Path $LegacyDist | Out-Null
        foreach ($ArtifactName in @('ComputeTorrent_Seeder.exe', 'ComputeTorrent-Seeder-Installer.zip',
                'ComputeTorrent_Seeder.zip', 'Install-ComputeTorrent.ps1', 'Uninstall-ComputeTorrent.ps1',
                'README.txt', 'provider-release.json')) {
            Copy-Item -LiteralPath (Join-Path $DistPath $ArtifactName) -Destination (Join-Path $LegacyDist $ArtifactName) -Force
        }
    }
    Write-Output "✅ Build successful!"
    Write-Output ""
    Write-Output "Executable location:"
    Write-Output "   dist\ComputeTorrent_Seeder.exe"
    Write-Output "   dist\ComputeTorrent-Seeder-Installer.zip"
    Write-Output ""
    Write-Output "Size:"
    $size = (Get-Item "dist\ComputeTorrent_Seeder.exe").Length / 1MB
    Write-Output "   $([math]::Round($size, 2)) MB"
    Write-Output ""
    Write-Output "🎉 Ready to distribute!"
} else {
    Write-Output "❌ Build failed. Check errors above."
}
