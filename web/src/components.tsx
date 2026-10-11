import DOMPurify from 'dompurify'
import { ExternalLink, Mail, Star as StarIcon } from 'lucide-react'
import { marked } from 'marked'
import {
  useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore,
  type CSSProperties, type MouseEvent as ReactMouseEvent, type ReactNode,
} from 'react'
import { patch, post, reducedMotion } from './api'
import { actorName, dueTone, fmtDate, fmtDateTime, label } from './format'
import type {
  EventRow, FileRow, Kind, Outcome, ProjectOutcome, ProjectStage, ProjectStatus, Pursuit, Side, Stage, Status,
} from './types'

export const STAGES: Stage[] = ['drafting', 'applied', 'screening', 'interviewing', 'offer']
export const PROJECT_STAGES: ProjectStage[] = ['drafting', 'pitched', 'talking', 'proposal', 'negotiating']

/** The five stops of a job's or a project's route line. */
export function stagesOf(kind: Kind | undefined): string[] {
  return kind === 'project' ? PROJECT_STAGES : STAGES
}

export function stageColor(stage: string | null | undefined) {
  return stage ? `var(--st-${stage})` : 'var(--rule-strong)'
}

export function endColor(outcome: Outcome | ProjectOutcome | null | undefined, side: Side | null | undefined) {
  if (!outcome) return null
  if (outcome === 'accepted' || outcome === 'won') return 'var(--st-offer)'
  if (outcome === 'no_response') return 'var(--ink-3)'
  return side === 'them' ? 'var(--end-them)' : 'var(--end-me)'
}

/** The route line: five stops, filled up to the current one. A closed application (or project)
 *  ends in a terminus bar at the stage it reached, coloured by who ended it. */
export function Track({ stage, outcome, side, big, kind }: {
  stage: Stage | ProjectStage; outcome?: Outcome | ProjectOutcome | null; side?: Side | null; big?: boolean; kind?: Kind
}) {
  const STAGES = stagesOf(kind)
  const cur = STAGES.indexOf(stage)
  const line = endColor(outcome, side) ?? stageColor(stage)
  return (
    <div>
      <div className={`track${big ? ' big' : ''}`} style={{ ['--line' as string]: line }}
           role="img" aria-label={`Stage: ${label(stage)}${outcome ? `, closed: ${label(outcome)}` : ''}`}>
        {STAGES.map((s, i) => {
          const cls = i < cur ? 'done' : i === cur ? (outcome ? 'done end' : 'done here') : outcome ? 'gone' : 'future'
          return (
            <div key={s} className={`seg ${cls}`} style={{ '--i': i } as CSSProperties}>
              <span className="stop" />
              <span className="name">{label(s)}</span>
            </div>
          )
        })}
      </div>
      {outcome && (
        <div className="track-end" style={{ color: line }}>
          {label(outcome)}{side === 'me' ? ' (your call)' : ''}
        </div>
      )}
    </div>
  )
}

export const BEFORE: Status[] = ['new', 'shortlisted', 'passed']
export const OUTCOMES: Outcome[] = ['accepted', 'rejected', 'role_filled', 'no_response', 'withdrew', 'declined']
export const PROJECT_BEFORE: ProjectStatus[] = ['lead', 'qualified', 'passed']
export const PROJECT_OUTCOMES: ProjectOutcome[] = ['won', 'lost', 'no_response', 'cancelled', 'turned_down']

export function isInProgress(status: Status | ProjectStatus, kind: Kind = 'job'): boolean {
  return stagesOf(kind).includes(status)
}

/** The colour a status is drawn in: its stage line while in progress, its ending once closed. */
export function statusColor(j: { status: Status | ProjectStatus; outcome_side: Side | null; kind?: Kind }) {
  if (isInProgress(j.status, j.kind)) return stageColor(j.status)
  if (j.status === 'new' || j.status === 'lead') return 'var(--accent)'
  if (j.status === 'shortlisted' || j.status === 'qualified') return 'var(--ink-2)'
  if (j.status === 'passed') return 'var(--ink-3)'
  return endColor(j.status as Outcome, j.outcome_side) ?? 'var(--ink-3)'
}

