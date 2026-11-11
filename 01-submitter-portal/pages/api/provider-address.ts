import type { NextApiRequest, NextApiResponse } from 'next'
import { hasValidSession } from '../../lib/session'

export default async function providerAddress(req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Cache-Control', 'no-store')
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET')
    return res.status(405).json({ detail: 'Method not allowed' })
  }
  if (!hasValidSession(req)) return res.status(401).json({ detail: 'Sign in required' })

  const configuredHost = (process.env.COMPUTETORRENT_PROVIDER_LAN_HOST || '192.168.100.7').trim()
  let lanAddress = `ws://${configuredHost}:8001/ws/seeder`
  let publicAddress: string | null = null
  let enrollmentToken: string | null = null

  // Publish a candidate only while the inspector confirms the coordinator upstream.
  try {
    const response = await fetch('http://host.docker.internal:4040/api/tunnels', { signal: AbortSignal.timeout(1000) })
    if (response.ok) {
      const data = await response.json()
      const tunnel = data.tunnels?.find((t: any) =>
        t.public_url?.startsWith('https://') &&
        /^(?:http:\/\/)?(?:127\.0\.0\.1|localhost):8001\/?$/.test(t.config?.addr || '')
      )
      if (tunnel) {
        const candidate = new URL(tunnel.public_url)
        if (!candidate.username && !candidate.password && !candidate.search && !candidate.hash) {
          publicAddress = `wss://${candidate.host}/ws/seeder`
        }
      }
    }
  } catch {
    // Inspector unavailable. Leave the public candidate unset.
  }

  // Fetch live enrollment token from orchestrator
  const orchestratorApi = process.env.COMPUTETORRENT_ORCHESTRATOR_API_URL || 'http://orchestrator:8001/api'
  const apiToken = process.env.COMPUTETORRENT_API_TOKEN || ''
  try {
    const resOrch = await fetch(`${orchestratorApi}/coordinator/enrollment-code`, {
      headers: { Authorization: `Bearer ${apiToken}` },
      signal: AbortSignal.timeout(1500),
    })
    if (resOrch.ok) {
      const orchData = await resOrch.json()
      if (orchData.enrollment_token) {
        enrollmentToken = orchData.enrollment_token
      }
    }
  } catch {
    // Ignore
  }

  let resolvedLanHost = configuredHost
  let resolvedLanInterface: string | null = null
  let resolvedLanSource = 'env'
  let resolvedUpdatedAt = -1
  const isLanIpv4 = (host: unknown): host is string =>
    typeof host === 'string' &&
    /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host.trim()) &&
    !host.trim().startsWith('127.') &&
    !host.trim().startsWith('169.254.') &&
    host.trim() !== '0.0.0.0'

  try {
    const fs = await import('fs')
    const path = await import('path')
    const candidates = [
      path.join(process.cwd(), 'runtime', 'swarm', 'host-network.json'),
      path.resolve(process.cwd(), '..', 'runtime', 'swarm', 'host-network.json'),
    ]
    for (const file of candidates) {
      if (!fs.existsSync(file)) continue
      const raw = JSON.parse(fs.readFileSync(file, 'utf-8').replace(/^\uFEFF/, ''))
      if (isLanIpv4(raw?.lan_ip)) {
        const ts = Number(raw?.updated_at || 0)
        if (ts >= resolvedUpdatedAt) {
          resolvedLanHost = raw.lan_ip.trim()
          resolvedLanInterface = typeof raw?.interface === 'string' ? raw.interface : null
          resolvedLanSource = typeof raw?.source === 'string' ? raw.source : 'host-sync'
          resolvedUpdatedAt = ts
        }
      }
      break
    }
  } catch {
    // Ignore optional runtime network cache read errors
  }

  try {
    const apiBase = process.env.COMPUTETORRENT_ORCHESTRATOR_API_URL || 'http://orchestrator:8001/api'
    const token = process.env.COMPUTETORRENT_API_TOKEN
    if (token) {
      const upstream = await fetch(`${apiBase.replace(/\/$/, '')}/network`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (upstream.ok) {
        const net = await upstream.json()
        const ts = Number(net?.lan_updated_at || 0)
        if (isLanIpv4(net?.lan_host) && ts >= resolvedUpdatedAt) {
          resolvedLanHost = net.lan_host.trim()
          resolvedLanInterface = typeof net?.lan_interface === 'string' ? net.lan_interface : resolvedLanInterface
          resolvedLanSource = typeof net?.lan_ip_source === 'string' ? net.lan_ip_source : 'coordinator'
          resolvedUpdatedAt = ts
        }
      }
    }
  } catch {
    // Fallback to host-sync or request host
  }

  if (resolvedUpdatedAt <= 0 && req.headers.host) {
    const reqHost = req.headers.host.split(':')[0]?.trim() || ''
    if (isLanIpv4(reqHost)) {
      resolvedLanHost = reqHost
      resolvedLanSource = 'request-host'
    }
  }

  lanAddress = `ws://${resolvedLanHost}:8001/ws/seeder`
  res.setHeader('Cache-Control', 'no-store')
  return res.status(200).json({
    lan_ip: resolvedLanHost,
    lan_interface: resolvedLanInterface,
    lan_ip_source: resolvedLanSource,
    address: publicAddress || lanAddress,
    lan_address: lanAddress,
    public_address: publicAddress,
    has_public_tunnel: Boolean(publicAddress),
    enrollment_token: enrollmentToken,
  })
}
