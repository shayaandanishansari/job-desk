import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { flushSync } from 'react-dom'
import type { EventRow } from './types'

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const msg = (body && (body as { error?: string }).error) || `${res.status} ${res.statusText}`
    throw new ApiError(msg, res.status, body)
  }
  return body as T
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const result = await api<T>(path, { method, body: JSON.stringify(body ?? {}) })
  bump()
  return result
}

export const post = <T,>(path: string, body?: unknown) => send<T>('POST', path, body)
export const patch = <T,>(path: string, body?: unknown) => send<T>('PATCH', path, body)

// ------------------------------------------------------------------ live store
// One revision number for the whole app. It goes up whenever the database changes
// (an SSE message from the server, or our own write), and every useApi refetches.

type Live = { revision: number; connected: boolean; recent: EventRow[] }
let live: Live = { revision: 0, connected: false, recent: [] }
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

function set(next: Partial<Live>) {
  live = { ...live, ...next }
  emit()
}

export function bump() {
  set({ revision: live.revision + 1 })
}

let source: EventSource | null = null
export function connectLive() {
  if (source) return
  source = new EventSource('/api/stream')
  source.addEventListener('hello', () => set({ connected: true }))
  source.addEventListener('events', (e) => {
    const rows = JSON.parse((e as MessageEvent).data) as EventRow[]
    set({ revision: live.revision + 1, connected: true, recent: [...rows, ...live.recent].slice(0, 50) })
  })
  source.addEventListener('change', () => set({ revision: live.revision + 1, connected: true }))
  source.onerror = () => set({ connected: false })
  source.onopen = () => set({ connected: true })
}

export function useLive(): Live {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => live,
  )
}

// The last copy of every path fetched, so a view you return to (or a job you hovered) shows at
// once and then refreshes. Small enough to keep whole: one entry per path, oldest dropped first.
const cache = new Map<string, unknown>()
const pending = new Set<string>()

function remember(path: string, data: unknown) {
  cache.delete(path)
  cache.set(path, data)
  if (cache.size > 200) cache.delete(cache.keys().next().value!)
}

/** Fetch a path ahead of time (on hover), so opening it needs no wait. */
export function prefetch(path: string) {
  if (cache.has(path) || pending.has(path)) return
  pending.add(path)
  api(path).then((d) => remember(path, d), () => {}).finally(() => pending.delete(path))
}

/** Fetch JSON and refetch whenever the database changes. Keeps the last data while reloading.
 *  A new path shows its cached copy straight away; with `keep`, the old path's data stays up
 *  until the new one arrives (`loading` is true meanwhile) instead of blanking. */
export function useApi<T>(path: string | null, { keep = false } = {}) {
  const { revision } = useLive()
  const cached = (p: string | null) => (p ? (cache.get(p) as T | undefined) : undefined)
  const [data, setData] = useState<T | null>(() => cached(path) ?? null)
  const [shown, setShown] = useState<string | null>(() => (cached(path) !== undefined ? path : null))
  const [error, setError] = useState<string | null>(null)
  const current = useRef(path)
  current.current = path

  // A new path: switch during render, so the old data never shows under the new path.
  const [seen, setSeen] = useState(path)
  if (seen !== path) {
    setSeen(path)
    const c = cached(path)
    if (c !== undefined) {
      setData(c)
      setShown(path)
    } else if (!keep) {
      setData(null)
      setShown(null)
    }
  }

  const load = useCallback(() => {
    if (!path) {
      setData(null)
      return
    }
    api<T>(path)
      .then((d) => {
        remember(path, d)
        if (current.current === path) {
          setData(d)
          setShown(path)
          setError(null)
        }
      })
      .catch((e: Error) => current.current === path && setError(e.message))
  }, [path])

  useEffect(() => {
    load()
  }, [load, revision])

  return { data, error, reload: load, loading: !!path && shown !== path }
}

// ------------------------------------------------------------------ routing
// #/<view>?a=1&b=2 — shareable, survives reloads, and the back button works.

export type View = 'today' | 'jobs' | 'stats' | 'people'
const VIEWS: View[] = ['today', 'jobs', 'stats', 'people']

export interface Route { view: View; params: URLSearchParams }

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, query] = raw.split('?')
  const view = (VIEWS.includes(path as View) ? path : 'today') as View
  return { view, params: new URLSearchParams(query || '') }
}

export function reducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

let route = parse()
const routeListeners = new Set<() => void>()

/** Apply the URL to the app. Moving between views slides the page in the direction of the tab
 *  (a view transition, where the browser has them); changes within a view apply at once. */
function commit() {
  const next = parse()
  const from = VIEWS.indexOf(route.view)
  const to = VIEWS.indexOf(next.view)
  const apply = () => {
    route = next
    routeListeners.forEach((l) => l())
  }
  if (from === to || !document.startViewTransition || reducedMotion()) return apply()
  document.documentElement.dataset.nav = to > from ? 'forward' : 'back'
  document.startViewTransition(() => flushSync(apply))
}

window.addEventListener('hashchange', commit)

export function useRoute(): Route {
  return useSyncExternalStore(
    (cb) => {
      routeListeners.add(cb)
      return () => routeListeners.delete(cb)
    },
    () => route,
  )
}

export function href(view: View, params?: URLSearchParams | Record<string, string | null | undefined>) {
  const p = params instanceof URLSearchParams ? new URLSearchParams(params) : new URLSearchParams()
  if (params && !(params instanceof URLSearchParams)) {
    for (const [k, v] of Object.entries(params)) if (v != null && v !== '') p.set(k, v)
  }
  const q = p.toString()
  return `#/${view}${q ? `?${q}` : ''}`
}

export function go(view: View, params?: URLSearchParams | Record<string, string | null | undefined>, replace = false) {
  const target = href(view, params)
  if (replace) window.history.replaceState(null, '', target)
  else window.history.pushState(null, '', target)
  commit()
}

/** Change some params on the current route (null removes one). */
export function setParams(changes: Record<string, string | string[] | null>, replace = true) {
  const p = new URLSearchParams(route.params)
  for (const [k, v] of Object.entries(changes)) {
    p.delete(k)
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else if (v != null && v !== '') p.set(k, v)
  }
  go(route.view, p, replace)
}
