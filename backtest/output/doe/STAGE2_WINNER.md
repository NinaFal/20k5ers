# Stage 2 — Sizing / Risk Optimization: WINNER

**Date locked:** 2026-06-11
**Method:** Optuna TPE, 100 trials/entry, 5 evaluation windows (~2yr each), maximin objective
**Objective:** `maximin(net across 5 windows) − MARGIN_K·max(0, worst_tdd − 8%)²`; breach → −1e9
**Anchor:** BASE_RISK_PCT = 1.1% (Stage 1 lock)

---

## WINNER: Entry A, trial 25

Dominates on **both** axes — higher profit *and* lower drawdown than Entry B's best.

| Metric            | **A-t25 (WINNER)** | B-t25 (runner-up) |
|-------------------|--------------------|-------------------|
| Objective         | **+$49,069**       | +$35,814          |
| Maximin (worst window) | **$49,069**   | $35,814           |
| Avg net (5 win)   | **$107,836**       | $68,682           |
| Worst-case TDD    | **6.67%**          | 7.83%             |
| Margin to 10% wall| **3.33%**          | 2.17%             |

### Entry A window breakdown (net P&L per ~2yr window)
| w0 | w1 | w2 | w3 (worst) | w4 |
|----|----|----|-----------|----|
| $106,612 | $137,062 | $100,608 | **$49,069** | $145,831 |

Worst single ~2-year window still returns **~98% on $50K** with TDD peaking at 6.67% — comfortably inside the 10% wall.

---

## Locked parameters (Entry A, trial 25)

| Parameter              | Value  |
|------------------------|--------|
| RISK_CALM_MULT         | 1.15   |
| RISK_VOLATILE_MULT     | 0.55   |
| VOL_REGIME_DD_OFF      | 2.5    |
| CFG_MAX_CUM_RISK       | 4.0    |
| CFG_DAILY_HALT_PCT     | 2.0    |
| CFG_TDD_CAUTION_PCT    | 4.0    |
| CFG_TDD_WARNING_PCT    | 5.5    |
| CFG_TDD_EMERGENCY_PCT  | 8.0    |
| CFG_RISK_CAUTIOUS      | 0.30   |
| CFG_RISK_CONSERVATIVE  | 0.25   |
| CFG_RISK_ULTRASAFE     | 0.15   |
| TDD_WALL_SAFETY        | 5.0    |

**Regime logic:** More risk in calm regimes (1.15× base) to harvest favorable
conditions; sharply less in volatile regimes (0.55× base) to protect against
drawdown clusters. Vol multiplier is a razor-thin sweet spot — 0.60× breached
all windows in tuning, 0.50× lost the worst window.

---

## Runner-up: Entry B, trial 25 (retained as documented alternative)

calm=0.85 / vol=1.65 — opposite regime profile (B's signal favors volatile
participation). Best of 100 trials, 65 surviving. Safe (7.83% TDD) but
materially lower profit. Not selected; kept for potential Stage 4 joint study.

| Parameter | Value | | Parameter | Value |
|-----------|-------|-|-----------|-------|
| RISK_CALM_MULT | 0.85 | | CFG_TDD_WARNING_PCT | 7.0 |
| RISK_VOLATILE_MULT | 1.65 | | CFG_TDD_EMERGENCY_PCT | 8.0 |
| VOL_REGIME_DD_OFF | 3.5 | | CFG_RISK_CAUTIOUS | 0.30 |
| CFG_MAX_CUM_RISK | 4.5 | | CFG_RISK_CONSERVATIVE | 0.20 |
| CFG_DAILY_HALT_PCT | 3.25 | | CFG_RISK_ULTRASAFE | 0.15 |
| CFG_TDD_CAUTION_PCT | 4.5 | | TDD_WALL_SAFETY | 2.0 |

---

## Next: Stage 3 — TP ladder optimization

Optimize take-profit ladder on the locked Stage 1 + Stage 2 (A-t25) config,
same maximin / no-breach objective, same watchdog + CSV-checkpoint + resumable
SQLite infrastructure.
