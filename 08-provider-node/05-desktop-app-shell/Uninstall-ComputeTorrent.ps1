$InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\ComputeTorrent'
$StartMenuLink = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ComputeTorrent Seeder.lnk'
Remove-Item -LiteralPath $StartMenuLink -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Output 'ComputeTorrent was removed. Model cache and workspace data remain under %LOCALAPPDATA%\ComputeTorrent.'
