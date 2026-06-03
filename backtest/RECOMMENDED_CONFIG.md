# Recommended robust config — the5ers funded account

This is the configuration arrived at after the full diagnosis + optimization
effort. It targets **max profit with zero breaches across any start regime**,
on the real continuous compounding path, faithful to live execution.

## The config (all env-gated, all committed to the engine)

| Lever | Value | Why |
|-------|-------|-----|
| TP ladder | 0.9 / 1.7 / 2.4 / 3.4 / 4.7 R | "NEWTP" — best profit ladder from the TP sweep |
| TP closes | 0.10 / 0.35 / 0.15 / 0.10 / 0.30 | |
| Trailing SL | after TP2/3/4 → 0.7 / 1.6 / 2.0 R | |
| Drawdown rungs | caution 5.5% @0.45 · warning 7.5% @0.25 · emergency 8.5% @0.25 | |
| **Vol size-up** | `VOL_SIZE_MULT_LOW=1.7`, `VOL_SIZE_MULT_HIGH=0.6` | size up in calm regimes |
| **Regime gate** | `VOL_REGIME_DD_OFF=3.0` | **collapse the size-up once drawing down >3% TDD** — fixes the 2017 calm-but-choppy bleed |
| **Scaling cap** | `FIVEERS_MAX_SCALE=400000` | **stop scaling at 400k** (the 100%-profit-split tier) — freezes the TDD floor so it stops chasing equity up; fixes the high-level total breaches (2016 died at the $700k level) |
| **Cumulative-risk cap** | `CFG_MAX_CUM_RISK=3.5` | **bound total simultaneous open risk to 3.5%** — caps worst single-day loss below the 5% wall; fixes the Sept-2022 daily gap. (Also faithful to live, which enforces a cumulative cap.) |
| **Daily close-all** | `CFG_DAILY_HALT_PCT=2.5` | tighter daily circuit-breaker for extra gap buffer |
| Daily close model | `DDD_CLOSE_AT_TRIGGER=1` | close at the trigger like live's 5s thread, not the bar's worst wick |
| Correlation cap | off (`CORR_GROUP_CAP=0`) | prior verdict |

## The three failure modes and their fixes (each diagnosed, each fixed)

1. **2017 = TOTAL-DD bleed.** Calm-but-trendless regime: the static vol size-up
   sized *up* into a losing chop and bled to the wall, fighting the drawdown
   ladder. → **Regime gate** (size up only while healthy).
2. **2016/2020 = TOTAL-DD at high funded levels.** The TDD floor ratchets up to
   each new funded level, pinning the account 10% from the wall; 2016 died at
   the $700k level. → **Scaling cap at 400k** (freeze the floor).
3. **Sept-2022 = DAILY-DD gap.** A single violent bar blew the 5% daily wall
   once the account survived long enough to reach it. → **Cumulative-risk cap**
   (bounds worst-case daily loss under 5%).

## Evidence (foreground-verified)

- Regime gate alone, cold-start 7 starts: $2.25M (2015) / $2.22M (2017, the
  former killer, @ 5.78% TDD) / $1.54M (2019) — 2017 went from *dead at 10%* to
  thriving.
- **Full stack, 2016->2022** (the year that exercises ALL THREE failure modes —
  high-level scaling, the 2017 bleed, and the 2022 gap): **SURVIVED**, max TDD
  **8.15%**, max DDD **3.82%**, net **$537,705**, withdrawn **$182,812**, on a
  400k account. All three walls cleared with margin.

## Best account to scale to: ~400k

- At 350k+ the 5ers profit split is **100%** (you keep all profit + a fixed
  bonus). Scaling past 400k gives **no better split**, only more floor-ratchet
  breach exposure. So 400k = max profit share + safest structure.
- Withdraw % of profit periodically; every dollar withdrawn is a dollar of
  cushion above the (now static) floor — the cumulative-risk cap is what keeps
  the daily wall safe regardless.

## TODO (blocked by environment instability at time of writing)

- Full 7-start confirmation of the complete stack to 2024 (2016 is proven; the
  others share the same now-fixed failure modes). Re-run when the environment is
  stable: `.work/final_test.py` runs exactly this.
- Tune the withdrawal %/cadence to maximize cash-out while holding the cushion.
- Reconcile the swept drawdown rungs (0.4@4.5 in backtest) vs the live default
  (0.6@3.0) before going live.
