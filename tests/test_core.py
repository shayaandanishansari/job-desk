import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from jobdesk import db, rules
from jobdesk.core import Desk, DeskError, PossibleDuplicate


@pytest.fixture
def desk(tmp_path):
    d = Desk(actor="claude", path=tmp_path / "t.db")
    yield d
    d.close()


def make_job(desk, **kw):
    fields = dict(title="AI Engineer", company="Acme", city="Karachi", country="Pakistan",
                  work_mode="onsite", source="linkedin", apply_method="email", apply_to="hr@acme.com")
    fields.update(kw)
    return desk.add_job(**fields)


def test_add_job_creates_company_contact_and_event(desk):
    job = make_job(desk, contact={"name": "Sam Rivera", "email": "Sam@Acme.com", "title": "Architect"})
    assert job["company"] == "Acme"
    assert job["contact"]["email"] == "sam@acme.com"
    assert job["status"] == "new" and job["visa"] == "unknown" and job["stage_reached"] is None
    actions = [e["action"] for e in desk.events_after(0)]
    assert actions.count("created") == 3          # company, contact, job


def test_duplicates_are_caught(desk):
    make_job(desk, source="aijobsuae", source_ref=123)
    with pytest.raises(PossibleDuplicate):
        make_job(desk, title="AI Engineer (Multi-Agent)")            # same company, similar title
    with pytest.raises(PossibleDuplicate):
        make_job(desk, company="Other", source="aijobsuae", source_ref="123", force=True)  # exact listing: never
    other = make_job(desk, title="AI Engineer (Multi-Agent)", force=True)
    assert other["possible_duplicates"]


def test_validation_rejects_bad_values(desk):
    with pytest.raises(Exception):
        make_job(desk, work_mode="sometimes")
    with pytest.raises(DeskError):
        desk.add_job(company="NoTitle")
    with pytest.raises(DeskError):
        desk.set_status(make_job(desk, company="X")["id"], "hired")


def test_status_flow_and_follow_up_rules(desk):
    job = make_job(desk)
    job = desk.set_status(job["id"], "drafting")
    assert job["next_action"] == "Send the application" and job["channel"] == "email"

    sent = date(2026, 10, 1)                          # a Thursday
    job = desk.set_status(job["id"], "applied", on=sent)
    assert job["applied_on"] == "2026-10-01" and job["stage_reached"] == "applied"
    assert job["next_action"] == "Follow up"
    assert job["next_action_due"] == "2026-10-12"     # 7 business days, skipping the weekend

    job = desk.log_follow_up(job["id"], on=date(2026, 10, 12))
    assert job["follow_ups_sent"] == 1 and job["next_action"] == "Second follow-up"
    job = desk.log_follow_up(job["id"], on=date(2026, 10, 21))
    assert job["next_action"].startswith("Close as no response")

    flags = rules.attention(desk._job(job["id"]), today=sent + timedelta(days=31))
    assert any(f["flag"] == "suggest_no_response" for f in flags)

    job = desk.set_status(job["id"], "no_response")
    assert job["status"] == "no_response" and job["outcome_side"] == "them" and job["next_action"] is None
    assert job["stage_reached"] == "applied" and job["closed_on"]
    job = desk.set_status(job["id"], "applied")       # reopen
    assert job["closed_on"] is None and job["applied_on"] == "2026-10-01"


def test_passing_a_job(desk):
    job = desk.set_status(make_job(desk)["id"], "passed", pass_reason="too_senior")
    assert job["status"] == "passed" and job["pass_reason"] == "too_senior"
    job = desk.set_status(job["id"], "shortlisted")
    assert job["pass_reason"] is None


def test_form_application_without_contact_skips_follow_ups(desk):
    job = make_job(desk, apply_method="form", apply_to=None)
    job = desk.set_status(job["id"], "applied", on=date(2026, 10, 1))
    assert job["channel"] == "form"
    assert job["next_action"].startswith("Close as no response")
    assert job["next_action_due"] == "2026-10-31"


def test_add_job_already_applied(desk):
    job = make_job(desk, status="applied", applied_on=date(2026, 9, 1))
    assert job["status"] == "applied" and job["applied_on"] == "2026-09-01"
    assert job["resume_version"] is None             # a past application doesn't get today's resume


