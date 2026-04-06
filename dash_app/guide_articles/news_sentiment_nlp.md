# News Sentiment NLP Strategy
### Machine Reading the Market: Systematic Alpha from Text That Humans Process Too Slowly

---

## Detailed Introduction

Financial markets are information-processing machines, and their efficiency is imperfect not because humans are irrational but because they are slow. A Bloomberg terminal shows an earnings release the moment it hits the wire. A human analyst reads it, processes the key metrics, compares to consensus, and forms a view — in perhaps 5–10 minutes. An institutional trader executes based on that view in another minute. A retail investor reads about it on CNBC that afternoon. Natural language processing can process the same release in seconds, extract the key signals, and score the sentiment against consensus in a structured, consistent, scalable way. The edge is not that the machine is smarter — it is that it is faster and more consistent.

The systematic nature of NLP sentiment also eliminates the framing effects that distort human judgment. When a company reports "record revenue," a human reader feels a positive signal even if that revenue missed estimates — the word "record" triggers an emotional response. An NLP model trained on financial text (like FinBERT) understands that "record revenue that missed consensus expectations" is bearish, not bullish, because the critical variable is the comparison to expectations. The machine learns to filter signal from noise in financial language in a way that even experienced analysts frequently fail to do when processing information quickly under time pressure.

The pipeline has three tiers of implementation quality. Lexicon-based models (matching words to positive/negative dictionaries) are fast, transparent, and crude. Pre-trained language models fine-tuned on financial text (FinBERT, BloombergGPT) are substantially better at context and negation. Large language model extraction (using GPT-4 or similar to structure sentiment with explanations) is best quality but expensive and slow at scale. A practical implementation uses FinBERT for the volume processing and LLM extraction for the highest-priority content (earnings releases, major analyst reports, SEC filings).

Who is on the other side of this trade? Other investors who are processing the same information manually, with human latency and human emotional biases. The early-mover advantage in post-earnings positioning (in the first 15–30 minutes of the next trading day) goes to whoever processed the earnings release fastest and most accurately. In 2023, HFT and quant shops have largely captured the sub-second alpha. But the 5–30 minute window after a complex earnings release — where the narrative implications take time to be fully digested — remains partially available to sophisticated retail traders with NLP pipelines.

The sentiment z-score framework — comparing current sentiment to the trailing 30-day baseline for that specific stock — is the key signal construction insight. A z-score of +2.5 on META does not mean "META news is positive today" — it means "META news is unusually positive relative to how it has been covered recently." The comparison to recent history filters out the chronic positive or negative bias that different stocks carry in their media coverage and focuses on the change in tone that matters for price.

The ideal setup is a large, liquid stock with real-time news coverage, a post-earnings release that is genuinely more positive or negative than consensus, and a system fast enough to generate the z-score within 10 minutes of the release. The one thing that kills this strategy is sentiment without price confirmation — a stock can have very positive NLP sentiment and still fall if large institutional sellers are distributing stock for reasons not visible in the public news (index deletion, fund outflow, insider selling window).

---

## How It Works

**Three-tier NLP architecture:**
```
Tier 1 — Lexicon-based (fastest, weakest quality):
  Loughran-McDonald financial dictionary: 350 positive, 2,345 negative financial terms
  Each article scored: (positive_count − negative_count) / total_words
  Processing: < 0.1 seconds per article
  Weakness: "not bad" gets negative score; misses context

Tier 2 — FinBERT (best price/quality balance):
  Model: fine-tuned BERT on 1.8M financial news articles
  Output: [positive, negative, neutral] probability scores per article
  Processing: 2–5 seconds per article (GPU: < 0.5 seconds)
  Strength: understands context, negation, financial jargon
  Access: HuggingFace (free, open source)

Tier 3 — LLM extraction (best quality, highest cost):
  Prompt: "Rate the sentiment of this text for [TICKER] from -5 to +5.
           Consider: EPS vs estimate, revenue vs estimate, guidance direction,
           forward outlook language, management tone"
  Cost: $0.01–$0.10 per article (GPT-4o-mini)
  Use for: earnings releases, major analyst reports, material SEC filings only
```

**Signal construction:**
```python
# Step 1: Score each article
sentiment_i = finbert_score(article_text)  # [-1, +1]
relevance_i = relevance_score(article_text, ticker)  # [0, 1]
weight_i    = source_weight[source] × exp(-0.1 × age_hours)

# Step 2: Weighted aggregate (recent articles matter more)
current_score = Σ(sentiment_i × relevance_i × weight_i) / Σ(weight_i)

# Step 3: Z-score vs 30-day baseline
sentiment_z = (current_score − 30d_rolling_mean) / 30d_rolling_std

# Trading signals:
# sentiment_z > +2.0 → Strong bullish signal
# sentiment_z > +1.5 → Mild bullish
# -1.5 to +1.5      → Neutral
# sentiment_z < -1.5 → Mild bearish
# sentiment_z < -2.0 → Strong bearish signal
```

**Source weights (relative importance):**
```
SEC 8-K filing (earnings release): 1.5
Earnings call transcript: 1.3
WSJ / FT / Bloomberg article: 1.0
Reuters / AP: 0.9
Seeking Alpha (institutional author): 0.7
Analyst upgrade/downgrade note: 1.2
General blog / news aggregator: 0.3
```

---

## Real Trade Examples

### Win — META Earnings, October 2023

> **Date:** October 25, 2023 (earnings after close) | **META:** $303 (pre-earnings)

