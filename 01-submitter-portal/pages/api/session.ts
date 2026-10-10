import type { NextApiRequest, NextApiResponse } from 'next'
import { clearSession, hasValidSession, passwordMatches, setSession } from '../../lib/session'

export default function session(req: NextApiRequest, res: NextApiResponse) {
  if (req.method === 'GET') return res.status(200).json({ authenticated: hasValidSession(req) })
  if (req.method === 'DELETE') {
    clearSession(res)
    return res.status(200).json({ authenticated: false })
  }
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'GET, POST, DELETE')
    return res.status(405).json({ detail: 'Method not allowed' })
  }
  if (!process.env.COMPUTETORRENT_SESSION_SECRET || !process.env.COMPUTETORRENT_PORTAL_PASSWORD) {
    return res.status(503).json({ detail: 'Portal login is not configured by the operator' })
  }
  if (!passwordMatches(String(req.body?.password || ''))) return res.status(401).json({ detail: 'Incorrect access password' })
  setSession(res)
  return res.status(200).json({ authenticated: true })
}
