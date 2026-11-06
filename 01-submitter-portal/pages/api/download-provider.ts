import type { NextApiRequest, NextApiResponse } from 'next'
import http from 'http'

export const config = {
  api: {
    responseLimit: false,
  },
}

export default async function downloadProvider(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    return res.status(405).json({ detail: 'Method not allowed' })
  }

  const orchestratorUrl = process.env.COMPUTETORRENT_ORCHESTRATOR_API_URL || 'http://orchestrator:8001/api'
  const targetUrl = new URL(`${orchestratorUrl.replace(/\/$/, '')}/provider-update/download`)

  const upstreamReq = http.request(
    targetUrl,
    {
      method: 'GET',
      headers: {
        Accept: 'application/octet-stream',
        'User-Agent': 'ComputeTorrent-Portal/1.0',
      },
    },
    (upstreamRes) => {
      if (upstreamRes.statusCode !== 200) {
        res.status(upstreamRes.statusCode || 502).json({ detail: 'Provider update unavailable from coordinator' })
        return
      }

      res.setHeader('Content-Type', 'application/octet-stream')
      res.setHeader('Content-Disposition', 'attachment; filename="ComputeTorrent_Seeder.exe"')
      if (upstreamRes.headers['content-length']) {
        res.setHeader('Content-Length', upstreamRes.headers['content-length'])
      }

      upstreamRes.pipe(res)
    }
  )

  upstreamReq.on('error', (err) => {
    if (!res.headersSent) {
      res.status(502).json({ detail: `Could not reach coordinator: ${err.message}` })
    }
  })

  upstreamReq.end()
}
