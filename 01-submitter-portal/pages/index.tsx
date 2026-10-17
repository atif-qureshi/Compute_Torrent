import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import styles from '../styles/Home.module.css'
import PortalNav from '../components/PortalNav'

const API = '/api/ct'
const ACCOUNT = 'web-portal'

async function responseJson(response: Response) {
  let body: any = {}
  try { body = await response.json() } catch { /* ignore */ }
  if (!response.ok) {
    const detail = body.detail || body.message
    throw new Error(typeof detail === 'string' ? detail : `Coordinator returned ${response.status}`)
  }
  return body
}

function timeAgo(value?: string) {
  if (!value) return 'Last seen unknown'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return 'Last seen unknown'
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) return 'Seen just now'
  if (seconds < 3600) return `Seen ${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `Seen ${Math.floor(seconds / 3600)}h ago`
  return `Seen ${Math.floor(seconds / 86400)}d ago`
}

export default function Home() {
  const [tasks, setTasks] = useState<any[]>([])
  const [seeders, setSeeders] = useState<any[]>([])
  const [credits, setCredits] = useState<any>(null)
  const [network, setNetwork] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [taskFilter, setTaskFilter] = useState('all')
  const [errorMessage, setErrorMessage] = useState('')
  const [lastUpdated, setLastUpdated] = useState('')
  const [providerAddress, setProviderAddress] = useState('ws://127.0.0.1:8001/ws/seeder')
  const [copiedAddress, setCopiedAddress] = useState(false)

  useEffect(() => {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const fallback = `${scheme}://${window.location.hostname}:8001/ws/seeder`
    fetch('/api/provider-address').then(responseJson).then((data) => {
      if (data.address) setProviderAddress(data.address)
      else setProviderAddress(fallback)
    }).catch(() => setProviderAddress(fallback))
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [tasksRes, seedersRes, creditsRes] = await Promise.all([
        fetch(`${API}/tasks?limit=12&submitter_id=${ACCOUNT}`),
        fetch(`${API}/seeders`),
        fetch(`${API}/credits?submitter_id=${ACCOUNT}`),
      ])
      const [taskData, seederData, creditData] = await Promise.all([
        responseJson(tasksRes), responseJson(seedersRes), responseJson(creditsRes),
      ])
      const [healthResult, networkResult] = await Promise.allSettled([
        fetch(`${API}/health`).then(responseJson),
        fetch(`${API}/network`).then(responseJson),
      ])
      setHealth(healthResult.status === 'fulfilled' ? healthResult.value : { status: 'unavailable' })
      setNetwork(networkResult.status === 'fulfilled' ? networkResult.value : { status: 'unavailable', connected_peer_count: 0 })
      setTasks(taskData)
      setSeeders(seederData)
      setCredits(creditData)
      setLastUpdated(new Date().toISOString())
      setErrorMessage('')
    } catch (error: any) {
      setErrorMessage(error.message || 'Coordinator is unavailable')
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 7000)
    return () => clearInterval(timer)
  }, [refresh])

  const onlineSeeders = seeders.filter((node) => ['online', 'idle', 'busy'].includes(node.state || node.status))
  const visibleTasks = taskFilter === 'all' ? tasks : tasks.filter((task) => task.status === taskFilter)
  const coordinatorOnline = health?.status === 'healthy'
  const connectionLabel = coordinatorOnline ? 'Coordinator online' : health === null ? 'Checking coordinator…' : 'Coordinator offline'
  const sortedSeeders = [...seeders].sort((left, right) => {
    const leftOnline = ['online', 'idle', 'busy'].includes(left.state || left.status) ? 1 : 0
    const rightOnline = ['online', 'idle', 'busy'].includes(right.state || right.status) ? 1 : 0
    return rightOnline - leftOnline
  })

  const revokeProvider = async (nodeId: string) => {
    if (!window.confirm(`Revoke ${nodeId}? It will need to enroll again to reconnect.`)) return
    try {
      const result = await responseJson(await fetch(`${API}/seeders/${encodeURIComponent(nodeId)}/credential`, { method: 'DELETE' }))
      if (result.status === 'revoked') await refresh()
    } catch (error: any) {
      setErrorMessage(error.message || 'Could not revoke provider')
    }
  }

  const copyProviderAddress = async () => {
    try {
      await navigator.clipboard.writeText(providerAddress)
      setCopiedAddress(true)
      window.setTimeout(() => setCopiedAddress(false), 1800)
    } catch {
      setErrorMessage('Clipboard access is unavailable. Select and copy the provider address manually.')
    }
  }

  return <div className={styles.container}>
    <Head><title>ComputeTorrent | Volunteer Compute</title><meta name="description" content="Submit local AI work to a trusted volunteer-computing network." /></Head>
    <main className={styles.main}>
      <header className={styles.header}>
        <div>
          <div className={styles.eyebrow}>LOCAL VOLUNTEER COMPUTE</div>
          <h1 className={styles.title}>ComputeTorrent</h1>
          <p className={styles.description}>Your volunteer compute workspace. Open Model Studio to run a small model across your connected PCs.</p>
        </div>
        <PortalNav />
      </header>

      <section className={styles.statsGrid} aria-label="Network overview">
        <div className={styles.statCard}><span>WORKERS ONLINE</span><strong>{onlineSeeders.length}</strong><small>Connected provider PCs</small></div>
        <div className={styles.statCard}><span>RECENT ACTIVE TASKS</span><strong>{tasks.filter((task) => ['pending', 'allocated', 'running'].includes(task.status)).length}</strong><small>Waiting or processing</small></div>
        <div className={styles.statCard}><span>RECENTLY COMPLETED</span><strong>{tasks.filter((task) => task.status === 'completed').length}</strong><small>Verified jobs</small></div>
        <div className={styles.statCard}><span>AVAILABLE CREDITS</span><strong>{credits?.balance ?? '—'}</strong><small>1 demo credit per task</small></div>
      </section>

      {errorMessage && <div className={styles.error} role="alert">{errorMessage} <button type="button" onClick={refresh}>Retry</button></div>}

      <div className={styles.workspaceGrid}>
        <section className={styles.card}>
          <div className={styles.sectionHeading}>
            <div><div className={styles.eyebrow}>VOLUNTEER NETWORK</div><h2>Connect worker PCs</h2></div>
            <span className={styles.liveBadge} data-offline={!coordinatorOnline}>{onlineSeeders.length} online</span>
          </div>
          <p className={styles.muted}>Install the provider app on each trusted computer. The address below is configured for this coordinator.</p>
          <div className={styles.networkAddress}>
            <code>{providerAddress}</code>
            <button type="button" className={styles.buttonSecondary} onClick={copyProviderAddress}>{copiedAddress ? 'Copied' : 'Copy address'}</button>
          </div>
          <ol className={styles.setupSteps}>
            <li>Keep this coordinator and its local stack running.</li>
            <li>Enter the address above in the provider app.</li>
            <li>Enter the join code from <code>COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN</code> in <code>.env</code>.</li>
            <li>For another PC, allow ports 8001 and 9100 on the trusted LAN only.</li>
          </ol>
          {seeders.length === 0 ? <p className={styles.muted}>No provider PCs are enrolled yet.</p> : <div className={styles.workerList}>{sortedSeeders.slice(0, 8).map((node) => {
            const state = node.status === 'revoked' ? 'revoked' : (node.state || node.status || 'offline')
            const profile = node.profile || {}
            return <div className={styles.workerRow} key={node.node_id}>
              <span className={styles.workerDot} data-state={state} />
              <div className={styles.workerInfo}>
                <strong>{node.node_id}</strong>
                <small>{[
                  profile.GPU ? `${profile.GPU}${profile.VRAM ? ` · ${(Number(profile.VRAM) / 1024).toFixed(1)} GB VRAM` : ''} · ${profile.CUDA ? 'CUDA ready' : 'CPU inference'}` : `${profile.cpu_cores || '—'} CPU cores · CPU inference`,
                  `${profile.RAM ?? '—'} GB RAM`,
                  `Docker ${profile.docker_ok === false ? 'unavailable' : 'ready'}`,
                  timeAgo(node.last_heartbeat),
                ].join(' · ')}</small>
              </div>
              <span className={styles.workerState}>{state}</span>
              <button className={styles.revokeButton} type="button" onClick={() => revokeProvider(node.node_id)} disabled={state === 'revoked'}>Revoke</button>
            </div>
          })}</div>}
          <a className={styles.textLink} href="/history">Open task history →</a>
        </section>

        <section className={styles.card}>
          <div className={styles.sectionHeading}>
            <div><div className={styles.eyebrow}>IMPLEMENTATION STATUS</div><h2>What runs today</h2></div>
          </div>
          <ul className={styles.featureList}>
            <li>WebTorrent file transfer with SHA-256 checks</li>
            <li>Unique-provider replica agreement and private known-answer canary jobs</li>
            <li>Challenged output-report receipts with independently checked Merkle proofs</li>
          </ul>
          <p className={styles.muted}>The receipt verifies committed output reports and sampled openings; it does not prove model hidden-state execution. Full VeriLLM layer verification remains future work.</p>
          <p className={styles.muted}>Connected libp2p peers: {network?.status === 'unavailable' ? 'unavailable' : (network?.connected_peer_count ?? 'checking…')}. Last refresh: {lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : 'checking…'}.</p>
        </section>
      </div>

      <section className={styles.card}>
        <div className={styles.sectionHeading}>
          <div><div className={styles.eyebrow}>RECENT ACTIVITY</div><h2>Your tasks</h2></div>
          <select aria-label="Filter tasks" value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)} className={styles.filterSelect}>
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="allocated">Assigned</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        {visibleTasks.length === 0
          ? <p className={styles.muted}>No tasks yet. Start a run from Model Studio.</p>
          : <div className={styles.taskTable}>{visibleTasks.map((task) =>
            <a href={`/history?task_id=${encodeURIComponent(task.task_id)}`} className={styles.taskRow} key={task.task_id}>
              <span className={styles.taskId}>{task.task_id}</span>
              <span>{task.model_name}</span>
              <span className={`${styles.statusPill} ${styles[`status_${task.status}`] || ''}`}>{task.status}</span>
              <span>{task.mode || 'WS-RR'}</span>
              <span>{new Date(task.created_at).toLocaleString()}</span>
              <span>Details →</span>
            </a>)
          }</div>}
      </section>

      <footer className={styles.footer}>Local-first volunteer compute. Inference runs in a network-isolated container on each provider; demo credits have no cash value.</footer>
    </main>
  </div>
}
