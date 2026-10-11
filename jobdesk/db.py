"""Connection and schema. Dates are 'YYYY-MM-DD'; timestamps are local
'YYYY-MM-DDTHH:MM:SS' (in this PC's time zone)."""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import paths
from .vocab import (
    ACTORS, APPLY_METHODS, CHANNELS, CONTACT_ROLES, DRAFT_KINDS, DRAFT_STATUSES, EMPLOYMENT_TYPES,
    FILE_ENTITIES, FILE_KINDS, INTERVIEW_KINDS, PASS_REASONS, POSTING_STATUSES, PRICING, PROJECT_CHANNELS,
    PROJECT_PASS_REASONS, PROJECT_SOURCES, PROJECT_STAGES, PROJECT_STATUSES,
    SALARY_PERIODS, SENIORITIES, SOURCES, STAGES, STATUSES, TRI_STATE, WORK_MODES, check,
)

SCHEMA_VERSION = 5

STAMPS = "created_at TEXT NOT NULL, updated_at TEXT NOT NULL"


# Tables whose shape changed in v3 are written as functions of their name, so the
# migration can build the new version next to the old one before swapping them.

def jobs_table(name="jobs"):
    return f"""
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    city TEXT,
    country TEXT,
    work_mode TEXT NOT NULL DEFAULT 'unknown' {check('work_mode', WORK_MODES)},
    remote_region TEXT,
    employment_type TEXT NOT NULL DEFAULT 'unknown' {check('employment_type', EMPLOYMENT_TYPES)},
    seniority TEXT NOT NULL DEFAULT 'unknown' {check('seniority', SENIORITIES)},
    experience TEXT,
    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT,
    salary_period TEXT {check('salary_period', SALARY_PERIODS, nullable=True)},
    salary_text TEXT,
    visa TEXT NOT NULL DEFAULT 'unknown' {check('visa', TRI_STATE)},
    relocation TEXT NOT NULL DEFAULT 'unknown' {check('relocation', TRI_STATE)},
    description TEXT,
    apply_method TEXT NOT NULL DEFAULT 'unknown' {check('apply_method', APPLY_METHODS)},
    apply_to TEXT,
    apply_notes TEXT,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'other' {check('source', SOURCES)},
    source_url TEXT,
    source_ref TEXT,
    posted_by TEXT,
    posted_on TEXT,
    found_on TEXT NOT NULL,
    deadline TEXT,
    posting_status TEXT NOT NULL DEFAULT 'open' {check('posting_status', POSTING_STATUSES)},
    priority INTEGER CHECK (priority BETWEEN 1 AND 4 OR priority IS NULL),
    starred INTEGER NOT NULL DEFAULT 0,           -- the user's own marker, set by hand
    fit_score INTEGER CHECK (fit_score BETWEEN 1 AND 5 OR fit_score IS NULL),
    fit_notes TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    duplicate_of INTEGER REFERENCES jobs(id) ON DELETE SET NULL,

    -- where the pursuit stands (see vocab.STATUSES)
    status TEXT NOT NULL DEFAULT 'new' {check('status', STATUSES)},
    stage_reached TEXT {check('stage_reached', STAGES, nullable=True)},
    pass_reason TEXT {check('pass_reason', PASS_REASONS, nullable=True)},
    channel TEXT {check('channel', CHANNELS, nullable=True)},
    applied_on TEXT,
    resume_version TEXT,
    next_action TEXT,
    next_action_due TEXT,
    last_contact_on TEXT,
    first_response_on TEXT,
    follow_ups_sent INTEGER NOT NULL DEFAULT 0,
    last_follow_up_on TEXT,
    closed_on TEXT,
    outcome_notes TEXT,
    notes TEXT,
    {STAMPS}
);"""


def interviews_table(name="interviews"):
    return f"""
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'other' {check('kind', INTERVIEW_KINDS)},
    scheduled_at TEXT,
    duration_min INTEGER,
    with_whom TEXT,
    location TEXT,
    prep_notes TEXT,
    outcome_notes TEXT,
    thank_you_sent INTEGER NOT NULL DEFAULT 0,
    {STAMPS}
);"""


