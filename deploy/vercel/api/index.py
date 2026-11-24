"""Vercel entrypoint: the unchanged FastAPI app from backend/server.py.
vercel.json rewrites /api/* and /research-admin here; FastAPI still sees the
original path, so routes match exactly as they do under uvicorn."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from server import app  # noqa: E402,F401
