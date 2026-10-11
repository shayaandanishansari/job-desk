"""Client work: projects, and what they share with jobs (companies, contacts, email, files, Today)."""

import json
from datetime import date, timedelta

import pytest

from jobdesk import db, rules
from jobdesk.core import Desk, DeskError, PossibleDuplicate


@pytest.fixture
def desk(tmp_path):
    d = Desk(actor="claude", path=tmp_path / "t.db")
    yield d
    d.close()


def make_project(desk, **kw):
    fields = dict(title="Voice receptionist", company="Acme Clinic", source="outreach",
                  contact={"name": "Dana Cho", "email": "dana@acmeclinic.com", "role": "decision_maker"})
    fields.update(kw)
    return desk.add_project(**fields)


def test_pitch_flow_and_follow_up_rules(desk):
    p = make_project(desk)
    assert p["status"] == "lead" and p["kind"] == "project" and p["stage_reached"] is None
    assert p["contact"]["role"] == "decision_maker"

    p = desk.set_project_status(p["id"], "drafting")
    assert p["next_action"] == "Send the pitch" and p["channel"] == "email"   # there's an address to write to

    sent = date(2026, 10, 1)                              # a Thursday
    p = desk.set_project_status(p["id"], "pitched", on=sent)
    assert p["pitched_on"] == "2026-10-01" and p["stage_reached"] == "pitched"
    assert (p["next_action"], p["next_action_due"]) == ("Follow up", "2026-10-06")          # 3 business days

    p = desk.log_project_follow_up(p["id"], on=date(2026, 10, 6))
    assert (p["next_action"], p["next_action_due"]) == ("Second follow-up", "2026-10-13")   # 5 more
    p = desk.log_project_follow_up(p["id"], on=date(2026, 10, 13))
    assert p["next_action"].startswith("Close as no response") and p["next_action_due"] == "2026-10-22"
    flags = rules.project_attention(desk._project(p["id"]), today=sent + timedelta(days=22))
    assert any(f["flag"] == "suggest_no_response" for f in flags)

    p = desk.set_project_status(p["id"], "talking", on=date(2026, 10, 15))
    assert p["first_response_on"] == "2026-10-15"
    assert (p["next_action"], p["next_action_due"]) == ("Follow up if there's no news", "2026-10-20")
    desk.set_project_status(p["id"], "proposal", on=date(2026, 10, 16))
    p = desk.set_project_status(p["id"], "won", on=date(2026, 10, 20), value=1500)
    assert p["status"] == "won" and p["outcome_side"] == "me" and p["closed_on"] == "2026-10-20"
    assert p["next_action"] is None and p["stage_reached"] == "proposal" and p["value"] == 1500
    assert p["timeline"][0]["summary"] == "Won on 2026-10-20, price 1500"

    p = desk.set_project_status(p["id"], "negotiating")                # reopen
    assert p["closed_on"] is None and p["timeline"][0]["summary"].startswith("Reopened")


def test_upwork_proposal_waits_instead_of_following_up(desk):
    p = make_project(desk, title="Retell agent for a dental group", company=None, contact=None, source="upwork",
                     source_ref="022108", status="drafting")
    assert p["next_action"] == "Submit the proposal" and p["channel"] == "upwork"
    p = desk.set_project_status(p["id"], "pitched", on=date(2026, 10, 1))
    assert p["next_action"].startswith("Close as no response") and p["next_action_due"] == "2026-10-15"
    flags = rules.project_attention(desk._project(p["id"]), today=date(2026, 10, 16))
    assert any(f["flag"] == "suggest_no_response" for f in flags)
    with pytest.raises(PossibleDuplicate):                              # the same Upwork listing, never twice
        make_project(desk, title="Something else", source="upwork", source_ref="022108", force=True)


def test_validation(desk):
    with pytest.raises(DeskError):
        desk.add_project(company="No title")
    with pytest.raises(Exception):
        make_project(desk, pricing="per vibe")
    p = make_project(desk)
    with pytest.raises(DeskError):
        desk.set_project_status(p["id"], "applied")                    # a job status
    with pytest.raises(DeskError):
        desk.set_project_status(p["id"], "passed", pass_reason="too_senior")
    with pytest.raises(PossibleDuplicate):
        make_project(desk, title="Voice receptionist (phase 1)")      # same company, similar title
    p = desk.set_project_status(p["id"], "passed", pass_reason="budget_too_low")
    assert p["pass_reason"] == "budget_too_low" and p["timeline"][0]["summary"] == "Passed: Budget too low"


