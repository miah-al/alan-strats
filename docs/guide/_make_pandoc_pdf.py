"""
Build consolidated PDF via pandoc + xelatex.
Uses native LaTeX math rendering — no JavaScript required, much faster than
Chrome/MathJax route for large documents.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

GUIDE = Path(__file__).resolve().parent
OUT = GUIDE / "pdf" / "Quant-Guide-Full.pdf"
OUT.parent.mkdir(exist_ok=True)


def main() -> None:
    try:
        import pypandoc
    except ImportError:
        print("Install: pip install pypandoc_binary", file=sys.stderr)
        sys.exit(1)

    def chapter_num(p: Path) -> int:
        # "Chapter-7-Greeks.md" -> 7; falls back to large number if no match
        m = re.match(r"Chapter-(\d+)-", p.name)
        return int(m.group(1)) if m else 999

    chapters = [GUIDE / "README.md"] + sorted(GUIDE.glob("Chapter-*.md"), key=chapter_num)
    print(f"Merging {len(chapters)} files...")

    parts = []
    for p in chapters:
        text = p.read_text(encoding="utf-8")
        # Convert ```math fences into $$ display math so pandoc treats them
        # as LaTeX, not code blocks.
        text = re.sub(
            r"```math\s*\n(.+?)\n```",
            lambda m: "\n\n$$\n" + m.group(1) + "\n$$\n\n",
            text,
            flags=re.DOTALL,
        )
        parts.append(text)

    combined = "\n\n\\newpage\n\n".join(parts)
    tmp_md = GUIDE / "_combined.md"
    tmp_md.write_text(combined, encoding="utf-8")
    print(f"combined markdown: {tmp_md.stat().st_size:,} bytes")

    try:
        print("running pandoc + xelatex (may take 2-5 min)...")
        pypandoc.convert_file(
            str(tmp_md),
            "pdf",
            outputfile=str(OUT),
            extra_args=[
                "--pdf-engine=xelatex",
                "-f", "markdown+raw_tex+tex_math_dollars",
                "-H", str(GUIDE / "_preamble.tex"),
                "-B", str(GUIDE / "_cover.tex"),
                "--variable", "title:",
                "--variable", "date:",
                "-V", "geometry:margin=0.75in",
                "-V", "fontsize=10pt",
                "-V", "colorlinks=true",
                "--toc",
                "--number-sections",
            ],
        )
        print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    finally:
        tmp_md.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
