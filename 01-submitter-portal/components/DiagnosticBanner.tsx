import React, { useState } from 'react'

interface DiagnosticBannerProps {
  error: string
  onDismiss?: () => void
  onRetry?: () => void
}

interface Diagnosis {
  title: string
  summary: string
  recommendations: string[]
  severity: 'warning' | 'danger'
}

export function diagnoseError(rawError: string): Diagnosis {
  const err = rawError.toLowerCase()

  if (err.includes('can host') && err.includes('layers')) {
    return {
      title: 'Insufficient Provider Memory Headroom',
      summary: 'Connected provider PCs do not have enough combined free RAM to host all required transformer layers for this model.',
      recommendations: [
        'Close heavy background applications (browsers, IDEs, games) on connected provider PCs to free up memory.',
        'Connect an additional PC to the coordinator using the join code to distribute the remaining layers.',
        'Choose a smaller model architecture (such as BLOOMZ 560M) which requires less memory per layer.',
      ],
      severity: 'warning',
    }
  }

  if (err.includes('petals server exited (1)') || err.includes('exited (1)')) {
    return {
      title: 'Provider Container Runtime Failure (Exit Code 1)',
      summary: 'The model server container process on the provider PC terminated unexpectedly while attempting to load or serve its assigned layers.',
      recommendations: [
        'Inspect the Provider Desktop application or PowerShell console window on that PC for Python tracebacks.',
        'Verify Docker Desktop is actively running and responsive on the provider machine.',
        'Check that the provider has at least 3.5 GB of free, uncommitted physical RAM.',
        'Restart the provider application on the affected PC and retry.',
      ],
      severity: 'danger',
    }
  }

  if (err.includes('dht bootstrap') || err.includes('firewall') || err.includes('31331') || err.includes('relay could not connect')) {
    return {
      title: 'Network & Port Ingress Blocked',
      summary: 'The provider machine cannot reach the coordinator DHT overlay port 31331. This is typically caused by Windows Firewall blocking incoming peer connections.',
      recommendations: [
        'Run `open_firewall_ports.bat` as Administrator on the Coordinator PC to allow TCP ports 31330 and 31331.',
        'Confirm both the coordinator and provider PCs are connected to the same Wi-Fi router or LAN subnet.',
        'Verify that the provider desktop app is pointed to the correct LAN IP address shown in Network Settings.',
      ],
      severity: 'danger',
    }
  }

  if (err.includes('422') || err.includes('unprocessable entity') || err.includes('schema')) {
    return {
      title: 'Invalid Model Configuration Schema',
      summary: 'The submitted model configuration contains invalid fields or an unsupported model identifier.',
      recommendations: [
        'Select a verified model from the catalog: `bigscience/bloomz-560m`, `TinyLlama/TinyLlama-1.1B-Chat-v1.0`, or `bigscience/bloom-560m`.',
        'Verify parameters: `max_new_tokens` must be an integer between 1 and 128, `prompt` cannot be empty.',
      ],
      severity: 'warning',
    }
  }

  if (err.includes('gateway') || err.includes('502') || err.includes('could not reach')) {
    return {
      title: 'Coordinator Service Unreachable',
      summary: 'The Submitter Portal cannot communicate with the ComputeTorrent coordinator container on port 8001.',
      recommendations: [
        'Check Docker Desktop to ensure the `computetorrent-orchestrator` container is running.',
        'Verify network bridge connectivity using `docker ps`.',
      ],
      severity: 'danger',
    }
  }

  return {
    title: 'Execution Error Encountered',
    summary: rawError,
    recommendations: [
      'Check system logs and provider statuses.',
      'Retry the operation once cluster resources stabilize.',
    ],
    severity: 'danger',
  }
}

export default function DiagnosticBanner({ error, onDismiss, onRetry }: DiagnosticBannerProps) {
  const [showTechnical, setShowTechnical] = useState(false)
  if (!error) return null

  const diagnosis = diagnoseError(error)
  const isDanger = diagnosis.severity === 'danger'

  const border = isDanger ? 'rgba(244, 63, 94, 0.3)' : 'rgba(245, 158, 11, 0.3)'
  const bg = isDanger ? 'rgba(244, 63, 94, 0.08)' : 'rgba(245, 158, 11, 0.08)'
  const titleColor = isDanger ? '#fb7185' : '#fbbf24'

  return (
    <div
      style={{
        backgroundColor: bg,
        border: `1px solid ${border}`,
        borderRadius: '10px',
        padding: '14px 18px',
        marginBottom: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '16px' }}>{isDanger ? '❌' : '⚠️'}</span>
          <span style={{ fontSize: '14px', fontWeight: 600, color: titleColor }}>
            {diagnosis.title}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {onRetry && (
            <button
              onClick={onRetry}
              style={{
                fontSize: '12px',
                padding: '3px 10px',
                borderRadius: '6px',
                backgroundColor: 'rgba(255, 255, 255, 0.08)',
                color: '#f8fafc',
                border: '1px solid rgba(255, 255, 255, 0.15)',
              }}
            >
              Retry
            </button>
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              style={{
                fontSize: '12px',
                padding: '3px 8px',
                color: '#94a3b8',
                borderRadius: '6px',
              }}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>

      <p style={{ fontSize: '13px', color: '#e2e8f0', margin: 0, lineHeight: '1.5' }}>
        {diagnosis.summary}
      </p>

      {/* Actionable Recovery Checklist */}
      <div style={{ backgroundColor: 'rgba(0, 0, 0, 0.25)', borderRadius: '8px', padding: '10px 14px' }}>
        <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '6px' }}>
          Recommended Next Steps:
        </span>
        <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: '#cbd5e1', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {diagnosis.recommendations.map((rec, i) => (
            <li key={i}>{rec}</li>
          ))}
        </ul>
      </div>

      {/* Technical Diagnostics Expander */}
      <div>
        <button
          onClick={() => setShowTechnical(!showTechnical)}
          style={{
            fontSize: '11px',
            color: '#94a3b8',
            textDecoration: 'underline',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          {showTechnical ? 'Hide Technical Error' : 'View Technical Error Details'}
        </button>
        {showTechnical && (
          <pre
            style={{
              marginTop: '8px',
              padding: '10px',
              backgroundColor: '#090d16',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              fontSize: '11px',
              color: '#f43f5e',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
            }}
          >
            {error}
          </pre>
        )}
      </div>
    </div>
  )
}
