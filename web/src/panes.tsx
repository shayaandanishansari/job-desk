import { Check, ChevronDown, Copy, ExternalLink, FileText, Mail, MessageSquareReply, X } from 'lucide-react'
import { useState } from 'react'
import { href, patch, post, useApi } from './api'
import {
  act, BEFORE, isInProgress, Markdown, Menu, OUTCOMES, Prio, PROJECT_OUTCOMES, PROJECT_STAGES, Skeleton, STAGES, Star,
  StatusChip, Thumbs, Timeline, toast, Track,
} from './components'
import { ago, due, dueTone, fmtDate, fmtDateTime, label, place, plural, price, resumeLabel, todayIso } from './format'
import type { Draft, JobDetail, Kind, Meta, Outcome, ProjectDetail, ProjectOutcome, Thread } from './types'

const base = (kind: Kind) => (kind === 'project' ? '/api/projects' : '/api/jobs')

// A Gmail thread shared by several jobs is saved per job as "<threadId>#<part>". `account` is the
// first address in settings.json, so the link opens the right Gmail account.
const gmailThread = (id: string, account: string | null) =>
  `https://mail.google.com/mail/u/${account ? `?authuser=${encodeURIComponent(account)}` : '0/'}#all/${id.split('#')[0]}`

function isUrl(s: string | null) {
  return !!s && /^https?:\/\//.test(s)
}

