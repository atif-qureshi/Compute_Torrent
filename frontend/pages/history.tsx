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
      fetch(`${API}/tasks/${encodeURIComponent(selected.task_id)}`).then((response) => response.ok ? response.json() : null)
        .then((details) => { if (details) setSelected(details) }).catch(() => {})
    }, 3000)
    return () => clearInterval(timer)
  }, [selected?.task_id, selected?.status])
  const loadTask = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API}/tasks/${encodeURIComponent(id)}`)
      if (!response.ok) {
        let message = 'Could not load task details'
        try { message = (await response.json()).detail || message } catch { /* Keep the readable fallback. */ }
        throw new Error(message)
      }
      setSelected(await response.json())
      setError('')
    } catch (reason: any) { setError(reason.message || 'Could not load task details') }
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
  const visibleTasks = filter === 'all' ? tasks : tasks.filter((task) => task.status === filter)
  return <div className={styles.container}><Head><title>Task history | ComputeTorrent</title></Head><main className={styles.main}>
    <header className={styles.header}><div><div className={styles.eyebrow}>WORKSPACE</div><h1 className={styles.title}>Task history</h1><p className={styles.description}>Follow progress from provider assignment through replica verification and result delivery.</p></div>
      <PortalNav /></header>
    {error && <p className={styles.error}>{error}</p>}
    <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>TASKS</div><h2>{tasks.length} submitted</h2></div><select className={styles.filterSelect} value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter task status"><option value="all">All statuses</option><option value="pending">Pending</option><option value="allocated">Assigned</option><option value="running">Running</option><option value="completed">Completed</option><option value="failed">Failed</option></select></div>
      {loading ? <p className={styles.muted}>Loading tasks…</p> : visibleTasks.length === 0 ? <p className={styles.muted}>No tasks match this filter.</p> : <div className={styles.taskTable}>{visibleTasks.map((task) => <button className={styles.historyTaskRow} type="button" key={task.task_id} onClick={() => openTask(task.task_id)}>
        <span className={styles.taskId}>{task.task_id}</span><span>{task.model_name}</span><span className={`${styles.statusPill} ${styles[`status_${task.status}`] || ''}`}>{task.status}</span><span>{task.mode || 'WS-RR'}</span><span>{new Date(task.created_at).toLocaleString()}</span><span>Open →</span>
      </button>)}</div>}
    </section>
    {selected && <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>TASK DETAIL</div><h2>{selected.task_id}</h2></div><span className={`${styles.statusPill} ${styles[`status_${selected.status}`] || ''}`}>{selected.status}</span></div>
      <div className={styles.progressTrack}><span style={{ width: `${selected.progress?.total ? (selected.progress.completed / selected.progress.total) * 100 : 0}%` }} /></div>
      <p className={styles.muted}>{selected.progress?.completed || 0} of {selected.progress?.total || 0} chunks verified · {selected.mode || 'WS-RR'} scheduler · {selected.model_name}</p>
      {!!selected.chunks?.length && <div className={styles.chunkList}>{selected.chunks.map((chunk) => <div className={styles.chunkRow} key={chunk.chunk_id}><span>{chunk.index + 1}</span><strong>{chunk.chunk_id}</strong><span>{chunk.status}</span><small>{chunk.verification?.method || (chunk.status === 'verified' ? 'Replica agreement' : 'Waiting for provider')}{chunk.verification?.canary?.passed ? ` · Known-answer check passed (${chunk.verification.canary.id})` : ''}</small>{chunk.failure_reason && <small className={styles.chunkFailure}>Failure: {chunk.failure_reason}</small>}{chunk.verification?.verillm_audit && <details className={styles.auditEvidence}><summary>Output transcript root {chunk.verification.verillm_audit.commitment_root.slice(0, 18)}…</summary><pre className={styles.result}>{JSON.stringify(chunk.verification.verillm_audit, null, 2)}</pre></details>}</div>)}</div>}
      {selected.result?.text && <><h3>Verified result</h3><pre className={styles.result}>{selected.result.text}</pre><button type="button" className={styles.buttonSecondary} onClick={downloadResult}>Download JSON result</button></>}
      {selected.result?.error && <p className={styles.error}>{selected.result.error}</p>}
      <button type="button" className={styles.buttonSecondary} onClick={() => { setSelected(null); void router.replace('/history', undefined, { shallow: true }) }}>Close task details</button>
    </section>}
  </main></div>
}
