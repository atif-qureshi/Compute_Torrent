<#
.SYNOPSIS
  Start a public Ngrok tunnel for ComputeTorrent Coordinator (Port 8001).
  Enables volunteer peers anywhere in the world to connect to this coordinator.

.PARAMETER AuthToken
  Optional Ngrok authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
#>

param(
    [string]$AuthToken = ""
)

$ErrorActionPreference = "Stop"
$appData = "$env:LOCALAPPDATA\ComputeTorrent"
$binDir = "$appData\bin"
$tunnelFile = Join-Path $PSScriptRoot "runtime\public_tunnel.json"

# Check if ngrok is on system PATH first
$sysNgrok = Get-Command ngrok -ErrorAction SilentlyContinue
if ($sysNgrok) {
    $ngrok = $sysNgrok.Source
} else {
    $ngrok = "$binDir\ngrok.exe"
    if (-not (Test-Path $ngrok)) {
        Write-Host "Installing Ngrok binary into $binDir..." -ForegroundColor Cyan
        New-Item -ItemType Directory -Path $binDir -Force | Out-Null
        $zip = "$env:TEMP\ngrok.zip"
        Invoke-WebRequest -Uri "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $binDir -Force
        Remove-Item -Path $zip -Force -ErrorAction SilentlyContinue
    }
}

if ($AuthToken) {
    Write-Host "Configuring Ngrok AuthToken..." -ForegroundColor Cyan
    & $ngrok config add-authtoken $AuthToken
}

# Check if ngrok is already running with an active tunnel
$publicUrl = ""
try {
    $api = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 -ErrorAction Stop
    if ($api.tunnels -and $api.tunnels.Count -gt 0) {
        $httpsTunnel = $api.tunnels | Where-Object { $_.public_url -match "^https:" } | Select-Object -First 1
        if ($httpsTunnel) {
            $publicUrl = $httpsTunnel.public_url
            Write-Host "Existing active Ngrok tunnel found: $publicUrl" -ForegroundColor Cyan
        }
    }
} catch {
    # Not running yet
}

if (-not $publicUrl) {
    Write-Host "Launching Ngrok HTTP Tunnel for Port 8001..." -ForegroundColor Green
    $proc = Start-Process -FilePath $ngrok -ArgumentList "http 8001 --log=stdout" -PassThru -WindowStyle Hidden

    Write-Host "Waiting for tunnel allocation (up to 45s)..." -ForegroundColor Yellow
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        try {
            $api = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 -ErrorAction Stop
            if ($api.tunnels -and $api.tunnels.Count -gt 0) {
                $httpsTunnel = $api.tunnels | Where-Object { $_.public_url -match "^https:" } | Select-Object -First 1
                if ($httpsTunnel) {
                    $publicUrl = $httpsTunnel.public_url
                    break
                }
            }
        } catch {
            # Waiting for agent handshake
        }
    }
}

if ($publicUrl) {
    $wsUrl = $publicUrl -replace "^https:", "wss:"
    $wsUrl = "$wsUrl/ws/seeder"

    # Get active enrollment token from orchestrator or default
    $enrollmentToken = "local-volunteer-join"
    try {
        $envToken = docker exec computetorrent-orchestrator printenv COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN 2>$null
        if ($envToken) { $enrollmentToken = $envToken.Trim() }
    } catch {}
    
    New-Item -ItemType Directory -Path (Split-Path $tunnelFile) -Force | Out-Null
    @{
        public_url = $publicUrl
        ws_url = $wsUrl
        enrollment_token = $enrollmentToken
        created_at = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -Path $tunnelFile -Encoding utf8

    try {
        docker exec computetorrent-portal mkdir -p /app/runtime 2>$null | Out-Null
        docker cp $tunnelFile computetorrent-portal:/app/runtime/public_tunnel.json 2>$null | Out-Null
    } catch {
        # Optional sync
    }
    
    Write-Host ""
    Write-Host "=======================================================" -ForegroundColor Green
    Write-Host "GLOBAL PEER TUNNEL ACTIVE!" -ForegroundColor Green
    Write-Host "=======================================================" -ForegroundColor Green
    Write-Host "Remote Provider Connection URL (Send to your friend):" -ForegroundColor White
    Write-Host "   $wsUrl" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Provider Enrollment / Join Code:" -ForegroundColor White
    Write-Host "   $enrollmentToken" -ForegroundColor Yellow
    Write-Host "   (or: local-volunteer-join)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Steps for your friend on another network:" -ForegroundColor White
    Write-Host "1. Open ComputeTorrent Provider app" -ForegroundColor Gray
    Write-Host "2. Paste Coordinator URL: $wsUrl" -ForegroundColor Gray
    Write-Host "3. Paste Join Code:       $enrollmentToken" -ForegroundColor Gray
    Write-Host "4. Click 'Connect & Join Compute Network'" -ForegroundColor Gray
    Write-Host "=======================================================" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "Could not retrieve public tunnel URL." -ForegroundColor Red
    Write-Host "If this is your first time using Ngrok, you need to set your free authtoken:" -ForegroundColor Yellow
    Write-Host "1. Sign up for free at: https://dashboard.ngrok.com/signup" -ForegroundColor White
    Write-Host "2. Copy your token from: https://dashboard.ngrok.com/get-started/your-authtoken" -ForegroundColor White
    Write-Host "3. Run: .\start-ngrok.ps1 -AuthToken YOUR_TOKEN" -ForegroundColor Cyan
    Write-Host ""
}
