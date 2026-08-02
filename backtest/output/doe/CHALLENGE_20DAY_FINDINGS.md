# Can the full 2-step challenge pass in ≤20 days? (closed balance)

**Date:** 2026-07-20. **Requirement:** pass Step 1 (+8%) → reset → Step 2 (+5%)
in ≤20 calendar days total, no breach. Target measured on **closed balance**
(confirmed by user), walls on equity. Fresh $100k, t49 regime skeleton, CHF on.

## Answer: not a reliable target — ~19% of starts, and it's throughput-limited

The blocker is NOT breaches and NOT (mostly) the TP ladder — it's **trade
throughput**: this is a selective HTF-confluence strategy that takes few setups,
so it often can't bank +8% of *closed* profit fast enough, in one or both step
windows.

### Full 2-step ≤20-day pass rate (16 starts each)

| ladder | risk 2.5% | risk 3.5% | risk 4.5% |
|--------|:---------:|:---------:|:---------:|
| runner (funded ladder) | 0/16 | 0/16 | 0/16 |
| **bank_fast** (close ~80% by 1.0R) | 0/16 | **3/16 (19%)** | 3/16 |
| bank_med | 0/16 | 1/16 | 2/16 |

- **The runner ladder never passes** — it holds runners, so realized +8% comes
  too late. A challenge-only **fast-banking** ladder is necessary.
- **Fast banking + ~3.5% risk is the best**: 3/16 pass, fastest **9 and 11 days**.
  Above that, risk 4.5% adds no passes (just slower/uglier tails).

### Why only 19% — bank_fast @ 3.5%, per start

```
PASS  2019-07 total  9d (d1=2, d2=6)
PASS  2022-01 total 11d (d1=4, d2=6)
PASS  2021-07 total 20d (d1=6, d2=13)
slow  2016-07 total 21d   2021-01 total 26d
step2 2016-01, 2018-07, 2019-01, 2024-07  (Step 1 fast, Step 2 stalled)
step1 2017-01, 2017-07, 2018-01, 2022-07, 2023-01, 2023-07, 2024-01  (no +8% in 25d)
```

Two failure modes, both throughput:
1. **7/16 can't bank +8% in Step 1** within 25 days.
2. **4/16 pass Step 1 fast (1–6 days) but Step 2 stalls** — the next window didn't
   offer enough setups to bank +5%.

You need favorable (trending) conditions in **both** consecutive step windows;
that lines up ~1 in 5 starts.

## Recommendation / options

**Best config for the attempt (challenge phase only):**
`bank_fast` ladder + **base risk ~3.5%**, t49 regime skeleton, cap 3, CHF on —
then switch to the runner ladder once funded. Strictly beats the runner ladder
for challenge speed (3/16 vs 0/16), fastest passes 9–11 days.

`bank_fast` = tp 0.5/1.0/1.5R, close 45%/35%/20% (100% closed by 1.5R),
sl_after 0.5/1.2/1.8.

**But 20 days can't be *guaranteed* with this strategy.** Three ways forward:
1. **Accept it as best-case (~19%)** — run the challenge with the config above and
   simply re-take until a favorable start (or start when the trend is clearly on).
2. **Raise trade throughput** (the only lever that can break the ceiling) — loosen
   the entry gates *for the challenge phase* so more setups fire and +8% banks
   faster. This trades against entry quality (the Stage-1/2 edge), so it must be
   tested for breach-rate. I can prototype + measure this.
3. **Relax the deadline** to what's reliably achievable (median ~30–40 days at
   safe risk, per CHALLENGE_FINDINGS.md), if 20 days isn't a hard firm rule.

Reproduce: `LADDER_RISK=3.5 uv run python3 backtest/src/challenge_ladder_test.py`

---

## Option 2 tested and CLOSED — entry throughput can't be increased

Hypothesis: loosen the challenge-phase entry gates (confluence / quality / ATR
percentile) so more setups fire and +8% banks faster. **Result: it does nothing.**

Throughput sweep (bank_fast, risk 3.5%, 16 starts), 4 entry-looseness levels:

| entry gates (trend/range/quality) | avg trades (Step 1) | pass ≤20 |
|-----------------------------------|:-------------------:|:--------:|
| 6/3/3 (baseline) | 27.1 | 3/16 |
| 5/3/2 | 27.1 | 3/16 |
| 4/2/2 | 27.1 | 3/16 |
| 3/2/1 | 27.1 | 3/16 |

Identical trade counts. Direct engine probe on a fixed window confirms the gates
are **non-binding in the operating range**:
- `trend_min_confluence` 3 / 6 / 15 → all **46 trades**; only at **25** does it drop to 0.
  The natural confluence scores sit ~15–24, so any threshold ≤15 admits every setup.
- `atr_min_percentile` 41 / 0 → **46 / 46** (no change).

So the strategy already takes **every setup it detects (~1 trade/day)**. The
20-day ceiling is **not** a trade-frequency problem — it's the rate at which this
selective strategy's setups *net +8% closed* (win-rate × R per unit time), which
no entry-gate change affects. Raising throughput would require a different, lower-
timeframe entry model — a new strategy, out of scope here.

## Final recommendation

**20 days for the full 2-step cannot be guaranteed with this strategy (~19%
best-case).** Two honest paths:
1. **Run it as best-case:** `bank_fast` ladder + ~3.5% risk during the challenge
   (fastest passes 9–11 days), start when a trend is clearly underway, and be
   prepared to re-take — it lands ≤20 days ~1 in 5 attempts.
2. **Relax the deadline** to ~30–40 day median (reliable at safe 1.0–1.5% risk,
   per CHALLENGE_FINDINGS.md), which the strategy hits comfortably without breaching.
