import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import StatusBadge from './StatusBadge'
import Modal from './Modal'
import { CopyButton, Empty, ErrorNotice } from './UI'
import { array, useData } from './Data'
import { dateText, exportFile, isActive, modelName, number, request, seconds, statusLabel } from '../lib/portal'

export default function RunDetail({ job }: { job: any }) {
  const router = useRouter()
  const [tab, setTab] = useState('Overview')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [interactivePrompt, setInteractivePrompt] = useState('')
  const [submittingPrompt, setSubmittingPrompt] = useState(false)
  const { refresh } = useData()

  useEffect(() => {
    setTab('Overview')
    setError('')
    setConfirm(false)
    setInteractivePrompt('')
  }, [job.id])

  const plan = array(job.plan)

  async function cancel() {
    setBusy(true)
    setError('')
    try {
      await request(`/api/ct/distributed/jobs/${encodeURIComponent(job.id)}`, { method: 'DELETE' })
      setConfirm(false)
      await refresh()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitInteractivePrompt() {
    if (!interactivePrompt.trim()) return
    setSubmittingPrompt(true)
    setError('')
    try {
      const spec = { ...job.spec, prompt: interactivePrompt.trim() }
      const res = await request('/api/ct/distributed/jobs', {
        method: 'POST',
        body: JSON.stringify({ content: spec, format: 'json' }),
      })
      if (!res.id) throw new Error('The coordinator did not return a run ID. Check deployments.')
      await refresh()
      router.push(`/deployments?id=${encodeURIComponent(res.id)}`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmittingPrompt(false)
    }
  }

  // Calculate or retrieve metrics
  const generatedTokens = job.metrics?.generated_tokens
  const genSec = job.metrics?.distributed_generation_seconds
  const throughput = job.metrics?.throughput_tokens_per_sec
    ? `${job.metrics.throughput_tokens_per_sec} tokens/sec`
    : generatedTokens && genSec
    ? `${(generatedTokens / genSec).toFixed(2)} tokens/sec`
    : 'Not reported'
  const latencyPerToken = job.metrics?.latency_per_token_ms
    ? `${job.metrics.latency_per_token_ms} ms/tok`
    : generatedTokens && genSec
    ? `${((genSec / generatedTokens) * 1000).toFixed(1)} ms/tok`
    : 'Not reported'

  const fields = [
    ['Model', job.spec?.model_id],
    ['Run ID', job.id],
    ['Created', dateText(job.created_at)],
    ['Last update', dateText(job.updated_at)],
    ['Revision', job.spec?.revision],
    ['Runtime lifecycle', 'Per-run session; resources released after completion'],
  ]

  return (
    <>
      <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <StatusBadge status={job.status} />
        <div className="inline-actions">
          <Link className="button small secondary" href={`/inference?from=${encodeURIComponent(job.id)}`}>
            Run again
          </Link>
          <button className="button small secondary" onClick={() => exportFile(`run-${job.id}.json`, job)}>
            Export run
          </button>
          {isActive(job.status) && (
            <button className="button small danger" onClick={() => setConfirm(true)}>
              Cancel run
            </button>
          )}
        </div>
      </div>

      <ErrorNotice error={error} />
      {job.error && <ErrorNotice error={job.error} />}

      <div className="tabs" role="tablist" aria-label="Run details">
        {['Overview', 'Nodes & layers', 'Playground', 'Metrics', 'Logs', 'Settings'].map(t => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            id={`run-tab-${t}`}
            aria-controls="run-panel"
            onClick={() => setTab(t)}
            onKeyDown={e => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                e.preventDefault()
                const tabs = Array.from(e.currentTarget.parentElement!.querySelectorAll('button'))
                const next = tabs[(tabs.indexOf(e.currentTarget) + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]
                next.focus()
                next.click()
              }
            }}
          >
            {t}
          </button>
        ))}
      </div>

      <div id="run-panel" role="tabpanel" aria-labelledby={`run-tab-${tab}`} tabIndex={0}>
        {tab === 'Overview' && (
          <>
            <dl className="detail-grid">
              {fields.map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{v || 'Not reported'}</dd>
                </div>
              ))}
            </dl>
            <ol className="timeline">
              <li>
                <strong>Run created</strong>
                <p>{dateText(job.created_at)}</p>
              </li>
              <li>
                <strong>{statusLabel(job.status)}</strong>
                <p>{dateText(job.updated_at)} · Current recorded state</p>
              </li>
            </ol>
            <h3 style={{ marginBottom: 12 }}>Model response</h3>
            {job.result ? (
              <div className="output">{typeof job.result === 'string' ? job.result : JSON.stringify(job.result, null, 2)}</div>
            ) : (
              <p>{isActive(job.status) ? 'The response will appear when generation completes.' : 'No response was returned for this run.'}</p>
            )}
          </>
        )}

        {tab === 'Nodes & layers' && (
          <>
            {plan.length ? (
              <>
                <p className="muted">
                  Tokens pass through these contiguous ranges in order. Range sizes reflect the backend allocation, not an equal visual split.
                </p>
                <div className="layer-bar" aria-label="Assigned layer proportions">
                  {plan.map((p, i) => (
                    <span key={p.node_id} style={{ flex: p.end - p.start }} title={`Provider ${i + 1}: ${p.end - p.start} layers`}>
                      {p.end - p.start}
                    </span>
                  ))}
                </div>
                <div className="grid-equal">
                  {plan.map((p, i) => (
                    <div className="node-stage" key={p.node_id}>
                      <small>PROVIDER {i + 1} · {p.device || 'Unknown device'}</small>
                      <h3>Layers {p.start}–{p.end - 1}</h3>
                      <p className="mono">{p.node_id}</p>
                      <div style={{ marginTop: 12 }}>
                        <StatusBadge status={job.stage_status?.[p.node_id]?.status} />
                      </div>
                      <dl className="fact">
                        <dt>Allocation basis</dt>
                        <dd>{p.allocation_basis || 'Not reported'}</dd>
                      </dl>
                      <dl className="fact">
                        <dt>Measured layer capacity</dt>
                        <dd>{number(p.capacity_layers)}</dd>
                      </dl>
                      <dl className="fact">
                        <dt>Route</dt>
                        <dd>{p.transport?.mode || job.stage_status?.[p.node_id]?.transport?.mode || 'Not reported'}</dd>
                      </dl>
                      {job.stage_status?.[p.node_id]?.error && <ErrorNotice error={job.stage_status[p.node_id].error} />}
                      <Link className="text-link" href={`/nodes?id=${encodeURIComponent(p.node_id)}`}>
                        Inspect provider →
                      </Link>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <Empty title="No layer assignment recorded">Capacity measurement and assignment occur after a run is accepted.</Empty>
            )}
          </>
        )}

        {tab === 'Playground' && (
          <>
            <label className="field">
              Submitted prompt
              <textarea readOnly value={job.spec?.prompt || ''} />
            </label>
            {job.result && (
              <div className="output">
                {typeof job.result === 'string' ? job.result : JSON.stringify(job.result)}
              </div>
            )}

            <div style={{ marginTop: 24, padding: '16px', background: 'var(--panel-subtle, rgba(255,255,255,0.03))', borderRadius: '8px', border: '1px solid var(--border)' }}>
              <h3 style={{ fontSize: 16, marginBottom: 8 }}>Send another prompt</h3>
              <p style={{ fontSize: 12, marginBottom: 12, color: 'var(--muted)' }}>
                Provide a prompt in simple text format to run with the same model configuration.
              </p>
              <label className="field" style={{ marginBottom: 12 }}>
                <textarea
                  placeholder="Type your prompt here in simple text..."
                  value={interactivePrompt}
                  onChange={e => setInteractivePrompt(e.target.value)}
                  rows={4}
                  style={{ width: '100%' }}
                />
              </label>
              <div className="inline-actions" style={{ gap: 10 }}>
                <button
                  className="button"
                  disabled={submittingPrompt || !interactivePrompt.trim()}
                  onClick={submitInteractivePrompt}
                >
                  {submittingPrompt ? 'Submitting run…' : 'Run prompt →'}
                </button>
                <Link className="button secondary" href={`/inference?from=${encodeURIComponent(job.id)}`}>
                  Adjust model & peers in Studio
                </Link>
              </div>
            </div>
          </>
        )}

        {tab === 'Metrics' && (
          <>
            <dl className="detail-grid">
              {[
                ['Providers', job.metrics?.provider_count ?? (plan.length || undefined)],
                ['Generated tokens', job.metrics?.generated_tokens],
                ['Throughput', throughput],
                ['Latency per token', latencyPerToken],
                ['Time to first token (TTFT)', job.metrics?.prefill_latency_seconds ? `${job.metrics.prefill_latency_seconds}s` : 'Not reported'],
                ['Model preparation', seconds(job.metrics?.model_load_seconds)],
                ['Generation time', seconds(job.metrics?.distributed_generation_seconds)],
                ['Total time', seconds(job.metrics?.total_seconds)],
              ].map(([label, v]) => (
                <div key={String(label)}>
                  <dt>{label}</dt>
                  <dd>{typeof v === 'number' ? number(v) : v || 'Not reported'}</dd>
                </div>
              ))}
            </dl>
            <p style={{ marginTop: 22, fontSize: 12 }}>
              Measured coordinator and distributed generation metrics.
            </p>
          </>
        )}

        {tab === 'Logs' && (
          <>
            <p style={{ marginBottom: 16 }}>Saved diagnostics and current provider stages. A full streamed container log is not exposed by this API.</p>
            {job.error && <pre className="log">{job.error}</pre>}
            {plan.map(p => (
              <details key={p.node_id} className="fact">
                <summary className="mono">{p.node_id} · {statusLabel(job.stage_status?.[p.node_id]?.status)}</summary>
                <pre className="log">
                  {JSON.stringify(
                    {
                      status: statusLabel(job.stage_status?.[p.node_id]?.status),
                      error: job.stage_status?.[p.node_id]?.error,
                      transport: job.stage_status?.[p.node_id]?.transport,
                    },
                    null,
                    2
                  )}
                </pre>
              </details>
            ))}
            {!job.error && !plan.length && <p>No diagnostics recorded yet.</p>}
          </>
        )}

        {tab === 'Settings' && (
          <>
            <p style={{ marginBottom: 20 }}>Submitted configuration is read-only. Run again to change it.</p>
            <pre className="log">{JSON.stringify(job.spec || {}, null, 2)}</pre>
            <CopyButton value={JSON.stringify(job.spec || {}, null, 2)} label="Copy recipe" />
          </>
        )}
      </div>

      <Modal isOpen={confirm} onClose={() => !busy && setConfirm(false)} title="Cancel this run?" maxWidth="460px">
        <p>The coordinator will stop the active session and ask its providers to release the assigned layers. This run cannot be resumed.</p>
        <div className="form-actions">
          <button className="button secondary" disabled={busy} onClick={() => setConfirm(false)}>
            Keep running
          </button>
          <button className="button danger" disabled={busy} onClick={cancel}>
            {busy ? 'Cancelling…' : 'Cancel run'}
          </button>
        </div>
      </Modal>
    </>
  )
}
