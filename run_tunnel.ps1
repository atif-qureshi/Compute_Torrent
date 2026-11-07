$Host.UI.RawUI.WindowTitle = "ComputeTorrent - Global Coordinator Tunnel"
Clear-Host

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    ComputeTorrent Global Coordinator Tunnel (Cloudflare) " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[1/2] Checking Coordinator on port 8001..." -ForegroundColor Gray

$p = Test-NetConnection -ComputerName '127.0.0.1' -Port 8001 -WarningAction SilentlyContinue
if (-not $p.TcpTestSucceeded) {
    Write-Host "[WARNING] Coordinator on 127.0.0.1:8001 is not responding yet!" -ForegroundColor Red
    Write-Host "Make sure docker or uvicorn is running: docker compose -f docker\docker-compose.yml up -d" -ForegroundColor Yellow
    Write-Host ""
} else {
    Write-Host "[OK] Coordinator is running and healthy on port 8001." -ForegroundColor Green
}

Write-Host "[2/2] Requesting secure global tunnel from Cloudflare..." -ForegroundColor Gray
$logFile = Join-Path $PSScriptRoot "runtime\current_tunnel.log"
if (Test-Path $logFile) { Remove-Item $logFile -Force }

$cfExe = Join-Path $PSScriptRoot "cloudflared.exe"
$cfProcess = Start-Process -FilePath $cfExe -ArgumentList "tunnel", "--url", "http://127.0.0.1:8001" -NoNewWindow -PassThru -RedirectStandardError $logFile

$url = $null
for ($i = 0; $i -lt 35; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $lines = Get-Content $logFile -ErrorAction SilentlyContinue
        $match = $lines | Select-String "https://[a-zA-Z0-9-]+\.trycloudflare\.com"
        if ($match) {
            $url = $match.Matches[0].Value
            break
        }
        if ($lines | Select-String "context deadline exceeded") {
            Write-Host "[ERROR] Cloudflare rate limit cooldown in progress. Retrying..." -ForegroundColor Yellow
        }
    }
}

if ($url) {
    try { Set-Clipboard -Value $url } catch {}
    $url | Set-Content (Join-Path $PSScriptRoot "runtime\current_tunnel_url.txt")
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "  YOUR LIVE GLOBAL URL (COPIED TO CLIPBOARD!):" -ForegroundColor Green
    Write-Host "  $url" -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Steps on the other PC / laptop:" -ForegroundColor White
    Write-Host "  1. Open ComputeTorrent_Seeder.exe" -ForegroundColor White
    Write-Host "  2. In 'Coordinator Address', paste: $url" -ForegroundColor White
    Write-Host "  3. In 'Provider join code', type:   local-volunteer-join" -ForegroundColor White
    Write-Host "  4. Click 'Connect'!" -ForegroundColor Green
    Write-Host ""
    Write-Host "(Keep this window OPEN while testing. Press Ctrl+C to stop.)" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] Could not extract tunnel URL. Log output:" -ForegroundColor Red
    if (Test-Path $logFile) { Get-Content $logFile -Tail 10 }
}

Wait-Process -Id $cfProcess.Id
