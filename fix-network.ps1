# ComputeTorrent - Network Fix Script
# Run this as Administrator to:
# 1. Set Wi-Fi to Private network
# 2. Open firewall port 8001 for ComputeTorrent

Write-Host "=== ComputeTorrent Network Fix ===" -ForegroundColor Cyan

# Step 1: Set Wi-Fi network to Private
Write-Host "`n[1] Setting Wi-Fi network to Private..." -ForegroundColor Yellow
try {
    Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
    Write-Host "    OK - Wi-Fi set to Private network" -ForegroundColor Green
} catch {
    Write-Host "    WARNING: $($_.Exception.Message)" -ForegroundColor Red
}

# Step 2: Remove old firewall rules if they exist
Write-Host "`n[2] Cleaning up old firewall rules..." -ForegroundColor Yellow
try {
    netsh advfirewall firewall delete rule name="ComputeTorrent Orchestrator" | Out-Null
    Write-Host "    OK - Old rules removed" -ForegroundColor Green
} catch {}

# Step 3: Add inbound firewall rule for port 8001
Write-Host "`n[3] Adding firewall rule for port 8001..." -ForegroundColor Yellow
$result = netsh advfirewall firewall add rule name="ComputeTorrent Orchestrator" dir=in action=allow protocol=TCP localport=8001
if ($LASTEXITCODE -eq 0) {
    Write-Host "    OK - Port 8001 allowed for inbound connections" -ForegroundColor Green
} else {
    Write-Host "    FAILED - $result" -ForegroundColor Red
}

# Step 4: Add inbound firewall rule for port 9100 (libp2p swarm)
Write-Host "`n[4] Adding firewall rule for port 9100 (libp2p swarm)..." -ForegroundColor Yellow
netsh advfirewall firewall delete rule name="ComputeTorrent Swarm" | Out-Null
$result2 = netsh advfirewall firewall add rule name="ComputeTorrent Swarm" dir=in action=allow protocol=TCP localport=9100
if ($LASTEXITCODE -eq 0) {
    Write-Host "    OK - Port 9100 allowed for inbound connections" -ForegroundColor Green
} else {
    Write-Host "    FAILED - $result2" -ForegroundColor Red
}

# Step 5: Add inbound rule for port 31331 (libp2p petals)
Write-Host "`n[5] Adding firewall rule for port 31331 (Petals P2P)..." -ForegroundColor Yellow
netsh advfirewall firewall delete rule name="ComputeTorrent Petals" | Out-Null
$result3 = netsh advfirewall firewall add rule name="ComputeTorrent Petals" dir=in action=allow protocol=TCP localport=31331
if ($LASTEXITCODE -eq 0) {
    Write-Host "    OK - Port 31331 allowed for inbound connections" -ForegroundColor Green
} else {
    Write-Host "    FAILED - $result3" -ForegroundColor Red
}

# Final status
Write-Host "`n=== Done! ===" -ForegroundColor Cyan
Write-Host "Your Wi-Fi IP on this router: " -NoNewline
(Get-NetIPAddress -InterfaceAlias "Wi-Fi" -AddressFamily IPv4).IPAddress | Write-Host -ForegroundColor Green
Write-Host ""
Write-Host "Other PCs should connect to:" -ForegroundColor Yellow
$ip = (Get-NetIPAddress -InterfaceAlias "Wi-Fi" -AddressFamily IPv4).IPAddress
Write-Host "  ws://$ip`:8001/ws/seeder" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
