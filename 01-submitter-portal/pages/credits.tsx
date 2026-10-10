import { useEffect, useState } from 'react'
import Head from 'next/head'
import styles from '../styles/Home.module.css'
import PortalNav from '../components/PortalNav'

const API = '/api/ct'

export default function Credits() {
  const [credits, setCredits] = useState<any>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const load = () => fetch(`${API}/credits?submitter_id=web-portal`).then(async (response) => {
      if (!response.ok) throw new Error('Could not load credits')
      setCredits(await response.json())
      setError('')
    }).catch((reason) => setError(reason.message))
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])
  return <div className={styles.container}><Head><title>Credits | ComputeTorrent</title></Head><main className={styles.main}>
    <header className={styles.header}><div><div className={styles.eyebrow}>WORKSPACE</div><h1 className={styles.title}>Credits</h1><p className={styles.description}>Review task charges and contribution rewards recorded by this network.</p></div>
      <PortalNav /></header>
    {error && <p className={styles.error}>{error}</p>}
    {credits && <><section className={styles.statsGrid}><div className={styles.statCard}><span>AVAILABLE BALANCE</span><strong>{credits.balance}</strong><small>Demo credits for this workspace</small></div><div className={styles.statCard}><span>TASK COST</span><strong>1</strong><small>Credit per submitted task</small></div><div className={styles.statCard}><span>LEDGER ENTRIES</span><strong>{credits.entries.length}</strong><small>Charges and provider rewards</small></div></section>
      <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>ACCOUNT ACTIVITY</div><h2>Credit ledger</h2></div></div>{credits.entries.length ? <div className={styles.ledgerList}>{credits.entries.map((entry) => <article className={styles.ledgerRow} key={entry.id || `${entry.entry_type}-${entry.created_at}`}>
        <div><strong>{entry.description}</strong><small>{entry.entry_type} {entry.task_id ? `· ${entry.task_id}` : ''}</small></div><b className={entry.amount > 0 ? styles.creditPlus : styles.creditMinus}>{entry.amount > 0 ? '+' : ''}{entry.amount}</b><time>{new Date(entry.created_at).toLocaleString()}</time>
      </article>)}</div> : <p className={styles.muted}>No credit activity yet.</p>}</section>
      <p className={styles.muted}>Credits are demonstration accounting for this MVP. They have no cash value and cannot be redeemed.</p></>}
  </main></div>
}
