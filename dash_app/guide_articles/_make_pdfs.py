"""
Consolidated PDF builder for strategy guides — one PDF with cover + TOC +
all 89 guides concatenated in sorted order.
Usage:  python dash_app/guide_articles/_make_pdfs.py
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT_DIR = HERE / "pdf"
OUT_DIR.mkdir(exist_ok=True)
COVER_PNG = REPO / "docs" / "guide" / "figures" / "strategy_cover.png"
PREAMBLE = REPO / "docs" / "guide" / "_preamble.tex"


def main() -> None:
    try:
        import pypandoc
    except ImportError:
        print("pip install pypandoc_binary", file=sys.stderr)
        sys.exit(1)

    # Build cover.tex on the fly using the absolute path to the PNG.
    cover_tex = HERE / "_cover.tex"
    cover_tex.write_text(
        "\\AddToShipoutPictureBG*{%\n"
        f"  \\includegraphics[width=\\paperwidth,height=\\paperheight,keepaspectratio=false]{{{COVER_PNG.as_posix()}}}%\n"
        "}\n"
        "\\thispagestyle{empty}\n"
        "\\null\\clearpage\n",
        encoding="utf-8",
    )

    # Collect + concatenate all markdown guides in sorted order.
    guides = sorted(p for p in HERE.glob("*.md") if not p.name.startswith("_"))
    print(f"Merging {len(guides)} guides -> one PDF")

    chunks = []
    for p in guides:
        title = p.stem.replace("_", " ").replace("-", " ").title()
        text = p.read_text(encoding="utf-8")
        # If the file does not start with an H1, add one using the stem.
        if not re.match(r"^#\s", text):
            text = f"# {title}\n\n" + text
        # Convert ```math fences to $$ display math.
        text = re.sub(
            r"```math\s*\n(.+?)\n```",
            lambda m: "\n\n$$\n" + m.group(1) + "\n$$\n\n",
            text,
            flags=re.DOTALL,
        )
        chunks.append(text)

    combined = "\n\n\\newpage\n\n".join(chunks)
    tmp = HERE / "_combined.md"
    tmp.write_text(combined, encoding="utf-8")
    print(f"  combined markdown: {tmp.stat().st_size:,} bytes")

    pdf_path = OUT_DIR / "Strategy-Playbook.pdf"
    try:
        print("  running pandoc + xelatex (may take 5-10 min)...")
        pypandoc.convert_file(
            str(tmp), "pdf",
            outputfile=str(pdf_path),
            extra_args=[
                "--pdf-engine=xelatex",
                "-f", "markdown+raw_tex+tex_math_dollars",
                "-H", str(PREAMBLE),
                "-B", str(cover_tex),
                "--toc",
                "--number-sections",
                "-V", "geometry:margin=0.75in",
                "-V", "fontsize=10pt",
                "-V", "colorlinks=true",
                "-V", "title:",
                "-V", "date:",
            ],
        )
        print(f"  wrote {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
    finally:
        tmp.unlink(missing_ok=True)
        cover_tex.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
