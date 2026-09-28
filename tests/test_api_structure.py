"""Term-structure maths that doesn't need the network: constant-maturity interpolation and the GEX profile."""
import math

import numpy as np
import pandas as pd

from api.services.market import _gex_profile
from api.services.structure import _interp_iv


def test_constant_maturity_iv_interpolates_total_variance():
    pts = [{"dte": 20, "atm_iv": 0.10}, {"dte": 40, "atm_iv": 0.20}]
    iv30 = _interp_iv(pts, 30)
    w = (0.10 ** 2 * 20 + 0.20 ** 2 * 40) / 2          # halfway in total variance
    assert math.isclose(iv30, round(math.sqrt(w / 30), 4))
    assert _interp_iv(pts, 20) == 0.10
    assert _interp_iv(pts, 60) is None                   # no extrapolation


def test_gex_profile_is_positive_above_a_call_heavy_book_and_crosses_zero():
    # Dealers short calls above spot, long puts below (index convention): calls at 105 and puts at 95.
    chain = pd.DataFrame({"strike": [105.0, 95.0], "iv": [0.2, 0.2], "dte": [30, 30], "type": ["call", "put"]})
    cols = {"strike": "strike", "iv": "iv", "dte": "dte"}
    oi = np.array([10_000.0, 10_000.0])
    is_call = np.array([True, False])
    chain = pd.concat([chain] * 5, ignore_index=True)    # the profile needs >= 10 contracts
    oi, is_call = np.tile(oi, 5), np.tile(is_call, 5)
    p = _gex_profile(chain, cols, 100.0, gamma_fallback=None, oi=oi, is_call=is_call, span=0.10, n=21)
    assert p is not None and len(p["s"]) == 21
    assert p["gex"][-1] > 0 > p["gex"][0]                # call gamma dominates up top, put gamma below


def test_yield_surface_buckets_take_the_last_observed_day_and_fill_short_gaps_only():
    from api.services.structure import surface_rows
    idx = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-08",      # week ending Fri 01-09: last obs Thu 01-08
                          "2026-01-12", "2026-01-16",                    # week ending 01-16: Fri 01-16
                          "2026-01-30"])                                 # week ending 01-30 (01-19..01-23 has none)
    df = pd.DataFrame({"rate_2y": [4.0, 4.1, 4.2, 4.3, 4.4, 4.5],
                       "rate_10y": [4.5, 4.6, None, None, None, 4.9]}, index=idx)
    w = surface_rows(df, "1w")
    assert [d.date().isoformat() for d in w.index] == ["2026-01-08", "2026-01-16", "2026-01-30"]
    assert w["rate_2y"].tolist() == [4.2, 4.4, 4.5]
    # 10Y on 01-08 fills from 01-06 (2 days); on 01-16 the last 10Y print (01-06) is 10 days old: stays missing
    assert w["rate_10y"].iloc[0] == 4.6 and pd.isna(w["rate_10y"].iloc[1]) and w["rate_10y"].iloc[2] == 4.9
    m = surface_rows(df, "1m")
    assert [d.date().isoformat() for d in m.index] == ["2026-01-30"]
    d = surface_rows(df, "1d")
    assert len(d) == len(df)
    capped = surface_rows(pd.DataFrame({"rate_2y": range(1000)},
                                       index=pd.date_range("2020-01-01", periods=1000, freq="D")), "1d", max_rows=800)
    assert len(capped) == 800 and capped.index[-1] == pd.Timestamp("2020-01-01") + pd.Timedelta(days=999)
    import pytest
    with pytest.raises(ValueError):
        surface_rows(df, "2w")