function ApplyTarget({ to }: { to: string | null }) {
  if (!to) return <>Not given</>
  if (isUrl(to)) return <a href={to} target="_blank" rel="noreferrer">{to.replace(/^https?:\/\//, '')}</a>
  if (to.includes('@')) return <a href={`mailto:${to}`}>{to}</a>
  return <>{to}</>
}

function DateField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <input className="input" type="date" value={value} onChange={(e) => onChange(e.target.value)} />
}

// ------------------------------------------------------------------ status control

function StatusMenu({ job, meta }: { job: JobDetail; meta: Meta }) {
  const [on, setOn] = useState(todayIso())
  const set = (status: string, extra: Record<string, string> = {}) =>
    act(() => post(`/api/jobs/${job.id}/status`, { status, on, ...extra }), `Marked ${label(status)}`)
  const theirs = OUTCOMES.filter((o) => meta.outcome_side[o] === 'them')
  const mine = OUTCOMES.filter((o) => meta.outcome_side[o] === 'me')
  return (
    <Menu trigger={<button className="btn">Change status <ChevronDown size={14} /></button>}>
      {(close) => (<>
        <div className="group">Date</div>
        <div style={{ padding: '0 10px 6px' }}><DateField value={on} onChange={setOn} /></div>
        <div className="group">Before applying</div>
        {(['new', 'shortlisted'] as const).filter((s) => s !== job.status).map((s) => (
          <button key={s} onClick={() => { close(); set(s) }}>{label(s)}</button>
        ))}
        <div className="group">In progress</div>
        {STAGES.filter((s) => s !== job.status).map((s) => (
          <button key={s} onClick={() => { close(); set(s) }}>
            <span className="dot" style={{ background: `var(--st-${s})` }} /> {label(s)}
          </button>
        ))}
        <div className="group">They ended it</div>
        {theirs.filter((s) => s !== job.status).map((o) => <button key={o} onClick={() => { close(); set(o) }}>{label(o)}</button>)}
        <div className="group">You ended it</div>
        {mine.filter((s) => s !== job.status).map((o) => <button key={o} onClick={() => { close(); set(o) }}>{label(o)}</button>)}
        <div className="group">Not for you</div>
        {meta.vocab.PASS_REASONS.map((r) => (
          <button key={r} onClick={() => { close(); set('passed', { pass_reason: r }) }}>Pass: {label(r)}</button>
        ))}
      </>)}
    </Menu>
  )
}

// ------------------------------------------------------------------ next action

/** The next step on a job or project in progress, with "I sent the follow-up" when that's the step. */
function NextAction({ job }: { job: { id: number; kind: Kind; status: string; next_action: string | null; next_action_due: string | null } }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(job.next_action ?? '')
  const [when, setWhen] = useState(job.next_action_due ?? '')
  const tone = dueTone(job.next_action_due)
  const followUp = (job.kind === 'project' || job.status === 'applied') && /follow/i.test(job.next_action ?? '')

  const save = () => act(() => patch(`${base(job.kind)}/${job.id}`, { next_action: text || null, next_action_due: when || null }))
    .then(() => setEditing(false))

  if (editing) {
    return (
      <div className="next-box">
        <div className="next-line">
          <input className="input" style={{ flex: 1, minWidth: 200 }} value={text} onChange={(e) => setText(e.target.value)} placeholder="What's the next step?" autoFocus />
          <DateField value={when} onChange={setWhen} />
        </div>
        <div className="next-line">
          <button className="btn primary small" onClick={save}>Save next action</button>
          <button className="btn quiet small" onClick={() => setEditing(false)}>Cancel</button>
        </div>
      </div>
    )
  }
  return (
    <div className={`next-box ${tone === 'late' ? 'late' : tone === 'now' ? 'now' : ''}`}>
      <div className="next-line">
        <strong>{job.next_action ?? 'No next action set'}</strong>
        {job.next_action_due && <span className={`due ${tone}`}>{due(job.next_action_due)}</span>}
        <span style={{ marginLeft: 'auto' }} />
        {followUp && (
          <button className="btn small" onClick={() => act(() => post(`${base(job.kind)}/${job.id}/follow-up`, {}), 'Follow-up recorded')}>
            <Check size={14} /> I sent the follow-up
          </button>
        )}
        <button className="btn quiet small" onClick={() => { setText(job.next_action ?? ''); setWhen(job.next_action_due ?? ''); setEditing(true) }}>Change</button>
      </div>
    </div>
  )
}

const PRIORITY = ['', 'Send first', 'This week', 'If there is time', 'Skip or last']

function PriorityMenu({ kind, id, priority }: { kind: Kind; id: number; priority: number | null }) {
  return (
    <Menu trigger={<button className="btn quiet">Priority {priority ?? 'not set'} <ChevronDown size={14} /></button>}>
      {(closeMenu) => (<>
        {[1, 2, 3, 4, null].map((n) => (
          <button key={String(n)} onClick={() => { closeMenu(); act(() => patch(`${base(kind)}/${id}`, { priority: n })) }}>
            {n ? <Prio n={n} /> : null}{n ? PRIORITY[n] : 'Clear priority'}
          </button>
        ))}
      </>)}
    </Menu>
  )
}

// ------------------------------------------------------------------ email

function copyRich(draft: Draft) {
  const html = document.getElementById(`draft-${draft.id}`)?.innerHTML ?? ''
  const item = new ClipboardItem({
    'text/html': new Blob([html], { type: 'text/html' }),
    'text/plain': new Blob([draft.body], { type: 'text/plain' }),
  })
  navigator.clipboard.write([item]).then(() => toast('Email copied with formatting'), () => toast('Copy failed', 'error'))
}

function DraftCard({ draft }: { draft: Draft }) {
  const [expanded, setExpanded] = useState(draft.status === 'draft')
  const tone = { draft: 'blue', in_gmail: 'now', sent: 'ok', discarded: 'ghost' }[draft.status]
  const set = (status: string) => act(() => patch(`/api/drafts/${draft.id}`, { status }))
  return (
    <div className={`draft${expanded ? '' : ' collapsed'}`}>
      <div className="draft-head">
        <FileText size={16} />
        <strong>{draft.subject ?? '(no subject)'}</strong>
        <span className={`pill ${tone}`}>{draft.status === 'in_gmail' ? 'In Gmail drafts' : label(draft.status)}</span>
        <span style={{ marginLeft: 'auto' }} />
        <button className="btn quiet small" onClick={() => copyRich(draft)} title="Copy for pasting into Gmail"><Copy size={14} /> Copy</button>
        <Menu right trigger={<button className="btn quiet small">Mark <ChevronDown size={13} /></button>}>
          {(close) => (<>
            {(['draft', 'in_gmail', 'sent', 'discarded'] as const).map((s) => (
              <button key={s} onClick={() => { close(); set(s) }}>{s === 'in_gmail' ? 'In Gmail drafts' : label(s)}</button>
            ))}
          </>)}
        </Menu>
        <button className="btn quiet small" onClick={() => setExpanded((e) => !e)}>{expanded ? 'Collapse' : 'Show all'}</button>
      </div>
      <div style={{ fontSize: 13, color: 'var(--ink-3)', marginBottom: 8 }}>
        To {draft.to_addr ?? '(not set)'}{draft.attach_resume ? ', with the resume attached' : ''}
      </div>
      <div id={`draft-${draft.id}`}><Markdown text={draft.body} /></div>
    </div>
  )
}

function ThreadCard({ thread, account }: { thread: Thread; account: string | null }) {
  const [open, setOpen] = useState<Set<number>>(() => new Set(thread.messages.slice(-1).map((m) => m.id)))
  const toggle = (id: number) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  return (
    <div className="thread">
      <div className="thread-head">
        <Mail size={15} />
        <span>{thread.subject ?? '(no subject)'}</span>
        {thread.last_direction === 'in' && <span className="pill ok"><MessageSquareReply size={13} /> Their reply is last</span>}
        <span className="meta">{plural(thread.message_count, 'message')}</span>
        {thread.gmail_thread_id && <a className="btn quiet small" href={gmailThread(thread.gmail_thread_id, account)} target="_blank" rel="noreferrer">Open in Gmail</a>}
      </div>
      {thread.messages.map((m) => (
        <div key={m.id} className={`msg ${m.direction}${m.automated ? ' auto' : ''}`}>
          <div className="msg-head" onClick={() => toggle(m.id)} role="button" tabIndex={0}
               onKeyDown={(e) => { if (e.key === 'Enter') toggle(m.id) }}>
            <span className="who">{m.direction === 'out' ? 'You' : (m.from_addr ?? 'Them')}</span>
            {!!m.automated && <span className="pill ghost" title="A confirmation or notification, not a reply from a person">Automated</span>}
            {m.direction === 'out' && m.to_addrs && <span style={{ color: 'var(--ink-3)' }}>to {m.to_addrs}</span>}
            <span className="when">{fmtDateTime(m.sent_at)}</span>
          </div>
          {open.has(m.id) && (<>
            <div className="msg-body">{m.body ?? '(no text saved)'}</div>
            {m.attachments.length > 0 && (
              <div className="msg-attach">{m.attachments.map((a, i) => <span key={`${a}${i}`} className="pill">{a}</span>)}</div>
            )}
          </>)}
        </div>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------ the pane

export function JobPane({ id, meta, onClose }: { id: number; meta: Meta; onClose: () => void }) {
  const { data: job, error } = useApi<JobDetail>(`/api/jobs/${id}`)
  if (error) return <div className="pane"><p>{error}</p></div>
  if (!job) return <Skeleton kind="pane" />

  const pursued = !!job.stage_reached
  const active = isInProgress(job.status)
  const closed = (OUTCOMES as string[]).includes(job.status)
  const salary = job.salary_text || (job.salary_min ? `${job.salary_currency ?? ''} ${job.salary_min}${job.salary_max && job.salary_max !== job.salary_min ? `–${job.salary_max}` : ''}${job.salary_period ? ` per ${job.salary_period}` : ''}` : null)
  const flags = job.flags.filter((f) => !['overdue', 'due_today', 'no_next_action'].includes(f.flag))
  const close = (outcome: Outcome) => act(() => post(`/api/jobs/${job.id}/status`, { status: outcome }), `Closed: ${label(outcome)}`)

  const fit = job.fit_notes && (
    <section className="section" key="fit">
      <h3>Why it fits</h3>
      <div className="callout"><Markdown text={job.fit_notes} /></div>
    </section>
  )
  const howTo = (
    <section className="section" key="how">
      <h3>How to apply</h3>
      <dl className="kv">
        <dt>Method</dt><dd>{label(job.apply_method)}</dd>
        <dt>Where</dt><dd><ApplyTarget to={job.apply_to} /></dd>
        {job.apply_notes && <><dt>Notes</dt><dd>{job.apply_notes}</dd></>}
        {job.posted_by && <><dt>Posted by</dt><dd>{job.posted_by}</dd></>}
        {job.deadline && <><dt>Deadline</dt><dd>{fmtDate(job.deadline)}</dd></>}
        {job.company_info?.visa_notes && <><dt>Visa notes</dt><dd>{job.company_info.visa_notes}</dd></>}
      </dl>
    </section>
  )
  const application = pursued && (
    <section className="section" key="app">
      <h3>Application</h3>
      <dl className="kv">
        <dt>Sent</dt><dd>{job.applied_on ? `${fmtDate(job.applied_on)} (${ago(job.applied_on)}) by ${label(job.channel ?? 'other').toLowerCase()}` : 'Not yet'}</dd>
        <dt>Resume sent</dt>
        <dd>{job.resume
          ? job.resume.path
            ? <a href={`/api/resume?version=${encodeURIComponent(job.resume.id)}`} target="_blank" rel="noreferrer">{resumeLabel(job.resume.id)}</a>
            : `${resumeLabel(job.resume.id)} (file not found)`
          : job.applied_on ? 'Not recorded' : 'Recorded when it’s sent'}</dd>
        <dt>Follow-ups sent</dt><dd>{job.follow_ups_sent}{job.last_follow_up_on ? `, last on ${fmtDate(job.last_follow_up_on)}` : ''}</dd>
        <dt>Last contact</dt><dd>{job.last_contact_on ? `${fmtDate(job.last_contact_on)} (${ago(job.last_contact_on)})` : 'None'}</dd>
        <dt>First reply</dt><dd>{job.first_response_on ? fmtDate(job.first_response_on) : 'No reply yet'}</dd>
        {closed && <><dt>Closed</dt><dd>{fmtDate(job.closed_on)}{job.outcome_notes ? `: ${job.outcome_notes}` : ''}</dd></>}
        {job.notes && <><dt>Notes</dt><dd>{job.notes}</dd></>}
      </dl>
    </section>
  )
  const interviews = job.interviews.length > 0 && (
    <section className="section" key="iv">
      <h3>Interviews</h3>
      <dl className="kv">
        {job.interviews.map((iv) => (
          <div key={iv.id} style={{ display: 'contents' }}>
            <dt>{iv.scheduled_at ? fmtDateTime(iv.scheduled_at) : 'Not scheduled'}</dt>
            <dd>
              <strong>{label(iv.kind)}</strong>{iv.with_whom ? ` with ${iv.with_whom}` : ''}{iv.location ? `, ${iv.location}` : ''}
              {iv.prep_notes && <div style={{ color: 'var(--ink-2)' }}>{iv.prep_notes}</div>}
              {iv.outcome_notes && <div style={{ color: 'var(--ink-2)' }}>{iv.outcome_notes}</div>}
              {!iv.thank_you_sent && iv.kind !== 'take_home' && iv.scheduled_at && iv.scheduled_at < new Date().toISOString() && (
                <button className="btn small" style={{ marginTop: 6 }}
                        onClick={() => act(() => patch(`/api/interviews/${iv.id}`, { thank_you_sent: true }), 'Thank-you recorded')}>
                  I sent the thank-you
                </button>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
  const emails = (pursued || job.drafts.length > 0 || job.threads.length > 0) && (
    <section className="section" key="mail">
      <h3>Emails <span className="meta">{plural(job.threads.length, 'thread')}{job.drafts.length ? `, ${plural(job.drafts.length, 'draft')}` : ''}</span></h3>
      {job.drafts.filter((d) => d.status !== 'discarded').map((d) => <DraftCard key={d.id} draft={d} />)}
      {job.threads.map((t) => <ThreadCard key={t.id} thread={t} account={meta.me.gmail} />)}
      {!job.threads.length && !job.drafts.length && (
        <p style={{ color: 'var(--ink-3)' }}>No emails saved. Ask Claude to sync this job's Gmail thread.</p>
      )}
    </section>
  )

  return (
    <article className="pane">
      <div className="pane-kicker">
        <Prio n={job.priority} />
        <span>{label(job.source)}{job.source_ref ? ` #${job.source_ref}` : ''}</span>
        <span>Found {fmtDate(job.found_on)}</span>
        {job.posted_on && <span>Posted {fmtDate(job.posted_on)}</span>}
        <span style={{ marginLeft: 'auto' }}>
          <button className="btn quiet small pane-close" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </span>
      </div>
      <div className="pane-title">
        <h1>{job.title}</h1>
        <Star job={job} size={22} />
      </div>
      <div className="company-line">{job.company ?? 'Company not named'}, {place(job)}</div>

      <div className="facts">
        {job.work_mode !== 'unknown' && <span className="pill">{label(job.work_mode)}</span>}
        {job.employment_type !== 'unknown' && <span className="pill">{label(job.employment_type)}</span>}
        {job.seniority !== 'unknown' && <span className="pill">{label(job.seniority)}</span>}
        {job.experience && <span className="pill">{job.experience}</span>}
        {salary && <span className="pill">{salary}</span>}
        <span className={`pill visa-${job.visa}`}>{job.visa === 'yes' ? 'Sponsors visa' : job.visa === 'no' ? 'No visa sponsorship' : 'Visa unknown'}</span>
        {job.relocation === 'yes' && <span className="pill visa-yes">Relocation support</span>}
        {job.posting_status === 'closed' && <span className="pill late">Posting closed</span>}
        {job.tags.map((t) => <span key={t} className="pill ghost">{t}</span>)}
      </div>

      <div className="section" style={{ marginTop: 6 }}>
        {pursued
          ? <Track key={job.status} stage={job.stage_reached!} outcome={closed ? job.status as Outcome : null} side={job.outcome_side} big />
          : <StatusChip job={job} />}
      </div>

      <div className="actions" style={{ marginTop: 14 }}>
        <StatusMenu job={job} meta={meta} />
        {(BEFORE as string[]).includes(job.status) && job.status !== 'passed' && (
          <button className="btn primary" onClick={() => act(() => post(`/api/jobs/${job.id}/status`, { status: 'drafting' }), 'Started the application')}>
            Start application
          </button>
        )}
        {job.status === 'new' && (
          <button className="btn" onClick={() => act(() => post(`/api/jobs/${job.id}/status`, { status: 'shortlisted' }))}>Shortlist</button>
        )}
        <PriorityMenu kind="job" id={job.id} priority={job.priority} />
        {job.source_url && <a className="btn quiet" href={job.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Original posting</a>}
      </div>

      {flags.map((f) => (
        <div key={f.flag} className={`callout ${f.flag === 'suggest_no_response' ? 'warn' : ''}`} style={{ marginTop: 12 }}>
          {f.text}
          {f.flag === 'suggest_no_response' && (
            <> <button className="btn small" style={{ marginLeft: 8 }} onClick={() => close('no_response')}>Close as no response</button></>
          )}
        </div>
      ))}

      {active && <div className="section"><NextAction key={`${job.next_action}-${job.next_action_due}`} job={job} /></div>}

      {job.possible_duplicates.length > 0 && (
        <div className="callout warn section">
          Possibly the same job as{' '}
          {job.possible_duplicates.map((d, i) => (
            <span key={d.id}>{i > 0 && ', '}<a href={href('jobs', { job: String(d.id) })}>#{d.id} {d.title}</a> ({d.reason})</span>
          ))}.
        </div>
      )}
      {job.applied_here_before.length > 0 && (
        <div className="callout section">
          You've also applied to {job.company} for{' '}
          {job.applied_here_before.map((a, i) => (
            <span key={a.id}>{i > 0 && ', '}<a href={href('jobs', { job: String(a.id) })}>{a.title}</a> ({fmtDate(a.applied_on)}, {label(a.status)})</span>
          ))}.
        </div>
      )}
      {job.company_projects.length > 0 && (
        <div className="callout section">
          You also have client work with {job.company}:{' '}
          {job.company_projects.map((x, i) => (
            <span key={x.id}>{i > 0 && ', '}<a href={href('projects', { project: String(x.id) })}>{x.title}</a> ({label(x.status)})</span>
          ))}.
        </div>
      )}

      <section className="section">
        <h3>Contact</h3>
        <p>{job.contact
          ? <>{job.contact.name}{job.contact.title ? `, ${job.contact.title}` : ''}{job.contact.email && <>{' ('}<a href={`mailto:${job.contact.email}`}>{job.contact.email}</a>{')'}</>}</>
          : <span style={{ color: 'var(--ink-3)' }}>No contact yet</span>}</p>
      </section>

      {/* Once you've applied, the application comes first; before that, the fit and how to apply. */}
      {pursued ? [application, interviews, emails, fit, howTo] : [fit, howTo, emails]}

      {job.files.length > 0 && (
        <section className="section">
          <h3>Screenshots and files</h3>
          <Thumbs files={job.files} />
        </section>
      )}

      <section className="section">
        <h3>The posting</h3>
        {job.description
          ? <Markdown className="posting" text={job.description} />
          : <p style={{ color: 'var(--ink-3)' }}>The posting's text wasn't saved.</p>}
      </section>

      <section className="section">
        <h3>Timeline</h3>
        <Timeline events={job.timeline} entityType="job" entityId={job.id} />
      </section>
    </article>
  )
}

// ------------------------------------------------------------------ the project pane

function ProjectStatusMenu({ project, meta }: { project: ProjectDetail; meta: Meta }) {
  const [on, setOn] = useState(todayIso())
  const set = (status: string, extra: Record<string, string> = {}) =>
    act(() => post(`/api/projects/${project.id}/status`, { status, on, ...extra }), `Marked ${label(status)}`)
  const theirs = PROJECT_OUTCOMES.filter((o) => meta.outcome_side[o] === 'them')
  const mine = PROJECT_OUTCOMES.filter((o) => meta.outcome_side[o] === 'me' && o !== 'won')
  return (
    <Menu trigger={<button className="btn">Change status <ChevronDown size={14} /></button>}>
      {(close) => (<>
        <div className="group">Date</div>
        <div style={{ padding: '0 10px 6px' }}><DateField value={on} onChange={setOn} /></div>
        <div className="group">Before pitching</div>
        {(['lead', 'qualified'] as const).filter((s) => s !== project.status).map((s) => (
          <button key={s} onClick={() => { close(); set(s) }}>{label(s)}</button>
        ))}
        <div className="group">In progress</div>
        {PROJECT_STAGES.filter((s) => s !== project.status).map((s) => (
          <button key={s} onClick={() => { close(); set(s) }}>
            <span className="dot" style={{ background: `var(--st-${s})` }} /> {label(s)}
          </button>
        ))}
        {project.status !== 'won' && (<>
          <div className="group">Done</div>
          <button onClick={() => { close(); set('won') }}><span className="dot" style={{ background: 'var(--st-offer)' }} /> Won</button>
        </>)}
        <div className="group">They ended it</div>
        {theirs.filter((s) => s !== project.status).map((o) => <button key={o} onClick={() => { close(); set(o) }}>{label(o)}</button>)}
        <div className="group">You ended it</div>
        {mine.filter((s) => s !== project.status).map((o) => <button key={o} onClick={() => { close(); set(o) }}>{label(o)}</button>)}
        <div className="group">Not for you</div>
        {meta.vocab.PROJECT_PASS_REASONS.map((r) => (
          <button key={r} onClick={() => { close(); set('passed', { pass_reason: r }) }}>Pass: {label(r)}</button>
        ))}
      </>)}
    </Menu>
  )
}

export function ProjectPane({ id, meta, onClose }: { id: number; meta: Meta; onClose: () => void }) {
  const { data: p, error } = useApi<ProjectDetail>(`/api/projects/${id}`)
  if (error) return <div className="pane"><p>{error}</p></div>
  if (!p) return <Skeleton kind="pane" />

  const pursued = !!p.stage_reached
  const active = isInProgress(p.status, 'project')
  const closed = (PROJECT_OUTCOMES as string[]).includes(p.status)
  const upwork = p.channel === 'upwork' || p.source === 'upwork'
  const cost = price(p)
  const flags = p.flags.filter((f) => !['overdue', 'due_today', 'no_next_action'].includes(f.flag))
  const setStatus = (status: string, done?: string) => act(() => post(`/api/projects/${p.id}/status`, { status }), done)
  const projectLink = (x: { id: number; title: string; status: string }) =>
    <><a href={href('projects', { project: String(x.id) })}>{x.title}</a> ({label(x.status)})</>

  const fit = p.fit_notes && (
    <section className="section" key="fit">
      <h3>Why it fits</h3>
      <div className="callout"><Markdown text={p.fit_notes} /></div>
    </section>
  )
  const brief = (
    <section className="section" key="brief">
      <h3>What they need</h3>
      {p.description
        ? <Markdown className="posting" text={p.description} />
        : <p style={{ color: 'var(--ink-3)' }}>No brief saved yet.</p>}
    </section>
  )
  const pitch = pursued && (
    <section className="section" key="pitch">
      <h3>The pitch</h3>
      <dl className="kv">
        <dt>Pitched</dt><dd>{p.pitched_on ? `${fmtDate(p.pitched_on)} (${ago(p.pitched_on)})${p.channel ? `, via ${label(p.channel)}` : ''}` : 'Not yet'}</dd>
        <dt>Your price</dt><dd>{cost ? `${cost}${p.pricing === 'fixed' ? ', fixed' : ''}` : 'Not set'}</dd>
        {p.budget_text && <><dt>Their budget</dt><dd>{p.budget_text}</dd></>}
        <dt>Follow-ups sent</dt><dd>{p.follow_ups_sent}{p.last_follow_up_on ? `, last on ${fmtDate(p.last_follow_up_on)}` : ''}</dd>
        <dt>Last contact</dt><dd>{p.last_contact_on ? `${fmtDate(p.last_contact_on)} (${ago(p.last_contact_on)})` : 'None'}</dd>
        <dt>First reply</dt><dd>{p.first_response_on ? fmtDate(p.first_response_on) : 'No reply yet'}</dd>
        {closed && <><dt>{p.status === 'won' ? 'Won' : 'Closed'}</dt><dd>{fmtDate(p.closed_on)}{p.outcome_notes ? `: ${p.outcome_notes}` : ''}</dd></>}
        {p.notes && <><dt>Notes</dt><dd>{p.notes}</dd></>}
      </dl>
    </section>
  )
  const emails = (pursued || p.drafts.length > 0 || p.threads.length > 0) && (
    <section className="section" key="mail">
      <h3>Emails <span className="meta">{plural(p.threads.length, 'thread')}{p.drafts.length ? `, ${plural(p.drafts.length, 'draft')}` : ''}</span></h3>
      {p.drafts.filter((d) => d.status !== 'discarded').map((d) => <DraftCard key={d.id} draft={d} />)}
      {p.threads.map((t) => <ThreadCard key={t.id} thread={t} account={meta.me.gmail} />)}
      {!p.threads.length && !p.drafts.length && (
        <p style={{ color: 'var(--ink-3)' }}>No emails saved. Ask Claude to sync this project's Gmail thread.</p>
      )}
    </section>
  )

  return (
    <article className="pane">
      <div className="pane-kicker">
        <Prio n={p.priority} />
        <span className="kind-tag">Client work</span>
        <span>{label(p.source)}{p.source_ref ? ` #${p.source_ref}` : ''}</span>
        <span>Found {fmtDate(p.found_on)}</span>
        <span style={{ marginLeft: 'auto' }}>
          <button className="btn quiet small pane-close" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </span>
      </div>
      <div className="pane-title">
        <h1>{p.title}</h1>
        <Star job={p} size={22} />
      </div>
      <div className="company-line">{p.company ?? 'No company yet'}</div>

      <div className="facts">
        {cost && <span className="pill">{cost}</span>}
        {p.pricing !== 'unknown' && <span className="pill">{label(p.pricing)}</span>}
        {p.budget_text && <span className="pill ghost" title="Their budget, as they put it">Their budget: {p.budget_text}</span>}
        {p.channel && <span className="pill">Via {label(p.channel)}</span>}
        {p.tags.map((t) => <span key={t} className="pill ghost">{t}</span>)}
      </div>

      <div className="section" style={{ marginTop: 6 }}>
        {pursued
          ? <Track key={p.status} kind="project" stage={p.stage_reached!} outcome={closed ? p.status as ProjectOutcome : null} side={p.outcome_side} big />
          : <StatusChip job={p} />}
      </div>

      <div className="actions" style={{ marginTop: 14 }}>
        <ProjectStatusMenu project={p} meta={meta} />
        {(p.status === 'lead' || p.status === 'qualified') && (
          <button className="btn primary" onClick={() => setStatus('drafting', 'Started the pitch')}>
            {upwork ? 'Start the proposal' : 'Start the pitch'}
          </button>
        )}
        {p.status === 'lead' && <button className="btn" onClick={() => setStatus('qualified')}>Qualify</button>}
        {p.status === 'drafting' && (
          <button className="btn primary" onClick={() => setStatus('pitched', 'Marked as pitched')}>
            {upwork ? 'I submitted the proposal' : 'I sent the pitch'}
          </button>
        )}
        {(p.status === 'proposal' || p.status === 'negotiating') && (
          <button className="btn primary" onClick={() => setStatus('won', 'Won')}>We won it</button>
        )}
        <PriorityMenu kind="project" id={p.id} priority={p.priority} />
        {p.source_url && <a className="btn quiet" href={p.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Original posting</a>}
      </div>

      {flags.map((f) => (
        <div key={f.flag} className={`callout ${f.flag === 'suggest_no_response' ? 'warn' : ''}`} style={{ marginTop: 12 }}>
          {f.text}
          {f.flag === 'suggest_no_response' && (
            <> <button className="btn small" style={{ marginLeft: 8 }} onClick={() => setStatus('no_response', 'Closed: No response')}>Close as no response</button></>
          )}
        </div>
      ))}

      {active && <div className="section"><NextAction key={`${p.next_action}-${p.next_action_due}`} job={p} /></div>}

      {p.possible_duplicates.length > 0 && (
        <div className="callout warn section">
          Possibly the same as{' '}
          {p.possible_duplicates.map((d, i) => (
            <span key={d.id}>{i > 0 && ', '}<a href={href('projects', { project: String(d.id) })}>#{d.id} {d.title}</a> ({d.reason})</span>
          ))}.
        </div>
      )}
      {(p.follow_on_from || p.follow_ons.length > 0) && (
        <div className="callout section">
          {p.follow_on_from && <div>More work after {projectLink(p.follow_on_from)}.</div>}
          {p.follow_ons.length > 0 && (
            <div>Work that came after this: {p.follow_ons.map((x, i) => <span key={x.id}>{i > 0 && ', '}{projectLink(x)}</span>)}.</div>
          )}
        </div>
      )}
      {(p.company_jobs.length > 0 || p.company_projects.length > 0) && (
        <div className="callout section">
          Also with {p.company}:{' '}
          {p.company_projects.map((x, i) => <span key={`p${x.id}`}>{i > 0 && ', '}{projectLink(x)}</span>)}
          {p.company_projects.length > 0 && p.company_jobs.length > 0 && ', '}
          {p.company_jobs.map((j, i) => (
            <span key={`j${j.id}`}>{i > 0 && ', '}the <a href={href('jobs', { job: String(j.id) })}>{j.title}</a> job ({label(j.status)})</span>
          ))}.
        </div>
      )}

      <section className="section">
        <h3>Contact</h3>
        <p>{p.contact
          ? <>{p.contact.name}{p.contact.role && <span className="pill ghost role">{label(p.contact.role)}</span>}
              {p.contact.title ? `, ${p.contact.title}` : ''}
              {p.contact.email && <>{' ('}<a href={`mailto:${p.contact.email}`}>{p.contact.email}</a>{')'}</>}</>
          : <span style={{ color: 'var(--ink-3)' }}>No contact yet</span>}</p>
      </section>

      {/* Once it's pitched, the pitch and its emails come first; before that, the fit and the brief. */}
      {pursued ? [pitch, emails, brief, fit] : [fit, brief, emails]}

      {p.files.length > 0 && (
        <section className="section">
          <h3>Files</h3>
          <Thumbs files={p.files} />
        </section>
      )}

      <section className="section">
        <h3>Timeline</h3>
        <Timeline events={p.timeline} entityType="project" entityId={p.id} />
      </section>
    </article>
  )
}