def test_people_and_companies_are_shared(desk):
    job = desk.add_job(title="AI Engineer", company="Acme Clinic", contact={"email": "DANA@acmeclinic.com"})
    p = make_project(desk)
    assert job["contact_id"] == p["contact_id"]                        # one person, matched on email
    contact = next(c for c in desk.list_contacts() if c["id"] == p["contact_id"])
    assert (contact["role"], contact["job_count"], contact["project_count"]) == ("decision_maker", 1, 1)
    company = desk.get_company(p["company_id"])
    assert [j["id"] for j in company["jobs"]] == [job["id"]] and [x["id"] for x in company["projects"]] == [p["id"]]
    assert next(c for c in desk.list_companies() if c["name"] == "Acme Clinic")["project_count"] == 1
    assert desk.get_job(job["id"])["company_projects"][0]["id"] == p["id"]
    assert desk.get_project(p["id"])["company_jobs"][0]["id"] == job["id"]


def test_email_drafts_notes_and_files_on_projects(desk, tmp_path):
    (desk.path.parent / "settings.json").write_text(json.dumps({"email_addresses": ["me@example.com"]}))
    p = desk.set_project_status(make_project(desk)["id"], "pitched", on=date(2026, 10, 1))

    draft = desk.save_draft(project_id=p["id"], body="Hi Dana", subject="Missed calls")
    assert (draft["kind"], draft["attach_resume"], draft["job_id"]) == ("pitch", 0, None)
    assert any(d["project_id"] == p["id"] for d in desk.today()["drafts"])
    with pytest.raises(DeskError):
        desk.save_draft(body="Nowhere to go")
    desk.update_draft(draft["id"], status="sent")

    desk.record_thread(gmail_thread_id="g1", project_id=p["id"], messages=[
        {"gmail_message_id": "m1", "sent_at": "2026-10-01T10:00:00", "from_addr": "me@example.com", "body": "Hi"},
        {"gmail_message_id": "m2", "sent_at": "2026-10-03T09:00:00", "from_addr": "dana@acmeclinic.com", "body": "Tell me more"},
    ])
    p = desk.get_project(p["id"])
    assert p["first_response_on"] == "2026-10-03" and p["last_contact_on"] == "2026-10-03"
    assert any(f["flag"] == "reply_waiting" for f in p["flags"]) and len(p["threads"]) == 1
    assert desk.list_threads()[0]["project_title"] == "Voice receptionist"

    desk.add_note("project", p["id"], "Prefers WhatsApp")
    shot = tmp_path / "brief.png"
    shot.write_bytes(b"png")
    desk.attach_file("project", p["id"], shot, kind="document")
    p = desk.get_project(p["id"])
    assert p["files"][0]["path"].startswith("projects/") and p["file_count"] == 1
    assert {"Prefers WhatsApp", "Email draft marked sent"} <= {e["summary"] for e in p["timeline"]}
    assert not any(f["flag"] == "reply_waiting" for f in p["flags"])  # a note counts as acting on it

    job = desk.add_job(title="AI Engineer", company="Acme Clinic")
    thread = desk.link_thread(p["threads"][0]["id"], job_id=job["id"])  # moves the thread over
    assert (thread["job_id"], thread["project_id"]) == (job["id"], None)
    assert desk.get_project(p["id"])["threads"] == []


def test_today_mixes_jobs_and_projects(desk):
    long_ago = date.today() - timedelta(days=20)
    job = desk.add_job(title="AI Engineer", company="Acme", apply_method="email", apply_to="hr@acme.com")
    desk.set_status(job["id"], "applied", on=long_ago)
    p = desk.set_project_status(make_project(desk)["id"], "pitched", on=long_ago)
    make_project(desk, title="Chat agent", company="Globex")                  # a lead
    t = desk.today()
    assert {(x["kind"], x["id"]) for x in t["due"]} == {("job", job["id"]), ("project", p["id"])}
    assert t["leads"]["total"] == 1 and t["week"]["open"] == 2
    o = desk.overview()
    assert any(d.get("project") == "Voice receptionist (Acme Clinic)" for d in o["due_now"])
    assert o["projects"] == 2 and o["new_leads"] == 1


def test_search_and_facets(desk):
    make_project(desk, description="They miss half their calls", pricing="fixed")
    desk.add_project(title="Shopify cart agent", company="Globex", source="upwork", pricing="hourly")
    res = desk.search_projects(q="calls", with_facets=True)
    assert [p["company"] for p in res["projects"]] == ["Acme Clinic"]
    res = desk.search_projects(filters={"source": ["upwork"]}, with_facets=True)
    assert res["total"] == 1
    assert {f["value"]: f["count"] for f in res["facets"]["source"]} == {"outreach": 1, "upwork": 1}


