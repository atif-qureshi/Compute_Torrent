import React, { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import AppLayout from '../components/AppLayout'
import StatusBadge from '../components/StatusBadge'
import { CapacitySummary, useData } from '../components/Data'
import { Empty, ErrorNotice, ResourceError, Section, Skeleton } from '../components/UI'
import { modelName, readyNode, request } from '../lib/portal'
import { initialRecipe, Recipe, validateRecipe } from '../lib/recipe'

export default function Studio() {
  const router = useRouter()
  const { catalog, nodes, providers, resources, refresh, jobs, loading } = useData()
  const [step, setStep] = useState(0)
  const [recipe, setRecipe] = useState<Recipe>(initialRecipe)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [source, setSource] = useState('')
  const titleRef = useRef<HTMLHeadingElement>(null)
  const restored = useRef('')

  const eligible = nodes.filter(n => readyNode(n, providers))
  const gateway = resources.capacity?.data?.status === 'ready'
  const unavailable = !!resources.nodes?.error || !!resources.capacity?.error || !resources.nodes?.updated || !resources.capacity?.updated
  const selected = catalog.find(m => m.model_id === recipe.model_id)

  useEffect(() => {
    if (catalog.length && !recipe.model_id) {
      const preferred = catalog.find(m => m.model_id.includes('bloomz')) || catalog[0]
      setRecipe(r => ({ ...r, model_id: preferred.model_id }))
    }
  }, [catalog, recipe.model_id])

  useEffect(() => {
    const id = typeof router.query.from === 'string' ? router.query.from : ''
    const old = jobs.find(j => j.id === id)
    if (old && restored.current !== id) {
      restored.current = id
      const s = old.spec || {}
      setRecipe({
        ...initialRecipe,
        ...(s.model_id != null ? { model_id: s.model_id } : {}),
        ...(s.revision != null ? { revision: s.revision } : {}),
        ...(s.prompt != null ? { prompt: s.prompt } : {}),
        ...(s.max_new_tokens != null ? { max_new_tokens: s.max_new_tokens } : {}),
        ...(s.min_peers != null ? { min_peers: s.min_peers } : {}),
        ...(s.max_peers != null ? { max_peers: s.max_peers } : {}),
      })
      setSource('Parameters copied from an earlier run. Review before submitting.')
    }
  }, [jobs, router.query.from])

  function update(k: keyof Recipe, v: any) {
    setRecipe(r => ({ ...r, [k]: v }))
    setError('')
  }

  function next() {
    setError('')
    if (step === 0 && !selected) {
      setError('Select a supported model first.')
      return
    }
    if (step === 1 && (unavailable || !gateway || eligible.length < recipe.min_peers)) {
      setError('The current gateway and provider requirements are not met. Refresh or connect eligible providers.')
      return
    }
    if (step === 2) {
      try {
        setRecipe(validateRecipe(recipe, catalog))
      } catch (e: any) {
        setError(e.message)
        return
      }
    }
    setStep(s => s + 1)
    setTimeout(() => titleRef.current?.focus(), 0)
  }

  async function submit() {
    setError('')
    if (unavailable || !gateway || eligible.length < recipe.min_peers) {
      setError('Provider availability changed. Check compatibility before submitting.')
      return
    }
    setBusy(true)
    try {
      const content = validateRecipe(recipe, catalog)
      const job = await request('/api/ct/distributed/jobs', {
        method: 'POST',
        body: JSON.stringify({ content, format: 'json' }),
      })
      if (!job.id) throw new Error('The coordinator did not return a run ID. Check deployments before retrying.')
      await refresh()
      router.push(`/deployments?id=${encodeURIComponent(job.id)}`)
    } catch (e: any) {
      setError(e.message)
      setBusy(false)
    }
  }

  const stepNames = ['Select model', 'Compatibility', 'Write prompt', 'Review']

  return (
    <AppLayout
      title="Model Studio"
      subtitle="Enter a plain-text prompt and run distributed inference across connected providers."
      actions={
        <Link className="button secondary" href="/deployments">
          View model runs →
        </Link>
      }
    >
      <ResourceError names={['catalog', 'nodes', 'capacity']} />
      <div className="grid-two">
        <section className="panel">
          <ol className="steps" aria-label="Run setup steps">
            {stepNames.map((s, i) => (
              <li key={s} className={step === i ? 'current' : ''} aria-current={step === i ? 'step' : undefined}>
                <span>{i < step ? '✓' : i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
          <div className="panel-body">
            <p className="eyebrow">STEP {step + 1} OF 4</p>
            <h2 ref={titleRef} tabIndex={-1} style={{ fontSize: 21, marginBottom: 10 }}>
              {['Choose your model', 'Check connected capacity', 'Enter plain-text prompt', 'Ready to submit?'][step]}
            </h2>
            <p style={{ fontSize: 12, marginBottom: 24 }}>
              {[
                'Only models supported by this coordinator are listed. Choose an instruction-tuned model for Q&A accuracy.',
                'These checks use the current coordinator snapshot. Exact model capacity and routes are measured after acceptance.',
                'Write your prompt directly in plain text—no JSON or XML formatting required.',
                'The coordinator will lock your submitted prompt, assign layer ranges, and stream output.',
              ][step]}
            </p>
            {source && <div className="selection-note">{source}</div>}
            <ErrorNotice error={error} />

            {step === 0 && (
              <>
                {!resources.catalog?.updated && loading ? (
                  <Skeleton />
                ) : !catalog.length ? (
                  <Empty title="Model catalog unavailable">Refresh the coordinator connection to select a supported model.</Empty>
                ) : (
                  <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
                    <legend className="sr-only">Supported models</legend>
                    {catalog.map(m => (
                      <label className="model-option" key={m.model_id}>
                        <input
                          type="radio"
                          name="model"
                          value={m.model_id}
                          checked={recipe.model_id === m.model_id}
                          onChange={() => update('model_id', m.model_id)}
                        />
                        <span>
                          <strong>{m.label || modelName(m.model_id)}</strong>
                          <small>{m.model_id}</small>
                          <small>{m.layers} transformer layers · Downloaded automatically by compute systems</small>
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}
              </>
            )}

            {step === 1 && (
              <>
                <div className="list-row">
                  <span>Model gateway</span>
                  <StatusBadge status={resources.capacity?.data?.status} />
                </div>
                <div className="list-row">
                  <span>Eligible connected providers</span>
                  <strong>
                    {unavailable ? 'Unknown' : eligible.length} / {recipe.min_peers} minimum
                  </strong>
                </div>
                <div className="list-row">
                  <span>Model</span>
                  <strong>{selected?.label || recipe.model_id}</strong>
                </div>
                <div className="selection-note" style={{ marginTop: 20 }}>
                  Preflight checks node readiness; the backend measures model-specific memory and throughput before selecting contiguous layer ranges.
                </div>
                {providers
                  .filter(p => !p.layer_ready)
                  .map(p => (
                    <div className="fact" key={p.node_id}>
                      <span className="mono">{p.node_id}</span>
                      <p>{p.layer_reason || 'Provider is not eligible.'}</p>
                    </div>
                  ))}
                <div className="inline-actions" style={{ marginTop: 20 }}>
                  <button className="button secondary" disabled={loading} onClick={refresh}>
                    Refresh capacity
                  </button>
                  <Link className="text-link" href="/nodes">
                    Manage providers →
                  </Link>
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <label className="field">
                  Prompt (plain text)
                  <textarea
                    required
                    maxLength={4000}
                    placeholder="Ask a clear question or give an instruction in plain English, e.g. What is the capital of US?"
                    value={recipe.prompt}
                    readOnly={busy}
                    disabled={busy}
                    onChange={e => update('prompt', e.target.value)}
                  />
                  <small>{recipe.prompt.length.toLocaleString()} / 4,000 characters</small>
                </label>
                <div className="form-grid">
                  <label className="field">
                    Maximum new tokens
                    <input
                      type="number"
                      min="1"
                      max="128"
                      value={recipe.max_new_tokens}
                      disabled={busy}
                      onChange={e => update('max_new_tokens', Number(e.target.value))}
                    />
                    <small>1–128 tokens</small>
                  </label>
                  <label className="field">
                    Model revision
                    <input
                      value={recipe.revision}
                      disabled={busy}
                      onChange={e => update('revision', e.target.value)}
                      spellCheck={false}
                    />
                    <small>main or an immutable 40-character commit SHA</small>
                  </label>
                  <label className="field">
                    Minimum providers
                    <input
                      type="number"
                      min="1"
                      max="8"
                      value={recipe.min_peers}
                      disabled={busy}
                      onChange={e => update('min_peers', Number(e.target.value))}
                    />
                  </label>
                  <label className="field">
                    Maximum providers
                    <input
                      type="number"
                      min="2"
                      max="8"
                      value={recipe.max_peers}
                      disabled={busy}
                      onChange={e => update('max_peers', Number(e.target.value))}
                    />
                  </label>
                </div>
                <label className="inline-actions">
                  <input
                    type="checkbox"
                    checked={recipe.benchmark}
                    disabled={busy}
                    onChange={e => update('benchmark', e.target.checked)}
                  />
                  Compare with a local CPU baseline <small>Measures baseline token-match accuracy &amp; speedup.</small>
                </label>
              </>
            )}

            {step === 3 && (
              <>
                <dl className="detail-grid">
                  {[
                    ['Model', recipe.model_id],
                    ['Revision', recipe.revision],
                    ['New tokens', recipe.max_new_tokens],
                    ['Providers', `${recipe.min_peers}–${recipe.max_peers}`],
                    ['Eligible now', unavailable ? 'Unknown' : eligible.length],
                    ['Baseline comparison', recipe.benchmark ? 'Enabled' : 'Disabled'],
                  ].map(([k, v]) => (
                    <div key={String(k)}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
                <div className="inline-actions" style={{ justifyContent: 'space-between', margin: '24px 0 10px' }}>
                  <h3>Your submitted prompt</h3>
                  <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Read-only once started
                  </span>
                </div>
                <div className="output" role="textbox" aria-readonly="true" style={{ cursor: 'default' }}>
                  {recipe.prompt}
                </div>
                <div className="selection-note" style={{ marginTop: 20 }}>
                  Providers may download model weights and process prompt activations. Use trusted computers. This creates a new run, not a permanent hosted endpoint.
                </div>
              </>
            )}

            <div className="form-actions">
              <button className="button secondary" disabled={step === 0 || busy} onClick={() => { setStep(step - 1); setError('') }}>
                Back
              </button>
              {step < 3 ? (
                <button className="button" disabled={busy || (step === 0 && !selected) || (step === 2 && !recipe.prompt.trim())} onClick={next}>
                  Continue →
                </button>
              ) : (
                <button className="button" disabled={busy || unavailable || !gateway || eligible.length < recipe.min_peers || !recipe.prompt.trim()} onClick={submit}>
                  {busy ? 'Submitting run…' : 'Start model run →'}
                </button>
              )}
            </div>
          </div>
        </section>

        <div>
          <Section title="Your compute pool" note="Current coordinator snapshot">
            <CapacitySummary />
          </Section>
          <Section title="What happens next">
            <ol className="instructions panel-body" style={{ margin: 0, paddingLeft: 42 }}>
              <li>
                <h3>Resolve the model</h3>
                <p>The coordinator pins the model revision from Hugging Face.</p>
              </li>
              <li>
                <h3>Measure and allocate</h3>
                <p>Available providers report capacity. The backend assigns contiguous layer ranges.</p>
              </li>
              <li>
                <h3>Prepare and generate</h3>
                <p>Providers start their layer runtimes. Tokens pass through the distributed model.</p>
              </li>
              <li>
                <h3>Inspect the result</h3>
                <p>Open live response streaming, throughput, accuracy, and diagnostics in Deployments.</p>
              </li>
            </ol>
          </Section>
          <Link className="text-link" href="/help#first-run">
            First run checklist →
          </Link>
        </div>
      </div>
    </AppLayout>
  )
}
