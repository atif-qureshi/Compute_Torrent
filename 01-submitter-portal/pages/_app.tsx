import { useEffect, useState } from 'react'
import type { AppProps } from 'next/app'
import { useRouter } from 'next/router'
import '../styles/globals.css'
import styles from '../styles/Home.module.css'

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (router.pathname === '/login') { setReady(true); return }
    let active = true
    fetch('/api/session').then((response) => response.json()).then((result) => {
      if (!active) return
      if (result.authenticated) setReady(true)
      else router.replace(`/login?next=${encodeURIComponent(router.asPath)}`)
    }).catch(() => router.replace('/login'))
    return () => { active = false }
  }, [router.pathname, router.asPath])
  if (!ready && router.pathname !== '/login') return <main className={styles.loginPage}><p>Checking operator session…</p></main>
  return <Component {...pageProps} />
}
