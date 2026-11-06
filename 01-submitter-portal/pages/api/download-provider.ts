import type { NextApiRequest, NextApiResponse } from 'next'

export default function downloadProvider(_req: NextApiRequest, res: NextApiResponse) {
  return res.status(410).json({ detail: 'Legacy provider download retired. Obtain a trusted installer from your operator.' })
}
