"""Regenerate docs/08-api-reference.md from the code.  Run from backend/:  python scripts/sync_docs.py"""
import os
import sys
from pathlib import Path

os.environ.setdefault("WAYFINDER_OFFLINE", "1")  # generating docs must never touch the network
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import docsync  # noqa: E402

print(f"wrote {docsync.write()}")
