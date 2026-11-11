param(
    [string]$RootDir = $PSScriptRoot,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RootDir)) {
    $RootDir = (Get-Location).Path
}

$virtualPattern = 'vEthernet|Hyper-V|WSL|Docker|VMware|VirtualBox|Loopback|Teredo|Bluetooth|TAP-Windows|OpenVPN|WireGuard|Tailscale|ZeroTier|Npcap|6to4|isatap'

function Test-PrivateIpv4 {
    param([string]$Ip)
    if ($Ip -match '^192\.168\.' -or $Ip -match '^10\.') { return $true }
    if ($Ip -match '^172\.(\d+)\.') {
        $second = [int]$Matches[1]
        return ($second -ge 16 -and $second -le 31)
    }
    return $false
}

function Get-ActiveLanCandidate {
    $candidates = @()
    try {
        $configs = Get-NetIPConfiguration -ErrorAction Stop | Where-Object {
            $_.IPv4Address -and $_.IPv4DefaultGateway -and $_.NetAdapter -and $_.NetAdapter.Status -eq 'Up'
        }
        foreach ($cfg in $configs) {
            $alias = [string]$cfg.InterfaceAlias
            $desc = [string]$cfg.NetAdapter.InterfaceDescription
            if ($alias -match $virtualPattern -or $desc -match $virtualPattern) { continue }

            foreach ($addr in $cfg.IPv4Address) {
                $ip = [string]$addr.IPAddress
                if ([string]::IsNullOrWhiteSpace($ip) -or $ip.StartsWith('127.') -or $ip.StartsWith('169.254.')) { continue }
                $isWifi = ($alias -match 'Wi-?Fi|WLAN|Wireless' -or $desc -match 'Wi-?Fi|Wireless|802\.11')
                $score = 0
                if ($isWifi) { $score += 100 }
                if (Test-PrivateIpv4 $ip) { $score += 20 }
                if ($cfg.IPv4DefaultGateway.NextHop) { $score += 10 }
                $candidates += [pscustomobject]@{
                    Ip        = $ip
                    Interface = $alias
                    Score     = $score
                }
            }
        }
    } catch {
        # Fallback below if NetTCPIP cmdlets are unavailable
    }

    if ($candidates.Count -eq 0) {
        try {
            $routes = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction Stop |
                Sort-Object { $_.RouteMetric + $_.InterfaceMetric }
            foreach ($route in $routes) {
                $adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue
                if (-not $adapter -or $adapter.Status -ne 'Up') { continue }
                $alias = [string]$adapter.Name
                $desc = [string]$adapter.InterfaceDescription
                if ($alias -match $virtualPattern -or $desc -match $virtualPattern) { continue }

                $addrs = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue |
                    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }
                foreach ($a in $addrs) {
                    $isWifi = ($alias -match 'Wi-?Fi|WLAN|Wireless' -or $desc -match 'Wi-?Fi|Wireless|802\.11')
                    $candidates += [pscustomobject]@{
                        Ip        = [string]$a.IPAddress
                        Interface = $alias
                        Score     = $(if ($isWifi) { 100 } else { 50 })
                    }
                }
            }
        } catch {
            # Fallback to .NET NetworkInterface below
        }
    }

    if ($candidates.Count -eq 0) {
        foreach ($nic in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
            if ($nic.OperationalStatus -ne 'Up') { continue }
            if ($nic.NetworkInterfaceType -eq 'Loopback' -or $nic.NetworkInterfaceType -eq 'Tunnel') { continue }
            $alias = [string]$nic.Name
            $desc = [string]$nic.Description
            if ($alias -match $virtualPattern -or $desc -match $virtualPattern) { continue }
            $props = $nic.GetIPProperties()
            $hasGw = ($props.GatewayAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' }).Count -gt 0
            if (-not $hasGw) { continue }
            foreach ($ua in $props.UnicastAddresses) {
                if ($ua.Address.AddressFamily -ne 'InterNetwork') { continue }
                $ip = $ua.Address.ToString()
                if ($ip.StartsWith('127.') -or $ip.StartsWith('169.254.')) { continue }
                $isWifi = ($nic.NetworkInterfaceType -eq 'Wireless80211' -or $alias -match 'Wi-?Fi|WLAN|Wireless' -or $desc -match 'Wi-?Fi|Wireless|802\.11')
                $candidates += [pscustomobject]@{
                    Ip        = $ip
                    Interface = $alias
                    Score     = $(if ($isWifi) { 100 } else { 50 })
                }
            }
        }
    }

    return $candidates | Sort-Object -Property Score -Descending | Select-Object -First 1
}

function Set-EnvKey {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [string]$Key,
        [string]$Value
    )
    $prefix = "$Key="
    $updated = $false
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i].StartsWith($prefix)) {
            if ($Lines[$i] -ne "$prefix$Value") {
                $Lines[$i] = "$prefix$Value"
            }
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $Lines.Add("$prefix$Value")
    }
}

$selected = Get-ActiveLanCandidate
if (-not $selected) {
    if (-not $Quiet) {
        Write-Warning "Could not auto-detect an active physical Wi-Fi/LAN IPv4 address."
    }
    exit 0
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$runtimeSwarmDir = Join-Path $RootDir 'runtime\swarm'
if (-not (Test-Path $runtimeSwarmDir)) {
    New-Item -ItemType Directory -Path $runtimeSwarmDir -Force | Out-Null
}

$networkPayload = @{
    lan_ip     = $selected.Ip
    interface  = $selected.Interface
    source     = 'host-sync'
    updated_at = [int64][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
} | ConvertTo-Json -Depth 3

$networkJsonPath = Join-Path $runtimeSwarmDir 'host-network.json'
[System.IO.File]::WriteAllText($networkJsonPath, $networkPayload + "`n", $utf8NoBom)

$envPath = Join-Path $RootDir '.env'
$envExamplePath = Join-Path $RootDir '.env.example'
if (-not (Test-Path $envPath) -and (Test-Path $envExamplePath)) {
    Copy-Item $envExamplePath $envPath
}

if (Test-Path $envPath) {
    $rawLines = [System.IO.File]::ReadAllLines($envPath)
    $lineList = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $rawLines) { $lineList.Add($line) }
    Set-EnvKey -Lines $lineList -Key 'COMPUTETORRENT_LIBP2P_ADVERTISE_HOST' -Value $selected.Ip
    Set-EnvKey -Lines $lineList -Key 'COMPUTETORRENT_PROVIDER_LAN_HOST' -Value $selected.Ip
    [System.IO.File]::WriteAllText($envPath, ($lineList -join "`r`n") + "`r`n", $utf8NoBom)
}

if (-not $Quiet) {
    Write-Host ("Auto-detected host LAN IP: {0} ({1})" -f $selected.Ip, $selected.Interface) -ForegroundColor Cyan
}
