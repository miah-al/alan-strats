"""
Build the consolidated PDF for "Binomial Option Pricing".

Two-step pipeline (cloned from docs/guide/_make_pandoc_pdf.py):
  1. pandoc converts merged markdown -> intermediate .tex
  2. regex-strips problematic `alt={...}` attributes that pandoc 3 auto-emits
     on every \\includegraphics
  3. xelatex compiles the cleaned .tex -> PDF

The book cover (figures/cover.png) and front-page _cover.tex are OPTIONAL — if
either is missing the build skips the cover insertion and produces a plain
title page. This keeps early-stage builds working before a cover exists.

Output: pdf/Binomial-Option-Pricing.pdf
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

BOOK = Path(__file__).resolve().parent
OUT = BOOK / "pdf" / "Binomial-Option-Pricing.pdf"
OUT.parent.mkdir(exist_ok=True)


def convert_longtables_to_tabular(tex: str) -> str:
    """Convert pandoc-emitted `longtable` environments to `table+tabular`
    so short tables don't paginate. Also strips `\\noalign{}`, `\\endhead`,
    `\\endlastfoot`, and the `>{\\raggedleft\\arraybackslash}p{...}` column
    specs (replaced with simple `c` cells centered)."""
    # Pattern: capture column spec and body of each longtable
    pat = re.compile(
        r"\\begin\{longtable\}\[\]\{@\{\}(.*?)@\{\}\}(.*?)\\end\{longtable\}",
        re.DOTALL,
    )

    def simplify_colspec(spec: str) -> str:
        """If pandoc emitted complex column specs like `>{\\raggedright...}p{...}`,
        replace each with a single-letter alignment. Default to 'c' (centered)."""
        spec = spec.strip()
        # Detect simple form like 'llrc'
        if re.fullmatch(r"[lrc]+", spec):
            return spec
        # Detect complex form: one or more `>{...}p{...}` blocks
        blocks = re.findall(
            r">\{\\raggedleft\\arraybackslash\}p\{[^}]+(?:\{[^}]*\}[^}]*)*\}|"
            r">\{\\raggedright\\arraybackslash\}p\{[^}]+(?:\{[^}]*\}[^}]*)*\}|"
            r">\{\\centering\\arraybackslash\}p\{[^}]+(?:\{[^}]*\}[^}]*)*\}",
            spec,
        )
        if blocks:
            out = ""
            for b in blocks:
                if "raggedleft" in b:
                    out += "r"
                elif "centering" in b:
                    out += "c"
                else:
                    out += "l"
            return out
        # Fallback: count cells by looking at first body row
        return "c"

    def repl(m: "re.Match") -> str:
        col_spec_raw = m.group(1)
        body = m.group(2)
        col_spec = simplify_colspec(col_spec_raw)
        # Strip longtable-specific directives
        body = re.sub(r"\\noalign\{\}", "", body)
        body = re.sub(r"\\endhead\b", "", body)
        body = re.sub(r"\\endfirsthead\b", "", body)
        body = re.sub(r"\\endlastfoot\b", "", body)
        body = re.sub(r"\\endfoot\b", "", body)
        # Pandoc puts \bottomrule BEFORE the body rows (because longtable's
        # \endlastfoot defines the bottom-of-table content as a directive
        # near the top). For a plain tabular we want it AFTER the body rows.
        # Strip it from wherever it appears in the body and append it at the
        # very end ourselves.
        body = re.sub(r"\\bottomrule", "", body)
        body = body.rstrip() + "\n\\bottomrule"
        # Strip the `\begin{minipage}[b]{\linewidth}\raggedleft ... \end{minipage}`
        # wrappers in header cells: keep just the inner content.
        body = re.sub(
            r"\\begin\{minipage\}\[[bt]\]\{[^}]+\}\s*"
            r"(?:\\(?:raggedleft|raggedright|centering))?\s*(.*?)\s*\\end\{minipage\}",
            r"\1",
            body,
            flags=re.DOTALL,
        )
        # Keep vertical column separators ("|" between every column).
        col_spec_v = "|" + "|".join(col_spec) + "|"
        # Booktabs rules ONLY at top, header/body boundary, and bottom — NO
        # per-row hlines. The original \toprule/\midrule/\bottomrule are kept;
        # we don't substitute with \hline (which would put a line on EVERY row).
        return (
            "\\begin{table}[H]\n"
            "\\centering\n"
            "\\begin{tabular}{" + col_spec_v + "}\n"
            + body.strip()
            + "\n\\end{tabular}\n"
            "\\end{table}"
        )

    return pat.sub(repl, tex)


def strip_alt_attributes(tex: str) -> str:
    """Remove `alt={...}` from \\includegraphics options (pandoc 3 workaround)."""
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
    fm = BOOK / "_frontmatter.md"
    if fm.exists():
        front.append(fm)
    readme = BOOK / "README.md"
    if readme.exists():
        front.append(readme)
    chapters = front + sorted(BOOK.glob("Chapter-*.md"), key=chapter_num)
    if not chapters:
        print("No chapter files found; nothing to build.", file=sys.stderr)
        sys.exit(1)
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
    tmp_md = BOOK / "_combined.md"
    tmp_md.write_text(combined, encoding="utf-8")
    print(f"combined markdown: {tmp_md.stat().st_size:,} bytes")

    tmp_tex = BOOK / "_combined.tex"

    # Cover is optional — only pass -B if both PNG and TeX wrapper exist.
    cover_tex = BOOK / "_cover.tex"
    extra = [
        "-f", "markdown+raw_tex+tex_math_dollars",
        "-H", str(BOOK / "_preamble.tex"),
        "--resource-path", str(BOOK),
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
    ]
    if cover_tex.exists():
        extra[2:2] = ["-B", str(cover_tex)]

    try:
        print("step 1: pandoc -> tex ...")
        pypandoc.convert_file(str(tmp_md), "latex", outputfile=str(tmp_tex),
                              extra_args=extra)
        print(f"  wrote {tmp_tex.name} ({tmp_tex.stat().st_size:,} bytes)")

        print("step 2: stripping alt={...} from \\includegraphics ...")
        original = tmp_tex.read_text(encoding="utf-8")
        cleaned = strip_alt_attributes(original)
        removed = original.count("alt={") - cleaned.count("alt={")
        print(f"  removed {removed} alt= attributes")

        # Convert paginating longtable to floating tabular and add vertical
        # column separators so column boundaries are visually obvious.
        n_lt = cleaned.count("\\begin{longtable}")
        cleaned = convert_longtables_to_tabular(cleaned)
        print(f"  converted {n_lt} longtable -> table+tabular (vertical rules added)")

        tmp_tex.write_text(cleaned, encoding="utf-8")

        def run_xelatex(pass_num: int) -> None:
            r = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 f"-output-directory={BOOK}", str(tmp_tex)],
                cwd=str(BOOK), capture_output=True,
                encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                log_path = BOOK / "_combined.log"
                if log_path.exists():
                    log = log_path.read_text(encoding="utf-8", errors="replace")
                    err_idx = log.find("\n! ")
                    snippet = log[err_idx:err_idx + 4000] if err_idx >= 0 else log[-3000:]
                    print(f"xelatex pass {pass_num} failed:\n{snippet}", file=sys.stderr)
                else:
                    tail = (r.stdout or r.stderr or "")[-3000:]
                    print(f"xelatex pass {pass_num} failed:\n{tail}", file=sys.stderr)
                sys.exit(1)
            print(f"  pass {pass_num} ok")

        def extract_toc_from_aux(aux_path: Path) -> str:
            """Extract `\\@writefile{toc}{...}` payloads from .aux and emit
            them as a .toc file. Pandoc-generated documents end up with empty
            .toc files even after two xelatex passes because xelatex's
            \\enddocument-time re-read of .aux does not write back to the
            already-truncated .toc handle. We bypass that bug here."""
            if not aux_path.exists():
                return ""
            text = aux_path.read_text(encoding="utf-8", errors="replace")
            needle = "\\@writefile{toc}{"
            entries: list[str] = []
            i = 0
            while i < len(text):
                idx = text.find(needle, i)
                if idx < 0:
                    break
                j = idx + len(needle)
                start = j
                depth = 1
                while j < len(text) and depth > 0:
                    ch = text[j]
                    if ch == "\\" and j + 1 < len(text):
                        j += 2
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            entries.append(text[start:j])
                            break
                    j += 1
                i = j + 1
            return "\n".join(entries) + ("\n" if entries else "")

        print("step 3: xelatex -> pdf (two passes for TOC) ...")
        run_xelatex(1)
        # TOC manual injection: pass 1 produced .aux with writefile entries
        # but .toc is empty. Inject before pass 2 so the TOC renders correctly.
        aux = BOOK / "_combined.aux"
        toc = BOOK / "_combined.toc"
        toc_payload = extract_toc_from_aux(aux)
        if toc_payload.strip():
            toc.write_text(toc_payload, encoding="utf-8")
            print(f"  injected {toc_payload.count(chr(10))} TOC entries into _combined.toc")
        else:
            print("  WARNING: no TOC entries found in _combined.aux", file=sys.stderr)
        run_xelatex(2)
        # Pass 2 truncates the injected .toc when \tableofcontents fires;
        # re-inject so the file on disk also reflects the final TOC for
        # downstream readers.
        toc_payload2 = extract_toc_from_aux(aux)
        if toc_payload2.strip():
            toc.write_text(toc_payload2, encoding="utf-8")

        built_pdf = BOOK / "_combined.pdf"
        if built_pdf.exists():
            built_pdf.replace(OUT)
            print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
        else:
            print("WARNING: expected _combined.pdf not found", file=sys.stderr)
    finally:
        tmp_md.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
