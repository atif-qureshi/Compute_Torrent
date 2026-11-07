import React, { useCallback, useEffect, useState } from 'react'
import AppLayout from '../components/AppLayout'
import StatCard from '../components/StatCard'
import StatusBadge from '../components/StatusBadge'
import DiagnosticBanner from '../components/DiagnosticBanner'

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
  if (!value) return 'Just now'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return 'Just now'
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
  const [health, setHealth] = useState<any>(null)
  const [distStatus, setDistStatus] = useState<any>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lanAddress, setLanAddress] = useState('ws://192.168.100.7:8001/ws/seeder')
  const [publicAddress, setPublicAddress] = useState<string | null>(null)
  const [enrollmentToken, setEnrollmentToken] = useState('')
  const [copiedToken, setCopiedToken] = useState(false)
  const [copiedLan, setCopiedLan] = useState(false)

  useEffect(() => {
    fetch('/api/provider-address')
      .then(responseJson)
      .then((data) => {
        if (data.lan_address) setLanAddress(data.lan_address)
        setPublicAddress(data.public_address || null)
        setEnrollmentToken(data.enrollment_token || '')
      })
      .catch(() => {})
  }, [])

  const refresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const [tasksRes, seedersRes, creditsRes, healthRes, distRes] = await Promise.allSettled([
        fetch(`${API}/tasks?limit=10&submitter_id=${ACCOUNT}`).then(responseJson),
        fetch(`${API}/seeders`).then(responseJson),
        fetch(`${API}/credits?submitter_id=${ACCOUNT}`).then(responseJson),
        fetch(`${API}/health`).then(responseJson),
        fetch(`${API}/distributed/status`).then(responseJson),
      ])

      if (tasksRes.status === 'fulfilled') setTasks(tasksRes.value || [])
      if (seedersRes.status === 'fulfilled') setSeeders(seedersRes.value || [])
      if (creditsRes.status === 'fulfilled') setCredits(creditsRes.value)
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value)
      if (distRes.status === 'fulfilled') setDistStatus(distRes.value)

      setErrorMessage('')
    } catch (error: any) {
      setErrorMessage(error.message || 'Coordinator connection error')
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  const onlineSeeders = seeders.filter((node) => (
    typeof node.control_age_seconds === 'number' ||
    ['online', 'idle', 'busy', 'paused'].includes(node.state || node.status)
  ))

  const readyProviders = distStatus?.providers?.filter((p: any) => p.layer_ready) || []
  const isHealthy = health?.status === 'healthy'
  const isDhtReady = distStatus?.status === 'ready'

  // Calculate cluster aggregate resources
  const totalCores = seeders.reduce((acc, s) => acc + (s.profile?.cpu_cores || s.profile?.physical_cores || 0), 0)
  const totalRamGb = seeders.reduce((acc, s) => acc + (Number(s.profile?.RAM) || 0), 0)
  const gpuCount = seeders.filter((s) => s.profile?.GPU && !s.profile.GPU.toLowerCase().includes('none')).length

  return (
    <AppLayout
      title="Cluster Overview"
      subtitle="Real-time telemetry, provider node availability, and distributed model compute health."
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
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>{isRefreshing ? '🔄' : '↻'}</span>
            <span>{isRefreshing ? 'Refreshing…' : 'Refresh'}</span>
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
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>🧠</span>
            <span>Deploy Model →</span>
          </a>
        </div>
      }
    >
      {/* Actionable Error Banner if any */}
      {errorMessage && (
        <DiagnosticBanner
          error={errorMessage}
          onDismiss={() => setErrorMessage('')}
          onRetry={refresh}
        />
      )}

      {/* Top 4 KPI Metrics */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        <StatCard
          label="Active Providers"
          value={
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span>{onlineSeeders.length}</span>
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: 500 }}>
                / {seeders.length} Enrolled
              </span>
            </div>
          }
          subtext={
            readyProviders.length >= 2
              ? '✨ Cluster primed for multi-peer layer slicing'
              : 'Requires at least 2 layer-ready peers'
          }
          icon="🖥️"
          statusColor={onlineSeeders.length >= 2 ? 'emerald' : onlineSeeders.length > 0 ? 'amber' : 'rose'}
        />

        <StatCard
          label="Petals DHT Gateway"
          value={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ textTransform: 'uppercase' }}>{isDhtReady ? 'Ready' : distStatus?.status || 'Offline'}</span>
              <StatusBadge status={isDhtReady ? 'ready' : 'checking'} size="sm" showDot={true} />
            </div>
          }
          subtext="Distributed hash table layer coordination"
          icon="🌐"
          statusColor={isDhtReady ? 'emerald' : 'amber'}
        />

        <StatCard
          label="Total Task Executions"
          value={tasks.length}
          subtext="Executed across distributed provider nodes"
          icon="⚡"
          statusColor="blue"
        />

        <StatCard
          label="Demo Credits Balance"
          value={credits ? `${credits.balance}` : '—'}
          subtext="Incentive test accounting ledger"
          icon="💳"
          statusColor="purple"
        />
      </section>

      {/* Cluster Hardware Capacity Strip */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '8px',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
            }}
          >
            ⚡
          </div>
          <div>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>
              Aggregated Cluster Compute Capacity
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Hardware detected across online volunteer machines
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block' }}>
              Logical Cores
            </span>
            <span style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
              {totalCores || '—'} Cores
            </span>
          </div>

          <div style={{ borderLeft: '1px solid rgba(255, 255, 255, 0.08)', paddingLeft: '24px' }}>
            <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block' }}>
              Total System RAM
            </span>
            <span style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
              {totalRamGb ? `${totalRamGb.toFixed(0)} GB` : '—'}
            </span>
          </div>

          <div style={{ borderLeft: '1px solid rgba(255, 255, 255, 0.08)', paddingLeft: '24px' }}>
            <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block' }}>
              GPU Accelerators
            </span>
            <span style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
              {gpuCount} Detected
            </span>
          </div>

          <div style={{ borderLeft: '1px solid rgba(255, 255, 255, 0.08)', paddingLeft: '24px' }}>
            <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block' }}>
              Coordinator Health
            </span>
            <div style={{ marginTop: '2px' }}>
              <StatusBadge status={isHealthy ? 'healthy' : 'checking'} size="sm" />
            </div>
          </div>
        </div>
      </section>

      {/* Main 2-Column Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '24px', marginBottom: '24px' }}>
        {/* Left Column: Live Provider Nodes Table */}
        <section
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '10px',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  Enrolled Provider Machines
                </h2>
                <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
                  Machines registered to accept distributed model layer partitions.
                </p>
              </div>
              <a
                href="/nodes"
                style={{ fontSize: '12px', color: '#60a5fa', fontWeight: 500 }}
              >
                Manage Nodes ({seeders.length}) →
              </a>
            </div>

            {seeders.length === 0 ? (
              <div
                style={{
                  padding: '36px',
                  textAlign: 'center',
                  backgroundColor: '#090d16',
                  borderRadius: '8px',
                  border: '1px dashed rgba(255, 255, 255, 0.1)',
                }}
              >
                <div style={{ fontSize: '24px', marginBottom: '8px' }}>💻</div>
                <div style={{ fontSize: '14px', fontWeight: 500, color: '#f8fafc' }}>
                  No provider computers enrolled yet
                </div>
                <p style={{ fontSize: '12px', color: '#64748b', margin: '4px 0 16px' }}>
                  Launch the provider desktop client on a volunteer PC with the join code on the right.
                </p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: '#64748b' }}>
                      <th style={{ padding: '8px 10px', fontWeight: 600 }}>Node ID</th>
                      <th style={{ padding: '8px 10px', fontWeight: 600 }}>Hardware Specs</th>
                      <th style={{ padding: '8px 10px', fontWeight: 600 }}>Status</th>
                      <th style={{ padding: '8px 10px', fontWeight: 600 }}>Layer Ready</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seeders.slice(0, 5).map((node) => {
                      const isOnline = (
                        typeof node.control_age_seconds === 'number' ||
                        ['online', 'idle', 'busy', 'paused'].includes(node.state || node.status)
                      )
                      const prof = node.profile || {}
                      const distPeer = distStatus?.providers?.find((p: any) => p.node_id === node.node_id)
                      const isReady = distPeer ? distPeer.layer_ready : prof.docker_ok

                      return (
                        <tr
                          key={node.node_id}
                          style={{
                            borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                            transition: 'background-color 0.1s ease',
                          }}
                        >
                          <td style={{ padding: '10px', fontFamily: 'var(--font-mono)', color: '#cbd5e1' }}>
                            {node.node_id.slice(-10)}
                          </td>
                          <td style={{ padding: '10px' }}>
                            <div style={{ fontWeight: 500, color: '#f8fafc' }}>
                              {prof.cpu_model || 'Standard CPU'}
                            </div>
                            <div style={{ fontSize: '11px', color: '#64748b' }}>
                              {prof.RAM || '—'} GB RAM · {prof.GPU || 'Integrated Graphics'}
                            </div>
                          </td>
                          <td style={{ padding: '10px' }}>
                            <StatusBadge
                              status={isOnline ? (node.state || 'online') : 'offline'}
                              size="sm"
                            />
                          </td>
                          <td style={{ padding: '10px' }}>
                            <span
                              style={{
                                fontSize: '11px',
                                color: isReady ? '#34d399' : '#fbbf24',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              {isReady ? '✅ Ready' : '⚠️ Pending'}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        {/* Right Column: Connection Helper & Supported Models */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Quick Connect Credentials Card */}
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '20px',
            }}
          >
            <div style={{ marginBottom: '14px' }}>
              <h2 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                🔑 Provider Connection Credentials
              </h2>
              <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
                Required to enroll client machines on your local network.
              </p>
            </div>

            {/* Join Code */}
            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '4px' }}>
                Provider Join Token
              </label>
              <div style={{ display: 'flex', gap: '6px' }}>
                <input
                  type="text"
                  readOnly
                  value={enrollmentToken || 'Unavailable'}
                  style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#fbbf24', backgroundColor: '#090d16' }}
                />
                <button
                  onClick={() => {
                    if (!enrollmentToken) return
                    navigator.clipboard.writeText(enrollmentToken)
                    setCopiedToken(true)
                    setTimeout(() => setCopiedToken(false), 2000)
                  }}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#3b82f6',
                    color: '#ffffff',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                  }}
                >
                  {copiedToken ? '✅' : 'Copy'}
                </button>
              </div>
            </div>

            {/* LAN Address */}
            <div>
              <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '4px' }}>
                Coordinator LAN WebSocket URL
              </label>
              <div style={{ display: 'flex', gap: '6px' }}>
                <input
                  type="text"
                  readOnly
                  value={publicAddress || lanAddress}
                  style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#60a5fa', backgroundColor: '#090d16' }}
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(publicAddress || lanAddress)
                    setCopiedLan(true)
                    setTimeout(() => setCopiedLan(false), 2000)
                  }}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: 'rgba(255, 255, 255, 0.08)',
                    color: '#f8fafc',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    borderRadius: '6px',
                    fontSize: '11px',
                  }}
                >
                  {copiedLan ? '✅' : 'Copy'}
                </button>
              </div>
            </div>
          </section>

          {/* Model Catalog Quick Launch Card */}
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div>
                <h2 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  🧠 Supported Model Catalog
                </h2>
                <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
                  Tested architectures with verified weights.
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div
                style={{
                  padding: '10px 12px',
                  backgroundColor: '#090d16',
                  borderRadius: '6px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '12px' }}>
                    TinyLlama 1.1B Chat
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b' }}>
                    22 Layers · 2048 Hidden Dim · Sliced across 2+ PCs
                  </div>
                </div>
                <a
                  href="/inference?model=tinyllama"
                  style={{
                    padding: '4px 10px',
                    backgroundColor: 'rgba(59, 130, 246, 0.15)',
                    color: '#60a5fa',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 500,
                  }}
                >
                  Deploy →
                </a>
              </div>

              <div
                style={{
                  padding: '10px 12px',
                  backgroundColor: '#090d16',
                  borderRadius: '6px',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '12px' }}>
                    BLOOMZ 560M Instruction
                  </div>
                  <div style={{ fontSize: '11px', color: '#64748b' }}>
                    24 Layers · 1024 Hidden Dim · Multilingual
                  </div>
                </div>
                <a
                  href="/inference?model=bloomz"
                  style={{
                    padding: '4px 10px',
                    backgroundColor: 'rgba(59, 130, 246, 0.15)',
                    color: '#60a5fa',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 500,
                  }}
                >
                  Deploy →
                </a>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Bottom Section: Recent Execution Audit */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '20px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
              Recent Task & Inference Executions
            </h2>
            <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
              Historical task records and model execution logs.
            </p>
          </div>
          <a href="/history" style={{ fontSize: '12px', color: '#60a5fa', fontWeight: 500 }}>
            View Full Audit History →
          </a>
        </div>

        {tasks.length === 0 ? (
          <div
            style={{
              padding: '30px',
              textAlign: 'center',
              backgroundColor: '#090d16',
              borderRadius: '8px',
              border: '1px dashed rgba(255, 255, 255, 0.1)',
              color: '#64748b',
              fontSize: '13px',
            }}
          >
            No task records logged yet. Run your first model in Model Studio.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: '#64748b' }}>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Task ID</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Model</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Status</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Execution Mode</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Timestamp</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tasks.slice(0, 6).map((t) => (
                  <tr
                    key={t.task_id}
                    style={{
                      borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                      transition: 'background-color 0.1s ease',
                    }}
                  >
                    <td style={{ padding: '10px', fontFamily: 'var(--font-mono)', color: '#cbd5e1' }}>
                      {t.task_id.slice(0, 16)}…
                    </td>
                    <td style={{ padding: '10px', fontWeight: 500, color: '#f8fafc' }}>
                      {t.model_name || 'Generic Model'}
                    </td>
                    <td style={{ padding: '10px' }}>
                      <StatusBadge status={t.status} size="sm" />
                    </td>
                    <td style={{ padding: '10px', color: '#94a3b8' }}>
                      {t.mode || 'Distributed P2P'}
                    </td>
                    <td style={{ padding: '10px', color: '#64748b' }}>
                      {timeAgo(t.created_at)}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right' }}>
                      <a
                        href={`/history?task_id=${encodeURIComponent(t.task_id)}`}
                        style={{
                          fontSize: '11px',
                          color: '#60a5fa',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        }}
                      >
                        Inspect Details →
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppLayout>
  )
}
