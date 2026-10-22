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
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export default function Home() {
  const [tasks, setTasks] = useState<any[]>([])
  const [seeders, setSeeders] = useState<any[]>([])
  const [credits, setCredits] = useState<any>(null)
  const [network, setNetwork] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [taskFilter, setTaskFilter] = useState('all')
  const [errorMessage, setErrorMessage] = useState('')
  const [providerAddress, setProviderAddress] = useState('ws://127.0.0.1:8001/ws/seeder')
  const [lanAddress, setLanAddress] = useState('ws://192.168.100.7:8001/ws/seeder')
  const [publicAddress, setPublicAddress] = useState<string | null>(null)
  const [copiedLan, setCopiedLan] = useState(false)
  const [copiedPublic, setCopiedPublic] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  useEffect(() => {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const fallback = `${scheme}://${window.location.hostname}:8001/ws/seeder`
    fetch('/api/provider-address')
      .then(responseJson)
      .then((data) => {
        if (data.address) setProviderAddress(data.address)
        else setProviderAddress(fallback)
        if (data.lan_address) setLanAddress(data.lan_address)
        if (data.public_address) setPublicAddress(data.public_address)
      })
      .catch(() => setProviderAddress(fallback))
  }, [])

  const refresh = useCallback(async () => {
    setIsRefreshing(true)
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
      setErrorMessage('')
    } catch (error: any) {
      setErrorMessage(error.message || 'Coordinator is unavailable')
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  const onlineSeeders = seeders.filter((node) => ['online', 'idle', 'busy'].includes(node.state || node.status))
  const visibleTasks = taskFilter === 'all' ? tasks : tasks.filter((task) => task.status === taskFilter)
  const coordinatorOnline = health?.status === 'healthy'

  const revokeProvider = async (nodeId: string) => {
    if (!window.confirm(`Revoke credentials for ${nodeId}? This machine will need the join token to reconnect.`)) return
    try {
      const result = await responseJson(await fetch(`${API}/seeders/${encodeURIComponent(nodeId)}/credential`, { method: 'DELETE' }))
      if (result.status === 'revoked') await refresh()
    } catch (error: any) {
      setErrorMessage(error.message || 'Could not revoke provider')
    }
  }

  const copyWs = () => {
    navigator.clipboard.writeText(publicAddress || lanAddress)
    setCopiedLan(true)
    setTimeout(() => setCopiedLan(false), 2200)
  }

  return (
    <div className={styles.container}>
      <Head>
        <title>Cluster Nodes & Overview | ComputeTorrent</title>
        <meta name="description" content="ComputeTorrent distributed cluster management dashboard." />
      </Head>

      <main className={styles.main}>
        <PortalNav />

        {/* Hero Header */}
        <header className={styles.header}>
          <div>
            <div className={styles.eyebrow}>COMPUTETORRENT CLUSTER</div>
            <h1 className={styles.title}>
              Cluster Nodes & <span className={styles.titleGradient}>Resources</span>
            </h1>
            <p className={styles.description}>
              Monitor enrolled provider machines, distribute LLM inference workloads, and track verified task commitments across your private network.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button className={styles.actionButton} onClick={refresh}>
              {isRefreshing ? '🔄 Refreshing…' : '🔄 Refresh Status'}
            </button>
            <a href="/inference" className={`${styles.actionButton} ${styles.actionPrimary}`}>
              🧠 Open Model Studio →
            </a>
          </div>
        </header>

        {errorMessage && (
          <div className={styles.errorBanner}>
            <span>⚠️ {errorMessage}</span>
            <button className={styles.actionButton} onClick={() => { setErrorMessage(''); refresh() }}>Dismiss</button>
          </div>
        )}

        {/* 4 Multi-Accent Metric Cards */}
        <section className={styles.statsGrid}>
          <div className={`${styles.statCard} ${styles.cardEmerald}`}>
            <div className={styles.cardHeader}>
              <span>Active Nodes</span>
              <div className={styles.statIcon}>🖥️</div>
            </div>
            <strong>{onlineSeeders.length} <small style={{ fontSize: '14px', color: '#94a3b8' }}>/ {seeders.length} enrolled</small></strong>
            <small>{onlineSeeders.length >= 2 ? 'Cluster ready for distributed tasks' : 'Connect client PCs to scale'}</small>
          </div>

          <div className={`${styles.statCard} ${styles.cardCyan}`}>
            <div className={styles.cardHeader}>
              <span>Coordinator Status</span>
              <div className={styles.statIcon}>🌐</div>
            </div>
            <strong>{coordinatorOnline ? 'HEALTHY' : 'CHECKING'}</strong>
            <small>{coordinatorOnline ? 'REST API & WebSockets operational' : 'Attempting to ping service'}</small>
          </div>

          <div className={`${styles.statCard} ${styles.cardViolet}`}>
            <div className={styles.cardHeader}>
              <span>Total Tasks</span>
              <div className={styles.statIcon}>⚡</div>
            </div>
            <strong>{tasks.length}</strong>
            <small>Processed through replica consensus</small>
          </div>

          <div className={`${styles.statCard} ${styles.cardAmber}`}>
            <div className={styles.cardHeader}>
              <span>Demo Credits Balance</span>
              <div className={styles.statIcon}>💳</div>
            </div>
            <strong>{credits?.balance ?? '—'}</strong>
            <small>Demonstration rewards ledger</small>
          </div>
        </section>

        {/* Main Grid: Left: Node List, Right: Quick Connect & Recent Tasks */}
        <div className={styles.workspaceGrid}>
          {/* Left Column: Enrolled Compute Nodes */}
          <section className={styles.card}>
            <div className={styles.sectionHeading}>
              <div>
                <span className={styles.eyebrow}>HARDWARE INVENTORY</span>
                <h2>Enrolled Provider Computers</h2>
              </div>
              <span className={styles.clusterPill}>
                <span className={styles.dotGreen}></span>
                <span>{onlineSeeders.length} Active Now</span>
              </span>
            </div>

            {!seeders.length ? (
              <div className={styles.emptyState}>
                <p>No provider PCs enrolled yet.</p>
                <small style={{ color: '#64748b', display: 'block', marginTop: '6px' }}>
                  Run the provider desktop app on client machines using the WebSocket address shown on the right.
                </small>
              </div>
            ) : (
              <div className={styles.workerList}>
                {seeders.map((node) => {
                  const isOnline = ['online', 'idle', 'busy'].includes(node.state || node.status)
                  const profile = node.profile || {}
                  return (
                    <article className={styles.nodeCard} key={node.node_id}>
                      <div className={styles.nodeCardHeader}>
                        <div className={styles.nodeIdentity}>
                          <div className={styles.nodeIconWrapper}>
                            {profile.GPU ? '🎮' : '💻'}
                          </div>
                          <div className={styles.nodeTitleBlock}>
                            <span className={styles.nodeName}>
                              {profile.cpu_model || `Node ${node.node_id.slice(-10)}`}
                            </span>
                            <span className={styles.nodeSub}>
                              ID: {node.node_id} · {timeAgo(node.last_seen_at || node.updated_at)}
                            </span>
                          </div>
                        </div>

                        <span className={`${styles.statusPill} ${isOnline ? (node.state === 'busy' ? styles.statusBusy : styles.statusOnline) : styles.statusOffline}`}>
                          {node.state || node.status || 'offline'}
                        </span>
                      </div>

                      {/* Specs Badge Grid */}
                      <div className={styles.nodeSpecGrid}>
                        <div className={styles.specBadge}>
                          <span className={styles.specLabel}>CPU Cores</span>
                          <span className={styles.specValue}>{profile.cpu_cores || '—'} Logical</span>
                        </div>
                        <div className={styles.specBadge}>
                          <span className={styles.specLabel}>System RAM</span>
                          <span className={styles.specValue}>{profile.RAM || '—'} GB</span>
                        </div>
                        <div className={styles.specBadge}>
                          <span className={styles.specLabel}>GPU Device</span>
                          <span className={styles.specValue} title={profile.GPU || 'None'}>
                            {profile.GPU ? (profile.GPU.length > 18 ? profile.GPU.slice(0, 16) + '…' : profile.GPU) : 'CPU Only'}
                          </span>
                        </div>
                        <div className={styles.specBadge}>
                          <span className={styles.specLabel}>Docker SDK</span>
                          <span className={styles.specValue}>{profile.docker_ok ? '✅ Ready' : '❌ Missing'}</span>
                        </div>
                      </div>

                      <div className={styles.nodeFooter}>
                        <span style={{ fontSize: '11px', color: '#64748b' }}>
                          Petals Protocol: <b>v{profile.petals_protocol_version || '1'}</b> · Tier {node.tier || profile.tier || 2}
                        </span>
                        <button
                          type="button"
                          className={styles.revokeButton}
                          onClick={() => revokeProvider(node.node_id)}
                          title="Revoke client authentication key"
                        >
                          Revoke Access
                        </button>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </section>

          {/* Right Column: Connection Helper & Activity */}
          <div className={styles.sideColumn}>
            {/* Quick Connect Card */}
            <div className={styles.networkCard}>
              <div className={styles.sectionHeading} style={{ border: 'none', padding: 0 }}>
                <div>
                  <span className={styles.eyebrow}>CLIENT SETUP & TUNNEL</span>
                  <h2 style={{ fontSize: '17px' }}>Provider Connection URLs</h2>
                </div>
              </div>

              {publicAddress ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8' }}>🌐 GLOBAL REMOTE (NGROK TUNNEL)</span>
                    <span style={{ fontSize: '10px', color: '#34d399', fontWeight: 600 }}>Active Online</span>
                  </div>
                  <div className={styles.networkAddressRow} style={{ borderColor: 'rgba(6, 182, 212, 0.4)' }}>
                    <code>{publicAddress}</code>
                    <button
                      type="button"
                      className={styles.copyAddressBtn}
                      onClick={() => {
                        navigator.clipboard.writeText(publicAddress)
                        setCopiedPublic(true)
                        setTimeout(() => setCopiedPublic(false), 2200)
                      }}
                    >
                      {copiedPublic ? '✅ Copied' : '📋 Copy'}
                    </button>
                  </div>
                  <small style={{ color: '#94a3b8', fontSize: '11px' }}>
                    Use this URL for peers anywhere in the world across the internet.
                  </small>
                </div>
              ) : (
                <div style={{ background: 'rgba(99, 102, 241, 0.08)', border: '1px dashed rgba(99, 102, 241, 0.3)', borderRadius: '10px', padding: '12px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#a5b4fc', display: 'block' }}>
                    🌐 Want remote peers from other locations to join?
                  </span>
                  <p style={{ margin: '4px 0 8px', fontSize: '11px', color: '#94a3b8', lineHeight: '1.5' }}>
                    Run <code>.\start-ngrok.ps1</code> on this coordinator to create an instant public tunnel URL.
                  </p>
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, color: '#818cf8' }}>🏠 LOCAL NETWORK (WI-FI LAN)</span>
                  <span style={{ fontSize: '10px', color: '#34d399', fontWeight: 600 }}>Active Online</span>
                </div>
                <div className={styles.networkAddressRow}>
                  <code>{lanAddress}</code>
                  <button
                    type="button"
                    className={styles.copyAddressBtn}
                    onClick={() => {
                      navigator.clipboard.writeText(lanAddress)
                      setCopiedLan(true)
                      setTimeout(() => setCopiedLan(false), 2200)
                    }}
                  >
                    {copiedLan ? '✅ Copied' : '📋 Copy'}
                  </button>
                </div>
                <small style={{ color: '#64748b', fontSize: '11px' }}>
                  Use this URL for PCs connected to the same local Wi-Fi router.
                </small>
              </div>
            </div>

            {/* Quick Navigation Card */}
            <div className={styles.card}>
              <div className={styles.sectionHeading}>
                <h2>Workspace Navigation</h2>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <a href="/inference" className={styles.actionButton} style={{ justifyContent: 'space-between', padding: '12px 16px' }}>
                  <span>🧠 <b>Model Studio</b> (Distributed LLM)</span>
                  <span>→</span>
                </a>
                <a href="/history" className={styles.actionButton} style={{ justifyContent: 'space-between', padding: '12px 16px' }}>
                  <span>📜 <b>Task History & Audit</b></span>
                  <span>→</span>
                </a>
                <a href="/credits" className={styles.actionButton} style={{ justifyContent: 'space-between', padding: '12px 16px' }}>
                  <span>💳 <b>Demo Credits Ledger</b></span>
                  <span>→</span>
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Section: Recent Task Submissions */}
        <section className={styles.card}>
          <div className={styles.sectionHeading}>
            <div>
              <span className={styles.eyebrow}>AUDIT TRAILS</span>
              <h2>Recent Task Executions</h2>
            </div>
            <select
              className={styles.filterSelect}
              value={taskFilter}
              onChange={(e) => setTaskFilter(e.target.value)}
            >
              <option value="all">All Statuses ({tasks.length})</option>
              <option value="pending">Pending</option>
              <option value="allocated">Assigned</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          {!visibleTasks.length ? (
            <div className={styles.emptyState}>
              <p>No tasks found matching this criteria.</p>
            </div>
          ) : (
            <div className={styles.taskTable}>
              <div className={styles.taskTableHeader}>
                <span>Task ID</span>
                <span>Model Name</span>
                <span>Status</span>
                <span>Mode</span>
                <span>Created At</span>
                <span>Action</span>
              </div>
              {visibleTasks.map((task) => (
                <div className={styles.taskRow} key={task.task_id}>
                  <span className={styles.taskId}>{task.task_id.slice(0, 16)}…</span>
                  <span style={{ fontWeight: 600, color: '#f8fafc' }}>{task.model_name}</span>
                  <div>
                    <span className={`${styles.statusPill} ${styles[`status_${task.status}`] || ''}`}>
                      {task.status}
                    </span>
                  </div>
                  <span style={{ color: '#94a3b8' }}>{task.mode || 'WS-RR'}</span>
                  <span style={{ color: '#64748b' }}>{new Date(task.created_at).toLocaleTimeString()}</span>
                  <a href={`/history?task_id=${encodeURIComponent(task.task_id)}`} className={styles.actionButton}>
                    Inspect Details →
                  </a>
                </div>
              ))}
            </div>
          )}
        </section>

        <footer style={{ textAlign: 'center', color: '#64748b', fontSize: '12px', padding: '16px 0' }}>
          ComputeTorrent Platform · Multi-PC Volunteer LLM Infrastructure
        </footer>
      </main>
    </div>
  )
}
