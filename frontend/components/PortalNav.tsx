import { useRouter } from 'next/router'
import styles from '../styles/Home.module.css'

export default function PortalNav() {
  const router = useRouter()
  const logout = async () => {
    await fetch('/api/session', { method: 'DELETE' })
    router.replace('/login')
  }
  return <nav className={styles.portalNav}><a className={router.pathname === '/' ? styles.activeNav : ''} href="/">Workspace</a><a className={router.pathname === '/history' ? styles.activeNav : ''} href="/history">Task history</a><a className={router.pathname === '/credits' ? styles.activeNav : ''} href="/credits">Credits</a><button type="button" onClick={logout}>Sign out</button></nav>
}