def test_project_stats(desk):
    on = date(2026, 10, 1)
    won = desk.set_project_status(make_project(desk)["id"], "pitched", on=on)
    desk.update_project(won["id"], pricing="fixed", currency="usd")
    desk.set_project_status(won["id"], "talking", on=date(2026, 10, 3))
    desk.set_project_status(won["id"], "won", on=date(2026, 10, 9), value=1500)
    talking = desk.add_project(title="Chat agent", company="Globex", source="upwork", pricing="hourly",
                               value=30, currency="USD", status="pitched", status_on=on)
    desk.set_project_status(talking["id"], "talking", on=date(2026, 10, 5))
    desk.add_project(title="Intake bot", company="Initech", status="pitched", status_on=on)
    make_project(desk, title="Booking agent", company="Umbrella")                 # never pitched
    s = desk.project_stats()
    assert s["funnel"] == {"pitched": 3, "replied": 2, "proposals": 1, "won": 1}
    assert s["median_days_to_reply"] == 3 and s["outcomes"] == {"won": 1}
    assert s["won_value"] == [{"currency": "USD", "pricing": "fixed", "count": 1, "total": 1500, "average": 1500}]
    assert s["open_value"][0]["pricing"] == "hourly" and s["open_value"][0]["average"] == 30
    assert s["pipeline"]["talking"] == 1 and s["projects_by_status"]["lead"] == 1
    assert {r["value"]: r["pitched"] for r in s["by_source"]} == {"outreach": 1, "upwork": 1, "other": 1}


def test_follow_on_work_links_back(desk):
    first = make_project(desk)
    second = desk.add_project(title="Voice receptionist, phase 2", company="Acme Clinic", follow_on_of=first["id"],
                              force=True)
    assert desk.get_project(second["id"])["follow_on_from"]["id"] == first["id"]
    assert [p["id"] for p in desk.get_project(first["id"])["follow_ons"]] == [second["id"]]
    with pytest.raises(DeskError):
        desk.update_project(first["id"], follow_on_of=first["id"])
    desk.delete_project(first["id"])
    assert desk.get_project(second["id"])["follow_on_of"] is None


def test_v4_database_migrates_to_v5(tmp_path):
    """A v4 database (no projects) gains them, keeping its drafts, files and threads."""
    import sqlite3
    path = tmp_path / "v4.db"
    c = sqlite3.connect(path)
    c.executescript(f"""
        CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, website TEXT,
            linkedin TEXT, city TEXT, country TEXT, visa_notes TEXT, notes TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE contacts (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT COLLATE NOCASE, title TEXT,
            company_id INTEGER, linkedin TEXT, phone TEXT, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        {db.jobs_table()}
        {db.interviews_table()}
        CREATE TABLE email_threads (id INTEGER PRIMARY KEY, gmail_thread_id TEXT UNIQUE, job_id INTEGER, subject TEXT,
            participants TEXT, first_at TEXT, last_at TEXT, message_count INTEGER NOT NULL DEFAULT 0,
            last_direction TEXT, synced_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE email_messages (id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL, gmail_message_id TEXT UNIQUE,
            sent_at TEXT NOT NULL, direction TEXT NOT NULL, from_addr TEXT, to_addrs TEXT, cc_addrs TEXT, subject TEXT,
            body TEXT, attachments TEXT NOT NULL DEFAULT '[]', automated INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE email_drafts (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'application', to_addr TEXT, cc_addr TEXT, subject TEXT, body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', gmail_draft_id TEXT, attach_resume INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE files (id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL CHECK (entity_type IN ('job', 'company')),
            entity_id INTEGER NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'other', caption TEXT,
            created_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id INTEGER, job_id INTEGER, application_id INTEGER, action TEXT NOT NULL,
            summary TEXT NOT NULL, data TEXT);
        INSERT INTO companies VALUES (1, 'Acme', NULL, NULL, NULL, NULL, NULL, NULL, 't', 't');
        INSERT INTO jobs (id, title, company_id, found_on, created_at, updated_at) VALUES (1, 'AI Engineer', 1, '2026-10-01', 't', 't');
        INSERT INTO email_drafts (id, job_id, subject, body, created_at, updated_at) VALUES (1, 1, 'Hi', 'Body', 't', 't');
        INSERT INTO email_threads (id, gmail_thread_id, job_id, subject, synced_at, created_at, updated_at)
            VALUES (1, 'g1', 1, 'Hi', 't', 't', 't');
        INSERT INTO files VALUES (1, 'job', 1, 'jobs/1/x.png', 'screenshot', NULL, 't');
        INSERT INTO events (at, actor, entity_type, entity_id, job_id, action, summary)
            VALUES ('t', 'me', 'job', 1, 1, 'created', 'Added job: AI Engineer at Acme');
        PRAGMA user_version = 4;
    """)
    c.close()
    d = Desk(path=path)
    job = d.get_job(1)
    assert len(job["drafts"]) == 1 and len(job["threads"]) == 1 and job["files"][0]["path"] == "jobs/1/x.png"
    assert job["timeline"][0]["summary"] == "Added job: AI Engineer at Acme"
    assert d.query("PRAGMA user_version")["rows"][0]["user_version"] == db.SCHEMA_VERSION == 5
    assert list((tmp_path / "backups").glob("*_before-v5.db"))
    p = d.add_project(title="Voice agent", company="Acme", contact={"name": "Sam", "role": "founder"})
    d.save_draft(project_id=p["id"], body="Hello")
    assert d.get_company(1)["projects"][0]["id"] == p["id"] and d.get_project(p["id"])["drafts"]
    d.close()
