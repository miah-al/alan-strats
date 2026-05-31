"""
app/pages/course/print_view.py — print-ready combined HTML + Flask routes.

Provides `/course/print` (single scrollable HTML of one or all chapters, MathJax
for LaTeX, ready for the browser's Print → Save-as-PDF) and `/guide-figure/<rel>`
(cached figure serving). `register_routes(app)` is called from the package
__init__ at import time. This logic is faithfully preserved from the original
course.py — only relocated.
"""
from __future__ import annotations

import base64
import re

import dash
import flask

from app.pages.course.content import _GUIDE_DIR, _FIG_DIR, parse_chapter_stem


_PRINT_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+Pro:wght@400;700&family=Source+Code+Pro&display=swap');
* { box-sizing: border-box; }
body {
  font-family: 'Source Serif Pro', Georgia, serif;
  color: #222; background: #fff; line-height: 1.6;
  max-width: 780px; margin: 2em auto; padding: 0 1em;
}
h1, h2, h3, h4 { font-family: system-ui, -apple-system, sans-serif; color: #111; }
h1 { font-size: 28px; border-bottom: 2px solid #333; padding-bottom: 4px; margin-top: 2em; page-break-before: always; }
h1:first-of-type { page-break-before: auto; }
h2 { font-size: 20px; margin-top: 1.6em; }
h3 { font-size: 16px; }
p, li { font-size: 13pt; }
code, pre { font-family: 'Source Code Pro', Consolas, monospace; font-size: 11pt; }
pre { background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }
code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #999; padding: 4px 8px; font-size: 11pt; }
th { background: #eee; }
img { max-width: 100%; height: auto; margin: 1em 0; display: block; }
em { color: #555; }
hr { border: 0; border-top: 1px solid #ccc; margin: 1.5em 0; }
blockquote { border-left: 3px solid #999; color: #555; padding-left: 1em; margin-left: 0; }
.MathJax { font-size: 105% !important; }
@media print {
  body { margin: 0; max-width: none; padding: 0.3in; }
  h1 { page-break-before: always; }
  h2, h3 { page-break-after: avoid; }
  img { page-break-inside: avoid; }
  .no-print { display: none !important; }
}
.toolbar {
  position: fixed; top: 12px; right: 12px; z-index: 1000;
  background: #6366f1; color: #fff; padding: 8px 14px; border-radius: 6px;
  font-family: system-ui; font-size: 13px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15); border: none;
}
.toolbar:hover { background: #4f46e5; }
"""

_MATHJAX = """
<script>
MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true,
    tags: 'none'
  },
  chtml: { fontURL: 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/output/chtml/fonts/woff-v2' },
  startup: {
    ready: function() {
      MathJax.startup.defaultReady();
      MathJax.startup.promise.then(function() {
        document.title = document.title.replace(/^⏳ /, '') + ' ✓';
      });
    }
  }
};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
"""


def _inline_figures_for_print(markdown: str) -> str:
    """Rewrite figures/xxx.png → inline data URIs so they render offline."""
    def swap(m):
        rel = m.group(1)
        fp = (_GUIDE_DIR / rel).resolve()
        if not fp.is_file():
            return m.group(0)
        ext = fp.suffix.lstrip(".").lower() or "png"
        data = base64.b64encode(fp.read_bytes()).decode("ascii")
        return f"](data:image/{ext};base64,{data})"
    return re.sub(r"\]\((figures/[^)\s]+\.(?:png|jpe?g|svg))\)", swap, markdown)


def build_print_html(only_chapter: str | None = None) -> str:
    """Combined print HTML. `only_chapter` restricts to one chapter (so MathJax
    renders ~500 spans in seconds, vs 9,000+ / several minutes for the full guide)."""
    try:
        import markdown as md_lib
    except ImportError:
        return ("<html><body><h1>Error</h1><p>Install the <code>markdown</code> "
                "package: <code>pip install markdown</code></p></body></html>")

    chapters = []
    if only_chapter:
        p = _GUIDE_DIR / f"{only_chapter}.md"
        if not p.is_file():
            return f"<html><body><h1>Not found</h1><p>{only_chapter}.md</p></body></html>"
        chapters.append(p.read_text(encoding="utf-8"))
    else:
        readme = _GUIDE_DIR / "README.md"
        if readme.is_file():
            chapters.append(readme.read_text(encoding="utf-8"))
        chapter_paths = [
            (parsed[0], p) for p in _GUIDE_DIR.glob("Chapter-*.md")
            if (parsed := parse_chapter_stem(p.stem)) is not None
        ]
        chapter_paths.sort(key=lambda t: t[0])
        for _, p in chapter_paths:
            chapters.append(p.read_text(encoding="utf-8"))

    combined_md = "\n\n".join(_inline_figures_for_print(c) for c in chapters)

    # Protect math from the markdown converter, convert, then restore with
    # MathJax-friendly delimiters.
    math_spans: list[str] = []

    def _stash_display(m):
        math_spans.append(m.group(1))
        return f"@@MATHDISPLAY{len(math_spans)-1}@@"

    def _stash_inline(m):
        math_spans.append(m.group(1))
        return f"@@MATHINLINE{len(math_spans)-1}@@"

    combined_md = re.sub(r"```math\s*\n(.+?)\n```", _stash_display, combined_md, flags=re.DOTALL)
    combined_md = re.sub(r"\$\$(.+?)\$\$", _stash_display, combined_md, flags=re.DOTALL)
    combined_md = re.sub(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)", _stash_inline, combined_md)

    html_body = md_lib.markdown(
        combined_md, extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )

    def _restore_display(m):
        return f"\\[{math_spans[int(m.group(1))]}\\]"

    def _restore_inline(m):
        return f"\\({math_spans[int(m.group(1))]}\\)"

    html_body = re.sub(r"@@MATHDISPLAY(\d+)@@", _restore_display, html_body)
    html_body = re.sub(r"@@MATHINLINE(\d+)@@", _restore_inline, html_body)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Quant Guide — Print View</title>
<style>{_PRINT_CSS}</style>
{_MATHJAX}
</head><body>
<button class="toolbar no-print" onclick="window.print()">📄 Print / Save as PDF</button>
{html_body}
</body></html>"""


def register_routes(app) -> None:
    @app.server.route("/course/print")
    def _course_print():
        only = flask.request.args.get("chapter")
        return flask.Response(build_print_html(only), mimetype="text/html")

    @app.server.route("/guide-figure/<path:rel>")
    def _guide_figure(rel):
        fp = (_FIG_DIR / rel).resolve()
        try:
            fp.relative_to(_FIG_DIR.resolve())
        except ValueError:
            flask.abort(404)
        if not fp.is_file():
            flask.abort(404)
        return flask.send_file(fp, max_age=3600)


# Register with the app at import time (mirrors original behaviour).
try:
    register_routes(dash.get_app())
except Exception:
    pass  # app not yet created; caller can register_routes(app) manually
