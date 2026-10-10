import { createHmac, createHash, timingSafeEqual } from 'node:crypto'
import type { NextApiRequest, NextApiResponse } from 'next'

const COOKIE_NAME = 'ct_session'
const SESSION_SECONDS = 60 * 60 * 24 * 7

function signature(expires: string) {
  const secret = process.env.COMPUTETORRENT_SESSION_SECRET || ''
  return createHmac('sha256', secret).update(expires).digest('hex')
}

export function hasValidSession(req: NextApiRequest) {
  const [expires, provided] = (req.cookies[COOKIE_NAME] || '').split('.')
  if (!expires || !provided || !process.env.COMPUTETORRENT_SESSION_SECRET || Number(expires) < Date.now()) return false
  const expected = signature(expires)
  const presented = Buffer.from(provided, 'hex')
  const expectedBytes = Buffer.from(expected, 'hex')
  return presented.length === expectedBytes.length && timingSafeEqual(presented, expectedBytes)
}

export function setSession(res: NextApiResponse) {
  const expires = String(Date.now() + SESSION_SECONDS * 1000)
  const value = `${expires}.${signature(expires)}`
  const secure = process.env.COMPUTETORRENT_COOKIE_SECURE === 'true' ? '; Secure' : ''
  res.setHeader('Set-Cookie', `${COOKIE_NAME}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_SECONDS}${secure}`)
}

export function clearSession(res: NextApiResponse) {
  const secure = process.env.COMPUTETORRENT_COOKIE_SECURE === 'true' ? '; Secure' : ''
  res.setHeader('Set-Cookie', `${COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`)
}

export function passwordMatches(value: string) {
  const expected = process.env.COMPUTETORRENT_PORTAL_PASSWORD || ''
  if (!expected || !value) return false
  return timingSafeEqual(createHash('sha256').update(value).digest(), createHash('sha256').update(expected).digest())
}
