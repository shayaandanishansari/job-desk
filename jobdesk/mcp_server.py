"""MCP server: the same operations as the dashboard, for Claude Code or any
MCP client. Runs over stdio (`python -m jobdesk mcp`); writes are logged as
actor 'claude', and open dashboards pick them up within a second."""

from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import paths, settings
from .core import CompanyIn, ContactIn, Desk, DraftIn, InterviewIn, JobIn, MessageIn, ProjectIn
from .vocab import (FILE_ENTITIES, FILE_KINDS, INTERVIEW_KINDS, PASS_REASONS, PROJECT_PASS_REASONS,
                    PROJECT_STATUSES, STATUSES)


def _instructions():
    me = settings.load(paths.SETTINGS_DIR)
    who = me["name"] or "the user"
    guide = (f"Application emails follow {me['email_guide']}: read it before drafting one.\n"
             if me["email_guide"] and me["email_guide"].is_file() else "")
    return f"""Job Desk holds every job {who} is considering or has applied to. One record per job; its
status says where things stand: new -> shortlisted (or passed) -> drafting -> applied -> screening ->
interviewing -> offer, then closed as accepted, rejected, role_filled, no_response, withdrew or declined.
Each job also carries its contact, interviews, email threads copied from Gmail, email drafts,
screenshots and a timeline of every change.

It also holds client work (freelance): one record per project, from a lead {who} found or an Upwork
job to bid on, through lead -> qualified (or passed) -> drafting -> pitched -> talking -> proposal ->
negotiating, closed as won, lost, no_response, cancelled or turned_down. An Upwork proposal is a pitch.
More work from the same client is a new project with follow_on_of pointing at the earlier one. Use the
*_project tools for these. Companies, contacts (with a role), email threads, drafts, files and notes
are shared: one company or person can have both jobs and projects.

Start with `overview`. Use `search_jobs` before `add_job` and `search_projects` before
`add_project` (both refuse likely duplicates unless force=True). Change status only with
`set_status` / `set_project_status`, which record the dates and next action.
Record what actually happened; never invent facts, dates or numbers.
{guide}Emails are sent by {who} from Gmail: save the draft here with `save_email_draft`, create it in
Gmail with the Gmail connector if you have one, then mark the draft 'in_gmail'. Once it's sent, set
the job to 'applied' and sync the thread with `record_email_thread`.
Statuses never move on their own; follow-up dates are suggested by the rules and can be overridden."""


mcp = FastMCP("jobdesk", instructions=_instructions())


def _call(fn, *args, **kwargs):
    with Desk(actor="claude") as d:
        return getattr(d, fn)(*args, **kwargs)


def _compact(j):
    where = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
    return {
        "id": j["id"], "title": j["title"], "company": j["company"], "where": where or None,
        "status": j["status"], "starred": bool(j["starred"]), "work_mode": j["work_mode"], "visa": j["visa"], "priority": j["priority"],
        "applied_on": j["applied_on"], "next_action": j["next_action"], "next_action_due": j["next_action_due"],
        "follow_ups_sent": j["follow_ups_sent"], "flags": [f["flag"] for f in j["flags"]],
        "source": j["source"], "posted_on": j["posted_on"], "found_on": j["found_on"], "deadline": j["deadline"],
    }


# ------------------------------------------------------------------ orientation

@mcp.tool()
def overview() -> dict:
    """Counts by status for jobs and projects, both funnels, what's due, what needs attention, jobs
    closing soon, drafts waiting and new leads. Call this first."""
    return _call("overview")


@mcp.tool()
def today() -> dict:
    """The dashboard's Today view in full: due and upcoming next actions (jobs and projects mixed; each
    row has `kind`), attention flags, interviews in the next two weeks, drafts waiting, jobs closing
    soon, new jobs, new leads, this week's numbers."""
    return _call("today")


