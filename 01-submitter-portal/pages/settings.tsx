import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import AppLayout from '../components/AppLayout'
import StatusBadge from '../components/StatusBadge'
import DiagnosticBanner from '../components/DiagnosticBanner'

const API = '/api/ct'

export default function Settings() {
  const router = useRouter()
  const [addrInfo, setAddrInfo] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [distStatus, setDistStatus] = useState<any>(null)
  const [error, setError] = useState('')
  const [copiedLan, setCopiedLan] = useState(false)
  const [copiedToken, setCopiedToken] = useState(false)
  const [copiedPortScript, setCopiedPortScript] = useState(false)

  const loadData = async () => {
    try {
      const [addrRes, healthRes, distRes] = await Promise.all([
        fetch('/api/provider-address').then((r) => (r.ok ? r.json() : null)),
        fetch(`${API}/health`).then((r) => (r.ok ? r.json() : null)),
        fetch(`${API}/distributed/status`).then((r) => (r.ok ? r.json() : null)),
      ])
      setAddrInfo(addrRes)
      setHealth(healthRes)
      setDistStatus(distRes)
      setError('')
    } catch (err: any) {
      setError(err.message || 'Failed to load network settings')
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const logout = async () => {
    try {
      await fetch('/api/session', { method: 'DELETE' })
    } finally {
      router.replace('/login')
    }
  }

  const lanUrl = addrInfo?.lan_address || 'ws://192.168.100.7:8001/ws/seeder'
  const joinToken = addrInfo?.enrollment_token || 'Unavailable'

  return (
    <AppLayout
      title="Network & Coordinator Settings"
      subtitle="Inspect network topology, firewall rules, listening ports, and operator credentials."
    >
      {error && (
        <DiagnosticBanner
          error={error}
          onDismiss={() => setError('')}
        />
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '24px' }}>
        {/* Left Column: Network Endpoints & Ports */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Active Network Endpoints */}
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
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                Coordinator Connection Endpoints
              </h2>
              <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
                Addresses used by client machines and browser dashboards to reach this node.
              </p>
            </div>

            {/* LAN URL */}
            <div>
              <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '4px' }}>
                Local Network (Wi-Fi LAN) WebSocket
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  readOnly
                  value={lanUrl}
                  style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#60a5fa', backgroundColor: '#090d16' }}
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(lanUrl)
                    setCopiedLan(true)
                    setTimeout(() => setCopiedLan(false), 2000)
                  }}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: 'rgba(255, 255, 255, 0.08)',
                    borderRadius: '6px',
                    fontSize: '11px',
                    color: '#f8fafc',
                  }}
                >
                  {copiedLan ? '✅ Copied' : 'Copy'}
                </button>
              </div>
              <small style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
                Volunteer machines connected to the same Wi-Fi router connect through this address.
              </small>
            </div>

            {/* Join Token */}
            <div>
              <label style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '4px' }}>
                Provider Join Token
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input
                  type="text"
                  readOnly
                  value={joinToken}
                  style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#fbbf24', backgroundColor: '#090d16' }}
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(joinToken)
                    setCopiedToken(true)
                    setTimeout(() => setCopiedToken(false), 2000)
                  }}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: '#3b82f6',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    color: '#ffffff',
                  }}
                >
                  {copiedToken ? '✅ Copied' : 'Copy'}
                </button>
              </div>
            </div>
          </section>

          {/* Listening Port Matrix */}
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '20px',
            }}
          >
            <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: '0 0 12px' }}>
              Service Port Bindings
            </h2>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: '#64748b' }}>
                  <th style={{ padding: '8px 10px', textAlign: 'left' }}>Port</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left' }}>Protocol</th>
                  <th style={{ padding: '8px 10px', textAlign: 'left' }}>Service Component</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: '#60a5fa' }}>8001</td>
                  <td style={{ padding: '8px 10px' }}>TCP / HTTP / WS</td>
                  <td style={{ padding: '8px 10px', color: '#cbd5e1' }}>Orchestrator REST & Provider WS</td>
                  <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                    <StatusBadge status="ready" size="sm" />
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: '#60a5fa' }}>31331</td>
                  <td style={{ padding: '8px 10px' }}>TCP</td>
                  <td style={{ padding: '8px 10px', color: '#cbd5e1' }}>Petals DHT Bootstrap Listener</td>
                  <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                    <StatusBadge status={distStatus?.status === 'ready' ? 'ready' : 'checking'} size="sm" />
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: '#60a5fa' }}>8002</td>
                  <td style={{ padding: '8px 10px' }}>HTTP</td>
                  <td style={{ padding: '8px 10px', color: '#cbd5e1' }}>Local Petals Gateway Container</td>
                  <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                    <StatusBadge status="ready" size="sm" />
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                  <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)', color: '#60a5fa' }}>3000</td>
                  <td style={{ padding: '8px 10px' }}>HTTP</td>
                  <td style={{ padding: '8px 10px', color: '#cbd5e1' }}>Submitter Web Portal (Next.js)</td>
                  <td style={{ padding: '8px 10px', textAlign: 'right' }}>
                    <StatusBadge status="ready" size="sm" />
                  </td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>

        {/* Right Column: Windows Defender Firewall Guide & Operator Controls */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Windows Firewall Quick Fix Card */}
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <span style={{ fontSize: '18px' }}>🛡️</span>
              <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                Windows Defender Firewall Inbound Rules
              </h2>
            </div>
            <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.5, margin: '0 0 12px' }}>
              For other client PCs on your local Wi-Fi router to connect to Petals DHT without getting blocked, inbound TCP port <strong>31331</strong> must be allowed through Windows Firewall.
            </p>

            <div style={{ backgroundColor: '#090d16', padding: '10px 12px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.08)', marginBottom: '12px' }}>
              <span style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>
                Run in PowerShell as Administrator:
              </span>
              <code style={{ fontSize: '11px', color: '#34d399', wordBreak: 'break-all' }}>
                .\open_firewall_ports.bat
              </code>
            </div>

            <button
              onClick={() => {
                navigator.clipboard.writeText('netsh advfirewall firewall add rule name="ComputeTorrent Petals DHT" dir=in action=allow protocol=TCP localport=31330,31331')
                setCopiedPortScript(true)
                setTimeout(() => setCopiedPortScript(false), 2000)
              }}
              style={{
                width: '100%',
                padding: '6px 12px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                fontSize: '11px',
                color: '#cbd5e1',
              }}
            >
              {copiedPortScript ? '✅ Copied netsh Command' : '📋 Copy netsh Rule Command'}
            </button>
          </section>

          {/* Operator Workspace Session Card */}
          <section
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              padding: '20px',
            }}
          >
            <h2 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: '0 0 8px' }}>
              Operator Session
            </h2>
            <p style={{ fontSize: '12px', color: '#94a3b8', margin: '0 0 16px' }}>
              Authenticated to operator workspace with local cryptographic session cookie.
            </p>

            <button
              onClick={logout}
              style={{
                padding: '8px 16px',
                backgroundColor: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid rgba(244, 63, 94, 0.25)',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                color: '#fb7185',
                cursor: 'pointer',
              }}
            >
              Sign Out of Operator Workspace
            </button>
          </section>
        </div>
      </div>
    </AppLayout>
  )
}
