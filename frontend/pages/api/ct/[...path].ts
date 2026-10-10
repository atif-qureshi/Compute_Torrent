import type { NextApiRequest, NextApiResponse } from 'next'
import { hasValidSession } from '../../../lib/session'

const allowedMethods = new Set(['GET', 'POST', 'DELETE'])
export const config = { api: { bodyParser: { sizeLimit: '12mb' } } }

export default async function orchestratorProxy(req: NextApiRequest, res: NextApiResponse) {
  if (!hasValidSession(req)) return res.status(401).json({ detail: 'Sign in to the ComputeTorrent workspace first' })
  if (!req.method || !allowedMethods.has(req.method)) {
    res.setHeader('Allow', Array.from(allowedMethods).join(', '))
    return res.status(405).json({ detail: 'Method not allowed' })
  }

  const token = process.env.COMPUTETORRENT_API_TOKEN
  const apiBase = process.env.COMPUTETORRENT_ORCHESTRATOR_API_URL || 'http://orchestrator:8001/api'
  if (!token) return res.status(503).json({ detail: 'Portal API credentials are not configured' })

  const segments = Array.isArray(req.query.path) ? req.query.path : [req.query.path || '']
  const target = new URL(`${apiBase.replace(/\/$/, '')}/${segments.map(encodeURIComponent).join('/')}`)
  for (const [key, value] of Object.entries(req.query)) {
    if (key === 'path') continue
    for (const item of Array.isArray(value) ? value : [value]) {
      if (typeof item === 'string') target.searchParams.append(key, item)
    }
  }

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(req.method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(req.method === 'POST' ? { body: JSON.stringify(req.body ?? {}) } : {}),
    })
    const contentType = upstream.headers.get('content-type')
    if (contentType) res.setHeader('Content-Type', contentType)
    res.status(upstream.status).send(await upstream.text())
  } catch {
    res.status(502).json({ detail: 'Could not reach the ComputeTorrent coordinator' })
  }
}
