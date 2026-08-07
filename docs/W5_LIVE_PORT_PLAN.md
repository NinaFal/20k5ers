# Live-bot port plan — moving the validated config out of the backtest

**Status: analysis complete, nothing ported yet.**

Every number produced in this round came from `main_live_bot_backtest.py` driven
by environment variables. **29 of those variables are read by the backtest and by
nothing in `main_live_bot.py`.** Five of them switch on behaviour the live bot
does not implement at all. Until that is closed, starting a challenge means
trading a different system from the one that was tested, and none of the
evidence transfers.

Source of truth for the target config:
`backtest/output/doe/wall5/BASELINE_t65_tdd_FROZEN.json`.

---

## A. Features absent from the live bot that are ACTIVE in the winner

These need code, not configuration.

### A1. Nightly de-risk — the big one
`_nightly` appears 4 times in the backtest, **0 times** in `main_live_bot.py`.

The winner runs it every night at 22:00 UTC with `NIGHTLY_MAX_PER_GROUP=0` and
`NIGHTLY_MAX_TOTAL=0` — hold **zero** non-crypto positions overnight, close
anything below 0.25R, reduce the rest by 75%. This removes overnight gap
exposure entirely and is very likely a large part of why drawdown is controlled.

The machinery already exists live: both files import `weekend_gap_manager` and
call `select_positions_for_weekend_tier1`. Live only invokes it before the
weekend. **Port the caller** at `main_live_bot_backtest.py:1924-2010` and its
invocation at line 6004 (live equivalent: near `handle_weekend_gap_positions()`
at line 6309).

Env: `NIGHTLY_DERISK=1`, `NIGHTLY_DERISK_HOUR=22`, `NIGHTLY_MAX_PER_GROUP=0`,
`NIGHTLY_MAX_TOTAL=0`, `NIGHTLY_R_CLOSE_LOSING=0.25`, `NIGHTLY_R_NEW=0.5`,
`NIGHTLY_REDUCE_PCT=0.75`.

### A2. Correlation group cap
`CORR_GROUP_CAP=6` — 8 references in the backtest, **0** live. Live has
correlation logic only inside the weekend gap manager, not as an entry-time cap.

### A3. Symbol exclusions
`EXCLUDE_SYMBOLS=AUD_NZD,EUR_NZD,AUD_JPY` — 5 references in the backtest, **0**
live. Simple filter, but it changes which trades are taken.

### A4. Risk regime multiplier
`RISK_REGIME_ENABLE=1`, `RISK_CALM_MULT=1.45`, `RISK_VOLATILE_MULT=1.0` — **0**
live. Note what this does: in calm regimes it sizes positions **45% larger**.
That is not a safety feature, it is a return driver, and omitting it would make
live materially more conservative than tested. Must be ported deliberately, not
by accident.

### A5. Cumulative risk cap — re-enable
`main_live_bot.py:5001` reads:
```python
# NOTE: NO cumulative risk check - removed to match simulator
# Simulator has no cumulative risk limits, only position count limit
```
That comment is **false today**. The backtest enforces a cap at
`main_live_bot_backtest.py:3557` and the winner sets `CFG_MAX_CUM_RISK=7.0`.
Live does pass `max_cumulative_risk_pct` into `ChallengeRiskManager` (line 2941,
default 5.0), so a cap may exist on another path — establish which before
changing anything, then wire 7.0 through the entry path.

---

## B. Features present live with wrong values — transcription only

### B1. `ftmo_config.py`

| field | live now | required |
|---|---|---|
| `risk_per_trade_pct` | 0.6 | **2.7** |
| `daily_loss_halt_pct` | 3.2 | **2.50** |
| `max_cumulative_risk_pct` | 5.0 | **7.0** |
| `max_risk_conservative_pct` | 0.4 | **0.25** |
| `max_concurrent_trades` | 100 | **20** |

### B2. `params/current_params.json` — 15 parameters

