import React, { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import AppLayout from '../components/AppLayout'
import StatusBadge from '../components/StatusBadge'
import DiagnosticBanner from '../components/DiagnosticBanner'

const API = '/api/ct'

export default function History() {
  const router = useRouter()
  const [tasks, setTasks] = useState<any[]>([])
  const [selected, setSelected] = useState<any>(null)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [copiedText, setCopiedText] = useState(false)

  const loadTasks = useCallback(() => {
    fetch(`${API}/history?submitter_id=web-portal`)
      .then(async (res) => {
        if (!res.ok) throw new Error('Failed to load task history')
        return res.json()
      })
      .then((data) => {
        setTasks(data || [])
        setError('')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadTasks()
    const timer = setInterval(loadTasks, 5000)
    return () => clearInterval(timer)
  }, [loadTasks])

  // Single task inspector loader
  const loadTaskDetails = useCallback(async (id: string) => {
    try {
      const response = await fetch(`${API}/tasks/${encodeURIComponent(id)}`)
      if (!response.ok) {
        let msg = 'Could not load task details'
        try { msg = (await response.json()).detail || msg } catch { /* ignore */ }
        throw new Error(msg)
      }
      setSelected(await response.json())
      setError('')
    } catch (reason: any) {
      setError(reason.message || 'Could not load task details')
    }
  }, [])

  useEffect(() => {
    const id = router.query.task_id
    if (router.isReady && typeof id === 'string' && id !== selected?.task_id) {
      void loadTaskDetails(id)
    }
  }, [router.isReady, router.query.task_id, selected?.task_id, loadTaskDetails])

  const openTask = (id: string) => {
    void router.push({ pathname: '/history', query: { task_id: id } }, undefined, { shallow: true })
    void loadTaskDetails(id)
  }

  const downloadResult = () => {
    if (!selected) return
    const blob = new Blob([JSON.stringify(selected, null, 2)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `task-${selected.task_id}-receipt.json`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  const copyResult = () => {
    const text = selected?.result?.text || (typeof selected?.result === 'string' ? selected.result : JSON.stringify(selected?.result))
    if (text) {
      navigator.clipboard.writeText(text)
      setCopiedText(true)
      setTimeout(() => setCopiedText(false), 2000)
    }
  }

  const filteredTasks = tasks.filter((t) => {
    if (filter !== 'all' && t.status !== filter) return false
    if (search.trim()) {
      const term = search.toLowerCase()
      const matchId = (t.task_id || '').toLowerCase().includes(term)
      const matchModel = (t.model_name || '').toLowerCase().includes(term)
      return matchId || matchModel
    }
    return true
  })

  return (
    <AppLayout
      title="Task Audit & Execution History"
      subtitle="Task execution history, provider allocations, and verification logs."
      actions={
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
          + Submit New Task
        </a>
      }
    >
      {error && (
        <DiagnosticBanner
          error={error}
          onDismiss={() => setError('')}
        />
      )}

      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1.2fr 1fr' : '1fr', gap: '24px' }}>
        {/* Left Column: Task Table */}
        <section
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '10px',
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          {/* Controls Bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                Submissions ({tasks.length})
              </span>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                style={{
                  fontSize: '12px',
                  backgroundColor: '#090d16',
                  color: '#cbd5e1',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '6px',
                  padding: '4px 8px',
                }}
              >
                <option value="all">All Statuses</option>
                <option value="pending">Pending</option>
                <option value="allocated">Assigned</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            <input
              type="text"
              placeholder="Search by Task ID or Model…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                fontSize: '12px',
                backgroundColor: '#090d16',
                minWidth: '220px',
                padding: '4px 10px',
              }}
            />
          </div>

          {/* Table */}
          {loading ? (
            <div style={{ padding: '30px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
              Loading audit history…
            </div>
          ) : filteredTasks.length === 0 ? (
            <div
              style={{
                padding: '36px',
                textAlign: 'center',
                backgroundColor: '#090d16',
                borderRadius: '8px',
                border: '1px dashed rgba(255, 255, 255, 0.1)',
                color: '#64748b',
                fontSize: '13px',
              }}
            >
              No task records matched this query.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: '#64748b' }}>
                    <th style={{ padding: '8px 10px', fontWeight: 600 }}>Task Identifier</th>
                    <th style={{ padding: '8px 10px', fontWeight: 600 }}>Model Name</th>
                    <th style={{ padding: '8px 10px', fontWeight: 600 }}>Status</th>
                    <th style={{ padding: '8px 10px', fontWeight: 600 }}>Mode</th>
                    <th style={{ padding: '8px 10px', fontWeight: 600 }}>Timestamp</th>
                    <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTasks.map((t) => {
                    const isSelected = selected?.task_id === t.task_id
                    return (
                      <tr
                        key={t.task_id}
                        style={{
                          borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                          backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.08)' : 'transparent',
                          cursor: 'pointer',
                        }}
                        onClick={() => openTask(t.task_id)}
                      >
                        <td style={{ padding: '10px', fontFamily: 'var(--font-mono)', color: isSelected ? '#60a5fa' : '#cbd5e1' }}>
                          {t.task_id.slice(0, 14)}…
                        </td>
                        <td style={{ padding: '10px', fontWeight: 500, color: '#f8fafc' }}>
                          {t.model_name || 'Generic Task'}
                        </td>
                        <td style={{ padding: '10px' }}>
                          <StatusBadge status={t.status} size="sm" />
                        </td>
                        <td style={{ padding: '10px', color: '#94a3b8' }}>
                          {t.mode || 'WS-RR'}
                        </td>
                        <td style={{ padding: '10px', color: '#64748b' }}>
                          {new Date(t.created_at).toLocaleTimeString()}
                        </td>
                        <td style={{ padding: '10px', textAlign: 'right' }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              openTask(t.task_id)
                            }}
                            style={{
                              fontSize: '11px',
                              color: '#60a5fa',
                              padding: '2px 8px',
                              borderRadius: '4px',
                              backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            }}
                          >
                            Inspect →
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Right Column: Selected Task Inspector */}
        {selected && (
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Task Execution Detail
                </span>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: '2px 0 0' }}>
                  {selected.model_name || 'Task Execution'}
                </h3>
                <code style={{ fontSize: '11px', color: '#64748b', display: 'block', marginTop: '2px' }}>
                  {selected.task_id}
                </code>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setSelected(null)}
                  style={{
                    color: '#94a3b8',
                    fontSize: '16px',
                    padding: '2px 6px',
                  }}
                  title="Close inspector"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Status & Timing */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '8px',
                padding: '12px',
                backgroundColor: '#090d16',
                borderRadius: '8px',
                fontSize: '12px',
              }}
            >
              <div>
                <span style={{ color: '#64748b', display: 'block', fontSize: '11px' }}>Status</span>
                <StatusBadge status={selected.status} size="sm" />
              </div>
              <div>
                <span style={{ color: '#64748b', display: 'block', fontSize: '11px' }}>Created</span>
                <span style={{ color: '#cbd5e1' }}>{new Date(selected.created_at).toLocaleString()}</span>
              </div>
              <div>
                <span style={{ color: '#64748b', display: 'block', fontSize: '11px' }}>Submitter</span>
                <span style={{ color: '#cbd5e1' }}>{selected.submitter_id || 'web-portal'}</span>
              </div>
              <div>
                <span style={{ color: '#64748b', display: 'block', fontSize: '11px' }}>Replicas</span>
                <span style={{ color: '#cbd5e1' }}>{selected.replicas || 1} Peer</span>
              </div>
            </div>

            {/* Error banner if failed */}
            {selected.error && (
              <div style={{ padding: '10px 12px', backgroundColor: 'rgba(244, 63, 94, 0.08)', borderRadius: '6px', border: '1px solid rgba(244, 63, 94, 0.2)', color: '#fb7185', fontSize: '12px' }}>
                ❌ {selected.error}
              </div>
            )}

            {/* Result Payload */}
            {selected.result && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' }}>
                    Execution Result
                  </span>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button
                      onClick={copyResult}
                      style={{
                        padding: '3px 8px',
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '4px',
                        fontSize: '11px',
                        color: '#cbd5e1',
                      }}
                    >
                      {copiedText ? '✅ Copied' : '📄 Copy'}
                    </button>
                    <button
                      onClick={downloadResult}
                      style={{
                        padding: '3px 8px',
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '4px',
                        fontSize: '11px',
                        color: '#cbd5e1',
                      }}
                    >
                      💾 Export JSON
                    </button>
                  </div>
                </div>

                <pre
                  style={{
                    backgroundColor: '#090d16',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '8px',
                    padding: '12px',
                    fontSize: '12px',
                    color: '#f8fafc',
                    maxHeight: '240px',
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    lineHeight: 1.5,
                  }}
                >
                  {typeof selected.result === 'object'
                    ? JSON.stringify(selected.result, null, 2)
                    : selected.result}
                </pre>
              </div>
            )}
          </section>
        )}
      </div>
    </AppLayout>
  )
}
