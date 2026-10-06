"""Your own details, from settings.json next to the database. Everything in it is optional and
Job Desk works without the file. Paths can be absolute or relative to the file.

{
  "name": "Ada Lovelace",                        whose job search this is; Claude's instructions use it
  "email_addresses": ["ada@example.com"],        synced mail from these counts as sent by you,
                                                 and the first one opens "Open in Gmail" links
  "resumes": {                                   the resumes you send now, one per variant; the first
    "general": "C:/Users/ada/Resume/resume.pdf", is the default when you mark a job applied today
    "research": "C:/Users/ada/Resume/research.pdf"
  },
  "old_resumes": "C:/Users/ada/Resume/old",      past builds, named 'YYYY-MM-DD_<name>.pdf'
  "email_guide": "C:/Users/ada/email-guide.md"   how you write application emails; Claude reads it first
}
"""

import json
from pathlib import Path

FILE_NAME = "settings.json"
DEFAULTS = {"name": None, "email_addresses": [], "resumes": {}, "old_resumes": None, "email_guide": None}


def load(folder):
    """Settings from `folder`/settings.json. Read on every call, so edits apply without a restart."""
    path = Path(folder) / FILE_NAME
    given = {}
    if path.is_file():
        try:
            given = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} isn't valid JSON: {e}") from None
    s = {**DEFAULTS, **{k: v for k, v in given.items() if k in DEFAULTS}}

    def resolve(p):
        return (path.parent / Path(p).expanduser()).resolve() if p else None

    s["email_addresses"] = [a.strip().lower() for a in s["email_addresses"] or [] if a.strip()]
    s["resumes"] = {variant: resolve(p) for variant, p in (s["resumes"] or {}).items() if p}
    s["old_resumes"] = resolve(s["old_resumes"])
    s["email_guide"] = resolve(s["email_guide"])
    return s


def write_template(folder):
    """Create an empty settings.json for people to fill in, unless there is one already."""
    path = Path(folder) / FILE_NAME
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULTS, indent=2) + "\n", encoding="utf-8")
    return path
