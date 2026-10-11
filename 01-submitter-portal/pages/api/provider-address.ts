import type { NextApiRequest, NextApiResponse } from 'next'
import { hasValidSession } from '../../lib/session'

export default function providerAddress(req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Cache-Control', 'no-store')
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET')
    return res.status(405).json({ detail: 'Method not allowed' })
  }
  if (!hasValidSession(req)) return res.status(401).json({ detail: 'Sign in required' })

  const configuredHost = (process.env.COMPUTETORRENT_PROVIDER_LAN_HOST || '').trim()
  const host = /^[a-zA-Z0-9.:-]+$/.test(configuredHost) ? configuredHost : ''
  const scheme = req.headers['x-forwarded-proto'] === 'https' ? 'wss' : 'ws'
  return res.status(200).json({
    address: host ? `${scheme}://${host}:8001/ws/seeder` : null,
  })
}
