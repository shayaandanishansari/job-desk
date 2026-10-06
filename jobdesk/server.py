"""The dashboard's API. Run with `python -m jobdesk serve`.

Writes made here are logged as actor 'me'. Changes from any process (Claude
through MCP, the CLI, an import script) reach open dashboards through
/api/stream, which watches the events table."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import db, paths, rules, vocab
from .core import Desk, DeskError, NotFound, PossibleDuplicate

app = FastAPI(title="Job Desk")


def desk():
    return Desk(actor="me")


@app.exception_handler(NotFound)
async def _not_found(request: Request, exc: NotFound):
    return JSONResponse({"error": str(exc)}, status_code=404)


@app.exception_handler(PossibleDuplicate)
async def _dupe(request: Request, exc: PossibleDuplicate):
    return JSONResponse({"error": str(exc), "matches": exc.matches}, status_code=409)


@app.exception_handler(DeskError)
async def _desk_error(request: Request, exc: DeskError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(ValidationError)
async def _invalid(request: Request, exc: ValidationError):
    return JSONResponse({"error": "Invalid input", "details": json.loads(exc.json())}, status_code=422)


def run(fn, *args, **kwargs):
    with desk() as d:
        return getattr(d, fn)(*args, **kwargs)


# ------------------------------------------------------------------ meta

@app.get("/api/meta")
def meta():
    me = run("settings")
    return {
        "me": {"name": me["name"], "gmail": me["email_addresses"][0] if me["email_addresses"] else None},
        "vocab": {name: list(getattr(vocab, name)) for name in (
            "WORK_MODES", "EMPLOYMENT_TYPES", "SENIORITIES", "TRI_STATE", "APPLY_METHODS", "SOURCES",
            "STATUSES", "BEFORE", "STAGES", "OUTCOMES", "PASS_REASONS", "CHANNELS", "INTERVIEW_KINDS",
            "DRAFT_STATUSES", "DRAFT_KINDS")},
        "labels": vocab.LABELS,
        "outcome_side": vocab.OUTCOME_SIDE,
        "rules": {"follow_up_after_business_days": rules.FOLLOW_UP_AFTER, "max_follow_ups": rules.MAX_FOLLOW_UPS,
                  "no_response_after_days": rules.NO_RESPONSE_AFTER},
        "resumes": run("resume_versions"),
        "today": date.today().isoformat(),
    }


@app.get("/api/today")
def today():
    return run("today")


@app.get("/api/stats")
def stats():
    return run("stats")


# ------------------------------------------------------------------ jobs

FACET_PARAMS = Desk.FACETS


@app.get("/api/jobs")
def jobs(request: Request, q: str | None = None, sort: str = "priority"):
    filters = {}
    for key in FACET_PARAMS:
        values = request.query_params.getlist(key)
        if values:
            filters[key] = values
    return run("search_jobs", q=q, filters=filters, sort=sort, with_facets=True)


@app.get("/api/jobs/{job_id}")
def job(job_id: int):
    return run("get_job", job_id)


@app.patch("/api/jobs/{job_id}")
def patch_job(job_id: int, body: dict[str, Any]):
    return run("update_job", job_id, **body)


@app.post("/api/jobs/{job_id}/status")
def status(job_id: int, body: dict[str, Any]):
    return run("set_status", job_id, body["status"], on=body.get("on"), note=body.get("note"),
               pass_reason=body.get("pass_reason"), outcome_notes=body.get("outcome_notes"))


@app.post("/api/jobs/{job_id}/follow-up")
def follow_up(job_id: int, body: dict[str, Any] | None = None):
    body = body or {}
    return run("log_follow_up", job_id, on=body.get("on"), note=body.get("note"))


@app.patch("/api/interviews/{interview_id}")
def patch_interview(interview_id: int, body: dict[str, Any]):
    return run("update_interview", interview_id, **body)


@app.patch("/api/drafts/{draft_id}")
def patch_draft(draft_id: int, body: dict[str, Any]):
    return run("update_draft", draft_id, **body)


@app.post("/api/notes")
def note(body: dict[str, Any]):
    return run("add_note", body["entity_type"], int(body["entity_id"]), body["text"])


# ------------------------------------------------------------------ people and mail

@app.get("/api/companies")
def companies():
    return run("list_companies")


@app.get("/api/companies/{company_id}")
def company(company_id: int):
    return run("get_company", company_id)


@app.get("/api/contacts")
def contacts():
    return run("list_contacts")


@app.get("/api/threads")
def threads(unlinked_only: bool = False):
    return run("list_threads", unlinked_only=unlinked_only)


@app.get("/api/threads/{thread_id}")
def thread(thread_id: int):
    return run("get_thread", thread_id)


@app.get("/api/events")
def events(after: int = 0, limit: int = 100):
    return run("events_after", after, limit)


# ------------------------------------------------------------------ files

@app.get("/files/{path:path}")
def files(path: str):
    target = (paths.FILES_DIR / path).resolve()
    if paths.FILES_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404)
    return FileResponse(target)


@app.get("/api/resume")
def resume(version: str):
    v = run("resolve_resume", version)
    if not v or not v.get("path") or not Path(v["path"]).is_file():
        raise HTTPException(404, f"No resume file for {version}")
    return FileResponse(v["path"], media_type="application/pdf" if v["path"].endswith(".pdf") else None,
                        filename=Path(v["path"]).name, content_disposition_type="inline")


# ------------------------------------------------------------------ live updates

@app.get("/api/stream")
async def stream(request: Request):
    """Server-sent events. Sends each new row of the events table, plus a bare
    'change' when the database changes without an event (someone edited it by hand)."""

    async def gen():
        watcher = db.connect()
        last = watcher.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()[0]
        version = watcher.execute("PRAGMA data_version").fetchone()[0]
        yield f"event: hello\ndata: {json.dumps({'last_event': last})}\n\n"
        idle = 0
        try:
            while not await request.is_disconnected():
                await asyncio.sleep(1)
                rows = watcher.execute("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT 200", (last,)).fetchall()
                new_version = watcher.execute("PRAGMA data_version").fetchone()[0]
                if rows:
                    last = rows[-1]["id"]
                    yield f"event: events\ndata: {json.dumps([dict(r) for r in rows], default=str)}\n\n"
                    idle = 0
                elif new_version != version:
                    yield "event: change\ndata: {}\n\n"
                    idle = 0
                else:
                    idle += 1
                    if idle >= 15:
                        yield ": keep-alive\n\n"
                        idle = 0
                version = new_version
        finally:
            watcher.close()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def serve(port=8780):
    import uvicorn
    # Open dashboards hold a live-update stream; cap the wait for it when shutting down.
    uvicorn.run(app, host="127.0.0.1", port=port, timeout_graceful_shutdown=2)


# The built dashboard, when there is one. During development Vite serves it instead.
if paths.WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=paths.WEB_DIST, html=True), name="web")
