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
      const response = await fetch('/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Login failed')
      const next = typeof router.query.next === 'string' && router.query.next.startsWith('/') && !router.query.next.startsWith('//') ? router.query.next : '/'
      router.replace(next)
    } catch (reason: any) { setError(reason.message) } finally { setLoading(false) }
  }
  return <div className={styles.container}><Head><title>Sign in | ComputeTorrent</title></Head><main className={styles.loginPage}>
    <div className={styles.loginCard}><div className={styles.eyebrow}>COMPUTETORRENT NETWORK</div><h1>Operator sign in</h1><p>Enter the private workspace password configured by your network operator.</p>
      <form className={styles.form} onSubmit={submit}><div className={styles.formGroup}><label htmlFor="password">Workspace password</label><input id="password" className={styles.select} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        {error && <p className={styles.error}>{error}</p>}<button className={styles.button} disabled={loading}>{loading ? 'Signing in…' : 'Sign in to workspace'}</button></form>
    </div>
  </main></div>
}
