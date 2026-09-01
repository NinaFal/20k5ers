# D0 + D1 findings (WALL3_RD_PLAN.md phases)

**Date:** 2026-07-21. Branch `claude/3pct-challenge-rd`.

## D0a — Retry economics: does NOT rescue the target (closed)

Monte-Carlo over the empirical per-start outcome distributions of all 40
C1-wall3 configs (`src/d0_retry_economics.py`), modeling re-takes (breach →
lose ~10-25 days + restart, try again, up to 10 attempts):

- Primary grid (60d/step horizon): **P(funded ≤45d) ≈ 0.00 for every config**;
  best P(≤90d) only ~0.13.
- Hotter 40d grid (lower bounds): best P(≤30d) ≈ 0.09, P(≤45d) ≈ 0.16
  (c0.65_v0.65_t1.15 @ risk 1.5, 6/16 breach).

**Why re-takes don't help here:** the dominant failure mode is NOT breach —
it's the slow grind (attempt neither passes nor breaches, it just drags).
A grinding attempt never grants a re-take; you're simply stuck in it. Retry
economics only pays when outcomes are binary-fast (pass fast or breach fast).
**Design implication for D2/D3:** the goal is not just "safer" but
"faster-resolving" — compress time-in-attempt.

D0b (per-step config split) deferred: the data shows Step 1 is the blocker
(most failures are step1-frozen), so a hotter Step-2 config can't move the
headline number. Revisit only if a fast Step-1 config emerges.

## D1 — Symbol expectancy audit (~32k trades from 9 long-run backtests)

Per-symbol expectancy across all persistent diag trades.csv (2015-2024 runs):

**Net-negative symbols (candidates for EXCLUDE_SYMBOLS):**

| symbol | trades | total PnL | avg $/trade | win% |
|---|---:|---:|---:|---:|
| AUD_NZD | 1,197 | **−$65,484** | −54.71 | 62% |
| EUR_NZD | 520 | −$15,911 | −30.60 | 65% |
| AUD_JPY | 1,235 | −$8,842 | −7.16 | 60% |

AUD_NZD is a major structural bleeder. Everything else is net-positive; top
earners: USD_JPY (+$182k), USD_CAD (+$141k), EUR_CHF (+$82k), EUR_AUD (+$77k).
Caveat: measured under funded-phase runner-ladder configs — relative ranking
should transfer to the challenge config, but re-verify at D1-full.

**Bigger discovery — 10 of 39 universe symbols NEVER trade:** XAU_USD,
XAG_USD, NAS100_USD, UK100_USD, SPX500_USD, BTC_USD, ETH_USD, XRP_USD,
ADA_USD (and NZD_JPY) produce **zero trades** in every long run examined.
The strategy is forex-only in practice. Data files exist for ALL their
timeframes (M15/H4/D1/W1/MN), so this is a **pipeline bug, not missing
data** — most likely the HTF-file symbol-name translation (files are named
`XAUUSD_D1_...` while the runtime symbol is `XAU_USD`), silently yielding no
HTF trend → no confluence → no setups. **Fixing this could be a large free
throughput unlock** (gold trends exceptionally well; crypto adds weekend
banking days). → D1-full work item #1.

## D2 — Cushion-ratchet lever: IMPLEMENTED (engine), search pending

New env-gated sizing multiplier in `main_live_bot_backtest.py` (after the
regime-risk block): when realized profit since challenge start exceeds
CUSHION_T1/T2/T3 (%), risk is multiplied by CUSHION_M1/M2/M3 — the reverse of
the TDD ladder, exploiting the fact that banked profit raises the 3% wall's
EOD floor. Gated off whenever daily loss or total DD exceeds CUSHION_DD_OFF
(default 1.0%) so it never fights the safety ladders. Default OFF —
`CUSHION_RATCHET_ENABLE=1` to activate.

Smoke-tested: off = behavior unchanged; on (aggressive test thresholds) =
sizing visibly changes (in the test window it *hurt* — thresholds/mults need
the Optuna search, queued behind the running C2-wall3 ladder study).

## Next actions (in order)

1. **D1-full #1: debug the zero-trade symbols** (HTF name-translation) — a
   potentially large, free throughput unlock; do BEFORE the D2 search so the
   search benefits from the wider universe.
2. D1-full #2: re-screen with `EXCLUDE_SYMBOLS=AUD_NZD,EUR_NZD,AUD_JPY`.
3. D2 Optuna: cushion thresholds/mults × risk × caps (after ladder study
   completes / absorbing its conclusion).
