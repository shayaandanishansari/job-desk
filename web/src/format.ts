let LABELS: Record<string, string> = {}

export function setLabels(labels: Record<string, string>) {
  LABELS = labels
}

export function label(value: string | null | undefined): string {
  if (value == null || value === '') return ''
  if (value === 'none') return 'Not set'
  return LABELS[value] ?? value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ')
}

export function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function parseDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function daysFromToday(iso: string): number {
  return Math.round((parseDay(iso).getTime() - parseDay(todayIso()).getTime()) / 86400000)
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = parseDay(iso)
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${sameYear ? '' : ` ${d.getFullYear()}`}`
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const time = iso.length > 10 ? iso.slice(11, 16) : ''
  return `${fmtDate(iso)}${time && time !== '00:00' ? `, ${time}` : ''}`
}

/** "3 days overdue", "today", "tomorrow", "in 4 days", or a date further out. */
export function due(iso: string | null | undefined): string {
  if (!iso) return ''
  const n = daysFromToday(iso)
  if (n < -1) return `${-n} days overdue`
  if (n === -1) return '1 day overdue'
  if (n === 0) return 'today'
  if (n === 1) return 'tomorrow'
  if (n < 7) return `in ${n} days`
  return fmtDate(iso)
}

export function dueTone(iso: string | null | undefined): 'late' | 'now' | 'soon' | 'later' | '' {
  if (!iso) return ''
  const n = daysFromToday(iso)
  if (n < 0) return 'late'
  if (n === 0) return 'now'
  if (n <= 3) return 'soon'
  return 'later'
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return ''
  const n = -daysFromToday(iso)
  if (n <= 0) return 'today'
  if (n === 1) return 'yesterday'
  return `${n} days ago`
}

/** "2026-09-18 before-ats-fixes" -> "18 Sep build, before ATS fixes". */
export function resumeLabel(id: string | null | undefined): string {
  if (!id || id === 'unknown') return 'Not recorded'
  const m = id.match(/^(\d{4}-\d{2}-\d{2}) (.+)$/)
  if (!m) return id
  const variant = m[2].replace(/-/g, ' ').replace(/\b(ats|ceo|cto|cv|ai|ml|ui|ux)\b/gi, (w) => w.toUpperCase())
  return `${fmtDate(m[1])} build, ${variant}`
}

export function place(j: { city: string | null; country: string | null; work_mode?: string; remote_region?: string | null }) {
  const where = [j.city, j.country].filter(Boolean).join(', ')
  if (j.work_mode === 'remote') return where ? `Remote, ${where}` : j.remote_region ? `Remote (${j.remote_region})` : 'Remote'
  return where || 'Location not given'
}

export function actorName(actor: string): string {
  return { me: 'You', claude: 'Claude', import: 'Import', system: 'System' }[actor] ?? actor
}

/** "$1,500", "PKR 50,000": an amount in its currency, or a plain number when there's none. */
export function money(value: number, currency: string | null | undefined): string {
  if (currency) {
    try {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: value % 1 ? 2 : 0 }).format(value)
    } catch { /* not an ISO code: show it as written */ }
  }
  return `${currency ? `${currency} ` : ''}${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

/** A project's price as a card shows it: "$1,500", "$30/hr", "$500/mo". */
export function price(p: { pricing: string; value: number | null; currency: string | null }): string | null {
  if (p.value == null) return null
  const m = money(p.value, p.currency)
  return p.pricing === 'hourly' ? `${m}/hr` : p.pricing === 'retainer' ? `${m}/mo` : m
}

export function plural(n: number, word: string, many?: string) {
  return `${n} ${n === 1 ? word : many ?? word + 's'}`
}
