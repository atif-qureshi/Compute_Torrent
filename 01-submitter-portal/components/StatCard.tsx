import React from 'react'

interface StatCardProps {
  label: string
  value: React.ReactNode
  subtext?: string
  icon?: string
  trend?: string
  statusColor?: 'emerald' | 'blue' | 'purple' | 'amber' | 'rose'
}

export default function StatCard({
  label,
  value,
  subtext,
  icon,
  statusColor,
}: StatCardProps) {
  const accentBorder = {
    emerald: 'rgba(16, 185, 129, 0.25)',
    blue: 'rgba(59, 130, 246, 0.25)',
    purple: 'rgba(139, 92, 246, 0.25)',
    amber: 'rgba(245, 158, 11, 0.25)',
    rose: 'rgba(244, 63, 94, 0.25)',
  }[statusColor || 'blue']

  return (
    <div
      style={{
        backgroundColor: '#0f172a',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '10px',
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        position: 'relative',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.2)',
        transition: 'border-color 0.15s ease',
      }}
    >
      {/* Subtle top indicator bar */}
      {statusColor && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '2px',
            backgroundColor: accentBorder,
          }}
        />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {label}
        </span>
        {icon && (
          <span style={{ fontSize: '16px', opacity: 0.85 }}>{icon}</span>
        )}
      </div>

      <div style={{ fontSize: '24px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.02em', margin: '2px 0 6px' }}>
        {value}
      </div>

      {subtext && (
        <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '4px' }}>
          {subtext}
        </div>
      )}
    </div>
  )
}
