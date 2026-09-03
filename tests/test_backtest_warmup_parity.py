import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
"""
Regression tests for the four CRITICAL defects found in the 2026-08-01 edge
review. Each one produced plausible-looking output while being wrong, which is
why they survived: none of them crashed.
"""

import numpy as np
import pandas as pd
import pytest


def test_backtest_tab_uses_the_same_warmup_as_performance():
    """
    The warm-up fix reached rank_strategies.py and performance.py but not
    backtest_view.py, so the two tabs disagreed on identical inputs
    (ts_momentum 12.05% vs 15.20% CAGR; vix_term_structure flipped sign).
    """
    from alan_trader.app.pages.strategies import backtest_view as bv
    from alan_trader.app.pages.strategies import performance as perf

    assert bv._WARMUP_DAYS == perf.WARMUP_DAYS, (
        f"warm-up differs: backtest_view={bv._WARMUP_DAYS} vs "
        f"performance={perf.WARMUP_DAYS}"
    )
