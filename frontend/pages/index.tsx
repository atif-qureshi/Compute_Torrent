import { useCallback, useEffect, useMemo, useState } from 'react'
import Head from 'next/head'
import styles from '../styles/Home.module.css'
import PortalNav from '../components/PortalNav'

const API = '/api/ct'
const ACCOUNT = 'web-portal'
const MAX_PROMPTS = 500
const MAX_PROMPT_CHARS = 20_000

async function responseJson(response: Response) {
  let body: any = {}
  try { body = await response.json() } catch { /* The coordinator may return an empty error response. */ }
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
  const [models, setModels] = useState<any[]>([])
  const [tasks, setTasks] = useState<any[]>([])
  const [seeders, setSeeders] = useState<any[]>([])
  const [credits, setCredits] = useState<any>(null)
  const [network, setNetwork] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [modelName, setModelName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [batchMode, setBatchMode] = useState(false)
  const [mode, setMode] = useState('WS-RR')
  const [maxTokens, setMaxTokens] = useState(256)
  const [minRam, setMinRam] = useState(0)
  const [requireCuda, setRequireCuda] = useState(false)
  const [taskFilter, setTaskFilter] = useState('all')
  const [status, setStatus] = useState('idle')
  const [taskId, setTaskId] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [lastUpdated, setLastUpdated] = useState('')
  const [providerAddress, setProviderAddress] = useState('ws://127.0.0.1:8001/ws/seeder')
  const [copiedAddress, setCopiedAddress] = useState(false)

  useEffect(() => {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    setProviderAddress(`${scheme}://${window.location.hostname}:8001/ws/seeder`)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [modelsRes, tasksRes, seedersRes, creditsRes] = await Promise.all([
        fetch(`${API}/models`),
        fetch(`${API}/tasks?limit=12&submitter_id=${ACCOUNT}`),
        fetch(`${API}/seeders`),
        fetch(`${API}/credits?submitter_id=${ACCOUNT}`),
      ])
      const [modelData, taskData, seederData, creditData] = await Promise.all([
        responseJson(modelsRes), responseJson(tasksRes), responseJson(seedersRes), responseJson(creditsRes),
      ])
      const [healthResult, networkResult] = await Promise.allSettled([
        fetch(`${API}/health`).then(responseJson),
        fetch(`${API}/network`).then(responseJson),
      ])
      setHealth(healthResult.status === 'fulfilled' ? healthResult.value : { status: 'unavailable' })
      setNetwork(networkResult.status === 'fulfilled' ? networkResult.value : { status: 'unavailable', connected_peer_count: 0 })
      setModels(modelData)
      setModelName((current) => current || modelData[0]?.name || '')
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

  const promptItems = useMemo(() => batchMode
    ? prompt.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
    : (prompt.trim() ? [prompt.trim()] : []), [batchMode, prompt])
  const promptIssue = useMemo(() => {
    if (promptItems.some((item) => item.length > MAX_PROMPT_CHARS)) return `Each prompt must be ${MAX_PROMPT_CHARS.toLocaleString()} characters or fewer.`
    if (promptItems.length > MAX_PROMPTS) return `A batch can contain at most ${MAX_PROMPTS} prompts.`
    return ''
  }, [promptItems])

  const onlineSeeders = seeders.filter((node) => ['online', 'idle', 'busy'].includes(node.state || node.status))
  const eligibleSeeders = onlineSeeders.filter((node) => {
    const profile = node.profile || {}
    return profile.docker_ok !== false && (!requireCuda || profile.CUDA) && Number(profile.RAM || 0) >= minRam
  })
  const visibleTasks = taskFilter === 'all' ? tasks : tasks.filter((task) => task.status === taskFilter)
  const coordinatorOnline = health?.status === 'healthy'
  const sortedSeeders = [...seeders].sort((left, right) => {
    const leftOnline = ['online', 'idle', 'busy'].includes(left.state || left.status) ? 1 : 0
    const rightOnline = ['online', 'idle', 'busy'].includes(right.state || right.status) ? 1 : 0
    return rightOnline - leftOnline
  })

  const submitTask = async (event: any) => {
    event.preventDefault()
    setErrorMessage('')
    if (!coordinatorOnline) { setErrorMessage('The local coordinator is not ready yet. Retry after the service is online.'); return }
    if (!modelName || promptIssue || promptItems.length === 0) return
    setStatus('submitting')
    const payload: any = {
      model_name: modelName,
      submitter_id: ACCOUNT,
      max_tokens: maxTokens,
      mode,
      min_ram_gb: minRam,
      require_cuda: requireCuda,
      ...(batchMode ? { prompts: promptItems } : { prompt: promptItems[0] }),
    }
    try {
      const result = await responseJson(await fetch(`${API}/tasks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      }))
      setTaskId(result.task_id)
      setStatus('submitted')
      setPrompt('')
      await refresh()
    } catch (error: any) {
      setErrorMessage(error.message || 'Could not submit this task')
      setStatus('error')
    }
  }

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

  const submitDisabled = !coordinatorOnline || !modelName || promptItems.length === 0 || Boolean(promptIssue) || status === 'submitting'
  const connectionLabel = coordinatorOnline ? 'Coordinator online' : health === null ? 'Checking coordinator…' : 'Coordinator offline'

  return <div className={styles.container}>
    <Head><title>ComputeTorrent | Volunteer Compute</title><meta name="description" content="Submit local AI work to a trusted volunteer-computing network." /></Head>
    <main className={styles.main}>
      <header className={styles.header}>
        <div><div className={styles.eyebrow}>LOCAL VOLUNTEER COMPUTE</div><h1 className={styles.title}>ComputeTorrent</h1>
          <p className={styles.description}>Submit independent AI jobs to connected worker PCs. Follow execution, verification, results, and demo credits from one local workspace.</p></div>
        <PortalNav />
      </header>

      <section className={styles.statsGrid} aria-label="Network overview">
        <div className={styles.statCard}><span>WORKERS ONLINE</span><strong>{onlineSeeders.length}</strong><small>Connected provider PCs</small></div>
        <div className={styles.statCard}><span>RECENT ACTIVE TASKS</span><strong>{tasks.filter((task) => ['pending', 'allocated', 'running'].includes(task.status)).length}</strong><small>Waiting or processing in recent activity</small></div>
        <div className={styles.statCard}><span>RECENTLY COMPLETED</span><strong>{tasks.filter((task) => task.status === 'completed').length}</strong><small>Verified jobs in recent activity</small></div>
        <div className={styles.statCard}><span>AVAILABLE CREDITS</span><strong>{credits?.balance ?? '—'}</strong><small>1 demo credit per submitted task</small></div>
      </section>

      {errorMessage && <div className={styles.error} role="alert">{errorMessage} <button type="button" onClick={refresh}>Retry</button></div>}
      {status === 'submitted' && <div className={styles.success} role="status">Task queued: <code>{taskId}</code> <a href="/history">View progress →</a></div>}

      <div className={styles.workspaceGrid}>
        <section className={styles.card}>
          <div className={styles.sectionHeading}><div><div className={styles.eyebrow}>NEW WORKLOAD</div><h2>Submit AI task</h2></div><span className={styles.liveBadge} data-offline={!coordinatorOnline}>{connectionLabel}</span></div>
          {!coordinatorOnline && <div className={styles.emptyState}><strong>Coordinator is not ready</strong><p>Keep the local Compose stack running, then retry. You can still configure provider PCs while models are being prepared.</p><button type="button" className={styles.buttonSecondary} onClick={refresh}>Check again</button></div>}
          {coordinatorOnline && models.length === 0 ? <div className={styles.emptyState}><strong>No model is available yet</strong><p>Register an operator-approved GGUF model with the local coordinator. Model weights are not bundled with ComputeTorrent.</p></div> : coordinatorOnline &&
            <form onSubmit={submitTask} className={styles.form}>
              <div className={styles.twoColumns}>
                <div className={styles.formGroup}><label htmlFor="model">Inference model</label><select id="model" value={modelName} onChange={(e) => setModelName(e.target.value)} className={styles.select}>
                  {models.map((model) => <option key={model.name} value={model.name}>{model.label || model.name}</option>)}</select></div>
                <div className={styles.formGroup}><label htmlFor="mode">Scheduling strategy</label><select id="mode" value={mode} onChange={(e) => setMode(e.target.value)} className={styles.select}>
                  <option value="WS-RR">WS-RR · balance work across workers</option><option value="CC-BP">CC-BP · prefer higher capacity</option></select></div>
              </div>
              <div className={styles.formGroup}><div className={styles.labelRow}><label htmlFor="prompt">Prompt</label><label className={styles.checkboxLabel}><input type="checkbox" checked={batchMode} onChange={(e) => { setBatchMode(e.target.checked); setStatus('idle') }} /> One independent prompt per line</label></div>
                <textarea id="prompt" value={prompt} onChange={(e) => { setPrompt(e.target.value); setStatus('idle') }} placeholder={batchMode ? 'One independent prompt per line (blank lines are ignored)' : 'Describe the work you want the model to do…'} rows={7} className={styles.textarea} required />
                <small className={styles.formHint}>{batchMode ? `${promptItems.length} of ${MAX_PROMPTS} prompts · ${promptItems.length} independent chunks` : `${promptItems[0]?.length || 0} of ${MAX_PROMPT_CHARS.toLocaleString()} characters`}{promptIssue ? ` · ${promptIssue}` : ''}</small>
              </div>
              <div className={styles.twoColumns}>
                <div className={styles.formGroup}><label htmlFor="tokens">Maximum output · {maxTokens} tokens</label><input id="tokens" className={styles.range} type="range" min="32" max="2048" step="32" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /></div>
                <div className={styles.formGroup}><label htmlFor="ram">Minimum worker RAM · {minRam ? `${minRam} GB` : 'Any available'}</label><input id="ram" className={styles.range} type="range" min="0" max="64" step="4" value={minRam} onChange={(e) => setMinRam(Number(e.target.value))} /></div>
              </div>
              <label className={styles.checkboxLabel}><input type="checkbox" checked={requireCuda} onChange={(e) => setRequireCuda(e.target.checked)} /> Only assign to CUDA-capable workers</label>
              <p className={styles.formHint}>{eligibleSeeders.length} currently connected worker(s) meet these hardware filters. Jobs can remain queued while matching PCs reconnect.</p>
              <div className={styles.privacyNote}><strong>Before submitting:</strong> prompts are sent to assigned volunteer PCs for inference. Do not include passwords, personal records, or other sensitive data. One batch submission costs 1 demo credit, regardless of its prompt count.</div>
              <button type="submit" disabled={submitDisabled} className={styles.button}>{status === 'submitting' ? 'Submitting…' : `Submit ${batchMode ? `${promptItems.length || 0} prompts` : 'task'} · 1 demo credit`}</button>
            </form>}
        </section>

        <aside className={styles.sideColumn}>
          <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>VOLUNTEER NETWORK</div><h2>Connect worker PCs</h2></div><span className={styles.liveBadge} data-offline={!coordinatorOnline}>{onlineSeeders.length} online</span></div>
            <p className={styles.muted}>Install the provider app on each trusted computer. On the coordinator PC use localhost; on another PC, replace the hostname with the coordinator’s private LAN IP.</p>
            <div className={styles.networkAddress}><code>{providerAddress}</code><button type="button" className={styles.buttonSecondary} onClick={copyProviderAddress}>{copiedAddress ? 'Copied' : 'Copy address'}</button></div>
            <ol className={styles.setupSteps}><li>Keep this coordinator and its local stack running.</li><li>Enter the address above in the provider app.</li><li>Enter the join code configured as <code>COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN</code> in the coordinator’s local <code>.env</code>.</li><li>For another PC, allow ports 8001 and 9100 only on the trusted LAN. Do not expose them to the public internet.</li></ol>
            {seeders.length === 0 ? <p className={styles.muted}>No provider PCs are enrolled yet.</p> : <div className={styles.workerList}>{sortedSeeders.slice(0, 8).map((node) => {
              const state = node.status === 'revoked' ? 'revoked' : (node.state || node.status || 'offline')
              const profile = node.profile || {}
              return <div className={styles.workerRow} key={node.node_id}>
                <span className={styles.workerDot} data-state={state} /><div className={styles.workerInfo}><strong>{node.node_id}</strong><small>{profile.GPU || `${profile.cpu_cores || '—'} CPU cores`} · {profile.RAM ?? '—'} GB RAM · {timeAgo(node.last_heartbeat)}</small></div><span className={styles.workerState}>{state}</span><button className={styles.revokeButton} type="button" onClick={() => revokeProvider(node.node_id)} disabled={state === 'revoked'}>Revoke</button>
              </div>
            })}</div>}
            <a className={styles.textLink} href="/history">Open task history →</a>
          </section>
          <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>IMPLEMENTATION STATUS</div><h2>What runs today</h2></div></div>
            <ul className={styles.featureList}><li>WebTorrent file transfer with SHA-256 checks</li><li>Replica agreement and operator-supplied output-hash canaries (MVP checks)</li><li>VeriLLM-inspired transcript commitments (limited audit record)</li></ul>
            <p className={styles.muted}>libp2p currently supports LAN discovery and relay connectivity; it does not carry model or prompt files yet. Trackerless libp2p data transfer and the full VeriLLM/canary architecture remain future work.</p>
            <p className={styles.muted}>Connected libp2p peers: {network?.status === 'unavailable' ? 'unavailable' : (network?.connected_peer_count ?? 'checking…')}. Last portal refresh: {lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : 'checking…'}.</p>
          </section>
        </aside>
      </div>

      <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>RECENT ACTIVITY</div><h2>Your tasks</h2></div><select aria-label="Filter tasks" value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)} className={styles.filterSelect}><option value="all">All statuses</option><option value="pending">Pending</option><option value="allocated">Assigned</option><option value="running">Running</option><option value="completed">Completed</option><option value="failed">Failed</option></select></div>
        {visibleTasks.length === 0 ? <p className={styles.muted}>No tasks match this view yet.</p> : <div className={styles.taskTable}>{visibleTasks.map((task) => <a href={`/history?task_id=${encodeURIComponent(task.task_id)}`} className={styles.taskRow} key={task.task_id}><span className={styles.taskId}>{task.task_id}</span><span>{task.model_name}</span><span className={`${styles.statusPill} ${styles[`status_${task.status}`] || ''}`}>{task.status}</span><span>{task.mode || 'WS-RR'}</span><span>{new Date(task.created_at).toLocaleString()}</span><span>Details →</span></a>)}</div>}
      </section>
      <footer className={styles.footer}>Local-first volunteer compute. Inference runs in a network-isolated container on each provider; demo credits have no cash value.</footer>
    </main>
  </div>
}
