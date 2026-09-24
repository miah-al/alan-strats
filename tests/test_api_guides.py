"""The guides library (/api/guides): catalogue, titles and summaries, link rewriting, file serving confined to a
guide's folder. The link and front-matter tests run on a temporary guides directory."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

BOOT = bootstrap()

from api.services import guides as G  # noqa: E402


def test_title_and_summary_rules():
    t, s, _ = G.title_and_summary("# Iron Condor\n### Selling Premium\n\n---\n\n## The Core Edge\nText.", "x")
    assert (t, s) == ("Iron Condor", "Selling Premium")
    t, s, _ = G.title_and_summary("## Jade Lizard\n\n### What It Is\nA jade lizard **combines** a [put](x.md).\n", "x")
    assert t == "Jade Lizard" and s == "A jade lizard combines a put."          # a section heading is not a subtitle
    t, s, m = G.title_and_summary("---\ntitle: Own Title\ncategory: Research\nsummary: Short.\n---\n# H\nBody", "x")
    assert (t, s, m["category"]) == ("Own Title", "Short.", "Research")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    d = tmp_path / "guides"
    (d / "playbooks").mkdir(parents=True)
    (d / "img").mkdir()
    (d / "img" / "chart.png").write_bytes(b"\x89PNG fake")
    (d / "alpha.md").write_text("# Alpha\n### Sub\n\n---\nSee [beta](beta.md#part), ![c](img/chart.png), "
                                "<img src=\"img/chart.png\"> and [gone](../../nowhere.py) and [web](https://x.org).\n",
                                encoding="utf-8")
    (d / "beta.md").write_text("---\ncategory: Research\n---\n# Beta\nFirst paragraph.\n", encoding="utf-8")
    (d / "playbooks" / "alpha.md").write_text("## Alpha Playbook\n\n### What It Is\nA playbook.\n", encoding="utf-8")
    (d / "secret.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(G, "GUIDES_DIR", d)
    monkeypatch.setattr(G, "COURSE_DIR", tmp_path / "no_course")
    return d


def test_catalogue_links_and_files(lib):
    rows = {r["slug"]: r for r in G.list_guides()}
    assert rows["alpha"]["category"] == "Guides" and rows["alpha"]["summary"] == "Sub"
    assert rows["beta"]["category"] == "Research" and rows["beta"]["summary"] == "First paragraph."
    assert rows["playbook:alpha"]["category"] == "Playbooks" and rows["playbook:alpha"]["summary"] == "A playbook."
    g = G.get("alpha", base="http://h:1")
    md = g["markdown"]
    assert "](http://h:1/api/guides/beta#part)" in md
    assert "](http://h:1/api/guides/alpha/files/img/chart.png)" in md
    assert 'src="http://h:1/api/guides/alpha/files/img/chart.png"' in md
    assert "(https://x.org)" in md and "(../../nowhere.py)" in md
    assert g["unresolved_links"] == ["../../nowhere.py"] and g["links_rewritten"] == 3
    assert G.file_path("alpha", "img/chart.png").name == "chart.png"
    for bad in ("../../etc/passwd", "secret.py", "img/none.png"):
        with pytest.raises(G.UnknownGuide):
            G.file_path("alpha", bad)
    with pytest.raises(G.UnknownGuide):
        G.get("nope")


def test_endpoints_on_the_real_library():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    try:
        with TestClient(create_app()) as c:
            rows = c.get("/api/guides").json()
            assert rows and {"slug", "title", "category", "summary"} <= set(rows[0])
            slugs = {r["slug"] for r in rows}
            assert {"iron_condor", "playbook:iron_condor"} <= slugs
            g = c.get("/api/guides/iron_condor").json()
            assert g["title"] == "Iron Condor" and g["markdown"].startswith("# Iron Condor") and g["category"] == "Guides"
            if BOOT.get("strategies_dir"):
                strat = [r for r in rows if r["category"] == "Strategies"]
                assert strat and all(r["slug"].startswith("strategy:") for r in strat)
                one = c.get(f"/api/guides/{strat[0]['slug']}").json()
                assert one["markdown"] and one["category"] == "Strategies"
            assert c.get("/api/guides/no_such_guide").status_code == 404
            assert c.get("/api/guides/iron_condor/files/..%2F..%2Fapi%2Fapp.py").status_code == 404
    finally:
        if not had:
            uninstall_db_read_only_guard()
