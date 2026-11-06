$ErrorActionPreference = 'Stop'
$SourceExe = Join-Path $PSScriptRoot 'ComputeTorrent_Seeder.exe'
if (-not (Test-Path -LiteralPath $SourceExe)) { throw 'ComputeTorrent_Seeder.exe must be beside this installer.' }
$InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\ComputeTorrent'
$StartMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
New-Item -ItemType Directory -Force -Path $InstallDir, (Join-Path $env:LOCALAPPDATA 'ComputeTorrent\models') | Out-Null
Copy-Item -LiteralPath $SourceExe -Destination (Join-Path $InstallDir 'ComputeTorrent_Seeder.exe') -Force
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut((Join-Path $StartMenu 'ComputeTorrent Seeder.lnk'))
$Shortcut.TargetPath = Join-Path $InstallDir 'ComputeTorrent_Seeder.exe'
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Save()
Write-Output "Installed to $InstallDir. Docker Desktop must be running. Model files are fetched on demand from the configured network."