def threads_table(name="email_threads"):
    return f"""
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    gmail_thread_id TEXT UNIQUE,
    job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,   -- a thread belongs to a job or a project
    subject TEXT,
    participants TEXT,
    first_at TEXT,
    last_at TEXT,
    message_count INTEGER NOT NULL DEFAULT 0,
    last_direction TEXT {check('last_direction', ('in', 'out'), nullable=True)},
    synced_at TEXT NOT NULL,
    {STAMPS}
);"""


def drafts_table(name="email_drafts"):
    return f"""
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'application' {check('kind', DRAFT_KINDS)},
    to_addr TEXT,
    cc_addr TEXT,
    subject TEXT,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' {check('status', DRAFT_STATUSES)},
    gmail_draft_id TEXT,
    attach_resume INTEGER NOT NULL DEFAULT 1,
    {STAMPS},
    CHECK ((job_id IS NULL) != (project_id IS NULL))        -- on a job or on a project, never both
);"""


def files_table(name="files"):
    return f"""
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL {check('entity_type', FILE_ENTITIES)},
    entity_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'other' {check('kind', FILE_KINDS)},
    caption TEXT,
    created_at TEXT NOT NULL
);"""


def projects_table(name="projects"):
    """Client work (v5): one record per opportunity, shaped like a job."""
    return f"""
CREATE TABLE {name} (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    description TEXT,                    -- what they need: the brief or the posting, as Markdown
    source TEXT NOT NULL DEFAULT 'other' {check('source', PROJECT_SOURCES)},
    source_url TEXT,
    source_ref TEXT,                     -- the listing's id where it came from, e.g. an Upwork job id
    pricing TEXT NOT NULL DEFAULT 'unknown' {check('pricing', PRICING)},
    budget_text TEXT,                    -- their budget as they put it, e.g. '$15-40/hr'
    value REAL,                          -- your price: the fixed fee, hourly rate or monthly retainer
    currency TEXT,
    found_on TEXT NOT NULL,
    priority INTEGER CHECK (priority BETWEEN 1 AND 4 OR priority IS NULL),
    starred INTEGER NOT NULL DEFAULT 0,
    fit_notes TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    follow_on_of INTEGER REFERENCES {name}(id) ON DELETE SET NULL,   -- more work from an earlier project

    -- where the pursuit stands (see vocab.PROJECT_STATUSES)
    status TEXT NOT NULL DEFAULT 'lead' {check('status', PROJECT_STATUSES)},
    stage_reached TEXT {check('stage_reached', PROJECT_STAGES, nullable=True)},
    pass_reason TEXT {check('pass_reason', PROJECT_PASS_REASONS, nullable=True)},
    channel TEXT {check('channel', PROJECT_CHANNELS, nullable=True)},
    pitched_on TEXT,                     -- the first pitch or proposal went out
    next_action TEXT,
    next_action_due TEXT,
    last_contact_on TEXT,
    first_response_on TEXT,
    follow_ups_sent INTEGER NOT NULL DEFAULT 0,
    last_follow_up_on TEXT,
    closed_on TEXT,
    outcome_notes TEXT,
    notes TEXT,
    {STAMPS}
);"""


INDEXES = """
CREATE UNIQUE INDEX jobs_source_ref ON jobs(source, source_ref) WHERE source_ref IS NOT NULL;
CREATE INDEX jobs_company ON jobs(company_id);
CREATE INDEX jobs_status ON jobs(status);
CREATE INDEX interviews_job ON interviews(job_id);
CREATE INDEX email_threads_job ON email_threads(job_id);
CREATE INDEX email_drafts_job ON email_drafts(job_id);
CREATE INDEX files_entity ON files(entity_type, entity_id);
"""

