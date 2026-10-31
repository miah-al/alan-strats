"""
StrategyPlugin — what a strategy package publishes to the platform.

A plugin package exposes a module-level ``PLUGIN`` object (or registers an
entry point in the ``alan_trader.strategies`` group that resolves to one).
The platform reads only this object; it never imports strategy modules by
name. Everything strategy-specific — metadata, model artifacts, guide
articles, scope documents, tests — is located through the paths declared here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class StrategyPlugin:
    #: Unique plugin name (used to de-duplicate discovery).
    name: str
    #: ``slug -> metadata`` for every strategy the plugin provides. Each entry is
    #: the same shape the registry has always used (display_name, type, status,
    #: class_path, ...) plus the optional UI keys documented in
    #: ``strategy_api.ui``: ui, ui_visible, ui_label, review_status, score, loaders.
    metadata: dict[str, dict]
    #: Root of the plugin checkout (informational; used for the Test tab cwd).
    root: Optional[Path] = None
    #: Where this plugin's persisted model artifacts live.
    model_dir: Optional[Path] = None
    #: Directory holding scope documents (``strategy_scope.md``, ``reviews/``).
    docs_dir: Optional[Path] = None
    #: Directory holding guide articles named ``<slug>.md``.
    guide_dir: Optional[Path] = None
    #: ``article slug -> importable module`` exposing ``render_charts()`` for
    #: interactive charts under a guide article.
    guide_charts: dict[str, str] = field(default_factory=dict)
    #: Directory holding the plugin's pytest suite (for the Test tab).
    tests_dir: Optional[Path] = None
    version: str = ""

    def slugs(self) -> list[str]:
        return list(self.metadata.keys())

    def __post_init__(self) -> None:
        for attr in ("root", "model_dir", "docs_dir", "guide_dir", "tests_dir"):
            v = getattr(self, attr)
            if v is not None and not isinstance(v, Path):
                setattr(self, attr, Path(v))
