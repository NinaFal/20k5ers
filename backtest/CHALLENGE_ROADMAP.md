# 100k 2-Step Challenge — Optimization Roadmap (plan of record)

**Goal:** pass the 5%ers High-Stakes 2-step challenge on a **$100k** account —
Step 1 **+8%**, then Step 2 **+5%** — as fast as possible with breach risk ≈ 0.
This REPLACES the funded-profit objective of `OPTIMIZATION_ROADMAP.md` for the
current program. The funded-phase winner (t39 @ cap=3, runner ladder) stays
locked for AFTER the challenge; nothing here touches it.

## The objective (per config, across many start dates)

A start "passes a step" when ALL of (closed-balance target hit, ≥3 profitable
days of ≥0.5%, no 5% daily / 10% total equity breach before it). Step 2 begins
fresh the day after Step 1 passes.

```
score = 3·P(full pass ≤20d) + 1·P(full pass ≤40d) − 10·P(breach) − median_total_days/100
```
- ≤20 days is the stretch goal (~19% with hand-tuned settings — the bar to beat);
- ≤40 days is the reliability band; breaches are near-vetoed.

**Anti-overfit protocol:** every stage optimizes on the TRAIN starts
(2016/2018/2021/2023 × Jan,Apr,Jul,Oct — includes the toxic Apr/Oct windows) and
is validated on the HOLDOUT starts (2017/2019/2022/2024 × same months) that no
stage ever optimizes against. Black swans (2015 CHF, 2020 COVID) excluded.

Scorer: `src/challenge_score.py` (single source of truth for the rules).

## Stages (each locks its winner into the next)

| stage | what is searched | held fixed | status |
|-------|------------------|------------|--------|
| **C0** | build the scorer (targets on closed balance, 3-profitable-days rule, sequential steps, train/holdout splits) | — | ✅ done |
| **C1** | **entry shape**: entry_fib_level (calm), entry_fib_level_volatile, fib_vol_ratio_threshold — the params that set win-rate × R per unit time, which is the binding constraint (entry *gates* proved non-binding) | bank_fast ladder, risk 3.5%, t49 regime skeleton, cap 3, CHF on | 🔄 running |
| **C2** | **ladder**: TP levels + close % + trail (Optuna) — optimize fast-banking properly instead of the hand-made bank_fast | C1 winner entry | pending |
| **C3** | **risk & regime**: base risk, calm/vol (and 3-way) mults, regime-off, corr cap, daily halt, TDD ladder (Optuna; reuse challenge_optimize re-pointed at the full-2-step score) | C1+C2 winners | pending |
| **C4** | joint refinement of the top-K from C1-C3 + parameter perturbation (plateau check) | — | pending |
| **C5** | final validation: all 32 holdout+train starts, both steps, worst-case breach detection (TDD_WORST_CASE=1), slippage stress; lock **CHALLENGE_WINNER.md** with exact live env | — | pending |

## Fixed context

- $100k, targets $8,000 then $5,000 closed; walls 5% daily / 10% total (equity).
- ≥3 profitable days (≥$500/day realized) per step.
- CHF pairs ON (the 2015 swan is outside all test windows; CHF adds throughput).
- Funded-phase config after passing = STAGE5D_WINNER.md (runner ladder, cap 3).

## Prior findings this plan builds on (don't re-learn)

1. Runner ladder can NEVER pass fast on closed balance (0/16 ≤20d) — fast-banking
   ladder is mandatory for the challenge phase (CHALLENGE_20DAY_FINDINGS.md).
2. Entry GATES (confluence/quality/ATR-percentile) are non-binding — the strategy
   already takes every setup it detects (~1/day). Throughput can't be raised by
   loosening them; speed must come from entry SHAPE, ladder, and risk.
3. Breaches cluster in toxic Apr/Oct start windows → they are IN the train set.
4. Regime-adaptive sizing (calm↑/vol↓) was the optimizer's favorite lever; 3-way
   split is wired (RISK_REGIME_3WAY) and goes into C3's space.
