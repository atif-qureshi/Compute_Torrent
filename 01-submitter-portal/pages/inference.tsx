import Head from 'next/head'
import { useCallback, useEffect, useState } from 'react'
import PortalNav from '../components/PortalNav'
import styles from '../styles/Inference.module.css'

const sample = { model_id: 'bigscience/bloomz-560m', revision: 'main', prompt: 'Explain volunteer computing in one sentence.', max_new_tokens: 32, min_peers: 1, max_peers: 4, benchmark: false }
async function api(path: string, options?: RequestInit) {
  const response = await fetch(`/api/ct/distributed${path}`, options)
  const body = await response.json()
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  return body
}
const active = ['queued', 'resolving', 'loading', 'running', 'verifying', 'canary', 'benchmarking']

export default function Inference() {
  const [content, setContent] = useState('')
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
  const ready = providers.filter((p: any) => p.profile?.petals_enabled !== false && p.state !== 'paused' && p.state !== 'offline')
  const current = jobs.find(j => j.id === selected) || jobs[0]
  const running = jobs.some(j => active.includes(j.status))
  const submit = async () => {
    if (!content) {
      setError('Please upload a JSON or XML recipe file first.')
      return
    }
    setBusy(true); setError('')
    try {
      JSON.parse(content)
    } catch {
      setError('Uploaded content is not valid JSON.')
      setBusy(false)
      return
    }
    try {
      const job = await api('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content, format: 'json' }) })
      setSelected(job.id); await refresh()
    } catch (e: any) { setError(e.message) } finally { setBusy(false) }
  }
  const parseXmlToJson = (xmlText: string) => {
    const parser = new DOMParser()
    const xmlDoc = parser.parseFromString(xmlText, 'text/xml')
    const parseError = xmlDoc.getElementsByTagName('parsererror')
    if (parseError.length > 0) {
      throw new Error('Invalid XML document format')
    }
    const root = xmlDoc.documentElement
    const result: Record<string, any> = {}
    Array.from(root.children).forEach(child => {
      const tag = child.tagName
      const text = child.textContent?.trim() ?? ''
      if (text.toLowerCase() === 'true') result[tag] = true
      else if (text.toLowerCase() === 'false') result[tag] = false
      else if (!isNaN(Number(text)) && text !== '') result[tag] = Number(text)
      else result[tag] = text
    })
    if (!result.model_id) {
      result.model_id = root.getAttribute('model_id') || root.getAttribute('id') || ''
    }
    if (!result.model_id) {
      throw new Error('XML must contain a <model_id> tag')
    }
    return result
  }
  const upload = async (file?: File) => {
    if (!file) return
    if (file.size > 65536) { setError('Choose a file under 64 KiB.'); return }
    const isJson = /\.json$/i.test(file.name)
    const isXml = /\.xml$/i.test(file.name)
    if (!isJson && !isXml) {
      setError('Please upload a .json or .xml file.')
      return
    }
    try {
      const text = await file.text()
      let parsed: any
      if (isXml) {
        parsed = parseXmlToJson(text)
      } else {
        parsed = JSON.parse(text)
      }
      if (!parsed || typeof parsed !== 'object' || !parsed.model_id) {
        throw new Error('Uploaded file must include "model_id"')
      }
      setContent(JSON.stringify(parsed, null, 2))
      setError('')
    } catch (err: any) {
      setError(err.message || 'Uploaded file is not valid JSON or XML.')
    }
  }
  const download = (data: any, name: string) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url)
  }
  return <div className={styles.page}>
    <Head><title>Model Studio | ComputeTorrent</title><meta name="description" content="Run a small language model across your volunteer PCs." /></Head>
    <main className={styles.main}>
      <header className={styles.header}><div><span className={styles.kicker}>COMPUTETORRENT / MODEL STUDIO</span><h1>One model.<br /><em>Your connected computers.</em></h1><p>Upload a model recipe in JSON or XML. We prepare the weights, place its layers across your peers according to their capacity, and check the result.</p></div><PortalNav /></header>
      <section className={styles.stats} aria-label="Network overview">
        <div><span>LAYER PROVIDERS</span><strong>{ready.length}<small> / {providers.length} connected</small></strong></div>
        <div><span>GATEWAY</span><strong className={network.status === 'ready' ? styles.good : styles.warn}>{network.status}</strong></div>
        <div><span>MODEL SIZE</span><strong>Dynamic<small> · custom JSON model</small></strong></div>
      </section>
      {error && <div role="alert" className={styles.error}>{error}<button onClick={() => { setError(''); refresh() }}>Retry</button></div>}
      <div className={styles.grid}>
        <section className={styles.card}>
          <div className={styles.sectionTitle}><div><span className={styles.kicker}>01 / YOUR MODEL RECIPE</span><h2>Start an inference</h2></div><span className={styles.badge}>{content ? 'FILE LOADED (READ-ONLY)' : 'UPLOAD REQUIRED'}</span></div>
          <label className={styles.upload}>Drop in or browse your model recipe (.JSON or .XML)<input type="file" accept=".json,.xml,application/json,text/xml,application/xml" onChange={e => upload(e.target.files?.[0])} /><small>Upload JSON or XML metadata file. Model weights download automatically on compute PCs according to system capacity.</small></label>
          <div className={styles.tools}>
            <button onClick={() => setContent(JSON.stringify(sample, null, 2))}>Load example recipe</button>
            <button onClick={() => download(sample, 'model-recipe.json')}>Download JSON example</button>
            {content && <button onClick={() => setContent('')}>Clear / Remove file</button>}
          </div>
          {content && <>
            <label className={styles.editorLabel} htmlFor="recipe">Uploaded model details and prompt (Read-only)</label>
            <textarea id="recipe" className={styles.editor} spellCheck={false} value={content} readOnly={true} />
            <p className={styles.note}>Model recipe loaded. Weights download and split automatically across connected computers based on system capacity.</p>
          </>}
          <button className={styles.primary} disabled={busy || running || ready.length < 1 || !content} onClick={submit}>
            {busy ? 'Submitting…' : running ? 'A model job is already active' : !content ? 'Upload a JSON or XML recipe to start →' : ready.length < 1 ? 'No layer providers connected' : 'Prepare peers & run model →'}
          </button>
          <p className={styles.note}>Providers process prompt activations. Use trusted PCs. The coordinator caches weights for verification; nothing needs to be downloaded manually by the submitter. Pilot jobs have no credit charge or payout.</p>
        </section>
        <aside className={styles.card}>
          <span className={styles.kicker}>02 / CONNECTED CAPACITY</span><h2>Your layer providers</h2>
          {!providers.length && <div className={styles.empty}>No provider PCs connected.<p>Open the provider app on each PC, connect to this coordinator. Model layers will be assigned and downloaded automatically according to capacity.</p></div>}
          {providers.map((p: any) => {
            const isReady = p.profile?.petals_enabled !== false && p.state !== 'paused' && p.state !== 'offline'
            return <article className={styles.provider} key={p.node_id}><div className={styles.providerTitle}><strong>{p.profile?.cpu_model || p.node_id.slice(-12)}</strong><span className={styles.badge}>{p.state}</span></div><p>{p.profile?.os || 'OS unknown'} · {p.profile?.physical_cores || '—'} physical / {p.profile?.cpu_cores || '—'} logical cores</p><div className={styles.capacity}><span>RAM <b>{p.profile?.free_ram_gb ?? '—'} GB free</b></span><span>Limit <b>{p.profile?.memory_limit_gb ?? '—'} GB</b></span><span>VRAM <b>{((p.profile?.VRAM || 0) / 1024).toFixed(1)} GB</b></span><span>Disk <b>{p.profile?.disk_free_gb ?? '—'} GB free</b></span></div><p>{p.profile?.GPU || 'CPU provider'} · {p.profile?.petals_cuda_ready ? 'CUDA runtime ready' : 'CPU runtime'}</p><small className={isReady ? styles.good : styles.warn}>{!isReady ? 'Layer sharing disabled' : 'Layer sharing ready'}</small>{p.profile?.petals?.error && <p className={styles.warn}>{p.profile.petals.error}</p>}</article>
          })}
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
            {current.metrics && <p className={styles.note}>Generation: <b>{current.metrics.distributed_generation_seconds}s</b> for {current.metrics.generated_tokens} tokens across {current.metrics.provider_count} providers · Verification: <b>{current.metrics.verification_seconds}s</b> · Canary: <b>{current.metrics.canary_seconds}s</b> · Total runtime: <b>{current.metrics.total_seconds}s</b>{current.metrics.single_node_reference_seconds != null && <> · Single-node CPU baseline: <b>{current.metrics.single_node_reference_seconds}s</b> for {current.metrics.single_node_reference_tokens} tokens</>}</p>}
            {current.receipt && <div className={styles.verification}><h3>Computation checks</h3><p>Generated tokens: <b>{current.receipt.verification.token_match ? 'match trusted replay' : 'mismatch'}</b></p><p>Every generated stage boundary: <b>{current.receipt.verification.passed ? 'passed' : 'failed'}</b> · Hidden canary: <b>{current.receipt.canary.passed ? 'passed' : 'failed'}</b></p><p className={styles.note}>The local coordinator replays the complete generated sequence and checks every provider boundary. The receipt includes a post-commit challenge and the canary result. This is an off-chain research check with a trusted coordinator.</p><button onClick={() => download(current, `${current.id}-receipt.json`)}>Download result & audit receipt</button></div>}
            {active.includes(current.status) && <button onClick={async () => { try { await api(`/jobs/${current.id}`, { method: 'DELETE' }); await refresh() } catch (e: any) { setError(e.message) } }}>Stop this run</button>}
          </article>}
        </div>}
      </section>
      <footer className={styles.note}>ComputeTorrent · Local volunteer inference · Model weights stay cached on compute systems for later runs.</footer>
    </main>
  </div>
}
