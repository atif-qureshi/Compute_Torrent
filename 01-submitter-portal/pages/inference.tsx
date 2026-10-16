import Head from 'next/head'
import { useCallback, useEffect, useState } from 'react'
import PortalNav from '../components/PortalNav'
import styles from '../styles/Inference.module.css'

const sample = { model_id: 'bigscience/bloomz-560m', revision: 'main', prompt: 'Explain volunteer computing in one sentence.', max_new_tokens: 32, min_peers: 2 }
const xml = '<inference>\n  <model_id>bigscience/bloomz-560m</model_id>\n  <revision>main</revision>\n  <prompt>Explain volunteer computing in one sentence.</prompt>\n  <max_new_tokens>32</max_new_tokens>\n  <min_peers>2</min_peers>\n</inference>'
async function api(path: string, options?: RequestInit) {
  const response = await fetch(`/api/ct/distributed${path}`, options)
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  return body
}
const active = ['queued', 'resolving', 'loading', 'running', 'verifying', 'canary']

export default function Inference() {
  const [content, setContent] = useState(JSON.stringify(sample, null, 2))
  const [format, setFormat] = useState('json')
  const [jobs, setJobs] = useState<any[]>([])
  const [network, setNetwork] = useState<any>({ providers: [], status: 'checking' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState('')
  const refresh = useCallback(async () => {
    try {
      const [state, history] = await Promise.all([api('/status'), api('/jobs')])
      setNetwork(state); setJobs(history)
    } catch (e: any) { setError(e.message || 'Coordinator unavailable') }
  }, [])
  useEffect(() => { refresh(); const timer = setInterval(refresh, 4000); return () => clearInterval(timer) }, [refresh])
  const providers = network.providers || []
  const ready = providers.filter((p: any) => p.profile?.petals_enabled && p.profile?.petals_image_ready && p.state !== 'paused')
  const current = jobs.find(j => j.id === selected) || jobs[0]
  const running = jobs.some(j => active.includes(j.status))
  const submit = async () => {
    setBusy(true); setError('')
    try {
      const job = await api('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, format }) })
      setSelected(job.id); await refresh()
    } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }
  const upload = async (file?: File) => {
    if (!file) return
    if (file.size > 65536 || !/\.(json|xml)$/i.test(file.name)) { setError('Choose a JSON or XML file under 64 KiB.'); return }
    setFormat(file.name.toLowerCase().endsWith('.xml') ? 'xml' : 'json')
    setContent(await file.text()); setError('')
  }
  const download = (data: any, name: string) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url)
  }
  return <div className={styles.page}>
    <Head><title>Model Studio | ComputeTorrent</title><meta name="description" content="Run a small language model across your volunteer PCs." /></Head>
    <main className={styles.main}>
      <header className={styles.header}><div><span className={styles.kicker}>COMPUTETORRENT / MODEL STUDIO</span><h1>One model.<br /><em>Your connected computers.</em></h1><p>Upload a model recipe. We prepare the weights, place its layers across your peers, and check the result.</p></div><PortalNav /></header>
      <section className={styles.stats} aria-label="Network overview">
        <div><span>LAYER PROVIDERS</span><strong>{ready.length}<small> / {providers.length} connected</small></strong></div>
        <div><span>GATEWAY</span><strong className={network.status === 'ready' ? styles.good : styles.warn}>{network.status}</strong></div>
        <div><span>MODEL SIZE</span><strong>560M<small> parameters · small-model pilot</small></strong></div>
      </section>
      {error && <div role="alert" className={styles.error}>{error}<button onClick={() => { setError(''); refresh() }}>Retry</button></div>}
      <div className={styles.grid}>
        <section className={styles.card}>
          <div className={styles.sectionTitle}><div><span className={styles.kicker}>01 / YOUR MODEL RECIPE</span><h2>Start an inference</h2></div><span className={styles.badge}>JSON / XML</span></div>
          <label className={styles.upload}>Drop in your model details<input type="file" accept=".json,.xml,application/json,application/xml,text/xml" onChange={e => upload(e.target.files?.[0])} /><small>Up to 64 KiB. Upload metadata only; model weights download automatically on the compute PCs.</small></label>
          <div className={styles.tools}><label>Format <select value={format} onChange={e => setFormat(e.target.value)}><option value="json">JSON</option><option value="xml">XML</option></select></label><button onClick={() => setContent(format === 'json' ? JSON.stringify(sample, null, 2) : xml)}>Load example</button><button onClick={() => download(sample, 'model-recipe.json')}>Download JSON example</button></div>
          <label className={styles.editorLabel} htmlFor="recipe">Model details and prompt</label>
          <textarea id="recipe" className={styles.editor} spellCheck={false} value={content} onChange={e => setContent(e.target.value)} />
          <p className={styles.note}>Available: BLOOM 560M and BLOOMZ 560M. Revision <code>main</code> resolves to a fixed commit before download. At least two layer providers are required. Up to 128 output tokens.</p>
          <button className={styles.primary} disabled={busy || running || network.status !== 'ready' || ready.length < 2} onClick={submit}>{busy ? 'Submitting…' : running ? 'A model job is already active' : 'Prepare peers & run model →'}</button>
          <p className={styles.note}>Providers process prompt activations. Use trusted PCs. The coordinator caches weights for verification; nothing needs to be downloaded manually by the submitter. Pilot jobs have no credit charge or payout.</p>
        </section>
        <aside className={styles.card}>
          <span className={styles.kicker}>02 / CONNECTED CAPACITY</span><h2>Your layer providers</h2>
          {!providers.length && <div className={styles.empty}>No provider PCs connected.<p>Open the updated provider app on each PC, connect to this coordinator and enable “Share model layers”. Import the Petals runtime image first.</p></div>}
          {providers.map((p: any) => <article className={styles.provider} key={p.node_id}><div className={styles.providerTitle}><strong>{p.profile?.cpu_model || p.node_id.slice(-12)}</strong><span className={styles.badge}>{p.state}</span></div><p>{p.profile?.os || 'OS unknown'} · {p.profile?.physical_cores || '—'} physical / {p.profile?.cpu_cores || '—'} logical cores</p><div className={styles.capacity}><span>RAM <b>{p.profile?.free_ram_gb ?? '—'} GB free</b></span><span>Limit <b>{p.profile?.memory_limit_gb ?? '—'} GB</b></span><span>VRAM <b>{((p.profile?.VRAM || 0) / 1024).toFixed(1)} GB</b></span><span>Disk <b>{p.profile?.disk_free_gb ?? '—'} GB free</b></span></div><p>{p.profile?.GPU || 'CPU provider'} · {p.profile?.petals_cuda_ready ? 'CUDA runtime ready' : 'CPU runtime'}</p><small className={p.profile?.petals_image_ready && p.profile?.petals_enabled ? styles.good : styles.warn}>{!p.profile?.petals_enabled ? 'Layer sharing disabled' : p.profile?.petals_image_ready ? 'Petals runtime installed' : 'Petals image needed'}</small>{p.profile?.petals?.error && <p className={styles.warn}>{p.profile.petals.error}</p>}</article>)}
          <a className={styles.link} href="/">Manage connections & enrollment →</a>
        </aside>
      </div>
      <section className={styles.card}>
        <div className={styles.sectionTitle}><div><span className={styles.kicker}>03 / EXECUTION & VERIFICATION</span><h2>Model runs</h2></div><button onClick={refresh}>Refresh</button></div>
        {!jobs.length ? <div className={styles.empty}>Your first model run will appear here with its assigned layers, output and verification receipt.</div> : <div className={styles.history}>
          <div className={styles.jobList}>{jobs.map(j => <button key={j.id} aria-pressed={current?.id === j.id} onClick={() => setSelected(j.id)}><strong>{j.spec.model_id.split('/')[1]}</strong><span>{j.status}</span><small>{new Date(j.created_at * 1000).toLocaleString()}</small></button>)}</div>
          {current && <article className={styles.jobDetail}><div className={styles.sectionTitle}><div><h3>{current.spec.model_id}</h3><code>{current.id}</code></div><span className={styles.badge}>{current.status}</span></div>
            <div className={styles.pipeline}>{(current.plan || []).map((stage: any, i: number) => <div key={stage.node_id}><span>PEER {i + 1} · {stage.device}</span><strong>Layers {stage.start}–{stage.end - 1}</strong><small>{stage.node_id.slice(-12)}</small></div>)}</div>
            <p className={styles.note}>Each token passes through these ranges in order. All providers host their assigned layers concurrently.</p>
            {current.error && <p className={styles.error}>{current.error}</p>}
            {current.result && <><h3>{current.status === 'completed' ? 'Verified result' : 'Unverified output'}</h3><pre className={styles.result}>{current.result}</pre></>}
            {current.receipt && <div className={styles.verification}><h3>Computation checks</h3><p>Generated tokens: <b>{current.receipt.verification.token_match ? 'match trusted replay' : 'mismatch'}</b></p><p>Sampled stage boundaries: <b>{current.receipt.verification.passed ? 'passed' : 'failed'}</b> · Canary: <b>{current.receipt.canary.passed ? 'passed' : 'failed'}</b></p><p className={styles.note}>Local verification inspired by VeriLLM: actual activation commitments, post-commit samples and trusted recomputation. This is not the full on-chain VeriLLM protocol.</p><button onClick={() => download(current, `${current.id}-receipt.json`)}>Download result & audit receipt</button></div>}
            {active.includes(current.status) && <button onClick={async () => { try { await api(`/jobs/${current.id}`, { method: 'DELETE' }); await refresh() } catch (e: any) { setError(e.message) } }}>Stop this run</button>}
          </article>}
        </div>}
      </section>
      <footer className={styles.note}>ComputeTorrent · Local volunteer inference · Model weights stay cached on compute systems for later runs.</footer>
    </main>
  </div>
}
