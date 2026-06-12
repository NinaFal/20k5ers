# Stage 3 — TP-Ladder Winner (LOCKED)

**Date**: 2026-06-12  
**Study**: `stage3_tp` (SQLite: stage3.db)  
**Trials**: 50 COMPLETE (73 sampled — PRUNED excluded from CSV)  
**Surviving**: 20 / 50 (non-breach across all 5 windows)  
**Winner**: trial 68

---

## Locked TP Configuration (Stage 3)

| Parameter | Value |
|-----------|-------|
| tp1_r_multiple | 0.7 R |
| tp2_r_multiple | 1.6 R |
| tp3_r_multiple | 2.7 R |
| tp4_r_multiple | 3.4 R |
| tp5_r_multiple | 5.5 R |
| tp1_close_pct | 15% |
| tp2_close_pct | 20% |
| tp3_close_pct | 15% |
| tp4_close_pct | 5% |
| tp5_close_pct | 45% |
| sl_after_tp2_r | 0.60 R (move SL to 0.60R profit after TP2 hit) |
| sl_after_tp3_r | 1.50 R (move SL to 1.50R profit after TP3 hit) |
| sl_after_tp4_r | 1.90 R (move SL to 1.90R profit after TP4 hit) |

---

## Fully Locked Config (Stage 1 + 2 + 3)

Env vars (Stage 2 sizing):
```
RISK_REGIME_ENABLE=1
VOL_SIZE_ENABLE=0
VOL_REGIME_DD_MULT=1.0
RISK_CALM_MULT=1.15
RISK_VOLATILE_MULT=0.55
VOL_REGIME_DD_OFF=2.5
CFG_MAX_CUM_RISK=4.0
CFG_DAILY_HALT_PCT=2.0
CFG_TDD_CAUTION_PCT=4.0
CFG_TDD_WARNING_PCT=5.5
CFG_TDD_EMERGENCY_PCT=8.0
CFG_RISK_CAUTIOUS=0.30
CFG_RISK_CONSERVATIVE=0.25
CFG_RISK_ULTRASAFE=0.15
TDD_WALL_SAFETY=5.0
```

OPT_PARAMS JSON (Stage 1 entry + Stage 3 TP):
```json
{
  "risk_per_trade_pct": 1.1,
  "entry_type": "A",
  "tp1_r_multiple": 0.7,
  "tp2_r_multiple": 1.6,
  "tp3_r_multiple": 2.7,
  "tp4_r_multiple": 3.4,
  "tp5_r_multiple": 5.5,
  "tp1_close_pct": 0.15,
  "tp2_close_pct": 0.20,
  "tp3_close_pct": 0.15,
  "tp4_close_pct": 0.05,
  "tp5_close_pct": 0.45,
  "sl_after_tp2_r": 0.60,
  "sl_after_tp3_r": 1.50,
  "sl_after_tp4_r": 1.90
}
```

---

## Performance (5 Evaluation Windows)

| Window | Net P&L |
|--------|---------|
| 2022–2024 | +$50,735 |
| 2016–2018 | +$66,065 |
| 2020–2022 | +$65,249 |
| 2017–2019 | +$110,759 |
| 2019Jul–2022Jun | +$109,599 |
| **Maximin (worst)** | **+$50,735** |
| **Average net** | **+$80,481** |
| **Worst TDD** | **6.82%** (wall = 10%) |

**Objective**: +$50,735 (maximin, penalty-free — worst_tdd 6.82% < 8% wall margin)

---

## Leaderboard (Top 5 Surviving Trials)

| Rank | Trial | Obj | Maximin | Avg Net | Worst TDD | Notes |
|------|-------|-----|---------|---------|-----------|-------|
| 1 | **t68** | **+$50,735** | **+$50,735** | **+$80,481** | **6.82%** | **WINNER** |
| 2 | t8 | +$49,069 | +$49,069 | +$107,836 | 6.67% | BASE_TP seed |
| 3 | t55 | +$40,461 | +$40,461 | +$90,874 | 7.43% | |
| 4 | t70 | +$31,468 | +$33,150 | +$88,902 | 8.29% | |
| 5 | t48 | +$25,591 | +$25,591 | +$72,022 | 7.33% | |

---

## Notes

- t8 (BASE_TP seed) is the runner-up with lower maximin (+$49,069) but better avg_net (+$107,836) and lower TDD (6.67%). The winner t68 beats it by +$1,666 on the worst-case window.
- 60% of trials breached (30/50) — confirms the constraint is tight; the TPE search converged around the 0.7R first-TP / wide-final-TP family.
- Stage 4 next: joint Pareto search or walk-forward OOS validation gauntlet.
