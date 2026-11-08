import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { request } from '../lib/portal'

const endpoints: Record<string, string> = {
  health: '/api/ct/health', nodes: '/api/ct/seeders', capacity: '/api/ct/distributed/status',
  jobs: '/api/ct/distributed/jobs', catalog: '/api/ct/distributed/catalog',
  history: '/api/ct/history?submitter_id=web-portal&limit=100',
  credits: '/api/ct/credits?submitter_id=web-portal&limit=100', network: '/api/ct/network',
}
type Resource = { data: any; error: string; updated: number | null }
const Context = createContext<any>(null)
export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [resources, setResources] = useState<Record<string, Resource>>({})
  const [loading, setLoading] = useState(true)
  const running = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const alive = useRef(true)
  const refresh = useCallback(async () => {
    if (running.current) return
    running.current = true; setLoading(true)
    const abort = new AbortController(); controller.current = abort
    const timeout = setTimeout(() => abort.abort(), 12000)
    await Promise.all(Object.entries(endpoints).map(async ([key, url]) => {
      try {
        const data = await request(url, { signal: abort.signal })
        if (alive.current) setResources(old => ({ ...old, [key]: { data, error: '', updated: Date.now() } }))
      } catch (e: any) {
        if (alive.current) setResources(old => ({ ...old, [key]: { data: old[key]?.data ?? null, updated: old[key]?.updated ?? null, error: e.name === 'AbortError' ? 'The coordinator response timed out.' : e.message } }))
      }
    }))
    clearTimeout(timeout); running.current = false
    if (alive.current) setLoading(false)
  }, [])
  useEffect(() => {
    alive.current = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => { await refresh(); if (alive.current) timer = setTimeout(poll, document.hidden ? 30000 : 6000) }
    void poll()
    const focus = () => { if (!document.hidden) void refresh() }
    document.addEventListener('visibilitychange', focus)
    return () => { alive.current = false; clearTimeout(timer); controller.current?.abort(); document.removeEventListener('visibilitychange', focus) }
  }, [refresh])
  return <Context.Provider value={{ resources, loading, refresh }}>{children}</Context.Provider>
}
export function useWorkspace() {
  const context = useContext(Context)
  if (!context) throw new Error('Workspace provider missing')
  return context as { resources: Record<string, Resource>; loading: boolean; refresh: () => Promise<void> }
}
