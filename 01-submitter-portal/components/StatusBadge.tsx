import React from 'react'

interface StatusBadgeProps {
  status: string
  label?: string
  size?: 'sm' | 'md'
  showDot?: boolean
}

export default function StatusBadge({ status, label, size = 'md', showDot = true }: StatusBadgeProps) {
  const norm = (status || '').toLowerCase().trim()

  let color = 'default'
  let display = label || status || 'Unknown'

  if (['healthy', 'ready', 'online', 'serving', 'completed', 'verified', 'active'].includes(norm)) {
    color = 'success'
  } else if (['busy', 'running', 'profiling_capacity', 'assigning', 'downloading_model', 'connecting_layers', 'loading', 'loading_reference', 'verifying'].includes(norm)) {
    color = 'info'
  } else if (['idle', 'paused', 'checking', 'pending', 'queued', 'warn'].includes(norm)) {
    color = 'warning'
  } else if (['failed', 'error', 'offline', 'stopped', 'disconnected', 'unavailable', 'revoked'].includes(norm)) {
    color = 'danger'
  }

  const styles: Record<string, { bg: string; text: string; border: string; dot: string }> = {
    success: {
      bg: 'rgba(16, 185, 129, 0.12)',
      text: '#34d399',
      border: 'rgba(16, 185, 129, 0.25)',
      dot: '#10b981',
    },
    info: {
      bg: 'rgba(59, 130, 246, 0.12)',
      text: '#60a5fa',
      border: 'rgba(59, 130, 246, 0.25)',
      dot: '#3b82f6',
    },
    warning: {
      bg: 'rgba(245, 158, 11, 0.12)',
      text: '#fbbf24',
      border: 'rgba(245, 158, 11, 0.25)',
      dot: '#f59e0b',
    },
    danger: {
      bg: 'rgba(244, 63, 94, 0.12)',
      text: '#fb7185',
      border: 'rgba(244, 63, 94, 0.25)',
      dot: '#f43f5e',
    },
    default: {
      bg: 'rgba(148, 163, 184, 0.1)',
      text: '#94a3b8',
      border: 'rgba(148, 163, 184, 0.2)',
      dot: '#64748b',
    },
  }

  const s = styles[color]

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: size === 'sm' ? '4px' : '6px',
        padding: size === 'sm' ? '2px 6px' : '3px 8px',
        borderRadius: '9999px',
        fontSize: size === 'sm' ? '11px' : '12px',
        fontWeight: 500,
        backgroundColor: s.bg,
        color: s.text,
        border: `1px solid ${s.border}`,
        whiteSpace: 'nowrap',
        textTransform: 'capitalize',
      }}
    >
      {showDot && (
        <span
          style={{
            width: size === 'sm' ? '5px' : '6px',
            height: size === 'sm' ? '5px' : '6px',
            borderRadius: '50%',
            backgroundColor: s.dot,
            display: 'inline-block',
          }}
        />
      )}
      {display}
    </span>
  )
}