@mcp.tool()
def stats() -> dict:
    """Funnel (applied -> responded -> interviewed -> offers) overall and by source, resume version,
    country and channel; median days to first response; applications per week; counts by status."""
    return _call("stats")


@mcp.tool()
def project_stats() -> dict:
    """Client work: funnel (pitched -> replied -> proposal -> won) overall and by source and channel,
    median days to a first reply, pitches per week, projects by status, and the money in the open
    pipeline and won (grouped by currency and pricing; hourly rates are averaged, not summed)."""
    return _call("project_stats")


# ------------------------------------------------------------------ jobs

@mcp.tool()
def search_jobs(query: str | None = None, status: list[str] | None = None, country: list[str] | None = None,
                city: list[str] | None = None, work_mode: list[str] | None = None, visa: list[str] | None = None,
                source: list[str] | None = None, priority: list[int] | None = None, starred: bool | None = None,
                sort: Literal["priority", "newest", "posted", "company", "due", "activity"] = "priority",
                limit: int = 50) -> dict:
    """Search all jobs. `query` matches every word anywhere (title, company, location, posting,
    fit notes, notes, contact). Each filter takes a list of values; 'none' matches an empty field.
    status values: new, shortlisted, drafting, applied, screening, interviewing, offer, accepted,
    rejected, role_filled, no_response, withdrew, declined, passed. starred=true shows only the jobs
    the user starred. The default sort puts starred jobs first."""
    filters = {k: v for k, v in dict(status=status, country=country, city=city, work_mode=work_mode, visa=visa,
                                     source=source, priority=priority).items() if v}
    if starred is not None:
        filters["starred"] = [1 if starred else 0]
    res = _call("search_jobs", q=query, filters=filters, sort=sort, limit=limit)
    return {"total": res["total"], "jobs": [_compact(j) for j in res["jobs"]]}


@mcp.tool()
def get_job(job_id: int) -> dict:
    """Everything about one job: the posting, fit notes, status and dates, contact, interviews,
    email threads with messages, drafts, files, timeline, attention flags, resume version sent,
    possible duplicates and other applications to the same company."""
    return _call("get_job", job_id)


@mcp.tool()
def add_job(job: JobIn, status: Literal[STATUSES] = "new", status_on: date | None = None,
            force: bool = False) -> dict:
    """Store a job (from a screenshot, pasted text or a link). Fill in what the post says: title,
    company, city/country, work_mode, employment_type, seniority, experience, salary, visa and
    relocation (yes/no/unknown; leave unknown unless the post says), description (the post's text
    as Markdown, original wording), apply_method + apply_to + apply_notes, contact (the person to
    email), source + source_url, posted_on (work out from relative labels like '5d'), and your
    fit_notes. For a job already applied to, pass status='applied' and status_on (the date sent).
    Refuses a likely duplicate unless force=True."""
    return _call("add_job", force=force, status=status, status_on=status_on, **job.given())


@mcp.tool()
def update_job(job_id: int, changes: JobIn) -> dict:
    """Change any job fields except status (use set_status): posting details, fit notes, priority,
    contact, channel, next_action / next_action_due, notes, resume_version, dates. Only the fields
    you pass are touched; pass null to clear one."""
    return _call("update_job", job_id, **changes.given())


@mcp.tool()
def set_status(job_id: int, status: Literal[STATUSES], on: date | None = None, note: str | None = None,
               pass_reason: Literal[PASS_REASONS] | None = None, resume_version: str | None = None,
               next_action: str | None = None, next_action_due: date | None = None,
               outcome_notes: str | None = None) -> dict:
    """Move a job to a status, dated `on` (default today). Applied or later the first time records the
    applied date, channel and resume version (the default resume's current build, only if sent today);
    screening or later records the first reply; in progress recomputes the next action unless you pass
    one; closing records the date. Their side: rejected, role_filled, no_response. The user's side:
    accepted, withdrew, declined. 'passed' takes a pass_reason."""
    return _call("set_status", job_id, status, on=on, note=note, pass_reason=pass_reason,
                 resume_version=resume_version, next_action=next_action, next_action_due=next_action_due,
                 outcome_notes=outcome_notes)


