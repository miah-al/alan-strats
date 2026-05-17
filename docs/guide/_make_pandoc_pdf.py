"""
Build consolidated PDF via pandoc + xelatex.

Two-step pipeline:
  1. pandoc converts merged markdown -> intermediate .tex
  2. regex-strips problematic `alt={...}` attributes that pandoc 3 auto-emits
     on every \\includegraphics (the auto-generated alt re-escapes math chars
     in a way that breaks graphicx's keyval parser inside xelatex)
  3. xelatex compiles the cleaned .tex -> PDF

Step 2 is the workaround for the pandoc-3 / xelatex / unicode-math interaction:
pandoc 3 emits `\\includegraphics[keepaspectratio,alt={...}]{...}` where the
alt value contains `\\textbackslash`, `\\{`, `\\}`, `\\^{}` sequences derived
from caption math like $\\kappa^\\mathbb{Q}$. Inside graphicx's keyval parser
these escape sequences mis-balance braces and propagate as a `Missing {
inserted` error far down the document. Sizing comes from
`\\setkeys{Gin}{width=\\linewidth,keepaspectratio}` set in _preamble.tex.
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

GUIDE = Path(__file__).resolve().parent
OUT = GUIDE / "pdf" / "Quant-Guide-Full.pdf"
OUT.parent.mkdir(exist_ok=True)


def strip_alt_attributes(tex: str) -> str:
    """Remove `alt={...}` from \\includegraphics options.

    Walks the text manually to handle balanced braces and `\\{`/`\\}` escapes
    inside the alt value (which a regex cannot match correctly).
    """
    out = []
    i = 0
    needle = "alt={"
    while i < len(tex):
        idx = tex.find(needle, i)
        if idx < 0:
            out.append(tex[i:])
            break
        out.append(tex[i:idx])
        j = idx + len(needle)
        depth = 1
        while j < len(tex) and depth > 0:
            ch = tex[j]
            if ch == "\\" and j + 1 < len(tex):
                j += 2
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            j += 1
        if j < len(tex) and tex[j] == ",":
            j += 1
        if out and out[-1].endswith(","):
            out[-1] = out[-1][:-1]
        i = j
    return "".join(out)


def main() -> None:
    try:
        import pypandoc
    except ImportError:
        print("Install: pip install pypandoc_binary", file=sys.stderr)
        sys.exit(1)

    def chapter_num(p: Path) -> int:
        m = re.match(r"Chapter-(\d+)-", p.name)
        return int(m.group(1)) if m else 999

    front = []
    fm = GUIDE / "_frontmatter.md"
    if fm.exists():
        front.append(fm)
    front.append(GUIDE / "README.md")
    chapters = front + sorted(GUIDE.glob("Chapter-*.md"), key=chapter_num)
    print(f"Merging {len(chapters)} files...")

    parts = []
    for p in chapters:
        text = p.read_text(encoding="utf-8")
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

    tmp_tex = GUIDE / "_combined.tex"
    try:
        print("step 1: pandoc -> tex ...")
        pypandoc.convert_file(
            str(tmp_md),
            "latex",
            outputfile=str(tmp_tex),
            extra_args=[
                "-f", "markdown+raw_tex+tex_math_dollars",
                "-H", str(GUIDE / "_preamble.tex"),
                "-B", str(GUIDE / "_cover.tex"),
                "--resource-path", str(GUIDE),
                "--variable", "title:",
                "--variable", "date:",
                "-V", "geometry:paperwidth=6in,paperheight=9in,inner=0.75in,outer=0.5in,top=0.6in,bottom=0.6in",
                "-V", "fontsize=10pt",
                "-V", "documentclass=book",
                "-V", "classoption=twoside",
                "-V", "colorlinks=true",
                "--standalone",
                "--toc",
                "--toc-depth=2",
            ],
        )
        print(f"  wrote {tmp_tex.name} ({tmp_tex.stat().st_size:,} bytes)")

        print("step 2: stripping alt={...} from \\includegraphics ...")
        original = tmp_tex.read_text(encoding="utf-8")
        cleaned = strip_alt_attributes(original)
        removed = original.count("alt={") - cleaned.count("alt={")
        tmp_tex.write_text(cleaned, encoding="utf-8")
        print(f"  removed {removed} alt= attributes")

        print("step 3: xelatex -> pdf (two passes for TOC) ...")
        for pass_num in (1, 2):
            r = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 f"-output-directory={GUIDE}", str(tmp_tex)],
                cwd=str(GUIDE), capture_output=True,
                encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                log_path = GUIDE / "_combined.log"
                if log_path.exists():
                    log = log_path.read_text(encoding="utf-8", errors="replace")
                    # Print the lines around the first '! ' error marker
                    err_idx = log.find("\n! ")
                    if err_idx >= 0:
                        snippet = log[err_idx:err_idx + 4000]
                    else:
                        snippet = log[-3000:]
                    print(f"xelatex pass {pass_num} failed (from _combined.log):\n{snippet}", file=sys.stderr)
                else:
                    tail = (r.stdout or r.stderr or "")[-3000:]
                    print(f"xelatex pass {pass_num} failed:\n{tail}", file=sys.stderr)
                sys.exit(1)
            print(f"  pass {pass_num} ok")

        # Move the produced PDF to final location
        built_pdf = GUIDE / "_combined.pdf"
        if built_pdf.exists():
            built_pdf.replace(OUT)
            print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
        else:
            print("WARNING: expected _combined.pdf not found", file=sys.stderr)
    finally:
        tmp_md.unlink(missing_ok=True)
        # Auxiliary cleanup only; keep .tex and .log for inspection


if __name__ == "__main__":
    main()
