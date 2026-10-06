"""python -m jobdesk <command>   (or JobDesk.exe <command>)

  launch [--port 8780]             start the server and open the dashboard in the browser
                                   (what JobDesk.exe does when it's double-clicked)
  serve [--port 8780] [--reload]   run the dashboard API (and the built dashboard)
  mcp                              run the MCP server over stdio
  today                            print what's due
  search <words...>                search jobs
  backup [label]                   copy the database into backups/ next to it
  version                          print the version
"""

import json
import sys


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8780

    if cmd == "launch":
        from .launcher import launch
        launch(port)
    elif cmd == "version":
        from . import __version__
        print(__version__)
    elif cmd == "serve":
        if "--reload" in args:
            # uvicorn's own reloader hangs on Windows here; watchfiles restarts the whole process instead.
            from watchfiles import PythonFilter, run_process
            from .paths import ROOT
            # The target is named by its import path so the restarted process can find it on Windows.
            run_process(ROOT / "jobdesk", target="jobdesk.server.serve", args=(port,), watch_filter=PythonFilter(),
                        sigint_timeout=2, sigkill_timeout=1)
        else:
            from .server import serve
            serve(port)
    elif cmd == "mcp":
        from .mcp_server import main as run_mcp
        run_mcp()
    elif cmd == "today":
        from .core import Desk
        with Desk() as d:
            print(json.dumps(d.overview(), indent=2, ensure_ascii=False, default=str))
    elif cmd == "search":
        from .core import Desk
        with Desk() as d:
            res = d.search_jobs(q=" ".join(args))
        for j in res["jobs"]:
            where = ", ".join(x for x in (j["city"], j["country"]) if x)
            state = "" if j["app_state"] == "none" else f"  [{j['app_state']}]"
            print(f"#{j['id']:<4} {j['title']} · {j['company'] or '?'} · {where}{state}")
        print(f"{res['total']} job(s)")
    elif cmd == "backup":
        from .db import backup
        print(backup(args[0] if args else "manual"))
    else:
        print(f"Unknown command: {cmd}\n{__doc__}")
        sys.exit(2)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