**Pre-announcement NLP (3pm, 7-day scan of 42 articles):**
- Baseline sentiment z-score: +0.8 (mildly positive)
- Key themes: "AI investments beginning to pay off," "ad recovery," "Reality Labs losses narrowing"
- No negative themes: no layoffs, no regulatory threats, no guidance concerns

**Post-announcement NLP run (5:30pm, within 30 minutes of earnings release):**
- Analyzed earnings press release + 8 immediate coverage articles
- Sentiment z-score: **+3.2** (extremely bullish — 3.2 standard deviations above baseline)
- Key phrases extracted: "revenue +23% YoY," "EPS $4.39 vs estimate $3.63 (+21% beat)," "2024 guidance raised," "Year of Efficiency delivering"
- Signal: Strong Buy (z > +2.0) ✓

**Execution at 5:35pm (after-hours):**
- Buy 200 shares META at $311.50
- Total investment: $62,300

**October 26 (next day):**
- META opened at $325 (+4.3% gap up)
- Post-open NLP: 28 additional articles processed; z-score maintained at +2.9 (sustained bullishness)
- META closed at $327.20

**Exit at close (October 26):**
- Sell 200 shares at $327.20
- P&L: ($327.20 − $311.50) × 200 = **+$3,140** in 24 hours

### Loss — SNAP, February 2023

> **Sentiment z-score:** +2.4 (bullish signal triggered on earnings) | **SNAP:** $11.20 after earnings gap up

NLP correctly extracted positive user growth metrics from the press release (+2.5% monthly active users, above estimates). Sentiment z-score: +2.4. Entry triggered.

However: the earnings call transcript (processed 45 minutes later) contained significantly negative guidance language — revenue per user declining, cost-per-impression under pressure. The transcript z-score fell to −0.8, but the trade was already entered.

SNAP gave back the +8% earnings gap over the next 3 days as institutional analysts processed the guidance weakness.

**P&L: −$890** on 500 shares entered at $11.20, exited at $9.42 (−$1.78/share).

**The lesson:** Always process the earnings CALL TRANSCRIPT in addition to the press release. The press release has the headline numbers; the transcript has the guidance narrative. A transcript processor running 45–90 minutes behind earnings can update the signal before you are fully committed.

---

## Entry Checklist

- [ ] Sentiment z-score crosses ±2.0 (strong signal threshold — not ±1.5)
- [ ] Signal driven by fundamental news (earnings, guidance, significant business development) — not just article volume
- [ ] Earnings call transcript processed and confirmed directionally consistent with press release
- [ ] Price is confirming the sentiment direction (stock moving in the direction of the signal)
- [ ] Source quality is adequate: signal dominated by high-weight sources (WSJ, SEC filings, Bloomberg), not low-weight blogs
- [ ] No conflicting signals: retail sentiment vs institutional analyst sentiment should agree
- [ ] Time of day: post-earnings signals in first 15–30 minutes of next trading day preferred; mid-day news signals during low-volume periods are less reliable

---

## Risk Management

**Max loss per trade:** Define maximum position size at entry. For post-earnings sentiment plays, limit to 3–5% of portfolio.

**Stop-loss rule:** If price moves more than 3% against the sentiment signal within the first 2 hours of entry, close the position. The sentiment signal may be correctly identifying tone while missing a structural issue (insider selling, index deletion) that is driving price.

**Update the signal continuously:** Re-run the NLP every 30 minutes during the active trading day. If the z-score reverses significantly (drops from +3.2 to +0.5) as more articles process, close the position — the consensus is revising.

**What to do when it goes wrong:** Close on the stop-loss. Investigate whether the NLP missed a key signal (guidance language, unusual negative phrasing) and use the failure to improve the model's weighting or the source priority.

---

## When to Avoid

1. **When price action contradicts sentiment.** A stock with z-score +2.5 that is falling in after-hours trading despite positive NLP has a signal the NLP cannot see: large institutional selling, fund outflow, or negative information not yet in public text. Price trumps sentiment.

2. **During macro risk events.** Strong positive META sentiment on an afternoon when CPI surprise causes broad market selloff is irrelevant — META will fall with the market regardless of its own news. Check macro calendar before acting on company-specific signals.

3. **For small-cap stocks with sparse coverage.** A company with 3 news articles per week cannot generate a statistically meaningful 30-day baseline. The z-score on sparse coverage is unreliable. Focus on large-caps with daily news volume.

4. **Without processing the earnings call transcript.** The press release announces numbers; the call explains trajectory and guidance. The 2023 META press release was positive; the 2023 SNAP press release looked positive until the call revealed guidance weakness. Always include transcript processing.

5. **When NLP models are trained on general text.** Standard BERT or GPT models not fine-tuned on financial text will misinterpret financial language. "Not a record" will be scored positive (contains "record"). Use FinBERT or Loughran-McDonald specifically.

---

## Strategy Parameters

```
Parameter              Conservative                            Standard       Aggressive
---------------------  --------------------------------------  -------------  -------------
Signal threshold       z > ±2.5                                z > ±2.0       z > ±1.5
NLP tier               LLM extraction (highest quality)        FinBERT        Lexicon-based
Source quality filter  High weight only (WSJ, SEC, Bloomberg)  Mix            All sources
Transcript required    Yes (mandatory before entry)            Yes            Preferred
Price confirmation     Required (same direction as signal)     Required       Preferred
Entry timing           Within 10 min of signal                 Within 30 min  Within 1 hour
Stop loss              −2% from entry                          −3%            −5%
Max position size      2% of portfolio                         4%             6%
```
