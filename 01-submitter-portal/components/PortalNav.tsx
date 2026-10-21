import { useRouter } from 'next/router'
import { useState, useEffect } from 'react'
import styles from '../styles/Home.module.css'

export default function PortalNav() {
  const router = useRouter()
  const [onlineCount, setOnlineCount] = useState<number | null>(null)
  const [copiedUrl, setCopiedUrl] = useState(false)

  useEffect(() => {
    fetch('/api/ct/seeders')
      .then(res => res.ok ? res.json() : [])
      .then((data: any[]) => {
        if (Array.isArray(data)) {
          const count = data.filter(s => ['online', 'idle', 'busy'].includes(s.state || s.status)).length
          setOnlineCount(count)
        }
      })
      .catch(() => {})
  }, [])

  const logout = async () => {
    await fetch('/api/session', { method: 'DELETE' })
    router.replace('/login')
  }

  const copyWsAddress = () => {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${scheme}://${window.location.hostname}:8001/ws/seeder`
    navigator.clipboard.writeText(wsUrl)
    setCopiedUrl(true)
    setTimeout(() => setCopiedUrl(false), 2200)
  }

  return (
    <header className={styles.navHeader}>
      <div className={styles.brandContainer}>
        <a href="/" className={styles.brandLogo}>
          <span className={styles.brandIcon}>⚡</span>
          <span className={styles.brandText}>ComputeTorrent</span>
          <span className={styles.brandBadge}>Distributed AI</span>
        </a>
      </div>

      <nav className={styles.portalNav}>
        <a className={router.pathname === '/inference' ? styles.activeNav : styles.navLink} href="/inference">
          <span className={styles.navIcon}>🧠</span>
          <span>Model Studio</span>
        </a>
        <a className={router.pathname === '/' ? styles.activeNav : styles.navLink} href="/">
          <span className={styles.navIcon}>🖥️</span>
          <span>Cluster Nodes</span>
        </a>
        <a className={router.pathname === '/history' ? styles.activeNav : styles.navLink} href="/history">
          <span className={styles.navIcon}>📜</span>
          <span>Task Audit</span>
        </a>
        <a className={router.pathname === '/credits' ? styles.activeNav : styles.navLink} href="/credits">
          <span className={styles.navIcon}>💳</span>
          <span>Credits</span>
        </a>
      </nav>

      <div className={styles.navActions}>
        <button
          type="button"
          onClick={copyWsAddress}
          className={styles.copyBtn}
          title="Click to copy WebSocket URL for provider desktop apps"
        >
          {copiedUrl ? '✅ Copied WS URL' : '🔗 Copy Provider URL'}
        </button>

        {onlineCount !== null && (
          <div className={styles.clusterPill}>
            <span className={onlineCount > 0 ? styles.dotGreen : styles.dotAmber}></span>
            <span>{onlineCount} {onlineCount === 1 ? 'Node' : 'Nodes'} Live</span>
          </div>
        )}

        <button type="button" onClick={logout} className={styles.signOutBtn} title="Sign out of workspace">
          <span>Sign Out</span>
          <span className={styles.logoutIcon}>🚪</span>
        </button>
      </div>
    </header>
  )
}
