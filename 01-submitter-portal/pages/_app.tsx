import React, { useEffect, useState } from 'react'
import type { AppProps } from 'next/app'
import { useRouter } from 'next/router'
import '../styles/globals.css'

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (router.pathname === '/login') {
      setReady(true)
      return
    }
    let active = true
    fetch('/api/session')
      .then((res) => res.json())
      .then((result) => {
        if (!active) return
        if (result.authenticated) setReady(true)
        else router.replace(`/login?next=${encodeURIComponent(router.asPath)}`)
      })
      .catch(() => router.replace('/login'))
    return () => {
      active = false
    }
  }, [router.pathname, router.asPath])

  if (!ready && router.pathname !== '/login') {
    return (
      <main
        style={{
          minHeight: '100vh',
          backgroundColor: '#090d16',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--font-sans)',
          color: '#94a3b8',
          fontSize: '13px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '16px' }}>⚡</span>
          <span>Verifying operator session…</span>
        </div>
      </main>
    )
  }

  return <Component {...pageProps} />
}
