import React from 'react'
import StatusBadge from './StatusBadge'

interface Stage {
  node_id: string
  start: number
  end: number
  device?: string
  capacity_layers?: number
  allocation_basis?: string
  allocation_weight?: number
  transport?: string
}

interface LayerPipelineVisualizerProps {
  totalLayers?: number
  plan?: Stage[]
  stageStatus?: Record<string, any>
  jobStatus?: string
}

const PEER_COLORS = [
  { bar: '#3b82f6', bg: 'rgba(59, 130, 246, 0.1)', border: 'rgba(59, 130, 246, 0.3)', text: '#93c5fd' },
  { bar: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.1)', border: 'rgba(139, 92, 246, 0.3)', text: '#c4b5fd' },
  { bar: '#10b981', bg: 'rgba(16, 185, 129, 0.1)', border: 'rgba(16, 185, 129, 0.3)', text: '#6ee7b7' },
  { bar: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)', border: 'rgba(245, 158, 11, 0.3)', text: '#fcd34d' },
]

export default function LayerPipelineVisualizer({
  totalLayers = 22,
  plan = [],
  stageStatus = {},
  jobStatus,
}: LayerPipelineVisualizerProps) {
  if (!plan || plan.length === 0) {
    return (
      <div
        style={{
          padding: '24px',
          backgroundColor: '#090d16',
          border: '1px dashed rgba(255, 255, 255, 0.1)',
          borderRadius: '8px',
          textAlign: 'center',
          color: '#64748b',
          fontSize: '13px',
        }}
      >
        Waiting for layer allocation plan from coordinator…
      </div>
    )
  }

  const computedTotal = totalLayers || plan.reduce((acc, s) => Math.max(acc, s.end), 0) || 22

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {/* Horizontal Contiguous Pipeline Bar */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
          <span>Layer 0 (Input Embedding)</span>
          <span>Layer {computedTotal - 1} (LM Head)</span>
        </div>

        <div
          style={{
            display: 'flex',
            height: '24px',
            borderRadius: '6px',
            overflow: 'hidden',
            backgroundColor: '#090d16',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            position: 'relative',
          }}
        >
          {plan.map((stage, idx) => {
            const count = stage.end - stage.start
            const pct = Math.max(5, (count / computedTotal) * 100)
            const color = PEER_COLORS[idx % PEER_COLORS.length]
            const status = stageStatus[stage.node_id]?.status || (jobStatus === 'completed' ? 'serving' : 'assigned')
            const isFailed = status === 'failed' || (jobStatus === 'failed' && idx === 0)

            return (
              <div
                key={stage.node_id || idx}
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  backgroundColor: isFailed ? '#f43f5e' : color.bar,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ffffff',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRight: idx < plan.length - 1 ? '2px solid #090d16' : 'none',
                  transition: 'width 0.3s ease',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap',
                  padding: '0 4px',
                }}
                title={`Peer ${idx + 1}: Layers ${stage.start}–${stage.end - 1} (${count} layers)`}
              >
                L{stage.start}–{stage.end - 1}
              </div>
            )
          })}
        </div>
      </div>

      {/* Peer Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(auto-fit, minmax(240px, 1fr))`,
          gap: '12px',
        }}
      >
        {plan.map((stage, idx) => {
          const color = PEER_COLORS[idx % PEER_COLORS.length]
          const statusInfo: any = stageStatus[stage.node_id] || {}
          const currentStageStatus = statusInfo.status || (jobStatus === 'completed' ? 'serving' : jobStatus || 'pending')
          const transport = statusInfo.transport || stage.transport || 'Direct LAN'
          const count = stage.end - stage.start

          return (
            <div
              key={stage.node_id || idx}
              style={{
                backgroundColor: color.bg,
                border: `1px solid ${color.border}`,
                borderRadius: '8px',
                padding: '12px 14px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: color.text, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  PEER {idx + 1} · {stage.device?.toUpperCase() || 'CPU'}
                </span>
                <StatusBadge status={currentStageStatus} size="sm" />
              </div>

              <div>
                <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
                  Layers {stage.start}–{stage.end - 1}
                </div>
                <div style={{ fontSize: '12px', color: '#94a3b8', fontFamily: 'var(--font-mono)' }}>
                  {stage.node_id.length > 16 ? stage.node_id.slice(-12) : stage.node_id}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#cbd5e1', paddingTop: '6px', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
                <span>{count} Layers Assigned</span>
                <span style={{ color: '#94a3b8' }}>
                  {transport === 'wss' ? '🌐 WSS Relay' : '🏠 Direct LAN'}
                </span>
              </div>

              {stage.capacity_layers != null && (
                <div style={{ fontSize: '11px', color: '#64748b' }}>
                  Headroom: {stage.capacity_layers} max layers
                  {stage.allocation_basis === 'native_inference_rps' && stage.allocation_weight ? ` (${stage.allocation_weight} blk/s)` : ''}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
