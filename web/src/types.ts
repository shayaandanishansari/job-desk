export type Stage = 'drafting' | 'applied' | 'screening' | 'interviewing' | 'offer'
export type Outcome = 'accepted' | 'rejected' | 'role_filled' | 'no_response' | 'withdrew' | 'declined'
export type Side = 'me' | 'them'

export interface Facet { value: string; count: number }

export type Status =
  | 'new' | 'shortlisted' | 'passed'
  | Stage
  | Outcome

// Client work: the same shape of journey, with its own stops.
export type ProjectStage = 'drafting' | 'pitched' | 'talking' | 'proposal' | 'negotiating'
export type ProjectOutcome = 'won' | 'lost' | 'no_response' | 'cancelled' | 'turned_down'
export type ProjectStatus = 'lead' | 'qualified' | 'passed' | ProjectStage | ProjectOutcome
export type Kind = 'job' | 'project'

export interface Flag { flag: string; text: string }

/** One record per job: the posting and, once pursued, the application on it. */
export interface JobSummary {
  kind: 'job'
  id: number
  title: string
  company: string | null
  company_id: number | null
  city: string | null
  country: string | null
  work_mode: string
  remote_region: string | null
  employment_type: string
  seniority: string
  experience: string | null
  salary_min: number | null
  salary_max: number | null
  salary_currency: string | null
  salary_period: string | null
  salary_text: string | null
  visa: 'yes' | 'no' | 'unknown'
  relocation: 'yes' | 'no' | 'unknown'
  apply_method: string
  apply_to: string | null
  apply_notes: string | null
  source: string
  source_url: string | null
  source_ref: string | null
  posted_by: string | null
  posted_on: string | null
  found_on: string
  deadline: string | null
  posting_status: 'open' | 'closed'
  priority: number | null
  starred: number
  fit_score: number | null
  fit_notes: string | null
  tags: string[]
  contact_id: number | null
  contact_name: string | null
  contact_email: string | null
  // the pursuit
  status: Status
  stage_reached: Stage | null
  outcome_side: Side | null
  pass_reason: string | null
  channel: string | null
  applied_on: string | null
  resume_version: string | null
  next_action: string | null
  next_action_due: string | null
  last_contact_on: string | null
  first_response_on: string | null
  follow_ups_sent: number
  last_follow_up_on: string | null
  closed_on: string | null
  outcome_notes: string | null
  notes: string | null
  updated_at: string
  // signals for the row tags
  flags: Flag[]
  file_count: number
  thread_count: number
  open_drafts: number
  next_interview: string | null
}

export interface JobList { total: number; jobs: JobSummary[]; facets: Record<string, Facet[]> }

/** One record per piece of client work: from a lead or an Upwork posting to won (or not). */
export interface ProjectSummary {
  kind: 'project'
  id: number
  title: string
  company: string | null
  company_id: number | null
  contact_id: number | null
  contact_name: string | null
  contact_email: string | null
  contact_role: string | null
  source: string
  source_url: string | null
  source_ref: string | null
  pricing: 'fixed' | 'hourly' | 'retainer' | 'unknown'
  budget_text: string | null
  value: number | null
  currency: string | null
  found_on: string
  priority: number | null
  starred: number
  fit_notes: string | null
  tags: string[]
  follow_on_of: number | null
  // the pursuit
  status: ProjectStatus
  stage_reached: ProjectStage | null
  outcome_side: Side | null
  pass_reason: string | null
  channel: string | null
  pitched_on: string | null
  next_action: string | null
  next_action_due: string | null
  last_contact_on: string | null
  first_response_on: string | null
  follow_ups_sent: number
  last_follow_up_on: string | null
  closed_on: string | null
  outcome_notes: string | null
  notes: string | null
  updated_at: string
  flags: Flag[]
  file_count: number
  thread_count: number
  open_drafts: number
}

export interface ProjectList { total: number; projects: ProjectSummary[]; facets: Record<string, Facet[]> }

/** Either kind of record, where lists mix them (Today). */
export type Pursuit = JobSummary | ProjectSummary

type Link<S> = { id: number; title: string; status: S }

export interface EventRow {
  id: number
  at: string
  actor: 'me' | 'claude' | 'system' | 'import'
  entity_type: string
  entity_id: number | null
  job_id: number | null
  project_id: number | null
  application_id: number | null
  action: string
  summary: string
  data: string | null
}

export interface FileRow { id: number; path: string; kind: string; caption: string | null; created_at: string }

export interface Contact {
  id: number
  name: string
  email: string | null
  title: string | null
  company_id: number | null
  company?: string | null
  linkedin: string | null
  phone: string | null
  role: string | null
  notes: string | null
  job_count?: number
  project_count?: number
}

