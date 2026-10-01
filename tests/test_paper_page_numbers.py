"""The Paper Trading page's money arithmetic, without a database: the figures must tie to cash."""
import pandas as pd


def _grp(rows):
    return pd.DataFrame(rows)


def test_net_entry_is_the_cash_moved_costs_included():
    from app.pages.paper_trading.data import _net_entry
    g = _grp([
        {"SecurityType": "Option", "Direction": "Buy", "Quantity": 1, "TransactionPrice": 76.22, "Multiplier": 100, "Amount": -3422.0},
        {"SecurityType": "Option", "Direction": "Sell", "Quantity": 1, "TransactionPrice": 42.02, "Multiplier": 100, "Amount": 0.0},
    ])
    assert _net_entry(g) == -3422.0                                   # the booked cash, commission included
    g2 = _grp([{"SecurityType": "Option", "Direction": "Buy", "Quantity": 1, "TransactionPrice": 10.0, "Multiplier": 100, "Amount": None}])
    assert _net_entry(g2) == -1000.0                                  # a manual row without Amount: price x qty x multiplier


def test_structure_label_reads_direction_off_the_legs():
    from app.pages.paper_trading.data import structure_label
    def two(kb, ks, t):
        return _grp([{"SecurityType": "Option", "Direction": "Buy", "Strike": kb, "OptionType": t},
                     {"SecurityType": "Option", "Direction": "Sell", "Strike": ks, "OptionType": t}])
    assert structure_label(two(30525, 30475, "Put")) == "Bear put 30475/30525"
    assert structure_label(two(30400, 30450, "Call")) == "Bull call 30400/30450"
    assert structure_label(two(30400, 30450, "Put")) == "Bull put 30400/30450"
    assert structure_label(two(30450, 30400, "Call")) == "Bear call 30400/30450"


def test_runner_marks_join_on_the_ledger_id():
    """The page keys a group 'NDX-NDX_0DTE-10029'; the runner records the bare id 10029."""
    from app.pages.paper_trading.data import runner_mark_for
    marks = {"10029": (36.1, 2.0, "tastytrade")}
    assert runner_mark_for(marks, "NDX-NDX_0DTE-10029") == (36.1, 2.0, "tastytrade")
    assert runner_mark_for(marks, "10029") == (36.1, 2.0, "tastytrade")
    assert runner_mark_for(marks, "NDX-NDX_0DTE-10030") is None


def test_closed_rows_are_built_once_and_relabelled_each_time(monkeypatch):
    """A closed trade never changes: its (slow) row is built once per process, keyed by the ledger's closed-row
    fields, while the strategy label is applied fresh (2026-10-01: 48 rows took 5-10 s, past the app's timeout)."""
    import pandas as pd
    from api.services import paper as PS
    built = []
    monkeypatch.setattr(PS, "_CLOSED_ROWS", {})
    monkeypatch.setattr(PS, "_closed_row", lambda r, t, l: built.append(r["TradeGroupId"]) or
                        {"trade_group_id": r["TradeGroupId"], "strategy": "s1", "strategy_label": "old", "pnl": 1.0})
    r = {"TradeGroupId": "G1", "P&L $": 10.0, "Close Date": "2026-10-01", "Net Entry": -5.0}
    a = PS._closed_row_cached(r, pd.DataFrame(), {"s1": "First"})
    b = PS._closed_row_cached(r, pd.DataFrame(), {"s1": "Renamed"})
    assert built == ["G1"] and a["strategy_label"] == "First" and b["strategy_label"] == "Renamed"
    PS._closed_row_cached({**r, "P&L $": 12.0}, pd.DataFrame(), {})          # a corrected trade is rebuilt
    assert built == ["G1", "G1"]
