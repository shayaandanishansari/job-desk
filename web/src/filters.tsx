import { ChevronDown, ChevronsDownUp, ChevronsUpDown, X } from 'lucide-react'
import { useEffect, useState, type CSSProperties } from 'react'
import { setParams } from './api'
import { Num, statusColor, useFlip } from './components'
import { label, plural } from './format'
import type { Facet, JobList, Side, Status } from './types'

// The filter column: one accordion section per facet, drawn as a transit line with each value
// a stop on it. Chosen values are filled stops; a closed section lists its choices as chips.

const STATUS_ORDER = ['new', 'shortlisted', 'drafting', 'applied', 'screening', 'interviewing', 'offer',
  'accepted', 'rejected', 'role_filled', 'no_response', 'withdrew', 'declined', 'passed']

export const FACETS: [string, string][] = [
  ['status', 'Status'], ['country', 'Country'], ['city', 'City'], ['work_mode', 'Work mode'],
  ['visa', 'Visa sponsorship'], ['priority', 'Priority'], ['source', 'Found on'],
  ['seniority', 'Seniority'], ['employment_type', 'Type'], ['posting_status', 'Posting'],
]

// Facets with a natural order list in that order; the rest list by count.
const VALUE_ORDER: Record<string, string[]> = {
  status: STATUS_ORDER,
  priority: ['1', '2', '3', '4', 'none'],
  visa: ['yes', 'no', 'unknown'],
  posting_status: ['open', 'closed'],
}

const MY_ENDINGS = ['accepted', 'withdrew', 'declined']
const OPEN_KEY = 'jobdesk.filters.open'
const SHOW = 6 // values shown before "Show more"

function facetLabel(facet: string, value: string) {
  if (facet === 'priority') return value === 'none' ? 'No priority' : ['', '1, send first', '2, this week', '3, if there is time', '4, skip or last'][Number(value)] ?? value
  if (facet === 'visa') return { yes: 'Sponsors', no: "Doesn't sponsor", unknown: 'Not stated' }[value] ?? value
  if (facet === 'country' || facet === 'city') return value === 'none' ? 'Not given' : value
  return label(value)
}

/** The colour a chosen stop fills with: the status's own line colour, or what the value means. */
function stopColor(facet: string, value: string) {
  if (facet === 'status') {
    const side: Side = MY_ENDINGS.includes(value) ? 'me' : 'them'
    return statusColor({ status: value as Status, outcome_side: side })
  }
  if (facet === 'visa') return { yes: 'var(--ok)', no: 'var(--late)' }[value] ?? 'var(--ink-3)'
  if (facet === 'priority') return value === 'none' ? 'var(--ink-3)' : 'var(--ink)'
  return 'var(--accent)'
}

/** How many filters are on, counting the Starred toggle. */
export function activeFilters(p: URLSearchParams) {
  return FACETS.reduce((n, [f]) => n + p.getAll(f).length, 0) + (p.has('starred') ? 1 : 0)
}

function loadOpen(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(OPEN_KEY) ?? 'null')
    if (Array.isArray(v)) return v
  } catch { /* storage blocked or corrupt: fall back to the default */ }
  return ['status']
}

function pick(p: URLSearchParams, facet: string, value: string) {
  const cur = p.getAll(facet)
  setParams({ [facet]: cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value] })
}