/** The row tag: a tiny route line (once the job or project has been pursued) and the status name. */
export function StatusChip({ job }: { job: { kind?: Kind; status: Status | ProjectStatus; stage_reached: string | null; outcome_side: Side | null; pass_reason?: string | null } }) {
  const STAGES = stagesOf(job.kind)
  const color = statusColor(job)
  const reached = job.stage_reached ? STAGES.indexOf(job.stage_reached) : -1
  const name = job.status === 'passed' && job.pass_reason ? `Passed: ${label(job.pass_reason)}` : label(job.status)
  return (
    <span className={`status-chip${job.status === 'passed' ? ' muted' : ''}`} style={{ ['--line' as string]: color }}>
      {reached >= 0 && (
        <span className="mini" aria-hidden="true">
          {STAGES.map((s, i) => (
            <span key={s} className="mini-step">
              {i > 0 && <b className={i <= reached ? 'on' : ''} />}
              <i className={i <= reached ? 'on' : ''} />
            </span>
          ))}
        </span>
      )}
      {name}
    </span>
  )
}

/** Small tags after the status: what's due, follow-ups, replies, interviews, drafts. */
/** "linkedin.com/jobs/view/4466646758" from a full URL: enough to tell where it goes. */
function shortUrl(u: string) {
  try {
    const x = new URL(u)
    return x.host.replace(/^www\./, '') + x.pathname.replace(/\/$/, '')
  } catch {
    return u
  }
}

/** Where to apply, on the card: an email address or a link, clickable without opening the job. */
export function ApplyLink({ to }: { to: string | null }) {
  if (!to) return null
  const stop = (e: ReactMouseEvent) => e.stopPropagation()
  if (/^https?:\/\//.test(to)) {
    return (
      <div className="row-apply">
        <ExternalLink size={13} aria-hidden />
        <a href={to} target="_blank" rel="noreferrer" title={to} onClick={stop}>{shortUrl(to)}</a>
      </div>
    )
  }
  if (to.includes('@')) {
    return (
      <div className="row-apply">
        <Mail size={13} aria-hidden />
        <a href={`mailto:${to}`} title={`Email ${to}`} onClick={stop}>{to}</a>
      </div>
    )
  }
  return <div className="row-apply"><span>{to}</span></div>
}

export function Signals({ job }: { job: Pursuit }) {
  const out: ReactNode[] = []
  if (isInProgress(job.status, job.kind) && job.next_action_due) {
    const tone = dueTone(job.next_action_due)
    if (tone === 'late' || tone === 'now') {
      out.push(<span key="due" className={`pill ${tone}`} title={job.next_action ?? ''}>
        {tone === 'late' ? 'Overdue' : 'Due today'}
      </span>)
    }
  }
  if (job.flags.some((f) => f.flag === 'reply_waiting')) out.push(<span key="reply" className="pill ok">Reply waiting</span>)
  if (job.kind === 'job' && job.next_interview) out.push(<span key="iv" className="pill blue">Interview {fmtDate(job.next_interview)}</span>)
  if (job.follow_ups_sent > 0) {
    out.push(<span key="fu" className="pill">{job.follow_ups_sent === 1 ? '1 follow-up' : `${job.follow_ups_sent} follow-ups`}</span>)
  }
  if (job.open_drafts > 0) out.push(<span key="dr" className="pill">Draft ready</span>)
  return <>{out}</>
}

marked.setOptions({ breaks: true, gfm: true })
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function Markdown({ text, className }: { text: string | null | undefined; className?: string }) {
  if (!text) return null
  const html = DOMPurify.sanitize(marked.parse(text, { async: false }) as string)
  return <div className={`md ${className ?? ''}`} dangerouslySetInnerHTML={{ __html: html }} />
}

