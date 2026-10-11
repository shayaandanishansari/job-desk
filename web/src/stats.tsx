import { useState, type CSSProperties } from 'react'
import { setParams, useApi, type Route } from './api'
import { Num, PROJECT_OUTCOMES, PROJECT_STAGES, STAGES, Thumbed } from './components'
import { fmtDate, label, money, plural, resumeLabel } from './format'
import type { Funnel, Money, ProjectFunnel, ProjectStats, Stats } from './types'

const pct = (n: number, of: number) => (of ? `${Math.round((n / of) * 100)}%` : '–')
const percent = (n: number) => `${Math.round(n)}%`

/** A headline number that counts up from zero. `null` shows a dash. */
function Tile({ value, format, caption }: { value: number | null; format?: (n: number) => string; caption: string }) {
  return (
    <div className="panel" style={{ padding: '16px 18px' }}>
      <div style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.1 }}>
        {value == null ? '–' : <Num value={value} format={format} />}
      </div>
      <div style={{ color: 'var(--ink-2)', fontSize: 13, marginTop: 4 }}>{caption}</div>
    </div>
  )
}

/** Steps of a funnel, each a share of the first. One series, one hue; each bar is labelled. */
function Steps({ steps, of, name: chart }: { steps: [string, number][]; of: string; name: string }) {
  const total = steps[0][1]
  const max = Math.max(total, 1)
  return (
    <div role="table" aria-label={chart}>
      {steps.map(([name, n], i) => (
        <div className="funnel-row" role="row" key={name} title={`${name}: ${n} (${pct(n, total)} of ${of})`}>
          <span role="cell">{name}</span>
          <span className="bar" role="cell"><i style={{ width: `${(n / max) * 100}%`, background: 'var(--accent)', borderRadius: '0 4px 4px 0', '--i': i } as CSSProperties} /></span>
          <span className="num" role="cell">{n}<small>{i === 0 ? '' : pct(n, total)}</small></span>
        </div>
      ))}
    </div>
  )
}

/** Applied -> responded -> interviewed -> offers. */
function FunnelChart({ f }: { f: Funnel }) {
  return <Steps name="Application funnel" of="applications"
                steps={[['Applied', f.applied], ['Got a reply', f.responded], ['Interviewed', f.interviewed], ['Offers', f.offers]]} />
}

