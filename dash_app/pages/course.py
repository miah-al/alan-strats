"""
dash_app/pages/course.py — Quant Course

Renders the 12-chapter guide built under docs/guide/ with:
  - Chapter dropdown (left panel)
  - Rendered markdown with LaTeX + figure embeds (main panel)
  - /course/print route: print-ready combined HTML (all chapters concatenated,
    MathJax-rendered, clean typography) — use browser Ctrl+P → Save as PDF.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import flask
from dash import html, dcc, callback, Input, Output, no_update

from dash_app import theme as T

_GUIDE_DIR  = Path(__file__).parent.parent.parent / "docs" / "guide"
_FIG_DIR    = _GUIDE_DIR / "figures"


# ── Chapter discovery ─────────────────────────────────────────────────────

_PARTS: list[tuple[str, range]] = [
    ("Part I — Discrete-Time Models",              range(1, 3)),   # CH01–CH02
    ("Part II — Continuous-Time Models",           range(3, 6)),   # CH03–CH05
    ("Part III — Equity Derivatives",              range(6, 11)),  # CH06–CH10
    ("Part IV — Interest-Rate Models",             range(11, 14)), # CH11–CH13
    ("Part V — Stochastic Vol & Rate Derivatives", range(14, 16)), # CH14–CH15
]


def _chapter_options() -> list[dict]:
    """Flat list of chapter options (value = filename stem), used by the callback."""
    opts = []
    for p in sorted(_GUIDE_DIR.glob("CH*.md")):
        stem = p.stem
        num = stem[2:4]
        title = stem[5:].replace("-", " ")
        opts.append({"label": f"{num} — {title}", "value": stem, "num": int(num)})
    return opts


def _grouped_chapter_options() -> list[tuple[str, list[dict]]]:
    """Return [(part_name, [options])] grouped per Part I–V."""
    all_opts = _chapter_options()
    groups: list[tuple[str, list[dict]]] = []
    for part_name, nums in _PARTS:
        part_opts = [{"label": o["label"], "value": o["value"]}
                     for o in all_opts if o["num"] in nums]
        if part_opts:
            groups.append((part_name, part_opts))
    return groups


def _rewrite_figure_paths(markdown: str) -> str:
    """Rewrite `figures/chNN-foo.png` image paths to the `/guide-figure/...`
    Flask route so the browser fetches each PNG once and caches it, instead of
    re-encoding the whole image as base64 on every chapter navigation."""
    return re.sub(
        r"\]\(figures/([^)\s]+\.(?:png|jpe?g|svg))\)",
        lambda m: f"](/guide-figure/{m.group(1)})",
        markdown,
    )


def _convert_math_fences(markdown: str) -> str:
    """dcc.Markdown's MathJax handles $...$ and $$...$$ but not ```math fenced
    blocks. Rewrite every ```math ... ``` fence to a $$ ... $$ display-math
    block so the live course view renders equations instead of showing raw
    LaTeX inside a code block."""
    return re.sub(
        r"```math\s*\n(.+?)\n```",
        lambda m: f"\n\n$$\n{m.group(1)}\n$$\n\n",
        markdown,
        flags=re.DOTALL,
    )


# ── Layout ────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    groups = _grouped_chapter_options()
    default = groups[0][1][0]["value"] if groups and groups[0][1] else None
    readme_path = _GUIDE_DIR / "README.md"
    readme_exists = readme_path.is_file()

    sidebar = html.Div([
        html.Div("Quant Course",
                 style={"color": T.ACCENT, "fontSize": "11px",
                        "fontWeight": "700", "letterSpacing": "0.08em",
                        "textTransform": "uppercase", "marginBottom": "10px"}),
        dbc.Button(
            "📖 Overview (README)", id="course-overview-btn",
            color="secondary", outline=True, size="sm",
            className="w-100 mb-2",
            style={"fontSize": "12px", "textAlign": "left"},
            disabled=not readme_exists,
        ),
        dbc.Button(
            "📄 Print this chapter (fast)", id="course-print-one-btn",
            color="primary", outline=True, size="sm",
            className="w-100 mb-2",
            style={"fontSize": "12px", "textAlign": "left"},
            external_link=True, target="_blank",
            # href is set per-chapter by a callback below
        ),
        dbc.Button(
            "📚 Full guide (slow: ~3 min MathJax)", id="course-print-btn",
            color="secondary", outline=True, size="sm",
            className="w-100 mb-3",
            style={"fontSize": "11px", "textAlign": "left"},
            href="/course/print", external_link=True, target="_blank",
        ),
        # Parts I–V rendered as grouped sections. Each RadioItems has a
        # pattern-matching id so the callback sees whichever part was clicked;
        # shared dcc.Store keeps the current chapter across parts.
        *[
            html.Div([
                html.Div(part_name, style={
                    "color": T.ACCENT, "fontSize": "10.5px",
                    "fontWeight": "700", "letterSpacing": "0.06em",
                    "textTransform": "uppercase",
                    "marginTop": "12px" if idx > 0 else "0",
                    "marginBottom": "4px",
                }),
                dbc.RadioItems(
                    id={"type": "course-chapter-part", "part": idx},
                    options=part_opts,
                    value=default if (idx == 0 and part_opts and part_opts[0]["value"] == default) else None,
                    className="course-chapter-list",
                    labelStyle={
                        "display": "block",
                        "color": T.TEXT_PRIMARY, "fontSize": "13px",
                        "padding": "6px 10px",
                        "borderRadius": "4px",
                        "cursor": "pointer",
                        "marginBottom": "1px",
                    },
                    inputStyle={"display": "none"},
                ),
            ])
            for idx, (part_name, part_opts) in enumerate(groups)
        ],
        dcc.Store(id="course-chapter", data=default),
        html.Div([
            html.Hr(style={"borderColor": T.BORDER, "margin": "14px 0 10px"}),
            html.Div(
                f"📊 {len(list(_FIG_DIR.glob('*.png'))) if _FIG_DIR.is_dir() else 0} figures",
                style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
        ]),
        dcc.Store(id="course-show-overview", data=False),
    ], style={**T.STYLE_CARD, "marginBottom": "0", "position": "sticky", "top": "20px"})

    main = html.Div([
        dcc.Loading(
            html.Div(id="course-content",
                     className="guide-md",
                     style={"color": T.TEXT_PRIMARY, "fontSize": "14px",
                            "lineHeight": "1.75", "minHeight": "400px"}),
            type="circle", color=T.ACCENT,
        ),
    ], style={**T.STYLE_CARD})

    return html.Div([
        html.H1("Quant Course", style={"color": T.TEXT_PRIMARY, "fontSize": "22px",
                                         "fontWeight": "700", "marginBottom": "4px"}),
        html.Div("12-chapter study guide on arbitrage pricing, "
                 "stochastic-vol, short-rate models and rate derivatives.",
                 style={"color": T.TEXT_SEC, "fontSize": "13px",
                        "marginBottom": "20px"}),
        dbc.Row([
            dbc.Col(sidebar, md=3),
            dbc.Col(main, md=9),
        ]),
    ], style=T.STYLE_PAGE)


# ── Callbacks ─────────────────────────────────────────────────────────────

from dash import ALL


@callback(
    Output("course-print-one-btn", "href"),
    Input("course-chapter", "data"),
    prevent_initial_call=False,
)
def _print_one_href(chapter_slug):
    return f"/course/print?chapter={chapter_slug}" if chapter_slug else "/course/print"


@callback(
    Output("course-chapter", "data"),
    Input({"type": "course-chapter-part", "part": ALL}, "value"),
    prevent_initial_call=True,
)
def _route_part_clicks(values):
    # Whichever Part's RadioItems was just clicked carries the new chapter slug.
    from dash import ctx
    if not ctx.triggered:
        return no_update
    # The last non-None value across all parts is the user's current selection.
    picked = next((v for v in values if v), None)
    return picked or no_update


@callback(
    Output("course-show-overview", "data"),
    Input("course-overview-btn", "n_clicks"),
    Input("course-chapter", "data"),
    prevent_initial_call=False,
)
def _toggle_overview(n, chapter_change):
    # Any chapter change resets to chapter mode.
    from dash import ctx
    if ctx.triggered_id == "course-overview-btn":
        return True
    return False


@callback(
    Output("course-content", "children"),
    Input("course-chapter", "data"),
    Input("course-show-overview", "data"),
)
def _render(chapter_slug, show_overview):
    if show_overview:
        p = _GUIDE_DIR / "README.md"
    elif chapter_slug:
        p = _GUIDE_DIR / f"{chapter_slug}.md"
    else:
        return html.Div("Select a chapter", style={"color": T.TEXT_MUTED})

    if not p.is_file():
        return html.Div(f"Not found: {p.name}", style={"color": T.DANGER})

    content = _convert_math_fences(_rewrite_figure_paths(p.read_text(encoding="utf-8")))
    return dcc.Markdown(
        content,
        mathjax=True,
        className="guide-md",
        style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.75"},
    )


# ── Print-ready combined HTML route ──────────────────────────────────────
# Register on the Flask server so /course/print returns a single scrollable
# HTML page with every chapter in order, MathJax for LaTeX, ready for the
# browser's native Print → Save-as-PDF flow.

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
        // Signal to the browser that rendering is complete so Ctrl+P
        // doesn't fire mid-render.
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


def _build_print_html(only_chapter: str | None = None) -> str:
    """Build the print-ready combined HTML. If `only_chapter` is a chapter
    slug (e.g. 'CH07-Dynamic-Hedging-II-Greeks'), render only that chapter —
    useful for the full-guide view where MathJax has to process 9,000+ spans
    and would take 2-5 minutes to finish."""
    try:
        import markdown as md_lib
    except ImportError:
        return "<html><body><h1>Error</h1><p>Install the <code>markdown</code> package: <code>pip install markdown</code></p></body></html>"

    chapters = []
    if only_chapter:
        p = _GUIDE_DIR / f"{only_chapter}.md"
        if not p.is_file():
            return f"<html><body><h1>Not found</h1><p>{only_chapter}.md</p></body></html>"
        chapters.append(p.read_text(encoding="utf-8"))
    else:
        # Optional README on top
        readme = _GUIDE_DIR / "README.md"
        if readme.is_file():
            chapters.append(readme.read_text(encoding="utf-8"))
        # Every chapter in order
        for p in sorted(_GUIDE_DIR.glob("CH*.md")):
            chapters.append(p.read_text(encoding="utf-8"))

    combined_md = "\n\n".join(_inline_figures_for_print(c) for c in chapters)

    # Protect math from the markdown converter so $$...$$ blocks don't get
    # wrapped in <pre><code>. Stash each math span under a sentinel, convert
    # markdown, then restore the math with MathJax-friendly \[...\] / \(...\)
    # delimiters.
    math_spans: list[str] = []

    def _stash_display(m):
        math_spans.append(m.group(1))
        return f"@@MATHDISPLAY{len(math_spans)-1}@@"

    def _stash_inline(m):
        math_spans.append(m.group(1))
        return f"@@MATHINLINE{len(math_spans)-1}@@"

    # ```math ... ``` fenced blocks (used throughout reference-formula sections),
    # then $$ ... $$ (display), then $ ... $ (inline). Non-greedy, DOTALL.
    combined_md = re.sub(r"```math\s*\n(.+?)\n```", _stash_display, combined_md, flags=re.DOTALL)
    combined_md = re.sub(r"\$\$(.+?)\$\$", _stash_display, combined_md, flags=re.DOTALL)
    combined_md = re.sub(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)", _stash_inline, combined_md)

    html_body = md_lib.markdown(
        combined_md,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
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


def _register_print_route(app):
    @app.server.route("/course/print")
    def _course_print():
        # Optional ?chapter=CHNN-... param restricts to a single chapter so
        # MathJax only has to render ~500 spans (5s) instead of 9,000 (3 min).
        only = flask.request.args.get("chapter")
        return flask.Response(_build_print_html(only), mimetype="text/html")

    @app.server.route("/guide-figure/<path:rel>")
    def _guide_figure(rel):
        fp = (_FIG_DIR / rel).resolve()
        try:
            fp.relative_to(_FIG_DIR.resolve())
        except ValueError:
            flask.abort(404)
        if not fp.is_file():
            flask.abort(404)
        # Browser-cache for an hour — figures are content-addressed by filename.
        return flask.send_file(fp, max_age=3600)


# Register with the app — done at import time.
try:
    _register_print_route(dash.get_app())
except Exception:
    pass   # if called before app exists, user can wire manually
