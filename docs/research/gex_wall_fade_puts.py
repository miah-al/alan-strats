"""The call-wall fade booked as the bear put spread: what the substitution costs, priced on the put prints.

    python docs/research/gex_wall_fade_puts.py [--out puts.json]

For every trade of the chosen variant (map B, 11:00-15:00, B50, held to settlement) in gex_wall_fade.py's backtest:
the call credit spread's entry (short wall+25 / long wall+75 calls, their first prints in the 3 minutes after the
trigger) next to the same-strike bear put spread's (long wall+75 / short wall+25 puts, their first prints in the
same window). By parity the put debit should be 50 - the call credit; the gap is what the in-the-money puts'
thinner, wider prints cost (or give). P&L per trade both ways, before slippage and commission. Read only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gex_wall_fade as F  # noqa: E402
import gex_walls as GW  # noqa: E402
import gex_edge as GE  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-10-01")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    from api.bootstrap import bootstrap
    bootstrap()
    GE.strict_read_only()
    since = _dt.date.fromisoformat(a.since)
    opt = F.option_prints(since)
    m = GE.minutes("NDX", since)
    vx = GW.vxn_prev(since)
    by_day = {d: x for d, x in opt.groupby("day")}
    ss = []
    for day, b in m.groupby("day"):
        o = by_day.get(day)
        bars = GW.session_arrays(b)
        if o is None or bars is None or o["volume"].sum() <= 0:
            continue
        ss.append(F.Session(day, bars, o, (vx.get(day) or 20.0) / 100.0))
    trades = F.run(ss, "wall", "B", "11-15", "B", 50.0, "hold")
    sess = {s.day: s for s in ss}
    rows = []
    for t in trades:
        s = sess[t["day"]]
        wall = float(t["strike"])
        ks, kl = wall + 25.0, wall + 75.0
        i = int(t["i"])
        ps, pl = s.fill(False, ks, i + 1), s.fill(False, kl, i + 1)       # short / long put
        call_credit = t["credit"]
        settle = float(s.c[-1])
        call_value = min(max(settle - ks, 0.0), 50.0)
        row = {"day": str(t["day"]), "minute": F.GW.N_MIN and (570 + i + 1), "wall": wall, "call_credit": call_credit,
               "call_pnl": (call_credit - call_value) * 100.0, "put_debit": None, "put_pnl": None, "gap_pts": None}
        if ps is not None and pl is not None:
            debit = pl[0] - ps[0]
            put_value = min(max(kl - settle, 0.0), 50.0)
            row.update(put_debit=debit, put_pnl=(put_value - debit) * 100.0, gap_pts=debit - (50.0 - call_credit))
        rows.append(row)
    both = [r for r in rows if r["gap_pts"] is not None]

    def part(xs, lo, hi):
        return [r for r in xs if lo <= _dt.date.fromisoformat(r["day"]) <= hi]

    def stat(xs):
        if not xs:
            return {"n": 0}
        g = np.array([r["gap_pts"] for r in xs])
        return {"n": len(xs), "gap_mean_pts": float(g.mean()), "gap_median_pts": float(np.median(g)),
                "gap_per_leg_mean": float(g.mean() / 2), "gap_p90_pts": float(np.percentile(g, 90)),
                "call_pnl_mean": float(np.mean([r["call_pnl"] for r in xs])),
                "put_pnl_mean": float(np.mean([r["put_pnl"] for r in xs]))}
    res = {"trades": len(rows), "with_put_prints": len(both),
           "put_fill_rate": len(both) / len(rows) if rows else None,
           "all": stat(both), "in_sample": stat(part(both, _dt.date(2000, 1, 1), F.IS_END)),
           "out_of_sample": stat(part(both, F.IS_END + _dt.timedelta(days=1), _dt.date(2100, 1, 1))),
           "rows": rows}
    txt = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
