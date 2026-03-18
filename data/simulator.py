"""
Simulated market data generator.
Produces realistic price, VIX, rates, and news sentiment data
using GBM for price, mean-reversion for VIX, and correlated noise.
No API key needed — use this for testing and demos.
Supports any ticker via TICKER_PROFILES; defaults to SPY-like behaviour.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta


# ── Per-ticker simulation profiles ────────────────────────────────────────────
TICKER_PROFILES: dict[str, dict] = {
    # Broad market ETFs
    "SPY":  {"start_price": 500.0, "annual_vol": 0.18, "annual_drift": 0.08,
             "category": "etf",         "sector_peers": ["QQQ", "IWM", "DIA", "VTI", "GLD"]},
    "QQQ":  {"start_price": 450.0, "annual_vol": 0.22, "annual_drift": 0.10,
             "category": "etf",         "sector_peers": ["SPY", "IWM", "ARKK", "XLK", "SMH"]},
    "IWM":  {"start_price": 200.0, "annual_vol": 0.24, "annual_drift": 0.07,
             "category": "etf",         "sector_peers": ["SPY", "QQQ", "DIA", "MDY", "IJR"]},
    "DIA":  {"start_price": 380.0, "annual_vol": 0.16, "annual_drift": 0.07,
             "category": "etf",         "sector_peers": ["SPY", "QQQ", "IWM", "XLF", "XLI"]},
    "GLD":  {"start_price": 185.0, "annual_vol": 0.14, "annual_drift": 0.04,
             "category": "commodity",   "sector_peers": ["SLV", "GDX", "GDXJ", "IAU", "RING"]},
    "SLV":  {"start_price":  25.0, "annual_vol": 0.28, "annual_drift": 0.03,
             "category": "commodity",   "sector_peers": ["GLD", "GDX", "SIVR", "PPLT", "PALL"]},
    "TLT":  {"start_price":  95.0, "annual_vol": 0.15, "annual_drift": 0.01,
             "category": "fixed_income","sector_peers": ["IEF", "SHY", "AGG", "BND", "HYG"]},
    "HYG":  {"start_price":  76.0, "annual_vol": 0.08, "annual_drift": 0.04,
             "category": "fixed_income","sector_peers": ["TLT", "LQD", "JNK", "AGG", "BND"]},
    # Large-cap tech
    "AAPL": {"start_price": 175.0, "annual_vol": 0.26, "annual_drift": 0.12,
             "category": "tech",        "sector_peers": ["MSFT", "GOOGL", "META", "AMZN", "NVDA"]},
    "MSFT": {"start_price": 380.0, "annual_vol": 0.24, "annual_drift": 0.14,
             "category": "tech",        "sector_peers": ["AAPL", "GOOGL", "META", "AMZN", "CRM"]},
    "NVDA": {"start_price": 500.0, "annual_vol": 0.55, "annual_drift": 0.28,
             "category": "semiconductors","sector_peers": ["AMD", "INTC", "QCOM", "AVGO", "MU"]},
    "AMD":  {"start_price": 160.0, "annual_vol": 0.52, "annual_drift": 0.18,
             "category": "semiconductors","sector_peers": ["NVDA", "INTC", "QCOM", "MU", "AVGO"]},
    "AMZN": {"start_price": 180.0, "annual_vol": 0.30, "annual_drift": 0.12,
             "category": "tech",        "sector_peers": ["MSFT", "GOOGL", "META", "AAPL", "SHOP"]},
    "GOOGL":{"start_price": 170.0, "annual_vol": 0.28, "annual_drift": 0.12,
             "category": "tech",        "sector_peers": ["META", "MSFT", "AMZN", "AAPL", "NFLX"]},
    "META": {"start_price": 500.0, "annual_vol": 0.38, "annual_drift": 0.16,
             "category": "tech",        "sector_peers": ["AAPL", "GOOGL", "SNAP", "PINS", "RDDT"]},
    "TSLA": {"start_price": 250.0, "annual_vol": 0.62, "annual_drift": 0.10,
             "category": "auto",        "sector_peers": ["RIVN", "LCID", "NIO", "F", "GM"]},
    "NFLX": {"start_price": 620.0, "annual_vol": 0.38, "annual_drift": 0.14,
             "category": "tech",        "sector_peers": ["GOOGL", "DIS", "PARA", "WBD", "AMZN"]},
    # Financials
    "JPM":  {"start_price": 195.0, "annual_vol": 0.22, "annual_drift": 0.10,
             "category": "financials",  "sector_peers": ["BAC", "WFC", "GS", "MS", "C"]},
    "GS":   {"start_price": 450.0, "annual_vol": 0.26, "annual_drift": 0.10,
             "category": "financials",  "sector_peers": ["MS", "JPM", "BAC", "BX", "KKR"]},
    # Energy
    "XOM":  {"start_price": 115.0, "annual_vol": 0.24, "annual_drift": 0.08,
             "category": "energy",      "sector_peers": ["CVX", "COP", "SLB", "EOG", "OXY"]},
    "USO":  {"start_price":  75.0, "annual_vol": 0.38, "annual_drift": 0.04,
             "category": "commodity",   "sector_peers": ["XOM", "CVX", "XLE", "OXY", "COP"]},
}

DEFAULT_PROFILE: dict = {
    "start_price": 100.0, "annual_vol": 0.30, "annual_drift": 0.08,
    "category": "equity", "sector_peers": ["SPY", "QQQ", "IWM"],
}

POPULAR_TICKERS: list[str] = [
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "HYG",
    "AAPL", "MSFT", "NVDA", "AMD", "AMZN", "GOOGL", "META", "TSLA", "NFLX",
    "JPM", "GS", "XOM", "USO",
]


def _trading_days(start: str, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, end=end)


def simulate_price(
    ticker: str = "SPY",
    n_days: int = 504,
    seed: int = 42,
    keep_regime: bool = False,
) -> pd.DataFrame:
    """
    Generate realistic OHLCV data for *any* ticker using its profile.
    Falls back to DEFAULT_PROFILE for unknown tickers.
    Returns the same DataFrame structure as simulate_spy().

    Set keep_regime=True to retain the _regime column (for VIX correlation).
    """
    p = TICKER_PROFILES.get(ticker.upper(), DEFAULT_PROFILE)
    ticker_seed = seed + sum(ord(c) for c in ticker)
    df = simulate_spy(
        n_days=n_days,
        start_price=p["start_price"],
        annual_drift=p["annual_drift"],
        annual_vol=p["annual_vol"],
        seed=ticker_seed,
    )
    if not keep_regime and "_regime" in df.columns:
        df = df.drop(columns=["_regime"])
    return df


def _simulate_regimes(n_days: int, rng) -> np.ndarray:
    """
    Markov regime sequence: 0=Bear, 1=Neutral, 2=Bull.
    High self-transition probability → regimes persist ~10-18 days on average,
    long enough for momentum / mean-reversion features to predict forward returns.
    """
    # Expected regime duration: 1/(1 - p_stay)
    # Bull: ~15 days, Neutral: ~10 days, Bear: ~12 days
    P = np.array([
        [0.917, 0.060, 0.023],   # from Bear  → stays Bear 91.7%
        [0.055, 0.900, 0.045],   # from Neutral → stays Neutral 90%
        [0.030, 0.035, 0.935],   # from Bull  → stays Bull 93.5%
    ])
    regimes = np.zeros(n_days, dtype=int)
    regimes[0] = 1  # start neutral
    for t in range(1, n_days):
        regimes[t] = rng.choice(3, p=P[regimes[t - 1]])
    return regimes


def simulate_spy(
    n_days: int = 504,  # ~2 years
    start_price: float = 420.0,
    annual_drift: float = 0.08,
    annual_vol: float = 0.18,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dt = 1 / 252

    regimes = _simulate_regimes(n_days, rng)

    # ── Regime-dependent drift and vol ──────────────────────────────────────
    # Bull regime:    strong positive drift + low vol → clear Bull labels
    # Bear regime:    strong negative drift + high vol → clear Bear labels
    # Neutral regime: base drift only, normal vol
    #
    # Signal-to-noise design target (5-day forward return vs 5-day noise):
    #   Bull: mean = +3.0%, std = 1.4% → P(fwd > 1%) ≈ 92%
    #   Bear: mean = -2.5%, std = 5.1% → P(fwd < -1%) ≈ 62%
    extra_drift = np.where(regimes == 2,  0.0060,   # Bull: +60 bps/day
                  np.where(regimes == 0, -0.0050,   # Bear: -50 bps/day
                           0.0))
    vol_mult    = np.where(regimes == 2,  0.55,      # Bull: quiet market
                  np.where(regimes == 0,  2.00,      # Bear: fearful / high vol
                           1.0))

    eff_vol = annual_vol * vol_mult
    log_rets = (
        (annual_drift / 252 + extra_drift) - 0.5 * eff_vol ** 2 * dt
        + eff_vol * np.sqrt(dt) * rng.standard_normal(n_days)
    )

    # Momentum autocorrelation: yesterday's return nudges today (trend persistence)
    for t in range(1, n_days):
        log_rets[t] += 0.20 * log_rets[t - 1]

    prices = start_price * np.exp(np.cumsum(log_rets))
    prices = np.insert(prices, 0, start_price)[:-1]

    intraday_range = eff_vol * np.sqrt(dt) * rng.uniform(0.5, 2.0, n_days)
    high  = prices * (1 + intraday_range * 0.6)
    low   = prices * (1 - intraday_range * 0.4)
    open_ = prices * (1 + rng.normal(0, 0.003, n_days))

    volume_base = 80_000_000
    # Volume spikes in Bear regime
    vol_regime_mult = np.where(regimes == 0, 1.8, np.where(regimes == 2, 1.1, 1.0))
    volume = (volume_base * vol_regime_mult * rng.lognormal(0, 0.3, n_days)).astype(int)

    end_date = (date.today() - timedelta(days=1)).isoformat()
    start_date = (date.today() - timedelta(days=int(n_days * 2.0))).isoformat()
    dates = _trading_days(start_date, end_date)[:n_days]

    df = pd.DataFrame({
        "open":   open_,
        "high":   high,
        "low":    low,
        "close":  prices,
        "volume": volume,
        "vwap":   (open_ + high + low + prices) / 4,
        "_regime": regimes,   # carry forward for VIX correlation
    }, index=dates.date)
    df.index.name = "date"
    return df


def simulate_vix(
    n_days: int = 504,
    mean_vix: float = 18.0,
    speed: float = 0.08,
    vol_vix: float = 2.5,
    seed: int = 43,
    price_df: pd.DataFrame = None,  # when provided, derive VIX from realized vol + regimes
) -> pd.DataFrame:
    """
    Generate realistic VIX.

    If price_df is supplied (output of simulate_spy / simulate_price):
      - VIX is anchored to 10-day realized vol of prices × 1.1 (typical VIX premium)
      - VIX spikes when prices sell off (puts are expensive → VIX elevated)
      - Bull regimes hold VIX near 12-16; Bear regimes push VIX to 25-45
    Otherwise falls back to mean-reverting OU process.
    """
    rng = np.random.default_rng(seed)

    end_date = (date.today() - timedelta(days=1)).isoformat()
    start_date = (date.today() - timedelta(days=int(n_days * 2.0))).isoformat()
    dates = _trading_days(start_date, end_date)[:n_days]

    if price_df is not None and len(price_df) >= n_days:
        price_arr = price_df["close"].values[:n_days]
        regimes   = price_df["_regime"].values[:n_days] if "_regime" in price_df.columns else np.ones(n_days)

        # 10-day realized vol annualized
        log_rets = np.diff(np.log(price_arr), prepend=np.log(price_arr[0]))
        rvol = pd.Series(log_rets).rolling(10, min_periods=2).std().fillna(0.012).values * np.sqrt(252)

        # Regime-target VIX level
        target_vix = np.where(regimes == 0, 30.0,      # Bear: VIX elevated
                     np.where(regimes == 2, 14.0,       # Bull: VIX calm
                               mean_vix))               # Neutral: ~18

        # VIX = blend of realized vol premium + regime target + noise
        vix = np.zeros(n_days)
        vix[0] = mean_vix
        for t in range(1, n_days):
            rvol_t = float(rvol[t]) * 100 * 1.12   # realized vol → VIX-like scale, +12% premium
            blend  = 0.60 * float(target_vix[t]) + 0.40 * rvol_t
            # Mean-revert toward blend
            vix[t] = vix[t - 1] + 0.25 * (blend - vix[t - 1]) + rng.normal(0, vol_vix * 0.4)
            vix[t] = max(10.0, vix[t])

        # Intraday VIX varies ~±7% around close
        vix_high = vix * (1 + abs(rng.normal(0, 0.04, n_days)))
        vix_low  = vix * (1 - abs(rng.normal(0, 0.03, n_days)))
    else:
        vix = np.zeros(n_days)
        vix[0] = mean_vix
        for t in range(1, n_days):
            shock  = rng.normal(0, vol_vix * np.sqrt(1 / 252))
            vix[t] = vix[t - 1] + speed * (mean_vix - vix[t - 1]) / 252 + shock
            vix[t] = max(10.0, vix[t])
        spike_days = rng.choice(n_days, size=6, replace=False)
        for d in spike_days:
            vix[d] += rng.uniform(5, 15)
        vix_high = vix * 1.05
        vix_low  = vix * 0.95

    df = pd.DataFrame({
        "open":   vix,
        "high":   vix_high,
        "low":    vix_low,
        "close":  vix,
        "volume": 0,
        "vwap":   vix,
    }, index=dates.date)
    df.index.name = "date"
    return df


def simulate_rates(
    n_days: int = 504,
    start_2y: float = 4.5,
    start_10y: float = 4.2,
    seed: int = 44,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dt = 1 / 252
    vol_r = 0.012

    r2 = np.zeros(n_days)
    r10 = np.zeros(n_days)
    r2[0] = start_2y
    r10[0] = start_10y

    for t in range(1, n_days):
        r2[t]  = r2[t-1]  + rng.normal(0, vol_r) * np.sqrt(dt)
        r10[t] = r10[t-1] + rng.normal(0, vol_r * 0.8) * np.sqrt(dt)
        r2[t]  = max(0.1, r2[t])
        r10[t] = max(0.1, r10[t])

    end_date = (date.today() - timedelta(days=1)).isoformat()
    start_date = (date.today() - timedelta(days=int(n_days * 2.0))).isoformat()
    dates = _trading_days(start_date, end_date)[:n_days]

    def _df(arr):
        d = pd.DataFrame({
            "open": arr, "high": arr * 1.001, "low": arr * 0.999,
            "close": arr, "volume": 0, "vwap": arr
        }, index=dates.date)
        d.index.name = "date"
        return d

    return _df(r2), _df(r10)


def simulate_macro(n_days: int = 756, seed: int = 55) -> pd.DataFrame:
    """
    Simulate full macro dataset matching loader.fetch_macro() output.
    Columns: rate_3m, rate_6m, rate_1y, rate_5y, rate_30y,
             sofr, jobless_claims, curve_3m10y, curve_5y30y,
             curve_butterfly, sofr_spread, claims_ma4w, claims_chg4w
    All rates in decimal (e.g. 0.045 = 4.5%).
    """
    rng = np.random.default_rng(seed)
    dt  = 1 / 252
    vol = 0.012

    # Simulate yield curve (correlated walk, steepening front-to-back)
    r3m  = np.zeros(n_days); r3m[0]  = 0.053
    r6m  = np.zeros(n_days); r6m[0]  = 0.052
    r1y  = np.zeros(n_days); r1y[0]  = 0.050
    r5y  = np.zeros(n_days); r5y[0]  = 0.044
    r30y = np.zeros(n_days); r30y[0] = 0.043
    sofr = np.zeros(n_days); sofr[0] = 0.053   # tracks 3M closely

    for t in range(1, n_days):
        shock = rng.normal(0, vol * np.sqrt(dt))
        r3m[t]  = max(0.001, r3m[t-1]  + shock * 1.0)
        r6m[t]  = max(0.001, r6m[t-1]  + shock * 0.97)
        r1y[t]  = max(0.001, r1y[t-1]  + shock * 0.93)
        r5y[t]  = max(0.001, r5y[t-1]  + shock * 0.82)
        r30y[t] = max(0.001, r30y[t-1] + shock * 0.68)
        sofr[t] = max(0.001, sofr[t-1] + rng.normal(0, vol * 0.3 * np.sqrt(dt)))

    # Jobless claims: mean-reverting around 220k, weekly releases (held daily)
    claims = np.zeros(n_days)
    claims[0] = 220_000
    for t in range(1, n_days):
        claims[t] = max(100_000, claims[t-1] * 0.97 + 0.03 * 220_000
                        + (rng.normal(0, 12_000) if t % 5 == 0 else 0))

    end_date   = (date.today() - timedelta(days=1)).isoformat()
    start_date = (date.today() - timedelta(days=int(n_days * 2.0))).isoformat()
    dates = _trading_days(start_date, end_date)[:n_days]
    idx   = dates.date

    df = pd.DataFrame({
        "rate_3m":        r3m,
        "rate_6m":        r6m,
        "rate_1y":        r1y,
        "rate_5y":        r5y,
        "rate_30y":       r30y,
        "sofr":           sofr,
        "jobless_claims": claims,
    }, index=idx)
    df.index.name = "date"
    return df



def simulate_news(n_days: int = 504, seed: int = 45) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end_date = (date.today() - timedelta(days=1)).isoformat()
    start_date = (date.today() - timedelta(days=int(n_days * 2.0))).isoformat()
    dates = _trading_days(start_date, end_date)[:n_days]

    # ~3-5 news items per day
    rows = []
    bull_titles = [
        "SPY rallies to new highs on strong earnings",
        "Fed signals rate pause, markets surge",
        "Strong jobs report boosts S&P 500",
        "Tech earnings beat expectations, SPY rises",
        "Inflation data shows cooling, markets celebrate",
    ]
    bear_titles = [
        "SPY falls on recession fears",
        "Fed hints at more hikes, stocks plunge",
        "Weak GDP data rattles markets",
        "Banking sector fears drag S&P 500 lower",
        "Geopolitical tensions weigh on equities",
    ]
    neutral_titles = [
        "Markets mixed ahead of earnings season",
        "SPY trades sideways in thin volume",
        "Investors await Fed decision",
    ]

    for d in dates.date:
        n_articles = rng.integers(2, 6)
        sentiment_bias = rng.choice([-1, 0, 1], p=[0.3, 0.4, 0.3])
        for _ in range(n_articles):
            if sentiment_bias == 1:
                title = rng.choice(bull_titles)
            elif sentiment_bias == -1:
                title = rng.choice(bear_titles)
            else:
                title = rng.choice(neutral_titles)
            rows.append({
                "date": d,
                "published_utc": str(d),
                "title": title,
                "description": title,
                "keywords": [],
            })

    return pd.DataFrame(rows)


def simulate_training_history(
    n_epochs: int = 80,
    seed: int = 99,
) -> dict:
    """Simulate a realistic training history (loss/accuracy curves)."""
    rng = np.random.default_rng(seed)
    epochs = np.arange(1, n_epochs + 1)

    # Realistic: fast drop then plateau
    base_loss = 1.1 * np.exp(-epochs / 20) + 0.55
    train_loss = base_loss + rng.normal(0, 0.015, n_epochs)
    val_loss   = base_loss * 1.08 + rng.normal(0, 0.025, n_epochs)
    val_loss   = np.clip(val_loss, 0.5, 2.0)

    base_acc = 0.70 - 0.40 * np.exp(-epochs / 18)
    train_acc = np.clip(base_acc + rng.normal(0, 0.01, n_epochs), 0.3, 0.95)
    val_acc   = np.clip(base_acc * 0.95 + rng.normal(0, 0.015, n_epochs), 0.3, 0.90)

    return {
        "train_loss": train_loss.tolist(),
        "val_loss":   val_loss.tolist(),
        "train_acc":  train_acc.tolist(),
        "val_acc":    val_acc.tolist(),
    }


def simulate_confusion_matrix(seed: int = 50) -> np.ndarray:
    """Returns a 3x3 confusion matrix [bear, neutral, bull]."""
    rng = np.random.default_rng(seed)
    cm = np.array([
        [120, 25, 15],   # bear: mostly correct
        [30, 180, 35],   # neutral: some confusion
        [18, 22, 115],   # bull: mostly correct
    ], dtype=float)
    return cm


def simulate_feature_importance(feature_names: list[str], seed: int = 51) -> pd.Series:
    rng = np.random.default_rng(seed)
    raw = rng.exponential(1.0, len(feature_names))
    raw[feature_names.index("vix")] *= 3.0 if "vix" in feature_names else 1
    raw[feature_names.index("rsi_14")] *= 2.5 if "rsi_14" in feature_names else 1
    raw /= raw.sum()
    return pd.Series(raw, index=feature_names).sort_values(ascending=False)


def simulate_live_state(n_signals: int = 30, seed: int = 77) -> pd.DataFrame:
    """Simulate a log of recent live signals and their outcomes using regime-aware data."""
    rng = np.random.default_rng(seed)
    today = date.today()
    rows = []
    portfolio = 100_000.0
    spy_price = 520.0
    vix_level = 18.0

    # Regime sequence for the live window
    regimes = _simulate_regimes(n_signals, rng)

    for i in range(n_signals):
        regime = int(regimes[i])

        # In Bull regime: model is more confident on Bull signals (win prob ~60-75%)
        # In Bear regime: model is more confident on Bear signals
        # In Neutral: lower confidence, more often skip
        if regime == 2:   # Bull
            signal_class = rng.choice([0, 1, 2], p=[0.10, 0.25, 0.65])
            confidence   = rng.uniform(0.58, 0.82)
            win_p        = 0.65
        elif regime == 0:  # Bear
            signal_class = rng.choice([0, 1, 2], p=[0.60, 0.25, 0.15])
            confidence   = rng.uniform(0.55, 0.78)
            win_p        = 0.62
        else:              # Neutral
            signal_class = rng.choice([0, 1, 2], p=[0.28, 0.48, 0.24])
            confidence   = rng.uniform(0.42, 0.65)
            win_p        = 0.50

        proba = np.array([0.1, 0.1, 0.1])
        proba[signal_class] = confidence
        proba /= proba.sum()

        spread_types = {0: "bear_put", 1: "skip", 2: "bull_call"}
        stype = spread_types[signal_class]

        pnl = 0.0
        if stype != "skip":
            outcome = rng.choice([-1, 1], p=[1 - win_p, win_p])
            pnl = outcome * rng.uniform(80, 350)
        portfolio += pnl

        # Price and VIX move consistent with regime
        spy_drift = 0.0035 if regime == 2 else (-0.0030 if regime == 0 else 0.0)
        spy_vol   = 0.007 if regime == 2 else (0.015 if regime == 0 else 0.010)
        spy_price *= (1 + spy_drift + rng.normal(0, spy_vol))

        vix_target = 14.0 if regime == 2 else (30.0 if regime == 0 else 18.0)
        vix_level  = vix_level + 0.25 * (vix_target - vix_level) + rng.normal(0, 1.0)
        vix_level  = max(10.0, vix_level)

        rows.append({
            "date":            today - timedelta(days=n_signals - i),
            "signal":          ["BEAR", "NEUTRAL", "BULL"][signal_class],
            "spread_type":     stype,
            "confidence":      round(confidence, 3),
            "proba_bear":      round(proba[0], 3),
            "proba_neutral":   round(proba[1], 3),
            "proba_bull":      round(proba[2], 3),
            "price":           round(spy_price, 2),
            "vix":             round(vix_level, 1),
            "pnl":             round(pnl, 2),
            "portfolio_value": round(portfolio, 2),
        })

    return pd.DataFrame(rows)


def simulate_options_chain_with_violations(
    S: float = 500.0,
    iv: float = 0.18,
    r: float = 0.045,
    q: float = 0.013,
    dte: int = 30,
    n_strikes: int = 11,
    strike_spacing: float = 5.0,
    inject_violation: bool = False,
    violation_size: float = None,
    rng=None,
) -> pd.DataFrame:
    """
    Synthetic SPY options chain priced via Black-Scholes.
    Optionally injects a put-call parity violation on one strike.

    Returns DataFrame: strike, type, bid, ask, mid, iv, delta, dte
    """
    from alan_trader.backtest.engine import bs_price
    from scipy.stats import norm

    if rng is None:
        rng = np.random.default_rng(0)

    T = dte / 252
    atm = round(S / strike_spacing) * strike_spacing
    strikes = [atm + i * strike_spacing for i in range(-(n_strikes // 2), n_strikes // 2 + 1)]

    # Realistic IV skew: OTM puts carry more vol than OTM calls
    def _strike_iv(K):
        moneyness = np.log(K / S)
        skew_bump = -0.04 * moneyness   # downside skew (puts richer)
        return max(0.05, iv + skew_bump)

    # Choose one strike to inject a violation on
    viol_strike = rng.choice(strikes) if inject_violation else None
    viol_side   = rng.choice(["call", "put"]) if inject_violation else None
    if violation_size is None:
        violation_size = float(rng.uniform(0.004, 0.012)) * S

    rows = []
    for K in strikes:
        for opt_type in ("call", "put"):
            local_iv = _strike_iv(K)
            fair     = bs_price(S, K, T, r, local_iv, opt_type)
            if fair <= 0:
                continue

            spread = max(0.05, fair * 0.005)   # ~0.5% bid-ask
            bid    = fair - spread / 2
            ask    = fair + spread / 2

            # Inject violation: bump one side's price away from parity
            if inject_violation and K == viol_strike and opt_type == viol_side:
                bump = violation_size * (1 if opt_type == "call" else -1)
                bid  = max(0.01, bid + bump)
                ask  = max(0.01, ask + bump)

            # Delta
            if T > 0:
                d1 = (np.log(S / K) + (r - q + 0.5 * local_iv ** 2) * T) / (local_iv * np.sqrt(T))
                delta = float(norm.cdf(d1) if opt_type == "call" else norm.cdf(d1) - 1)
            else:
                delta = 1.0 if (opt_type == "call" and S > K) else 0.0

            rows.append({
                "strike": K,
                "type":   opt_type,
                "bid":    round(max(0.01, bid), 3),
                "ask":    round(max(0.01, ask), 3),
                "mid":    round((bid + ask) / 2, 3),
                "iv":     round(local_iv, 4),
                "delta":  round(delta, 4),
                "dte":    dte,
            })

    return pd.DataFrame(rows)


def simulate_dividend_events(
    price_df: pd.DataFrame,
    annual_yield: float = 0.012,
    seed: int = 60,
) -> pd.DataFrame:
    """
    Generate quarterly SPY-like dividend events.
    Returns DataFrame: ex_date, record_date, payment_date, div_per_share.
    """
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime(price_df.index)
    start_year  = dates.min().year
    end_year    = dates.max().year

    rows = []
    # SPY pays ~quarterly; ex-dates typically mid-Mar/Jun/Sep/Dec
    quarter_months = [3, 6, 9, 12]
    for year in range(start_year, end_year + 1):
        for month in quarter_months:
            # Find a Friday in the 3rd week of the month
            try:
                target = pd.Timestamp(year=year, month=month, day=15)
                # Move to nearest Friday
                offset = (4 - target.weekday()) % 7
                ex_date = target + pd.Timedelta(days=offset)
                if ex_date not in dates:
                    closest = min(dates, key=lambda d: abs((d - ex_date).days))
                    ex_date = closest
                # Dividend per share ≈ price * quarterly_yield
                price_on_date = price_df.loc[ex_date.date() if hasattr(ex_date, 'date') else ex_date, "close"] \
                    if hasattr(ex_date, 'date') else price_df["close"].iloc[0]
                div = price_on_date * (annual_yield / 4) * rng.uniform(0.95, 1.05)
                rows.append({
                    "ex_date":      ex_date.date() if hasattr(ex_date, "date") else ex_date,
                    "record_date":  (ex_date + pd.Timedelta(days=1)).date() if hasattr(ex_date, "date") else ex_date,
                    "payment_date": (ex_date + pd.Timedelta(days=14)).date() if hasattr(ex_date, "date") else ex_date,
                    "div_per_share": round(float(div), 4),
                })
            except Exception:
                continue

    return pd.DataFrame(rows)


def simulate_vol_surface(
    S: float = 500.0,
    iv_base: float = 0.18,
    seed: int = 70,
) -> tuple:
    """
    Returns (strikes, dtes, iv_matrix) for a 3D vol surface.
    strikes: 1-D array of dollar strikes
    dtes: 1-D array of days-to-expiration
    iv_matrix: 2-D array (len(dtes) x len(strikes)) of implied vols
    """
    rng = np.random.default_rng(seed)
    strikes_pct = np.linspace(0.80, 1.20, 15)
    dtes = np.array([7, 14, 21, 30, 45, 60, 90, 120, 180])
    strikes = strikes_pct * S

    iv_matrix = np.zeros((len(dtes), len(strikes_pct)))
    for i, dte in enumerate(dtes):
        for j, K_pct in enumerate(strikes_pct):
            moneyness = np.log(K_pct)
            skew      = -0.05 * moneyness           # downside skew
            smile     =  0.02 * moneyness ** 2      # symmetrical smile
            term_bump =  0.01 * np.log(max(dte, 1) / 30)
            noise     = rng.normal(0, 0.004)
            iv_matrix[i, j] = max(0.05, iv_base + skew + smile + term_bump + noise)

    return strikes, dtes, iv_matrix


def simulate_iv_smile(
    S: float = 500.0,
    iv_base: float = 0.18,
    seed: int = 71,
) -> pd.DataFrame:
    """IV smile across strikes for multiple expirations."""
    rng = np.random.default_rng(seed)
    strikes_pct = np.linspace(0.85, 1.15, 13)
    strikes     = strikes_pct * S
    expirations = [7, 21, 45, 90]

    rows = []
    for dte in expirations:
        for K, K_pct in zip(strikes, strikes_pct):
            m  = np.log(K_pct)
            iv = max(0.05, iv_base - 0.05 * m + 0.02 * m ** 2
                     + 0.01 * np.log(max(dte, 1) / 30) + rng.normal(0, 0.004))
            rows.append({"strike": round(K, 1), "dte": dte,
                         "iv": round(iv, 4), "moneyness": round(K_pct, 3)})
    return pd.DataFrame(rows)


def simulate_top_movers(
    ticker: str = "SPY",
    n: int = 30,
    seed: int = 72,
) -> pd.DataFrame:
    """
    Simulate daily top gainers / losers for the universe of the selected ticker.
    Uses sector peers from TICKER_PROFILES to build a relevant universe.
    """
    rng = np.random.default_rng(seed + sum(ord(c) for c in ticker))
    profile = TICKER_PROFILES.get(ticker.upper(), DEFAULT_PROFILE)
    peers   = profile.get("sector_peers", [])

    # Category-specific universes
    category = profile.get("category", "equity")
    _universes: dict[str, list] = {
        "etf": [
            "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "GLD", "SLV",
            "TLT", "HYG", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY",
            "ARKK", "SMH", "MDY", "IJR", "SCHD", "VIG", "VYM", "RSP",
            "SPLG", "SPYG", "SPYV", "SDY", "DVY", "VNQ",
        ],
        "tech": [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX",
            "AMD", "INTC", "QCOM", "AVGO", "CRM", "ADBE", "ORCL", "NOW",
            "SNOW", "PLTR", "UBER", "LYFT", "SHOP", "SQ", "PYPL", "COIN",
            "AMAT", "LRCX", "KLAC", "MU", "WDC", "STX",
        ],
        "semiconductors": [
            "NVDA", "AMD", "INTC", "QCOM", "AVGO", "MU", "AMAT", "LRCX",
            "KLAC", "TXN", "ADI", "MCHP", "ON", "MRVL", "SWKS", "QRVO",
            "MPWR", "ENTG", "ACLS", "CAMT", "FORM", "MKSI", "UCTT", "COHU",
            "ONTO", "AMBA", "SLAB", "DIOD", "SITM", "RMBS",
        ],
        "financials": [
            "JPM", "BAC", "WFC", "GS", "MS", "C", "BX", "KKR", "APO",
            "AXP", "V", "MA", "COF", "DFS", "SYF", "ALLY", "USB", "PNC",
            "TFC", "KEY", "CFG", "FITB", "RF", "HBAN", "MTB", "ZION",
            "SCHW", "BK", "STT", "NTRS",
        ],
        "energy": [
            "XOM", "CVX", "COP", "SLB", "EOG", "OXY", "PXD", "HAL", "BKR",
            "PSX", "VLO", "MPC", "HES", "DVN", "FANG", "APA", "MRO", "NOV",
            "CHK", "SM", "CDEV", "PDCE", "VTLE", "MGY", "REX", "TPVG",
            "XLE", "OIH", "IEZ", "PSCE", "FCG",
        ],
        "commodity": [
            "GLD", "SLV", "GDX", "GDXJ", "IAU", "RING", "SIVR", "USO",
            "UNG", "CORN", "SOYB", "WEAT", "DBA", "PDBC", "CPER", "PALL",
            "PPLT", "DBO", "DBP", "DBC", "COMT", "GSG", "FTGC", "BCI",
            "RJI", "KOLD", "BOIL", "UGAZ", "DGAZ", "UGA",
        ],
        "fixed_income": [
            "TLT", "IEF", "SHY", "AGG", "BND", "HYG", "LQD", "JNK",
            "MBB", "EMB", "BWX", "BNDX", "VCIT", "VCSH", "BSV", "BIV",
            "FLOT", "NEAR", "SHV", "BIL", "SGOV", "VGSH", "VGIT", "VGLT",
            "GOVT", "SPAB", "SPIB", "SPSB", "TIPX", "VTIP",
        ],
        "auto": [
            "TSLA", "RIVN", "LCID", "NIO", "LI", "XPEV", "F", "GM", "STLA",
            "TM", "HMC", "VOW3", "BMW", "MBLY", "APTV", "LEA", "BWA",
            "ALV", "GT", "CTB", "LCII", "FOXF", "THRM", "MODG", "DORM",
        ],
    }

    default_universe = [
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B",
        "UNH", "JNJ", "XOM", "V", "JPM", "PG", "MA", "HD", "CVX", "LLY",
        "ABBV", "AVGO", "MRK", "PEP", "COST", "KO", "WMT", "BAC", "TMO",
        "CSCO", "MCD", "CRM",
    ]
    universe = _universes.get(category, default_universe)

    # Always include the target ticker and its known peers first
    prioritised = [ticker.upper()] + [p for p in peers if p not in (ticker.upper(),)]
    remaining   = [t for t in universe if t not in prioritised]
    all_tickers = (prioritised + remaining)[:n]
    actual_n = len(all_tickers)

    # Use ticker-appropriate volatility for the move distribution
    ticker_vol = profile.get("annual_vol", 0.30) / np.sqrt(252)
    changes = rng.normal(0, ticker_vol, actual_n)
    outlier_idx = rng.choice(actual_n, size=min(4, actual_n), replace=False)
    for i in outlier_idx[:2]:
        changes[i] = rng.uniform(0.04, ticker_vol * 6)
    for i in outlier_idx[2:]:
        changes[i] = rng.uniform(-ticker_vol * 6, -0.04)

    prices  = rng.uniform(
        profile["start_price"] * 0.3,
        profile["start_price"] * 1.5,
        actual_n,
    )
    # Use the actual target ticker price for the first entry
    prices[0] = profile["start_price"]
    volumes = rng.lognormal(18, 1, actual_n).astype(int)

    df = pd.DataFrame({
        "ticker":     all_tickers,
        "price":      np.round(prices, 2),
        "change_pct": np.round(changes * 100, 2),
        "volume":     volumes,
    }).sort_values("change_pct", ascending=False).reset_index(drop=True)
    return df


def simulate_gex(
    S: float = 500.0,
    n_strikes: int = 20,
    seed: int = 73,
) -> pd.DataFrame:
    """
    Simulate dealer Gamma Exposure (GEX) by strike.
    Positive GEX = dealers long gamma (price-stabilising).
    Negative GEX = dealers short gamma (price-destabilising).
    """
    rng = np.random.default_rng(seed)
    spacing = 5.0
    atm     = round(S / spacing) * spacing
    strikes = [atm + i * spacing for i in range(-(n_strikes // 2), n_strikes // 2 + 1)]

    rows = []
    for K in strikes:
        mono     = (K - S) / S
        weight   = float(np.exp(-4 * mono ** 2))
        call_gex = float(rng.normal(-300_000, 1_800_000) * weight)
        put_gex  = float(rng.normal( 400_000, 1_400_000) * weight)
        net      = call_gex + put_gex
        rows.append({"strike": K, "call_gex": round(call_gex),
                     "put_gex": round(put_gex), "net_gex": round(net)})
    return pd.DataFrame(rows)


def simulate_momentum_indicators(
    ticker: str = "SPY",
    n_days: int = 252,
    seed: int = 74,
) -> pd.DataFrame:
    """
    Returns close prices with RSI-14 and MACD (12/26/9) pre-calculated.
    Columns: close, rsi, macd_line, signal_line, macd_histogram
    """
    spy   = simulate_price(ticker=ticker, n_days=n_days, seed=seed)
    close = spy["close"]

    # RSI-14
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12       = close.ewm(span=12, adjust=False).mean()
    ema26       = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram   = macd_line - signal_line

    df = pd.DataFrame({
        "close":          close,
        "rsi":            rsi.round(2),
        "macd_line":      macd_line.round(4),
        "signal_line":    signal_line.round(4),
        "macd_histogram": histogram.round(4),
    })
    df.index.name = "date"
    return df


def simulate_portfolio_returns(
    n_strategies: int = 2,
    n_days: int = 252,
    starting_capital: float = 100_000,
    seed: int = 88,
) -> dict:
    """
    Simulate correlated equity curves for n_strategies strategies.
    Returns dict: strategy_name -> pd.Series (equity curve, date-indexed).
    """
    rng = np.random.default_rng(seed)

    # Build correlated return matrix
    # Strategy 0 (SPY spread): moderate correlation with market
    # Strategy 1 (Div arb): low correlation
    base_corr = np.array([
        [1.0,  0.25],
        [0.25, 1.0],
    ]) if n_strategies == 2 else np.eye(n_strategies)

    from scipy.linalg import cholesky
    L = cholesky(base_corr[:n_strategies, :n_strategies], lower=True)

    daily_vols   = np.array([0.015, 0.004] + [0.012] * max(0, n_strategies - 2))[:n_strategies]
    daily_drifts = np.array([0.0004, 0.0002] + [0.0003] * max(0, n_strategies - 2))[:n_strategies]

    raw = rng.standard_normal((n_days, n_strategies))
    correlated = (L @ raw.T).T
    returns = correlated * daily_vols + daily_drifts

    end_date   = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=int(n_days * 2.0))
    dates      = _trading_days(start_date.isoformat(), end_date.isoformat())[:n_days]

    strategy_names = ["options_spread", "dividend_arb"] + \
                     [f"strategy_{i}" for i in range(2, n_strategies)]

    result = {}
    for i, name in enumerate(strategy_names[:n_strategies]):
        equity = starting_capital * np.cumprod(1 + returns[:, i])
        equity = np.insert(equity, 0, starting_capital)[:-1]
        s = pd.Series(equity, index=dates.date, name=name)
        s.index.name = "date"
        result[name] = s

    return result