def test_email_thread_sets_response_dates(desk):
    (desk.path.parent / "settings.json").write_text(json.dumps({"email_addresses": ["Me@Example.com"]}))
    job = desk.set_status(make_job(desk)["id"], "applied", on=date(2026, 10, 1))
    desk.record_thread(gmail_thread_id="t1", job_id=job["id"], subject="Application", messages=[
        {"gmail_message_id": "m1", "sent_at": "2026-10-01T10:00:00", "from_addr": "Me <me@example.com>",
         "to_addrs": "hr@acme.com", "body": "Hello"},
        {"gmail_message_id": "m2", "sent_at": "2026-10-04T09:00:00", "from_addr": "hr@acme.com", "body": "Thanks"},
    ])
    job = desk.get_job(job["id"])
    assert job["first_response_on"] == "2026-10-04" and job["last_contact_on"] == "2026-10-04"
    assert job["threads"][0]["last_direction"] == "in"
    assert any(f["flag"] == "reply_waiting" for f in job["flags"])
    desk.record_thread(gmail_thread_id="t1", messages=[{"gmail_message_id": "m2", "sent_at": "2026-10-04T09:00:00",
                                                        "from_addr": "hr@acme.com"}])
    assert desk.get_job(job["id"])["threads"][0]["message_count"] == 2
    desk.update_job(job["id"], next_action="Wait for their answer")
    assert not any(f["flag"] == "reply_waiting" for f in desk.get_job(job["id"])["flags"])


