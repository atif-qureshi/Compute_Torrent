import { useEffect, useState } from 'react'
import Head from 'next/head'
import styles from '../styles/Home.module.css'
import PortalNav from '../components/PortalNav'

const API = '/api/ct'

export default function Credits() {
  const [credits, setCredits] = useState<any>(null)
  const [error, setError] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)

  const load = () => {
    setIsRefreshing(true)
    fetch(`${API}/credits?submitter_id=web-portal`)
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load credits')
        setCredits(await response.json())
        setError('')
      })
      .catch((reason) => setError(reason.message))
      .finally(() => setIsRefreshing(false))
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className={styles.container}>
      <Head>
        <title>Demo Credits Ledger | ComputeTorrent</title>
        <meta name="description" content="Accounting, task fees and contribution rewards." />
      </Head>

      <main className={styles.main}>
        <PortalNav />

        <header className={styles.header}>
          <div>
            <div className={styles.eyebrow}>ACCOUNTING & INCENTIVES</div>
            <h1 className={styles.title}>
              Demonstration <span className={styles.titleGradient}>Credits Ledger</span>
            </h1>
            <p className={styles.description}>
              Review task computation charges, volunteer reward distributions, and account balance history recorded on this coordinator.
            </p>
          </div>
          <button className={styles.actionButton} onClick={load}>
            {isRefreshing ? '🔄 Refreshing…' : '🔄 Refresh Ledger'}
          </button>
        </header>

        {error && (
          <div className={styles.errorBanner}>
            <span>⚠️ {error}</span>
            <button className={styles.actionButton} onClick={() => setError('')}>Dismiss</button>
          </div>
        )}

        {credits && (
          <>
            {/* 3 Metric Cards */}
            <section className={styles.statsGrid}>
              <div className={`${styles.statCard} ${styles.cardEmerald}`}>
                <div className={styles.cardHeader}>
                  <span>Available Balance</span>
                  <div className={styles.statIcon}>💳</div>
                </div>
                <strong>{credits.balance} Credits</strong>
                <small>Allocated for this workspace submitter</small>
              </div>

              <div className={`${styles.statCard} ${styles.cardCyan}`}>
                <div className={styles.cardHeader}>
                  <span>Inference Task Fee</span>
                  <div className={styles.statIcon}>⚡</div>
                </div>
                <strong>1.00 <small style={{ fontSize: '13px' }}>Credit/Task</small></strong>
                <small>Standard task verification unit cost</small>
              </div>

              <div className={`${styles.statCard} ${styles.cardViolet}`}>
                <div className={styles.cardHeader}>
                  <span>Ledger Transactions</span>
                  <div className={styles.statIcon}>📜</div>
                </div>
                <strong>{credits.entries.length}</strong>
                <small>Recorded charges and provider rewards</small>
              </div>
            </section>

            {/* Ledger Transactions Table */}
            <section className={styles.card}>
              <div className={styles.sectionHeading}>
                <div>
                  <span className={styles.eyebrow}>TRANSACTIONS</span>
                  <h2>Recent Credit Activities</h2>
                </div>
                <span className={styles.clusterPill}>
                  <span>{credits.entries.length} Events</span>
                </span>
              </div>

              {credits.entries.length ? (
                <div className={styles.ledgerList}>
                  {credits.entries.map((entry: any) => (
                    <article className={styles.ledgerRow} key={entry.id || `${entry.entry_type}-${entry.created_at}`}>
                      <div>
                        <strong style={{ fontSize: '14px', color: '#f8fafc', display: 'block' }}>
                          {entry.description}
                        </strong>
                        <small style={{ color: '#64748b', fontSize: '11px', marginTop: '4px', display: 'block' }}>
                          Type: {entry.entry_type} {entry.task_id ? `· Task: ${entry.task_id}` : ''}
                        </small>
                      </div>
                      <div>
                        <span className={entry.amount > 0 ? styles.creditPlus : styles.creditMinus}>
                          {entry.amount > 0 ? `+${entry.amount}` : entry.amount} Credits
                        </span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <time style={{ color: '#64748b', fontSize: '11px' }}>
                          {new Date(entry.created_at).toLocaleString()}
                        </time>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className={styles.emptyState}>
                  <p>No credit transactions recorded yet.</p>
                </div>
              )}
            </section>

            <p style={{ color: '#64748b', fontSize: '12px', textAlign: 'center', margin: 0 }}>
              💡 Credits are for demonstration accounting and verification benchmark in this MVP. They carry no monetary or cash value.
            </p>
          </>
        )}
      </main>
    </div>
  )
}
