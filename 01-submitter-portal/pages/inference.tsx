import Head from 'next/head'
import { useCallback, useEffect, useState } from 'react'
import PortalNav from '../components/PortalNav'
import styles from '../styles/Inference.module.css'

const sample = {
  model_id: 'bigscience/bloomz-560m',
  revision: 'main',
  prompt: 'Explain volunteer computing in one sentence.',
  max_new_tokens: 32,
  min_peers: 2,
  max_peers: 4,
  benchmark: false
}

async function api(path: string, options?: RequestInit) {
  const response = await fetch(`/api/ct/distributed${path}`, options)
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  return body
}

const active = ['queued', 'resolving', 'loading', 'running', 'verifying', 'canary', 'benchmarking']

export default function Inference() {
  const [content, setContent] = useState('')
  const [format, setFormat] = useState<'json' | 'xml'>('json')
  const [jobs, setJobs] = useState<any[]>([])
  const [network, setNetwork] = useState<any>({ providers: [], status: 'checking' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState('')
  const [copiedResult, setCopiedResult] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const refresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const [state, history] = await Promise.all([api('/status'), api('/jobs')])
      setNetwork(state)
      setJobs(history)
    } catch (e: any) {
      setError(e.message || 'Coordinator unavailable')
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 4000)
    return () => clearInterval(timer)
  }, [refresh])

  const providers = network.providers || []
  const ready = providers.filter((p: any) => p.layer_ready)
  const current = jobs.find(j => j.id === selected) || jobs[0]
  const running = jobs.some(j => active.includes(j.status))

  const submit = async () => {
    if (!content) {
      setError('Please upload a JSON or XML recipe file first.')
      return
    }
    setBusy(true)
    setError('')
    if (format === 'json') {
      try {
        JSON.parse(content)
      } catch {
        setError('Uploaded content is not valid JSON.')
        setBusy(false)
        return
      }
    }
    try {
      const job = await api('/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, format })
      })
      setSelected(job.id)
      await refresh()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const upload = async (file?: File) => {
    if (!file) return
    if (file.size > 65536) {
      setError('Choose a file under 64 KiB.')
      return
    }
    const isJson = /\.json$/i.test(file.name)
    const isXml = /\.xml$/i.test(file.name)
    if (!isJson && !isXml) {
      setError('Please upload a .json or .xml file.')
      return
    }
    try {
      const text = await file.text()
      if (isXml) {
        const parsed = new DOMParser().parseFromString(text, 'text/xml')
        if (parsed.getElementsByTagName('parsererror').length || parsed.documentElement.tagName !== 'inference') {
          throw new Error('XML must have a valid <inference> root')
        }
        setContent(text)
        setFormat('xml')
      } else {
        const parsed = JSON.parse(text)
        if (!parsed || typeof parsed !== 'object' || !parsed.model_id) {
          throw new Error('JSON recipe must include model_id')
        }
        setContent(text)
        setFormat('json')
      }
      setError('')
    } catch (err: any) {
      setError(err.message || 'Uploaded file is not valid JSON or XML.')
    }
  }

  const download = (data: any, name: string) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    URL.revokeObjectURL(url)
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedResult(true)
    setTimeout(() => setCopiedResult(false), 2000)
  }

  return (
    <div className={styles.page}>
      <Head>
        <title>Model Studio | ComputeTorrent</title>
        <meta name="description" content="Distributed AI inference platform with dynamic layer placement across volunteer PCs." />
      </Head>

      <main className={styles.main}>
        <PortalNav />

        {/* Hero Section */}
        <header className={styles.header}>
          <div>
            <span className={styles.kicker}>COMPUTETORRENT / MODEL STUDIO</span>
            <h1>
              Distributed AI Inference.<br />
              <em>Powered by your peer network.</em>
            </h1>
            <p>
              Upload a JSON or XML model recipe. Transformer layers are partitioned dynamically across connected volunteer PCs based on available RAM, VRAM, and CPU capacity.
            </p>
          </div>
          <button
            onClick={refresh}
            className={styles.toolButton}
            title="Refresh network status and jobs"
          >
            <span>{isRefreshing ? '🔄 Refreshing…' : '🔄 Refresh Data'}</span>
          </button>
        </header>

        {/* Multi-Accent Network Metric Widgets */}
        <section className={styles.stats} aria-label="Network overview">
          <div className={`${styles.statWidget} ${styles.statWidgetEmerald}`}>
            <span>Active Layer Providers</span>
            <strong>{ready.length} <small>/ {providers.length} connected</small></strong>
            <small>{ready.length >= 2 ? '✨ Minimum 2 peers ready for layer slicing' : '⚠️ Connect at least 2 providers'}</small>
          </div>

          <div className={`${styles.statWidget} ${styles.statWidgetViolet}`}>
            <span>Petals DHT Gateway</span>
            <strong>{network.status?.toUpperCase() || 'OFFLINE'}</strong>
            <small>{network.status === 'ready' ? '🌐 DHT overlay initialized & ready' : 'Connecting to local gateway…'}</small>
          </div>

          <div className={`${styles.statWidget} ${styles.statWidgetCyan}`}>
            <span>Supported Model Architectures</span>
            <strong>BLOOM / BLOOMZ</strong>
            <small>Generic HuggingFace config loader enabled</small>
          </div>
        </section>

        {error && (
          <div role="alert" className={styles.errorBox}>
            <span>⚠️ {error}</span>
            <button className={styles.toolButton} onClick={() => { setError(''); refresh() }}>Dismiss</button>
          </div>
        )}

        {/* 2-Column Studio Grid */}
        <div className={styles.grid}>
          {/* Left Column: Recipe & Submission */}
          <section className={styles.card}>
            <div className={styles.sectionTitle}>
              <div>
                <span className={styles.kicker}>STEP 01</span>
                <h2>Upload Model Recipe</h2>
              </div>
              <span className={`${styles.badge} ${content ? styles.badgeLoaded : styles.badgePending}`}>
                {content ? `FILE LOADED (${format.toUpperCase()})` : 'FILE REQUIRED'}
              </span>
            </div>

            <label className={styles.uploadZone}>
              <span className={styles.uploadIcon}>📁</span>
              <span className={styles.uploadTitle}>
                {content ? 'Click to replace recipe file' : 'Drop or browse .JSON / .XML recipe'}
              </span>
              <input
                type="file"
                accept=".json,.xml,application/json,text/xml,application/xml"
                onChange={e => upload(e.target.files?.[0])}
              />
              <span className={styles.uploadSub}>
                Upload a JSON or XML recipe specifying model ID, prompt, and peer limits. Providers will stream layer weights directly.
              </span>
            </label>

            <div className={styles.tools}>
              <button
                type="button"
                className={styles.toolButton}
                onClick={() => { setContent(JSON.stringify(sample, null, 2)); setFormat('json') }}
              >
                📋 Load Example Recipe
              </button>
              <button
                type="button"
                className={styles.toolButton}
                onClick={() => download(sample, 'model-recipe.json')}
              >
                💾 Download Sample JSON
              </button>
              {content && (
                <button
                  type="button"
                  className={`${styles.toolButton} ${styles.toolButtonClear}`}
                  onClick={() => setContent('')}
                >
                  🗑️ Remove File
                </button>
              )}
            </div>

            {content && (
              <div className={styles.editorContainer}>
                <div className={styles.editorHeader}>
                  <label className={styles.editorLabel} htmlFor="recipe">
                    {format.toUpperCase()} Recipe Content (Read-Only)
                  </label>
                  <button
                    type="button"
                    className={styles.toolButton}
                    onClick={() => copyToClipboard(content)}
                  >
                    {copiedResult ? '✅ Copied' : '📄 Copy'}
                  </button>
                </div>
                <textarea
                  id="recipe"
                  className={styles.editor}
                  spellCheck={false}
                  value={content}
                  readOnly={true}
                />
              </div>
            )}

            <button
              className={styles.primaryButton}
              disabled={busy || running || ready.length < 2 || network.status !== 'ready' || !content}
              onClick={submit}
            >
              {busy
                ? '⏳ Partitioning Layers & Submitting…'
                : running
                ? '⚡ A Model Inference is Currently Active'
                : !content
                ? 'Upload Recipe to Begin →'
                : network.status !== 'ready'
                ? 'Petals Gateway Not Ready'
                : ready.length < 2
                ? 'Needs At Least 2 Ready Providers'
                : '🚀 Prepare Peers & Run Distributed Model →'}
            </button>

            <p className={styles.note}>
              Contiguous layer ranges are assigned across connected providers automatically according to their available memory.
            </p>
          </section>

          {/* Right Column: Connected Providers */}
          <aside className={styles.card}>
            <div className={styles.sectionTitle}>
              <div>
                <span className={styles.kicker}>STEP 02</span>
                <h2>Connected Providers</h2>
              </div>
              <span className={styles.badge}>
                {ready.length} Active / {providers.length} Total
              </span>
            </div>

            {!providers.length ? (
              <div className={styles.emptyState}>
                <p>No provider computers connected right now.</p>
                <small style={{ color: '#64748b', display: 'block', marginTop: '8px' }}>
                  Launch the provider desktop app on your client PCs, connect to the coordinator LAN address, and tick "Share model layers".
                </small>
              </div>
            ) : (
              <div className={styles.providerList}>
                {providers.map((p: any) => {
                  const isReady = p.layer_ready
                  return (
                    <article className={styles.providerCard} key={p.node_id}>
                      <div className={styles.providerHeader}>
                        <div>
                          <strong className={styles.providerTitle}>
                            {p.profile?.cpu_model || p.node_id.slice(-12)}
                          </strong>
                          <div className={styles.providerMeta}>
                            {p.profile?.physical_cores || '—'} Cores · {p.profile?.GPU || 'CPU Provider'}
                          </div>
                        </div>
                        <span className={`${styles.badge} ${p.state === 'busy' ? styles.badgePending : styles.badgeLoaded}`}>
                          {p.state}
                        </span>
                      </div>

                      <div className={styles.capacityGrid}>
                        <div className={styles.capacityItem}>
                          <span className={styles.capacityLabel}>Free RAM</span>
                          <span className={styles.capacityVal}>{p.profile?.free_ram_gb ?? '—'} GB</span>
                        </div>
                        <div className={styles.capacityItem}>
                          <span className={styles.capacityLabel}>Memory Cap</span>
                          <span className={styles.capacityVal}>{p.profile?.memory_limit_gb ?? '—'} GB</span>
                        </div>
                        <div className={styles.capacityItem}>
                          <span className={styles.capacityLabel}>VRAM</span>
                          <span className={styles.capacityVal}>{((p.profile?.VRAM || 0) / 1024).toFixed(1)} GB</span>
                        </div>
                        <div className={styles.capacityItem}>
                          <span className={styles.capacityLabel}>Free Disk</span>
                          <span className={styles.capacityVal}>{p.profile?.disk_free_gb ?? '—'} GB</span>
                        </div>
                      </div>

                      <div className={styles.providerHeader}>
                        <span className={`${styles.statusIndicator} ${isReady ? styles.statusReady : styles.statusWarn}`}>
                          {p.layer_reason || '🟢 Ready for Layer Serving'}
                        </span>
                        <small style={{ color: '#64748b', fontSize: '10px' }}>
                          {p.runtime_installed ? 'Docker Runtime Ready' : 'Runtime Pending'}
                        </small>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
            <a href="/" className={styles.toolButton} style={{ alignSelf: 'flex-start' }}>
              ⚙️ Manage Connections & Node Tokens →
            </a>
          </aside>
        </div>

        {/* Section 03: Execution & Verification */}
        <section className={styles.card}>
          <div className={styles.sectionTitle}>
            <div>
              <span className={styles.kicker}>STEP 03</span>
              <h2>Model Execution Pipeline</h2>
            </div>
            <button onClick={refresh} className={styles.toolButton}>
              🔄 Refresh Runs
            </button>
          </div>

          {!jobs.length ? (
            <div className={styles.emptyState}>
              <p>Your first distributed model run will appear here with layer distribution and verification receipt.</p>
            </div>
          ) : (
            <div className={styles.historyLayout}>
              {/* Job Picker */}
              <div className={styles.jobList}>
                {jobs.map(j => (
                  <button
                    key={j.id}
                    className={`${styles.jobItem} ${current?.id === j.id ? styles.jobItemActive : ''}`}
                    onClick={() => setSelected(j.id)}
                  >
                    <span className={styles.jobModelName}>{j.spec.model_id.split('/').pop()}</span>
                    <span style={{ fontSize: '11px', color: '#38bdf8', textTransform: 'capitalize' }}>
                      Status: {j.status}
                    </span>
                    <span className={styles.jobTime}>{new Date(j.created_at * 1000).toLocaleTimeString()}</span>
                  </button>
                ))}
              </div>

              {/* Active / Selected Job Details */}
              {current && (
                <article style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div className={styles.sectionTitle}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: '18px', color: '#f8fafc' }}>{current.spec.model_id}</h3>
                      <code style={{ fontSize: '11px', color: '#64748b' }}>Job ID: {current.id}</code>
                    </div>
                    <span className={`${styles.badge} ${current.status === 'completed' ? styles.badgeLoaded : styles.badgePending}`}>
                      {current.status}
                    </span>
                  </div>

                  {/* Partitioned Layer Stages Visualization */}
                  <div>
                    <span className={styles.kicker}>LAYER PARTITIONING SCHEME</span>
                    <div className={styles.pipelineFlow}>
                      {(current.plan || []).map((stage: any, i: number) => (
                        <div key={stage.node_id} className={styles.stageCard}>
                          <span className={styles.stageNumber}>PEER {i + 1} · {stage.device?.toUpperCase()}</span>
                          <span className={styles.stageLayers}>Layers {stage.start}–{stage.end - 1}</span>
                          <span className={styles.stageNode}>{stage.node_id.slice(-12)}</span>
                          <span style={{ fontSize: '10px', color: current.stage_status?.[stage.node_id]?.status === 'serving' ? '#34d399' : '#fbbf24' }}>
                            {current.stage_status?.[stage.node_id]?.status || 'Allocated'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {current.error && (
                    <div className={styles.errorBox}>
                      <span>❌ {current.error}</span>
                    </div>
                  )}

                  {/* Inference Result Output */}
                  {current.result && (
                    <div>
                      <div className={styles.sectionTitle}>
                        <h3 style={{ margin: 0, fontSize: '15px' }}>
                          {current.status === 'completed' ? '✅ Verified Model Output' : 'Unverified Generation Output'}
                        </h3>
                        <button
                          className={styles.toolButton}
                          onClick={() => copyToClipboard(current.result)}
                        >
                          {copiedResult ? '✅ Copied' : '📄 Copy Result'}
                        </button>
                      </div>
                      <pre className={styles.resultBox}>{current.result}</pre>
                    </div>
                  )}

                  {/* Metrics */}
                  {current.metrics && (
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                      <span className={styles.capacityItem}>
                        <span className={styles.capacityLabel}>Distributed Run</span>
                        <span className={styles.capacityVal}>{current.metrics.distributed_generation_seconds}s</span>
                      </span>
                      <span className={styles.capacityItem}>
                        <span className={styles.capacityLabel}>Tokens</span>
                        <span className={styles.capacityVal}>{current.metrics.generated_tokens} tokens</span>
                      </span>
                      <span className={styles.capacityItem}>
                        <span className={styles.capacityLabel}>Providers</span>
                        <span className={styles.capacityVal}>{current.metrics.provider_count} peers</span>
                      </span>
                      <span className={styles.capacityItem}>
                        <span className={styles.capacityLabel}>Verification</span>
                        <span className={styles.capacityVal}>{current.metrics.verification_seconds}s</span>
                      </span>
                    </div>
                  )}

                  {/* Verification Receipt */}
                  {current.receipt && (
                    <div className={styles.verificationReceipt}>
                      <h3>🛡️ VeriLLM Consensus & Audit Receipt</h3>
                      <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1' }}>
                        Replay Match: <b>{current.receipt.verification.token_match ? '✅ Passed (100% Token Consensus)' : '❌ Mismatch'}</b> ·
                        Canary Test: <b>{current.receipt.canary.passed ? '✅ Passed' : '❌ Failed'}</b>
                      </p>
                      <button
                        className={styles.toolButton}
                        style={{ alignSelf: 'flex-start' }}
                        onClick={() => download(current, `${current.id}-receipt.json`)}
                      >
                        💾 Download Complete Audit Receipt (.json)
                      </button>
                    </div>
                  )}

                  {active.includes(current.status) && (
                    <button
                      className={`${styles.toolButton} ${styles.toolButtonClear}`}
                      style={{ alignSelf: 'flex-start' }}
                      onClick={async () => {
                        try {
                          await api(`/jobs/${current.id}`, { method: 'DELETE' })
                          await refresh()
                        } catch (e: any) {
                          setError(e.message)
                        }
                      }}
                    >
                      🛑 Terminate Job Run
                    </button>
                  )}
                </article>
              )}
            </div>
          )}
        </section>

        <footer style={{ textAlign: 'center', color: '#64748b', fontSize: '12px', padding: '16px 0' }}>
          ComputeTorrent · Distributed AI Inference Platform · Peer weights cached on client Docker runtimes.
        </footer>
      </main>
    </div>
  )
}