/** Your own marker for jobs (and projects) you care about. Fills in at once; rolls back if the save fails. */
export function Star({ job, size = 17 }: { job: { id: number; starred: number; kind?: Kind }; size?: number }) {
  const [on, setOn] = useState(!!job.starred)
  const [pops, setPops] = useState(0)
  useEffect(() => { setOn(!!job.starred) }, [job.starred])
  const toggle = (e: ReactMouseEvent) => {
    e.stopPropagation()
    const next = !on
    setOn(next)
    if (next) setPops((n) => n + 1)
    act(() => patch(`/api/${job.kind === 'project' ? 'projects' : 'jobs'}/${job.id}`, { starred: next }))
      .then((r) => { if (r === undefined) setOn(!next) })
  }
  return (
    <button type="button" className={`star${on ? ' on' : ''}`} onClick={toggle} aria-pressed={on}
            aria-label={on ? 'Starred. Click to remove the star' : `Star this ${job.kind ?? 'job'}`} title={on ? 'Remove star' : 'Star'}>
      <StarIcon key={pops} className={pops && on ? 'pop' : undefined} size={size} strokeWidth={2} />
      {pops > 0 && on && <span key={`b${pops}`} className="burst" aria-hidden="true" />}
    </button>
  )
}

/** A starred job in a list that can't hold the toggle. */
export function StarMark() {
  return <span className="star on static" role="img" aria-label="Starred"><StarIcon size={14} strokeWidth={2} /></span>
}

export function Prio({ n }: { n: number | null }) {
  if (!n) return null
  const words = ['', 'Send first', 'This week', 'If there is time', 'Skip or last']
  return <span className={`prio prio-${n}`} title={`Priority ${n}: ${words[n]}`}>{n}</span>
}

export function Menu({ trigger, children, right }: { trigger: ReactNode; children: (close: () => void) => ReactNode; right?: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])
  return (
    <div className="menu" ref={ref}>
      <span onClick={() => setOpen((o) => !o)}>{trigger}</span>
      {open && <div className={`menu-list${right ? ' right' : ''}`}>{children(() => setOpen(false))}</div>}
    </div>
  )
}

export function Thumbs({ files }: { files: FileRow[] }) {
  const [big, setBig] = useState<FileRow | null>(null)
  if (!files.length) return null
  const isImage = (p: string) => /\.(png|jpe?g|gif|webp)$/i.test(p)
  return (
    <>
      <div className="thumbs">
        {files.map((f) => isImage(f.path) ? (
          <button key={f.id} className="thumb" onClick={() => setBig(f)} title="Open full size">
            <img src={`/files/${f.path}`} alt={f.caption ?? f.kind} loading="lazy" />
            <span>{f.caption ?? label(f.kind)}</span>
          </button>
        ) : (
          <a key={f.id} className="pill" href={`/files/${f.path}`} target="_blank" rel="noreferrer">{f.caption ?? f.path}</a>
        ))}
      </div>
      {big && (
        <div className="lightbox" onClick={() => setBig(null)} role="dialog" aria-label={big.caption ?? 'Image'}>
          <img src={`/files/${big.path}`} alt={big.caption ?? ''} />
        </div>
      )}
    </>
  )
}

