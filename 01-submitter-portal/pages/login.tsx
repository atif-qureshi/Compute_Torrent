import React, { useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'

export default function Login() {
  const router = useRouter()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Authentication failed')
      const next =
        typeof router.query.next === 'string' &&
        router.query.next.startsWith('/') &&
        !router.query.next.startsWith('//')
          ? router.query.next
          : '/'
      router.replace(next)
    } catch (reason: any) {
      setError(reason.message || 'Invalid operator password')
    } finally {
      setLoading(false)
    }
  }

  return <><Head><title>Sign in · ComputeTorrent</title></Head><main className="login-layout"><section className="login-story"><a className="brand" href="/login"><span className="brand-mark">CT</span><span>ComputeTorrent<small>VOLUNTEER COMPUTE NETWORK</small></span></a><div><p className="eyebrow" style={{color:'#c0baff'}}>COMPUTE, TOGETHER.</p><h1>More possibility.<br/>Shared by your network.</h1><p>Bring trusted computers together to run small language models. One workspace for your providers, model runs, and results.</p></div><small style={{color:'#b9c0d4'}}>ComputeTorrent / Private operator workspace</small></section><section className="login-form"><div><p className="eyebrow">OPERATOR ACCESS</p><h1>Welcome to your workspace.</h1><p>Sign in with the private workspace password configured by your network operator.</p><form onSubmit={submit}><label className="field" htmlFor="workspace-password">Workspace password<input id="workspace-password" type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)} aria-describedby={error?'login-error':undefined}/></label>{error&&<div className="notice danger" id="login-error" role="alert">{error}</div>}<button className="button" disabled={loading} type="submit">{loading?'Signing in…':'Sign in to workspace →'}</button></form><p style={{fontSize:11,marginTop:24}}>Need access? Contact the workspace operator. Provider enrollment codes are separate from this password.</p></div></section></main></>
}