# Kept apart from INDEXES, which the v3 migration replays before these tables and columns exist.
INDEXES_V5 = (
    "CREATE UNIQUE INDEX IF NOT EXISTS projects_source_ref ON projects(source, source_ref) WHERE source_ref IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS projects_company ON projects(company_id)",
    "CREATE INDEX IF NOT EXISTS projects_status ON projects(status)",
    "CREATE INDEX IF NOT EXISTS email_threads_project ON email_threads(project_id)",
    "CREATE INDEX IF NOT EXISTS email_drafts_project ON email_drafts(project_id)",
    "CREATE INDEX IF NOT EXISTS events_project ON events(project_id)",
)

SCHEMA = f"""
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    website TEXT,
    linkedin TEXT,
    city TEXT,
    country TEXT,
    visa_notes TEXT,
    notes TEXT,
    {STAMPS}
);

CREATE TABLE contacts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT COLLATE NOCASE,
    title TEXT,
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    linkedin TEXT,
    phone TEXT,
    role TEXT {check('role', CONTACT_ROLES, nullable=True)},   -- who they are to you
    notes TEXT,
    {STAMPS}
);
CREATE UNIQUE INDEX contacts_email ON contacts(email) WHERE email IS NOT NULL;
{jobs_table()}
{projects_table()}
{interviews_table()}
{threads_table()}

CREATE TABLE email_messages (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES email_threads(id) ON DELETE CASCADE,
    gmail_message_id TEXT UNIQUE,
    sent_at TEXT NOT NULL,
    direction TEXT NOT NULL {check('direction', ('in', 'out'))},
    from_addr TEXT,
    to_addrs TEXT,
    cc_addrs TEXT,
    subject TEXT,
    body TEXT,
    attachments TEXT NOT NULL DEFAULT '[]',
    automated INTEGER NOT NULL DEFAULT 0   -- confirmations and notifications: not a reply from a person
);
{drafts_table()}
{files_table()}

-- Every change, by whom. Doubles as each job's and project's timeline (notes are events with
-- action 'note') and as the feed the dashboard listens to for live updates.
-- application_id only appears on events from schema v1-2, when applications had their own table.
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL {check('actor', ACTORS)},
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    job_id INTEGER,
    application_id INTEGER,
    action TEXT NOT NULL,
    summary TEXT NOT NULL,
    data TEXT,
    project_id INTEGER
);
CREATE INDEX events_job ON events(job_id);
{INDEXES}
{';'.join(INDEXES_V5)};
"""