@mcp.tool()
def star_job(job_id: int, starred: bool = True) -> dict:
    """Star or unstar a job. Stars are the user's own marker for jobs they care about; star a job
    only when they ask you to."""
    return _call("star", job_id, starred)


@mcp.tool()
def log_follow_up(job_id: int, on: date | None = None, note: str | None = None) -> dict:
    """Record that a follow-up was sent. Updates the count and the next suggested action."""
    return _call("log_follow_up", job_id, on=on, note=note)


@mcp.tool()
def add_interview(job_id: int, kind: Literal[INTERVIEW_KINDS], scheduled_at: str | None = None,
                  on: date | None = None, details: InterviewIn | None = None) -> dict:
    """Add an interview (scheduled_at as 'YYYY-MM-DDTHH:MM', local time). Moves the job to screening
    (kind 'screen') or interviewing if it's behind, dated `on` (when they invited you; default today),
    and sets prep / thank-you actions."""
    extra = details.given() if details else {}
    extra.pop("kind", None)
    extra.pop("scheduled_at", None)
    return _call("add_interview", job_id, kind=kind, scheduled_at=scheduled_at, on=on, **extra)


@mcp.tool()
def update_interview(interview_id: int, changes: InterviewIn) -> dict:
    """Change an interview, e.g. thank_you_sent=true or outcome_notes."""
    return _call("update_interview", interview_id, **changes.given())


@mcp.tool()
def add_note(entity_type: Literal["job", "company", "project"], entity_id: int, text: str) -> dict:
    """Add a note to a job's, project's or company's timeline."""
    return _call("add_note", entity_type, entity_id, text)


@mcp.tool()
def delete_job(job_id: int) -> dict:
    """Permanently delete a job and everything on it. Only when the user asks for it."""
    return _call("delete_job", job_id)


# ------------------------------------------------------------------ projects (client work)

def _compact_project(p):
    return {
        "id": p["id"], "title": p["title"], "company": p["company"], "status": p["status"],
        "starred": bool(p["starred"]), "priority": p["priority"], "source": p["source"], "channel": p["channel"],
        "pricing": p["pricing"], "value": p["value"], "currency": p["currency"], "budget_text": p["budget_text"],
        "pitched_on": p["pitched_on"], "next_action": p["next_action"], "next_action_due": p["next_action_due"],
        "follow_ups_sent": p["follow_ups_sent"], "flags": [f["flag"] for f in p["flags"]], "found_on": p["found_on"],
        "follow_on_of": p["follow_on_of"],
    }


@mcp.tool()
def search_projects(query: str | None = None, status: list[str] | None = None, source: list[str] | None = None,
                    channel: list[str] | None = None, pricing: list[str] | None = None,
                    priority: list[int] | None = None, starred: bool | None = None,
                    sort: Literal["priority", "newest", "company", "due", "activity", "value"] = "priority",
                    limit: int = 50) -> dict:
    """Search all projects (client work). `query` matches every word anywhere (title, company, brief,
    fit notes, budget, notes, contact). Each filter takes a list of values; 'none' matches an empty
    field. status values: lead, qualified, drafting, pitched, talking, proposal, negotiating, won, lost,
    no_response, cancelled, turned_down, passed. source: upwork, outreach, inbound, referral, linkedin, other."""
    filters = {k: v for k, v in dict(status=status, source=source, channel=channel, pricing=pricing,
                                     priority=priority).items() if v}
    if starred is not None:
        filters["starred"] = [1 if starred else 0]
    res = _call("search_projects", q=query, filters=filters, sort=sort, limit=limit)
    return {"total": res["total"], "projects": [_compact_project(p) for p in res["projects"]]}


