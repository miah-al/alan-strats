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
