"""Follow-up rules. Change the numbers here; everything else reads them.

Defaults come from common job-search practice:
- After applying: follow up after 7 business days, a second time 7 business
  days later, never more than twice.
- After 30 days with no reply (and at least one follow-up, when there was
  someone to follow up with), suggest closing it as "no response". The
  dashboard and Claude only suggest; nothing closes on its own.
- After a screen or interview: thank-you within a day (not after a take-home),
  then follow up after 5 business days if there's no news.

Client work (projects) moves faster than hiring, so its nudges come sooner:
- After a pitch: follow up after 3 business days, a second time 5 business days
  later, never more than twice. After 21 days of silence, suggest "no response".
- An Upwork proposal can't be followed up (Upwork only lets you write once the
  client does), so it only gets the silence check, after 14 days.
- Once they're talking, or have a proposal or terms: follow up 3 business days
  after the last contact if there's no news.

Every function takes a job (or project) as a dict: the row plus 'contact_email'.
"""

from datetime import date, datetime, timedelta

from .vocab import PROJECT_STAGES, STAGES

FOLLOW_UP_AFTER = 7          # business days after applying, and between follow-ups
MAX_FOLLOW_UPS = 2
NO_RESPONSE_AFTER = 30       # calendar days of silence before suggesting "no response"
THANK_YOU_WITHIN = 1         # days after an interview
POST_INTERVIEW_FOLLOW_UP = 5 # business days after the last contact

PITCH_FOLLOW_UPS = (3, 5)    # business days: after the pitch, then after the first follow-up
PITCH_NO_RESPONSE_AFTER = 21 # calendar days of silence after a pitch
UPWORK_NO_RESPONSE_AFTER = 14
TALKING_FOLLOW_UP = 3        # business days after the last contact, once they're talking