@mcp.tool()
def get_project(project_id: int) -> dict:
    """Everything about one project: the brief, fit notes, price, status and dates, contact, email
    threads with messages, drafts, files, timeline, attention flags, possible duplicates, the project it
    follows on from and the ones that follow on from it, and the company's jobs and other projects."""
    return _call("get_project", project_id)


@mcp.tool()
def add_project(project: ProjectIn, status: Literal[PROJECT_STATUSES] = "lead", status_on: date | None = None,
                force: bool = False) -> dict:
    """Store a project: a lead to pitch, an Upwork job to bid on, or work someone offered. Fill in what
    you know: title (what the work is, e.g. 'Voice receptionist for a dental clinic'), company, contact
    (with role: recruiter, hiring_manager, founder, decision_maker, client, referrer, other), description
    (the posting or brief as Markdown, original wording), source (upwork, outreach, inbound, referral,
    linkedin, other) + source_url + source_ref (e.g. the Upwork job id), budget_text (their budget as
    stated), pricing (fixed, hourly, retainer) + value + currency for your price, channel, and your
    fit_notes. For more work from an earlier project, set follow_on_of. For a pitch already sent, pass
    status='pitched' and status_on. Refuses a likely duplicate unless force=True."""
    return _call("add_project", force=force, status=status, status_on=status_on, **project.given())


@mcp.tool()
def update_project(project_id: int, changes: ProjectIn) -> dict:
    """Change any project fields except status (use set_project_status): brief, price, contact,
    channel, next_action / next_action_due, notes, follow_on_of, dates. Only the fields you pass are
    touched; pass null to clear one."""
    return _call("update_project", project_id, **changes.given())


@mcp.tool()
def set_project_status(project_id: int, status: Literal[PROJECT_STATUSES], on: date | None = None,
                       note: str | None = None, pass_reason: Literal[PROJECT_PASS_REASONS] | None = None,
                       value: float | None = None, next_action: str | None = None,
                       next_action_due: date | None = None, outcome_notes: str | None = None) -> dict:
    """Move a project to a status, dated `on` (default today). Pitched or later the first time records
    the pitch date and channel; talking or later records the first reply; in progress recomputes the
    next action (pitch follow-ups after 3 and then 5 business days; none on Upwork, where only the
    client can write first) unless you pass one; closing records the date. 'won' can take `value`, the
    agreed price. Their side: lost, no_response, cancelled. The user's side: won, turned_down.
    'passed' takes a pass_reason."""
    return _call("set_project_status", project_id, status, on=on, note=note, pass_reason=pass_reason, value=value,
                 next_action=next_action, next_action_due=next_action_due, outcome_notes=outcome_notes)


@mcp.tool()
def log_project_follow_up(project_id: int, on: date | None = None, note: str | None = None) -> dict:
    """Record that a follow-up on a pitch or proposal was sent. Updates the count and the next action."""
    return _call("log_project_follow_up", project_id, on=on, note=note)


@mcp.tool()
def star_project(project_id: int, starred: bool = True) -> dict:
    """Star or unstar a project. Stars are the user's own marker; star one only when they ask you to."""
    return _call("star_project", project_id, starred)


@mcp.tool()
def delete_project(project_id: int) -> dict:
    """Permanently delete a project and everything on it. Only when the user asks for it."""
    return _call("delete_project", project_id)


# ------------------------------------------------------------------ email

@mcp.tool()
def save_email_draft(body: str, job_id: int | None = None, project_id: int | None = None,
                     subject: str | None = None, to_addr: str | None = None, cc_addr: str | None = None,
                     kind: Literal["application", "pitch", "follow_up", "thank_you", "other"] | None = None,
                     status: Literal["draft", "in_gmail", "sent", "discarded"] = "draft",
                     gmail_draft_id: str | None = None) -> dict:
    """Save an email draft (body in Markdown) on a job or a project (pass one of job_id / project_id)
    so it shows on the dashboard. kind defaults to 'application' on a job (resume attached) and
    'pitch' on a project (no resume)."""
    return _call("save_draft", job_id, body, subject=subject, to_addr=to_addr, cc_addr=cc_addr,
                 kind=kind, status=status, gmail_draft_id=gmail_draft_id, project_id=project_id)


