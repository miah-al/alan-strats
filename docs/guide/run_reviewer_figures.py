"""
Extract every ```python``` fenced code block from the reviewed chapters and
execute each one in a fresh namespace so it produces the PNG it references.
"""
from __future__ import annotations
import os, re, sys, glob, traceback
import io
import contextlib

sys.stdout.reconfigure(encoding="utf-8")

GUIDE_DIR = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.join(GUIDE_DIR, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# NumPy 2.x removed np.trapz → np.trapezoid; shim for old code from reviewers.
import numpy as _np
if not hasattr(_np, "trapz"):
    _np.trapz = _np.trapezoid

# Ensure relative `docs/guide/figures/...` paths in the embedded code resolve
# from the project root. Change CWD to the project root (parent of docs/).
PROJECT_ROOT = os.path.abspath(os.path.join(GUIDE_DIR, os.pardir, os.pardir))
os.chdir(PROJECT_ROOT)

FENCE_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)

summary = {"ok": 0, "fail": 0, "no_save": 0}
failures = []

for md_path in sorted(glob.glob(os.path.join(GUIDE_DIR, "CH*.md"))):
    name = os.path.basename(md_path)
    with open(md_path, "r", encoding="utf-8") as f:
        body = f.read()
    blocks = FENCE_RE.findall(body)
    if not blocks:
        continue
    print(f"\n=== {name}: {len(blocks)} python blocks ===")
    for i, code in enumerate(blocks, 1):
        if "savefig" not in code:
            print(f"  block {i}: no savefig, skipping")
            summary["no_save"] += 1
            continue
        # Matplotlib mathtext doesn't support a few LaTeX shortcuts.
        code = code.replace(r"\tfrac", r"\frac")
        code = code.replace(r"\dfrac", r"\frac")
        # \frac12 (no braces) → \frac{1}{2}
        code = re.sub(r"\\frac(\d)(\d)", r"\\frac{\1}{\2}", code)
        ns = {"__name__": "__main__", "__file__": md_path}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                exec(code, ns)
            print(f"  block {i}: OK")
            summary["ok"] += 1
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
            print(f"  block {i}: FAIL — {msg}")
            summary["fail"] += 1
            failures.append((name, i, msg))

print(f"\n=== summary ===")
print(f"  OK:       {summary['ok']}")
print(f"  FAIL:     {summary['fail']}")
print(f"  no-save:  {summary['no_save']}")
if failures:
    print(f"\n=== failures ===")
    for n, i, m in failures:
        print(f"  {n} block {i}: {m}")

print(f"\nFigures written under {FIG_DIR}")
print(f"Total PNGs now: {len([f for f in os.listdir(FIG_DIR) if f.endswith('.png')])}")