def d(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def add_business_days(start, n):
    day = d(start)
    while n > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:          # Mon-Fri
            n -= 1
    return day


def days_between(a, b):
    return (d(b) - d(a)).days


def in_progress(job):
    return job["status"] in STAGES


def can_follow_up(job):
    """Someone to write to: an email application, a referral, or a known contact."""
    return job.get("channel") in ("email", "referral") or bool(job.get("contact_email"))


def suggest_next(job, interviews=(), today=None):
    """The next action and due date a job in progress should carry right now."""
    today = d(today) or date.today()
    status = job["status"]
    if status == "drafting":
        return "Send the application", None

    if status == "applied":
        applied = d(job.get("applied_on")) or today
        sent = job.get("follow_ups_sent") or 0
        last = d(job.get("last_follow_up_on")) or applied
        close_on = max(applied + timedelta(days=NO_RESPONSE_AFTER),
                       add_business_days(last, FOLLOW_UP_AFTER) if sent else applied)
        if not can_follow_up(job):
            return "Close as no response if still silent", close_on
        if sent == 0:
            return "Follow up", add_business_days(applied, FOLLOW_UP_AFTER)
        if sent < MAX_FOLLOW_UPS:
            return "Second follow-up", add_business_days(last, FOLLOW_UP_AFTER)
        return "Close as no response if still silent", close_on

    if status in ("screening", "interviewing"):
        now = datetime.now()
        dated = [i for i in interviews if i.get("scheduled_at")]
        upcoming = sorted((i for i in dated if datetime.fromisoformat(i["scheduled_at"]) >= now),
                          key=lambda i: i["scheduled_at"])
        if upcoming:
            nxt = upcoming[0]
            return f"Prepare for the {nxt['kind'].replace('_', ' ')} interview", d(nxt["scheduled_at"])
        past = sorted((i for i in dated if datetime.fromisoformat(i["scheduled_at"]) < now),
                      key=lambda i: i["scheduled_at"])
        if past and not past[-1].get("thank_you_sent") and past[-1].get("kind") != "take_home":
            return "Send a thank-you", d(past[-1]["scheduled_at"]) + timedelta(days=THANK_YOU_WITHIN)
        last = d(job.get("last_contact_on")) or today
        return "Follow up if there's no news", add_business_days(last, POST_INTERVIEW_FOLLOW_UP)

    if status == "offer":
        return "Respond to the offer", today + timedelta(days=2)

    return None, None


def _shared_flags(job, threads, today, unhandled_mail):
    """The flags jobs and projects have in common: what's due, no next action, a reply waiting."""
    flags = []
    due = d(job.get("next_action_due"))
    if due and due < today:
        flags.append({"flag": "overdue", "text": f"{job.get('next_action') or 'Next action'} was due {due.isoformat()}"})
    elif due and due == today:
        flags.append({"flag": "due_today", "text": f"{job.get('next_action') or 'Next action'} is due today"})

    if not job.get("next_action"):
        flags.append({"flag": "no_next_action", "text": "No next action set"})

    waiting = [t for t in threads if t.get("last_direction") == "in"] if unhandled_mail else []
    if waiting:
        flags.append({"flag": "reply_waiting", "text": "They replied. Answer it or update the status."})
    return flags, bool(waiting)


def attention(job, threads=(), today=None, unhandled_mail=True):
    """Flags for a job in progress. Read-only: these drive the Today view and the row tags.
    `unhandled_mail` is true when the latest email sync came after the last time anyone acted on
    the job (status, next action, note...). A reply from them counts as waiting only then."""
    today = d(today) or date.today()
    if not in_progress(job):
        return []
    flags, waiting = _shared_flags(job, threads, today, unhandled_mail)

    if job["status"] == "applied":
        # Silence is counted from the day it was sent; any reply from them ends it.
        applied = d(job.get("applied_on"))
        silent = (applied and not job.get("first_response_on")
                  and days_between(applied, today) >= NO_RESPONSE_AFTER)
        followed = (job.get("follow_ups_sent") or 0) >= 1 or not can_follow_up(job)
        if silent and followed and not waiting:
            flags.append({"flag": "suggest_no_response",
                          "text": f"No reply in {NO_RESPONSE_AFTER}+ days. Close as no response?"})
    return flags


# ------------------------------------------------------------------ projects

def project_in_progress(project):
    return project["status"] in PROJECT_STAGES


def can_follow_up_pitch(project):
    """Upwork only lets you message a client after they've written to you."""
    return project.get("channel") != "upwork"


def silence_limit(project):
    return UPWORK_NO_RESPONSE_AFTER if project.get("channel") == "upwork" else PITCH_NO_RESPONSE_AFTER


def suggest_project_next(project, today=None):
    """The next action and due date a project in progress should carry right now."""
    today = d(today) or date.today()
    status = project["status"]
    if status == "drafting":
        upwork = "upwork" in (project.get("channel"), project.get("source"))
        return ("Submit the proposal" if upwork else "Send the pitch"), None

    if status == "pitched":
        pitched = d(project.get("pitched_on")) or today
        sent = project.get("follow_ups_sent") or 0
        last = d(project.get("last_follow_up_on")) or pitched
        close_on = max(pitched + timedelta(days=silence_limit(project)),
                       add_business_days(last, PITCH_FOLLOW_UPS[-1]) if sent else pitched)
        if not can_follow_up_pitch(project) or sent >= len(PITCH_FOLLOW_UPS):
            return "Close as no response if still silent", close_on
        return ("Follow up" if sent == 0 else "Second follow-up"), add_business_days(last, PITCH_FOLLOW_UPS[sent])

    if status in ("talking", "proposal", "negotiating"):
        last = d(project.get("last_contact_on")) or today
        what = {"talking": "Follow up if there's no news", "proposal": "Follow up on the proposal",
                "negotiating": "Follow up on the terms"}[status]
        return what, add_business_days(last, TALKING_FOLLOW_UP)

    return None, None


def project_attention(project, threads=(), today=None, unhandled_mail=True):
    """Flags for a project in progress, the same ones a job gets."""
    today = d(today) or date.today()
    if not project_in_progress(project):
        return []
    flags, waiting = _shared_flags(project, threads, today, unhandled_mail)
    if project["status"] == "pitched":
        pitched = d(project.get("pitched_on"))
        limit = silence_limit(project)
        silent = pitched and not project.get("first_response_on") and days_between(pitched, today) >= limit
        followed = (project.get("follow_ups_sent") or 0) >= 1 or not can_follow_up_pitch(project)
        if silent and followed and not waiting:
            flags.append({"flag": "suggest_no_response", "text": f"No reply in {limit}+ days. Close as no response?"})
    return flags