def test_gmail_utc_times_become_local_and_automated_mail_is_not_a_reply(desk):
    job = desk.set_status(make_job(desk)["id"], "applied", on=date(2026, 10, 1))
    desk.record_thread(gmail_thread_id="t9", job_id=job["id"], messages=[
        {"gmail_message_id": "a", "sent_at": "2026-10-01T20:30:00Z", "from_addr": "noreply@ats.com",
         "body": "Thanks for applying", "automated": True}])
    job = desk.get_job(job["id"])
    local = datetime(2026, 10, 1, 20, 30, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert job["threads"][0]["messages"][0]["sent_at"] == local.isoformat()   # stored in this PC's time zone
    assert job["first_response_on"] is None and not any(f["flag"] == "reply_waiting" for f in job["flags"])


def test_interview_moves_status_and_suggests_thank_you(desk):
    job = desk.set_status(make_job(desk)["id"], "applied", on=date(2026, 9, 20))
    job = desk.add_interview(job["id"], kind="technical", scheduled_at="2026-09-25T15:00", on=date(2026, 9, 22))
    assert job["status"] == "interviewing" and job["first_response_on"] == "2026-09-22"
    assert job["next_action"] == "Send a thank-you"
    job = desk.add_interview(job["id"], kind="take_home", scheduled_at="2026-09-28")
    assert job["status"] == "interviewing"


def test_search_filters_and_facets(desk):
    make_job(desk, title="Backend Engineer", company="Globex", description="Java and Spring Boot")
    valida = make_job(desk, title="LLM Engineer", company="Valida", city="Dubai", country="UAE", visa="yes")
    desk.set_status(valida["id"], "applied")
    res = desk.search_jobs(q="spring", with_facets=True)
    assert [j["company"] for j in res["jobs"]] == ["Globex"]
    res = desk.search_jobs(filters={"country": ["UAE"]}, with_facets=True)
    assert res["total"] == 1
    countries = {f["value"]: f["count"] for f in res["facets"]["country"]}
    assert countries == {"Pakistan": 1, "UAE": 1}        # a facet ignores its own filter
    assert desk.search_jobs(filters={"status": "applied"})["total"] == 1


def test_stats_funnel(desk):
    a = desk.set_status(make_job(desk)["id"], "applied", on=date(2026, 10, 1))
    b = desk.set_status(make_job(desk, company="B")["id"], "applied", on=date(2026, 10, 1))
    desk.set_status(b["id"], "screening", on=date(2026, 10, 5))
    desk.set_status(b["id"], "rejected", on=date(2026, 10, 8))       # rejected after a screen still counts
    desk.set_status(a["id"], "rejected", on=date(2026, 10, 3))
    s = desk.stats()
    assert s["funnel"] == {"applied": 2, "responded": 2, "interviewed": 1, "offers": 0}
    assert s["median_days_to_response"] == 3
    assert s["outcomes"] == {"rejected": 2}


def test_jobs_closing_soon_show_on_today(desk):
    make_job(desk, deadline=date.today() + timedelta(days=1))
    make_job(desk, company="Later", deadline=date.today() + timedelta(days=30))
    assert [j["company"] for j in desk.today()["closing_soon"]] == ["Acme"]


def test_query_is_read_only(desk):
    make_job(desk)
    assert desk.query("SELECT COUNT(*) AS n FROM jobs")["rows"][0]["n"] == 1
    with pytest.raises(Exception):
        desk.query("DELETE FROM jobs")


def test_v2_database_migrates_to_one_record_per_job(tmp_path):
    """A schema v2 database (separate applications table) merges into jobs, keeping history."""
    import sqlite3
    path = tmp_path / "v2.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT, website TEXT, linkedin TEXT, city TEXT,
            country TEXT, visa_notes TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE contacts (id INTEGER PRIMARY KEY, name TEXT, email TEXT, title TEXT, company_id INTEGER,
            linkedin TEXT, phone TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT, company_id INTEGER, city TEXT, country TEXT,
            work_mode TEXT, remote_region TEXT, employment_type TEXT, seniority TEXT, experience TEXT,
            salary_min REAL, salary_max REAL, salary_currency TEXT, salary_period TEXT, salary_text TEXT,
            visa TEXT, relocation TEXT, description TEXT, apply_method TEXT, apply_to TEXT, apply_notes TEXT,
            contact_id INTEGER, source TEXT, source_url TEXT, source_ref TEXT, posted_by TEXT, posted_on TEXT,
            found_on TEXT, deadline TEXT, posting_status TEXT, triage TEXT, pass_reason TEXT, priority INTEGER,
            fit_score INTEGER, fit_notes TEXT, tags TEXT, duplicate_of INTEGER, created_at TEXT, updated_at TEXT);
        CREATE TABLE applications (id INTEGER PRIMARY KEY, job_id INTEGER, stage TEXT, outcome TEXT, channel TEXT,
            contact_id INTEGER, applied_on TEXT, resume_version TEXT, next_action TEXT, next_action_due TEXT,
            last_contact_on TEXT, first_response_on TEXT, follow_ups_sent INTEGER, last_follow_up_on TEXT,
            closed_on TEXT, outcome_notes TEXT, notes TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE interviews (id INTEGER PRIMARY KEY, application_id INTEGER, kind TEXT, scheduled_at TEXT,
            duration_min INTEGER, with_whom TEXT, location TEXT, prep_notes TEXT, outcome_notes TEXT,
            thank_you_sent INTEGER, created_at TEXT, updated_at TEXT);
        CREATE TABLE email_threads (id INTEGER PRIMARY KEY, gmail_thread_id TEXT, application_id INTEGER,
            subject TEXT, participants TEXT, first_at TEXT, last_at TEXT, message_count INTEGER,
            last_direction TEXT, synced_at TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE email_messages (id INTEGER PRIMARY KEY, thread_id INTEGER, gmail_message_id TEXT,
            sent_at TEXT, direction TEXT, from_addr TEXT, to_addrs TEXT, cc_addrs TEXT, subject TEXT, body TEXT,
            attachments TEXT DEFAULT '[]', automated INTEGER DEFAULT 0);
        CREATE TABLE email_drafts (id INTEGER PRIMARY KEY, application_id INTEGER, kind TEXT, to_addr TEXT,
            cc_addr TEXT, subject TEXT, body TEXT, status TEXT, gmail_draft_id TEXT, attach_resume INTEGER,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE files (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id INTEGER, path TEXT, kind TEXT,
            caption TEXT, created_at TEXT);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, entity_type TEXT,
            entity_id INTEGER, job_id INTEGER, application_id INTEGER, action TEXT, summary TEXT, data TEXT);
        CREATE INDEX events_application ON events(application_id);
        INSERT INTO companies VALUES (1, 'Acme', NULL, NULL, NULL, NULL, NULL, NULL, 't', 't');
        INSERT INTO jobs (id, title, company_id, work_mode, employment_type, seniority, visa, relocation,
            apply_method, source, found_on, posting_status, triage, tags, created_at, updated_at)
        VALUES (1, 'AI Engineer', 1, 'onsite', 'unknown', 'unknown', 'unknown', 'unknown', 'email', 'linkedin',
                '2026-09-01', 'open', 'shortlisted', '[]', 't', 't'),
               (2, 'Data Engineer', 1, 'onsite', 'unknown', 'unknown', 'unknown', 'unknown', 'email', 'linkedin',
                '2026-09-01', 'open', 'new', '[]', 't', 't');
        INSERT INTO applications VALUES (7, 1, 'screening', 'rejected', 'email', NULL, '2026-09-02', NULL, NULL,
            NULL, '2026-09-05', '2026-09-05', 1, NULL, '2026-09-09', 'No', 'n', 't', 't');
        INSERT INTO interviews VALUES (1, 7, 'screen', '2026-09-05', NULL, NULL, NULL, NULL, NULL, 1, 't', 't');
        INSERT INTO email_drafts VALUES (1, 7, 'application', NULL, NULL, 'Hi', 'Body', 'sent', NULL, 1, 't', 't');
        INSERT INTO email_threads VALUES (1, 'g1', 7, 'Hi', NULL, NULL, NULL, 0, NULL, 't', 't', 't');
        INSERT INTO files VALUES (1, 'application', 7, 'applications/7/x.png', 'sent_email', NULL, 't');
        INSERT INTO events (at, actor, entity_type, entity_id, application_id, action, summary)
        VALUES ('t', 'me', 'application', 7, 7, 'closed', 'Closed: Rejected');
        PRAGMA user_version = 2;
    """)
    c.close()
    d = Desk(path=path)
    job = d.get_job(1)
    assert (job["status"], job["stage_reached"], job["applied_on"], job["follow_ups_sent"]) == \
           ("rejected", "screening", "2026-09-02", 1)
    assert len(job["interviews"]) == 1 and len(job["drafts"]) == 1 and len(job["threads"]) == 1
    assert job["files"][0]["path"] == "applications/7/x.png"
    assert job["timeline"][0]["summary"] == "Closed: Rejected"
    assert d.get_job(2)["status"] == "new"
    assert d.query("PRAGMA user_version")["rows"][0]["user_version"] == db.SCHEMA_VERSION
    assert job["starred"] == 0
    d.close()


def test_starring_jobs(desk):
    a = make_job(desk, priority=1)
    b = make_job(desk, company="B", priority=3)
    job = desk.star(b["id"])
    assert job["starred"] == 1 and job["timeline"][0]["summary"] == "Starred"
    assert [j["company"] for j in desk.search_jobs()["jobs"]] == ["B", "Acme"]      # starred first
    assert desk.search_jobs(filters={"starred": "1"})["total"] == 1
    assert desk.star(b["id"], False)["timeline"][0]["summary"] == "Removed the star"
    assert a["starred"] == 0


def test_resume_versions_come_from_settings(desk, tmp_path):
    assert desk.resume_versions() == [] and desk.current_resume_version() is None   # no settings.json
    folder = tmp_path / "Resume"
    (folder / "old").mkdir(parents=True)
    for name in ("general.pdf", "research.pdf", "old/2026-09-18_Ada_Lovelace_Resume_before_ATS_fixes.pdf",
                 "old/2026-06-04_Ada_Lovelace_CV.docx", "old/notes.txt"):
        (folder / name).write_bytes(b"%PDF")
    os.utime(folder / "general.pdf", (datetime(2026, 10, 6, 12).timestamp(),) * 2)
    (tmp_path / "settings.json").write_text(json.dumps({
        "name": "Ada Lovelace", "old_resumes": "Resume/old",                 # relative to settings.json
        "resumes": {"general": str(folder / "general.pdf"), "research": str(folder / "research.pdf"),
                    "missing": str(folder / "missing.pdf")}}))
    versions = {v["id"]: v for v in desk.resume_versions()}
    assert "2026-10-06 general" in versions and versions["2026-10-06 general"]["current"]
    assert {"2026-09-18 before-ats-fixes", "2026-06-04 cv-docx"} <= set(versions)
    assert versions["2026-09-18 before-ats-fixes"]["label"] == "2026-09-18 · before ATS fixes"
    assert not any("missing" in v or "notes" in v for v in versions)
    assert desk.current_resume_version() == "2026-10-06 general"              # the first one listed
    assert desk.current_resume_version("research").endswith(" research")
    job = desk.set_status(make_job(desk)["id"], "applied")
    assert job["resume_version"] == "2026-10-06 general"
