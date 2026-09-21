"""Keeps the markdown docs in step with the code. When one of these fails, the message says which doc to update.

Generated docs (docs/08-api-reference.md) are rebuilt with `python scripts/sync_docs.py`. The rest are written by
hand, and these tests fail if a new endpoint, page, module or setting is not mentioned anywhere.
"""
import re
from pathlib import Path

from app import docsync

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
DOCS = REPO / "docs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def all_docs() -> str:
    return "\n".join(read(p) for p in sorted(DOCS.glob("*.md")))


def test_generated_api_reference_is_up_to_date():
    assert docsync.DOC.exists(), "Run: python scripts/sync_docs.py (from backend/)"
    assert read(docsync.DOC) == docsync.render(), "docs/08-api-reference.md is stale. Run: python scripts/sync_docs.py (from backend/)"


def test_every_endpoint_has_a_plain_description():
    blank = [f"{m} {p}" for p, m, _auth, text in docsync.endpoints() if not text]
    assert not blank, f"Add a one-line docstring to these endpoint functions: {blank}"


def test_every_environment_variable_is_explained():
    text = read(DOCS / "05-live-data-and-ai.md")
    missing = [name for name, _ in docsync.env_vars() if f"`{name}`" not in text]
    assert not missing, f"Add these to the configuration table in docs/05-live-data-and-ai.md: {missing}"


def test_every_front_end_page_is_in_the_feature_registry():
    text = read(DOCS / "FEATURES.md")
    missing = [p.name for p in (REPO / "frontend" / "src" / "pages").glob("*.jsx") if f"pages/{p.name}" not in text]
    assert not missing, f"Add a feature row in docs/FEATURES.md that names these pages: {missing}"


def test_every_page_route_is_described_somewhere():
    docs = all_docs()
    missing = [p for p in docsync.pages() if p != "/" and f"`{p}`" not in docs and f"{p}" not in docs]
    assert not missing, f"Mention these page routes in the docs: {missing}"


def test_every_backend_module_is_mentioned_in_the_docs():
    docs = all_docs()
    modules = [p for p in (BACKEND / "app").rglob("*.py") if p.name != "__init__.py" and "__pycache__" not in p.parts]
    missing = sorted(str(p.relative_to(BACKEND)).replace("\\", "/") for p in modules
                     if p.name not in docs and str(p.relative_to(BACKEND)).replace("\\", "/") not in docs)
    assert not missing, f"Mention these modules in the docs (a code-map row in docs/02-architecture.md is the usual place): {missing}"


def test_feature_ids_are_not_reused():
    ids = re.findall(r"^\| (F-\d{3}[a-z]?) \|", read(DOCS / "FEATURES.md"), flags=re.M)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"Duplicate feature IDs in docs/FEATURES.md: {dupes}"