export interface Company {
  id: number
  name: string
  website: string | null
  linkedin: string | null
  city: string | null
  country: string | null
  visa_notes: string | null
  notes: string | null
  job_count?: number
  application_count?: number
  project_count?: number
}

export interface Message {
  id: number
  gmail_message_id: string | null
  sent_at: string
  direction: 'in' | 'out'
  from_addr: string | null
  to_addrs: string | null
  cc_addrs: string | null
  subject: string | null
  body: string | null
  attachments: string[]
  automated: number
}

export interface Thread {
  id: number
  gmail_thread_id: string | null
  job_id: number | null
  project_id: number | null
  subject: string | null
  participants: string | null
  first_at: string | null
  last_at: string | null
  message_count: number
  last_direction: 'in' | 'out' | null
  messages: Message[]
}

export interface Draft {
  id: number
  kind: string
  to_addr: string | null
  cc_addr: string | null
  subject: string | null
  body: string
  status: 'draft' | 'in_gmail' | 'sent' | 'discarded'
  gmail_draft_id: string | null
  attach_resume: number
  updated_at: string
}

export interface Interview {
  id: number
  kind: string
  scheduled_at: string | null
  duration_min: number | null
  with_whom: string | null
  location: string | null
  prep_notes: string | null
  outcome_notes: string | null
  thank_you_sent: number
}

export interface ResumeVersion {
  id: string
  label: string
  path: string | null
  current: boolean
  missing?: boolean
}

export interface JobDetail extends JobSummary {
  description: string | null
  company_info: Company | null
  contact: Contact | null
  files: FileRow[]
  interviews: Interview[]
  threads: Thread[]
  drafts: Draft[]
  timeline: EventRow[]
  resume: ResumeVersion | null
  possible_duplicates: { id: number; title: string; company: string | null; reason: string }[]
  applied_here_before: { id: number; title: string; status: Status; applied_on: string }[]
  company_projects: (Link<ProjectStatus> & { pitched_on: string | null })[]
}

export interface ProjectDetail extends ProjectSummary {
  description: string | null
  company_info: Company | null
  contact: Contact | null
  files: FileRow[]
  threads: Thread[]
  drafts: Draft[]
  timeline: EventRow[]
  possible_duplicates: { id: number; title: string; company: string | null; reason: string }[]
  follow_on_from: Link<ProjectStatus> | null
  follow_ons: Link<ProjectStatus>[]
  company_jobs: (Link<Status> & { applied_on: string | null })[]
  company_projects: (Link<ProjectStatus> & { pitched_on: string | null })[]
}

export interface TodayData {
  date: string
  due: Pursuit[]
  upcoming: Pursuit[]
  attention: Pursuit[]
  interviews: (Interview & { title: string; company: string | null; job_id: number })[]
  drafts: { id: number; subject: string | null; status: string; kind: string; to_addr: string | null;
            job_id: number | null; project_id: number | null; title: string; company: string | null }[]
  to_triage: { total: number; jobs: JobSummary[] }
  leads: { total: number; projects: ProjectSummary[] }
  closing_soon: JobSummary[]
  week: { start: string; sent: number; pitched: number; replies: number; open: number }
}

export interface Funnel { applied: number; responded: number; interviewed: number; offers: number }

export interface Stats {
  funnel: Funnel
  by_source: (Funnel & { value: string })[]
  by_resume: (Funnel & { value: string })[]
  by_country: (Funnel & { value: string })[]
  by_channel: (Funnel & { value: string })[]
  median_days_to_response: number | null
  responses_timed: number
  weeks: { week: string; sent: number }[]
  outcomes: Record<string, number>
  pipeline: Record<Stage, number>
  jobs_by_status: Record<string, number>
}

export interface ProjectFunnel { pitched: number; replied: number; proposals: number; won: number }

/** Prices grouped by currency and pricing. Fixed fees and retainers add up; hourly rates average. */
export interface Money { currency: string | null; pricing: string; count: number; total: number; average: number }

export interface ProjectStats {
  funnel: ProjectFunnel
  by_source: (ProjectFunnel & { value: string })[]
  by_channel: (ProjectFunnel & { value: string })[]
  median_days_to_reply: number | null
  replies_timed: number
  weeks: { week: string; sent: number }[]
  outcomes: Record<string, number>
  pipeline: Record<ProjectStage, number>
  projects_by_status: Record<string, number>
  open_value: Money[]
  won_value: Money[]
}

export interface Meta {
  me: { name: string | null; gmail: string | null }
  vocab: Record<string, string[]>
  labels: Record<string, string>
  outcome_side: Record<string, Side>
  rules: { follow_up_after_business_days: number; max_follow_ups: number; no_response_after_days: number }
  resumes: ResumeVersion[]
  today: string
}