function Weeks({ weeks, noun = 'application' }: { weeks: Stats['weeks']; noun?: string }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(...weeks.map((w) => w.sent), 1)
  const peak = weeks.reduce((best, w, i) => (w.sent > weeks[best].sent ? i : best), 0)
  return (
    <div style={{ position: 'relative' }}>
      <div className="weeks" onMouseLeave={() => setHover(null)}>
        {weeks.map((w, i) => {
          const showValue = w.sent > 0 && (i === peak || i === weeks.length - 1 || i === hover)
          return (
            <div className="wk" key={w.week} onMouseEnter={() => setHover(i)} title={`Week of ${fmtDate(w.week)}: ${plural(w.sent, noun, noun === 'pitch' ? 'pitches' : undefined)}`}>
              <b style={{ visibility: showValue ? 'visible' : 'hidden' }}>{w.sent}</b>
              <i className={w.sent ? '' : 'zero'} style={{ height: `${(w.sent / max) * 78}%`, opacity: hover === null || hover === i ? 1 : 0.55, '--i': i } as CSSProperties} />
              <span>{i % 2 === weeks.length % 2 ? fmtDate(w.week) : ''}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Breakdown({ rows, what }: { rows: Stats['by_source']; what: string }) {
  if (!rows.length) return <p style={{ color: 'var(--ink-3)' }}>Nothing sent yet.</p>
  return (
    <table className="table">
      <thead>
        <tr><th>{what}</th><th className="n">Sent</th><th className="n">Replies</th><th className="n">Interviews</th><th className="n">Offers</th><th className="n">Reply rate</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.value}>
            <td>{what === 'Resume version' ? resumeLabel(r.value) : r.value === 'unknown' ? 'Not given' : label(r.value)}</td>
            <td className="n">{r.applied}</td><td className="n">{r.responded}</td>
            <td className="n">{r.interviewed}</td><td className="n">{r.offers}</td>
            <td className="n">{pct(r.responded, r.applied)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Pitched -> replied -> proposal -> won, broken down by `what`. */
function ProjectBreakdown({ rows, what }: { rows: ProjectStats['by_source']; what: string }) {
  if (!rows.length) return <p style={{ color: 'var(--ink-3)' }}>Nothing pitched yet.</p>
  return (
    <table className="table">
      <thead>
        <tr><th>{what}</th><th className="n">Pitched</th><th className="n">Replies</th><th className="n">Proposals</th><th className="n">Won</th><th className="n">Reply rate</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.value}>
            <td>{r.value === 'unknown' ? 'Not given' : label(r.value)}</td>
            <td className="n">{r.pitched}</td><td className="n">{r.replied}</td>
            <td className="n">{r.proposals}</td><td className="n">{r.won}</td>
            <td className="n">{pct(r.replied, r.pitched)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** "$1,500", "$30/hr on average", "$500 a month": one line per currency and kind of pricing. */
function moneyText(g: Money) {
  if (g.pricing === 'hourly') return `${money(g.average, g.currency)}/hr on average`
  if (g.pricing === 'retainer') return `${money(g.total, g.currency)} a month`
  return money(g.total, g.currency)
}

function MoneyTable({ rows, empty }: { rows: Money[]; empty: string }) {
  if (!rows.length) return <p style={{ color: 'var(--ink-3)' }}>{empty}</p>
  return (
    <table className="table"><tbody>
      {rows.map((g) => (
        <tr key={`${g.pricing}-${g.currency}`}>
          <td>{g.pricing === 'unknown' ? 'Price set' : label(g.pricing)} <span style={{ color: 'var(--ink-3)' }}>({plural(g.count, 'project')})</span></td>
          <td className="n"><b>{moneyText(g)}</b></td>
        </tr>
      ))}
    </tbody></table>
  )
}

function ProjectStatsView() {
  const { data: s } = useApi<ProjectStats>('/api/stats/projects')
  if (!s) return null
  const f: ProjectFunnel = s.funnel
  const outcomeRows = PROJECT_OUTCOMES.filter((o) => s.outcomes[o]).map((o) => [o, s.outcomes[o]] as const)
  // The biggest pot of agreed money that adds up (fixed fees and retainers), for the headline.
  const headline = s.won_value.filter((g) => g.pricing !== 'hourly').sort((a, b) => b.total - a.total)[0]
  return (
    <>
      <p className="lede">
        Counts only work you pitched: outreach you sent and proposals you submitted. A reply means any answer
        from them, a no included. Prices are yours, as recorded on each project.
      </p>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
        <Tile value={f.pitched} caption="pitches and proposals sent" />
        <Tile value={f.pitched ? (f.replied / f.pitched) * 100 : null} format={percent} caption={`got a reply (${f.replied})`} />
        <Tile value={f.pitched ? (f.won / f.pitched) * 100 : null} format={percent} caption={`won (${f.won})`} />
        <Tile value={headline ? headline.total : null} format={(n) => money(Math.round(n), headline?.currency)}
              caption={headline ? `agreed on won work${headline.pricing === 'retainer' ? ', a month' : ''}` : 'agreed on won work'} />
      </div>

      <div className="stat-grid">
        <div className="panel">
          <h3>Funnel</h3>
          <div className="sub">Share of pitches that reached each step</div>
          <Steps name="Client work funnel" of="pitches"
                 steps={[['Pitched', f.pitched], ['Got a reply', f.replied], ['Proposal', f.proposals], ['Won', f.won]]} />
        </div>
        <div className="panel">
          <h3>Pitches per week</h3>
          <div className="sub">Last 12 weeks; hover a bar for its count</div>
          <Weeks weeks={s.weeks} noun="pitch" />
        </div>
        <div className="panel">
          <h3>In progress</h3>
          <div className="sub">Projects under way, by stage</div>
          <table className="table">
            <tbody>
              {PROJECT_STAGES.map((st) => (
                <tr key={st}>
                  <td><span className="dot" style={{ background: `var(--st-${st})`, marginRight: 8 }} />{label(st)}</td>
                  <td className="n"><b>{s.pipeline[st]}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h3>Open pipeline</h3>
          <div className="sub">Your price on the work still in play</div>
          <MoneyTable rows={s.open_value} empty="No prices on open work yet." />
        </div>
        <div className="panel">
          <h3>Won</h3>
          <div className="sub">The price agreed on work you won</div>
          <MoneyTable rows={s.won_value} empty="Nothing won yet." />
        </div>
        <div className="panel">
          <h3>How projects ended</h3>
          <div className="sub">Closed projects by outcome</div>
          {outcomeRows.length === 0 ? <p style={{ color: 'var(--ink-3)' }}>None closed yet.</p> : (
            <table className="table"><tbody>
              {outcomeRows.map(([o, n]) => <tr key={o}><td>{label(o)}</td><td className="n"><b>{n}</b></td></tr>)}
            </tbody></table>
          )}
        </div>
        <div className="panel">
          <h3>By where it came from</h3>
          <div className="sub">Which sources lead to replies and wins</div>
          <ProjectBreakdown rows={s.by_source} what="Source" />
        </div>
        <div className="panel">
          <h3>By channel</h3>
          <div className="sub">How the pitch went out</div>
          <ProjectBreakdown rows={s.by_channel} what="Channel" />
        </div>
        <div className="panel">
          <h3>Not pitched yet</h3>
          <div className="sub">Leads waiting at the start</div>
          <table className="table"><tbody>
            {['lead', 'qualified', 'passed'].map((t) => <tr key={t}><td>{label(t)}</td><td className="n"><b>{s.projects_by_status[t] ?? 0}</b></td></tr>)}
          </tbody></table>
        </div>
      </div>
    </>
  )
}

/** Stats for the job search or, with ?of=projects, for client work. */
export function StatsView({ route }: { route: Route }) {
  const projects = route.params.get('of') === 'projects'
  return (
    <div className="stats">
      <div className="stats-head">
        <h2>{projects ? 'How client work is going' : 'How the search is going'}</h2>
        <Thumbed className="views" label="Show stats for">
          <button aria-pressed={!projects} onClick={() => setParams({ of: null })}>Job search</button>
          <button aria-pressed={projects} onClick={() => setParams({ of: 'projects' })}>Client work</button>
        </Thumbed>
      </div>
      {projects ? <ProjectStatsView /> : <JobStatsView />}
    </div>
  )
}

function JobStatsView() {
  const { data: s } = useApi<Stats>('/api/stats')
  if (!s) return null
  const f = s.funnel
  const outcomeRows = Object.entries(s.outcomes).sort((a, b) => b[1] - a[1])
  return (
    <>
      <p className="lede">
        Counts only applications that were sent. A reply means any answer from them, rejections included.
        Cold applications typically get interview invites around 3% of the time, so small numbers early on are normal.
      </p>

      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
        <Tile value={f.applied} caption="applications sent" />
        <Tile value={f.applied ? (f.responded / f.applied) * 100 : null} format={percent} caption={`got a reply (${f.responded})`} />
        <Tile value={f.applied ? (f.interviewed / f.applied) * 100 : null} format={percent} caption={`reached an interview (${f.interviewed})`} />
        <Tile value={s.median_days_to_response}
              format={(n) => `${Number.isInteger(s.median_days_to_response) ? Math.round(n) : n.toFixed(1)} days`}
              caption={s.responses_timed ? `median wait for a first reply (${plural(s.responses_timed, 'reply', 'replies')})` : 'median wait for a first reply'} />
      </div>

      <div className="stat-grid">
        <div className="panel">
          <h3>Funnel</h3>
          <div className="sub">Share of sent applications that reached each step</div>
          <FunnelChart f={f} />
        </div>
        <div className="panel">
          <h3>Applications sent per week</h3>
          <div className="sub">Last 12 weeks; hover a bar for its count</div>
          <Weeks weeks={s.weeks} />
        </div>
        <div className="panel">
          <h3>In progress</h3>
          <div className="sub">Applications not yet closed, by status</div>
          <table className="table">
            <tbody>
              {STAGES.map((st) => (
                <tr key={st}>
                  <td><span className="dot" style={{ background: `var(--st-${st})`, marginRight: 8 }} />{label(st)}</td>
                  <td className="n"><b>{s.pipeline[st]}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h3>How applications ended</h3>
          <div className="sub">Closed applications by outcome</div>
          {outcomeRows.length === 0 ? <p style={{ color: 'var(--ink-3)' }}>None closed yet.</p> : (
            <table className="table"><tbody>
              {outcomeRows.map(([o, n]) => <tr key={o}><td>{label(o)}</td><td className="n"><b>{n}</b></td></tr>)}
            </tbody></table>
          )}
        </div>
        <div className="panel">
          <h3>By where you found the job</h3>
          <div className="sub">Which sources lead to replies</div>
          <Breakdown rows={s.by_source} what="Source" />
        </div>
        <div className="panel">
          <h3>By resume version</h3>
          <div className="sub">Which resume build was sent</div>
          <Breakdown rows={s.by_resume} what="Resume version" />
        </div>
        <div className="panel">
          <h3>By country</h3>
          <div className="sub">Where the job is</div>
          <Breakdown rows={s.by_country} what="Country" />
        </div>
        <div className="panel">
          <h3>Not applied yet</h3>
          <div className="sub">Jobs on the desk you haven't applied to</div>
          <table className="table"><tbody>
            {['new', 'shortlisted', 'passed'].map((t) => <tr key={t}><td>{label(t)}</td><td className="n"><b>{s.jobs_by_status[t] ?? 0}</b></td></tr>)}
          </tbody></table>
        </div>
      </div>
    </>
  )
}