export function Filters({ data, params, onDone }: { data: JobList | null; params: URLSearchParams; onDone?: () => void }) {
  const [open, setOpen] = useState<string[]>(loadOpen)
  useEffect(() => {
    try { localStorage.setItem(OPEN_KEY, JSON.stringify(open)) } catch { /* private window */ }
  }, [open])

  const groups = FACETS.flatMap(([facet, title]) => {
    const chosen = params.getAll(facet)
    const options: Facet[] = [...(data?.facets[facet] ?? [])]
    chosen.forEach((c) => { if (!options.some((o) => o.value === c)) options.push({ value: c, count: 0 }) })
    const order = VALUE_ORDER[facet]
    if (order) options.sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value))
    if (options.length <= 1 && !chosen.length) return []
    return [{ facet, title, options, chosen }]
  })
  const active = activeFilters(params)
  const allOpen = groups.length > 0 && groups.every((g) => open.includes(g.facet))

  return (
    <div className="filters">
      <div className="filters-head">
        <h2>Filters</h2>
        {active > 0 && (
          <button className="filters-clear" onClick={() => setParams({ ...Object.fromEntries(FACETS.map(([f]) => [f, null])), starred: null })}>
            Clear {plural(active, 'filter')}
          </button>
        )}
        <button className="icon-btn" onClick={() => setOpen(allOpen ? [] : groups.map((g) => g.facet))}
                title={allOpen ? 'Close every section' : 'Open every section'} aria-label={allOpen ? 'Close every section' : 'Open every section'}>
          {allOpen ? <ChevronsDownUp size={15} /> : <ChevronsUpDown size={15} />}
        </button>
      </div>
      {!data && Array.from({ length: 6 }, (_, i) => <div key={i} className="acc-skel skel-wrap"><i className="skel" style={{ width: `${40 + (i % 3) * 15}%`, height: 12 }} /></div>)}
      {data && groups.map((g) => (
        <FacetSection key={g.facet} {...g} params={params} open={open.includes(g.facet)}
                      onToggle={() => setOpen((o) => (o.includes(g.facet) ? o.filter((x) => x !== g.facet) : [...o, g.facet]))} />
      ))}
      {onDone && <button className="btn primary filters-done" onClick={onDone}>Show {data?.total ?? ''} jobs</button>}
    </div>
  )
}

function FacetSection({ facet, title, options, chosen, params, open, onToggle }: {
  facet: string; title: string; options: Facet[]; chosen: string[]; params: URLSearchParams; open: boolean; onToggle: () => void
}) {
  const [more, setMore] = useState(false)
  const stops = useFlip<HTMLDivElement>()
  const max = Math.max(1, ...options.map((o) => o.count))
  // Long lists show the first few and anything chosen; "Show 1 more" would be silly, so 7 show whole.
  const visible = more || options.length <= SHOW + 1 ? options : options.filter((o, i) => i < SHOW || chosen.includes(o.value))
  const rest = options.length - visible.length
  const id = `facet-${facet}`

  return (
    <section className={`acc${open ? ' open' : ''}${chosen.length ? ' on' : ''}`}>
      <h3>
        <button className="acc-head" aria-expanded={open} aria-controls={id} onClick={onToggle}>
          <span className="acc-title">{title}</span>
          {chosen.length > 0 && <span className="acc-badge" key={chosen.length}>{chosen.length}</span>}
          <ChevronDown className="acc-chev" size={15} aria-hidden="true" />
        </button>
      </h3>

      {/* Closed with choices: the choices as chips, each removable without opening the section. */}
      <div className="acc-chips" inert={open || !chosen.length}>
        <div>
          <div className="chips">
            {chosen.map((v) => (
              <span key={v} className="fchip" style={{ '--c': stopColor(facet, v) } as CSSProperties}>
                <i />{facetLabel(facet, v)}
                <button onClick={() => pick(params, facet, v)} aria-label={`Remove ${facetLabel(facet, v)}`}><X size={12} /></button>
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="acc-body" id={id} role="region" aria-label={title} inert={!open}>
        <div className="acc-inner">
          <div className="stops" ref={stops}>
            {visible.map((o, i) => (
              <button key={o.value} data-flip={o.value} className={`facet-opt${o.count ? '' : ' zero'}`}
                      aria-pressed={chosen.includes(o.value)} onClick={() => pick(params, facet, o.value)}
                      style={{ '--i': i, '--w': o.count / max, '--c': stopColor(facet, o.value) } as CSSProperties}>
                <span className="fstop" aria-hidden="true" />
                <span className="facet-name">{facetLabel(facet, o.value)}</span>
                <span className="n"><Num value={o.count} /></span>
              </button>
            ))}
          </div>
          {(more || rest > 0) && (
            <button className="facet-more" onClick={() => setMore((m) => !m)}>
              {more ? 'Show fewer' : `Show ${rest} more`}
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
