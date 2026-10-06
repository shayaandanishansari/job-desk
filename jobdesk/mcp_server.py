"""MCP server: the same operations as the dashboard, for Claude Code or any
MCP client. Runs over stdio (`python -m jobdesk mcp`); writes are logged as
actor 'claude', and open dashboards pick them up within a second."""

from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP

from . import paths, settings
from .core import CompanyIn, ContactIn, Desk, DraftIn, InterviewIn, JobIn, MessageIn
from .vocab import FILE_ENTITIES, FILE_KINDS, INTERVIEW_KINDS, PASS_REASONS, STATUSES


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

Start with `overview`. Use `search_jobs` before `add_job` (add_job also refuses likely duplicates
unless force=True). Change status only with `set_status`, which records the dates and next action.
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
    """Counts by status, the funnel, what's due, what needs attention, jobs closing soon and
    drafts waiting. Call this first."""
    return _call("overview")


@mcp.tool()
def today() -> dict:
    """The dashboard's Today view in full: due and upcoming next actions, attention flags,
    interviews in the next two weeks, drafts waiting, jobs closing soon, new jobs, this week's numbers."""
    return _call("today")


@mcp.tool()
def stats() -> dict:
    """Funnel (applied -> responded -> interviewed -> offers) overall and by source, resume version,
    country and channel; median days to first response; applications per week; counts by status."""
    return _call("stats")


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
def add_note(entity_type: Literal["job", "company"], entity_id: int, text: str) -> dict:
    """Add a note to a job's or company's timeline."""
    return _call("add_note", entity_type, entity_id, text)


@mcp.tool()
def delete_job(job_id: int) -> dict:
    """Permanently delete a job and everything on it. Only when the user asks for it."""
    return _call("delete_job", job_id)


# ------------------------------------------------------------------ email

@mcp.tool()
def save_email_draft(job_id: int, body: str, subject: str | None = None, to_addr: str | None = None,
                     cc_addr: str | None = None,
                     kind: Literal["application", "follow_up", "thank_you", "other"] = "application",
                     status: Literal["draft", "in_gmail", "sent", "discarded"] = "draft",
                     gmail_draft_id: str | None = None) -> dict:
    """Save an email draft (body in Markdown) on a job so it shows on the dashboard."""
    return _call("save_draft", job_id, body, subject=subject, to_addr=to_addr, cc_addr=cc_addr,
                 kind=kind, status=status, gmail_draft_id=gmail_draft_id)


@mcp.tool()
def update_email_draft(draft_id: int, changes: DraftIn) -> dict:
    """Edit a draft or change its status (draft, in_gmail, sent, discarded) and gmail_draft_id."""
    return _call("update_draft", draft_id, **changes.given())


@mcp.tool()
def record_email_thread(messages: list[MessageIn], gmail_thread_id: str | None = None,
                        subject: str | None = None, job_id: int | None = None) -> dict:
    """Save a Gmail thread (copied with the Gmail connector) and optionally link it to a job.
    Pass each message's gmail_message_id, sent_at (ISO), from_addr, to_addrs, subject and the body
    as plain text without quoted earlier messages. Set automated=true on confirmations and
    notifications ("application received", LinkedIn updates) so they don't count as a reply.
    Re-syncing a thread only adds new messages. Replies from a person set the job's first-response
    and last-contact dates; the status never moves on its own."""
    return _call("record_thread", messages, gmail_thread_id=gmail_thread_id, subject=subject, job_id=job_id)


@mcp.tool()
def link_email_thread(thread_id: int, job_id: int) -> dict:
    """Attach a saved email thread to a job."""
    return _call("link_thread", thread_id, job_id)


@mcp.tool()
def list_email_threads(unlinked_only: bool = False) -> list:
    """Saved email threads, newest first, with the job each belongs to."""
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
    """Create a contact or update one (matched on email, else name and company)."""
    return _call("upsert_contact", **contact.given())


@mcp.tool()
def list_companies() -> list:
    """All companies with job and application counts."""
    return _call("list_companies")


@mcp.tool()
def list_contacts() -> list:
    """All contacts with their company."""
    return _call("list_contacts")


@mcp.tool()
def attach_file(entity_type: Literal[FILE_ENTITIES], entity_id: int, file_path: str,
                kind: Literal[FILE_KINDS] = "screenshot", caption: str | None = None) -> dict:
    """Copy a local file (e.g. a screenshot of the job post) into the desk and attach it."""
    return _call("attach_file", entity_type, entity_id, file_path, kind=kind, caption=caption)


@mcp.tool()
def resume_versions() -> list:
    """The resumes named in settings.json (current builds and old versions). A job's
    resume_version is one of these ids, e.g. '2026-10-06 general'."""
    return _call("resume_versions")


@mcp.tool()
def query_db(sql: str) -> dict:
    """Read-only SQL against the database, for questions the other tools don't answer.
    Tables: jobs, companies, contacts, interviews, email_threads, email_messages, email_drafts,
    files, events. Returns at most 200 rows."""
    return _call("query", sql)


def main():
    mcp.run()
