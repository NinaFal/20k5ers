# Phase 3 R&D plan — getting the 3%-wall challenge under 30 days

**Branch:** `claude/3pct-challenge-rd`. **Date:** 2026-07-21.
**Trigger:** if the current C2-wall3 ladder search finishes without producing
p30 > 0 (49/150 in, every trial so far at p30 = 0.00), the parameter space of
the *current* trading logic is exhausted: entry shape, entry gates, risk,
regime mults, ladder, and position caps have ALL been searched under the
correct 3% wall (~2,000 backtests) and the frontier is stuck at
**0% breach / ~52-day median**. Getting under 30 days then requires new
*mechanisms* in the engine, not more tuning of existing ones.

**Hard constraint:** high-frequency / lower-timeframe entry models are ruled
out (user instruction). Everything below keeps the existing HTF signal
engine and M15 execution — the phases add mechanisms *around* it.

**Why we believe speed is even possible:** +8% needs ~0.45%/day of realized
profit. The strategy takes ~1 trade/day at ~1R≈1% risk when configured
safely. So the gap is expectancy-per-day, and it can be attacked from four
independent directions: (1) risk more when it's provably safe to do so,
(2) make each winning setup earn more, (3) take the same trades on a better
subset of instruments, (4) stop the rare disaster days that force everything
else to stay small. One phase per direction, cheapest first.

---

## D0 — Retry economics + per-step configs (analysis only, ~zero compute)

Two reframings that need no engine work:

**D0a. Optimize expected-days-INCLUDING-retakes, not single-attempt safety.**
The 5%ers fee model means a breached attempt costs a re-take, not the account.
If a hotter config passes in ~30 days 55% of the time and breaches 30% of the
time, its *expected* time-to-funded (over retries) may beat the 0-breach
52-day config. We already have per-start day/breach distributions for every
config ever scored — this is a pandas exercise over existing JSON/CSVs:
`E[days] = Σ p(breach)^k · (days_lost_per_failed_attempt + days_to_pass)`.
Deliverable: a ranking by expected-days-to-funded and P(funded within 30/60/90
days) per config, including re-takes. May show the target is already
effectively met by accepting ~30% re-take odds.

**D0b. Per-step config split.** Step 1 (+8%) and Step 2 (+5%) are separate
fresh accounts with identical walls but different targets. The scorer already
runs them separately — test a hotter Step-2 config (its target is 37% closer)
and asymmetric Step-1/Step-2 pairs. Cheap: reuse `challenge_score.run_step`.

**Gate:** if D0a shows expected-days < 30-40 with acceptable re-take odds,
we may STOP here and pick that config. Otherwise proceed.

## D1 — Symbol-level expectancy audit (screen, ~1 day of compute)

Same strategy, better instrument subset. The universe is 39 symbols; nothing
has ever ranked them by *challenge-relevant* expectancy under the 3% config.
- Mine the trades.csv outputs already generated (thousands of trades) for
  per-symbol expectancy, win rate, MAE — identify structurally net-negative
  tickers (the `EXCLUDE_SYMBOLS` hook exists for exactly this; unused).
- Test: universe-minus-losers vs full universe on the 16 TRAIN starts.
- Crypto angle: BTC/ETH trade weekends (more banking days per calendar month)
  but M15 data starts 2020 — evaluate on 2021+ starts only.
**Mechanism:** dropping negative-expectancy symbols raises expectancy/day
without touching risk; every freed position slot goes to a better trade.

## D2 — Cushion-ratchet risk (small engine lever + Optuna) ← highest expected impact

Today risk only ever ratchets DOWN (TDD ladder). Nothing scales it UP when
the account has banked profit — yet banked cushion is exactly when higher
risk is provably safer:
- The 3% daily wall is computed from EOD max(equity, balance) — banked profit
  RAISES the wall's dollar floor every day.
- With +4% banked, even a full 3% down-day cannot end the attempt (total wall
  10% stays far away); the worst case is giving back cushion at a bounded rate.
Mechanism: a `CFG_CUSHION_LADDER` mirroring the TDD ladder in reverse —
e.g. banked ≥2% → risk ×1.5, ≥4% → ×2.0, ≥6% → ×2.5 (all Optuna-searched).
Expected effect: the slow grind to the first +2-3% stays safe, then the back
half of the target compounds much faster — directly attacks the 52-day median,
whose time is mostly spent in the late, already-safe stretch.
Engine work: one multiplier keyed to realized-profit-since-challenge-start in
the sizing path (same pattern as `_regime_risk_multiplier`). ~30 lines.

## D3 — Trend-quality risk controller (engine lever + Optuna)

Flagged in the ORIGINAL roadmap ("revisit ADX as a regime CONTROLLER in Stage
2") and never built. The C1 data shows passes cluster in trending windows and
breaches in chop. Mechanism: continuous risk multiplier from trend strength
(e.g. ADX or the existing HTF-trend agreement count): full risk when the
universe is trending, floor risk in chop. NOT a binary skip-gate (that was
proven harmful) — a sizing controller. Pairs naturally with D2: cushion says
*how much you can afford*, trend quality says *when it's worth spending*.

## D4 — Event-calendar throttle (data + small lever)

Every toxic start window traces to scheduled macro events (FOMC weeks, 2023-10
etc.). FOMC dates and NFP (first Friday) are known for the whole backtest
period — encode a static calendar; block new entries / tighten the halt within
±1 day of red-flag events. Mechanism: cuts the breach TAIL, which is what
forces base risk low; even if it adds ~0 speed directly, it lets D2/D3 run
hotter for the same breach rate.

## D5 — Pyramiding winners (engine work, leverage existing research)

The repo already contains `reentry_analysis.py` / `reentry_impact.py` from
earlier research — scale-in was studied but never wired into the challenge
path. Mechanism: add to a position at +0.5R with SL ratcheted so the combined
position risks only already-locked profit. Raises R-velocity per *setup*
without new signals or a lower timeframe — the compliant way to earn more per
trade. Largest engine change of the plan; do last, only if D0-D4 haven't
reached the target.

---

## Sequencing, gates, validation

| phase | type | cost | gate to next |
|---|---|---|---|
| D0 | analysis | hours | stop if expected-days < target with acceptable re-takes |
| D1 | screen | ~1 day | keep winners' universe for all later phases |
| D2 | lever + Optuna | ~2-3 days | expect the big jump here |
| D3 | lever + Optuna | ~2 days | combine with D2 winner |
| D4 | calendar + lever | ~1 day | combine; re-run breach-tail check |
| D5 | engine feature | ~3-4 days | only if still short of target |

Every phase is scored by the SAME `challenge_score.py` (3% wall, closed
balance, 3-profitable-days, p30-weighted score) on the 16 TRAIN starts, and
nothing is locked without the 16 HOLDOUT starts. Final combined winner gets
the full gauntlet (worst-case intrabar, slippage stress) before any live use.

**Decision point:** when the current C2-wall3 ladder run (150 trials)
completes. If p30 is still 0 → start D0 immediately (it's free), then D1/D2.
