# Stage 5d Winner — first breach-free config over OOS + full continuous run

**Date:** 2026-07-03
**How found:** Stage 5c OOS screen was 0/20 (every trial breached the full
2015-2024 continuous window). Root-caused to uncapped correlated exposure
(15-19 same-group positions gapping together on flash/news days). Sweeping the
engine's `CORR_GROUP_CAP` lever (OFF for the whole 5c pool) at cap=3 across the
six "fail-only-full" trials → **4/6 now pass all 5 windows with zero breach.**
See `../../STAGE5C_BREACH_DIAGNOSIS.md`.

## Passing configs (cap=3), ranked by full-run net

| trial | full-run net | peak TDD | peak DDD | worst OOS window |
|------:|-------------:|---------:|---------:|------------------|
| **39**  | **$533,888** | **6.27** | **3.23** | 2018: TDD 4.98 DDD 4.05 |
| 104 | $471,295 | 8.61 | 4.40 | 2018: TDD 8.61 |
| 14  | $469,020 | 9.61 | 4.45 | 2023: TDD 9.61 |
| 217 | $232,510 | 7.70 | 4.21 | 2018: TDD 5.03 DDD 4.21 |

All four survive all 4 OOS starts (2018/2021/2023/2023-07) **and** the full
2015-2024 continuous run — through COVID, the 2019 JPY flash, and the 2022 gilt
crisis, the events that killed the whole cap-off pool.

## LOCKED WINNER — trial 39 @ CORR_GROUP_CAP=3

Chosen for the widest wall margin (TDD 6.27% / DDD 3.23% on the full run — both
comfortably under the 10% / 5% walls) with $534k net over 10 years, a robust
plateau rather than a spike (every window well inside the walls).

Env levers:
```
RISK_REGIME_ENABLE=1  VOL_SIZE_ENABLE=0  VOL_REGIME_DD_MULT=1.0
RISK_CALM_MULT=0.87   RISK_VOLATILE_MULT=0.71   VOL_REGIME_DD_OFF=5.0
CFG_MAX_CUM_RISK=5.0  CFG_DAILY_HALT_PCT=1.75
CFG_TDD_CAUTION_PCT=3.5  CFG_RISK_CAUTIOUS=0.65
CFG_TDD_WARNING_PCT=4.5  CFG_RISK_CONSERVATIVE=0.6
CFG_TDD_EMERGENCY_PCT=8.0 CFG_RISK_ULTRASAFE=0.4
TDD_WALL_SAFETY=4.0
CORR_GROUP_CAP=3          <-- the added lever
```
Entry/ladder = the Stage-5c PINNED_ENTRY + WINNER_LADDER (see
`src/stage5c_oos_screen.py`), `risk_per_trade_pct=1.0`. Base env from
`src/doe_harness.py::BASE_ENV` (FIVEERS_MAX_SCALE=400000, DDD_CLOSE_AT_TRIGGER=1,
GAP_FILLS=1, SLIPPAGE_PIPS=0.5, TERMINAL_ON_BREACH=1).

Reproduce:
```bash
uv run python3 backtest/src/diag_full_breach.py 39 --corr-cap 3
```

## Caveats / not-yet-done (before any live port)

The screen proves OOS + continuous survival. The full validation gauntlet
(ROADMAP §"Validation gauntlet") is NOT yet run on this winner:
- gap/slippage stress (`src/gap_stress.py`)
- worst-case intrabar TDD (`TDD_WORST_CASE=1`)
- Monte-Carlo trade-order shuffle (path dependence)
- parameter-perturbation robustness around cap=3 and the risk mults

Also: cap=3 is a *bolt-on* to a cap-off-tuned config. The joint
(cap + risk) optimizer `src/stage5d_corr_cap_optimize.py` can likely buy back
more net at equal safety by re-tuning risk for the capped regime — run it next.
