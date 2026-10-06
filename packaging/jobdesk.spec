# PyInstaller spec for JobDesk.exe. Run packaging/build.ps1, which builds the dashboard first.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "jobdesk_app.py")],
    pathex=[str(root)],
    datas=[(str(root / "web" / "dist"), "web/dist")],
    # uvicorn picks its loop, protocols and logging by name at runtime.
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("jobdesk"),
    # Never needed, but pulled in through optional imports when they happen to be installed.
    excludes=["watchfiles", "tkinter", "pytest", "IPython", "jedi", "matplotlib", "numpy", "pandas",
              "PIL", "PySide6", "PyQt5", "PyQt6", "boto3", "botocore", "zmq"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobDesk",
    icon=str(root / "packaging" / "jobdesk.ico"),
    console=True,  # the window shows where the data is and closing it stops the server
)
coll = COLLECT(exe, a.binaries, a.datas, name="JobDesk")
