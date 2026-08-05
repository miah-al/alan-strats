"""
app/pages/scope/content.py — document discovery and loading for the Scope page.

Data/content only: no Dash components, no callbacks. The page renders markdown
that lives on disk under docs/, so the documents stay readable and diffable
outside the app and cannot drift from what is committed.
"""
from __future__ import annotations

from pathlib import Path

# app/pages/scope/content.py → repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = _REPO_ROOT / "docs"
REVIEWS_DIR = DOCS_DIR / "reviews"

SCOPE_DOC = DOCS_DIR / "strategy_scope.md"


def _title_from_markdown(path: Path, fallback: str) -> str:
    """First `# heading` in the file, else the supplied fallback."""
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        pass
    return fallback


def _pretty_stem(stem: str) -> str:
    """`2026-07-11_full_strategy_validation` → `2026-07-11 · full strategy validation`."""
    if "_" in stem and stem[:4].isdigit():
        date_part, _, rest = stem.partition("_")
        return f"{date_part} · {rest.replace('_', ' ')}"
    return stem.replace("_", " ")


def document_options() -> list[dict]:
    """
    Dropdown options for every document the page can show.

    The scope document first, then review reports newest-first — reviews are
    named with a leading ISO date, so a reverse sort is chronological.
    """
    options: list[dict] = []

    if SCOPE_DOC.is_file():
        options.append({
            "label": _title_from_markdown(SCOPE_DOC, "Strategy Scope"),
            "value": str(SCOPE_DOC),
        })

    if REVIEWS_DIR.is_dir():
        for path in sorted(REVIEWS_DIR.glob("*.md"), reverse=True):
            options.append({
                "label": _pretty_stem(path.stem),
                "value": str(path),
            })

    return options


def default_document() -> str | None:
    options = document_options()
    return options[0]["value"] if options else None


def load_document(path_str: str | None) -> str:
    """
    Read a document, refusing anything outside docs/.

    The value arrives from a client-supplied dropdown, so it is not trusted:
    a path that escapes docs/ is rejected rather than read.
    """
    if not path_str:
        return "_No document selected._"

    try:
        path = Path(path_str).resolve()
        path.relative_to(DOCS_DIR.resolve())
    except (ValueError, OSError):
        return "_That document is outside the docs directory and was not loaded._"

    if not path.is_file() or path.suffix.lower() != ".md":
        return f"_Document not found: `{path.name}`_"

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"_Could not read `{path.name}`: {exc}_"
