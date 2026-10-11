import { BarChart3, Briefcase, CalendarCheck, FolderKanban, Search, Users } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { connectLive, go, href, prefetch, setParams, useApi, useLive, useRoute, type View } from './api'
import { EmptyPane, Toasts, toast } from './components'
import { actorName, setLabels } from './format'
import { JobPane, ProjectPane } from './panes'
import { StatsView } from './stats'
import type { Kind, Meta, TodayData } from './types'
import { JobsView, PeopleView, ProjectsView, TodayView } from './views'

// `loads` are fetched when the tab is hovered, so the view slides in with its data already there.
const NAV: { view: View; label: string; icon: typeof Briefcase; loads: string[] }[] = [
  { view: 'today', label: 'Today', icon: CalendarCheck, loads: ['/api/today'] },
  { view: 'jobs', label: 'Jobs', icon: Briefcase, loads: ['/api/jobs'] },
  { view: 'projects', label: 'Projects', icon: FolderKanban, loads: ['/api/projects'] },
  { view: 'stats', label: 'Stats', icon: BarChart3, loads: ['/api/stats', '/api/stats/projects'] },
  { view: 'people', label: 'People', icon: Users, loads: ['/api/companies', '/api/contacts'] },
]

function LiveBadge() {
  const { connected, recent } = useLive()
  const [pulse, setPulse] = useState(false)
  const seen = useRef<number>(0)
  useEffect(() => {
    const newest = recent[0]?.id ?? 0
    if (!seen.current) { seen.current = newest; return }
    const fresh = recent.filter((e) => e.id > seen.current)
    seen.current = Math.max(seen.current, newest)
    if (!fresh.length) return
    setPulse(true)
    const t = setTimeout(() => setPulse(false), 1300)
    // Your own clicks already show their result; announce what Claude and others changed.
    fresh.filter((e) => e.actor !== 'me').slice(0, 3).reverse()
      .forEach((e) => toast(e.summary, undefined, actorName(e.actor)))
    return () => clearTimeout(t)
  }, [recent])
  return (
    <span className={`livebadge${connected ? ' on' : ''}${pulse ? ' pulse' : ''}`}
          title={connected ? 'Live: changes from Claude and the CLI appear within a second' : 'Not connected to the server'}>
      <i />{connected ? 'Live' : 'Offline'}
    </span>
  )
}

function TopSearch() {
  const [q, setQ] = useState('')
  return (
    <form className="topsearch" role="search" onSubmit={(e) => { e.preventDefault(); go('jobs', { q }); setQ('') }}>
      <Search size={15} />
      <input placeholder="Search every job" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search every job" />
    </form>
  )
}

export default function App() {
  const route = useRoute()
  const { data: meta } = useApi<Meta>('/api/meta')
  const { data: today } = useApi<TodayData>('/api/today')

  // ?snapshot skips the live connection so headless screenshots can finish loading.
  useEffect(() => { if (!new URLSearchParams(window.location.search).has('snapshot')) connectLive() }, [])
  if (meta) setLabels(meta.labels)

  const jobId = Number(route.params.get('job')) || null
  const projectId = Number(route.params.get('project')) || null
  const closePane = () => setParams({ job: null, project: null })
  const select = (kind: Kind, id: number) =>
    setParams(kind === 'project' ? { project: String(id), job: null } : { job: String(id), project: null }, false)
  const selectJob = (id: number) => select('job', id)

  // Escape closes the reading pane (a drawer on the Projects board and on narrow screens),
  // unless a menu or picture is open or you're typing.
  const open = !!(jobId || projectId)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement
      if (e.key === 'Escape' && !typing && !document.querySelector('.menu-list, .lightbox')) setParams({ job: null, project: null })
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const dueCount = today ? today.due.length : 0
  const lateCount = today ? today.due.filter((a) => a.next_action_due! < today.date).length : 0

  const pane = !meta ? null
    : jobId ? <JobPane key={`j${jobId}`} id={jobId} meta={meta} onClose={closePane} />
    : projectId ? <ProjectPane key={`p${projectId}`} id={projectId} meta={meta} onClose={closePane} />
    : null

  let body
  if (route.view === 'jobs') {
    body = (
      <main className="ws ws-jobs">
        <JobsView route={route} selectJob={selectJob} />
        <section className={`col col-pane${pane ? ' open' : ''}`} aria-label="Details">
          {pane ?? <EmptyPane>Pick a job to see the posting, where the application stands, its emails and history.</EmptyPane>}
        </section>
      </main>
    )
  } else if (route.view === 'projects') {
    body = (
      <main className="ws ws-board">
        <ProjectsView route={route} selectProject={(id) => select('project', id)} />
        <section className={`col col-pane${pane ? ' open' : ''}`} aria-label="Details">{pane}</section>
      </main>
    )
  } else if (route.view === 'stats') {
    body = <main className="ws ws-full"><StatsView route={route} /></main>
  } else if (route.view === 'people') {
    body = <main className="ws ws-full"><PeopleView /></main>
  } else {
    body = (
      <main className="ws ws-two">
        <section className="col col-list" aria-label="Today"><TodayView route={route} select={select} /></section>
        <section className={`col col-pane${pane ? ' open' : ''}`} aria-label="Details">
          {pane ?? <EmptyPane>Pick anything on the left to open it here.</EmptyPane>}
        </section>
      </main>
    )
  }

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href={href('today')}>
          <svg width="26" height="14" viewBox="0 0 26 14" aria-hidden="true">
            <path d="M2 7h22" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
            <circle cx="6" cy="7" r="4" fill="#fff" stroke="var(--accent)" strokeWidth="2.5" />
            <circle cx="20" cy="7" r="4.5" fill="var(--accent)" />
          </svg>
          Job Desk
        </a>
        <nav className="nav" aria-label="Views">
          {NAV.map(({ view, label: name, icon: Icon, loads }) => (
            <a key={view} href={href(view)} aria-current={route.view === view ? 'page' : undefined}
               onMouseEnter={() => loads.forEach(prefetch)} onFocus={() => loads.forEach(prefetch)}>
              <Icon size={16} /><span className="lbl">{name}</span>
              {view === 'today' && dueCount > 0 && <span className={`count${lateCount ? ' late' : ''}`}>{dueCount}</span>}
              {route.view === view && <span className="nav-ink" aria-hidden="true" />}
            </a>
          ))}
        </nav>
        <TopSearch />
        <LiveBadge />
      </header>
      {body}
      <Toasts />
    </div>
  )
}
