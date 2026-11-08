import React, { useEffect, useState } from 'react'
import type { AppProps } from 'next/app'
import { useRouter } from 'next/router'
import '../styles/globals.css'
import { WorkspaceProvider } from '../components/Workspace'

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (router.pathname === '/login') {
      setReady(true)
      return
    }
    setReady(false)
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

  useEffect(() => {
    const theme = localStorage.getItem('ct-theme') || 'light'
    document.documentElement.dataset.theme = theme
  }, [])
  if (!ready && router.pathname !== '/login') return <main className="session-loading" role="status">Opening your workspace…</main>
  if (router.pathname === '/login') return <Component {...pageProps} />
  return <WorkspaceProvider><Component {...pageProps} /></WorkspaceProvider>
}
