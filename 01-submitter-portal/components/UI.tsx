import React, { useState } from 'react'
import Link from 'next/link'
import Icon from './Icon'
import { useWorkspace } from './Workspace'
import { friendlyError } from '../lib/portal'
export function Empty({ title, children, href, action }: { title: string; children: React.ReactNode; href?: string; action?: string }) {
  return <div className="empty"><div className="empty-symbol"><Icon name="model" size={26}/></div><h3>{title}</h3><p>{children}</p>{href && <Link className="button secondary" href={href}>{action || 'Get started'}<Icon name="arrow" size={15}/></Link>}</div>
}
export function ResourceError({ names }: { names: string[] }) {
  const { resources, refresh } = useWorkspace()
  const errors = names.filter(k => resources[k]?.error)
  if (!errors.length) return null
  return <div className="notice warning" role="status"><Icon name="alert"/><div><strong>Some workspace data is unavailable</strong><p>{errors.map(k => `${k}: ${resources[k].error}`).join(' · ')}{errors.some(k => resources[k].updated) ? ' Last received data is shown; it may be stale.' : ''}</p></div><button className="button small secondary" onClick={refresh}>Try again</button></div>
}
export function ErrorNotice({ error }: { error: string }) {
  if (!error) return null
  const [title, guidance] = friendlyError(error)
  return <div className="notice danger" role="alert"><Icon name="alert"/><div><strong>{title}</strong><p>{guidance}</p><details><summary>Technical details</summary><pre className="log">{error}</pre></details></div></div>
}
export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [state, setState] = useState('')
  async function copy() { try { await navigator.clipboard.writeText(value); setState('Copied'); setTimeout(() => setState(''), 2000) } catch { setState('Copy unavailable. Select the text manually.') } }
  return <span className="copy-control"><button type="button" className="button small secondary" disabled={!value} onClick={copy}><Icon name={state === 'Copied' ? 'check' : 'copy'} size={14}/>{state === 'Copied' ? 'Copied' : label}</button>{state && <span role="status" className="sr-only">{state}</span>}</span>
}
export function Skeleton({ rows = 4 }: { rows?: number }) { return <div className="skeleton-list" role="status" aria-label="Loading workspace data">{Array.from({length: rows}, (_,i) => <div key={i} className="skeleton" />)}</div> }
export function Toolbar({ query, setQuery, filter, setFilter, filters, label = 'Search', children }: any) {
  return <div className="toolbar"><label className="search"><Icon name="search"/><input aria-label={label} placeholder={label} value={query} onChange={e => setQuery(e.target.value)}/></label>{filters && <label className="filter-control"><span className="sr-only">Filter by status</span><select value={filter} onChange={e => setFilter(e.target.value)}>{filters.map((f: any) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>}{children}</div>
}
export function Pagination({ page, setPage, total, size = 10 }: any) {
  const last = Math.max(1, Math.ceil(total / size)); const current = Math.min(page,last)
  return <nav className="pagination" aria-label="Table pagination"><span>{total ? `${(current-1)*size+1}–${Math.min(current*size,total)} of ${total}` : '0 results'}</span><div><button className="button small secondary" disabled={current <= 1} onClick={() => setPage(current-1)}>Previous</button><span>Page {current} of {last}</span><button className="button small secondary" disabled={current >= last} onClick={() => setPage(current+1)}>Next</button></div></nav>
}
export function Section({ title, note, action, children, className = '' }: { title: string; note?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><header className="section-head"><div><h2>{title}</h2>{note && <p>{note}</p>}</div>{action}</header>{children}</section>
}
