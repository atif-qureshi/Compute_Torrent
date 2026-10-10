# ComputeTorrent Seeder - Build Installer Script
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

# Install dependencies
Write-Output "📦 Installing dependencies..."
& $PythonCommand.Source -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not install desktop application dependencies." }
& $PythonCommand.Source -m pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not install PyInstaller." }
Push-Location $SyncPath
npm ci --omit=dev
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Could not install the locked WebTorrent helper dependencies." }
Pop-Location

# Build executable
Write-Output ""
Write-Output "🏗️ Building executable..."
& $PythonCommand.Source -m PyInstaller seeder.spec --clean --noconfirm
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
    $Archive = Join-Path $DistPath "ComputeTorrent-Seeder-Installer.zip"
    if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
    Compress-Archive -Path (Join-Path $DistPath "ComputeTorrent_Seeder.exe"),
        (Join-Path $DistPath "Install-ComputeTorrent.ps1"),
        (Join-Path $DistPath "Uninstall-ComputeTorrent.ps1"),
        (Join-Path $DistPath "README.txt") -DestinationPath $Archive -CompressionLevel Optimal
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