# v2 -> v3: applications merge into jobs. Each job had at most one application.
MIGRATE_2_TO_3 = f"""
BEGIN;
{jobs_table('jobs_v3')}
INSERT INTO jobs_v3 (
    id, title, company_id, city, country, work_mode, remote_region, employment_type, seniority, experience,
    salary_min, salary_max, salary_currency, salary_period, salary_text, visa, relocation, description,
    apply_method, apply_to, apply_notes, contact_id, source, source_url, source_ref, posted_by, posted_on,
    found_on, deadline, posting_status, priority, fit_score, fit_notes, tags, duplicate_of,
    status, stage_reached, pass_reason, channel, applied_on, resume_version, next_action, next_action_due,
    last_contact_on, first_response_on, follow_ups_sent, last_follow_up_on, closed_on, outcome_notes, notes,
    created_at, updated_at)
SELECT
    j.id, j.title, j.company_id, j.city, j.country, j.work_mode, j.remote_region, j.employment_type, j.seniority,
    j.experience, j.salary_min, j.salary_max, j.salary_currency, j.salary_period, j.salary_text, j.visa,
    j.relocation, j.description, j.apply_method, j.apply_to, j.apply_notes, COALESCE(a.contact_id, j.contact_id),
    j.source, j.source_url, j.source_ref, j.posted_by, j.posted_on, j.found_on, j.deadline, j.posting_status,
    j.priority, j.fit_score, j.fit_notes, j.tags, j.duplicate_of,
    CASE WHEN a.id IS NULL THEN j.triage WHEN a.outcome IS NOT NULL THEN a.outcome ELSE a.stage END,
    a.stage, j.pass_reason, a.channel, a.applied_on, a.resume_version, a.next_action, a.next_action_due,
    a.last_contact_on, a.first_response_on, COALESCE(a.follow_ups_sent, 0), a.last_follow_up_on, a.closed_on,
    a.outcome_notes, a.notes, j.created_at, MAX(j.updated_at, COALESCE(a.updated_at, j.updated_at))
FROM jobs j LEFT JOIN applications a ON a.job_id = j.id;

{interviews_table('interviews_v3')}
INSERT INTO interviews_v3 (id, job_id, kind, scheduled_at, duration_min, with_whom, location, prep_notes,
                           outcome_notes, thank_you_sent, created_at, updated_at)
SELECT i.id, a.job_id, i.kind, i.scheduled_at, i.duration_min, i.with_whom, i.location, i.prep_notes,
       i.outcome_notes, i.thank_you_sent, i.created_at, i.updated_at
FROM interviews i JOIN applications a ON a.id = i.application_id;

{threads_table('email_threads_v3')}
INSERT INTO email_threads_v3 (id, gmail_thread_id, job_id, subject, participants, first_at, last_at, message_count,
                              last_direction, synced_at, created_at, updated_at)
SELECT t.id, t.gmail_thread_id, (SELECT job_id FROM applications a WHERE a.id = t.application_id), t.subject,
       t.participants, t.first_at, t.last_at, t.message_count, t.last_direction, t.synced_at, t.created_at,
       t.updated_at
FROM email_threads t;

{drafts_table('email_drafts_v3')}
INSERT INTO email_drafts_v3 (id, job_id, kind, to_addr, cc_addr, subject, body, status, gmail_draft_id,
                             attach_resume, created_at, updated_at)
SELECT d.id, a.job_id, d.kind, d.to_addr, d.cc_addr, d.subject, d.body, d.status, d.gmail_draft_id,
       d.attach_resume, d.created_at, d.updated_at
FROM email_drafts d JOIN applications a ON a.id = d.application_id;

{files_table('files_v3')}
INSERT INTO files_v3 (id, entity_type, entity_id, path, kind, caption, created_at)
SELECT f.id,
       CASE WHEN f.entity_type = 'application' THEN 'job' ELSE f.entity_type END,
       CASE WHEN f.entity_type = 'application'
            THEN (SELECT job_id FROM applications a WHERE a.id = f.entity_id) ELSE f.entity_id END,
       f.path, f.kind, f.caption, f.created_at
FROM files f;

UPDATE events SET job_id = (SELECT job_id FROM applications a WHERE a.id = events.application_id)
WHERE job_id IS NULL AND application_id IS NOT NULL;

DROP TABLE interviews;
DROP TABLE email_drafts;
DROP TABLE email_threads;
DROP TABLE files;
DROP TABLE applications;
DROP TABLE jobs;
ALTER TABLE jobs_v3 RENAME TO jobs;
ALTER TABLE interviews_v3 RENAME TO interviews;
ALTER TABLE email_threads_v3 RENAME TO email_threads;
ALTER TABLE email_drafts_v3 RENAME TO email_drafts;
ALTER TABLE files_v3 RENAME TO files;
DROP INDEX IF EXISTS events_application;
{INDEXES}
PRAGMA user_version = 3;
COMMIT;
"""


def _add_column(conn, table, column, definition):
    """ALTER TABLE ADD COLUMN, skipped when the column is already there (a table the v3 migration
    built from today's definition has it from the start)."""
    if column not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _rebuild(conn, table, definition):
    """Recreate `table` from its current definition, keeping every row and the columns both share.
    For constraint changes, which SQLite can't ALTER."""
    old = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    conn.execute(definition(f"{table}_new"))
    keep = ", ".join(c for c in (r[1] for r in conn.execute(f"PRAGMA table_info({table}_new)")) if c in old)
    conn.execute(f"INSERT INTO {table}_new ({keep}) SELECT {keep} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")


