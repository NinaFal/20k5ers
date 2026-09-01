# Pre-mortem — it is 12 months on and this has gone badly. What happened?

Written before deployment, deliberately. The question is not "is the config
good" — the 200-start evidence says it is. The question is what the evidence
does **not** cover, because that is where the loss comes from.

Two things to state first.

**This is not established as the best configuration.** Three lines of enquiry
were opened and none finished:

| lead | what it showed | why it stopped |
|---|---|---|
| 5-leg TP ladder | never tested at all — `space_ladder` hardcoded `tp4_close_pct: 0.0, tp5_close_pct: 0.0`, so every stage of every round inherited a 3-leg assumption. The position is flat at 2.75R and nothing ever rides a trend further | stopped by request after 17 trials, ties unresolved |
| survival optimizer | 3 of 5 trials **halved** total failures vs the incumbent (5 vs 9 per 30) via mutually contradictory parameters | paused, 5 of 80 trials |
| risk 2.2% | 7 breaches → 2 on the hard sample, McNemar p=0.062 | confirmation cancelled midway |

None is proven better. But "we did not find better" is different from "better
does not exist", and here we mostly stopped looking rather than exhausted the
search.

**And the profit figure has no error bars.** 196 samples for the challenge; for
the funded decade, **one path per config**. The $4,294,756 is a single draw.
Nobody has run 100 random-start funded decades, so the spread around that number
is completely unknown. Treat it as an existence proof, not an expectation.

---

## Ranked by probability x cost

### 1. Trading costs eat the edge — HIGH probability
Every result assumed a **flat 1.0 pip spread** on every instrument, including
XAU, XAG, NAS100 and crypto, where real spreads are multiples of that. The
strategy took **12,054 trades** across the 11-year run — roughly 1,100 a year.
An average extra 1.5 pips on a third of those is a large, permanent drag that
compounds against every figure in this project.

Unmeasured. This is the single most likely reason live comes in below backtest,
and it is measurable *before* trading: re-run one holdout with per-instrument
spreads.

### 2. A seventh port bug — MODERATE-HIGH
Nine port steps produced **six** silent configuration bugs, every one found only
because a *new* checking method was tried: a shared config object that rewrote
the backtest, an attribute-name mismatch that would have disabled the
wall-guard, an unported halt leaving live with breach-causing behaviour, a halt
threshold reading 3.2 against 2.50, a lot cap of 100 against 50, and halt
tightening that no env-var scan could have found.

The base rate of "one more method finds one more bug" is 6 for 6. There is no
basis for believing the seventh does not exist. Only the demo period tests this.

### 3. A 5ers rule assumption is wrong — MODERATE, one is catastrophic
Four unanswered questions, all cheap to resolve:

- **Are withdrawals charged against the daily loss limit?** If yes, every payout
  day at the cap is an instant breach and the entire capped-year result — which
  is 10 of the 11 years — is void. This is the one that kills the thesis, not
  just the number.
- Fixed payout cadence: $672k / $1.2M / $22k depending on the reading.
- Per-asset leverage: margin at 69.4% during the climb assumes 1:100 on
  indices and metals. At 1:20 for indices the climb may be *at* the ceiling.
- Any aggregate exposure cap beyond 50 lots per position.

### 4. The recent regime is harder, and 2026 resembles it — MODERATE
All **9 breaches fell in 2019 or later**; zero in 37 pre-2019 starts in the
first holdout, and both breaches in the second sample were also 2019+. Two
independent samples agree.

The holdouts were out-of-sample in *start date* but not in *time period* — the
config was optimised across 2015-2025 and validated on 2015-2025. If the next
year behaves like 2019-2025 rather than the full decade, the realised breach
rate sits at the upper end of the 1.7-7.5% interval, or above it.

### 5. The climb is the risk and you get exactly one — HIGH cost
2015, the only climbing year: worst total drawdown **6.33%** against ~2% for
every capped year, and worst daily 4.09%. Risk per trade is 3.92% below $300k
against 0.87% at the cap; margin usage 69.4% against 12.6%.

Every breach in this project happened while climbing. You will do the
$50k -> $500k climb **once, live, with real money**, and the 4.6% figure does
not describe it — that is a per-*challenge* rate, a different and shorter
exposure.

### 6. Execution reality — MODERATE
The simulator models **no margin at all** (`csv_mt5_simulator.py:557-559`
hardcodes `margin: 0.0`, `margin_free: equity`) and no slippage beyond a fixed
spread. The nightly de-risk flattens the entire non-crypto book in one pass —
up to 20 positions at once — with no market-impact model anywhere.

### 7. No validated fallback — MODERATE
One config, frozen. If live results diverge in month two there is no B-option
that has been through the same validation, and re-running the pipeline takes
days. The survival candidates are the natural fallback and none is confirmed.

---

## What would change the odds most, cheapest first

1. **Email 5ers the four questions.** Free. One answer can void the thesis.
2. **Cost-realism run** — one holdout with per-instrument spreads. Quantifies
   the largest known unknown.
3. **Demo two weeks**, comparing fills against the backtest on the same dates.
   The only test that catches bug #7.
4. **Funded-decade distribution** — 20+ random-start funded runs to put error
   bars on the $4.29M.
5. **Finish the survival search**, so a validated fallback exists.

---

## The honest summary

A config validated at 95.4% pass / 4.6% account loss over 196 out-of-sample
attempts, ported with configuration verified end to end.

Its profit figure rests on a single path. Its cost model is optimistic by an
unmeasured margin. Its rule assumptions are unconfirmed and one of them is
load-bearing. Its port has produced six silent bugs and has not been behaviourally
tested. And the search for something better was stopped rather than completed.

None of that means don't trade it. It means the fee is the right amount to risk
first, and the demo period is not a formality.
