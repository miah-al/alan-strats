## News Sentiment NLP Strategy

**In plain English:** Process thousands of news headlines, earnings call transcripts, and analyst reports using natural language processing to extract sentiment scores. Aggregate those scores into bullish/bearish signals for individual stocks or the market as a whole. Stocks with rapidly improving news sentiment tend to outperform; those with deteriorating sentiment underperform. The edge: NLP processes text faster and more consistently than any human analyst.

---

### How NLP Extracts Sentiment

**Three levels of sentiment analysis:**

1. **Lexicon-based (simplest):** Pre-built dictionaries of "positive" and "negative" financial words.
   - "Record revenue" → +1, "misses expectations" → −2, "guidance raised" → +3, "layoffs" → −2
   - Loughran-McDonald financial dictionary: 350 positive, 2,345 negative financial terms
   - Fast but misses context: "not a record" gives false positive from "record"

2. **Pre-trained BERT models (better):** Models fine-tuned on financial text that understand context.
   - FinBERT (HuggingFace): trained on 1.8M financial news articles
   - Understands "margins under pressure" as negative even without explicit negative words
   - Understands "beat estimates" vs "beat estimates but guidance disappoints"

3. **LLM-based extraction (best quality, highest cost):** Use Claude/GPT-4 to extract structured sentiment from each article.
   - Prompt: "Rate the sentiment of this earnings summary for NVDA from −5 to +5, with explanation"
   - Most accurate but expensive at scale ($0.01–0.10 per article)
   - Use for highest-priority articles (major earnings, analyst upgrades/downgrades)

---

### Signal Construction

**Step 1: Article scoring**
For each article, compute:
- `sentiment_score` ∈ [−5, +5]
- `relevance_score` ∈ [0, 1] (how relevant to the stock's fundamentals)
- `source_weight` (WSJ = 1.0, SEC filing = 1.5, random blog = 0.3)

**Step 2: Time-weighted aggregate**
```python
# More recent articles weighted higher (exponential decay)
weighted_score = Σ(score_i × relevance_i × source_weight_i × exp(−λ × age_hours_i))
# λ = 0.1 → half-life of ~7 hours for news freshness
```

**Step 3: Baseline comparison**
Compare current score to 30-day rolling average → z-score
```
sentiment_z = (current_score − 30d_avg) / 30d_std
```

**Trading signal:**
- sentiment_z > +2.0 → Strong buy signal
- sentiment_z > +1.5 → Mild buy
- −1.5 to +1.5 → Neutral
- sentiment_z < −1.5 → Mild sell
- sentiment_z < −2.0 → Strong sell / short

---

### Real Trade Walkthrough

> **Date:** October 25, 2023. META reports Q3 earnings after close.

**Pre-announcement NLP run (3pm):**
- Run FinBERT on last 7 days of META news (42 articles)
- Average 7-day sentiment z-score: +0.8 (mildly positive)
- Key themes detected: "AI investments paying off," "ad revenue recovery," "Reality Labs losses narrowing"
- No major negative keywords: no "layoffs," "miss," "guidance cut"

**Post-announcement NLP run (5:30pm — within 30 minutes of earnings release):**
- Analyze earnings press release + initial coverage (8 articles)
- Sentiment z-score: **+3.2** (extremely bullish)
- Key phrases: "revenue beat +23% YoY," "EPS beat," "2024 guidance raised," "Year of Efficiency paying off"
- Revenue $34.1B vs expected $33.6B; EPS $4.39 vs expected $3.63

**Signal: Strong Buy (z > +2.0)**

**Execution (5:35pm in after-hours):**
- Buy 200 shares META at $311.50
- Or: Buy Nov 3 $310 calls at $7.20 × 5 = $3,600

**Next day (October 26):**
- META opens at $325 (pre-market gap up +4.3%)
- Ongoing NLP coverage continues positive: 28 additional upgrade articles processed
- Mid-day sentiment z-score: +2.9 (sustained)
- META closes at $327.20

**Exit at close:**
- Shares: $327.20 − $311.50 = +$15.70 × 200 = **+$3,140**
- Calls: worth $17.20 at close → sell for +$10.00 × 5 × 100 = **+$5,000**

---

### Data Sources and Pipeline

**Tier 1 (fast, for intraday signals):**
- Benzinga Pro API: earnings headlines within 2 minutes of release
- Twitter/X API: trending $TICKER mentions with sentiment
- SEC EDGAR: 8-K filings (earnings, material events) — 15-minute delay

**Tier 2 (comprehensive, for overnight processing):**
- Financial Times API / Reuters API
- Earnings call transcripts (Seeking Alpha API)
- Analyst report summaries (Bloomberg if available)

**Processing time requirements:**
- Post-earnings articles must be processed in < 10 minutes for actionable signals
- Analyst upgrades/downgrades: < 5 minutes (these are time-sensitive)
- General news: can be batch-processed nightly for next-day signals

---

### Entry Checklist

- [ ] Sentiment z-score crosses ±2.0 (strong signal threshold)
- [ ] Signal is driven by fundamental news (earnings, guidance) not just volume of articles
- [ ] Confirm sentiment agrees with price action (avoid buying strong negative momentum even with positive sentiment — something you don't know may be driving price)
- [ ] No conflicting signals: check analyst consensus sentiment vs retail sentiment
- [ ] Time of day: post-earnings signals in first 30 minutes of next trading day are best; mid-day news signals during low-volume periods are less reliable

---

### Common Mistakes

1. **Sentiment without price confirmation.** A stock can have very positive sentiment and still fall if there are large sellers (insider selling, index deletion). Always require price to be trending in the direction of sentiment before entering.

2. **Not handling sarcasm and negation.** Simple lexicon models count "not bad" as negative (contains "bad") and miss sarcasm entirely. Use FinBERT minimum — simple word counting is not enough for financial text.

3. **Survivorship bias in training.** If you build a sentiment model using only news from companies that still exist, you've excluded all the companies that got destroyed by bad news (they no longer exist in the data). This makes the model appear more accurate than it is.

4. **Ignoring the "expectation vs actual" framing.** In financial news, a 10% revenue growth number is positive if analysts expected 5% and negative if they expected 15%. Pure sentiment (the words used) must be interpreted in the context of consensus expectations. The most important sentence in an earnings release is often "EPS of $X vs estimate of $Y."
