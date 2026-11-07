import React, { useEffect, useState } from 'react'
import AppLayout from '../components/AppLayout'
import StatCard from '../components/StatCard'
import DiagnosticBanner from '../components/DiagnosticBanner'

const API = '/api/ct'

export default function Credits() {
  const [credits, setCredits] = useState<any>(null)
  const [filter, setFilter] = useState<'all' | 'charges' | 'rewards'>('all')
  const [error, setError] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)

  const load = () => {
    setIsRefreshing(true)
    fetch(`${API}/credits?submitter_id=web-portal`)
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load credit balance')
        setCredits(await response.json())
        setError('')
      })
      .catch((reason) => setError(reason.message))
      .finally(() => setIsRefreshing(false))
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const entries: any[] = credits?.entries || []

  const filteredEntries = entries.filter((e) => {
    if (filter === 'charges') return Number(e.amount) < 0
    if (filter === 'rewards') return Number(e.amount) > 0
    return true
  })

  const totalCharges = entries
    .filter((e) => Number(e.amount) < 0)
    .reduce((sum, e) => sum + Math.abs(Number(e.amount)), 0)

  return (
    <AppLayout
      title="Credits Ledger"
      subtitle="Demonstration accounting balance, compute verification task fees, and volunteer provider incentives."
      actions={
        <button
          onClick={load}
          style={{
            padding: '6px 12px',
            backgroundColor: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '6px',
            fontSize: '12px',
            color: '#cbd5e1',
          }}
        >
          {isRefreshing ? '🔄 Refreshing…' : '↻ Refresh Ledger'}
        </button>
      }
    >
      {error && (
        <DiagnosticBanner
          error={error}
          onDismiss={() => setError('')}
          onRetry={load}
        />
      )}

      {/* Discalimer Callout */}
      <div
        style={{
          padding: '12px 16px',
          backgroundColor: 'rgba(59, 130, 246, 0.06)',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '8px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          fontSize: '12px',
          color: '#cbd5e1',
        }}
      >
        <span style={{ fontSize: '18px' }}>💡</span>
        <span>
          <strong>Pilot Demonstration Ledger:</strong> ComputeTorrent credits record resource accounting, task fees, and volunteer compute contributions within this local cluster. They carry no monetary or cash value.
        </span>
      </div>

      {/* 4 Metric Cards */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        <StatCard
          label="Available Balance"
          value={credits ? `${credits.balance} Credits` : '—'}
          subtext="Allocated operator balance"
          icon="💳"
          statusColor="emerald"
        />

        <StatCard
          label="Unit Task Fee"
          value="1.00 Credit"
          subtext="Standard model verification cost"
          icon="⚡"
          statusColor="blue"
        />

        <StatCard
          label="Total Task Charges"
          value={`-${totalCharges.toFixed(2)}`}
          subtext="Consumed across completed runs"
          icon="📉"
          statusColor="amber"
        />

        <StatCard
          label="Recorded Entries"
          value={entries.length}
          subtext="Signed ledger transactions"
          icon="📜"
          statusColor="purple"
        />
      </section>

      {/* Transactions Table Section */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '20px',
        }}
      >
        {/* Header & Filter */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
              Transaction Activity
            </h2>
            <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
              Historical credits deducted for task execution and distributed to providers.
            </p>
          </div>

          <div
            style={{
              display: 'inline-flex',
              backgroundColor: '#090d16',
              padding: '3px',
              borderRadius: '6px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            {(['all', 'charges', 'rewards'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setFilter(tab)}
                style={{
                  padding: '4px 10px',
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
        </div>

        {filteredEntries.length === 0 ? (
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
            No transaction records found matching this filter.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: '#64748b' }}>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Description</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Entry Type</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Task ID</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>Amount</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'right' }}>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {filteredEntries.map((e, idx) => {
                  const amt = Number(e.amount) || 0
                  const isPositive = amt > 0
                  return (
                    <tr
                      key={e.id || idx}
                      style={{
                        borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                        transition: 'background-color 0.1s ease',
                      }}
                    >
                      <td style={{ padding: '10px', fontWeight: 500, color: '#f8fafc' }}>
                        {e.description || 'Ledger event'}
                      </td>
                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: 'rgba(255, 255, 255, 0.04)',
                            fontSize: '11px',
                            color: '#94a3b8',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {e.entry_type || 'entry'}
                        </span>
                      </td>
                      <td style={{ padding: '10px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
                        {e.task_id ? `${e.task_id.slice(0, 14)}…` : '—'}
                      </td>
                      <td style={{ padding: '10px' }}>
                        <span
                          style={{
                            fontWeight: 600,
                            color: isPositive ? '#34d399' : '#fb7185',
                          }}
                        >
                          {isPositive ? `+${amt.toFixed(2)}` : amt.toFixed(2)} Credits
                        </span>
                      </td>
                      <td style={{ padding: '10px', textAlign: 'right', color: '#64748b' }}>
                        {new Date(e.created_at).toLocaleString()}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </AppLayout>
  )
}
