"""Vercel entrypoint. The Python runtime serves the ASGI app exported as `app`."""

import sys
from pathlib import Path

# The function file lives in api/, so the backend root has to be importable
# before `app` resolves to the FastAPI package rather than nothing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

__all__ = ["app"]