`risk_per_trade_pct` 2.7; `tp1_r/close` 0.65/0.25; `tp2_r/close` 1.85/0.60;
`tp3_r/close` 2.75/0.15; `sl_after_tp1_r` −0.10; `sl_after_tp2_r` 0.90;
`sl_after_tp3_r` 1.70; all six entry filters `False`.

### B3. TDD tiers
`CFG_TDD_CAUTION_PCT=1.5` → `CFG_RISK_CAUTIOUS=0.4`;
`CFG_TDD_WARNING_PCT=2.5` → `CFG_RISK_CONSERVATIVE=0.25`. Live has the tier
machinery (39 references) but the thresholds are hardcoded and the mapping onto
the live `total_dd_*` fields is **not** 1:1 — verify rather than transcribe.

---

## C. Do NOT port

* `TDD_WORST_CASE=1` — backtest measurement convention, marks positions to the
  bar's adverse extreme. No live meaning.
* `TERMINAL_ON_BREACH=1` — tells the backtest to stop on breach. No live meaning.
* `VOL_SIZE_*` — absent live, but `VOL_SIZE_ENABLE=0` in the winner, so it is
  off. Nothing to do.
* `CFG_DAILY_WALL_PCT=5.0` — the broker enforces the real wall; only needed live
  if the bot's own safety logic references it.

---

## D. Structural landmines — resolve BEFORE editing

### D1. The TP ladder has different depth in each system
Live `params/current_params.json` defines a **5-level** ladder (tp1-tp5, close
percentages 0.277/0.295/0.117/0.284/0.027). The winner defines **3 levels**
closing 0.25/0.60/0.15 = **1.00**, i.e. the position is fully closed at tp3.

The harness `BASE_TP` still carries tp4/tp5 values (3.4R and 4.7R at 0.1/0.3),
which the winner does not override — they are presumably unreachable because the
position is already flat. **This must be verified, not assumed.** If the engine
renormalises close percentages instead, the effective ladder is different from
what the table above implies and the live transcription would be wrong.

### D2. Two competing sources for risk per trade
`ftmo_config.py` says 0.6. `params/current_params.json` says 1.1. Both feed the
live bot. Determine which actually governs sizing before setting either, or the
account trades at a size nobody intended.

### D3. `max_lot` key mismatch (known, low priority)
Backtest reads `symbol_info.get('max_lot', 100.0)` but `get_symbol_info()`
returns `volume_max`, so it falls back to 100 — double the 50-lot 5ers cap the
live bot correctly enforces at `main_live_bot.py:4361`. No effect on any result
(peak observed 28.07 lots at $500k) but it should be fixed so the two engines
agree.

---

## E. Acceptance test — the part that makes this trustworthy

Transcription errors are silent. The plan is therefore not "port and inspect"
but:

1. Port A1-A5 and transcribe B1-B3.
2. Modify the backtest to read its configuration from **the live sources**
   (`ftmo_config.py` + `params/current_params.json`) instead of environment
   variables.
3. Re-run the 2015-2025 $50k scaled decade and the 63-start hard-period sample.
4. **The port is correct only if it reproduces $4,294,756 / 7 breaches per 63.**
   Any divergence means a setting did not transfer, and the diff tells us which.

Without step 4 there is no way to know the port worked, and a config that
silently differs is worse than no port at all — it would carry the credibility
of this round's testing while behaving differently.

---

## F. Sequence

| # | task | risk |
|---|---|---|
| 1 | Resolve D1, D2 | must precede any edit |
| 2 | Transcribe B1-B3 | low |
| 3 | Port A3 (exclusions), A2 (corr cap) | low |
| 4 | Port A1 (nightly de-risk) | medium — most behaviour-changing |
| 5 | Resolve and wire A5 (cum risk) | medium — contradictory comments |
| 6 | Port A4 (risk regime) | medium — increases position size |
| 7 | Acceptance test (E) | the gate |
| 8 | Fix D3 | cosmetic |

Nothing goes live until step 7 passes.
