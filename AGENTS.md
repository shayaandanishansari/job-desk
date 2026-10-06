# AGENTS.md

Job Desk: every job one person is considering or has applied to, one record per job, in one database, with a dashboard they read and an MCP server Claude works through. Their own details (name, email addresses, resumes, email guide) are in `settings.json` next to the database.

**If `AGENTS.local.md` exists, read it too.** It holds the owner's own rules and isn't in git.

## What's here

| Path | What it is |
|---|---|
| `data/jobdesk.db` | The database (SQLite). The only source of truth. Not in git. JobDesk.exe keeps its data in `%APPDATA%\JobDesk` instead; `JOBDESK_HOME` moves it anywhere. |
| `data/settings.json` | The owner's details; see `jobdesk/settings.py` for the keys. Not in git. |
| `data/files/` | Screenshots and files attached to jobs. Not in git. |
| `data/backups/` | Copies of the database: `python -m jobdesk backup <label>`, and automatic ones before migrations. |
| `jobdesk/` | Python package. `core.py` is the only code that writes to the database. `rules.py` holds the follow-up rules. `vocab.py` every fixed list of values, including the statuses. `server.py` is the dashboard API, `mcp_server.py` the MCP server, `launcher.py` what JobDesk.exe does when it's double-clicked. |
| `web/` | The dashboard: React + Vite + TypeScript, light mode. Today, Jobs (with filters, a Starred toggle and All / Not applied / In progress / Closed views), Stats, People. |
| `packaging/` | JobDesk.exe: the PyInstaller spec, its entry point, the icon and `build.ps1`. |
| `.github/workflows/` | Tests on every push; a tag `v*` builds the Windows zip and publishes a release. |
| `tests/` | `python -m pytest tests` |

## Running it

`start.ps1` starts both dev servers (skipping any already running) and opens the dashboard at http://127.0.0.1:5180. By hand:

```powershell
python -m jobdesk serve --reload      # API on 127.0.0.1:8780, restarts when jobdesk/ changes (watchfiles)
cd web; npx vite                      # dashboard on 127.0.0.1:5180, hot-reloads when web/src changes
```

`npm run build` in `web/` makes `web/dist`, which `python -m jobdesk serve` then serves on its own at http://127.0.0.1:8780. It runs on this PC only (127.0.0.1), with no login.

Changes reach open dashboards within a second, whoever makes them: the server watches the `events` table (and SQLite's `data_version` for edits made outside the code) and pushes them over `/api/stream`. Changes made by Claude show as a toast naming Claude.

## Working on the data

Use the MCP server (`jobdesk` in `.mcp.json`). Its tools validate every write and log it to the timeline. Start with `overview`. If MCP isn't loaded, use `core.Desk(actor="claude")` from Python; it's the same code. Never write to the database with raw SQL. `query_db` is read-only on purpose.

- **Adding a job** (from a screenshot, pasted text or a link): `search_jobs` first, then `add_job`. Copy the post's text word for word into `description` as Markdown. Fill only what the post says: visa and relocation stay `unknown` unless stated. Work out `posted_on` from LinkedIn's relative labels ("5d"). Save the screenshot with `attach_file`. Put your reading of the fit in `fit_notes`. `add_job` refuses a likely duplicate (same company and similar title) unless `force=True`. Use that only for genuinely different listings, such as a company's several "AI Engineer" posts.
- **One record per job.** The job's `status` says where it stands: `new → shortlisted` (or `passed`, with a reason) before applying; `drafting → applied → screening → interviewing → offer` in progress; then closed as `rejected`, `role_filled` or `no_response` (their side) or `accepted`, `withdrew` or `declined` (the owner's side). `stage_reached` keeps the furthest in-progress stage so the stats stay honest after a job closes. The application's details (sent date, channel, resume, follow-ups, next action, contact), its interviews, email threads, drafts and files all hang off the job. A job is pursued once; re-applying to a closed job reopens it.
- **Stars** are the owner's own marker for jobs they care about, separate from priority. They set them with the star on each card or in the job pane. Star or unstar a job (`star_job`) only when asked. `search_jobs(starred=True)` lists them, and the default sort puts starred jobs first, then priority.
- Change status only with `set_status`, which records the dates and next action, and use `log_follow_up` and `add_interview` rather than editing those fields. To add a job already applied to, pass `status='applied'` and `status_on` to `add_job`. Statuses never move on their own.
- **Resume version** is the build an application was sent with, e.g. `2026-10-06 general` (see `resume_versions`, which reads the resumes named in settings). Sending today defaults to the current build of the first resume listed. For a past application, record it only when you can tell. Leave it empty when it's unknown.
- **Follow-ups** (`rules.py`): 7 business days after applying, a second 7 business days later, never more than two. After 30 days with no reply the dashboard suggests closing as no response; it never closes anything itself. Forms with no contact get no follow-ups, only the 30-day check. These are suggestions; set `next_action` and `next_action_due` when a company gives its own timeline.
- **Gmail sync** (only when asked, read-only, through a Gmail connector): find sent applications and replies, then `record_email_thread` per job. Store plain text without quoted history. Set `automated=true` on confirmations and notifications (LinkedIn, ATS "we received your application"), so they don't count as replies. Redact credentials, such as API keys in submission emails. Gmail dates are UTC; core converts them to this PC's time zone. A message from an address in settings counts as sent by the owner. A Gmail thread that covers several jobs (LinkedIn groups some) is saved once per job, as `<threadId>#<messageId>`.
- **Email drafts:** if settings name an email guide, follow it. Save each draft with `save_email_draft`, create the Gmail draft, then mark it `in_gmail`. The owner attaches the resume and sends.

## Rules

- This is a real person's job search. Never invent facts, dates, numbers or outcomes. If something is inferred (a date from a follow-up email, a probable resume version), say so in a note.
- Before a migration or bulk change, back up: `python -m jobdesk backup <label>`.
- Nothing personal goes in git: `data/` (database, files, settings) and the files `.gitignore` lists stay local.

## Schema changes

Bump `SCHEMA_VERSION` in `jobdesk/db.py`, add the new columns to `SCHEMA` for fresh databases, and add an `if version == n:` step in `ensure_schema`, which backs up first (v3 merged the old applications table into jobs, see `MIGRATE_2_TO_3`; v4 added `jobs.starred`). Tests and other throwaway databases keep their files and backups next to themselves, never in `data/`. Add new fixed values to `vocab.py`. The schema's CHECK constraints, the input models and the dashboard's filters all read from it. Run `python -m pytest tests` and `npx tsc --noEmit` in `web/`.

## Releasing

Bump `__version__` in `jobdesk/__init__.py`, commit, then tag and push: `git tag v1.2.0; git push origin main v1.2.0`. The release workflow runs the tests, builds `JobDesk-<version>-windows.zip` and publishes it. To build the zip locally, run `packaging/build.ps1` (it builds from a clean `.venv-build`; PyInstaller bundles anything importable, so never build from a Python with other packages installed).
