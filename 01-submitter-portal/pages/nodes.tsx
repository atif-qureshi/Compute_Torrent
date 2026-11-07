import React, { useCallback, useEffect, useState } from 'react'
import AppLayout from '../components/AppLayout'
import StatusBadge from '../components/StatusBadge'
import Modal from '../components/Modal'
import DiagnosticBanner from '../components/DiagnosticBanner'

const API = '/api/ct'

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
  if (!value) return 'Unknown'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return 'Unknown'
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export default function Nodes() {
  const [seeders, setSeeders] = useState<any[]>([])
  const [distStatus, setDistStatus] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'ready' | 'online' | 'offline'>('all')
  const [selectedNode, setSelectedNode] = useState<any>(null)
  const [error, setError] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Enrollment helper state
  const [enrollmentToken, setEnrollmentToken] = useState('')
  const [lanAddress, setLanAddress] = useState('')
  const [copiedToken, setCopiedToken] = useState(false)
  const [copiedLan, setCopiedLan] = useState(false)

  const loadData = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const [seedersRes, distRes, addrRes] = await Promise.all([
        fetch(`${API}/seeders`).then(responseJson),
        fetch(`${API}/distributed/status`).then(responseJson),
        fetch('/api/provider-address').then(responseJson),
      ])
      setSeeders(seedersRes || [])
      setDistStatus(distRes || null)
      if (addrRes) {
        setEnrollmentToken(addrRes.enrollment_token || '')
        setLanAddress(addrRes.lan_address || '')
      }
      setError('')
    } catch (err: any) {
      setError(err.message || 'Failed to fetch provider nodes')
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    const timer = setInterval(loadData, 5000)
    return () => clearInterval(timer)
  }, [loadData])

  const revokeProvider = async (nodeId: string) => {
    if (!window.confirm(`Revoke authentication credentials for ${nodeId}? This machine will need the join token to re-enroll.`)) {
      return
    }
    try {
      await responseJson(await fetch(`${API}/seeders/${encodeURIComponent(nodeId)}/credential`, { method: 'DELETE' }))
      await loadData()
    } catch (err: any) {
      setError(err.message || 'Could not revoke provider')
    }
  }

  // Filter and search
  const filteredSeeders = seeders.filter((node) => {
    const isOnline = (
      typeof node.control_age_seconds === 'number' ||
      ['online', 'idle', 'busy', 'paused'].includes(node.state || node.status)
    )
    const distPeer = distStatus?.providers?.find((p: any) => p.node_id === node.node_id)
    const isReady = distPeer ? distPeer.layer_ready : node.profile?.docker_ok

    if (filter === 'ready' && !isReady) return false
    if (filter === 'online' && !isOnline) return false
    if (filter === 'offline' && isOnline) return false

    if (search.trim()) {
      const term = search.toLowerCase()
      const matchId = node.node_id.toLowerCase().includes(term)
      const matchCpu = (node.profile?.cpu_model || '').toLowerCase().includes(term)
      const matchGpu = (node.profile?.GPU || '').toLowerCase().includes(term)
      return matchId || matchCpu || matchGpu
    }
    return true
  })

  return (
    <AppLayout
      title="Compute Nodes"
      subtitle="Manage enrolled provider hardware, telemetry, layer readiness, and network credentials."
      actions={
        <button
          onClick={loadData}
          style={{
            padding: '6px 12px',
            backgroundColor: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '6px',
            fontSize: '12px',
            color: '#cbd5e1',
          }}
        >
          {isRefreshing ? '🔄 Refreshing…' : '↻ Refresh Status'}
        </button>
      }
    >
      {error && (
        <DiagnosticBanner
          error={error}
          onDismiss={() => setError('')}
          onRetry={loadData}
        />
      )}

      {/* Top Header Card: Quick Setup / Enrollment Banner */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '18px 22px',
          marginBottom: '24px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
        }}
      >
        <div>
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
            🔑 Provider Client Enrollment
          </h2>
          <p style={{ fontSize: '12px', color: '#94a3b8', margin: '4px 0 0' }}>
            New volunteer client machines use this token and address to join your local compute cluster.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Join Token Box */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
              Join Token:
            </span>
            <code style={{ fontSize: '12px', color: '#fbbf24', backgroundColor: '#090d16', padding: '4px 8px', borderRadius: '4px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
              {enrollmentToken || 'Unavailable'}
            </code>
            <button
              onClick={() => {
                if (!enrollmentToken) return
                navigator.clipboard.writeText(enrollmentToken)
                setCopiedToken(true)
                setTimeout(() => setCopiedToken(false), 2000)
              }}
              style={{
                padding: '4px 8px',
                backgroundColor: '#3b82f6',
                color: '#ffffff',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
              }}
            >
              {copiedToken ? '✅' : 'Copy'}
            </button>
          </div>

          {/* LAN Address Box */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
              LAN Address:
            </span>
            <code style={{ fontSize: '12px', color: '#60a5fa', backgroundColor: '#090d16', padding: '4px 8px', borderRadius: '4px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
              {lanAddress || 'ws://192.168.100.7:8001/ws/seeder'}
            </code>
            <button
              onClick={() => {
                navigator.clipboard.writeText(lanAddress)
                setCopiedLan(true)
                setTimeout(() => setCopiedLan(false), 2000)
              }}
              style={{
                padding: '4px 8px',
                backgroundColor: 'rgba(255, 255, 255, 0.08)',
                color: '#f8fafc',
                borderRadius: '4px',
                fontSize: '11px',
              }}
            >
              {copiedLan ? '✅' : 'Copy'}
            </button>
          </div>
        </div>
      </section>

      {/* Table Section with Filter & Search Controls */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '20px',
        }}
      >
        {/* Controls Bar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
            marginBottom: '16px',
          }}
        >
          {/* Filter Tabs */}
          <div
            style={{
              display: 'inline-flex',
              backgroundColor: '#090d16',
              padding: '3px',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {(['all', 'ready', 'online', 'offline'] as const).map((tab) => {
              const active = filter === tab
              const labels = {
                all: `All (${seeders.length})`,
                ready: 'Layer Ready',
                online: 'Online',
                offline: 'Offline',
              }
              return (
                <button
                  key={tab}
                  onClick={() => setFilter(tab)}
                  style={{
                    padding: '4px 12px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: active ? 600 : 500,
                    backgroundColor: active ? '#3b82f6' : 'transparent',
                    color: active ? '#ffffff' : '#94a3b8',
                  }}
                >
                  {labels[tab]}
                </button>
              )
            })}
          </div>

          {/* Search Input */}
          <div style={{ minWidth: '260px' }}>
            <input
              type="text"
              placeholder="Search by Node ID, CPU or GPU…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: '#090d16',
                fontSize: '12px',
                padding: '6px 12px',
              }}
            />
          </div>
        </div>

        {/* Data Table */}
        {filteredSeeders.length === 0 ? (
          <div
            style={{
              padding: '40px',
              textAlign: 'center',
              backgroundColor: '#090d16',
              borderRadius: '8px',
              border: '1px dashed rgba(255, 255, 255, 0.1)',
              color: '#64748b',
              fontSize: '13px',
            }}
          >
            No provider nodes matched the selected filter or search query.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: '#64748b', fontSize: '12px' }}>
                  <th style={{ padding: '10px 12px', fontWeight: 600 }}>Node Identifier</th>
                  <th style={{ padding: '10px 12px', fontWeight: 600 }}>CPU & Architecture</th>
                  <th style={{ padding: '10px 12px', fontWeight: 600 }}>System Memory</th>
                  <th style={{ padding: '10px 12px', fontWeight: 600 }}>GPU Accelerator</th>
                  <th style={{ padding: '10px 12px', fontWeight: 600 }}>Connection</th>
                  <th style={{ padding: '10px 12px', fontWeight: 600 }}>Layer Readiness</th>
                  <th style={{ padding: '10px 12px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredSeeders.map((node) => {
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
                      <td style={{ padding: '12px' }}>
                        <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#f8fafc', fontSize: '12px' }}>
                          {node.node_id.slice(-12)}
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>
                          Last seen {timeAgo(node.last_seen_at || node.updated_at)}
                        </div>
                      </td>

                      <td style={{ padding: '12px' }}>
                        <div style={{ fontWeight: 500, color: '#f8fafc' }}>
                          {prof.cpu_model || 'Standard CPU'}
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>
                          {prof.cpu_cores || prof.physical_cores || '—'} Cores · Tier {node.tier || prof.tier || 2}
                        </div>
                      </td>

                      <td style={{ padding: '12px' }}>
                        <div style={{ fontWeight: 500, color: '#cbd5e1' }}>
                          {prof.RAM || '—'} GB RAM
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>
                          {distPeer?.profile?.free_ram_gb ? `${distPeer.profile.free_ram_gb} GB Free` : 'Direct OS'}
                        </div>
                      </td>

                      <td style={{ padding: '12px' }}>
                        <div style={{ color: prof.GPU && !prof.GPU.toLowerCase().includes('none') ? '#a78bfa' : '#64748b' }}>
                          {prof.GPU && !prof.GPU.toLowerCase().includes('none') ? prof.GPU : 'CPU Provider'}
                        </div>
                      </td>

                      <td style={{ padding: '12px' }}>
                        <StatusBadge status={isOnline ? (node.state || 'online') : 'offline'} size="sm" />
                        {typeof node.control_age_seconds === 'number' && (
                          <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
                            Heartbeat {Math.round(node.control_age_seconds)}s ago
                          </div>
                        )}
                      </td>

                      <td style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '11px', color: isReady ? '#34d399' : '#fbbf24', fontWeight: 500 }}>
                            {isReady ? '✅ Ready' : '⚠️ Pending'}
                          </span>
                        </div>
                        {distPeer?.layer_reason && (
                          <div style={{ fontSize: '10px', color: '#64748b' }}>
                            {distPeer.layer_reason}
                          </div>
                        )}
                      </td>

                      <td style={{ padding: '12px', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '6px' }}>
                          <button
                            onClick={() => setSelectedNode({ ...node, distPeer })}
                            style={{
                              padding: '4px 10px',
                              backgroundColor: 'rgba(255, 255, 255, 0.05)',
                              border: '1px solid rgba(255, 255, 255, 0.1)',
                              borderRadius: '4px',
                              fontSize: '11px',
                              color: '#cbd5e1',
                            }}
                          >
                            Inspect
                          </button>
                          <button
                            onClick={() => revokeProvider(node.node_id)}
                            style={{
                              padding: '4px 8px',
                              backgroundColor: 'rgba(244, 63, 94, 0.08)',
                              border: '1px solid rgba(244, 63, 94, 0.2)',
                              borderRadius: '4px',
                              fontSize: '11px',
                              color: '#fb7185',
                            }}
                            title="Revoke node credentials"
                          >
                            Revoke
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Node Hardware Detail Modal */}
      {selectedNode && (
        <Modal
          isOpen={Boolean(selectedNode)}
          onClose={() => setSelectedNode(null)}
          title={`Node Details: ${selectedNode.node_id.slice(-12)}`}
          subtitle={`Hardware inventory, telemetry & protocol status`}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Grid of Telemetry */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '12px',
                backgroundColor: '#090d16',
                padding: '14px',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Processor / CPU</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                  {selectedNode.profile?.cpu_model || '—'}
                </span>
              </div>

              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Cores</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                  {selectedNode.profile?.cpu_cores || '—'} Cores ({selectedNode.profile?.physical_cores || '—'} Physical)
                </span>
              </div>

              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Total RAM</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                  {selectedNode.profile?.RAM || '—'} GB
                </span>
              </div>

              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Free RAM (Telemetry)</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#34d399' }}>
                  {selectedNode.distPeer?.profile?.free_ram_gb ?? '—'} GB
                </span>
              </div>

              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>GPU Device</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#a78bfa' }}>
                  {selectedNode.profile?.GPU || 'CPU Only'}
                </span>
              </div>

              <div>
                <span style={{ fontSize: '11px', color: '#64748b', display: 'block' }}>Docker Runtime</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: selectedNode.profile?.docker_ok ? '#34d399' : '#fbbf24' }}>
                  {selectedNode.profile?.docker_ok ? '✅ Operational' : '❌ Not Available'}
                </span>
              </div>
            </div>

            {/* Protocol & Registration Info */}
            <div>
              <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '6px' }}>
                Full Node Identifier
              </span>
              <code style={{ fontSize: '12px', display: 'block', padding: '8px', backgroundColor: '#090d16', borderRadius: '4px', wordBreak: 'break-all' }}>
                {selectedNode.node_id}
              </code>
            </div>

            {selectedNode.distPeer?.layer_reason && (
              <div style={{ padding: '10px 14px', backgroundColor: 'rgba(245, 158, 11, 0.08)', borderRadius: '6px', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#fbbf24', display: 'block' }}>
                  Layer Allocation Status:
                </span>
                <p style={{ fontSize: '12px', color: '#cbd5e1', margin: '2px 0 0' }}>
                  {selectedNode.distPeer.layer_reason}
                </p>
              </div>
            )}
          </div>
        </Modal>
      )}
    </AppLayout>
  )
}
