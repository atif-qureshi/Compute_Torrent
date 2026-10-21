import { useState } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import styles from '../styles/Home.module.css'

export default function Login() {
  const router = useRouter()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event: any) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Login failed')
      const next = typeof router.query.next === 'string' && router.query.next.startsWith('/') && !router.query.next.startsWith('//')
        ? router.query.next
        : '/'
      router.replace(next)
    } catch (reason: any) {
      setError(reason.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.container}>
      <Head>
        <title>Sign in | ComputeTorrent</title>
        <meta name="description" content="Sign in to ComputeTorrent operator portal." />
      </Head>

      <main className={styles.loginPage}>
        <div className={styles.loginCard}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '24px' }}>⚡</span>
            <span className={styles.eyebrow} style={{ margin: 0 }}>COMPUTETORRENT NETWORK</span>
          </div>

          <div>
            <h1>Operator Workspace</h1>
            <p style={{ margin: '6px 0 0', color: '#94a3b8', fontSize: '13px' }}>
              Sign in with your private workspace password configured by the network coordinator.
            </p>
          </div>

          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label htmlFor="password" style={{ fontSize: '12px', fontWeight: 600, color: '#e2e8f0' }}>
                Workspace Password
              </label>
              <input
                id="password"
                className={styles.inputField}
                type="password"
                autoComplete="current-password"
                placeholder="Enter password (default: local-computetorrent)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {error && (
              <div className={styles.errorBanner} style={{ padding: '10px 14px', fontSize: '12px' }}>
                <span>⚠️ {error}</span>
              </div>
            )}

            <button className={styles.submitBtn} disabled={loading}>
              {loading ? 'Authenticating…' : 'Enter Workspace →'}
            </button>
          </form>

          <small style={{ color: '#64748b', fontSize: '11px', textAlign: 'center' }}>
            Default development password is set in your <code>.env</code> file.
          </small>
        </div>
      </main>
    </div>
  )
}
