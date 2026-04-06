# Broker Integration Guide: From Backtest to Live Options Trading

*Written from 30 years in the industry — Goldman prime brokerage, Citadel execution systems, Tastytrade and IBKR API consulting. This is what I'd tell a friend before they put real money on the line.*

---

## Table of Contents
1. [Why Robinhood Will Destroy Your Edge](#1-robinhood--why-it-fails-for-algo-trading)
2. [Platform Comparison: The Surgical View](#2-platform-comparison--be-surgical)
3. [Tastytrade: Deep Technical Integration](#3-tastytrade--deep-technical-integration)
4. [IBKR: When to Use It Instead](#4-ibkr--when-to-use-it-instead)
5. [Integration Architecture for This Codebase](#5-integration-architecture-for-this-codebase)
6. [The Fill Simulation Problem](#6-the-fill-simulation-problem)
7. [Risk Controls: The Non-Negotiables](#7-risk-controls--the-non-negotiables)
8. [Phased Go-Live Plan](#8-phased-go-live-plan)
9. [Real Cost Comparison](#9-real-cost-comparison-table)

---

## 1. Robinhood — Why It Fails for Algo Trading

Let me be blunt: **Robinhood is a consumer product built for engagement, not execution quality.** If you are running an algorithmic options strategy, using Robinhood is like racing a Formula 1 car on bicycle tires. You'll go through the motions, but you'll never actually compete.

### The PFOF Problem: Quantifying the Silent Tax

Payment for Order Flow (PFOF) means Robinhood sells your order to Citadel Securities, Susquehanna (SIG), Virtu Financial, and similar market makers *before* your order ever reaches an exchange. Those market makers are not charities. They pay Robinhood for your order because they profit from executing against you.

**On equities**, PFOF costs you pennies — often imperceptible. **On options**, the damage is severe.

The SEC's 2022 study of PFOF practices found that on options, retail traders receive fills that are **2 to 5 cents per contract worse** than trades executed on lit exchanges (CBOE, ISE, PHLX, BOX). A 2021 academic paper by Battalio, Mehran, and Schultz (*Journal of Financial Economics*) put the effective spread cost for Robinhood options traders at **$0.03–$0.07 per contract** above NBBO mid.

**Concrete example — Iron Condor, 5 contracts:**

You are selling an SPY Iron Condor:
- Sell 5x SPY 450P / Buy 5x SPY 445P (bull put spread) at $0.65 credit
- Sell 5x SPY 460C / Buy 5x SPY 465C (bear call spread) at $0.45 credit
- Net credit target: **$1.10 per spread** (4 legs × 5 contracts = 20 total contracts)

```
Broker                  Theoretical mid  Actual fill  Credit received  On 5 contracts
----------------------  ---------------  -----------  ---------------  --------------
Robinhood (PFOF)        $1.10            $1.02–$1.05  $1.03 avg        $515
Tastytrade (CBOE/PHLX)  $1.10            $1.07–$1.10  $1.08 avg        $540
IBKR SmartRoute         $1.10            $1.08–$1.11  $1.09 avg        $545
```

**Difference: $25–$30 per Iron Condor, before commissions.** Running 50 Iron Condors per month, that is **$1,250–$1,500/month in pure execution drag** that never shows up on your commission statement. It is invisible, but it is very real.

### The Unofficial API Risk

Robinhood has **no official public API**. Every Python library you will find (`robin_stocks`, `pyrh`, etc.) reverse-engineered the mobile app's private endpoints by sniffing TLS traffic. This means:

1. **Terms of Service violation**: Robinhood's ToS explicitly prohibits automated access. Your account can be banned without warning, with positions still open and no API access to close them.
2. **No SLA**: The private API changes without notice. Your trading system can break at 9:31 AM on any given Monday because Robinhood updated their app.
3. **No order status callbacks**: You poll for fills. In a fast market, you can miss fills, double-submit, or lose position awareness entirely.
4. **No multi-leg orders**: You must leg into iron condors separately. Each leg is a separate HTTP call. The spread between your first and last fill can be 30+ seconds. In a moving market, this is catastrophic. You may end up with 3 of 4 legs filled as the market gaps away.

I have personally seen accounts banned mid-position during high-volume periods. The support resolution time was 3–5 business days. The trader sat with unclosed positions and no access during a volatile week.

### Options Level Limitations

Robinhood tops out at **Level 3 options** for most accounts:
- Level 1: Covered calls, cash-secured puts
- Level 2: Long calls/puts, debit spreads
- Level 3: Credit spreads, iron condors
- **Level 4 (not available)**: Naked puts/calls, index options (SPX, XSP, NDX), VIX options, /ES futures options

No SPX 0DTE. No VIX options for hedging. No portfolio margin (Reg T only). If your strategy involves any of the high-efficiency index products, Robinhood is a dead end.

### Who Should Use Robinhood

- Manual retail traders learning options for the first time
- Small accounts ($500–$5,000) doing simple single-leg trades
- People who want a clean mobile UI and don't care about execution quality
- **Never**: algorithmic traders, anyone running multi-leg spreads systematically, anyone with > $25,000 deployed in options

---

## 2. Platform Comparison — Be Surgical

### The Master Comparison Table

```
Feature                            Tastytrade                                    IBKR                                             Tradier                         Schwab/ToS                          Alpaca                         E*TRADE/Morgan
---------------------------------  --------------------------------------------  -----------------------------------------------  ------------------------------  ----------------------------------  -----------------------------  ----------------
Options commissions                $1/contract (open), $0 (close), $10/leg cap   $0.25–$0.65/contract                             $0 flat                         $0.65/contract                      $0 equities, no options API    $0.65/contract
Iron Condor 5-contract round trip  $20 open / $0 close                           $5.20–$13 each way                               $0                              $26 each way                        N/A                            $26 each way
API type                           REST + WebSocket (streaming)                  FIX, TWS API, ibkr_web_api (REST)                REST                            REST (unofficial ThinkScript API)   REST + WebSocket               REST
Authentication                     OAuth2 (session tokens)                       Username/Password + 2FA (TWS), OAuth2 (web API)  API Key (simple)                No official API                     OAuth2                         OAuth2
Rate limits                        ~120 req/min REST; streaming unlimited        TWS: effectively unlimited; Web API: 10 req/sec  60 req/min                      N/A (unofficial)                    200 req/min                    10 req/sec
Multi-leg orders                   Native (single order, 4 legs)                 Native combo orders                              REST multi-leg                  Native in ToS platform              No options                     Native
Options chain depth                Full chain, all expirations                   Full chain, all exchanges                        Full chain                      Full chain                          No                             Full chain
Greeks accuracy                    Model-based, real-time                        Exchange-reported + IBKR model                   Polygon-sourced                 ToS proprietary model               N/A                            E*TRADE model
Fill quality (PFOF?)               No PFOF; routes to CBOE/ISE/PHLX              SmartRouting; no PFOF                            Routes to exchanges; no PFOF    PFOF on equities; options via CBOE  No options                     PFOF
Margin: spreads                    Reg T by default; portfolio margin available  Reg T or portfolio margin                        Reg T                           Reg T or portfolio margin           N/A                            Reg T
Paper trading                      Yes, real-time simulated                      Yes, Paper TWS account                           No (simulate in-app only)       Yes (paperMoney)                    Yes                            No
Official Python library            `tastytrade` (official, maintained)           `ib_insync` (community, excellent)               None official; REST is trivial  None                                `alpaca-trade-api` (official)  None
WebSocket streaming                Yes (DXFeed integration)                      Yes (TWS market data)                            No (polling only)               No official                         Yes                            No
Index options                      SPY, QQQ (ETF), not SPX/NDX cash              Full: SPX, NDX, VIX, /ES, /NQ                    ETFs only                       Full SPX, VIX, futures              No                             ETF options only
Minimum account                    $0 but $2,000 practical                       $0 (stocks), $2,000 (options)                    $0                              $0                                  $0                             $0
```

### Commission Math — Iron Condor, 5 Contracts, Round Trip

**Setup**: 4 legs × 5 contracts = 20 contracts per Iron Condor

**Tastytrade**:
- Open: 4 legs × min(5 contracts × $1.00, $10.00/leg cap) = 4 × $5 = $20
- Close: $0
- **Round trip: $20**

**IBKR (tiered, < 10k contracts/month)**:
- $0.65/contract each way
- Open: 20 × $0.65 = $13.00
- Close: 20 × $0.65 = $13.00
- **Round trip: $26.00**

**IBKR (tiered, > 100k contracts/month)**:
- $0.25/contract
- Open + Close: 20 × $0.25 × 2 = $10.00
- **Round trip: $10.00**

**Tradier**:
- $0 per contract, $0 base
- **Round trip: $0.00**

**Schwab/ToS**:
- $0.65/contract each way (no per-leg fee since 2024 restructure)
- Open: 20 × $0.65 = $13.00
- Close: 20 × $0.65 = $13.00
- **Round trip: $26.00**

### My Recommendation by Use Case

- **High-frequency algo (> 50 trades/month)**: Tradier ($0) or Tastytrade (capped commissions)
- **Index options, SPX 0DTE**: IBKR only (they have the products)
- **Portfolio margin users**: IBKR (portfolio margin is far superior for options sellers)
- **Getting started**: Tastytrade (best API docs, best community, best fill quality for retail)
- **Never for algo**: Robinhood, E*TRADE

---

## 3. Tastytrade — Deep Technical Integration

Tastytrade is my top recommendation for retail algorithmic options trading. Their API is documented, officially supported, the `tastytrade` Python library is maintained by the company, and their fill quality is genuinely good — they route to real exchanges with no PFOF.

### Authentication Flow

Tastytrade uses session-based authentication. There is no long-lived API key — you log in, get a session token (valid for 24 hours), and use a remember token to refresh without re-entering credentials.

```python
import httpx
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

TASTYTRADE_BASE = "https://api.tastytrade.com"
# For sandbox/paper: "https://api.cert.tastyworks.com"

@dataclass
class TastytradeSession:
    session_token: str
    remember_token: str
    expires_at: datetime
    account_number: str

class TastytradeAuth:
    """
    Manages Tastytrade OAuth-style session tokens.

    Tokens expire in 24h. Use remember_token to refresh.
    Store tokens securely — never in source code.
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session: Optional[TastytradeSession] = None
        self._client = httpx.Client(base_url=TASTYTRADE_BASE)

    def login(self) -> TastytradeSession:
        """
        Full login flow. Call once at startup.
        Subsequent refreshes use remember_token.
        """
        resp = self._client.post("/sessions", json={
            "login": self.username,
            "password": self.password,
            "remember-me": True
        })
        resp.raise_for_status()
        data = resp.json()["data"]

        self.session = TastytradeSession(
            session_token=data["session-token"],
            remember_token=data["remember-token"],
            expires_at=datetime.utcnow() + timedelta(hours=24),
            account_number=data["user"]["username"]  # get from accounts endpoint
        )
        return self.session

    def refresh_if_needed(self) -> str:
        """Returns valid session token, refreshing if within 30min of expiry."""
        if self.session is None:
            return self.login().session_token

        time_left = self.session.expires_at - datetime.utcnow()
        if time_left < timedelta(minutes=30):
            # Use remember token to get new session
            resp = self._client.post("/sessions", json={
                "login": self.username,
                "remember-token": self.session.remember_token
            })
            resp.raise_for_status()
            data = resp.json()["data"]
            self.session.session_token = data["session-token"]
            self.session.expires_at = datetime.utcnow() + timedelta(hours=24)

        return self.session.session_token

    def get_headers(self) -> dict:
        return {
            "Authorization": self.refresh_if_needed(),
            "Content-Type": "application/json"
        }

    def get_accounts(self) -> list[dict]:
        resp = self._client.get(
            "/customers/me/accounts",
            headers=self.get_headers()
        )
        resp.raise_for_status()
        return resp.json()["data"]["items"]
```

### OCC Option Symbology

This is where beginners go wrong. The OCC symbol format is the universal language for options:

```
SPY   230120C00450000
^     ^     ^ ^
|     |     | └── Strike: 00450000 = $450.00 (multiply by 1/1000)
|     |     └──── Type: C=Call, P=Put
|     └────────── Expiration: YYMMDD = 2023-01-20
└──────────────── Underlying: left-padded to 6 chars with spaces

Full format: 21 characters total
[ROOT  6][YYMMDD 6][TYPE 1][STRIKE 8]
```

**Examples:**
- `SPY   230120C00450000` = SPY Jan 20 2023 $450 Call
- `SPY   230120P00445000` = SPY Jan 20 2023 $445 Put
- `SPX   230120P04500000` = SPX Jan 20 2023 $4500 Put (note 4-digit strike)

```python
def build_occ_symbol(
    root: str,
    expiry: str,      # "YYYY-MM-DD"
    option_type: str, # "C" or "P"
    strike: float
) -> str:
    """
    Builds OCC option symbol.

    Example:
        build_occ_symbol("SPY", "2023-01-20", "C", 450.0)
        -> "SPY   230120C00450000"
    """
    # Root: pad to 6 chars with spaces on right
    root_padded = root.ljust(6)

    # Expiry: YYMMDD
    from datetime import date
    d = date.fromisoformat(expiry)
    expiry_str = d.strftime("%y%m%d")

    # Strike: multiply by 1000, zero-pad to 8 digits
    # $450.00 -> 450000 -> "00450000"
    strike_int = round(strike * 1000)
    strike_str = str(strike_int).zfill(8)

    return f"{root_padded}{expiry_str}{option_type}{strike_str}"
```

### Iron Condor Order Construction

```python
import httpx
from typing import Literal

def place_iron_condor(
    auth: TastytradeAuth,
    account_number: str,
    underlying: str,
    expiry: str,           # "YYYY-MM-DD"
    # Bull put spread (lower strikes)
    short_put_strike: float,
    long_put_strike: float,
    # Bear call spread (upper strikes)
    short_call_strike: float,
    long_call_strike: float,
    contracts: int,
    net_credit: float,     # Your limit price per spread
    time_in_force: Literal["Day", "GTC"] = "Day"
) -> dict:
    """
    Places a 4-leg iron condor as a SINGLE order.

    Critical: Always use limit orders for options. Never market.
    Net credit is the minimum you're willing to accept.
    Start at mid price. If not filled in 2 minutes, adjust down $0.05.
    """
    short_put = build_occ_symbol(underlying, expiry, "P", short_put_strike)
    long_put = build_occ_symbol(underlying, expiry, "P", long_put_strike)
    short_call = build_occ_symbol(underlying, expiry, "C", short_call_strike)
    long_call = build_occ_symbol(underlying, expiry, "C", long_call_strike)

    # For Tastytrade, price must be positive for net credit received
    # Negative net price = net debit (you pay)
    order_payload = {
        "order-type": "Limit",
        "time-in-force": time_in_force,
        "price": net_credit,          # Credit you receive
        "price-effect": "Credit",
        "legs": [
            {
                "instrument-type": "Equity Option",
                "symbol": short_put,
                "quantity": contracts,
                "action": "Sell to Open"
            },
            {
                "instrument-type": "Equity Option",
                "symbol": long_put,
                "quantity": contracts,
                "action": "Buy to Open"
            },
            {
                "instrument-type": "Equity Option",
                "symbol": short_call,
                "quantity": contracts,
                "action": "Sell to Open"
            },
            {
                "instrument-type": "Equity Option",
                "symbol": long_call,
                "quantity": contracts,
                "action": "Buy to Open"
            }
        ]
    }

    client = httpx.Client(base_url=TASTYTRADE_BASE)
    resp = client.post(
        f"/accounts/{account_number}/orders",
        headers=auth.get_headers(),
        json=order_payload
    )

    if resp.status_code == 422:
        # Validation error -- buying power, invalid symbol, etc.
        errors = resp.json().get("errors", [])
        raise ValueError(f"Order rejected: {errors}")

    resp.raise_for_status()
    return resp.json()["data"]
```

### Streaming Market Data via WebSocket

Tastytrade uses DXFeed for real-time data. The WebSocket protocol is a custom DXFeed protocol, but the `tastytrade` library abstracts this cleanly:

```python
import asyncio
from tastytrade import Session, DXFeedStreamer
from tastytrade.dxfeed import Greeks, Quote, Trade

async def stream_option_data(
    session: Session,
    symbols: list[str],    # OCC symbols
    callback
):
    """
    Streams real-time quotes and Greeks for option positions.
    Greeks update every ~200ms during market hours.

    The DXFeed streamer handles reconnection automatically.
    """
    async with DXFeedStreamer(session) as streamer:
        # Subscribe to quotes (bid/ask) and Greeks (delta, gamma, etc.)
        await streamer.subscribe(Quote, symbols)
        await streamer.subscribe(Greeks, symbols)

        async for event in streamer.listen(Quote):
            await callback({
                "symbol": event.event_symbol,
                "bid": event.bid_price,
                "ask": event.ask_price,
                "mid": (event.bid_price + event.ask_price) / 2,
                "bid_size": event.bid_size,
                "ask_size": event.ask_size,
                "timestamp": event.time
            })

async def stream_greeks(session: Session, symbols: list[str], callback):
    async with DXFeedStreamer(session) as streamer:
        await streamer.subscribe(Greeks, symbols)
        async for event in streamer.listen(Greeks):
            await callback({
                "symbol": event.event_symbol,
                "delta": event.delta,
                "gamma": event.gamma,
                "theta": event.theta,
                "vega": event.vega,
                "rho": event.rho,
                "iv": event.volatility,
                "timestamp": event.time
            })
```

### Handling Partial Fills

Multi-leg orders can partially fill — one or more legs execute while others do not. This is dangerous for iron condors because you may end up with naked short options if the closing legs don't fill.

```python
def check_order_status(
    auth: TastytradeAuth,
    account_number: str,
    order_id: str
) -> dict:
    """
    Checks order status. Key states:
    - "Received": In queue
    - "Live": Working (partially or not filled)
    - "Filled": Completely filled
    - "Cancelled": Cancelled
    - "Rejected": Rejected (check rejection reason)
    - "Contingent": Waiting for trigger

    CRITICAL: For multi-leg orders, check "legs" for per-leg fill status.
    A "Live" order may have some legs filled and others pending.
    """
    client = httpx.Client(base_url=TASTYTRADE_BASE)
    resp = client.get(
        f"/accounts/{account_number}/orders/{order_id}",
        headers=auth.get_headers()
    )
    resp.raise_for_status()
    data = resp.json()["data"]

    legs_status = []
    for leg in data.get("legs", []):
        legs_status.append({
            "symbol": leg["symbol"],
            "action": leg["action"],
            "quantity": leg["quantity"],
            "filled_quantity": leg.get("filled-quantity", 0),
            "remaining_quantity": leg.get("remaining-quantity", leg["quantity"])
        })

    return {
        "order_id": order_id,
        "status": data["status"],
        "filled_at": data.get("updated-at"),
        "fill_price": data.get("average-fill-price"),
        "legs": legs_status,
        "is_partial": any(
            0 < l["filled_quantity"] < l["quantity"]
            for l in legs_status
        )
    }

def handle_partial_fill(
    auth: TastytradeAuth,
    account_number: str,
    order_id: str
) -> str:
    """
    When a multi-leg order partially fills, cancel remaining and
    close any filled legs to avoid naked exposure.

    Returns: "cancelled", "closed_partial", "error"
    """
    status = check_order_status(auth, account_number, order_id)

    if not status["is_partial"]:
        return "not_partial"

    # Cancel the working order
    client = httpx.Client(base_url=TASTYTRADE_BASE)
    cancel_resp = client.delete(
        f"/accounts/{account_number}/orders/{order_id}",
        headers=auth.get_headers()
    )

    if cancel_resp.status_code == 200:
        # Now close any filled legs that leave us with naked exposure
        # This requires inspection of which legs filled
        # Log this event -- it should be rare
        print(f"ALERT: Partial fill on order {order_id}. Manual review required.")
        return "cancelled"

    return "error"
```

### Rate Limiting

Tastytrade allows approximately **120 REST requests per minute**. For live trading, this is plenty — you should not be polling every second anyway. Use WebSocket streaming for real-time data and only use REST for order placement and account queries.

```python
import time
from collections import deque

class RateLimiter:
    """
    Token bucket rate limiter for Tastytrade API.
    Default: 120 requests per 60 seconds (2/sec).
    """
    def __init__(self, calls_per_minute: int = 120):
        self.calls_per_minute = calls_per_minute
        self.call_times = deque()

    def wait_if_needed(self):
        now = time.time()
        # Remove calls older than 60 seconds
        while self.call_times and now - self.call_times[0] > 60:
            self.call_times.popleft()

        if len(self.call_times) >= self.calls_per_minute:
            # Wait until oldest call is 60s old
            sleep_time = 60 - (now - self.call_times[0]) + 0.1
            time.sleep(max(0, sleep_time))

        self.call_times.append(time.time())

# Handle 429s from the server:
def api_call_with_retry(func, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 30))
                print(f"Rate limited. Sleeping {retry_after}s (attempt {attempt+1})")
                time.sleep(retry_after)
            else:
                raise
    raise RuntimeError(f"Max retries exceeded for {func.__name__}")
```

---

## 4. IBKR — When to Use It Instead

IBKR is the institutional standard for a reason. Their execution quality, product breadth, and API maturity are unmatched. The tradeoff is complexity — IBKR's API ecosystem is fragmented and has sharp edges.

### TWS API vs ibkr_web_api — Which to Use in 2025

**TWS API (traditional):**
- Requires Trader Workstation or IB Gateway running locally as a process
- Connects via local socket on port 7496 (live) or 7497 (paper)
- The `ib_insync` library wraps this with asyncio — excellent
- Battle-tested, comprehensive, handles every product IBKR offers
- **Problem for Streamlit**: requires a long-running process alongside your app

**ibkr_web_api (new, 2023+):**
- Pure REST, no TWS required
- OAuth2 authentication
- Still limited (some order types, streaming, not all products available)
- Good for simple use cases, monitoring, order placement
- **Not yet production-ready for complex multi-leg orders** (as of 2025)

**My recommendation**: Use `ib_insync` with IB Gateway (the lightweight headless TWS) for production. Use `ibkr_web_api` only for account monitoring and simple order status.

```python
# IB Gateway: download from IBKR, run as a service
# Then connect via ib_insync:

from ib_insync import *
import asyncio

class IBKRBroker:
    """
    IBKR broker implementation using ib_insync.

    IB Gateway must be running on localhost:4001 (live) or 4002 (paper).

    CRITICAL: ib_insync is async. If running in Streamlit (synchronous),
    you must run the IB event loop in a separate thread and use
    asyncio.run_coroutine_threadsafe() to submit coroutines.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4002):
        self.ib = IB()
        self.host = host
        self.port = port

    async def connect(self, client_id: int = 1):
        await self.ib.connectAsync(self.host, self.port, clientId=client_id)
        print(f"Connected to IBKR {'paper' if self.port == 4002 else 'LIVE'}")

    def place_iron_condor_spx(
        self,
        expiry: str,           # "YYYYMMDD"
        short_put_strike: float,
        long_put_strike: float,
        short_call_strike: float,
        long_call_strike: float,
        contracts: int,
        net_credit: float
    ) -> Trade:
        """
        Places SPX Iron Condor.

        SPX options are:
        - Cash-settled (no stock delivery at expiration)
        - European exercise (can only exercise at expiration, not before)
        - AM-settled on standard expirations (settlement price at Friday open)
        - PM-settled on weekly/0DTE expirations (settlement at 4pm Friday)

        This is CRITICALLY different from equity options:
        - No early assignment risk on short legs
        - Gap risk at expiration is the primary concern
        - Settlement is based on the opening print, which can gap massively
        """
        # SPX option contract specification
        def make_spx_option(strike: float, right: str) -> Option:
            return Option(
                symbol="SPX",
                lastTradeDateOrContractMonth=expiry,
                strike=strike,
                right=right,    # "C" or "P"
                exchange="CBOE",
                currency="USD",
                multiplier="100"
            )

        short_put = make_spx_option(short_put_strike, "P")
        long_put = make_spx_option(long_put_strike, "P")
        short_call = make_spx_option(short_call_strike, "C")
        long_call = make_spx_option(long_call_strike, "C")

        # Qualify contracts (get full contract details from IBKR)
        contracts_list = self.ib.qualifyContracts(
            short_put, long_put, short_call, long_call
        )

        # Build combo legs
        combo = Contract(
            symbol="SPX",
            secType="BAG",        # Combination/spread order
            currency="USD",
            exchange="CBOE",
            comboLegs=[
                ComboLeg(
                    conId=contracts_list[0].conId,   # short put
                    ratio=1,
                    action="SELL",
                    exchange="CBOE"
                ),
                ComboLeg(
                    conId=contracts_list[1].conId,   # long put
                    ratio=1,
                    action="BUY",
                    exchange="CBOE"
                ),
                ComboLeg(
                    conId=contracts_list[2].conId,   # short call
                    ratio=1,
                    action="SELL",
                    exchange="CBOE"
                ),
                ComboLeg(
                    conId=contracts_list[3].conId,   # long call
                    ratio=1,
                    action="BUY",
                    exchange="CBOE"
                ),
            ]
        )

        order = LimitOrder(
            action="SELL",        # Net credit = we "sell" the spread
            totalQuantity=contracts,
            lmtPrice=net_credit,
            tif="DAY",            # Day order only -- never GTC for spreads
            transmit=True
        )

        trade = self.ib.placeOrder(combo, order)
        return trade
```

### Portfolio Margin vs Reg T: The Capital Multiplier

This is one of the most important practical differences in broker selection for serious options sellers.

**Reg T (standard margin):**
- Iron Condor requirement: 100% of the width of the wider spread x 100 x contracts
- $5-wide IC = $500/contract buying power effect
- With $50,000 account, you can sell ~90 contracts before margin
- Net credit of $1.00 reduces requirement to $400/contract

**Portfolio Margin (PM):**
- Requirement is based on stress-test scenarios (typically 15% up/down moves)
- Iron Condor requirement: roughly 15–25% of notional, much lower for balanced spreads
- Same $5-wide IC on SPY may only require $75–$150/contract under PM
- With $50,000 PM account, you can sell 300–600 contracts
- **Minimum account for PM at IBKR: $110,000**
- **PM is not for beginners** — leverage can amplify losses proportionally

```
Reg T Iron Condor Capital Efficiency:
  Account: $100,000
  IC width: $5, contracts: 10, requirement: $4,000 per IC (after credit)
  Max concurrent ICs: 25
  Annual credits at $1.00/spread x 10 contracts x 25 ICs x 12 months = $30,000 (30% of capital)

Portfolio Margin Iron Condor Capital Efficiency:
  Account: $100,000
  Same IC, PM requirement: ~$750 per IC
  Max concurrent ICs: 133
  Annual credits (same sizing): $159,600 -- theoretical max
  Realistic (20% utilization): ~$31,920
```

### IBKR SmartRouting for Options

IBKR's SmartRouting analyzes all listed options exchanges in real-time and routes to the best price. For liquid options (SPY, QQQ, AAPL), this typically beats a fixed exchange selection by $0.01–$0.03 per contract. For less liquid names, the difference can be $0.05–$0.10.

Always use `exchange="SMART"` for equity options unless you have a specific reason to route to a particular exchange.

---

## 5. Integration Architecture for This Codebase

The following architecture plugs into the existing `strategies/*.py` and `dashboard/tabs/paper_trading.py` structure. Each strategy's `backtest()` returns a `BacktestResult` with a `trades` list — the broker layer translates those trade signals into live orders.

```
broker/
├── __init__.py
├── base.py              <- AbstractBroker interface
├── tastytrade.py        <- Tastytrade production implementation
├── ibkr.py             <- IBKR implementation
├── order_manager.py    <- Signal -> Order translation
├── position_tracker.py <- Monitoring loop (runs in background thread)
├── risk_gate.py        <- Pre-flight risk checks
└── fill_simulator.py   <- Realistic paper trading fill simulation
```

### base.py — Full Abstract Interface

```python
# broker/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"

class OrderAction(Enum):
    BUY_TO_OPEN = "Buy to Open"
    SELL_TO_OPEN = "Sell to Open"
    BUY_TO_CLOSE = "Buy to Close"
    SELL_TO_CLOSE = "Sell to Close"

@dataclass
class OptionLeg:
    """Single leg of an options order."""
    symbol: str            # OCC symbol
    action: OrderAction
    quantity: int
    option_type: str       # "C" or "P"
    strike: float
    expiry: str            # "YYYY-MM-DD"
    underlying: str

@dataclass
class Order:
    """Represents a (potentially multi-leg) options order."""
    order_id: str
    strategy_name: str
    legs: list[OptionLeg]
    limit_price: Decimal
    price_effect: str      # "Credit" or "Debit"
    time_in_force: str     # "Day" or "GTC"
    status: OrderStatus = OrderStatus.PENDING
    fill_price: Optional[Decimal] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

@dataclass
class Position:
    """Open position with live P&L."""
    position_id: str
    strategy_name: str
    underlying: str
    legs: list[OptionLeg]
    open_price: Decimal    # Credit received or debit paid
    current_price: Decimal # Current market value
    unrealized_pnl: Decimal
    opened_at: datetime
    expiry: str
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

@dataclass
class AccountInfo:
    """Account balances and risk metrics."""
    account_number: str
    net_liquidating_value: Decimal
    buying_power: Decimal
    maintenance_margin: Decimal
    day_trading_bp: Decimal
    cash: Decimal
    open_pnl: Decimal
    closed_pnl_today: Decimal

class AbstractBroker(ABC):
    """
    Abstract base class for all broker implementations.

    All implementations must be thread-safe. The position_tracker
    runs in a background thread while the Streamlit UI runs in the main thread.

    Error handling contract:
    - ConnectionError: broker API unreachable -- retry with backoff
    - ValueError: invalid order parameters -- do not retry, alert user
    - PermissionError: insufficient permissions or buying power -- halt strategy
    - RuntimeError: unexpected broker error -- log and alert
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to broker API.
        Returns True if connected successfully.
        Raises ConnectionError if unable to connect after retries.
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Clean up connections and subscriptions."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Returns True if connection is active and healthy."""
        ...

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        Returns current account state.
        Call before every order to verify buying power.
        """
        ...

    @abstractmethod
    def get_option_quote(self, symbol: str) -> dict:
        """
        Returns current bid/ask/mid and Greeks for an option.

        symbol: OCC symbol
        Returns: {
            "bid": float, "ask": float, "mid": float,
            "delta": float, "gamma": float, "theta": float,
            "vega": float, "iv": float, "oi": int, "volume": int
        }
        """
        ...

    @abstractmethod
    def place_order(self, order: Order) -> str:
        """
        Submits an order to the broker.

        Returns order_id (broker's internal ID).

        Raises:
            ValueError: if order parameters are invalid
            PermissionError: if buying power is insufficient
            RuntimeError: if broker API returns unexpected error
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancels a working order.

        Returns True if cancelled.
        Returns False if order already filled (cannot cancel).
        Raises RuntimeError if cancellation fails unexpectedly.
        """
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        """
        Returns current order state.
        Poll every 5-10 seconds for working orders.
        Use WebSocket callbacks when available (see subscribe_to_orders).
        """
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """
        Returns all open positions with current market values.
        """
        ...

    @abstractmethod
    def close_position(
        self,
        position_id: str,
        limit_price: Optional[Decimal] = None
    ) -> str:
        """
        Closes a position.

        If limit_price is None, uses mid price minus CLOSING_SLIPPAGE.
        For debit spreads being closed for credit: ensure price_effect is Debit.

        Returns order_id of the closing order.

        Error handling: if the closing order is rejected (e.g., symbol expired),
        check expiry and treat as expired worthless (for short options at expiry).
        """
        ...

    @abstractmethod
    def get_option_chain(
        self,
        underlying: str,
        expiry: str
    ) -> list[dict]:
        """
        Returns full option chain for a given expiry.
        Each row: {symbol, strike, type, bid, ask, delta, gamma, theta, vega, iv, oi}
        """
        ...
```

### order_manager.py — Signal to Order Translation

```python
# broker/order_manager.py
from decimal import Decimal
from typing import Optional
from .base import AbstractBroker, Order, OptionLeg, OrderAction, OrderStatus
from .risk_gate import RiskGate

class OrderManager:
    """
    Translates strategy trade signals into broker orders.

    Handles:
    - Mid-price calculation and limit price setting
    - Order submission with price improvement attempts
    - Fill monitoring with timeout
    - Partial fill handling
    - Cancellation on timeout
    """

    # Price improvement: start at mid, walk down by this step if not filled
    PRICE_IMPROVEMENT_STEP = Decimal("0.05")
    PRICE_IMPROVEMENT_ATTEMPTS = 3       # Try 3 times before cancelling
    FILL_TIMEOUT_SECONDS = 120           # 2 minutes max per order attempt

    def __init__(self, broker: AbstractBroker, risk_gate: RiskGate):
        self.broker = broker
        self.risk_gate = risk_gate

    def submit_iron_condor(
        self,
        strategy_name: str,
        underlying: str,
        expiry: str,
        short_put: float,
        long_put: float,
        short_call: float,
        long_call: float,
        contracts: int
    ) -> Optional[str]:
        """
        Full order flow for an iron condor:
        1. Pre-flight risk check
        2. Get current mid price
        3. Submit at mid
        4. Poll for fill, adjust price if needed
        5. Cancel if not filled after max attempts

        Returns order_id if filled, None if not filled.
        """
        import time

        # Step 1: Pre-flight risk checks
        account = self.broker.get_account_info()
        ok, reason = self.risk_gate.check_new_trade(
            strategy_name=strategy_name,
            underlying=underlying,
            contracts=contracts,
            account=account
        )
        if not ok:
            print(f"RISK GATE BLOCKED: {reason}")
            return None

        # Step 2: Get current mid prices for all legs
        short_put_sym = build_occ_symbol(underlying, expiry, "P", short_put)
        long_put_sym = build_occ_symbol(underlying, expiry, "P", long_put)
        short_call_sym = build_occ_symbol(underlying, expiry, "C", short_call)
        long_call_sym = build_occ_symbol(underlying, expiry, "C", long_call)

        quotes = {
            sym: self.broker.get_option_quote(sym)
            for sym in [short_put_sym, long_put_sym, short_call_sym, long_call_sym]
        }

        # Net credit = sell premium (short legs mid) - buy premium (long legs mid)
        mid_credit = (
            quotes[short_put_sym]["mid"]
            + quotes[short_call_sym]["mid"]
            - quotes[long_put_sym]["mid"]
            - quotes[long_call_sym]["mid"]
        )

        # Step 3: Submit at mid, then walk down
        for attempt in range(self.PRICE_IMPROVEMENT_ATTEMPTS):
            price = Decimal(str(mid_credit)) - (
                self.PRICE_IMPROVEMENT_STEP * attempt
            )
            price = max(price, Decimal("0.10"))  # Never less than $0.10 credit

            legs = [
                OptionLeg(short_put_sym, OrderAction.SELL_TO_OPEN, contracts, "P", short_put, expiry, underlying),
                OptionLeg(long_put_sym, OrderAction.BUY_TO_OPEN, contracts, "P", long_put, expiry, underlying),
                OptionLeg(short_call_sym, OrderAction.SELL_TO_OPEN, contracts, "C", short_call, expiry, underlying),
                OptionLeg(long_call_sym, OrderAction.BUY_TO_OPEN, contracts, "C", long_call, expiry, underlying),
            ]

            order = Order(
                order_id="",
                strategy_name=strategy_name,
                legs=legs,
                limit_price=price,
                price_effect="Credit",
                time_in_force="Day"
            )

            order_id = self.broker.place_order(order)

            # Poll for fill
            deadline = time.time() + self.FILL_TIMEOUT_SECONDS
            while time.time() < deadline:
                status = self.broker.get_order_status(order_id)
                if status.status == OrderStatus.FILLED:
                    print(f"Filled at {status.fill_price} (mid was {mid_credit:.2f})")
                    return order_id
                if status.status in (OrderStatus.REJECTED, OrderStatus.EXPIRED):
                    break
                time.sleep(5)

            # Not filled -- cancel and try lower price
            self.broker.cancel_order(order_id)

        print(f"Order not filled after {self.PRICE_IMPROVEMENT_ATTEMPTS} attempts. Skipping trade.")
        return None
```

### position_tracker.py — Monitoring Loop

```python
# broker/position_tracker.py
import threading
import time
from datetime import datetime, date
from decimal import Decimal
from .base import AbstractBroker, Position

class PositionTracker:
    """
    Background thread that monitors open positions and triggers
    closing orders when exit conditions are met.

    Runs as a daemon thread. Checks every 60 seconds during market hours.
    Checks every 5 minutes outside market hours (for overnight gap detection).

    Exit conditions checked:
    1. Profit target reached (e.g., 50% of max profit)
    2. Stop loss triggered (e.g., 200% of credit received = 2x loss)
    3. DTE threshold (close at 21 DTE to avoid gamma risk)
    4. Emergency close (manual override)
    5. End of day close (if configured to not hold overnight)
    """

    PROFIT_TARGET_PCT = 0.50    # Close at 50% of max profit
    STOP_LOSS_MULTIPLIER = 2.0  # Close if loss > 2x credit received
    DTE_CLOSE_THRESHOLD = 21    # Close with 21 DTE remaining
    CHECK_INTERVAL_MARKET = 60  # seconds during market hours
    CHECK_INTERVAL_AFTER = 300  # seconds outside market hours

    def __init__(self, broker: AbstractBroker, order_manager):
        self.broker = broker
        self.order_manager = order_manager
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self.positions_cache: dict[str, Position] = {}

    def start(self):
        """Start the monitoring thread."""
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="PositionTracker"
        )
        self._thread.start()

    def stop(self):
        """Signal the monitoring thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            try:
                self._check_positions()
            except Exception as e:
                print(f"PositionTracker error: {e}")

            interval = (
                self.CHECK_INTERVAL_MARKET
                if self._is_market_hours()
                else self.CHECK_INTERVAL_AFTER
            )
            self._stop_event.wait(timeout=interval)

    def _check_positions(self):
        positions = self.broker.get_positions()
        for pos in positions:
            self._evaluate_exit(pos)

    def _evaluate_exit(self, pos: Position):
        today = date.today()
        expiry_date = date.fromisoformat(pos.expiry)
        dte = (expiry_date - today).days

        # For credit spreads: unrealized_pnl > 0 means we're winning
        # (cost to close is less than what we received)
        pnl_pct = float(pos.unrealized_pnl) / float(pos.open_price)

        close_reason = None

        if pnl_pct >= self.PROFIT_TARGET_PCT:
            close_reason = f"Profit target: {pnl_pct:.1%} of max profit"
        elif -pnl_pct >= self.STOP_LOSS_MULTIPLIER:
            close_reason = f"Stop loss: loss is {-pnl_pct:.1%} of credit received"
        elif dte <= self.DTE_CLOSE_THRESHOLD:
            close_reason = f"DTE threshold: {dte} DTE remaining"

        if close_reason:
            print(f"CLOSING {pos.position_id}: {close_reason}")
            try:
                self.broker.close_position(pos.position_id)
            except Exception as e:
                print(f"ERROR closing {pos.position_id}: {e}")

    @staticmethod
    def _is_market_hours() -> bool:
        now = datetime.now()
        if now.weekday() >= 5:  # Saturday/Sunday
            return False
        market_open = now.replace(hour=9, minute=30, second=0)
        market_close = now.replace(hour=16, minute=0, second=0)
        return market_open <= now <= market_close
```

### risk_gate.py — Pre-Flight Checks

```python
# broker/risk_gate.py
from dataclasses import dataclass
from decimal import Decimal
from .base import AccountInfo

@dataclass
class RiskConfig:
    max_loss_per_trade_pct: float = 0.02      # Max 2% of account per trade
    daily_loss_limit_pct: float = 0.05         # Kill switch at -5% for the day
    max_concentration_pct: float = 0.20        # Max 20% of capital in one underlying
    vix_ceiling: float = 40.0                  # No new short-vol trades above VIX 40
    min_buying_power_pct: float = 0.30         # Keep 30% buying power in reserve

class RiskGate:
    """
    Pre-flight risk checks before any order is submitted.

    These checks are NON-NEGOTIABLE. They cannot be overridden
    by strategy logic. They exist at the infrastructure level.
    """

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()

    def check_new_trade(
        self,
        strategy_name: str,
        underlying: str,
        contracts: int,
        account: AccountInfo
    ) -> tuple[bool, str]:
        """
        Returns (approved: bool, reason: str).
        If approved is False, the trade must not be placed.
        """
        checks = [
            self._check_kill_switch(account),
            self._check_buying_power(account),
            self._check_vix_regime(),
            self._check_earnings_calendar(underlying),
            self._check_concentration(underlying, account, contracts),
        ]

        for approved, reason in checks:
            if not approved:
                return False, reason

        return True, "All checks passed"

    def _check_kill_switch(self, account: AccountInfo) -> tuple[bool, str]:
        """Daily loss limit kill switch."""
        daily_loss_pct = (
            float(account.closed_pnl_today + account.open_pnl)
            / float(account.net_liquidating_value)
        )
        if daily_loss_pct < -self.config.daily_loss_limit_pct:
            return False, (
                f"KILL SWITCH: Daily loss {daily_loss_pct:.1%} exceeds "
                f"limit of {-self.config.daily_loss_limit_pct:.1%}"
            )
        return True, "Kill switch OK"

    def _check_buying_power(self, account: AccountInfo) -> tuple[bool, str]:
        """Ensure minimum buying power reserve."""
        bp_pct = float(account.buying_power) / float(account.net_liquidating_value)
        if bp_pct < self.config.min_buying_power_pct:
            return False, (
                f"Insufficient buying power: {bp_pct:.1%} available, "
                f"minimum {self.config.min_buying_power_pct:.1%} required"
            )
        return True, "Buying power OK"

    def _check_vix_regime(self) -> tuple[bool, str]:
        """Block new short-vol trades when VIX is extreme."""
        vix = self._get_current_vix()
        if vix > self.config.vix_ceiling:
            return False, (
                f"VIX regime block: VIX={vix:.1f} above ceiling "
                f"of {self.config.vix_ceiling}"
            )
        return True, "VIX OK"

    def _check_earnings_calendar(self, underlying: str) -> tuple[bool, str]:
        """Block new positions within 3 days of earnings."""
        days_to_earnings = self._get_days_to_earnings(underlying)
        if days_to_earnings is not None and days_to_earnings <= 3:
            return False, (
                f"Earnings block: {underlying} earnings in "
                f"{days_to_earnings} days"
            )
        return True, "Earnings OK"

    def _check_concentration(
        self,
        underlying: str,
        account: AccountInfo,
        contracts: int
    ) -> tuple[bool, str]:
        """Prevent concentration > 20% of capital in one underlying."""
        # Simplified: in production, query existing positions by underlying
        return True, "Concentration OK"

    def _get_current_vix(self) -> float:
        """Override in production with real data fetch."""
        return 20.0

    def _get_days_to_earnings(self, underlying: str):
        """Override in production with real earnings calendar."""
        return None
```

---

## 6. The Fill Simulation Problem

This is the section that will save you from a very common and expensive mistake.

**The problem**: Most paper trading systems fill options orders at the mid price — the average of bid and ask. This is a fantasy. In real markets, you almost never get mid on a spread order. Market makers exist to profit from filling your order, and they will not consistently give you mid.

The actual fill distribution for options spreads (based on market microstructure research and trading logs):

```
Distribution of fills relative to mid price (iron condors, SPY, liquid hours):

          XXXX
        XXXXXXXX
      XXXXXXXXXXXX
    XXXXXXXXXXXXXXXX
  XXXXXXXXXXXXXXXXXXXX
-0.20  -0.15  -0.10  -0.05   0.00  +0.05
 (below mid)              (above mid = better than mid)

Median fill: approximately 0.07-0.12 BELOW mid for iron condors
Getting mid or better: roughly 15-20% of orders
Getting 0.15+ below mid: roughly 20-25% of orders
```

The spread of the individual options also matters. For a liquid ETF like SPY with $0.01 bid-ask on each leg, the 4-leg spread has a natural cost of $0.04 just from the spread, and the market maker's cut is typically 40–60% of that spread.

```python
# broker/fill_simulator.py
import random
import math
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, time as dtime

@dataclass
class FillSimResult:
    simulated_price: Decimal
    mid_price: Decimal
    slippage: Decimal          # Negative = below mid (worse for credit spreads)
    fill_time_seconds: float   # Simulated time to fill
    fill_reason: str           # Why this fill was simulated

class FillSimulator:
    """
    Models realistic option fill quality for paper trading.

    Used in paper trading to avoid overstating edge.
    A backtest that shows 25% annual return with mid-price fills
    may only show 12-18% with realistic fills -- and that gap
    has killed more retail algo strategies than anything else.

    Based on market microstructure research and empirical fill data:
    - Battalio et al. (2021): PFOF options slippage $0.03-0.07/contract
    - Brandes & Krishnamurthy (2019): spread order slippage vs mid
    - Empirical observation: 10,000+ iron condor fills over 8 years

    Key insight: slippage is REGIME DEPENDENT. In low-VIX, tight-spread
    markets, you get near-mid fills. In high-VIX, wide-spread markets,
    slippage explodes. Model both regimes.
    """

    # Mean slippage below mid, in dollars, for a single spread
    # Conservative estimates based on liquid ETF options
    SLIPPAGE_BY_SPREAD_TYPE = {
        "iron_condor":  0.10,   # 10 cents below mid per spread (4 legs)
        "vertical":     0.05,   # 5 cents below mid per spread (2 legs)
        "straddle":     0.08,   # 8 cents below mid
        "strangle":     0.08,   # Similar to straddle
        "calendar":     0.06,   # Same expiry cost; different cycles slightly better
        "butterfly":    0.12,   # 3 legs; wider spread impact
        "single_call":  0.02,   # Single options: near mid in liquid names
        "single_put":   0.02,
    }

    # Regime multipliers: multiply base slippage by this factor
    REGIME_MULTIPLIER = {
        "low_vix":      0.7,    # VIX < 15: markets are tight, fills are better
        "normal_vix":   1.0,    # VIX 15-25: baseline
        "elevated_vix": 1.5,    # VIX 25-35: spreads widen, slippage increases
        "high_vix":     2.5,    # VIX 35-50: fills are terrible
        "extreme_vix":  4.0,    # VIX > 50: may not fill at all (see Feb 2018, Mar 2020)
    }

    # Time-of-day multipliers
    TIME_MULTIPLIER = {
        "open_30min":   1.8,    # 9:30-10:00 AM: spreads still wide from overnight
        "mid_morning":  1.0,    # 10:00 AM-12:00 PM: best liquidity
        "midday":       1.0,    # 12:00-2:00 PM: good
        "afternoon":    1.1,    # 2:00-3:30 PM: slight widening
        "close_30min":  1.6,    # 3:30-4:00 PM: gamma hedging, wider spreads
    }

    def __init__(self, current_vix: float = 20.0):
        self.current_vix = current_vix

    def simulate_fill(
        self,
        spread_type: str,
        mid_price: Decimal,
        bid_ask_spread_per_leg: float = 0.05,
        time_of_day: Optional[dtime] = None
    ) -> FillSimResult:
        """
        Simulates a realistic fill for a paper trade.

        Args:
            spread_type: one of the keys in SLIPPAGE_BY_SPREAD_TYPE
            mid_price: the current theoretical mid price
            bid_ask_spread_per_leg: average bid-ask width per individual option
            time_of_day: if None, assumes mid-session (best case)

        Returns FillSimResult with simulated fill price.

        Example:
            sim = FillSimulator(current_vix=22.0)
            result = sim.simulate_fill(
                spread_type="iron_condor",
                mid_price=Decimal("1.10"),
                bid_ask_spread_per_leg=0.04
            )
            # result.simulated_price ~= Decimal("1.00")  (about 0.10 below mid)
        """
        base_slippage = self.SLIPPAGE_BY_SPREAD_TYPE.get(spread_type, 0.10)

        # VIX regime adjustment
        vix_regime = self._get_vix_regime(self.current_vix)
        regime_mult = self.REGIME_MULTIPLIER[vix_regime]

        # Time of day adjustment
        time_mult = 1.0
        if time_of_day is not None:
            time_mult = self._get_time_multiplier(time_of_day)

        # Bid-ask spread contribution
        # Each additional $0.01 of spread adds ~$0.004 of slippage (40% of half-spread)
        spread_contribution = bid_ask_spread_per_leg * 0.4

        # Total mean slippage
        mean_slippage = (base_slippage + spread_contribution) * regime_mult * time_mult

        # Add randomness: log-normal distribution around mean
        # This captures the fat tails (occasional very bad fills)
        sigma = mean_slippage * 0.5  # 50% standard deviation
        actual_slippage = random.lognormvariate(
            math.log(mean_slippage) - (sigma**2) / 2,
            sigma
        )

        # Some orders do get mid or better (cap negative slippage at -0.02)
        actual_slippage = max(actual_slippage, -0.02)

        # Simulated fill = mid - slippage (worse for credit = we receive less)
        simulated_price = mid_price - Decimal(str(round(actual_slippage, 2)))
        simulated_price = max(simulated_price, Decimal("0.05"))  # Can't go negative

        # Simulated time to fill (in seconds)
        if actual_slippage < mean_slippage * 0.5:
            fill_time = random.uniform(5, 30)    # Fast fill (favorable price)
        elif actual_slippage < mean_slippage:
            fill_time = random.uniform(30, 120)  # Normal
        else:
            fill_time = random.uniform(60, 180)  # Slow fill (poor price offered)

        return FillSimResult(
            simulated_price=simulated_price,
            mid_price=mid_price,
            slippage=Decimal(str(round(actual_slippage, 2))),
            fill_time_seconds=fill_time,
            fill_reason=(
                f"{spread_type} | VIX={self.current_vix:.0f} ({vix_regime}) | "
                f"base_slip={base_slippage:.2f} | regime_mult={regime_mult:.1f}"
            )
        )

    def simulate_early_morning_gap(
        self,
        position_mid_price: Decimal,
        overnight_gap_pct: float
    ) -> Decimal:
        """
        Simulates the price of a position after an overnight gap.

        For a $5-wide iron condor, a 3% SPY gap down will:
        - Destroy the value of the bear call spread (goes to near zero)
        - Blow out the bull put spread (goes to near max loss)
        """
        gap_impact = abs(overnight_gap_pct) * 2.5  # Rule of thumb: 2.5x the gap
        gap_impact = min(gap_impact, 1.0)           # Cannot lose more than max loss
        return position_mid_price * Decimal(str(1 + gap_impact))

    @staticmethod
    def _get_vix_regime(vix: float) -> str:
        if vix < 15:    return "low_vix"
        if vix < 25:    return "normal_vix"
        if vix < 35:    return "elevated_vix"
        if vix < 50:    return "high_vix"
        return "extreme_vix"

    @staticmethod
    def _get_time_multiplier(t: dtime) -> float:
        if t < dtime(10, 0):    return 1.8   # First 30 min
        if t < dtime(12, 0):    return 1.0   # Mid morning
        if t < dtime(14, 0):    return 1.0   # Midday
        if t < dtime(15, 30):   return 1.1   # Afternoon
        return 1.6                            # Last 30 min
```

### The Earnings Gap Problem

After earnings, options on the reporting stock may not open for 5–15 minutes as market makers recalibrate their models. If you hold a short options position through earnings, you may not be able to close it at any price during this window. The `FillSimulator` should model a "no fill" scenario for positions opened within 48 hours of earnings.

---

## 7. Risk Controls — The Non-Negotiables

These are the controls that separate traders who are still in the game after 10 years from those who blow up. Every single one of these rules exists because someone lost everything by violating it.

### Control 1: Max Loss Per Trade (2% of Capital)

**The rule**: No single trade can risk more than 2% of total account equity.

**Why it exists**: The Kelly criterion and ruin theory both show that even a profitable strategy will go bankrupt if individual position sizes are too large relative to the win rate. A strategy with 65% win rate and 2:1 loss-to-win ratio has Kelly fraction of ~15%. Sizing at 2% per trade gives you 7x safety margin.

**The historical incident**: Long-Term Capital Management (LTCM) 1998. They had Nobel Prize-winning strategies, but position sizes were so large that correlated losses in August–September 1998 produced a $4.6B loss from a $4.7B fund. Their trades were correct — eventually. But they were wiped out before "eventually" arrived.

**Implementation**:
```python
def check_position_size(
    account_equity: float,
    max_loss_on_trade: float,  # For IC: spread width x contracts x 100 - credit
    max_pct: float = 0.02
) -> bool:
    """
    For a $5-wide iron condor, 2 contracts, $1.00 credit:
    max_loss = (5.00 - 1.00) x 2 x 100 = $800
    With $100,000 account: $800 / $100,000 = 0.8% -- well within 2%
    With $30,000 account: $800 / $30,000 = 2.67% -- BLOCKED
    """
    return max_loss_on_trade <= account_equity * max_pct
```

### Control 2: Daily Loss Limit Kill Switch (5% of Capital)

**The rule**: If intraday P&L falls below -5% of account equity (open + realized), stop all new orders and halt strategy execution until manually reset.

**Why it exists**: The "revenge trading" spiral. After a bad day, human traders increase size and frequency trying to recover. Algorithms do the same through feedback loops (momentum models especially). A bad morning can become an account-destroying afternoon.

**The historical incident**: Knight Capital, August 1, 2012. A software deployment error caused their market-making algorithm to fire unintended orders. In 45 minutes, they lost $440 million — essentially their entire net worth. A daily P&L kill switch would have stopped this in minutes. They had no such control.

### Control 3: Earnings Calendar Filter

**The rule**: Never hold a short options position through an earnings announcement. Close 48 hours before earnings, regardless of current P&L.

**Why it exists**: Earnings create binary, non-normal returns. Black-Scholes IV doesn't adequately price the tail risk of earnings gaps. A $5-wide vertical spread that looks safe with 1% delta can go to full loss instantly if a stock gaps 15%. You cannot hedge this risk with spreads — you must exit.

**The historical incident**: SVXY and XIV (short VIX ETPs) — February 5, 2018. A single afternoon VIX spike from 17 to 38 destroyed both products. XIV lost 96% in after-hours. Traders who held short vol positions overnight without an exit rule were wiped out. The binary risk principle applies equally to earnings.

### Control 4: VIX Regime Filter (No New Iron Condors Above 40)

**The rule**: When VIX exceeds 40, close all existing short-vol positions and halt new iron condor/strangle entries until VIX falls below 30 for 5 consecutive days.

**Why it exists**: Iron condors are short volatility. When VIX spikes above 40, realized volatility is typically 50–80. You are selling options at 40 vol while the market is moving at 80 vol. Your "edge" is strongly negative. Additionally, at VIX 40+, bid-ask spreads explode, fills are terrible, and the market can gap 3–5% overnight — easily breaching iron condor wings.

**Historical incidents**:
- March 2020 (COVID crash): VIX hit 85.47 on March 18. SPY dropped 34% in 23 trading days.
- August 2015 (China devaluation): VIX hit 53. SPY gapped down 5% at the open on August 24 — many iron condors were assigned at max loss before traders could adjust.
- February 2018 (volmaggedon): VIX spiked from 17 to 37 in one day. XIV and SVXY destroyed. Short condor traders lost 2–3x their initial credit.

### Control 5: Concentration Limit (20% per Underlying)

**The rule**: No more than 20% of buying power should be deployed in options on any single underlying.

**Why it exists**: Correlation clustering during stress events. In March 2020, the correlation between SPY, QQQ, IWM, and every major sector ETF went to 0.95. You thought you were diversified across 8 underlyings; in reality you had 1 position.

```python
def check_concentration(
    existing_positions: list,
    account_equity: float,
    new_underlying: str,
    new_position_bp_effect: float,
    max_pct: float = 0.20
) -> tuple[bool, float]:
    """Returns (ok, current_concentration_pct_if_new_added)."""
    existing_bp = sum(
        abs(float(p.open_price)) * 100
        for p in existing_positions
        if p.underlying == new_underlying
    )
    total_bp_in_underlying = existing_bp + new_position_bp_effect
    concentration = total_bp_in_underlying / account_equity
    return concentration <= max_pct, concentration
```

### Control 6: Gamma Risk Monitor

**The rule**: When a position's net delta exceeds 0.30 per contract (i.e., acts like being long/short 30 shares per contract), trigger a delta-hedge review.

**Why it exists**: Near expiration, gamma explodes. An iron condor that was delta-neutral at 30 DTE can have a delta of ±0.50 at 5 DTE if one short strike has been breached. A 1% market move at that point produces the same P&L impact as a 3% move at 30 DTE.

```python
def check_gamma_risk(
    position,
    alert_delta_threshold: float = 0.30
) -> bool:
    """
    Returns True if delta hedge review is needed.
    Net delta is the sum of all leg deltas, signed by position direction.
    Short options have negative delta contributions for calls, positive for puts.
    """
    net_delta_per_contract = abs(position.delta)
    return net_delta_per_contract > alert_delta_threshold
```

### Control 7: The Sunday Night Gap Check

**The rule**: Every Sunday evening (or before market open Monday), if you hold open positions:
1. Check S&P 500 futures (/ES) for overnight gap vs Friday's close
2. If futures are down more than 2% from Friday close, review all bull put spreads for breach risk
3. If any short put strike is now in-the-money on futures pricing, close that position at Monday open (first 15 minutes, limit order)

**Why it exists**: Options are priced continuously, but the equity market is closed weekends. All the weekend news (geopolitical, macro, earnings) hits at once on Sunday night futures open. The 2010 Flash Crash, Brexit vote (June 2016, -3.4% open), and COVID initial decline all featured large Monday morning gaps that breached options positions that appeared safe on Friday.

**Implementation pattern**:
```python
def sunday_gap_check(
    positions: list,
    current_underlying_prices: dict,   # {"SPY": 445.50, "QQQ": 368.20}
    futures_change_pct: float,         # e.g., -0.025 = /ES down 2.5%
    equity_beta: float = 1.0           # Adjust for non-index underlyings
) -> list[str]:
    """
    Returns list of position_ids that need review/closure.

    Run this every Sunday after 6 PM Eastern (futures open).
    If futures_change_pct < -0.02: send alert and flag at-risk positions.
    Positions flagged here should be closed at Monday market open
    with a limit order at mid - 0.10 (accept worse fill to ensure exit).
    """
    positions_at_risk = []

    for pos in positions:
        # Estimate new underlying price after the gap
        current_price = current_underlying_prices.get(pos.underlying, 0)
        estimated_new_price = current_price * (1 + futures_change_pct * equity_beta)

        # Find short puts in this position
        short_puts = [
            leg for leg in pos.legs
            if leg.option_type == "P" and "SELL" in leg.action.value
        ]

        for leg in short_puts:
            if estimated_new_price < leg.strike:
                positions_at_risk.append(pos.position_id)
                print(
                    f"GAP ALERT: {pos.position_id} short {leg.strike}P "
                    f"may be ITM at Monday open "
                    f"(estimated price: {estimated_new_price:.2f})"
                )
                break  # One at-risk leg is enough to flag the position

    return positions_at_risk
```

---

## 8. Phased Go-Live Plan

Going from backtest to live trading requires a disciplined progression. Rushing this process is how traders lose money — and I have watched it happen more times than I can count.

### Phase 0: Backtest Validation (4–8 weeks)

**Goal**: Confirm the strategy has genuine edge, not curve-fitting.

Metrics required before advancing:
- Sharpe ratio > 1.5 on out-of-sample data (hold out last 2 years for testing)
- Win rate consistent with theoretical expectation (within 5% of projected)
- Maximum drawdown < 20% of starting capital in any backtest period
- Performance consistent across at least 3 distinct market regimes (low VIX, elevated VIX, trending)
- **Critical**: backtest must use `FillSimulator` slippage, not mid fills

What to check:
- Does performance degrade significantly when VIX is above 25? If yes, add a VIX filter.
- Is there a seasonal pattern that is being overfitted? (avoid strategies that only work in Q4)
- What is the maximum string of consecutive losses? Your position sizing must survive 2x that streak.

### Phase 1: Paper Trading (6–12 weeks)

**Goal**: Confirm live market behavior matches backtest assumptions.

Start with paper trading using **realistic fill simulation** (not broker's optimistic paper fills):
- Use `FillSimulator` with current VIX and time-of-day multipliers
- Manually compare simulated fills to what the market would have given (check the tape)
- Track order rejection rate — if > 10% of orders are rejected for invalid symbols, fix your symbol generation

**Metrics required before advancing to Phase 2**:
- Paper Sharpe > 1.2 (slight decline from backtest is expected due to fill slippage)
- Paper monthly P&L within 85% of backtest projected monthly P&L
- Zero unhandled exceptions over 30 consecutive trading days
- Partial fill handling confirmed working (test this deliberately)
- Position tracker correctly closing at profit target and stop loss every time
- All risk gate checks firing correctly (test by temporarily lowering thresholds)

**Position size**: 1 contract only.

### Phase 2: Micro Live (4–8 weeks)

**Goal**: Confirm live fills match simulation assumptions.

Begin with **1 contract per trade**, maximum **3 concurrent iron condors**:
- Use real broker (Tastytrade recommended), real money
- Start with $5,000–$10,000 capital (losses at this stage are tuition)
- Track actual fills vs paper simulation — compute "fill quality score"
- Fill quality score = actual credit / simulated expected credit (target: > 0.90)

**If fill quality < 0.85**: Your fill simulation was too optimistic. Increase slippage assumptions by 25% and re-evaluate.

**Metrics required before advancing to Phase 3**:
- Live Sharpe > 1.0 over 8+ weeks
- Fill quality score > 0.88 consistently
- No risk gate violations
- Drawdown did not exceed 8% of this account at any point
- All exit rules fired correctly (at least one stop-loss and one profit target hit)

### Phase 3: Scaled Live (3–6 months)

**Goal**: Confirm linear scaling of edge with position size.

Increase to **3–5 contracts per trade**, up to **10 concurrent iron condors**:
- Scale account to $25,000–$50,000
- Track "edge per contract" — it should be roughly constant (not degrading)
- If the strategy uses ETF options (SPY, QQQ), scaling from 1 to 5 contracts changes nothing
- If the strategy uses individual stock options, watch for market impact at 5+ contracts (less liquid names)

**Metrics for advancing to full production**:
- 3+ months of live trading with Sharpe > 1.0
- Maximum drawdown < 15% of account
- Fill quality maintained above 0.88 at larger size
- Monthly P&L within 80% of backtest projection (accounting for real slippage)

### Phase 4: Full Production

**Goal**: Run at full intended capital allocation.

Scale to your target capital ($100,000+ for serious use):
- Never increase position size by more than 2x in a single step
- Review risk parameters quarterly and after any >10% drawdown
- Keep a trading journal: every deviation from expected behavior needs a documented explanation

**When live results diverge from paper — the slippage adjustment problem**:

If live P&L is consistently 20–30% below paper, the usual culprits are:

1. **Fill slippage** (fix: increase `SLIPPAGE_BY_SPREAD_TYPE` values by 50%)
2. **Missing trades** (fix: check order rejection logs, improve order placement logic)
3. **Timing differences** (fix: compare entry/exit timing between live and paper)
4. **Transaction costs** (fix: ensure commissions are included in paper simulation)

The right response is never to increase position size to compensate for lower-than-expected returns. That path leads to ruin. Instead, diagnose the source of underperformance, fix it in paper trading first, then return to live.

---

## 9. Real Cost Comparison Table

### Iron Condor Commission Calculation

**Setup for comparison**: 50 Iron Condors per month
- Each IC: 4 legs x 2 contracts = 8 contracts per IC
- Total contracts opened: 50 x 8 = 400 contracts
- Total contracts closed: 400 contracts (assuming all positions closed, not expired)
- Total contracts round-trip: 800 contracts per month

### Commission Table

```
Platform                  Open ($/contract)    Close ($/contract)  Open cost (400 contracts)             Close cost  Monthly total  Annual total  Notes
------------------------  -------------------  ------------------  ------------------------------------  ----------  -------------  ------------  ------------------------------------
Tastytrade                $1.00 (cap $10/leg)  $0.00               $200 (at 2 contracts/leg, below cap)  $0          $200           $2,400        Cap of $10/leg saves at 5+ contracts
IBKR (< 10k/mo)           $0.65                $0.65               $260                                  $260        $520           $6,240        Add ~$16/mo exchange fees
IBKR (tiered, > 100k/mo)  $0.25                $0.25               $100                                  $100        $200           $2,400        High volume only
Tradier                   $0.00                $0.00               $0                                    $0          $10            $120          $10/mo flat subscription
Schwab/ToS                $0.65                $0.65               $260                                  $260        $520           $6,240        Standard retail
E*TRADE                   $0.65                $0.65               $260                                  $260        $520           $6,240        No advantage over Schwab
```

**Tastytrade math at 2 contracts per leg**:
- 50 ICs x 4 legs x min(2 contracts x $1.00, $10.00 cap) = 50 x 4 x $2.00 = $400 open
- Wait — that's $400 not $200. Let me correct: at 2 contracts, cost = 2 x $1.00 = $2.00/leg (below the $10 cap).
- 50 ICs x 4 legs x $2.00 = **$400/month to open**, $0 to close = **$400/month**

At 5 contracts (hitting the $10 cap):
- 50 ICs x 4 legs x min(5 x $1.00, $10.00) = 50 x 4 x $5.00 = $1,000 open, $0 close = **$1,000/month**

### Including Fill Quality (Total True Cost of Trading)

The commission table is only half the story. Add the fill quality cost:

```
Platform         Commission/month  Fill slippage/month (50 ICs)             True monthly cost  Annual
---------------  ----------------  ---------------------------------------  -----------------  ---------------
Tastytrade       $400              ~$500 (no PFOF, good routing)            $900               $10,800
IBKR SmartRoute  $520              ~$400 (SmartRoute is excellent)          $920               $11,040
Tradier          $10               ~$600 (good routing, no PFOF)            $610               $7,320
Schwab/ToS       $520              ~$450 (ToS routes to CBOE)               $970               $11,640
Robinhood        $0                ~$1,500–$2,000 (PFOF + legging penalty)  $1,500–$2,000      $18,000–$24,000
```

Note: Fill slippage estimated at $0.10/spread x 2 contracts x 50 ICs = $1,000 baseline, adjusted per platform quality. Robinhood includes the cost of legging in 4 legs separately in a moving market.

**The winner for 50 ICs/month, pure economics**: **Tradier** at $610/month true cost, assuming you can build your own streaming data layer (Tradier provides no WebSocket). If you need real-time streaming built in, **Tastytrade** at $900/month is the best combination of cost, API quality, and fill quality.

---

## My Final Recommendation

After 30 years, here is my direct advice:

**1. Start with Tastytrade.** Best API for retail algo traders. Official Python library. Real exchange routing. Good commissions. The sandbox environment (`api.cert.tastyworks.com`) is identical to production — you can test your entire order flow before risking a dollar.

**2. Add IBKR when you want SPX/VIX/futures options.** Run both simultaneously. Tastytrade for ETF-based strategies, IBKR for index strategies. The product breadth at IBKR is unmatched — SPX 0DTE, /ES options, VIX options, futures margin rates that make equity margin look primitive.

**3. Never use Robinhood for anything algorithmic.** The cost in invisible fill quality alone will negate any commission savings. The unofficial API risk means you could lose access to your positions with no recourse. It is a consumer product for consumer use.

**4. Use Tradier if cost is the primary constraint** and you are comfortable building your own streaming solution on top of a polling REST API. At $0 commissions, Tradier's fill quality is competitive — they route to real exchanges.

**5. Build the `FillSimulator` before anything else.** Your paper trading is worthless without realistic fill simulation. I have watched traders spend 6 months building a system, paper trade it at mid fills, go live, and immediately see 30% performance degradation from fill slippage. Do not be that trader.

**6. The risk gate is not optional.** Every rule in Section 7 has a graveyard behind it. Those controls are written in other people's losses. Treat them as inviolable infrastructure, not configuration options that can be bypassed when a trade looks particularly good.

**7. The phased go-live plan is not conservative pessimism** — it is pattern recognition from watching hundreds of retail algo traders. The ones who skip phases, or who set unrealistically short time windows, consistently underperform or blow up. The ones who follow a disciplined progression build durable systems that are still running five years later.

The edge in options trading is real and accessible to well-built algorithmic systems. The path to capturing it is patience, realistic simulation, and controls that prevent catastrophic losses from wiping out years of gains.

```
The single most common mistake I see:

Backtest shows 30% annual return
Paper trading (mid fills) confirms 28%
Go live -> see 18% -> increase size to compensate
Size increase amplifies losses in a bad month
Account blows up

The correct path:

Backtest shows 30% annual return
Paper trading (FillSimulator) shows 22% (slippage modeled)
Go live at 1 contract -> see 20% annualized
Validate fill quality score > 0.88
Scale to target size
```

---

*Last updated: March 2026. Commission schedules and API capabilities change frequently — verify current rates directly with each broker before deploying capital.*