def _migrate_4_to_5(conn):
    """v5 adds client work: the projects table; a project_id on email threads, drafts and events;
    'project' as a file owner; a role on contacts. Drafts and files are rebuilt because their
    constraints change. Runs as one transaction, and only if no other process got there first."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] != 4:
            conn.execute("ROLLBACK")
            return
        conn.execute(projects_table())
        _add_column(conn, "contacts", "role", f"TEXT {check('role', CONTACT_ROLES, nullable=True)}")
        _add_column(conn, "email_threads", "project_id", "INTEGER REFERENCES projects(id) ON DELETE SET NULL")
        _add_column(conn, "events", "project_id", "INTEGER")
        _rebuild(conn, "email_drafts", drafts_table)
        _rebuild(conn, "files", files_table)
        conn.execute("CREATE INDEX IF NOT EXISTS email_drafts_job ON email_drafts(job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS files_entity ON files(entity_type, entity_id)")
        for sql in INDEXES_V5:
            conn.execute(sql)
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"Foreign key problems after the v5 migration: {[tuple(r) for r in bad][:5]}")
        conn.execute("PRAGMA user_version = 5")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def now():
    return datetime.now().replace(microsecond=0).isoformat()


def today():
    return datetime.now().date().isoformat()


def connect(path=None):
    path = Path(path or paths.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # explicit BEGIN/COMMIT
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    # WAL lets the dashboard read while Claude or the CLI writes from another process.
    conn.execute("PRAGMA journal_mode = WAL")
    ensure_schema(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version == 0:
        conn.executescript("BEGIN;" + SCHEMA + f"PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")
        return
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Database is at schema v{version}, code expects v{SCHEMA_VERSION}")
    # One step per version, with a backup in data/backups/ first. Foreign keys are off
    # here (connect turns them on afterwards) because tables get rebuilt.
    backup_path(conn, f"before-v{SCHEMA_VERSION}")
    if version == 1:
        conn.executescript("""BEGIN;
            ALTER TABLE email_messages ADD COLUMN automated INTEGER NOT NULL DEFAULT 0;
            PRAGMA user_version = 2; COMMIT;""")
        version = 2
    if version == 2:
        extra = conn.execute("SELECT COUNT(*) FROM (SELECT job_id FROM applications GROUP BY job_id "
                             "HAVING COUNT(*) > 1)").fetchone()[0]
        if extra:
            raise RuntimeError(f"{extra} job(s) have more than one application; merge them by hand first")
        conn.executescript(MIGRATE_2_TO_3)
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"Foreign key problems after the v3 migration: {[tuple(r) for r in bad][:5]}")
        version = 3
    if version == 3:
        # The v3 rebuild above already creates jobs from today's definition, starred included.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
        try:
            if "starred" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError as exc:      # another process got there first
            if "duplicate column" not in str(exc):
                raise
        conn.execute("PRAGMA user_version = 4")
        version = 4
    if version == 4:
        _migrate_4_to_5(conn)


def backup_path(conn, label):
    """Copy the database `conn` is open on into a backups/ folder next to it."""
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    folder = Path(db_file).parent / "backups" if db_file else paths.BACKUP_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{label}.db"
    dst = sqlite3.connect(target)
    conn.backup(dst)
    dst.close()
    return target


def backup(label="manual"):
    """Copy the live database (safely, even mid-write) into data/backups/."""
    src = connect()
    target = backup_path(src, label)
    src.close()
    return target


def copy_into_files(source, subdir, name=None, files_dir=None):
    """Copy a file into <files_dir>/<subdir>/ and return its path relative to files_dir
    (default data/files). Never overwrites: a clashing name gets a -2, -3... suffix."""
    source = Path(source)
    files_dir = Path(files_dir or paths.FILES_DIR)
    dest_dir = files_dir / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or source.name)
    n = 2
    while dest.exists() and dest.resolve() != source.resolve():
        dest = dest_dir / f"{Path(name or source.name).stem}-{n}{source.suffix}"
        n += 1
    if not dest.exists():
        shutil.copy2(source, dest)
    return dest.relative_to(files_dir).as_posix()
