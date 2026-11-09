"""The nested chain is parsed root by root: one malformed root must not take the underlying's good roots with it.

2026-11-09: tastytrade's SPX nested chain carried an SPXO root without ``tick-sizes``. ``NestedOptionChain.get``
validates the whole list, so every SPX chain, straddle and surface failed over to stale yfinance quotes. Fakes only:
no tastytrade calls.
"""
import logging
from datetime import date

from api.marketdata.providers.tastytrade import parse_nested_chains


def _root(root: str, expiry: str, k: int, ticks: bool = True) -> dict:
    ymd = expiry[2:].replace("-", "")
    item = {
        "underlying-symbol": "SPX", "root-symbol": root, "option-chain-type": "Standard", "shares-per-contract": 100,
        "expirations": [{
            "expiration-type": "Weekly", "expiration-date": expiry, "days-to-expiration": 0, "settlement-type": "PM",
            "strikes": [{"strike-price": str(k),
                         "call": f"{root:<6}{ymd}C{k * 1000:08d}", "put": f"{root:<6}{ymd}P{k * 1000:08d}",
                         "call-streamer-symbol": f".{root}{ymd}C{k}", "put-streamer-symbol": f".{root}{ymd}P{k}"}],
        }],
    }
    if ticks:
        item["tick-sizes"] = [{"value": "0.05", "threshold": "3"}, {"value": "0.1"}]
    return item


def test_a_root_without_tick_sizes_is_skipped_and_the_others_kept(caplog):
    data = {"items": [_root("SPX", "2026-11-20", 7500), _root("SPXW", "2026-11-09", 7495),
                      _root("SPXO", "2026-12-16", 9400, ticks=False)]}
    with caplog.at_level(logging.WARNING):
        chains = parse_nested_chains(data, "SPX")
    assert [c.root_symbol for c in chains] == ["SPX", "SPXW"]
    spxw = chains[1].expirations[0]
    assert spxw.expiration_date == date(2026, 11, 9)
    assert spxw.strikes[0].call_streamer_symbol == ".SPXW261109C7495"
    assert "skipped 1 malformed root(s): SPXO (ValidationError)" in caplog.text


def test_a_clean_chain_parses_whole_and_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        chains = parse_nested_chains({"items": [_root("NDXP", "2026-11-09", 27600)]}, "NDX")
    assert [c.root_symbol for c in chains] == ["NDXP"]
    assert caplog.text == ""


def test_an_empty_or_missing_payload_gives_no_roots():
    assert parse_nested_chains({}, "SPX") == []
    assert parse_nested_chains({"items": []}, "SPX") == []
    assert parse_nested_chains(None, "SPX") == []
