"""Small local retrieval layer for product/business rules.

This is intentionally deterministic. It gives planner graph nodes the same rule
context a human would read in docs, without depending on a remote vector store.
It can be swapped for embeddings later while keeping the node contract stable.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

DOCS = [
    "ROUTE_DAY_BUSINESS_RULES.md",
    "AGENTIC_BUILD_WORKFLOW.md",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 2}


@lru_cache(maxsize=1)
def _chunks() -> tuple[dict, ...]:
    chunks = []
    for name in DOCS:
        path = _repo_root() / "docs" / name
        if not path.exists():
            continue
        title = ""
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                continue
            if line.strip():
                lines.append(line.strip())
        for index, line in enumerate(lines):
            chunks.append({
                "id": f"{name}:{index + 1}",
                "source": f"docs/{name}",
                "title": title or name,
                "text": line,
                "tokens": _tokens(line),
            })
    return tuple(chunks)


def retrieve(query: str, limit: int = 8) -> list[dict]:
    query_tokens = _tokens(query)
    scored = []
    for chunk in _chunks():
        overlap = len(query_tokens & chunk["tokens"])
        if overlap:
            scored.append((overlap, chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [
        {k: v for k, v in chunk.items() if k != "tokens"}
        for _, chunk in scored[:limit]
    ]

