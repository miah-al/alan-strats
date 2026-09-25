"""Does the paper runner's replay of ndx_gamma_walls reproduce the backtest's trades?

    python docs/research/gex_wall_fade_replay_check.py [--since 2026-06-01] [--days 16] [--out check.json]

Runs gex_wall_fade.py's chosen variant (map B, 11:00-15:00, B50, hold) over the window, then the platform's
paper runner in replay (scripts.paper_runner's PaperSession + ReplayProvider, no ledger) of the strategy on the
same days, and lines the trades up: signal bar, wall, strikes, entry minute, the entry price (the booked put
spread's debit vs 50 - the backtest's call credit) and P&L. Read only (the runner writes its CSV log and state
file to a scratch folder).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gex_edge as GE  # noqa: E402
import gex_wall_fade as F  # noqa: E402
import gex_walls as GW  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-06-01")
    ap.add_argument("--days", type=int, default=16)
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
    bt = F.run(ss, "wall", "B", "11-15", "B", 50.0, "hold")
    bt_days = {t["day"]: t for t in bt}
    traded = sorted(bt_days)[-a.days:]
    quiet = [s.day for s in ss if s.day not in bt_days][-4:]
    from db.client import get_engine
    from paper.providers import ReplayProvider
    from paper.runner import PaperSession
    eng = get_engine()
    tmp = Path(tempfile.mkdtemp(prefix="walls_replay_"))
    rows = []
    for day in sorted(traded + quiet):
        prov = ReplayProvider(eng, "NDX", day, half_spread=0.5, root="NDXP")
        ps = PaperSession("ndx_gamma_walls", prov, eng, write_ledger=False, log_dir=tmp, state_dir=tmp)
        res = ps.run_replay(day)
        rp = res.trades[0] if res.trades else None
        b = bt_days.get(day)
        row = {"day": str(day), "backtest": None, "replay": None}
        if b is not None:
            row["backtest"] = {"signal_min": 570 + int(b["i"]) + 1, "wall": b["strike"], "entry_min": 570 + int(b["entry_i"]) + 1,
                               "call_credit": round(b["credit"], 2), "put_equiv_debit": round(50 - b["credit"], 2),
                               "pnl_before_costs": round(b["pnl0"], 0)}
        if rp is not None:
            sig = next((f for f in res.fills if f["kind"] == "rest"), None)
            row["replay"] = {"signal_min": sig["m"] if sig else None, "wall": rp.get("wall"),
                             "entry_min": int(rp["entry_time"][:2]) * 60 + int(rp["entry_time"][3:]),
                             "put_debit": rp["entry_px"], "pnl": rp["pnl"], "strikes": [rp["k_low"], rp["k_high"]]}
        else:
            row["replay_fills"] = [f for f in res.fills if f["kind"] in ("rest", "cancel")]
        if row["backtest"] and row["replay"]:
            same = (row["backtest"]["wall"] == row["replay"]["wall"]
                    and row["backtest"]["signal_min"] == row["replay"]["signal_min"])
            row["same_signal"] = same
            row["debit_gap_pts"] = round(row["replay"]["put_debit"] - F.SLIPS[1] * 2 - row["backtest"]["put_equiv_debit"], 2)
        rows.append(row)
    both = [r for r in rows if r.get("backtest") and r.get("replay")]
    summary = {"days": len(rows), "backtest_trades": sum(1 for r in rows if r["backtest"]),
               "replay_trades": sum(1 for r in rows if r["replay"]), "matched": len(both),
               "same_signal": sum(1 for r in both if r["same_signal"]),
               "mean_debit_gap_pts": (sum(r["debit_gap_pts"] for r in both) / len(both)) if both else None,
               "backtest_only": [r["day"] for r in rows if r["backtest"] and not r["replay"]],
               "replay_only": [r["day"] for r in rows if r["replay"] and not r["backtest"]]}
    out = {"summary": summary, "rows": rows}
    txt = json.dumps(out, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
