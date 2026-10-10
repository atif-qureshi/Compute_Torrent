import { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import styles from '../styles/Home.module.css'
import PortalNav from '../components/PortalNav'

const API = '/api/ct'
const ACCOUNT = 'web-portal'

export default function Home() {
  const [models, setModels] = useState<any[]>([])
  const [tasks, setTasks] = useState<any[]>([])
  const [seeders, setSeeders] = useState<any[]>([])
  const [credits, setCredits] = useState<any>(null)
  const [network, setNetwork] = useState<any>(null)
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

  const refresh = useCallback(async () => {
    try {
      const [modelsRes, tasksRes, seedersRes, creditsRes] = await Promise.all([
        fetch(`${API}/models`),
        fetch(`${API}/tasks?limit=12&submitter_id=${ACCOUNT}`),
        fetch(`${API}/seeders`),
        fetch(`${API}/credits?submitter_id=${ACCOUNT}`),
      ])
      for (const response of [modelsRes, tasksRes, seedersRes, creditsRes]) {
        if (!response.ok) throw new Error(`Coordinator returned ${response.status}`)
      }
      const [modelData, taskData, seederData, creditData] = await Promise.all([
        modelsRes.json(), tasksRes.json(), seedersRes.json(), creditsRes.json(),
      ])
      fetch(`${API}/network`).then((response) => response.ok ? response.json() : null).then(setNetwork).catch(() => setNetwork(null))
      setModels(modelData)
      setModelName((current) => current || modelData[0]?.name || '')
      setTasks(taskData)
      setSeeders(seederData)
      setCredits(creditData)
      setErrorMessage('')
    } catch (error: any) {
      setErrorMessage(error.message || 'Coordinator is unavailable')
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  const submitTask = async (event: any) => {
    event.preventDefault()
    setErrorMessage('')
    setStatus('submitting')
    const prompts = prompt.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
    const payload: any = {
      model_name: modelName,
      submitter_id: ACCOUNT,
      max_tokens: maxTokens,
      mode,
      min_ram_gb: minRam,
      require_cuda: requireCuda,
      ...(batchMode ? { prompts } : { prompt: prompt.trim() }),
    }
    try {
      const response = await fetch(`${API}/tasks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Task submission failed')
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
    const response = await fetch(`${API}/seeders/${encodeURIComponent(nodeId)}/credential`, { method: 'DELETE' })
    const result = await response.json()
    if (!response.ok) setErrorMessage(result.detail || 'Could not revoke provider')
    else await refresh()
  }

  const onlineSeeders = seeders.filter((node) => ['online', 'idle', 'busy'].includes(node.state || node.status)).length
  const visibleTasks = taskFilter === 'all' ? tasks : tasks.filter((task) => task.status === taskFilter)

  return <div className={styles.container}>
    <Head><title>ComputeTorrent | Distributed AI Compute</title><meta name="description" content="Submit verified AI jobs to a volunteer compute network." /></Head>
    <main className={styles.main}>
      <header className={styles.header}>
        <div><div className={styles.eyebrow}>VOLUNTEER COMPUTE NETWORK</div><h1 className={styles.title}>ComputeTorrent</h1>
          <p className={styles.description}>Send independent AI jobs to connected worker PCs. Track execution, verification, and credits from one place.</p></div>
        <PortalNav />
      </header>

      <section className={styles.statsGrid} aria-label="Network overview">
        <div className={styles.statCard}><span>WORKERS ONLINE</span><strong>{onlineSeeders}</strong><small>Connected provider PCs</small></div>
        <div className={styles.statCard}><span>ACTIVE TASKS</span><strong>{tasks.filter((task) => ['pending', 'allocated', 'running'].includes(task.status)).length}</strong><small>Waiting or processing</small></div>
        <div className={styles.statCard}><span>COMPLETED</span><strong>{tasks.filter((task) => task.status === 'completed').length}</strong><small>Verified jobs in recent history</small></div>
        <div className={styles.statCard}><span>AVAILABLE CREDITS</span><strong>{credits?.balance ?? '—'}</strong><small>1 credit per submitted task</small></div>
      </section>

      {errorMessage && <div className={styles.error} role="alert">{errorMessage} <button type="button" onClick={refresh}>Retry</button></div>}
      {status === 'submitted' && <div className={styles.success}>Task queued: <code>{taskId}</code> <a href="/history">View progress →</a></div>}

      <div className={styles.workspaceGrid}>
        <section className={styles.card}>
          <div className={styles.sectionHeading}><div><div className={styles.eyebrow}>NEW WORKLOAD</div><h2>Submit AI task</h2></div><span className={styles.liveBadge}>● Network ready</span></div>
          {models.length === 0 ? <div className={styles.emptyState}><strong>No model is available yet</strong><p>The network operator needs to register a GGUF model and start at least one provider.</p></div> :
            <form onSubmit={submitTask} className={styles.form}>
              <div className={styles.twoColumns}>
                <div className={styles.formGroup}><label htmlFor="model">Inference model</label><select id="model" value={modelName} onChange={(e) => setModelName(e.target.value)} className={styles.select}>
                  {models.map((model) => <option key={model.name} value={model.name}>{model.label}</option>)}</select></div>
                <div className={styles.formGroup}><label htmlFor="mode">Scheduling strategy</label><select id="mode" value={mode} onChange={(e) => setMode(e.target.value)} className={styles.select}>
                  <option value="WS-RR">WS-RR · balance work across workers</option><option value="CC-BP">CC-BP · prefer higher capacity</option></select></div>
              </div>
              <div className={styles.formGroup}><div className={styles.labelRow}><label htmlFor="prompt">Prompt</label><label className={styles.checkboxLabel}><input type="checkbox" checked={batchMode} onChange={(e) => setBatchMode(e.target.checked)} /> Each line is a separate job</label></div>
                <textarea id="prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={batchMode ? 'One independent prompt per line' : 'Describe the work you want the model to do…'} rows={7} className={styles.textarea} required /></div>
              <div className={styles.twoColumns}>
                <div className={styles.formGroup}><label htmlFor="tokens">Maximum output · {maxTokens} tokens</label><input id="tokens" className={styles.range} type="range" min="32" max="2048" step="32" value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} /></div>
                <div className={styles.formGroup}><label htmlFor="ram">Minimum worker RAM · {minRam ? `${minRam} GB` : 'Any available'}</label><input id="ram" className={styles.range} type="range" min="0" max="64" step="4" value={minRam} onChange={(e) => setMinRam(Number(e.target.value))} /></div>
              </div>
              <label className={styles.checkboxLabel}><input type="checkbox" checked={requireCuda} onChange={(e) => setRequireCuda(e.target.checked)} /> Only assign to CUDA-capable workers</label>
              <button type="submit" disabled={status === 'submitting'} className={styles.button}>{status === 'submitting' ? 'Submitting…' : `Submit ${batchMode ? `${Math.max(1, prompt.split(/\r?\n/).filter((line) => line.trim()).length)} jobs` : 'task'} · 1 credit`}</button>
            </form>}
        </section>

        <aside className={styles.sideColumn}>
          <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>PROVIDER NETWORK</div><h2>Connected systems</h2></div><span className={styles.liveBadge} data-offline={Boolean(errorMessage)}>{errorMessage ? '● Reconnecting' : '● Live'}</span></div>
            {seeders.length === 0 ? <p className={styles.muted}>No workers have joined yet. Install the provider app on your computers and share the network join code.</p> : <div className={styles.workerList}>{seeders.slice(0, 8).map((node) => <div className={styles.workerRow} key={node.node_id}>
              <span className={styles.workerDot} data-state={node.state || node.status} /><div className={styles.workerInfo}><strong>{node.node_id}</strong><small>{node.profile?.GPU || `${node.profile?.cpu_cores || '—'} CPU cores`} · {node.profile?.RAM || '—'} GB RAM</small></div><span className={styles.workerState}>{node.state || node.status}</span><button className={styles.revokeButton} type="button" onClick={() => revokeProvider(node.node_id)}>Revoke</button>
            </div>)}</div>}
          </section>
          <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>VERIFICATION</div><h2>Trust by design</h2></div></div>
            <ul className={styles.featureList}><li>Payload and model hash checks</li><li>Independent replica execution</li><li>Hidden model-canary spot checks</li><li>VeriLLM-inspired Merkle output receipts</li></ul>
            <p className={styles.muted}>libp2p LAN relay: {network?.connected_peer_count ?? '…'} connected peer(s)</p>
            <a className={styles.textLink} href="/history">Review completed results →</a>
          </section>
        </aside>
      </div>

      <section className={styles.card}><div className={styles.sectionHeading}><div><div className={styles.eyebrow}>RECENT ACTIVITY</div><h2>Your tasks</h2></div><select aria-label="Filter tasks" value={taskFilter} onChange={(e) => setTaskFilter(e.target.value)} className={styles.filterSelect}><option value="all">All statuses</option><option value="pending">Pending</option><option value="allocated">Assigned</option><option value="running">Running</option><option value="completed">Completed</option><option value="failed">Failed</option></select></div>
        {visibleTasks.length === 0 ? <p className={styles.muted}>No tasks match this view yet.</p> : <div className={styles.taskTable}>{visibleTasks.map((task) => <a href="/history" className={styles.taskRow} key={task.task_id}><span className={styles.taskId}>{task.task_id}</span><span>{task.model_name}</span><span className={`${styles.statusPill} ${styles[`status_${task.status}`] || ''}`}>{task.status}</span><span>{task.mode || 'WS-RR'}</span><span>{new Date(task.created_at).toLocaleString()}</span><span>Details →</span></a>)}</div>}
      </section>
      <footer className={styles.footer}>ComputeTorrent coordinates volunteer machines. Inference runs in a network-isolated container on each provider.</footer>
    </main>
  </div>
}
