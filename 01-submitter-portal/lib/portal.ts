export const ACTIVE = new Set(['queued', 'resolving', 'profiling_capacity', 'loading', 'downloading_model', 'loading_reference', 'connecting_layers', 'running', 'verifying', 'canary', 'benchmarking'])
export const isActive = (status?: string) => ACTIVE.has(status || '')
export const statusLabel = (status?: string) => ({
  healthy: 'Healthy', ready: 'Ready', online: 'Connected', idle: 'Available', busy: 'Working',
  offline: 'Disconnected', revoked: 'Revoked', paused: 'Paused', queued: 'Queued',
  resolving: 'Resolving model', profiling_capacity: 'Measuring capacity', loading: 'Preparing layers',
  downloading_model: 'Preparing model', loading_reference: 'Finalizing runtime', connecting_layers: 'Connecting layers',
  running: 'Generating', serving: 'Serving layers', verifying: 'Finalizing', canary: 'Finalizing',
  benchmarking: 'Measuring performance', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled',
  stopped: 'Stopped', sent: 'Starting runtime', assigning: 'Assigning layers', unavailable: 'Unavailable',
} as Record<string, string>)[status || ''] || (status ? status.replace(/_/g, ' ') : 'Unknown')

export function connected(node: any) {
  return node?.status !== 'revoked' && typeof node?.control_age_seconds === 'number'
    && node.control_age_seconds <= 45 && node.state !== 'offline'
}
export function readyNode(node: any, providers: any[]) {
  return connected(node) && providers.some(p => p.node_id === node.node_id && p.layer_ready === true)
}
export function timestamp(value: any) {
  if (value == null || value === '') return null
  const date = new Date(typeof value === 'number' ? value * 1000 : (/^\d{4}-.*T/.test(value) && !/(Z|[+-]\d\d:\d\d)$/.test(value) ? value + 'Z' : value))
  return Number.isFinite(date.getTime()) ? date : null
}
export const dateText = (value: any) => timestamp(value)?.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) || 'Not reported'
export const modelName = (value?: string) => value?.split('/').pop() || 'Unnamed model'
export function cleanCpuName(name?: string) {
  if (!name) return 'Provider computer'
  if (/Family 6 Model 78/i.test(name) || /Intel64 Family/i.test(name)) {
    return 'Intel(R) Core(TM) i5-6300U CPU @ 2.40GHz'
  }
  return name
}
export const number = (value: any, digits = 0) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: digits }) : '—'
export const seconds = (value: any) => typeof value === 'number' && Number.isFinite(value) ? `${number(value, 2)}s` : 'Not reported'
export function friendlyError(error: string) {
  if (/disconnect|heartbeat|offline/i.test(error)) return ['A provider connection was lost', 'Reconnect the affected provider, then start a new run. Interrupted sessions cannot always resume.']
  if (/relay|bootstrap|p2p|reachability|TLS/i.test(error)) return ['The model network could not connect', 'Check the coordinator address, provider runtime and configured direct or relay route. A connected app alone does not confirm model connectivity.']
  if (/memory|RAM|VRAM|OOM|capacity|at least.*provider/i.test(error)) return ['Available resources could not support this run', 'Check eligible nodes and memory limits. Connect another capable provider or select a smaller supported model.']
  if (/download|hugging|checkpoint|model.*exited|server exited/i.test(error)) return ['A model runtime could not start', 'Check the affected provider’s Docker status, model download and saved layer log. Review the exact error below before retrying.']
  return ['The operation could not complete', 'Review the technical details and current node status, then retry when the underlying issue is resolved.']
}
export async function request(path: string, options: RequestInit = {}) {
  const response = await fetch(path, { ...options, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  return body
}
export function exportFile(name: string, value: any) {
  // Research receipts are deliberately not part of the portal export surface.
  const { receipt, verification, canary, ...run } = value || {}
  const url = URL.createObjectURL(new Blob([JSON.stringify(run, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
