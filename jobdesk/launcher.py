"""What JobDesk.exe does when you double-click it: start the server with the built dashboard,
open it in the browser, and keep running until its window is closed. If Job Desk is already
running, it only opens the dashboard."""

import json
import socket
import threading
import time
import urllib.request
import webbrowser

from . import __version__, paths, settings


def _is_jobdesk(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=1) as r:
            return "vocab" in json.load(r)
    except Exception:
        return False


def _free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def launch(port=8780):
    if _is_jobdesk(port):
        print(f"Job Desk is already running. Opening http://127.0.0.1:{port}/")
        webbrowser.open(f"http://127.0.0.1:{port}/")
        return
    if not _free(port):
        # Something else has the usual port; any free one will do.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    settings_file = settings.write_template(paths.SETTINGS_DIR)

    print(f"Job Desk {__version__} is running at {url}")
    print(f"Your data:      {paths.DATA_DIR}")
    print(f"Your settings:  {settings_file}")
    print("Keep this window open while you use Job Desk. Close it to stop.\n")

    def open_when_up():
        for _ in range(150):
            if _is_jobdesk(port):
                webbrowser.open(url)
                return
            time.sleep(0.2)

    threading.Thread(target=open_when_up, daemon=True).start()
    from .server import serve
    serve(port)
