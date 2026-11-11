import React, { useState } from 'react'
import Link from 'next/link'
import AppLayout from '../components/AppLayout'
import { DataState, Metrics, useData } from '../components/Data'
import { Empty, Pagination, ResourceError, Section } from '../components/UI'
import StatusBadge from '../components/StatusBadge'
import { cleanCpuName, connected, dateText, modelName, number, seconds } from '../lib/portal'

export default function Monitoring() {
  const { resources, nodes, jobs } = useData()
  const [page, setPage] = useState(1)
  const online = nodes.filter(connected)
  const reported = online.filter(n => typeof n.profile?.cpu_load_pct === 'number')
  const cpu = reported.length ? reported.reduce((sum, n) => sum + n.profile.cpu_load_pct, 0) / reported.length : null
  const timed = jobs.filter(
    j =>
      j.metrics &&
      Number.isFinite(j.metrics.model_load_seconds) &&
      Number.isFinite(j.metrics.distributed_generation_seconds) &&
      Number.isFinite(j.metrics.generated_tokens) &&
      Number.isFinite(j.metrics.total_seconds)
  )
  const pageSize = 8
  const totalPages = Math.max(1, Math.ceil(timed.length / pageSize))
  const currentPage = Math.min(page, totalPages)
  const paged = timed.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  return (
    <AppLayout title="Monitoring" subtitle="Current resource snapshots and recorded run timings. No synthetic telemetry.">
      <ResourceError names={['health', 'capacity', 'nodes', 'jobs', 'network']} />
      <Metrics
        items={[
          { label: 'Connected computers', value: resources.nodes?.updated ? online.length : '—', note: 'Recent control heartbeat', icon: 'nodes' },
          { label: 'Mean reported CPU load', value: cpu === null ? '—' : `${number(cpu, 1)}%`, note: `${reported.length} connected nodes reporting`, icon: 'activity' },
          { label: 'Current RAM telemetry', value: online.filter(n => typeof n.profile?.free_ram_gb === 'number').length, note: 'Connected nodes reporting free RAM', icon: 'nodes' },
          { label: 'Model gateway', value: resources.capacity?.data?.status === 'ready' ? 'Ready' : resources.capacity?.data?.status ? 'Unavailable' : '—', note: 'Control check, not route proof', icon: 'model' },
        ]}
      />
      <div className="grid-two">
        <Section title="Current resources" note="Per-node values from the latest provider reports.">
          <DataState name="nodes">
            {!online.length ? (
              <Empty title="No connected resources">Connect a provider to see reported CPU and memory availability.</Empty>
            ) : (
              online.map(n => {
                const p = n.profile || {}
                const ram = typeof p.RAM === 'number' && p.RAM > 0 && typeof p.free_ram_gb === 'number'
                  ? Math.max(0, Math.min(100, (100 * (p.RAM - p.free_ram_gb)) / p.RAM))
                  : null
                return (
                  <div className="panel-body" key={n.node_id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <div className="inline-actions" style={{ justifyContent: 'space-between' }}>
                      <Link className="text-link" href={`/nodes?id=${encodeURIComponent(n.node_id)}`}>
                        {cleanCpuName(p.cpu_model)}
                      </Link>
                      <StatusBadge status={n.state} />
                    </div>
                    <div className="grid-equal" style={{ marginTop: 15 }}>
                      <div>
                        <small>CPU LOAD · {typeof p.cpu_load_pct === 'number' ? number(p.cpu_load_pct, 1) + '%' : 'NOT REPORTED'}</small>
                        {typeof p.cpu_load_pct === 'number' && (
                          <div className="resource-bar" role="meter" aria-label="CPU load" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p.cpu_load_pct}>
                            <span style={{ width: `${Math.max(0, Math.min(100, p.cpu_load_pct))}%` }} />
                          </div>
                        )}
                      </div>
                      <div>
                        <small>RAM IN USE · {ram === null ? 'NOT REPORTED' : number(ram, 1) + '%'}</small>
                        {ram !== null && (
                          <div className="resource-bar" role="meter" aria-label="RAM used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={ram}>
                            <span style={{ width: `${ram}%` }} />
                          </div>
                        )}
                        <small>
                          {number(p.free_ram_gb, 1)} GB free / {number(p.RAM, 1)} GB total
                        </small>
                      </div>
                    </div>
                    <small>Control update {number(n.control_age_seconds)}s ago · No historical series retained here</small>
                  </div>
                )
              })
            )}
          </DataState>
        </Section>
        <div>
          <Section title="Component checks">
            {[
              ['Coordinator', resources.health?.data?.status],
              ['Model gateway', resources.capacity?.data?.status],
            ].map(([label, status]) => (
              <div className="list-row" key={label}>
                <span>{label}</span>
                <StatusBadge status={status} />
              </div>
            ))}
            <div className="panel-body">
              <p style={{ fontSize: 12 }}>
                Control connectivity and model data routes are separate. Latency, bandwidth, and packet loss are not reported by this portal API.
              </p>
              <Link className="text-link" href="/settings">
                Inspect network configuration →
              </Link>
            </div>
          </Section>
          <Section title="Snapshot freshness">
            <div className="panel-body">
              <dl className="detail-grid">
                {['nodes', 'jobs', 'health', 'capacity'].map(k => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>
                      {resources[k]?.updated ? new Date(resources[k].updated!).toLocaleTimeString() : 'Not received'}
                      {resources[k]?.error ? ' · stale/unavailable' : ''}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </Section>
        </div>
      </div>
      <Section title="Recorded performance" note="Measured timings from completed runs, sorted newest first.">
        {timed.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Recorded at</th>
                    <th>Preparation</th>
                    <th>Generation</th>
                    <th>Tokens</th>
                    <th>Total time</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map(j => (
                    <tr key={j.id}>
                      <td>
                        <Link className="text-link" href={`/deployments?id=${j.id}`}>
                          {modelName(j.spec?.model_id)}
                        </Link>
                      </td>
                      <td>{dateText(j.updated_at)}</td>
                      <td>{seconds(j.metrics.model_load_seconds)}</td>
                      <td>{seconds(j.metrics.distributed_generation_seconds)}</td>
                      <td>{number(j.metrics.generated_tokens)}</td>
                      <td>{seconds(j.metrics.total_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={currentPage} setPage={setPage} total={timed.length} size={pageSize} />
          </>
        ) : (
          <Empty title="No run timings yet">Metrics will appear after the coordinator records a model run.</Empty>
        )}
      </Section>
    </AppLayout>
  )
}
