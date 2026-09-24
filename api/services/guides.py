"""
api/services/guides.py — the guides library: every article the platform and its strategy plugin ship.

  docs/guides/*.md            category "Guides" (or a front-matter ``category:``), slug = file stem
  docs/guides/playbooks/*.md  category "Playbooks", slug ``playbook:<stem>``
  docs/guide/Chapter-*.md     category "Course" (the quant course, when the checkout has it), ``course:<stem>``
  each strategy's guide       category "Strategies", slug ``strategy:<slug>`` (the registry's guide_path / plugin
                              guide directories), and its ``playbook.md`` as ``strategy:<slug>:playbook``

Titles come from the first heading (or front-matter ``title:``); the summary from front-matter ``summary:``, else
the subtitle under the title, else the first paragraph. Articles are read on request (the plugin's are read in
place, read only). Relative links and images are rewritten to absolute URLs the client can fetch: another article
→ ``/api/guides/<slug>``, a file next to the article → ``/api/guides/<slug>/files/<path>``; links that point at
nothing are left as they are and listed in ``unresolved_links``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

from api.bootstrap import WORKING_COPY

GUIDES_DIR = WORKING_COPY / "docs" / "guides"
COURSE_DIR = WORKING_COPY / "docs" / "guide"
SERVABLE = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".csv", ".txt", ".json", ".md"}
CATEGORY_ORDER = ["Guides", "Playbooks", "Strategies", "Course"]

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)((?:\s+\"[^\"]*\")?\))")
_IMG_SRC = re.compile(r"""(<img\b[^>]*\bsrc=["'])([^"']+)(["'])""", re.I)


class UnknownGuide(KeyError):
    pass


@dataclass
class Guide:
    slug: str
    path: Path
    category: str
    root: Path                 # the directory its relative files may be served from


def _front_matter(text: str) -> tuple[dict, str]:
    m = _FRONT.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("'\"")
    return meta, text[m.end():]


def _plain(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_`]+", "", s)
    return " ".join(s.split())


def title_and_summary(text: str, fallback: str) -> tuple[str, str, dict]:
    meta, body = _front_matter(text)
    lines = body.splitlines()
    title, idx = None, 0
    for i, line in enumerate(lines):
        m = _HEADING.match(line.strip())
        if m:
            title, idx = _plain(m.group(2)), i
            break
    summary = meta.get("summary")
    if not summary:
        # a subtitle: a heading right under the title that is followed by a rule or another heading (not by a
        # paragraph, which would make it the first section's heading, e.g. "What It Is")
        rest = [(i, l.strip()) for i, l in enumerate(lines[idx + 1:], idx + 1) if l.strip()]
        if rest and _HEADING.match(rest[0][1]):
            after = rest[1][1] if len(rest) > 1 else "---"
            if after.startswith("---") or _HEADING.match(after):
                summary = _plain(_HEADING.match(rest[0][1]).group(2))
    if not summary:
        para: list[str] = []
        for line in lines[idx + 1:]:
            t = line.strip()
            if not t:
                if para:
                    break
                continue
            if t.startswith(("#", "---", "|", "```", ">", "<", "- ", "* ", "1.")):
                if para:
                    break
                continue
            para.append(t)
        summary = _plain(" ".join(para))
    if summary and len(summary) > 240:
        summary = summary[:237].rsplit(" ", 1)[0] + "…"
    return meta.get("title") or title or fallback, summary or "", meta


def _registry():
    from alan_trader.strategy_api import registry as R
    return R


def catalogue() -> dict[str, Guide]:
    out: dict[str, Guide] = {}
    if GUIDES_DIR.is_dir():
        for p in sorted(GUIDES_DIR.glob("*.md")):
            if not p.name.startswith("_"):
                out[p.stem] = Guide(p.stem, p, "Guides", GUIDES_DIR)
        pb = GUIDES_DIR / "playbooks"
        if pb.is_dir():
            for p in sorted(pb.glob("*.md")):
                out[f"playbook:{p.stem}"] = Guide(f"playbook:{p.stem}", p, "Playbooks", GUIDES_DIR)
    if COURSE_DIR.is_dir():
        for p in sorted(COURSE_DIR.glob("*.md")):
            out[f"course:{p.stem}"] = Guide(f"course:{p.stem}", p, "Course", COURSE_DIR)
    try:
        R = _registry()
        slugs = list(R.STRATEGY_METADATA)
    except Exception:
        R, slugs = None, []
    for s in slugs:
        try:
            g = R.find_guide(s)
        except Exception:
            g = None
        if g is None or not Path(g).is_file():
            continue
        g = Path(g)
        out[f"strategy:{s}"] = Guide(f"strategy:{s}", g, "Strategies", g.parent)
        pb = g.parent / "playbook.md"
        if pb.is_file():
            out[f"strategy:{s}:playbook"] = Guide(f"strategy:{s}:playbook", pb, "Strategies", g.parent)
    return out


def list_guides() -> list[dict]:
    rows = []
    labels = {}
    try:
        labels = {e["value"]: e["label"] for e in _registry().ui_entries()}
    except Exception:
        pass
    for g in catalogue().values():
        try:
            text = g.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        title, summary, meta = title_and_summary(text, g.slug)
        category = meta.get("category") or g.category
        row = {"slug": g.slug, "title": title, "category": category, "summary": summary}
        if g.slug.startswith("strategy:"):
            s = g.slug.split(":")[1]
            row["strategy"] = s
            row["strategy_label"] = labels.get(s, s)
        rows.append(row)
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return sorted(rows, key=lambda r: (order.get(r["category"], len(order)), r["category"], r["title"].lower()))


def _file_url(base: str, slug: str, rel: str) -> str:
    return f"{base}/api/guides/{quote(slug, safe=':')}/files/{quote(rel, safe='/')}"


def rewrite_links(markdown: str, guide: Guide, cat: dict[str, Guide], base: str) -> tuple[str, list[str], int]:
    """(markdown with relative links made absolute, unresolved targets, links rewritten)."""
    by_path = {g.path.resolve(): g.slug for g in cat.values()}
    unresolved: list[str] = []
    count = 0

    def target(t: str) -> Optional[str]:
        nonlocal count
        if not t or t.startswith(("#", "http://", "https://", "mailto:", "data:", "/")) or ":" in t.split("/")[0]:
            return None
        path, _, frag = t.partition("#")
        cand = (guide.path.parent / unquote(path)).resolve()
        if cand in by_path:
            count += 1
            return f"{base}/api/guides/{quote(by_path[cand], safe=':')}" + (f"#{frag}" if frag else "")
        try:
            rel = cand.relative_to(guide.root.resolve())
        except ValueError:
            rel = None
        if rel is not None and cand.is_file() and cand.suffix.lower() in SERVABLE:
            count += 1
            return _file_url(base, guide.slug, rel.as_posix())
        if t not in unresolved:
            unresolved.append(t)
        return None

    def md(m):
        new = target(m.group(2))
        return f"{m.group(1)}{new}{m.group(3)}" if new else m.group(0)

    def img(m):
        new = target(m.group(2))
        return f"{m.group(1)}{new}{m.group(3)}" if new else m.group(0)

    out = _LINK.sub(md, markdown)
    out = _IMG_SRC.sub(img, out)
    return out, unresolved, count


def get(slug: str, base: str = "") -> dict:
    cat = catalogue()
    g = cat.get(slug)
    if g is None:
        raise UnknownGuide(slug)
    text = g.path.read_text(encoding="utf-8", errors="replace")
    title, summary, meta = title_and_summary(text, slug)
    _meta, body = _front_matter(text)
    body, unresolved, n = rewrite_links(body, g, cat, base.rstrip("/"))
    return {"slug": slug, "title": title, "category": meta.get("category") or g.category, "summary": summary,
            "markdown": body, "links_rewritten": n, "unresolved_links": unresolved,
            "source": g.path.name}


def file_path(slug: str, rel: str) -> Path:
    """A file next to a guide, confined to the guide's directory and to document / image types."""
    g = catalogue().get(slug)
    if g is None:
        raise UnknownGuide(slug)
    root = g.root.resolve()
    p = (root / unquote(rel)).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise UnknownGuide(rel)
    if not p.is_file() or p.suffix.lower() not in SERVABLE:
        raise UnknownGuide(rel)
    return p