export function Timeline({ events, entityType, entityId }: { events: EventRow[]; entityType: 'job' | 'project' | 'company'; entityId: number }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const add = async () => {
    if (!text.trim()) return
    setBusy(true)
    try {
      await post('/api/notes', { entity_type: entityType, entity_id: entityId, text })
      setText('')
    } catch (e) {
      toast((e as Error).message, 'error')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div>
      <div className="note-form">
        <textarea className="input" rows={1} placeholder="Add a note" value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) add() }} />
        <button className="btn" onClick={add} disabled={busy || !text.trim()}>Add note</button>
      </div>
      <ul className="timeline">
        {events.map((e) => (
          <li key={e.id} className={e.action === 'note' ? 'note' : ''}>
            <span className="when" title={fmtDateTime(e.at)}>{fmtDate(e.at)}</span>
            <span>
              <span className={`who ${e.actor}`}>{actorName(e.actor)}</span>
              <span className="text">{e.action === 'note' ? e.summary : e.summary}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ------------------------------------------------------------------ toasts

type Toast = { id: number; text: string; who?: string; kind?: 'error'; life: number; leaving?: boolean }
let toasts: Toast[] = []
const toastListeners = new Set<() => void>()
let nextId = 1

function setToasts(next: Toast[]) {
  toasts = next
  toastListeners.forEach((l) => l())
}

export function toast(text: string, kind?: 'error', who?: string) {
  const t: Toast = { id: nextId++, text, kind, who, life: kind === 'error' ? 7000 : 4500 }
  setToasts([...toasts, t].slice(-4))
  setTimeout(() => {
    setToasts(toasts.map((x) => (x.id === t.id ? { ...x, leaving: true } : x)))
    setTimeout(() => setToasts(toasts.filter((x) => x.id !== t.id)), 220)
  }, t.life)
}

export function Toasts() {
  const list = useSyncExternalStore((cb) => { toastListeners.add(cb); return () => toastListeners.delete(cb) }, () => toasts)
  return (
    <div className="toasts" aria-live="polite">
      {list.map((t) => (
        <div key={t.id} className={`toast${t.kind === 'error' ? ' error' : ''}${t.leaving ? ' leaving' : ''}`}
             style={{ '--life': `${t.life}ms` } as CSSProperties}>
          {t.who && <b>{t.who}</b>}{t.text}
        </div>
      ))}
    </div>
  )
}

/** Run an API action and report failures as a toast. */
export async function act<T>(fn: () => Promise<T>, done?: string): Promise<T | undefined> {
  try {
    const r = await fn()
    if (done) toast(done)
    return r
  } catch (e) {
    toast((e as Error).message, 'error')
    return undefined
  }
}

export function EmptyPane({ children }: { children: ReactNode }) {
  return (
    <div className="pane-empty">
      <div>
        <svg className="art" width="120" height="40" viewBox="0 0 120 40" aria-hidden="true">
          <path d="M6 20h108" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeDasharray="2 10" />
          <circle cx="20" cy="20" r="8" fill="#fff" stroke="currentColor" strokeWidth="3" />
          <circle cx="60" cy="20" r="8" fill="#fff" stroke="currentColor" strokeWidth="3" />
          <circle cx="100" cy="20" r="8" fill="currentColor" />
        </svg>
        <p>{children}</p>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ motion

const EASE_OUT = 'cubic-bezier(.2,.8,.2,1)'
const FAR = 320 // px: a move longer than about three rows fades in place instead of sliding

/** Animate the `[data-flip]` children of the returned ref: a child that wasn't there before rises
 *  in (one after another), and one that moved slides from where it was, so a list that re-sorts
 *  or is filtered moves rather than jumps. Done here rather than in CSS because a CSS entrance
 *  replays whenever React moves the element. The container needs position: relative. */
export function useFlip<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const last = useRef(new Map<string, number>())
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const next = new Map<string, number>()
    const still = reducedMotion()
    let entering = 0
    el.querySelectorAll<HTMLElement>(':scope > [data-flip]').forEach((child) => {
      const key = child.dataset.flip!
      const top = child.offsetTop
      next.set(key, top)
      if (still) return
      const was = last.current.get(key)
      const dy = was === undefined ? 0 : was - top
      if (was === undefined || Math.abs(dy) > FAR) {
        // New, or moved from far away (a re-sort): rise in where it lands rather than fly across the list.
        child.animate([{ opacity: 0, transform: `translateY(${dy < 0 ? -8 : 8}px)`, offset: 0 }],
                      { duration: 420, easing: EASE_OUT, delay: Math.min(entering++, 12) * 28, fill: 'backwards' })
      } else if (dy) {
        child.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], { duration: 340, easing: EASE_OUT })
      }
    })
    last.current = next
  })
  return ref
}