@mcp.tool()
def update_email_draft(draft_id: int, changes: DraftIn) -> dict:
    """Edit a draft or change its status (draft, in_gmail, sent, discarded) and gmail_draft_id."""
    return _call("update_draft", draft_id, **changes.given())


@mcp.tool()
def record_email_thread(messages: list[MessageIn], gmail_thread_id: str | None = None,
                        subject: str | None = None, job_id: int | None = None,
                        project_id: int | None = None) -> dict:
    """Save a Gmail thread (copied with the Gmail connector) and optionally link it to a job or a project.
    Pass each message's gmail_message_id, sent_at (ISO), from_addr, to_addrs, subject and the body
    as plain text without quoted earlier messages. Set automated=true on confirmations and
    notifications ("application received", LinkedIn updates) so they don't count as a reply.
    Re-syncing a thread only adds new messages. Replies from a person set the job's (or project's)
    first-response and last-contact dates; the status never moves on its own."""
    return _call("record_thread", messages, gmail_thread_id=gmail_thread_id, subject=subject, job_id=job_id,
                 project_id=project_id)


@mcp.tool()
def link_email_thread(thread_id: int, job_id: int | None = None, project_id: int | None = None) -> dict:
    """Attach a saved email thread to a job or a project (one of the two)."""
    return _call("link_thread", thread_id, job_id=job_id, project_id=project_id)


@mcp.tool()
def list_email_threads(unlinked_only: bool = False) -> list:
    """Saved email threads, newest first, with the job or project each belongs to."""
    return _call("list_threads", unlinked_only=unlinked_only)


# ------------------------------------------------------------------ people, files, resume

@mcp.tool()
def upsert_company(name: str, details: CompanyIn | None = None) -> dict:
    """Create a company or update its details (website, linkedin, city, country, visa_notes, notes)."""
    extra = details.given() if details else {}
    extra.pop("name", None)
    return _call("upsert_company", name, **extra)


@mcp.tool()
def upsert_contact(contact: ContactIn) -> dict:
    """Create a contact or update one (matched on email, else name and company). `role` says who
    they are to the user: recruiter, hiring_manager, founder, decision_maker, client, referrer, other."""
    return _call("upsert_contact", **contact.given())


@mcp.tool()
def list_companies() -> list:
    """All companies with job, application and project counts."""
    return _call("list_companies")


@mcp.tool()
def list_contacts() -> list:
    """All contacts with their company, role, and how many jobs and projects they're on."""
    return _call("list_contacts")


@mcp.tool()
def attach_file(entity_type: Literal[FILE_ENTITIES], entity_id: int, file_path: str,
                kind: Literal[FILE_KINDS] = "screenshot", caption: str | None = None) -> dict:
    """Copy a local file (e.g. a screenshot of the job post or a client's brief) into the desk and attach
    it to a job, project or company."""
    return _call("attach_file", entity_type, entity_id, file_path, kind=kind, caption=caption)


@mcp.tool()
def resume_versions() -> list:
    """The resumes named in settings.json (current builds and old versions). A job's
    resume_version is one of these ids, e.g. '2026-10-06 general'."""
    return _call("resume_versions")


@mcp.tool()
def query_db(sql: str) -> dict:
    """Read-only SQL against the database, for questions the other tools don't answer.
    Tables: jobs, projects, companies, contacts, interviews, email_threads, email_messages, email_drafts,
    files, events. Returns at most 200 rows."""
    return _call("query", sql)


def main():
    mcp.run()
