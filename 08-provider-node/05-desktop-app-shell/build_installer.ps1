# ComputeTorrent Seeder - Build Installer Script
Write-Output "🔨 Building ComputeTorrent Seeder Installer"
Write-Output "==========================================="
Write-Output ""

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$SyncPath = (Resolve-Path "..\04-webtorrent-sync").Path
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
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
Push-Location $SyncPath
npm install --omit=dev
Pop-Location

# Build executable
Write-Output ""
Write-Output "🏗️ Building executable..."
pyinstaller seeder.spec --clean --noconfirm

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