/** A list whose `[data-flip]` children enter and move with useFlip. */
export function FlipList({ className, children }: { className?: string; children: ReactNode }) {
  const ref = useFlip<HTMLDivElement>()
  return <div className={`flip${className ? ` ${className}` : ''}`} ref={ref}>{children}</div>
}

/** A group of buttons with a pill behind the pressed one, which slides when another is pressed. */
export function Thumbed({ className, label: name, children }: { className: string; label: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState<string | null>(null)   // where the pressed button is, or was last
  const [on, setOn] = useState(false)
  const measure = useCallback(() => {
    const b = ref.current?.querySelector<HTMLElement>(':scope > [aria-pressed="true"]')
    setOn(!!b)
    if (b) setBox(`${b.offsetLeft} ${b.offsetTop} ${b.offsetWidth} ${b.offsetHeight}`)
  }, [])
  useLayoutEffect(measure)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    el.querySelectorAll(':scope > button').forEach((b) => ro.observe(b))
    return () => ro.disconnect()
  }, [measure])
  const [x, y, w, h] = (box ?? '0 0 0 0').split(' ').map(Number)
  return (
    <div className={className} role="group" aria-label={name} ref={ref}>
      <span className={`thumb-pill${on ? '' : ' off'}`} aria-hidden="true"
            style={{ transform: `translate(${x}px, ${y}px)`, width: w, height: h }} />
      {children}
    </div>
  )
}

/** A number that counts to its new value instead of jumping. */
export function Num({ value, format = (n: number) => String(Math.round(n)) }: { value: number; format?: (n: number) => string }) {
  const [shown, setShown] = useState(() => (reducedMotion() ? value : 0))
  const cur = useRef(shown)
  useEffect(() => {
    const from = cur.current
    if (from === value || reducedMotion()) {
      cur.current = value
      setShown(value)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 650)
      const v = k === 1 ? value : from + (value - from) * (1 - Math.pow(1 - k, 3))
      cur.current = v
      setShown(v)
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return <>{format(shown)}</>
}

/** Goes up by one each time `value` changes after the first render: a key for a one-off flash. */
export function useChanged(value: unknown) {
  const prev = useRef(value)
  const [n, setN] = useState(0)
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value
      setN((x) => x + 1)
    }
  }, [value])
  return n
}

/** Grey bars in the shape of what's loading. Fades in late, so quick loads never show it. */
export function Skeleton({ kind, n = 6 }: { kind: 'rows' | 'pane' | 'today'; n?: number }) {
  if (kind === 'pane') {
    return (
      <div className="pane skel-wrap" aria-busy="true" aria-label="Loading">
        <i className="skel" style={{ width: 180, height: 12 }} />
        <i className="skel" style={{ width: '70%', height: 26, marginTop: 14 }} />
        <i className="skel" style={{ width: '40%', height: 16, marginTop: 10 }} />
        <div style={{ display: 'flex', gap: 6, marginTop: 18 }}>
          {[70, 60, 90, 80].map((w, i) => <i key={i} className="skel" style={{ width: w, height: 22, borderRadius: 11 }} />)}
        </div>
        <i className="skel" style={{ width: '100%', height: 44, marginTop: 24 }} />
        {[92, 88, 95, 60].map((w, i) => <i key={i} className="skel" style={{ width: `${w}%`, height: 12, marginTop: i ? 10 : 30 }} />)}
      </div>
    )
  }
  return (
    <div className={`skel-wrap${kind === 'today' ? ' today' : ''}`} aria-busy="true" aria-label="Loading">
      {kind === 'today' && <>
        <i className="skel" style={{ width: 160, height: 12 }} />
        <i className="skel" style={{ width: '60%', height: 30, margin: '12px 0 30px' }} />
      </>}
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skel-row">
          <i className="skel" style={{ width: `${55 - (i % 3) * 9}%`, height: 14 }} />
          <i className="skel" style={{ width: `${35 + (i % 2) * 12}%`, height: 11, marginTop: 9 }} />
        </div>
      ))}
    </div>
  )
}
