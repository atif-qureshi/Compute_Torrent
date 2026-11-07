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

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#090d16',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <Head>
        <title>Sign in | ComputeTorrent</title>
        <meta name="description" content="Sign in to the ComputeTorrent operator workspace." />
      </Head>

      <div
        style={{
          width: '100%',
          maxWidth: '420px',
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '12px',
          padding: '32px 28px',
          boxShadow: '0 16px 40px rgba(0, 0, 0, 0.5)',
          display: 'flex',
          flexDirection: 'column',
          gap: '20px',
        }}
      >
        {/* Brand Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '8px',
              backgroundColor: 'rgba(59, 130, 246, 0.15)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
            }}
          >
            ⚡
          </div>
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc', margin: 0, letterSpacing: '-0.01em' }}>
              ComputeTorrent
            </h1>
            <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
              Distributed AI Operator Console
            </p>
          </div>
        </div>

        {/* Info Note */}
        <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0, lineHeight: 1.5 }}>
          Sign in with your private operator password to access cluster telemetry, model deployments, and provider management.
        </p>

        {/* Form */}
        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label htmlFor="password" style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1' }}>
              Operator Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="Enter workspace password…"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                backgroundColor: '#090d16',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                borderRadius: '8px',
                padding: '10px 12px',
                fontSize: '13px',
                color: '#f8fafc',
              }}
            />
          </div>

          {error && (
            <div
              style={{
                padding: '10px 12px',
                backgroundColor: 'rgba(244, 63, 94, 0.08)',
                border: '1px solid rgba(244, 63, 94, 0.25)',
                borderRadius: '6px',
                fontSize: '12px',
                color: '#fb7185',
              }}
            >
              ⚠️ {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: '10px 16px',
              backgroundColor: '#3b82f6',
              color: '#ffffff',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            {loading ? 'Authenticating…' : 'Enter Operator Console →'}
          </button>
        </form>

        <div style={{ textAlign: 'center', borderTop: '1px solid rgba(255, 255, 255, 0.06)', paddingTop: '16px' }}>
          <small style={{ color: '#64748b', fontSize: '11px' }}>
            Default development credentials are configured in your coordinator environment.
          </small>
        </div>
      </div>
    </div>
  )
}
