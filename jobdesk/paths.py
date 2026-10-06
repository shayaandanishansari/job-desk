import os
import sys
from pathlib import Path

# Running as JobDesk.exe (PyInstaller): the code and the built dashboard are unpacked into
# sys._MEIPASS, and the data lives in AppData, outside the program's folder.
FROZEN = getattr(sys, "frozen", False)

ROOT = Path(__file__).resolve().parent.parent          # the repo
WEB_DIST = (Path(sys._MEIPASS) if FROZEN else ROOT) / "web" / "dist"


def _default_data_dir():
    if FROZEN:
        return Path(os.environ.get("APPDATA") or Path.home()) / "JobDesk"
    return ROOT / "data"


# JOBDESK_HOME moves the whole data folder; JOBDESK_DB points everything at one database.
DATA_DIR = Path(os.environ.get("JOBDESK_HOME") or _default_data_dir())
DB_PATH = Path(os.environ.get("JOBDESK_DB", DATA_DIR / "jobdesk.db"))
# Files, backups and settings live next to whichever database is in use, so a test database
# never writes into the real data/files.
FILES_DIR = DB_PATH.parent / "files"
BACKUP_DIR = DB_PATH.parent / "backups"
SETTINGS_DIR = DB_PATH.parent
