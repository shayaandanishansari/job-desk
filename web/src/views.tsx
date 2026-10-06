import { PenLine, Search, SlidersHorizontal, Star as StarIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { href, prefetch, setParams, useApi, type Route } from './api'
import { ApplyLink, FlipList, Num, OUTCOMES, Prio, Signals, Skeleton, Star, StarMark, StatusChip, Thumbed, useChanged, useFlip } from './components'
import { activeFilters, Filters } from './filters'
import { ago, due, dueTone, fmtDate, fmtDateTime, label, place, plural } from './format'
import type { Company, Contact, JobList, JobSummary, TodayData } from './types'

/** Hovering a job loads it, so clicking opens it at once. */
const warm = (id: number) => () => prefetch(`/api/jobs/${id}`)

// ------------------------------------------------------------------ the one row

/** A job in a list. `agenda` adds the next action underneath, for the Today view. */
export function JobRow({ j, selected, onSelect, agenda, showFlags }: {
  j: JobSummary; selected: boolean; onSelect: () => void; agenda?: boolean; showFlags?: boolean
}) {
  const when = j.applied_on ? `Sent ${fmtDate(j.applied_on)}` : fmtDate(j.posted_on ?? j.found_on)
  const tone = dueTone(j.next_action_due)
  // A job changed while on screen (by Claude, the CLI or you) glows once.
  const changed = useChanged(j.updated_at)
  return (
    <div className={`row${j.status === 'passed' ? ' passed' : ''}`} role="button" tabIndex={0} aria-selected={selected} onClick={onSelect}
         onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onSelect() } }}
         onMouseEnter={warm(j.id)} onFocus={warm(j.id)} data-flip={j.id}>
      {changed > 0 && <span key={changed} className="row-flash" aria-hidden="true" />}
      <div className="row-top">
        <Prio n={j.priority} />
        <span className="row-title">{j.title}</span>
        <span className="row-side">{when}</span>
        <Star job={j} />
      </div>
      <div className="row-sub">
        <span className="row-company">{j.company ?? 'Company not named'}</span>
        <span>{place(j)}</span>
        <StatusChip job={j} />
        {!agenda && <Signals job={j} />}
        {j.visa === 'yes' && <span className="pill visa-yes">Sponsors visa</span>}
      </div>
      <ApplyLink to={j.apply_to} />
      {agenda && j.next_action && (
        <div className="row-next">
          <span>{j.next_action}</span>
          {j.next_action_due && <span className={`due ${tone}`}>{due(j.next_action_due)}</span>}
        </div>
      )}
      {showFlags && j.flags.length > 0 && (
        <div className="flags">{j.flags.map((f) => <span key={f.flag} className={`flag ${f.flag}`}>{f.text}</span>)}</div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ today

export function TodayView({ route, selectJob }: { route: Route; selectJob: (id: number) => void }) {
  const { data } = useApi<TodayData>('/api/today')
  const selected = Number(route.params.get('job'))
  if (!data) return <div className="today"><Skeleton kind="today" /></div>

  const late = data.due.filter((j) => dueTone(j.next_action_due) === 'late').length
  const replies = data.attention.filter((j) => j.flags.some((f) => f.flag === 'reply_waiting')).length
  const parts: string[] = []
  if (data.due.length) parts.push(`${plural(data.due.length, 'thing')} due${late ? ` (${late} overdue)` : ''}`)
  if (replies) parts.push(`${plural(replies, 'reply', 'replies')} waiting for you`)
  if (data.drafts.length) parts.push(`${plural(data.drafts.length, 'email')} ready to send`)
  if (data.interviews.length) parts.push(`${plural(data.interviews.length, 'interview')} coming up`)
  if (data.closing_soon.length) parts.push(`${plural(data.closing_soon.length, 'saved job')} closing soon`)
  const headline = parts.length
    ? parts.length === 1 ? `${parts[0]}.` : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}.`
    : 'Nothing is due. A good day to find new jobs.'
  const capital = headline.charAt(0).toUpperCase() + headline.slice(1)
  const d = new Date()

  return (
    <div className="today">
      <div className="today-date">{d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
      <h1 className="today-headline">{capital}</h1>
      <div className="today-week">
        <span><b><Num value={data.week.sent} /></b> sent this week</span>
        <span><b><Num value={data.week.replies} /></b> {data.week.replies === 1 ? 'reply' : 'replies'} this week</span>
        <span><b><Num value={data.week.open} /></b> in progress</span>
      </div>

      <div className="block">
        <h3>Due now <span className="meta">{data.due.length || ''}</span></h3>
        {data.due.length === 0 && <p className="empty">Nothing due today.</p>}
        <FlipList>{data.due.map((j) => <JobRow key={j.id} j={j} agenda selected={selected === j.id} onSelect={() => selectJob(j.id)} />)}</FlipList>
      </div>

      {data.closing_soon.length > 0 && (
        <div className="block">
          <h3>Closing soon <span className="meta">jobs you haven't applied to yet</span></h3>
          <FlipList>{data.closing_soon.map((j) => (
            <button key={j.id} data-flip={j.id} className="row" aria-selected={selected === j.id} onClick={() => selectJob(j.id)} onMouseEnter={warm(j.id)}>
              <div className="row-top">
                <Prio n={j.priority} />
                <span className="row-title">{j.title} <span className="row-company">at {j.company ?? '?'}</span></span>
                <span className={`due ${dueTone(j.deadline)}`}>closes {due(j.deadline)}</span>
                {!!j.starred && <StarMark />}
              </div>
            </button>
          ))}</FlipList>
        </div>
      )}

      {data.attention.length > 0 && (
        <div className="block">
          <h3>Needs a look <span className="meta">{data.attention.length}</span></h3>
          <FlipList>{data.attention.map((j) => <JobRow key={j.id} j={j} agenda showFlags selected={selected === j.id} onSelect={() => selectJob(j.id)} />)}</FlipList>
        </div>
      )}

      {data.drafts.length > 0 && (
        <div className="block">
          <h3>Emails ready to send <span className="meta">{data.drafts.length}</span></h3>
          <FlipList>{data.drafts.map((dr) => (
            <button key={dr.id} data-flip={dr.id} className="row" aria-selected={selected === dr.job_id} onClick={() => selectJob(dr.job_id)} onMouseEnter={warm(dr.job_id)}>
              <div className="row-top">
                <PenLine size={15} />
                <span className="row-title">{dr.subject ?? '(no subject)'}</span>
                <span className={`pill ${dr.status === 'in_gmail' ? 'now' : 'blue'}`}>{dr.status === 'in_gmail' ? 'In Gmail drafts' : 'Draft'}</span>
              </div>
              <div className="row-sub"><span>{dr.title} at {dr.company ?? '?'}</span>{dr.to_addr && <span>to {dr.to_addr}</span>}</div>
            </button>
          ))}</FlipList>
        </div>
      )}

      {data.interviews.length > 0 && (
        <div className="block">
          <h3>Interviews in the next two weeks</h3>
          <FlipList>{data.interviews.map((iv) => (
            <button key={iv.id} data-flip={iv.id} className="row" onClick={() => selectJob(iv.job_id)} onMouseEnter={warm(iv.job_id)}>
              <div className="row-top"><span className="row-title">{label(iv.kind)} interview, {iv.title} at {iv.company}</span>
                <span className="row-side">{fmtDateTime(iv.scheduled_at)}</span></div>
            </button>
          ))}</FlipList>
        </div>
      )}

      <div className="block">
        <h3>Coming up this week <span className="meta">{data.upcoming.length || ''}</span></h3>
        {data.upcoming.length === 0 && <p className="empty">Nothing scheduled in the next 7 days.</p>}
        <FlipList>{data.upcoming.map((j) => <JobRow key={j.id} j={j} agenda selected={selected === j.id} onSelect={() => selectJob(j.id)} />)}</FlipList>
      </div>

      <div className="block">
        <h3>New jobs to look at <span className="meta">{data.to_triage.total || ''}</span></h3>
        {data.to_triage.total === 0 && <p className="empty">No new jobs. Send Claude a screenshot or link to add one.</p>}
        <FlipList>{data.to_triage.jobs.map((j) => (
          <button key={j.id} data-flip={j.id} className="row" aria-selected={selected === j.id} onClick={() => selectJob(j.id)} onMouseEnter={warm(j.id)}>
            <div className="row-top"><span className="row-title">{j.title} <span className="row-company">at {j.company ?? '?'}</span></span>
              <span className="row-side">Found {ago(j.found_on)}</span>{!!j.starred && <StarMark />}</div>
          </button>
        ))}</FlipList>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ jobs

// Quick views over the status filter: the old Applications tab is "In progress" + "Closed".
const QUICK: { key: string; name: string; statuses: string[] }[] = [
  { key: 'all', name: 'All', statuses: [] },
  { key: 'todo', name: 'Not applied', statuses: ['new', 'shortlisted', 'drafting'] },
  { key: 'progress', name: 'In progress', statuses: ['applied', 'screening', 'interviewing', 'offer'] },
  { key: 'closed', name: 'Closed', statuses: [...OUTCOMES, 'passed'] },
]

function sameSet(a: string[], b: string[]) {
  return a.length === b.length && a.every((x) => b.includes(x))
}

export function JobsView({ route, selectJob }: { route: Route; selectJob: (id: number) => void }) {
  const p = route.params
  const query = useMemo(() => {
    const q = new URLSearchParams(p)
    q.delete('job')
    return q.toString()
  }, [p])
  // Filtering keeps the current list up until the new one arrives, so rows move instead of blinking.
  const { data, loading } = useApi<JobList>(`/api/jobs${query ? `?${query}` : ''}`, { keep: true })
  const rows = useFlip<HTMLDivElement>()
  const [text, setText] = useState(p.get('q') ?? '')
  const [facetsOpen, setFacetsOpen] = useState(false)
  const selected = Number(p.get('job'))
  const chosenStatuses = p.getAll('status')

  useEffect(() => { setText(p.get('q') ?? '') }, [p])
  useEffect(() => {
    const t = setTimeout(() => { if ((p.get('q') ?? '') !== text) setParams({ q: text || null }) }, 250)
    return () => clearTimeout(t)
  }, [text, p])

  const active = activeFilters(p)
  const starredOnly = p.get('starred') === '1'
  const starredCount = data?.facets.starred?.find((f) => f.value === '1')?.count ?? 0
  const statusCounts = Object.fromEntries((data?.facets.status ?? []).map((f) => [f.value, f.count]))
  const quickCount = (statuses: string[]) => statuses.length
    ? statuses.reduce((n, s) => n + (statusCounts[s] ?? 0), 0)
    : Object.values(statusCounts).reduce((n, c) => n + c, 0)

  return (
    <>
      <aside className={`col col-facets${facetsOpen ? ' open' : ''}`} aria-label="Filters">
        <Filters data={data} params={p} onDone={facetsOpen ? () => setFacetsOpen(false) : undefined} />
      </aside>
      <section className="col col-list" aria-label="Jobs">
        <div className={`list-head${loading ? ' busy' : ''}`}>
          <h2>Jobs</h2>
          <span className="meta">{data ? <Num value={data.total} /> : ''}</span>
          <span className="spacer" />
          <button className="btn small quiet facets-toggle" onClick={() => setFacetsOpen(true)}>
            <SlidersHorizontal size={14} /> Filters{active > 0 && <span className="badge">{active}</span>}
          </button>
          <select className="input" value={p.get('sort') ?? 'priority'} onChange={(e) => setParams({ sort: e.target.value === 'priority' ? null : e.target.value })} aria-label="Sort">
            <option value="priority">Starred, then priority</option>
            <option value="due">Next step due</option>
            <option value="activity">Recently changed</option>
            <option value="newest">Recently found</option>
            <option value="posted">Recently posted</option>
            <option value="company">Company A–Z</option>
          </select>
          <div className="quick">
            <button className="quick-star" aria-pressed={starredOnly} onClick={() => setParams({ starred: starredOnly ? null : '1' })}>
              <StarIcon size={14} strokeWidth={2} />Starred<span className="n">{data ? starredCount : ''}</span>
            </button>
            <Thumbed className="views" label="Show">
              {QUICK.map((v) => (
                <button key={v.key} aria-pressed={sameSet(chosenStatuses, v.statuses)} onClick={() => setParams({ status: v.statuses })}>
                  {v.name}<span className="n">{data ? quickCount(v.statuses) : ''}</span>
                </button>
              ))}
            </Thumbed>
          </div>
          <div style={{ position: 'relative', width: '100%' }}>
            <Search size={15} style={{ position: 'absolute', left: 10, top: 9, color: 'var(--ink-3)' }} />
            <input className="input" style={{ width: '100%', paddingLeft: 32 }} placeholder="Search titles, companies, postings, notes"
                   value={text} onChange={(e) => setText(e.target.value)} />
          </div>
        </div>
        {!data && <Skeleton kind="rows" n={7} />}
        <div className={`rows${loading ? ' stale' : ''}`} ref={rows}>
          {data?.jobs.map((j) => <JobRow key={j.id} j={j} selected={selected === j.id} onSelect={() => selectJob(j.id)} />)}
        </div>
        {data && data.total === 0 && <p className="list-empty">No jobs match. Clear a filter or change the search.</p>}
      </section>
    </>
  )
}

// ------------------------------------------------------------------ people

export function PeopleView() {
  const { data: companies } = useApi<Company[]>('/api/companies')
  const { data: contacts } = useApi<Contact[]>('/api/contacts')
  return (
    <div className="people">
      <div className="panel">
        <h3>Companies <span style={{ color: 'var(--ink-3)', fontWeight: 600 }}>{companies?.length ?? ''}</span></h3>
        {companies?.map((c) => (
          <div className="person" key={c.id}>
            <div className="nm"><a href={href('jobs', { q: c.name })}>{c.name}</a></div>
            <div className="sub">
              {plural(c.job_count ?? 0, 'job')}{c.application_count ? `, ${c.application_count} applied` : ''}
              {[c.city, c.country].filter(Boolean).length ? `, ${[c.city, c.country].filter(Boolean).join(', ')}` : ''}
            </div>
            {c.visa_notes && <div className="sub" style={{ color: '#136b39' }}>{c.visa_notes}</div>}
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>Contacts <span style={{ color: 'var(--ink-3)', fontWeight: 600 }}>{contacts?.length ?? ''}</span></h3>
        {contacts?.map((c) => (
          <div className="person" key={c.id}>
            <div className="nm">{c.name}</div>
            <div className="sub">
              {[c.title, c.company].filter(Boolean).join(', ')}
              {c.email && <>{c.title || c.company ? ', ' : ''}<a href={`mailto:${c.email}`}>{c.email}</a></>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
