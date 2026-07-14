"""
Production WSGI entrypoint.

Run with gunicorn (Linux/Mac):
    gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app

Run with waitress (Windows):
    waitress-serve --port=8000 wsgi:app
"""
import sys
from pathlib import Path

# Make sure the app/ package directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
