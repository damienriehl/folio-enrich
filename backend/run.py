"""Entry point for standalone executable (PyInstaller)."""
import os
import subprocess
import sys
import threading
import time
import webbrowser

_PORT = int(os.environ.get("FOLIO_ENRICH_PORT", "8731"))


def open_browser():
    time.sleep(2)
    webbrowser.open(f"http://localhost:{_PORT}")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=_PORT)
