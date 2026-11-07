import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/router'
import Head from 'next/head'
import Modal from './Modal'
import StatusBadge from './StatusBadge'

interface AppLayoutProps {
  children: React.ReactNode
  title?: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function AppLayout({ children, title, subtitle, actions }: AppLayoutProps) {
  const router = useRouter()
  const [onlineCount, setOnlineCount] = useState<number | null>(null)
  const [dhtStatus, setDhtStatus] = useState<string>('checking')
  const [enrollmentToken, setEnrollmentToken] = useState<string>('')
  const [lanAddress, setLanAddress] = useState<string>('')
  const [publicAddress, setPublicAddress] = useState<string | null>(null)
  const [showJoinModal, setShowJoinModal] = useState(false)
  const [copiedToken, setCopiedToken] = useState(false)
  const [copiedUrl, setCopiedUrl] = useState(false)

  useEffect(() => {
    // Fetch live node count and gateway status
    const fetchStatus = async () => {
      try {
        const [seedersRes, distRes, addrRes]: [any, any, any] = await Promise.all([
          fetch('/api/ct/seeders').then(async (r) => (r.ok ? await r.json() : [])),
          fetch('/api/ct/distributed/status').then(async (r) => (r.ok ? await r.json() : {})),
          fetch('/api/provider-address').then(async (r) => (r.ok ? await r.json() : {})),
        ])

        if (Array.isArray(seedersRes)) {
          const count = seedersRes.filter((s: any) =>
            typeof s.control_age_seconds === 'number' ||
            ['online', 'idle', 'busy'].includes(s.state || s.status)
          ).length
          setOnlineCount(count)
        }

        if (distRes?.status) {
          setDhtStatus(distRes.status)
        }

        if (addrRes) {
          if (addrRes.enrollment_token) setEnrollmentToken(addrRes.enrollment_token)
          if (addrRes.lan_address) setLanAddress(addrRes.lan_address)
          if (addrRes.public_address) setPublicAddress(addrRes.public_address)
        }
      } catch {
        // Handled silently
      }
    }

    fetchStatus()
    const timer = setInterval(fetchStatus, 5000)
    return () => clearInterval(timer)
  }, [])

  const logout = async () => {
    try {
      await fetch('/api/session', { method: 'DELETE' })
    } finally {
      router.replace('/login')
    }
  }

  const copyToken = () => {
    if (!enrollmentToken) return
    navigator.clipboard.writeText(enrollmentToken)
    setCopiedToken(true)
    setTimeout(() => setCopiedToken(false), 2000)
  }

  const copyAddress = () => {
    const target = publicAddress || lanAddress || `ws://${window.location.hostname}:8001/ws/seeder`
    navigator.clipboard.writeText(target)
    setCopiedUrl(true)
    setTimeout(() => setCopiedUrl(false), 2000)
  }

  const navItems = [
    { section: 'WORKSPACE' },
    { path: '/', label: 'Cluster Overview', icon: '📊' },
    { path: '/inference', label: 'Model Studio', icon: '🧠' },
    { path: '/deployments', label: 'Deployments', icon: '🚀' },
    { path: '/nodes', label: 'Compute Nodes', icon: '🖥️', badge: onlineCount !== null ? String(onlineCount) : undefined },
    { section: 'ACTIVITY & AUDIT' },
    { path: '/history', label: 'Task Audit', icon: '📜' },
    { path: '/credits', label: 'Credits Ledger', icon: '💳' },
    { section: 'MANAGEMENT' },
    { path: '/settings', label: 'Network & Settings', icon: '⚙️' },
  ]

  const isDhtReady = dhtStatus === 'ready'

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: '#090d16', color: '#f8fafc' }}>
      <Head>
        <title>{title ? `${title} | ComputeTorrent` : 'ComputeTorrent — Distributed AI Platform'}</title>
        <meta name="description" content="Decentralized peer-to-peer distributed AI computing platform." />
      </Head>

      {/* Modern High-Density Sidebar */}
      <aside
        style={{
          width: '260px',
          backgroundColor: '#0a0f1d',
          borderRight: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          height: '100vh',
          zIndex: 40,
          flexShrink: 0,
        }}
      >
        {/* Top Branding */}
        <div>
          <div
            style={{
              padding: '20px 18px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
              }}
            >
              ⚡
            </div>
            <div>
              <div style={{ fontSize: '15px', fontWeight: 700, letterSpacing: '-0.01em', color: '#f8fafc' }}>
                ComputeTorrent
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                Distributed AI Platform
              </div>
            </div>
          </div>

          {/* Navigation Links */}
          <nav style={{ padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {navItems.map((item, idx) => {
              if (item.section) {
                return (
                  <div
                    key={idx}
                    style={{
                      padding: '12px 10px 4px',
                      fontSize: '10px',
                      fontWeight: 700,
                      color: '#475569',
                      letterSpacing: '0.06em',
                    }}
                  >
                    {item.section}
                  </div>
                )
              }

              const isActive = router.pathname === item.path

              return (
                <a
                  key={item.path}
                  href={item.path}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '13px',
                    fontWeight: isActive ? 600 : 500,
                    backgroundColor: isActive ? 'rgba(59, 130, 246, 0.12)' : 'transparent',
                    color: isActive ? '#60a5fa' : '#94a3b8',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.04)'
                      e.currentTarget.style.color = '#f8fafc'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.backgroundColor = 'transparent'
                      e.currentTarget.style.color = '#94a3b8'
                    }
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '15px' }}>{item.icon}</span>
                    <span>{item.label}</span>
                  </div>
                  {item.badge && (
                    <span
                      style={{
                        padding: '1px 6px',
                        borderRadius: '9999px',
                        fontSize: '11px',
                        backgroundColor: isActive ? 'rgba(59, 130, 246, 0.3)' : 'rgba(255, 255, 255, 0.08)',
                        color: isActive ? '#93c5fd' : '#cbd5e1',
                      }}
                    >
                      {item.badge}
                    </span>
                  )}
                </a>
              )
            })}
          </nav>
        </div>

        {/* Sidebar Footer: DHT Status, Join Token, Sign Out */}
        <div style={{ padding: '14px', borderTop: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {/* DHT Gateway Status Pill */}
          <div
            style={{
              padding: '8px 10px',
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              borderRadius: '6px',
              border: '1px solid rgba(255, 255, 255, 0.06)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '11px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: isDhtReady ? '#10b981' : '#f59e0b',
                }}
              />
              <span style={{ color: '#cbd5e1' }}>DHT Overlay</span>
            </div>
            <StatusBadge status={isDhtReady ? 'ready' : dhtStatus} size="sm" showDot={false} />
          </div>

          {/* Quick Connect Trigger Button */}
          <button
            onClick={() => setShowJoinModal(true)}
            style={{
              width: '100%',
              padding: '8px 10px',
              backgroundColor: 'rgba(59, 130, 246, 0.08)',
              color: '#93c5fd',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <span>🔑</span>
            <span>Provider Join Code</span>
          </button>

          {/* Sign Out Action */}
          <button
            onClick={logout}
            style={{
              width: '100%',
              padding: '6px 10px',
              color: '#64748b',
              borderRadius: '6px',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              transition: 'color 0.15s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = '#f43f5e' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = '#64748b' }}
          >
            <span>Operator Sign Out</span>
            <span>🚪</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflowX: 'hidden' }}>
        {/* Top Header */}
        <header
          style={{
            height: '64px',
            padding: '0 28px',
            backgroundColor: '#0a0f1d',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            position: 'sticky',
            top: 0,
            zIndex: 30,
          }}
        >
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 600, color: '#f8fafc', margin: 0, letterSpacing: '-0.01em' }}>
              {title || 'Dashboard'}
            </h1>
            {subtitle && (
              <p style={{ fontSize: '12px', color: '#64748b', margin: '2px 0 0' }}>
                {subtitle}
              </p>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            {/* Live cluster indicator */}
            {onlineCount !== null && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  backgroundColor: 'rgba(255, 255, 255, 0.04)',
                  borderRadius: '9999px',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  fontSize: '12px',
                  color: '#cbd5e1',
                }}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: onlineCount >= 2 ? '#10b981' : onlineCount > 0 ? '#f59e0b' : '#64748b',
                  }}
                />
                <span>{onlineCount} {onlineCount === 1 ? 'Provider' : 'Providers'} Online</span>
              </div>
            )}

            {/* Injected Header Actions */}
            {actions}
          </div>
        </header>

        {/* Page Content */}
        <main style={{ flex: 1, padding: '28px', maxWidth: '1440px', width: '100%', margin: '0 auto' }}>
          {children}
        </main>

        {/* Global Footer */}
        <footer
          style={{
            padding: '16px 28px',
            borderTop: '1px solid rgba(255, 255, 255, 0.06)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '12px',
            color: '#64748b',
          }}
        >
          <span>ComputeTorrent Distributed AI Architecture · Multi-Provider P2P Inference</span>
          <span>Coordinator Port: 8001 · Petals Gateway: 8002</span>
        </footer>
      </div>

      {/* Provider Join Code Modal */}
      <Modal
        isOpen={showJoinModal}
        onClose={() => setShowJoinModal(false)}
        title="Connect Provider Computers"
        subtitle="Use these credentials on volunteer client PCs running the Windows desktop app."
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Join Code */}
          <div>
            <label style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '6px' }}>
              🔑 Provider Join Token
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                readOnly
                value={enrollmentToken || 'Unavailable'}
                style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '13px', color: '#fbbf24', backgroundColor: '#090d16' }}
              />
              <button
                onClick={copyToken}
                style={{
                  padding: '8px 14px',
                  backgroundColor: '#3b82f6',
                  color: '#ffffff',
                  borderRadius: '6px',
                  fontWeight: 600,
                  fontSize: '12px',
                  whiteSpace: 'nowrap',
                }}
              >
                {copiedToken ? '✅ Copied' : 'Copy Token'}
              </button>
            </div>
            <small style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
              Clients paste this token once during initial setup to enroll with the coordinator.
            </small>
          </div>

          {/* WebSocket Address */}
          <div>
            <label style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'block', marginBottom: '6px' }}>
              🏠 Coordinator WebSocket Address
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                readOnly
                value={publicAddress || lanAddress || `ws://${typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'}:8001/ws/seeder`}
                style={{ flex: 1, fontFamily: 'var(--font-mono)', fontSize: '13px', color: '#60a5fa', backgroundColor: '#090d16' }}
              />
              <button
                onClick={copyAddress}
                style={{
                  padding: '8px 14px',
                  backgroundColor: 'rgba(255, 255, 255, 0.08)',
                  color: '#f8fafc',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  borderRadius: '6px',
                  fontWeight: 500,
                  fontSize: '12px',
                  whiteSpace: 'nowrap',
                }}
              >
                {copiedUrl ? '✅ Copied' : 'Copy URL'}
              </button>
            </div>
            <small style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
              {publicAddress ? '🌐 Global Public Tunnel Active' : 'Connected client PCs on your local Wi-Fi router will use this address.'}
            </small>
          </div>

          {/* Quick instructions */}
          <div style={{ padding: '12px', backgroundColor: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.06)' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1', display: 'block', marginBottom: '6px' }}>
              Quick Provider Setup Checklist:
            </span>
            <ol style={{ margin: 0, paddingLeft: '18px', fontSize: '11px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <li>Ensure Docker Desktop is running on the client PC.</li>
              <li>Launch the ComputeTorrent Windows provider application.</li>
              <li>Paste the Coordinator WebSocket address and Join Token.</li>
              <li>Ensure the "Share model layers" toggle is enabled.</li>
            </ol>
          </div>
        </div>
      </Modal>
    </div>
  )
}
