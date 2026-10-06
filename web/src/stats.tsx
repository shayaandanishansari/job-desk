import { useState, type CSSProperties } from 'react'
import { useApi } from './api'
import { Num, STAGES } from './components'
import { fmtDate, label, plural, resumeLabel } from './format'
import type { Funnel, Stats } from './types'

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

/** Applied -> responded -> interviewed -> offers. One series, one hue; each bar is labelled. */
function FunnelChart({ f }: { f: Funnel }) {
  const steps: [string, number][] = [['Applied', f.applied], ['Got a reply', f.responded], ['Interviewed', f.interviewed], ['Offers', f.offers]]
  const max = Math.max(f.applied, 1)
  return (
    <div role="table" aria-label="Application funnel">
      {steps.map(([name, n], i) => (
        <div className="funnel-row" role="row" key={name} title={`${name}: ${n} (${pct(n, f.applied)} of applications)`}>
          <span role="cell">{name}</span>
          <span className="bar" role="cell"><i style={{ width: `${(n / max) * 100}%`, background: 'var(--accent)', borderRadius: '0 4px 4px 0', '--i': i } as CSSProperties} /></span>
          <span className="num" role="cell">{n}<small>{name === 'Applied' ? '' : pct(n, f.applied)}</small></span>
        </div>
      ))}
    </div>
  )
}

function Weeks({ weeks }: { weeks: Stats['weeks'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(...weeks.map((w) => w.sent), 1)
  const peak = weeks.reduce((best, w, i) => (w.sent > weeks[best].sent ? i : best), 0)
  return (
    <div style={{ position: 'relative' }}>
      <div className="weeks" onMouseLeave={() => setHover(null)}>
        {weeks.map((w, i) => {
          const showValue = w.sent > 0 && (i === peak || i === weeks.length - 1 || i === hover)
          return (
            <div className="wk" key={w.week} onMouseEnter={() => setHover(i)} title={`Week of ${fmtDate(w.week)}: ${plural(w.sent, 'application')}`}>
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

export function StatsView() {
  const { data: s } = useApi<Stats>('/api/stats')
  if (!s) return <div className="stats" />
  const f = s.funnel
  const outcomeRows = Object.entries(s.outcomes).sort((a, b) => b[1] - a[1])
  return (
    <div className="stats">
      <h2>How the search is going</h2>
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
    </div>
  )
}
