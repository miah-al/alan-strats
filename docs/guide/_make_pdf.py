"""
Standalone PDF generator for the quant guide.
Uses Chrome --headless --print-to-pdf with a local HTML file.
Writes one PDF per chapter (fast) and optionally a combined full-guide PDF (slow).

Usage:
    python docs/guide/_make_pdf.py                # per-chapter PDFs
    python docs/guide/_make_pdf.py --full         # plus a combined PDF
    python docs/guide/_make_pdf.py --only CH07    # single chapter
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Make the Dash-app imports resolve from the repo root.
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from dash_app.pages.course import _build_print_html  # type: ignore

GUIDE = REPO / "docs" / "guide"
OUT = GUIDE / "pdf"
OUT.mkdir(exist_ok=True)

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).is_file():
            return c
    raise FileNotFoundError("Chrome/Edge not found in standard locations")


def html_to_pdf(html_path: Path, pdf_path: Path, virtual_ms: int = 90_000) -> None:
    """Use Chrome headless to render an HTML file (with MathJax CDN) to PDF.
    `virtual_ms` controls how long the browser waits for JS to finish."""
    chrome = find_chrome()
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        f"--virtual-time-budget={virtual_ms}",
        "--run-all-compositor-stages-before-draw",
        f"file:///{html_path.as_posix()}",
    ]
    subprocess.run(cmd, check=True)


def build_chapter(stem: str) -> Path:
    """Render one chapter to PDF; returns the PDF path."""
    html = _build_print_html(only_chapter=stem)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(html)
        html_path = Path(fh.name)
    try:
        pdf_path = OUT / f"{stem}.pdf"
        print(f"  rendering {stem} -> {pdf_path.name}")
        html_to_pdf(html_path, pdf_path, virtual_ms=30_000)
        return pdf_path
    finally:
        html_path.unlink(missing_ok=True)


def build_full() -> Path:
    """Render the entire combined guide to a single PDF."""
    html = _build_print_html()
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(html)
        html_path = Path(fh.name)
    try:
        pdf_path = OUT / "Quant-Guide-Full.pdf"
        print(f"  rendering full guide -> {pdf_path.name} (allow ~2 min)")
        html_to_pdf(html_path, pdf_path, virtual_ms=180_000)
        return pdf_path
    finally:
        html_path.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="also build combined full-guide PDF")
    ap.add_argument("--only", type=str, default=None,
                    help="render just one chapter (e.g. CH07)")
    args = ap.parse_args()

    if args.only:
        # Find the matching file
        matches = list(GUIDE.glob(f"{args.only}-*.md"))
        if not matches:
            print(f"No chapter matching {args.only}-*.md")
            sys.exit(1)
        build_chapter(matches[0].stem)
        return

    # Every chapter
    for p in sorted(GUIDE.glob("CH*.md")):
        build_chapter(p.stem)
    if args.full:
        build_full()
    print(f"\nDone. PDFs in {OUT}")


if __name__ == "__main__":
    main()
