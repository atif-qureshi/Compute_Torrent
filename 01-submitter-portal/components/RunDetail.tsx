import React, { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/router'
import StatusBadge from './StatusBadge'
import Modal from './Modal'
import { Empty, ErrorNotice } from './UI'
import { array, useData } from './Data'
import { dateText, exportFile, isActive, number, request, seconds, statusLabel } from '../lib/portal'

function formatBytes(bytes?: number | null) {
  if (bytes == null || bytes < 0) return '—'
  if (bytes === 0) return '0 B'
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

function formatSpeed(bps?: number | null) {
  if (!bps || bps <= 0) return '—'
  if (bps >= 1024 * 1024) return `${(bps / (1024 * 1024)).toFixed(2)} MB/s`
  return `${(bps / 1024).toFixed(0)} KB/s`
}

function routeText(stage: any, stageState: any) {
  const raw = stage?.transport ?? stageState?.transport
  if (!raw) return 'Not reported'
  return typeof raw === 'string' ? raw : raw.mode || 'Not reported'
}

export default function RunDetail({ job }: { job: any }) {
  const router = useRouter()
  const [tab, setTab] = useState('Overview')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [interactivePrompt, setInteractivePrompt] = useState('')
  const [submittingPrompt, setSubmittingPrompt] = useState(false)
  const [liveJob, setLiveJob] = useState<any>(null)
  const { refresh } = useData()

  useEffect(() => {
    setTab('Overview')
    setError('')
    setConfirm(false)
    setInteractivePrompt('')
    setLiveJob(null)
  }, [job.id])

  const current = liveJob && liveJob.id === job.id ? liveJob : job
  const active = isActive(current.status)

  useEffect(() => {
    if (!job?.id || !isActive(current?.status)) return
    let stopped = false
    let wasActive = true
    const pollJob = async () => {
      try {
        const latest = await request(`/api/ct/distributed/jobs/${encodeURIComponent(job.id)}`)
        if (stopped || !latest || latest.id !== job.id) return
        setLiveJob(latest)
        if (wasActive && !isActive(latest.status)) {
          wasActive = false
          void refresh()
        }
      } catch {
        // Keep parent polling alive if single-job poll transiently fails
      }
    }
    const timer = setInterval(pollJob, 2000)
    void pollJob()
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [job?.id, current?.status, refresh])

  const plan = array(current.plan)
  const m = current.metrics || {}
  const stageStatus = current.stage_status || {}
  const coordinatorStage = stageStatus.coordinator || {}
  const displayOutput = current.result ?? current.partial_result ?? ''
  const isStreaming = !current.result && Boolean(current.partial_result)

  const generatedTokens = m.generated_tokens
  const maxNewTokens = m.max_new_tokens ?? current.spec?.max_new_tokens
  const genSec = m.distributed_generation_seconds
  const capacityValues = Object.values((current.capacity_measurements || {}) as Record<string, any>)
  const computedCapacity = capacityValues.length
    ? Number(capacityValues.reduce((sum, item) => sum + Number(item?.inference_rps || 0), 0).toFixed(2))
    : null
  const capacityTotalRps =
    m.capacity_inference_rps_total != null
      ? Number(m.capacity_inference_rps_total)
      : computedCapacity && computedCapacity > 0
      ? computedCapacity
      : null
  const throughput =
    m.throughput_tokens_per_sec != null
      ? `${m.throughput_tokens_per_sec} tok/s`
      : generatedTokens && genSec
      ? `${(generatedTokens / genSec).toFixed(2)} tok/s`
      : active
      ? 'Measuring during decode…'
      : 'Not reported'
  const latencyPerToken =
    m.latency_per_token_ms != null
      ? `${m.latency_per_token_ms} ms/tok`
      : generatedTokens && genSec
      ? `${((genSec / generatedTokens) * 1000).toFixed(1)} ms/tok`
      : active
      ? 'Measuring during decode…'
      : 'Not reported'

  const rpcByNode = useMemo(() => {
    const timings: any[] = Array.isArray(m.stage_rpc_timings) ? m.stage_rpc_timings : []
    const map: Record<
      string,
      { node_id: string; blocks: number; prefillMs: number | null; avgDecodeMs: number | null; decodeCount: number }
    > = {}
    const acc: Record<string, { blocks: number; prefill: number[]; decode: number[] }> = {}
    for (const item of timings) {
      if (!item?.node_id) continue
      const row = (acc[item.node_id] ||= { blocks: Number(item.blocks || 0), prefill: [], decode: [] })
      if (item.phase === 'prefill') row.prefill.push(Number(item.seconds || 0))
      else row.decode.push(Number(item.seconds || 0))
    }
    for (const [nodeId, row] of Object.entries(acc)) {
      map[nodeId] = {
        node_id: nodeId,
        blocks: row.blocks,
        prefillMs: row.prefill.length ? Math.round((row.prefill.reduce((a, b) => a + b, 0) / row.prefill.length) * 1000) : null,
        avgDecodeMs: row.decode.length ? Math.round((row.decode.reduce((a, b) => a + b, 0) / row.decode.length) * 1000) : null,
        decodeCount: row.decode.length,
      }
    }
    return map
  }, [m.stage_rpc_timings])

  async function cancel() {
    setBusy(true)
    setError('')
    try {
      await request(`/api/ct/distributed/jobs/${encodeURIComponent(current.id)}`, { method: 'DELETE' })
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
      const s = current.spec || {}
      const spec = {
        model_id: s.model_id,
        revision: s.revision || 'main',
        prompt: interactivePrompt.trim(),
        max_new_tokens: s.max_new_tokens ?? 32,
        min_peers: s.min_peers ?? 2,
        max_peers: s.max_peers ?? 4,
        benchmark: true,
      }
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

  const fields = [
    ['Model', current.spec?.model_id],
    ['Run ID', current.id],
    ['Created', dateText(current.created_at)],
    ['Last update', dateText(current.updated_at)],
    ['Revision', current.spec?.revision],
    ['Model weight size', m.weights_bytes ? formatBytes(m.weights_bytes) : 'Auto-resolved'],
    ['Elapsed runtime', seconds(m.total_seconds ?? m.elapsed_seconds)],
    ['Runtime lifecycle', 'Per-run session; resources released after completion'],
  ]

  const runtimeProgressBanner = active && (
    <div
      style={{
        marginBottom: 16,
        padding: 14,
        borderRadius: 8,
        border: '1px solid var(--border)',
        background: 'var(--panel-subtle, rgba(255,255,255,0.03))',
      }}
    >
      <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <strong style={{ fontSize: 13 }}>
          Live Phase: {statusLabel(current.status)}
          {current.status === 'running' && maxNewTokens ? ` (${generatedTokens || 0}/${maxNewTokens} tokens)` : ''}
        </strong>
        <span className="mono" style={{ fontSize: 12, color: 'var(--muted)' }}>
          {m.elapsed_seconds != null ? `${m.elapsed_seconds}s elapsed` : 'Updating every 2s'}
        </span>
      </div>

      {current.status === 'loading' && plan.length > 0 && (
        <div style={{ display: 'grid', gap: 8 }}>
          {plan.map((p, idx) => {
            const st = stageStatus[p.node_id] || {}
            const lp = st.progress
            const pct = typeof lp?.percent === 'number' ? lp.percent : st.status === 'serving' ? 100 : null
            return (
              <div key={p.node_id} style={{ fontSize: 12 }}>
                <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
                  <span>
                    Provider {idx + 1} (Layers {p.start}–{p.end - 1}) · <strong>{statusLabel(st.status)}</strong>
                  </span>
                  <span className="mono" style={{ color: 'var(--muted)' }}>
                    {lp?.downloaded_bytes != null
                      ? `${formatBytes(lp.downloaded_bytes)}${lp.total_bytes ? ` / ${formatBytes(lp.total_bytes)}` : ''}${pct != null ? ` (${pct}%)` : ''}${lp.speed_bps ? ` · ${formatSpeed(lp.speed_bps)}` : ''}`
                      : st.status === 'serving'
                      ? 'Ready (100%)'
                      : 'Waiting for container telemetry…'}
                  </span>
                </div>
                {pct != null && (
                  <div style={{ height: 6, borderRadius: 4, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.min(100, Math.max(2, pct))}%`, height: '100%', background: 'var(--accent, #6d5dfc)' }} />
                  </div>
                )}
              </div>
            )
          })}
          <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
            Model files stream into the isolated Docker cache volume inside each runtime; Docker Desktop Disk R/W stats only count container overlay writes.
          </p>
        </div>
      )}

      {current.status === 'downloading_model' && (
        <div style={{ fontSize: 12 }}>
          <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
            <span>Coordinator Gateway downloading tokenizer &amp; head weights</span>
            <span className="mono" style={{ color: 'var(--muted)' }}>
              {coordinatorStage.downloaded_bytes != null
                ? `${formatBytes(coordinatorStage.downloaded_bytes)}${coordinatorStage.total_bytes ? ` / ${formatBytes(coordinatorStage.total_bytes)}` : ''}${coordinatorStage.percent != null ? ` (${coordinatorStage.percent}%)` : ''}${coordinatorStage.speed_bps ? ` · ${formatSpeed(coordinatorStage.speed_bps)}` : ''}`
                : 'Resolving cache files…'}
            </span>
          </div>
          {coordinatorStage.percent != null && (
            <div style={{ height: 6, borderRadius: 4, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
              <div style={{ width: `${Math.min(100, Math.max(2, coordinatorStage.percent))}%`, height: '100%', background: 'var(--accent, #6d5dfc)' }} />
            </div>
          )}
        </div>
      )}

      {current.status === 'running' && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, color: 'var(--muted)' }}>
          <span>Speed: <strong>{throughput}</strong></span>
          <span>Latency: <strong>{latencyPerToken}</strong></span>
          {m.prefill_latency_seconds != null && <span>TTFT: <strong>{m.prefill_latency_seconds}s</strong></span>}
          {m.token_confidence_pct != null && <span>Confidence: <strong>{m.token_confidence_pct}%</strong></span>}
        </div>
      )}
    </div>
  )

  return (
    <>
      <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <StatusBadge status={current.status} />
        <div className="inline-actions">
          <Link className="button small secondary" href={`/inference?from=${encodeURIComponent(current.id)}`}>
            Run again
          </Link>
          <button className="button small secondary" onClick={() => exportFile(`run-${current.id}.json`, current)}>
            Export run
          </button>
          {active && (
            <button className="button small danger" onClick={() => setConfirm(true)}>
              Cancel run
            </button>
          )}
        </div>
      </div>

      <ErrorNotice error={error} />
      {current.error && <ErrorNotice error={current.error} />}
      {runtimeProgressBanner}

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
                <div key={String(k)}>
                  <dt>{k}</dt>
                  <dd>{v || 'Not reported'}</dd>
                </div>
              ))}
            </dl>
            <ol className="timeline">
              <li>
                <strong>Run created</strong>
                <p>{dateText(current.created_at)}</p>
              </li>
              <li>
                <strong>{statusLabel(current.status)}</strong>
                <p>
                  {dateText(current.updated_at)} · Current recorded state
                  {generatedTokens ? ` · ${generatedTokens}${maxNewTokens ? `/${maxNewTokens}` : ''} tokens` : ''}
                  {m.throughput_tokens_per_sec ? ` · ${m.throughput_tokens_per_sec} tok/s` : ''}
                </p>
              </li>
            </ol>
            <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
              <h3>Model response</h3>
              {isStreaming && (
                <span className="mono" style={{ fontSize: 12, color: 'var(--accent, #7c6cf6)' }}>
                  LIVE STREAM · {generatedTokens || 0}/{maxNewTokens || '?'} tokens
                </span>
              )}
            </div>
            {displayOutput ? (
              <div className="output">
                {typeof displayOutput === 'string' ? displayOutput : JSON.stringify(displayOutput, null, 2)}
              </div>
            ) : (
              <p className="muted">
                {active
                  ? 'Waiting for the distributed Petals layers to finish initializing before token streaming starts.'
                  : 'No response was returned for this run.'}
              </p>
            )}

            {m.single_node_reference_text && (
              <details style={{ marginTop: 16 }}>
                <summary style={{ cursor: 'pointer', fontSize: 13 }}>
                  Single-node CPU baseline comparison ({m.baseline_token_match_pct ?? '—'}% token agreement)
                </summary>
                <div className="output" style={{ marginTop: 8 }}>{m.single_node_reference_text}</div>
              </details>
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
                  {plan.map((p, i) => {
                    const st = stageStatus[p.node_id] || {}
                    const lp = st.progress
                    const cap = current.capacity_measurements?.[p.node_id]
                    const rpc = rpcByNode[p.node_id]
                    return (
                      <div className="node-stage" key={p.node_id}>
                        <small>PROVIDER {i + 1} · {p.device || 'Unknown device'}</small>
                        <h3>Layers {p.start}–{p.end - 1}</h3>
                        <p className="mono">{p.node_id}</p>
                        <div style={{ marginTop: 12 }}>
                          <StatusBadge status={st.status} />
                        </div>
                        <dl className="fact">
                          <dt>Allocation basis</dt>
                          <dd>{p.allocation_basis || 'Not reported'}</dd>
                        </dl>
                        <dl className="fact">
                          <dt>Measured layer capacity</dt>
                          <dd>
                            {number(p.capacity_layers)}
                            {cap?.inference_rps ? ` (${Number(cap.inference_rps).toFixed(2)} req/s)` : ''}
                          </dd>
                        </dl>
                        <dl className="fact">
                          <dt>Route</dt>
                          <dd>{routeText(p, st)}</dd>
                        </dl>
                        {lp && (
                          <dl className="fact">
                            <dt>Weight cache / progress</dt>
                            <dd>
                              {lp.downloaded_bytes != null
                                ? `${formatBytes(lp.downloaded_bytes)}${lp.total_bytes ? ` / ${formatBytes(lp.total_bytes)}` : ''}${lp.percent != null ? ` (${lp.percent}%)` : ''}`
                                : lp.percent != null
                                ? `${lp.percent}%`
                                : lp.phase || 'Active'}
                            </dd>
                          </dl>
                        )}
                        {rpc && (
                          <dl className="fact">
                            <dt>Stage RPC latency</dt>
                            <dd>
                              {rpc.prefillMs != null ? `Prefill ${rpc.prefillMs}ms` : ''}
                              {rpc.prefillMs != null && rpc.avgDecodeMs != null ? ' · ' : ''}
                              {rpc.avgDecodeMs != null ? `Decode ${rpc.avgDecodeMs}ms/tok (${rpc.decodeCount} hops)` : ''}
                            </dd>
                          </dl>
                        )}
                        {st.error && <ErrorNotice error={st.error} />}
                        <Link className="text-link" href={`/nodes?id=${encodeURIComponent(p.node_id)}`}>
                          Inspect provider →
                        </Link>
                      </div>
                    )
                  })}
                </div>
              </>
            ) : (
              <Empty title="No layer assignment recorded">Capacity measurement and assignment occur after a run is accepted.</Empty>
            )}
          </>
        )}

        {tab === 'Playground' && (
          <>
            <div className="field">
              <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                <span>Submitted prompt</span>
                <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>
                  Locked · Non-editable
                </span>
              </div>
              <div
                className="output"
                role="textbox"
                aria-readonly="true"
                aria-label="Submitted prompt (read-only)"
                style={{ opacity: 0.9, cursor: 'default', minHeight: 56, whiteSpace: 'pre-wrap' }}
              >
                {current.spec?.prompt || '—'}
              </div>
            </div>
            {displayOutput ? (
              <div>
                <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                  <strong style={{ fontSize: 13 }}>{isStreaming ? 'Live streaming output' : 'Generated output'}</strong>
                  {generatedTokens != null && (
                    <span className="mono" style={{ fontSize: 12, color: 'var(--muted)' }}>
                      {generatedTokens}{maxNewTokens ? ` / ${maxNewTokens}` : ''} tokens · {throughput}
                    </span>
                  )}
                </div>
                <div className="output">{typeof displayOutput === 'string' ? displayOutput : JSON.stringify(displayOutput)}</div>
              </div>
            ) : (
              active && <p className="muted">Output tokens will stream here live as soon as distributed decoding starts.</p>
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
                  readOnly={submittingPrompt}
                  disabled={submittingPrompt}
                  onChange={e => setInteractivePrompt(e.target.value)}
                  rows={4}
                  style={{ width: '100%', resize: submittingPrompt ? 'none' : undefined, opacity: submittingPrompt ? 0.65 : 1 }}
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
                <Link className="button secondary" href={`/inference?from=${encodeURIComponent(current.id)}`}>
                  Adjust model &amp; peers in Studio
                </Link>
              </div>
            </div>
          </>
        )}

        {tab === 'Metrics' && (
          <>
            <h3 style={{ fontSize: 14, marginBottom: 10 }}>Runtime &amp; Throughput</h3>
            <dl className="detail-grid">
              {[
                ['Current phase', statusLabel(current.status)],
                ['Providers', m.provider_count ?? (plan.length ? plan.length : active ? 'Selecting…' : undefined)],
                ['Generated tokens', generatedTokens != null ? `${generatedTokens}${maxNewTokens ? ` / ${maxNewTokens}` : ''}` : active ? `0 / ${maxNewTokens || '?'}` : 'Not reported'],
                ['Throughput', throughput],
                ['Latency per token', latencyPerToken],
                ['Time to first token (TTFT)', m.prefill_latency_seconds != null ? `${m.prefill_latency_seconds}s` : active ? 'Measuring during prefill…' : 'Not reported'],
                ['Cluster capacity rate', capacityTotalRps != null ? `${capacityTotalRps} req/s` : active ? 'Measuring capacity…' : 'Not reported'],
                ['Model preparation', m.model_load_seconds != null ? seconds(m.model_load_seconds) : active ? 'Preparing layers…' : 'Not reported'],
                ['Generation time', m.distributed_generation_seconds != null ? seconds(m.distributed_generation_seconds) : active ? 'Measuring during decode…' : 'Not reported'],
                ['Elapsed / total time', (m.total_seconds ?? m.elapsed_seconds) != null ? seconds(m.total_seconds ?? m.elapsed_seconds) : active ? 'In progress…' : 'Not reported'],
              ].map(([label, v]) => (
                <div key={String(label)}>
                  <dt>{label}</dt>
                  <dd>{typeof v === 'number' ? number(v) : v || 'Not reported'}</dd>
                </div>
              ))}
            </dl>

            <h3 style={{ fontSize: 14, marginTop: 22, marginBottom: 10 }}>Accuracy &amp; Output Quality</h3>
            <dl className="detail-grid">
              {[
                ['Mean token confidence', m.token_confidence_pct != null ? `${m.token_confidence_pct}%` : active ? 'Measuring during decode…' : 'Not recorded'],
                ['Perplexity', m.perplexity != null ? String(m.perplexity) : active ? 'Measuring during decode…' : 'Not recorded'],
                ['Finite logits integrity', m.finite_logits_pct != null ? `${m.finite_logits_pct}%` : active ? 'Measuring during decode…' : 'Not recorded'],
                [
                  'Baseline token match accuracy',
                  m.baseline_token_match_pct != null
                    ? `${m.baseline_token_match_pct}%`
                    : current.spec?.benchmark
                    ? active
                      ? 'Pending CPU baseline step'
                      : 'Not recorded'
                    : 'Enable baseline comparison in Studio',
                ],
                [
                  'Prefix agreement',
                  m.baseline_prefix_match_tokens != null
                    ? `${m.baseline_prefix_match_tokens} / ${m.baseline_compared_tokens} tokens`
                    : active && current.spec?.benchmark
                    ? 'Pending CPU baseline step'
                    : 'Not recorded',
                ],
                [
                  'Exact sequence match',
                  m.baseline_exact_text_match != null
                    ? m.baseline_exact_text_match
                      ? '100% Exact match'
                      : 'Diverged'
                    : active && current.spec?.benchmark
                    ? 'Pending CPU baseline step'
                    : 'Not recorded',
                ],
                [
                  'Single-node CPU speed',
                  m.single_node_throughput_tokens_per_sec != null
                    ? `${m.single_node_throughput_tokens_per_sec} tok/s (${m.single_node_reference_seconds}s)`
                    : active && current.spec?.benchmark
                    ? 'Pending CPU baseline step'
                    : 'Not recorded',
                ],
                [
                  'Distributed speedup',
                  m.speedup != null
                    ? `${m.speedup}x`
                    : active && current.spec?.benchmark
                    ? 'Pending CPU baseline step'
                    : 'Not recorded',
                ],
              ].map(([label, v]) => (
                <div key={String(label)}>
                  <dt>{label}</dt>
                  <dd>{String(v)}</dd>
                </div>
              ))}
            </dl>

            {plan.length > 0 && (
              <>
                <h3 style={{ fontSize: 14, marginTop: 22, marginBottom: 10 }}>Per-Provider Stage Timing Breakdown</h3>
                <dl className="detail-grid">
                  {plan.map((p, idx) => {
                    const rpc = rpcByNode[p.node_id]
                    const cap = current.capacity_measurements?.[p.node_id]
                    const text = rpc
                      ? `Prefill ${rpc.prefillMs ?? '—'}ms · Decode ${rpc.avgDecodeMs ?? '—'}ms/tok (${rpc.decodeCount} steps)`
                      : cap?.inference_rps
                      ? `Measured capacity ${Number(cap.inference_rps).toFixed(2)} req/s`
                      : statusLabel(stageStatus[p.node_id]?.status)
                    return (
                      <div key={p.node_id}>
                        <dt>
                          Provider {idx + 1} · Layers {p.start}–{p.end - 1} ({routeText(p, stageStatus[p.node_id])})
                        </dt>
                        <dd>{text}</dd>
                      </div>
                    )
                  })}
                </dl>
              </>
            )}

            <p style={{ marginTop: 22, fontSize: 12 }} className="muted">
              All throughput, latency, confidence, perplexity, and CPU baseline agreement metrics are measured directly from live execution logits and RPC timings.
            </p>
          </>
        )}

        {tab === 'Logs' && (
          <>
            <p style={{ marginBottom: 16 }}>
              Live coordinator gateway output, provider layer container logs, and structured stage diagnostics.
            </p>
            {current.error && <pre className="log">{current.error}</pre>}

            {Array.isArray(current.gateway_log_tail) && current.gateway_log_tail.length > 0 && (
              <details open className="fact" style={{ marginBottom: 14 }}>
                <summary className="mono">
                  Coordinator Gateway · {statusLabel(coordinatorStage.status || current.status)} ({current.gateway_log_tail.length} lines)
                </summary>
                <pre className="log">{current.gateway_log_tail.join('\n')}</pre>
              </details>
            )}

            {plan.map((p, idx) => {
              const st = stageStatus[p.node_id] || {}
              const tail: string[] = Array.isArray(st.progress?.log_tail) ? st.progress.log_tail : []
              return (
                <details key={p.node_id} open={idx === 0 && tail.length > 0} className="fact">
                  <summary className="mono">
                    {p.node_id} · Layers {p.start}–{p.end - 1} · {statusLabel(st.status)}
                    {tail.length ? ` (${tail.length} log lines)` : ''}
                  </summary>
                  {tail.length > 0 && <pre className="log">{tail.join('\n')}</pre>}
                  <pre className="log">
                    {JSON.stringify(
                      {
                        status: statusLabel(st.status),
                        error: st.error,
                        transport: routeText(p, st),
                        progress: st.progress
                          ? {
                              phase: st.progress.phase,
                              downloaded_bytes: st.progress.downloaded_bytes,
                              total_bytes: st.progress.total_bytes,
                              percent: st.progress.percent,
                              speed_bps: st.progress.speed_bps,
                            }
                          : undefined,
                      },
                      null,
                      2
                    )}
                  </pre>
                </details>
              )
            })}
            {!current.error && !plan.length && !(current.gateway_log_tail || []).length && <p>No diagnostics recorded yet.</p>}
          </>
        )}

        {tab === 'Settings' && (
          <>
            <p style={{ marginBottom: 16 }}>Submitted configuration is locked and read-only. Click &ldquo;Run again&rdquo; to launch a modified run.</p>
            <dl className="detail-grid">
              {[
                ['Model', current.spec?.model_id],
                ['Max new tokens', current.spec?.max_new_tokens],
                ['Providers range', `${current.spec?.min_peers ?? '—'}–${current.spec?.max_peers ?? '—'}`],
                ['Revision', current.spec?.revision],
                ['Baseline comparison', current.spec?.benchmark ? 'Enabled' : 'Disabled'],
              ].map(([k, v]) => (
                <div key={String(k)}>
                  <dt>{k}</dt>
                  <dd>{v ?? 'Not set'}</dd>
                </div>
              ))}
            </dl>
            <div style={{ marginTop: 18 }}>
              <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 6 }}>
                <strong style={{ fontSize: 13 }}>Submitted prompt</strong>
                <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>Locked · Non-editable</span>
              </div>
              <div className="output" role="textbox" aria-readonly="true" style={{ cursor: 'default', whiteSpace: 'pre-wrap' }}>
                {current.spec?.prompt || '—'}
              </div>
            </div>
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
