"""Entry point for JobDesk.exe. Double-clicked, it launches the dashboard; with arguments it
works like `python -m jobdesk` (e.g. `JobDesk.exe mcp` for Claude)."""

import sys

from jobdesk.__main__ import main

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:] or ["launch"])
