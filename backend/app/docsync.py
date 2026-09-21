"""Generates docs/08-api-reference.md from the running code, so the reference can never drift.

Everything in it is read from the app itself: the FastAPI routes, the nearby-engine rules, the variables in
backend/.env.example and the front-end page routes. A test fails when the committed file is stale; fix it with

    python scripts/sync_docs.py
"""
import re
from pathlib import Path

from app.live import nearby

DOC = Path(__file__).resolve().parents[2] / "docs" / "08-api-reference.md"
ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

_AUTH_BY_HEADER = {"authorization": "Partner sign-in", "x-admin-token": "Admin token", "x-api-key": "API key"}


def endpoints() -> list[tuple[str, str, str, str]]:
    """Read from the app's OpenAPI schema, which is complete however routers are nested or included."""
    from app.main import app  # imported late: main imports this package's siblings

    rows = []
    for path, item in app.openapi()["paths"].items():
        if not (path.startswith("/api") or path == "/health"):
            continue
        for method, op in item.items():
            headers = {p["name"].lower() for p in op.get("parameters", []) if p["in"] == "header"}
            auth = ", ".join(sorted({label for h, label in _AUTH_BY_HEADER.items() if h in headers})) or "Public"
            text = (op.get("description") or "").strip().split("\n\n")[0]
            rows.append((path, method.upper(), auth, " ".join(text.split())))
    return sorted(rows)


def env_vars() -> list[tuple[str, str]]:
    out, note = [], ""
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#"):
            note = f"{note} {line.lstrip('# ').strip()}".strip()
        elif "=" in line and re.match(r"^[A-Z_]+=", line):
            out.append((line.split("=", 1)[0], note))
            note = ""
        else:
            note = ""
    return out


def pages() -> list[str]:
    from app.main import SPA_ROUTES

    return ["/"] + [f"/{r}" for r in SPA_ROUTES]


def render() -> str:
    lines = [
        "# 08 · API reference (generated)",
        "",
        "> **Generated from the code. Do not edit by hand.** Run `python scripts/sync_docs.py` from `backend/` after",
        "> adding or changing an endpoint, a nearby rule, an environment variable or a page. A test fails when this",
        "> file is out of date, so it cannot silently drift.",
        "",
        "For what each feature means and who it is for, see the [feature registry](FEATURES.md).",
        "",
        "## Endpoints",
        "",
        "| Method | Path | Who can call it | What it does |",
        "|---|---|---|---|",
    ]
    for path, method, auth, summary in endpoints():
        lines.append(f"| {method} | `{path}` | {auth} | {summary} |")
    lines += ["", "## Front-end pages", "", "| Path |", "|---|"] + [f"| `{p}` |" for p in pages()]
    lines += ["", "## Nearby-engine rules", "", "| Rule | What it does |", "|---|---|"]
    lines += [f"| {rule} | {text} |" for rule, text in nearby.RULES.items()]
    lines += ["", "## Environment variables", "", "Set these in `backend/.env` (copy from `.env.example`).", "",
              "| Variable | Notes |", "|---|---|"]
    lines += [f"| `{name}` | {note or '-'} |" for name, note in env_vars()]
    return "\n".join(lines) + "\n"


def write() -> Path:
    DOC.write_text(render(), encoding="utf-8", newline="\n")
    return DOC
