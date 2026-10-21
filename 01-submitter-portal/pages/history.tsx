import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import styles from '../styles/Home.module.css'
import PortalNav from '../components/PortalNav'

const API = '/api/ct'

export default function History() {
  const router = useRouter()
  const [tasks, setTasks] = useState<any[]>([])
  const [selected, setSelected] = useState<any>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [copiedText, setCopiedText] = useState(false)

  useEffect(() => {
    const load = () => fetch(`${API}/history?submitter_id=web-portal`).then(async (response) => {
      if (!response.ok) throw new Error('Could not load task history')
      setTasks(await response.json())
      setError('')
    }).catch((reason) => setError(reason.message)).finally(() => setLoading(false))

    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!selected?.task_id || ['completed', 'failed'].includes(selected.status)) return
    const timer = setInterval(() => {
      fetch(`${API}/tasks/${encodeURIComponent(selected.task_id)}`)
        .then((response) => response.ok ? response.json() : null)
        .then((details) => { if (details) setSelected(details) })
        .catch(() => {})
    }, 3000)
    return () => clearInterval(timer)
  }, [selected?.task_id, selected?.status])

  const loadTask = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API}/tasks/${encodeURIComponent(id)}`)
      if (!response.ok) {
        let message = 'Could not load task details'
        try { message = (await response.json()).detail || message } catch { /* Keep fallback */ }
        throw new Error(message)
      }
      setSelected(await response.json())
      setError('')
    } catch (reason: any) {
      setError(reason.message || 'Could not load task details')
    }
  }, [])

  const openTask = (id: string) => {
    void router.push({ pathname: '/history', query: { task_id: id } }, undefined, { shallow: true })
    void loadTask(id)
  }

  useEffect(() => {
    const id = router.query.task_id
    if (router.isReady && typeof id === 'string' && id !== selected?.task_id) void loadTask(id)
  }, [router.isReady, router.query.task_id, selected?.task_id, loadTask])

  const downloadResult = () => {
    const blob = new Blob([JSON.stringify(selected.result, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.href = url
    link.download = `${selected.task_id}-result.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const copyResult = () => {
    if (selected?.result?.text) {
      navigator.clipboard.writeText(selected.result.text)
      setCopiedText(true)
      setTimeout(() => setCopiedText(false), 2000)
    }
  }

  const visibleTasks = filter === 'all' ? tasks : tasks.filter((task) => task.status === filter)

  return (
    <div className={styles.container}>
      <Head>
        <title>Task History & Audit | ComputeTorrent</title>
        <meta name="description" content="Audit trails, replica verification receipts and task history." />
      </Head>

      <main className={styles.main}>
        <PortalNav />

        <header className={styles.header}>
          <div>
            <div className={styles.eyebrow}>AUDIT TRAILS</div>
            <h1 className={styles.title}>
              Task Execution <span className={styles.titleGradient}>History</span>
            </h1>
            <p className={styles.description}>
              Inspect provider task allocations, chunk splitting, multi-peer replica verification, and cryptographic audit proofs.
            </p>
          </div>
          <a href="/inference" className={`${styles.actionButton} ${styles.actionPrimary}`}>
            🧠 New Inference Run →
          </a>
        </header>

        {error && (
          <div className={styles.errorBanner}>
            <span>⚠️ {error}</span>
            <button className={styles.actionButton} onClick={() => setError('')}>Dismiss</button>
          </div>
        )}

        {/* Task List Section */}
        <section className={styles.card}>
          <div className={styles.sectionHeading}>
            <div>
              <span className={styles.eyebrow}>SUBMISSIONS</span>
              <h2>{tasks.length} Total Task Records</h2>
            </div>
            <select className={styles.filterSelect} value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All Statuses ({tasks.length})</option>
              <option value="pending">Pending</option>
              <option value="allocated">Assigned</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {loading ? (
            <p style={{ color: '#94a3b8' }}>Loading execution history…</p>
          ) : visibleTasks.length === 0 ? (
            <div className={styles.emptyState}>
              <p>No tasks match the selected filter.</p>
            </div>
          ) : (
            <div className={styles.taskTable}>
              <div className={styles.taskTableHeader}>
                <span>Task ID</span>
                <span>Model Name</span>
                <span>Status</span>
                <span>Scheduler</span>
                <span>Created At</span>
                <span>Action</span>
              </div>
              {visibleTasks.map((task) => (
                <div
                  className={styles.taskRow}
                  key={task.task_id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => openTask(task.task_id)}
                >
                  <span className={styles.taskId}>{task.task_id.slice(0, 18)}…</span>
                  <span style={{ fontWeight: 600, color: '#f8fafc' }}>{task.model_name}</span>
                  <div>
                    <span className={`${styles.statusPill} ${styles[`status_${task.status}`] || ''}`}>
                      {task.status}
                    </span>
                  </div>
                  <span style={{ color: '#94a3b8' }}>{task.mode || 'WS-RR'}</span>
                  <span style={{ color: '#64748b' }}>{new Date(task.created_at).toLocaleString()}</span>
                  <button type="button" className={styles.actionButton}>
                    {selected?.task_id === task.task_id ? 'Viewing' : 'Inspect →'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Selected Task Detail Inspector */}
        {selected && (
          <section className={styles.card}>
            <div className={styles.sectionHeading}>
              <div>
                <span className={styles.eyebrow}>TASK INSPECTOR</span>
                <h2>{selected.task_id}</h2>
              </div>
              <span className={`${styles.statusPill} ${styles[`status_${selected.status}`] || ''}`}>
                {selected.status}
              </span>
            </div>

            <div className={styles.progressTrack}>
              <div
                className={styles.progressFill}
                style={{
                  width: `${selected.progress?.total ? (selected.progress.completed / selected.progress.total) * 100 : 0}%`
                }}
              />
            </div>

            <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8' }}>
              Progress: <b>{selected.progress?.completed || 0}</b> of <b>{selected.progress?.total || 0}</b> chunks verified · Model: <b>{selected.model_name}</b> · Scheduler: <b>{selected.mode || 'WS-RR'}</b>
            </p>

            {/* Chunks Accordion */}
            {!!selected.chunks?.length && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
                <span className={styles.eyebrow}>CHUNK VERIFICATION RECEIPTS</span>
                {selected.chunks.map((chunk: any) => (
                  <div
                    key={chunk.chunk_id}
                    style={{
                      background: 'rgba(15, 23, 42, 0.6)',
                      border: '1px solid rgba(255, 255, 255, 0.06)',
                      borderRadius: '10px',
                      padding: '12px 16px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '13px' }}>
                        Chunk #{chunk.index + 1} ({chunk.chunk_id})
                      </span>
                      <span className={`${styles.statusPill} ${chunk.status === 'verified' ? styles.statusOnline : styles.statusBusy}`}>
                        {chunk.status}
                      </span>
                    </div>

                    <small style={{ color: '#94a3b8', fontSize: '11px' }}>
                      Method: {chunk.verification?.method || (chunk.status === 'verified' ? 'Replica consensus' : 'Pending')}
                      {chunk.verification?.canary?.passed ? ` · Canary check passed (${chunk.verification.canary.id})` : ''}
                    </small>

                    {chunk.verification?.verillm_audit && (
                      <details style={{ marginTop: '6px', fontSize: '11px', color: '#a5b4fc' }}>
                        <summary style={{ cursor: 'pointer' }}>View VeriLLM cryptographic commitment root</summary>
                        <pre style={{ background: '#090e1a', padding: '10px', borderRadius: '8px', overflowX: 'auto', marginTop: '6px' }}>
                          {JSON.stringify(chunk.verification.verillm_audit, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Generated Output */}
            {selected.result?.text && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className={styles.eyebrow}>VERIFIED MODEL OUTPUT</span>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button type="button" className={styles.actionButton} onClick={copyResult}>
                      {copiedText ? '✅ Copied' : '📄 Copy Output'}
                    </button>
                    <button type="button" className={styles.actionButton} onClick={downloadResult}>
                      💾 Download Result JSON
                    </button>
                  </div>
                </div>
                <pre
                  style={{
                    background: '#090e1a',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    padding: '18px',
                    color: '#e2e8f0',
                    fontSize: '13px',
                    lineHeight: '1.7',
                    whiteSpace: 'pre-wrap',
                    overflowWrap: 'anywhere'
                  }}
                >
                  {selected.result.text}
                </pre>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
