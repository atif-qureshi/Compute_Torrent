import type { NextApiRequest, NextApiResponse } from 'next'
import fs from 'fs'
import path from 'path'
import { hasValidSession } from '../../lib/session'

export default async function providerAddress(req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Cache-Control', 'no-store')
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET')
    return res.status(405).json({ detail: 'Method not allowed' })
  }
  if (!hasValidSession(req)) return res.status(401).json({ detail: 'Sign in required' })

  const configuredHost = (process.env.COMPUTETORRENT_PROVIDER_LAN_HOST || '192.168.100.7').trim()
  const lanAddress = `ws://${configuredHost}:8001/ws/seeder`
  let publicAddress: string | null = null

  // 1. Try reading from runtime/public_tunnel.json
  try {
    const tunnelPath = path.join(process.cwd(), 'runtime', 'public_tunnel.json')
    if (fs.existsSync(tunnelPath)) {
      const data = JSON.parse(fs.readFileSync(tunnelPath, 'utf8'))
      if (data.ws_url) {
        publicAddress = data.ws_url
      }
    }
  } catch {
    // Ignore
  }

  // 2. Try querying local ngrok inspector if tunnel file wasn't found
  if (!publicAddress) {
    try {
      const response = await fetch('http://host.docker.internal:4040/api/tunnels', { signal: AbortSignal.timeout(1000) })
      if (response.ok) {
        const data = await response.json()
        const httpsTunnel = data.tunnels?.find((t: any) => t.public_url?.startsWith('https:'))
        if (httpsTunnel?.public_url) {
          publicAddress = `${httpsTunnel.public_url.replace(/^https:/, 'wss:')}/ws/seeder`
        }
      }
    } catch {
      // Ngrok not running on host
    }
  }

  return res.status(200).json({
    address: publicAddress || lanAddress,
    lan_address: lanAddress,
    public_address: publicAddress,
    has_public_tunnel: Boolean(publicAddress),
  })
}
