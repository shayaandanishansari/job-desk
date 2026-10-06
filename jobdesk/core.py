"""The only code that writes to the database. The dashboard API, the MCP server,
the CLI and import scripts all call Desk, so validation, duplicate checks and
the change log (events) behave the same whoever makes the change.

One record per job. Its `status` says where the pursuit stands (see vocab.STATUSES),
and `set_status` is the one way to change it, so dates and next actions stay right."""

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import db, paths, rules, settings
from .vocab import (
    ACTORS, APPLY_METHODS, CHANNELS, DRAFT_KINDS, DRAFT_STATUSES, EMPLOYMENT_TYPES,
    FILE_ENTITIES, FILE_KINDS, INTERVIEW_KINDS, LABELS, OUTCOME_SIDE, OUTCOMES, PASS_REASONS,
    POSTING_STATUSES, SALARY_PERIODS, SENIORITIES, SOURCES, STAGES, STATUSES, TRI_STATE, WORK_MODES,
)

STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}
RESPONDED_OUTCOMES = ("rejected", "role_filled", "accepted", "declined")


class DeskError(Exception):
    pass


class NotFound(DeskError):
    pass


class PossibleDuplicate(DeskError):
    def __init__(self, matches):
        self.matches = matches
        listed = "; ".join(f"#{m['id']} {m['title']} at {m['company'] or '?'} ({m['reason']})" for m in matches)
        super().__init__(f"Possible duplicate of {listed}. Update that job, or pass force=True to add anyway.")


# ---------------------------------------------------------------- input models

class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    def given(self):
        """Only the fields the caller actually passed (an explicit null counts)."""
        return {k: getattr(self, k) for k in self.model_fields_set}


def _iso_datetime(v):
    """ISO text in, local time out. Gmail gives UTC ('...Z'); dates are kept in this PC's time
    zone so an email sent at 1 am on the 6th counts as the 6th."""
    if v in (None, ""):
        return None
    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat()


def _variant_label(variant):
    """'before-ats-fixes' -> 'before ATS fixes'."""
    return re.sub(r"\b(ats|ceo|cto|cv|ai|ml|ui|ux)\b", lambda m: m.group().upper(), variant.replace("-", " "))


class ContactIn(In):
    name: str | None = None
    email: str | None = None
    title: str | None = None
    company: str | None = None
    linkedin: str | None = None
    phone: str | None = None
    notes: str | None = None


class CompanyIn(In):
    name: str | None = None
    website: str | None = None
    linkedin: str | None = None
    city: str | None = None
    country: str | None = None
    visa_notes: str | None = None
    notes: str | None = None


class JobIn(In):
    """Every field of a job except `status`, which changes through set_status."""
    title: str | None = None
    company: str | None = None
    city: str | None = None
    country: str | None = None
    work_mode: Literal[WORK_MODES] | None = None
    remote_region: str | None = None
    employment_type: Literal[EMPLOYMENT_TYPES] | None = None
    seniority: Literal[SENIORITIES] | None = None
    experience: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: Literal[SALARY_PERIODS] | None = None
    salary_text: str | None = None
    visa: Literal[TRI_STATE] | None = None
    relocation: Literal[TRI_STATE] | None = None
    description: str | None = None
    apply_method: Literal[APPLY_METHODS] | None = None
    apply_to: str | None = None
    apply_notes: str | None = None
    contact: ContactIn | None = None
    source: Literal[SOURCES] | None = None
    source_url: str | None = None
    source_ref: str | None = None
    posted_by: str | None = None
    posted_on: date | None = None
    found_on: date | None = None
    deadline: date | None = None
    posting_status: Literal[POSTING_STATUSES] | None = None
    pass_reason: Literal[PASS_REASONS] | None = None
    priority: int | None = Field(None, ge=1, le=4)
    starred: bool | None = None
    fit_score: int | None = Field(None, ge=1, le=5)
    fit_notes: str | None = None
    tags: list[str] | None = None
    duplicate_of: int | None = None
    # the pursuit
    channel: Literal[CHANNELS] | None = None
    applied_on: date | None = None
    resume_version: str | None = None
    next_action: str | None = None
    next_action_due: date | None = None
    last_contact_on: date | None = None
    first_response_on: date | None = None
    follow_ups_sent: int | None = Field(None, ge=0)
    last_follow_up_on: date | None = None
    closed_on: date | None = None
    outcome_notes: str | None = None
    notes: str | None = None

    @field_validator("source_ref", mode="before")
    @classmethod
    def _ref(cls, v):
        return None if v is None else str(v)


class InterviewIn(In):
    kind: Literal[INTERVIEW_KINDS] | None = None
    scheduled_at: str | None = None
    duration_min: int | None = None
    with_whom: str | None = None
    location: str | None = None
    prep_notes: str | None = None
    outcome_notes: str | None = None
    thank_you_sent: bool | None = None

    @field_validator("scheduled_at", mode="before")
    @classmethod
    def _when(cls, v):
        return _iso_datetime(v)


class DraftIn(In):
    kind: Literal[DRAFT_KINDS] | None = None
    to_addr: str | None = None
    cc_addr: str | None = None
    subject: str | None = None
    body: str | None = None
    status: Literal[DRAFT_STATUSES] | None = None
    gmail_draft_id: str | None = None
    attach_resume: bool | None = None


class MessageIn(In):
    gmail_message_id: str | None = None
    sent_at: str
    direction: Literal["in", "out"] | None = None
    from_addr: str | None = None
    to_addrs: str | None = None
    cc_addrs: str | None = None
    subject: str | None = None
    body: str | None = None
    attachments: list[str] = []
    automated: bool = False   # a confirmation or notification, not a person writing back

    @field_validator("sent_at", mode="before")
    @classmethod
    def _when(cls, v):
        return _iso_datetime(v)


# Columns that can't be NULL: clearing one resets it to its default instead.
JOB_DEFAULTS = {
    "work_mode": "unknown", "employment_type": "unknown", "seniority": "unknown",
    "visa": "unknown", "relocation": "unknown", "apply_method": "unknown",
    "source": "other", "posting_status": "open", "tags": [], "follow_ups_sent": 0, "starred": False,
}
QUIET_FIELDS = {"description", "fit_notes", "notes", "body", "apply_notes", "prep_notes", "outcome_notes"}


