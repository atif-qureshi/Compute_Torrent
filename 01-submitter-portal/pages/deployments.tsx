import React, { useCallback, useEffect, useState } from 'react'
import AppLayout from '../components/AppLayout'
import StatusBadge from '../components/StatusBadge'
import DiagnosticBanner from '../components/DiagnosticBanner'
import LayerPipelineVisualizer from '../components/LayerPipelineVisualizer'

const API = '/api/ct'

async function api(path: string, options?: RequestInit) {
  const response = await fetch(`/api/ct/distributed${path}`, options)
  const body = await response.json()
  if (!response.ok) {
    const detail = body.detail || body.message
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return body
}

const ACTIVE_STAGES = [
  'queued',
  'resolving',
  'profiling_capacity',
  'loading',
  'downloading_model',
  'loading_reference',
  'connecting_layers',
  'running',
  'verifying',
  'benchmarking',
]

export default function Deployments() {
  const [jobs, setJobs] = useState<any[]>([])
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [filter, setFilter] = useState<'all' | 'active' | 'completed' | 'failed'>('all')
  const [error, setError] = useState<string>('')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [copiedResult, setCopiedResult] = useState(false)

  const refresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const history = await api('/jobs')
      setJobs(history || [])
      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to fetch deployments')
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  const filteredJobs = jobs.filter((j) => {
    if (filter === 'active') return ACTIVE_STAGES.includes(j.status)
    if (filter === 'completed') return j.status === 'completed'
    if (filter === 'failed') return j.status === 'failed'
    return true
  })

  const currentJob = jobs.find((j) => j.id === selectedJobId) || filteredJobs[0] || jobs[0]

  const downloadReceipt = (job: any) => {
    const blob = new Blob([JSON.stringify(job, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `deployment-${job.id}.json`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const copyResult = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedResult(true)
    setTimeout(() => setCopiedResult(false), 2000)
  }

  return (
    <AppLayout
      title="Model Deployments"
      subtitle="Execution history, contiguous layer partitioning plans, and pipeline telemetry."
      actions={
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={refresh}
            style={{
              padding: '6px 12px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#cbd5e1',
            }}
          >
            {isRefreshing ? '🔄 Refreshing…' : '↻ Refresh Runs'}
          </button>
          <a
            href="/inference"
            style={{
              padding: '6px 14px',
              backgroundColor: '#3b82f6',
              color: '#ffffff',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
            }}
          >
            + New Deployment
          </a>
        </div>
      }
    >
      {error && (
        <DiagnosticBanner
          error={error}
          onDismiss={() => setError('')}
          onRetry={refresh}
        />
      )}

      {/* Deployments Filter & Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '24px' }}>
        {/* Left Column: List of Jobs */}
        <section
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '10px',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            height: 'fit-content',
          }}
        >
          {/* Filter Pills */}
          <div
            style={{
              display: 'flex',
              backgroundColor: '#090d16',
              padding: '3px',
              borderRadius: '6px',
              border: '1px solid rgba(255, 255, 255, 0.06)',
            }}
          >
            {(['all', 'active', 'completed', 'failed'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setFilter(tab)}
                style={{
                  flex: 1,
                  padding: '4px 6px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  fontWeight: filter === tab ? 600 : 500,
                  backgroundColor: filter === tab ? '#3b82f6' : 'transparent',
                  color: filter === tab ? '#ffffff' : '#94a3b8',
                  textTransform: 'capitalize',
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Job List */}
          {filteredJobs.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: '#64748b', fontSize: '12px' }}>
              No deployments found for this filter.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '70vh', overflowY: 'auto' }}>
              {filteredJobs.map((j) => {
                const isSelected = currentJob?.id === j.id
                return (
                  <div
                    key={j.id}
                    onClick={() => setSelectedJobId(j.id)}
                    style={{
                      padding: '12px',
                      borderRadius: '8px',
                      backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.1)' : '#090d16',
                      border: isSelected ? '1px solid #3b82f6' : '1px solid rgba(255, 255, 255, 0.06)',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '13px' }}>
                        {j.spec?.model_id?.split('/').pop() || 'Model'}
                      </span>
                      <StatusBadge status={j.status} size="sm" />
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{j.id.slice(0, 12)}…</span>
                      <span>{new Date(j.created_at * 1000).toLocaleTimeString()}</span>
                    </div>

                    {j.spec?.prompt && (
                      <p style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        "{j.spec.prompt}"
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* Right Column: Selected Deployment Detail */}
        {currentJob ? (
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
            }}
          >
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                    {currentJob.spec?.model_id}
                  </h2>
                  <StatusBadge status={currentJob.status} />
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', fontFamily: 'var(--font-mono)', marginTop: '4px' }}>
                  Job ID: {currentJob.id} · Created at {new Date(currentJob.created_at * 1000).toLocaleString()}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => downloadReceipt(currentJob)}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '6px',
                    fontSize: '12px',
                    color: '#cbd5e1',
                  }}
                >
                  💾 Export JSON
                </button>
                <a
                  href={`/inference?model=${currentJob.spec?.model_id?.toLowerCase().includes('bloom') ? 'bloomz' : 'tinyllama'}`}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    borderRadius: '6px',
                    fontSize: '12px',
                    color: '#60a5fa',
                    fontWeight: 500,
                  }}
                >
                  Re-run in Studio →
                </a>
              </div>
            </div>

            {/* Error Diagnostics if failed */}
            {currentJob.error && (
              <DiagnosticBanner error={currentJob.error} />
            )}

            {/* Prompt Card */}
            {currentJob.spec?.prompt && (
              <div style={{ backgroundColor: '#090d16', borderRadius: '8px', padding: '12px 16px', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '4px' }}>
                  Submitted Prompt:
                </span>
                <p style={{ fontSize: '13px', color: '#e2e8f0', margin: 0, fontStyle: 'italic' }}>
                  "{currentJob.spec.prompt}"
                </p>
              </div>
            )}

            {/* Layer Partitioning Visualizer */}
            <div>
              <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '8px' }}>
                Distributed Layer Allocation Scheme
              </span>
              <LayerPipelineVisualizer
                totalLayers={currentJob.spec?.layers || 22}
                plan={currentJob.plan || []}
                stageStatus={currentJob.stage_status || {}}
                jobStatus={currentJob.status}
              />
            </div>

            {/* Generation Result */}
            {currentJob.result && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Generated Model Output
                  </span>
                  <button
                    onClick={() => copyResult(currentJob.result)}
                    style={{
                      padding: '3px 8px',
                      backgroundColor: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: '4px',
                      fontSize: '11px',
                      color: '#cbd5e1',
                    }}
                  >
                    {copiedResult ? '✅ Copied' : '📄 Copy'}
                  </button>
                </div>

                <pre
                  style={{
                    backgroundColor: '#090d16',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    padding: '14px 16px',
                    fontSize: '13px',
                    color: '#f8fafc',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.6,
                  }}
                >
                  {currentJob.result}
                </pre>
              </div>
            )}

            {/* Telemetry Metrics Strip */}
            {currentJob.metrics && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                  gap: '12px',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: '8px',
                  padding: '14px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                }}
              >
                <div>
                  <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Generation Latency</span>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>
                    {currentJob.metrics.distributed_generation_seconds}s
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Tokens Generated</span>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>
                    {currentJob.metrics.generated_tokens} tokens
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Peer Count</span>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>
                    {currentJob.metrics.provider_count} machines
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Verification Duration</span>
                  <span style={{ fontSize: '14px', fontWeight: 600, color: '#34d399' }}>
                    {currentJob.metrics.verification_seconds ? `${currentJob.metrics.verification_seconds}s` : '—'}
                  </span>
                </div>
              </div>
            )}
          </section>
        ) : (
          <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
            No deployments recorded yet.
          </div>
        )}
      </div>
    </AppLayout>
  )
}
