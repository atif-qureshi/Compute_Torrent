import { statusLabel, isActive } from '../lib/portal'
export default function StatusBadge({ status, label, size, showDot = true }: { status?: string; label?: string; size?: string; showDot?: boolean }) {
  const tone = ['healthy','ready','completed','idle','serving','online'].includes(status || '') ? 'positive' : ['failed','revoked','error'].includes(status || '') ? 'negative' : isActive(status) || status === 'paused' ? 'attention' : 'neutral'
  return <span className={`badge ${tone}`}>{showDot && <span className="badge-dot" />}{label || statusLabel(status)}</span>
}