def _to_db(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return int(value)
    return value


def _row(r):
    if r is None:
        return None
    out = dict(r)
    for key in ("tags", "attachments"):
        if key in out and isinstance(out[key], str):
            try:
                out[key] = json.loads(out[key])
            except json.JSONDecodeError:
                pass
    return out


def _norm_title(t):
    t = re.sub(r"\(.*?\)", " ", (t or "").lower())
    t = re.sub(r"[^a-z0-9+#]+", " ", t)
    return " ".join(t.split())


def _label(v):
    return LABELS.get(v, v)


def _channel_for(apply_method):
    return {"email": "email", "form": "form", "link": "form", "referral": "referral"}.get(apply_method, "other")


# ---------------------------------------------------------------- the desk

class Desk:
    def __init__(self, actor="me", path=None):
        if actor not in ACTORS:
            raise DeskError(f"actor must be one of {ACTORS}")
        self.actor = actor
        self.path = Path(path or paths.DB_PATH)
        self.conn = db.connect(self.path)
        self._depth = 0

    def settings(self):
        """The owner's settings.json, from next to this database (see settings.py)."""
        return settings.load(self.path.parent)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- plumbing

    @contextmanager
    def tx(self):
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        self.conn.execute("BEGIN IMMEDIATE")
        self._depth = 1
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        finally:
            self._depth = 0

    def _one(self, sql, *args):
        return _row(self.conn.execute(sql, args).fetchone())

    def _all(self, sql, *args):
        return [_row(r) for r in self.conn.execute(sql, args).fetchall()]

    def _event(self, entity_type, entity_id, action, summary, job_id=None, data=None):
        self.conn.execute(
            "INSERT INTO events (at, actor, entity_type, entity_id, job_id, action, summary, data)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (db.now(), self.actor, entity_type, entity_id, job_id, action, summary,
             json.dumps(data, ensure_ascii=False, default=str) if data else None),
        )

    def _insert(self, table, values):
        stamp = db.now()
        values = {k: _to_db(v) for k, v in values.items()}
        values.setdefault("created_at", stamp)
        if table not in ("files", "email_messages"):
            values.setdefault("updated_at", stamp)
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        cur = self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
        return cur.lastrowid

    def _update(self, table, row_id, values):
        """Write changed values and return {field: [old, new]} for the ones that changed."""
        old = self._one(f"SELECT * FROM {table} WHERE id = ?", row_id)
        if old is None:
            raise NotFound(f"{table[:-1]} #{row_id} not found")
        changes = {}
        for k, v in values.items():
            new = _to_db(v)
            cur = old.get(k)
            if isinstance(cur, list):
                cur = json.dumps(cur, ensure_ascii=False)
            if cur != new:
                changes[k] = (old.get(k), v if not isinstance(v, (date, datetime)) else v.isoformat())
        if not changes:
            return {}
        sets = {k: _to_db(v) for k, v in values.items() if k in changes}
        if "updated_at" in old:
            sets["updated_at"] = db.now()
        assignments = ", ".join(f"{k} = ?" for k in sets)
        self.conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*sets.values(), row_id))
        return changes

    @staticmethod
    def _describe(changes):
        parts = []
        for k, (old, new) in changes.items():
            name = k.replace("_", " ")
            if k in QUIET_FIELDS or isinstance(new, (list, dict)) or (isinstance(new, str) and len(new) > 60):
                parts.append(name)
            else:
                parts.append(f"{name} → {_label(new) if new is not None else '(cleared)'}")
        return ", ".join(parts)

    @staticmethod
    def _quiet(changes):
        return {k: ("(changed)" if k in QUIET_FIELDS else v) for k, v in changes.items()}

    # -- companies and contacts

    def _company_id(self, name):
        if not name:
            return None
        row = self._one("SELECT id FROM companies WHERE name = ? COLLATE NOCASE", name)
        if row:
            return row["id"]
        cid = self._insert("companies", {"name": name})
        self._event("company", cid, "created", f"Added company {name}")
        return cid

    def upsert_company(self, name, **fields):
        data = CompanyIn(name=name, **fields).given()
        data.pop("name", None)
        with self.tx():
            cid = self._company_id(name)
            changes = self._update("companies", cid, data) if data else {}
            if changes:
                self._event("company", cid, "updated", f"Updated {name}: {self._describe(changes)}", data=self._quiet(changes))
        return self.get_company(cid)

    def _contact_id(self, contact, company_id=None):
        if contact is None:
            return None
        if isinstance(contact, dict):
            contact = ContactIn(**contact)
        data = contact.given()
        company_name = data.pop("company", None)
        if company_name:
            company_id = self._company_id(company_name)
        email = (data.get("email") or "").lower() or None
        name = data.get("name")
        if not email and not name:
            return None
        row = None
        if email:
            data["email"] = email
            row = self._one("SELECT * FROM contacts WHERE email = ?", email)
        if row is None and name:
            row = self._one(
                "SELECT * FROM contacts WHERE name = ? COLLATE NOCASE AND (company_id IS ? OR company_id IS NULL)"
                " AND (email IS NULL OR ? IS NULL)", name, company_id, email)
        if row:
            fill = {k: v for k, v in data.items() if v is not None}
            if company_id and not row["company_id"]:
                fill["company_id"] = company_id
            changes = self._update("contacts", row["id"], fill)
            if changes:
                self._event("contact", row["id"], "updated", f"Updated contact {row['name']}: {self._describe(changes)}")
            return row["id"]
        data.setdefault("name", email)
        data["company_id"] = company_id
        cid = self._insert("contacts", data)
        self._event("contact", cid, "created", f"Added contact {data['name']}")
        return cid

    def upsert_contact(self, **fields):
        with self.tx():
            cid = self._contact_id(ContactIn(**fields))
        if cid is None:
            raise DeskError("A contact needs a name or an email")
        return self._one("SELECT * FROM contacts WHERE id = ?", cid)

    def get_company(self, company_id):
        c = self._one("SELECT * FROM companies WHERE id = ?", company_id)
        if not c:
            raise NotFound(f"company #{company_id} not found")
        c["contacts"] = self._all("SELECT * FROM contacts WHERE company_id = ? ORDER BY name", company_id)
        c["jobs"] = [j for j in self._summaries() if j["company_id"] == company_id]
        return c

    def list_companies(self):
        return self._all("""
            SELECT co.*, COUNT(j.id) AS job_count, COUNT(j.applied_on) AS application_count
            FROM companies co LEFT JOIN jobs j ON j.company_id = co.id
            GROUP BY co.id ORDER BY co.name COLLATE NOCASE""")

    def list_contacts(self):
        return self._all("""
            SELECT c.*, co.name AS company FROM contacts c
            LEFT JOIN companies co ON co.id = c.company_id ORDER BY c.name COLLATE NOCASE""")

    # -- reading jobs

    def _job(self, job_id):
        j = self._one("""SELECT j.*, c.email AS contact_email, c.name AS contact_name
                         FROM jobs j LEFT JOIN contacts c ON c.id = j.contact_id WHERE j.id = ?""", job_id)
        if not j:
            raise NotFound(f"job #{job_id} not found")
        return j

    THREAD_COLS = """t.*, (SELECT MAX(sent_at) FROM email_messages m WHERE m.thread_id = t.id
                              AND m.direction = 'in' AND m.automated = 0) AS last_reply_at"""

    def _unhandled_mail(self, job_id):
        """True when the latest email sync is newer than the last action on the job. Compared by
        event id, not time, so old emails synced today still count as news until someone acts."""
        mail, other = self.conn.execute(
            "SELECT MAX(CASE WHEN entity_type = 'email' THEN id END), MAX(CASE WHEN entity_type != 'email' THEN id END)"
            " FROM events WHERE job_id = ?", (job_id,)).fetchone()
        return bool(mail) and mail > (other or 0)

    def _summaries(self):
        """Every job with what the list and filters need (no posting text), including the tags'
        signals: follow-ups, email counts, the next interview and attention flags."""
        rows = self._all("""
            SELECT j.*, co.name AS company, ct.name AS contact_name, ct.email AS contact_email,
                   (SELECT COUNT(*) FROM files f WHERE f.entity_type = 'job' AND f.entity_id = j.id) AS file_count,
                   (SELECT COUNT(*) FROM email_threads t WHERE t.job_id = j.id) AS thread_count,
                   (SELECT COUNT(*) FROM email_drafts d WHERE d.job_id = j.id AND d.status IN ('draft','in_gmail')) AS open_drafts,
                   (SELECT MIN(scheduled_at) FROM interviews i WHERE i.job_id = j.id AND i.scheduled_at >= ?) AS next_interview
            FROM jobs j
            LEFT JOIN companies co ON co.id = j.company_id
            LEFT JOIN contacts ct ON ct.id = j.contact_id
        """, db.now())
        for j in rows:
            j["outcome_side"] = OUTCOME_SIDE.get(j["status"])
            if rules.in_progress(j):
                threads = self._all(f"SELECT {self.THREAD_COLS} FROM email_threads t WHERE t.job_id = ?", j["id"])
                j["flags"] = rules.attention(j, threads, unhandled_mail=self._unhandled_mail(j["id"]))
            else:
                j["flags"] = []
        return rows

    def get_job(self, job_id):
        job = next((j for j in self._summaries() if j["id"] == job_id), None)
        if not job:
            raise NotFound(f"job #{job_id} not found")
        job["company_info"] = self._one("SELECT * FROM companies WHERE id = ?", job["company_id"]) if job["company_id"] else None
        job["contact"] = self._one("SELECT * FROM contacts WHERE id = ?", job["contact_id"]) if job["contact_id"] else None
        job["files"] = self._all("SELECT * FROM files WHERE entity_type = 'job' AND entity_id = ? ORDER BY id", job_id)
        job["interviews"] = self._all("SELECT * FROM interviews WHERE job_id = ? ORDER BY scheduled_at", job_id)
        job["threads"] = self._threads_for(job_id)
        job["drafts"] = self._all("SELECT * FROM email_drafts WHERE job_id = ? ORDER BY id DESC", job_id)
        job["timeline"] = self._all("SELECT * FROM events WHERE job_id = ? ORDER BY id DESC LIMIT 300", job_id)
        job["resume"] = self.resolve_resume(job["resume_version"]) if job["resume_version"] else None
        job["possible_duplicates"] = self.find_duplicates(job["title"], job["company"], exclude_id=job_id)
        job["applied_here_before"] = self._all("""
            SELECT id, title, status, applied_on FROM jobs
            WHERE company_id = ? AND id != ? AND applied_on IS NOT NULL""", job["company_id"], job_id) \
            if job["company_id"] else []
        return job

    def _threads_for(self, job_id):
        threads = self._all(f"SELECT {self.THREAD_COLS} FROM email_threads t WHERE t.job_id = ? "
                            "ORDER BY last_at DESC", job_id)
        for t in threads:
            t["messages"] = self._all("SELECT * FROM email_messages WHERE thread_id = ? ORDER BY sent_at", t["id"])
        return threads

    FACETS = ("status", "starred", "country", "city", "work_mode", "visa", "source", "seniority",
              "employment_type", "priority", "posting_status")

    @staticmethod
    def _haystack(j):
        bits = [j.get(k) or "" for k in ("title", "company", "city", "country", "description", "fit_notes",
                                          "apply_to", "posted_by", "experience", "salary_text", "remote_region",
                                          "contact_name", "contact_email", "notes", "outcome_notes", "next_action")]
        bits += j.get("tags") or []
        return " ".join(str(b) for b in bits).lower()

    def _filter(self, rows, q=None, filters=None, skip=None):
        terms = [t for t in (q or "").lower().split() if len(t) > 1]
        filters = {k: v for k, v in (filters or {}).items() if v not in (None, [], "") and k != skip}
        out = []
        for j in rows:
            if terms:
                hay = j.setdefault("_hay", self._haystack(j))
                if not all(t in hay for t in terms):
                    continue
            ok = True
            for k, want in filters.items():
                want = want if isinstance(want, (list, tuple, set)) else [want]
                have = j.get(k)
                have = "none" if have is None else str(have)
                if have not in {str(w) for w in want}:
                    ok = False
                    break
            if ok:
                out.append(j)
        return out

    def search_jobs(self, q=None, filters=None, sort="priority", limit=None, with_facets=False):
        """Search every job. `filters` maps a facet (see FACETS) to a value or list of values;
        'none' matches an empty field. Text search matches all words anywhere in the job."""
        rows = self._summaries()
        hits = self._filter(rows, q, filters)
        keys = {
            # starred jobs first, then by priority, then newest found
            "priority": lambda j: (not j["starred"], j["priority"] or 9, -(int((j["found_on"] or "0").replace("-", "")))),
            "newest": lambda j: (j["found_on"] or "", j["id"]),
            "posted": lambda j: (j["posted_on"] or j["found_on"] or "", j["id"]),
            "company": lambda j: ((j["company"] or "~").lower(), j["title"].lower()),
            "due": lambda j: (j["next_action_due"] or "9999", j["priority"] or 9),
            "activity": lambda j: (j["updated_at"] or "", j["id"]),
        }
        hits.sort(key=keys.get(sort, keys["priority"]), reverse=sort in ("newest", "posted", "activity"))
        total = len(hits)
        if limit:
            hits = hits[:limit]
        for j in hits:
            j.pop("_hay", None)
            j.pop("description", None)
        result = {"total": total, "jobs": hits}
        if with_facets:
            facets = {}
            for f in self.FACETS:
                counts = {}
                for j in self._filter(rows, q, filters, skip=f):
                    v = j.get(f)
                    v = "none" if v is None else str(v)
                    counts[v] = counts.get(v, 0) + 1
                facets[f] = sorted(({"value": k, "count": n} for k, n in counts.items()),
                                   key=lambda x: (-x["count"], x["value"]))
            result["facets"] = facets
        return result

    # -- writing jobs

    def find_duplicates(self, title, company=None, source=None, source_ref=None, exclude_id=None):
        matches = []
        if source and source_ref:
            for r in self._all("""SELECT j.id, j.title, co.name AS company, j.city, j.found_on FROM jobs j
                                  LEFT JOIN companies co ON co.id = j.company_id
                                  WHERE j.source = ? AND j.source_ref = ?""", source, str(source_ref)):
                if r["id"] != exclude_id:
                    matches.append({**r, "reason": f"same {source} listing {source_ref}"})
        if company and title:
            want = _norm_title(title)
            rows = self._all("""SELECT j.id, j.title, co.name AS company, j.city, j.found_on FROM jobs j
                                JOIN companies co ON co.id = j.company_id
                                WHERE co.name = ? COLLATE NOCASE""", company)
            for r in rows:
                if r["id"] == exclude_id or any(m["id"] == r["id"] for m in matches):
                    continue
                have = _norm_title(r["title"])
                ratio = SequenceMatcher(None, want, have).ratio()
                if ratio >= 0.8 or (want and have and (want in have or have in want)):
                    matches.append({**r, "reason": f"same company, similar title ({ratio:.0%})"})
        return matches

    def add_job(self, force=False, status=None, status_on=None, **fields):
        """Add a job. Pass `status` (and `status_on`, the date it happened) to add one that's
        already further along, e.g. status='applied' with applied_on for something sent last week."""
        if status is not None and status not in STATUSES:
            raise DeskError(f"status must be one of {STATUSES}")
        job = JobIn(**fields)
        data = job.given()
        if not data.get("title"):
            raise DeskError("A job needs a title")
        matches = self.find_duplicates(data["title"], data.get("company"), data.get("source"), data.get("source_ref"))
        exact = [m for m in matches if "listing" in m["reason"]]
        if exact:
            raise PossibleDuplicate(exact)
        if matches and not force:
            raise PossibleDuplicate(matches)

        with self.tx():
            company_name = data.pop("company", None)
            data["company_id"] = self._company_id(company_name)
            if data.pop("contact", None):
                data["contact_id"] = self._contact_id(job.contact, data["company_id"])
            data.setdefault("found_on", date.today())
            for k, default in JOB_DEFAULTS.items():
                if data.get(k) is None:
                    data[k] = default
            jid = self._insert("jobs", data)
            where = ", ".join(x for x in (data.get("city"), data.get("country")) if x)
            self._event("job", jid, "created",
                        f"Added job: {data['title']}" + (f" at {company_name}" if company_name else "")
                        + (f" ({where})" if where else ""), job_id=jid)
            if status and status != "new":
                self.set_status(jid, status, on=status_on or data.get("applied_on"),
                                pass_reason=data.get("pass_reason"))
        return self.get_job(jid)

    def update_job(self, job_id, **fields):
        job = JobIn(**fields)
        data = job.given()
        with self.tx():
            current = self._job(job_id)
            if "company" in data:
                data["company_id"] = self._company_id(data.pop("company"))
            if "contact" in data:
                data.pop("contact")
                data["contact_id"] = self._contact_id(job.contact, data.get("company_id", current["company_id"]))
            if "title" in data and not data["title"]:
                raise DeskError("A job's title can't be empty")
            for k, default in JOB_DEFAULTS.items():
                if k in data and data[k] is None:
                    data[k] = default
            changes = self._update("jobs", job_id, data)
            if set(changes) == {"starred"}:
                self._event("job", job_id, "starred" if data["starred"] else "unstarred",
                            "Starred" if data["starred"] else "Removed the star", job_id=job_id)
            elif changes:
                self._event("job", job_id, "updated", f"Updated {self._describe(changes)}",
                            job_id=job_id, data=self._quiet(changes))
        return self.get_job(job_id)

    def star(self, job_id, starred=True):
        return self.update_job(job_id, starred=starred)

    def current_resume_version(self, variant=None):
        """The current build of `variant`, or of the first resume in settings."""
        current = [v for v in self.resume_versions() if v["current"]]
        for v in current:
            if variant is None or v["variant"] == variant:
                return v["id"]
        return None

    def _refresh_next(self, job_id, today=None):
        job = self._job(job_id)
        interviews = self._all("SELECT * FROM interviews WHERE job_id = ?", job_id)
        action, due = rules.suggest_next(job, interviews, today)
        self._update("jobs", job_id, {"next_action": action, "next_action_due": due})

    def set_status(self, job_id, status, on=None, note=None, pass_reason=None, resume_version=None,
                   next_action=None, next_action_due=None, outcome_notes=None):
        """Move a job to any status, dated `on` (default today).
        - Applied or later the first time: records the applied date, channel and resume version
          (the default resume's current build if it's sent today; unknown for past dates).
        - Screening or later: records the first reply.
        - In progress: the next action is recomputed from the follow-up rules unless you pass one.
        - Closed: records the date and clears the next action. Moving a closed job back into
          progress reopens it."""
        if status not in STATUSES:
            raise DeskError(f"status must be one of {STATUSES}")
        job = self._job(job_id)
        on = rules.d(on) or date.today()
        values = {"status": status}
        if status in STAGES:
            reached = job["stage_reached"]
            if not reached or STAGE_ORDER[status] > STAGE_ORDER[reached]:
                values["stage_reached"] = status
            if not job["channel"]:
                values["channel"] = _channel_for(job["apply_method"])
            if STAGE_ORDER[status] >= STAGE_ORDER["applied"] and not job["applied_on"]:
                values["applied_on"] = on
                values["last_contact_on"] = on
                values["resume_version"] = (resume_version or job["resume_version"]
                                            or (self.current_resume_version() if on >= date.today() else None))
            elif resume_version:
                values["resume_version"] = resume_version
            if STAGE_ORDER[status] >= STAGE_ORDER["screening"]:
                if not job["first_response_on"]:
                    values["first_response_on"] = on
                values["last_contact_on"] = max(on, rules.d(job["last_contact_on"]) or on)
            values["closed_on"] = None
        elif status in OUTCOMES:
            values.update(closed_on=on, next_action=None, next_action_due=None)
            if outcome_notes:
                values["outcome_notes"] = outcome_notes
            if status in RESPONDED_OUTCOMES and job["applied_on"] and not job["first_response_on"]:
                values["first_response_on"] = on
        elif status == "passed":
            values.update(pass_reason=pass_reason or job["pass_reason"] or "other",
                          next_action=None, next_action_due=None)
        else:  # new, shortlisted
            values["pass_reason"] = None

        with self.tx():
            changes = self._update("jobs", job_id, values)
            if "status" in changes:
                when = f" on {on.isoformat()}" if on != date.today() else ""
                if status in OUTCOMES:
                    side = "they" if OUTCOME_SIDE[status] == "them" else "you"
                    summary = f"Closed: {_label(status)} ({side} ended it){when}" + (f". {outcome_notes}" if outcome_notes else "")
                elif status == "passed":
                    summary = f"Passed: {_label(values['pass_reason'])}"
                elif status in STAGES:
                    back = job["stage_reached"] and STAGE_ORDER[status] < STAGE_ORDER[job["stage_reached"]]
                    summary = f"{'Moved back to' if back else 'Moved to'} {_label(status)}{when}"
                    if job["status"] in OUTCOMES:
                        summary = f"Reopened: {_label(status)}{when}"
                else:
                    summary = f"Marked {_label(status)}"
                self._event("job", job_id, "status_changed", summary, job_id=job_id,
                            data={"from": job["status"], "to": status, "on": on.isoformat()})
            if status in STAGES:
                if next_action is not None:
                    self._update("jobs", job_id, {"next_action": next_action, "next_action_due": next_action_due})
                else:
                    self._refresh_next(job_id)
            if note:
                self._note(job_id, note)
        return self.get_job(job_id)

    def log_follow_up(self, job_id, on=None, note=None):
        job = self._job(job_id)
        if job["status"] not in STAGES:
            raise DeskError("Only a job in progress can be followed up")
        on = rules.d(on) or date.today()
        with self.tx():
            n = (job["follow_ups_sent"] or 0) + 1
            self._update("jobs", job_id, {
                "follow_ups_sent": n, "last_follow_up_on": on,
                "last_contact_on": max(on, rules.d(job["last_contact_on"]) or on)})
            self._event("job", job_id, "follow_up", f"Sent follow-up #{n}" + (f": {note}" if note else ""),
                        job_id=job_id)
            self._refresh_next(job_id)
        return self.get_job(job_id)

    def delete_job(self, job_id):
        job = self.get_job(job_id)
        with self.tx():
            self.conn.execute("DELETE FROM files WHERE entity_type = 'job' AND entity_id = ?", (job_id,))
            self.conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._event("job", job_id, "deleted", f"Deleted job: {job['title']} at {job['company'] or '?'}", job_id=job_id)
        return {"deleted": job_id}

    # -- interviews

    def add_interview(self, job_id, kind="other", scheduled_at=None, on=None, **fields):
        """Add an interview. Moves the job to screening (kind 'screen') or interviewing if it's
        behind, dated `on` (default today)."""
        data = InterviewIn(kind=kind, scheduled_at=scheduled_at, **fields).given()
        job = self._job(job_id)
        with self.tx():
            data = {k: v for k, v in data.items() if v is not None}
            data["job_id"] = job_id
            iid = self._insert("interviews", data)
            when = data.get("scheduled_at")
            self._event("interview", iid, "created",
                        f"Interview added: {_label(kind).replace('_', ' ')}" + (f" on {when.replace('T', ' ')[:16]}" if when else ""),
                        job_id=job_id)
            target = "screening" if kind == "screen" else "interviewing"
            reached = job["stage_reached"]
            if job["status"] in STAGES and (not reached or STAGE_ORDER[reached] < STAGE_ORDER[target]):
                self.set_status(job_id, target, on=on)
            elif job["status"] in STAGES:
                self._refresh_next(job_id)
        return self.get_job(job_id)

    def update_interview(self, interview_id, **fields):
        data = InterviewIn(**fields).given()
        iv = self._one("SELECT * FROM interviews WHERE id = ?", interview_id)
        if not iv:
            raise NotFound(f"interview #{interview_id} not found")
        job = self._job(iv["job_id"])
        with self.tx():
            changes = self._update("interviews", interview_id, data)
            if changes:
                self._event("interview", interview_id, "updated", f"Interview updated: {self._describe(changes)}",
                            job_id=job["id"], data=self._quiet(changes))
                if job["status"] in STAGES:
                    self._refresh_next(job["id"])
        return self.get_job(job["id"])

    # -- notes

    def _note(self, job_id, text, entity_type="job", entity_id=None):
        self._event(entity_type, entity_id or job_id, "note", text.strip(), job_id=job_id)

    def add_note(self, entity_type, entity_id, text):
        if entity_type not in ("job", "company"):
            raise DeskError("Notes go on a job or a company")
        if not (text or "").strip():
            raise DeskError("Empty note")
        with self.tx():
            if entity_type == "job":
                self._job(entity_id)
                self._note(entity_id, text)
            else:
                if not self._one("SELECT id FROM companies WHERE id = ?", entity_id):
                    raise NotFound(f"company #{entity_id} not found")
                self._event("company", entity_id, "note", text.strip())
        return {"ok": True}

    # -- email

    def save_draft(self, job_id, body, subject=None, to_addr=None, cc_addr=None, kind="application",
                   status="draft", gmail_draft_id=None, attach_resume=True):
        data = DraftIn(body=body, subject=subject, to_addr=to_addr, cc_addr=cc_addr, kind=kind, status=status,
                       gmail_draft_id=gmail_draft_id, attach_resume=attach_resume).given()
        self._job(job_id)
        with self.tx():
            data = {k: v for k, v in data.items() if v is not None}
            data["job_id"] = job_id
            did = self._insert("email_drafts", data)
            self._event("draft", did, "created", f"Drafted {_label(kind).replace('_', ' ')} email: {subject or '(no subject)'}",
                        job_id=job_id)
        return self._one("SELECT * FROM email_drafts WHERE id = ?", did)

    def update_draft(self, draft_id, **fields):
        data = DraftIn(**fields).given()
        draft = self._one("SELECT * FROM email_drafts WHERE id = ?", draft_id)
        if not draft:
            raise NotFound(f"draft #{draft_id} not found")
        with self.tx():
            changes = self._update("email_drafts", draft_id, data)
            if changes:
                summary = (f"Email draft marked {changes['status'][1].replace('_', ' ')}" if set(changes) == {"status"}
                           else f"Email draft updated: {self._describe(changes)}")
                self._event("draft", draft_id, "updated", summary, job_id=draft["job_id"], data=self._quiet(changes))
        return self._one("SELECT * FROM email_drafts WHERE id = ?", draft_id)

    def record_thread(self, messages, gmail_thread_id=None, subject=None, job_id=None):
        """Save (or refresh) an email thread from Gmail. Messages are matched on gmail_message_id,
        so syncing the same thread twice is safe. A message's direction is worked out from the
        sender when it isn't given."""
        msgs = [MessageIn(**m) if isinstance(m, dict) else m for m in messages]
        if not msgs:
            raise DeskError("A thread needs at least one message")
        mine = self.settings()["email_addresses"]
        for m in msgs:
            if m.direction is None:
                sender = (m.from_addr or "").lower()
                m.direction = "out" if any(a in sender for a in mine) else "in"
        if job_id:
            self._job(job_id)
        with self.tx():
            thread = self._one("SELECT * FROM email_threads WHERE gmail_thread_id = ?", gmail_thread_id) \
                if gmail_thread_id else None
            if thread is None:
                tid = self._insert("email_threads", {"gmail_thread_id": gmail_thread_id, "job_id": job_id,
                                                      "subject": subject or msgs[0].subject, "synced_at": db.now()})
                created = True
            else:
                tid = thread["id"]
                created = False
                if job_id and thread["job_id"] != job_id:
                    self._update("email_threads", tid, {"job_id": job_id})
                job_id = job_id or thread["job_id"]
            new = 0
            for m in msgs:
                existing = self._one("SELECT id FROM email_messages WHERE gmail_message_id = ?", m.gmail_message_id) \
                    if m.gmail_message_id else None
                if existing:
                    self.conn.execute("UPDATE email_messages SET body = COALESCE(?, body) WHERE id = ?",
                                      (m.body, existing["id"]))
                    continue
                row = {k: _to_db(v) for k, v in {**m.model_dump(), "thread_id": tid}.items()}
                cols = ", ".join(row)
                self.conn.execute(f"INSERT INTO email_messages ({cols}) VALUES ({', '.join('?' for _ in row)})",
                                  tuple(row.values()))
                new += 1
            stats = self._one("SELECT COUNT(*) AS n, MIN(sent_at) AS first_at, MAX(sent_at) AS last_at "
                              "FROM email_messages WHERE thread_id = ?", tid)
            last = self._one("SELECT direction FROM email_messages WHERE thread_id = ? AND automated = 0"
                             " ORDER BY sent_at DESC LIMIT 1", tid) or {"direction": None}
            people = sorted({a.strip() for r in self._all("SELECT from_addr, to_addrs, cc_addrs FROM email_messages WHERE thread_id = ?", tid)
                             for f in (r["from_addr"], r["to_addrs"], r["cc_addrs"]) if f for a in f.split(",") if a.strip()})
            self._update("email_threads", tid, {
                "message_count": stats["n"], "first_at": stats["first_at"], "last_at": stats["last_at"],
                "last_direction": last["direction"], "participants": ", ".join(people), "synced_at": db.now(),
                **({"subject": subject} if subject else {})})
            if job_id:
                self._apply_thread_to_job(job_id, tid)
            if created or new:
                label = subject or msgs[0].subject or "(no subject)"
                self._event("email", tid, "synced",
                            f"Email thread saved: {label} ({new} new message{'s' if new != 1 else ''})", job_id=job_id)
        return self.get_thread(tid)

    def _apply_thread_to_job(self, job_id, thread_id):
        """Replies from a person set the first-response and last-contact dates. The status doesn't move."""
        job = self._job(job_id)
        msgs = self._all("SELECT sent_at, direction, automated FROM email_messages WHERE thread_id = ?", thread_id)
        latest = max(rules.d(m["sent_at"]) for m in msgs)
        values = {}
        if not job["last_contact_on"] or latest > rules.d(job["last_contact_on"]):
            values["last_contact_on"] = latest
        if job["applied_on"]:
            sent = rules.d(job["applied_on"])
            replies = [rules.d(m["sent_at"]) for m in msgs
                       if m["direction"] == "in" and not m["automated"] and rules.d(m["sent_at"]) >= sent]
            if replies and (not job["first_response_on"] or min(replies) < rules.d(job["first_response_on"])):
                values["first_response_on"] = min(replies)
        if values:
            self._update("jobs", job_id, values)

    def link_thread(self, thread_id, job_id):
        thread = self._one("SELECT * FROM email_threads WHERE id = ?", thread_id)
        if not thread:
            raise NotFound(f"thread #{thread_id} not found")
        self._job(job_id)
        with self.tx():
            self._update("email_threads", thread_id, {"job_id": job_id})
            self._apply_thread_to_job(job_id, thread_id)
            self._event("email", thread_id, "linked", f"Linked email thread: {thread['subject']}", job_id=job_id)
        return self.get_thread(thread_id)

    def get_thread(self, thread_id):
        t = self._one("SELECT * FROM email_threads WHERE id = ?", thread_id)
        if not t:
            raise NotFound(f"thread #{thread_id} not found")
        t["messages"] = self._all("SELECT * FROM email_messages WHERE thread_id = ? ORDER BY sent_at", thread_id)
        return t

    def list_threads(self, unlinked_only=False):
        sql = """SELECT t.*, j.title AS job_title, co.name AS company FROM email_threads t
                 LEFT JOIN jobs j ON j.id = t.job_id LEFT JOIN companies co ON co.id = j.company_id"""
        if unlinked_only:
            sql += " WHERE t.job_id IS NULL"
        return self._all(sql + " ORDER BY t.last_at DESC")

    # -- files

    def attach_file(self, entity_type, entity_id, source_path, kind="other", caption=None, name=None):
        if entity_type not in FILE_ENTITIES:
            raise DeskError(f"entity_type must be one of {FILE_ENTITIES}")
        if kind not in FILE_KINDS:
            raise DeskError(f"kind must be one of {FILE_KINDS}")
        source = Path(source_path)
        if not source.is_file():
            raise DeskError(f"No such file: {source}")
        table = {"job": "jobs", "company": "companies"}[entity_type]
        if not self._one(f"SELECT id FROM {table} WHERE id = ?", entity_id):
            raise NotFound(f"{entity_type} #{entity_id} not found")
        rel = db.copy_into_files(source, f"{entity_type}s/{entity_id}", name, files_dir=self.path.parent / "files")
        with self.tx():
            fid = self._insert("files", {"entity_type": entity_type, "entity_id": entity_id, "path": rel,
                                         "kind": kind, "caption": caption})
            self._event("file", fid, "created", f"Attached {kind.replace('_', ' ')}: {caption or Path(rel).name}",
                        job_id=entity_id if entity_type == "job" else None)
        return self._one("SELECT * FROM files WHERE id = ?", fid)

    # -- views

    def today(self, today=None):
        t = rules.d(today) or date.today()
        rows = self._summaries()
        active = [j for j in rows if rules.in_progress(j)]
        due, upcoming, attention = [], [], []
        for j in active:
            due_on = rules.d(j["next_action_due"])
            if due_on and due_on <= t:
                due.append(j)
            elif due_on and due_on <= t + timedelta(days=7):
                upcoming.append(j)
            extra = [f for f in j["flags"] if f["flag"] in ("reply_waiting", "suggest_no_response", "no_next_action")]
            if extra:
                attention.append({**j, "flags": extra})
        due.sort(key=lambda j: j["next_action_due"])
        upcoming.sort(key=lambda j: j["next_action_due"])
        # Jobs not applied to yet whose posting closes within a week: easy to miss otherwise.
        closing_soon = sorted((j for j in rows if j["status"] in ("new", "shortlisted") and j["deadline"]
                               and j["posting_status"] == "open"
                               and t <= rules.d(j["deadline"]) <= t + timedelta(days=7)),
                              key=lambda j: j["deadline"])
        interviews = self._all("""
            SELECT i.*, j.title, co.name AS company FROM interviews i
            JOIN jobs j ON j.id = i.job_id LEFT JOIN companies co ON co.id = j.company_id
            WHERE i.scheduled_at >= ? AND i.scheduled_at <= ? ORDER BY i.scheduled_at""",
            t.isoformat(), (t + timedelta(days=14)).isoformat() + "T23:59:59")
        drafts = self._all("""
            SELECT d.id, d.subject, d.status, d.kind, d.to_addr, d.updated_at, d.job_id, j.title, co.name AS company
            FROM email_drafts d JOIN jobs j ON j.id = d.job_id LEFT JOIN companies co ON co.id = j.company_id
            WHERE d.status IN ('draft', 'in_gmail') AND j.status NOT IN ({}) ORDER BY d.updated_at DESC""".format(
            ", ".join(f"'{o}'" for o in OUTCOMES + ("passed",))))
        new_jobs = sorted((j for j in rows if j["status"] == "new"), key=lambda j: j["found_on"], reverse=True)
        week_start = t - timedelta(days=t.weekday())
        sent_this_week = sum(1 for j in rows if j["applied_on"] and rules.d(j["applied_on"]) >= week_start)
        replies_this_week = self._one("""SELECT COUNT(*) AS n FROM email_messages m JOIN email_threads th ON th.id = m.thread_id
                                         WHERE m.direction = 'in' AND m.automated = 0 AND th.job_id IS NOT NULL
                                         AND m.sent_at >= ?""", week_start.isoformat())["n"]
        for j in rows:
            j.pop("description", None)
        return {
            "date": t.isoformat(), "due": due, "upcoming": upcoming, "attention": attention,
            "interviews": interviews, "drafts": drafts, "closing_soon": closing_soon,
            "to_triage": {"total": len(new_jobs), "jobs": new_jobs[:8]},
            "week": {"start": week_start.isoformat(), "sent": sent_this_week, "replies": replies_this_week,
                     "open": len(active)},
        }

    def stats(self):
        jobs = self._all("""SELECT j.*, co.name AS company FROM jobs j LEFT JOIN companies co ON co.id = j.company_id""")
        sent = [j for j in jobs if j["applied_on"]]

        def marks(j):
            reached = STAGE_ORDER.get(j["stage_reached"] or "", -1)
            later = reached >= STAGE_ORDER["screening"]
            responded = bool(j["first_response_on"]) or later or j["status"] in RESPONDED_OUTCOMES
            offer = j["stage_reached"] == "offer" or j["status"] in ("accepted", "declined")
            return responded, later, offer

        def funnel(rows):
            f = {"applied": len(rows), "responded": 0, "interviewed": 0, "offers": 0}
            for j in rows:
                r, i, o = marks(j)
                f["responded"] += r
                f["interviewed"] += i
                f["offers"] += o
            return f

        def by(key):
            groups = {}
            for j in sent:
                groups.setdefault(j.get(key) or "unknown", []).append(j)
            return sorted(({"value": k, **funnel(v)} for k, v in groups.items()), key=lambda x: -x["applied"])

        waits = sorted(rules.days_between(j["applied_on"], j["first_response_on"]) for j in sent if j["first_response_on"])
        median = waits[len(waits) // 2] if waits else None
        if waits and len(waits) % 2 == 0:
            median = (waits[len(waits) // 2 - 1] + waits[len(waits) // 2]) / 2

        t = date.today()
        monday = t - timedelta(days=t.weekday())
        weeks = []
        for i in range(11, -1, -1):
            start = monday - timedelta(weeks=i)
            end = start + timedelta(days=7)
            weeks.append({"week": start.isoformat(),
                          "sent": sum(1 for j in sent if start <= rules.d(j["applied_on"]) < end)})

        counts = {}
        for j in jobs:
            counts[j["status"]] = counts.get(j["status"], 0) + 1
        return {
            "funnel": funnel(sent), "by_source": by("source"), "by_resume": by("resume_version"),
            "by_country": by("country"), "by_channel": by("channel"),
            "median_days_to_response": median, "responses_timed": len(waits), "weeks": weeks,
            "outcomes": {s: counts[s] for s in OUTCOMES if counts.get(s)},
            "pipeline": {s: counts.get(s, 0) for s in STAGES},
            "jobs_by_status": counts,
        }

    def overview(self):
        """A short orientation for an agent: counts and what needs doing."""
        today = self.today()
        s = self.stats()
        return {
            "jobs": sum(s["jobs_by_status"].values()), "jobs_by_status": s["jobs_by_status"],
            "funnel": s["funnel"],
            "due_now": [{"job_id": j["id"], "job": f"{j['title']} at {j['company']}",
                         "next_action": j["next_action"], "due": j["next_action_due"]} for j in today["due"]],
            "needs_attention": [{"job_id": j["id"], "job": f"{j['title']} at {j['company']}",
                                 "flags": [f["text"] for f in j["flags"]]} for j in today["attention"]],
            "closing_soon": [{"job_id": j["id"], "job": f"{j['title']} at {j['company']}", "deadline": j["deadline"]}
                             for j in today["closing_soon"]],
            "drafts_waiting": [{"draft_id": d["id"], "job_id": d["job_id"], "subject": d["subject"],
                                "status": d["status"]} for d in today["drafts"]],
            "new_jobs_to_triage": today["to_triage"]["total"],
        }

    def events_after(self, after_id=0, limit=200):
        return self._all("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?", after_id, limit)

    def last_event_id(self):
        return self.conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]

    # -- resume versions (read-only: the files named in settings)

    def resume_versions(self):
        """The resumes in settings. Each one listed under `resumes` is a current build, dated by
        when its file last changed. Past builds in `old_resumes` are named 'YYYY-MM-DD_<name>';
        their variant is the name without the owner's name or a leading 'resume'. A version's id
        is '<date> <variant>', e.g. '2026-10-06 general'."""
        s = self.settings()
        out = []
        for variant, p in s["resumes"].items():
            if p.is_file():
                built = date.fromtimestamp(p.stat().st_mtime).isoformat()
                out.append({"id": f"{built} {variant}", "built_on": built, "variant": variant, "current": True,
                            "label": f"{built} · {_variant_label(variant)} (current)", "path": str(p)})
        old = s["old_resumes"]
        if old and old.is_dir():
            owner = re.escape(s["name"] or "").replace(r"\ ", "[_ -]")
            for p in sorted(old.iterdir(), reverse=True):
                m = re.match(r"(\d{4}-\d{2}-\d{2})[_ -](.+)$", p.stem)
                if not p.is_file() or not m:
                    continue
                built, rest = m.groups()
                if owner:
                    rest = re.sub(rf"^{owner}[_ -]*", "", rest, flags=re.I)
                variant = re.sub(r"[_ ]+", "-", re.sub(r"^resume[_ -]?", "", rest.lower())) or "resume"
                if p.suffix.lower() != ".pdf":
                    variant += p.suffix.lower().replace(".", "-")
                vid = f"{built} {variant}"
                if any(v["id"] == vid for v in out):
                    continue
                out.append({"id": vid, "built_on": built, "variant": variant, "current": False,
                            "label": f"{built} · {_variant_label(variant)}", "path": str(p)})
        return out

    def resolve_resume(self, version):
        if not version:
            return None
        for v in self.resume_versions():
            if v["id"] == version:
                return v
        return {"id": version, "label": version, "path": None, "current": False, "missing": True}

    # -- ad hoc, read-only SQL for agents

    def query(self, sql, limit=200):
        ro = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        ro.row_factory = sqlite3.Row
        try:
            cur = ro.execute(sql)
            rows = [dict(r) for r in cur.fetchmany(limit)]
            return {"rows": rows, "truncated": len(rows) == limit}
        finally:
            ro.close()
