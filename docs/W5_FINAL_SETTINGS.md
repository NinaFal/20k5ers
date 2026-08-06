# Round W5 — final settings, evidence, and what still blocks deployment

Status: **validated in backtest, NOT yet deployable.** The configuration below
passes every test this round applied. It also depends on behaviour the live bot
does not currently implement. Section 4 is the part to read before trading it.

---

## 1. The configuration

Winner: nightly-stage trial 65 plus the TDD-tier tightening from the 2025
rescue (`halt2.50+tdd`). Stored in `backtest/output/doe/wall5/current_best.json`.

### Backtest environment variables

| Variable | Value | What it does |
|---|---|---|
| `RISK_VOLATILE_MULT` | `1.0` | No risk reduction in volatile regimes |
| `CFG_MAX_CUM_RISK` | `7.0` | Cap on summed open risk, % of balance |
| `CORR_GROUP_CAP` | `6` | Max positions per correlation group |
| `MAX_TOTAL_POSITIONS` | `20` | Max concurrent positions |
| `NIGHTLY_DERISK` | `1` | **Master gate — the whole nightly block is dead without it** |
| `NIGHTLY_DERISK_HOUR` | `22` | UTC hour for the nightly de-risk pass |
| `NIGHTLY_R_NEW` | `0.5` | Positions below this R get reduced rather than held |
| `NIGHTLY_MAX_PER_GROUP` | `0` | Overnight positions allowed per group — **zero** |
| `NIGHTLY_MAX_TOTAL` | `0` | Overnight non-crypto positions allowed — **zero** |
| `NIGHTLY_R_CLOSE_LOSING` | `0.25` | Close overnight positions below 0.25R |
| `NIGHTLY_REDUCE_PCT` | `0.75` | Reduce the survivors by 75% |
| `CFG_DAILY_HALT_PCT` | `2.50` | Close-all trigger, % daily loss |
| `TDD_WALL_SAFETY` | `5.5` | Total-drawdown safety margin |
| `CFG_TDD_CAUTION_PCT` | `1.5` | Total DD at which risk drops to cautious |
| `CFG_RISK_CAUTIOUS` | `0.4` | Risk per trade in cautious mode, % |
| `CFG_TDD_WARNING_PCT` | `2.5` | Total DD at which risk drops to conservative |
| `CFG_RISK_CONSERVATIVE` | `0.25` | Risk per trade in conservative mode, % |
| `TDD_WORST_CASE` | `1` | Measurement only — see §3 |
| `FIVEERS_MAX_SCALE` | `500000` | Stop scaling at $500k |

### Trade parameters (`OPT_PARAMS`)

| Parameter | Value |
|---|---|
| `risk_per_trade_pct` | 2.7 |
| `tp1_r_multiple` / `tp1_close_pct` | 0.65 / 0.25 |
| `tp2_r_multiple` / `tp2_close_pct` | 1.85 / 0.60 |
| `tp3_r_multiple` / `tp3_close_pct` | 2.75 / 0.15 |
| `sl_after_tp1_r` | −0.10 |
| `sl_after_tp2_r` | 0.90 |
| `sl_after_tp3_r` | 1.70 |
| all six entry filters | disabled |

The disabled filters are not an oversight — an explicit A/B in this round found
all-six-on took 85 days against 91 all-off, and the filter stage's screen
winners then died in the decade gauntlet.

---

## 2. Evidence

All figures under `TDD_WORST_CASE=1`, which marks every open position to its M15
bar's adverse extreme rather than the close.

**Fresh $100k every January, 2016-2025:** zero breaches in all ten years.
Payout $2,771,302. Worst daily 4.85% of the 5% wall; worst total 6.08% of 10%.

**One continuous account, $100k in Jan 2016, funded level carried forward:**
survived all ten years, **$3,400,723** withdrawn. Reached the $500k cap during
2016 and stayed there. Worst daily 4.73%, worst total 4.27%. Best year was 2025
at $463,715 — the year that originally needed the rescue.

Comparison arms over the same continuous decade: t105 $2,292,222, t61 (the
previous incumbent) $1,302,573. Both also survived.

**Holdout, 100 fresh random starts 2015-2025** (seed 20260805, deliberately not
the selection seed, extended back into 2015 which no arm of this round touched):
in progress. At 44/100: **one breach**, median 17 days, fastest 6, 31 of 44
inside 30 days.

The breach is the important number in this document. Start **2019-07-31** passed
Step 1 in 13 days and then breached during Step 2, so it died in mid-August 2019
— a window the January-anchored decade gauntlet cannot reach, since that test
only ever starts an account on 2 January. Both the fresh-$100k gauntlet and the
continuous account show 2019 as clean (2.24% worst daily), and both are wrong
about this window. That is precisely what the random-start holdout exists to
catch, and it is the argument against trusting the ten-year "zero breach"
headline on its own.

At this rate the true breach frequency is roughly 2-3 per 100 attempts, not
zero. Diagnosis of which wall it hit, and whether the safety tiers fired, is
pending — it needs a single re-run of that start with detail retained, queued
behind the current jobs.

Four further starts did not breach but failed to pass inside the 75-day horizon,
all clustered around the January 2015 SNB unpeg: the account survives the event
intact but cannot build the required gain in the window.

**Why drawdown is lower at the cap.** Crossing a scaling rung credits the next
account size (`csv_mt5_simulator.py:386` sets balance to the new level), so
sizing jumps mid-day while `day_start_equity`, the daily-drawdown denominator,
stays anchored to the pre-jump figure. Same year, same config, same prices,
varying only the starting level:

| year | climbing from $100k | capped at $500k | difference |
|---|---|---|---|
| 2016 | 4.73% | 3.12% | −1.61pp |
| 2019 | 3.59% | 2.24% | −1.35pp |
| 2021 | 4.85% | in progress | — |

Consistent across two independent years. Note the effect is real but partial —
capped 2016 still runs 3.12% against 2019's capped 2.24%, so the calendar year
matters at least as much as the climbing.

---

## 2b. UNRESOLVED: the Step 1 target may be wrong

Every challenge result in this document — the holdout's pass times, the 9-day
t47 run, every p30 figure across all seven optimisation stages — was measured
against a **Step 1 target of 8%** (`challenge_score.py:39`,
`STEP1_TARGET = 0.08 * ACCOUNT`).

The5ers' current High Stakes page states **Step 1 requires 10%**. Fetched twice,
same answer. This repo's own `docs/5ERS_COMPLIANCE.md:33` records `Step 1 | 8% |
$1,600` for a 20K High Stakes account, so either the programme changed after
that document was written or one of the two is simply wrong.

Everything else in the harness matches the published rules: 5% daily, 10% total,
3 minimum profitable days, and a profitable day defined as 0.5% of initial
balance. Only the Step 1 target is in dispute.

If 10% is correct, every pass-speed number here is optimistic — a 10% target is
25% more ground to cover than 8% — and the median would move materially. The
funded-account decade runs are unaffected, since they never simulate the
challenge. **Confirm the target for your specific account before relying on any
speed figure in this document.**

## 3. Assumptions this rests on

**Payouts are not charged against the daily loss limit.**
`main_live_bot_backtest.py:6078` subtracts scaling payouts from the daily
drawdown measure. This is necessary — a $50k milestone sweep is a balance
removal, not a trading loss, and counting it would register a phantom 10% breach
on every payout day. The arithmetic is sound (it measures net-of-withdrawal
equity, and a real trading loss still breaches). But whether 5ers actually
treats withdrawals this way is a **rule interpretation, not something the
backtest can prove**. If they do charge withdrawals against the daily limit,
every payout day at the cap becomes an instant breach and the capped-year
results collapse. Confirm with 5ers before trading.

**`TDD_WORST_CASE=1` is a measurement setting, not a trading setting.** It makes
the backtest pessimistic by assuming every open position hits its bar's worst
point simultaneously. It has no live equivalent and nothing to port.

**The 5% daily wall is enforced at the cap.** `main_live_bot_backtest.py:6088`
has no level condition. A behavioural test bracketing the wall around 2019's
known 2.24% capped drawdown (3.0% must survive, 2.0% and 1.5% must kill) is
queued — results go in `wall_enforcement.json`.

---

## 4. What blocks deployment

None of the tuned environment variables above are read by any live-bot file.
Every reader is under `backtest/src/`. Three specific gaps:

**4.1 The nightly de-risk pass does not exist live.** `_nightly` returns zero
matches in `main_live_bot.py` and four in the backtest fork. The underlying
machinery is there — `weekend_gap_manager.select_positions_for_weekend_tier1`
is called by both — but live only runs it before the *weekend*. The winner runs
it *every night at 22:00 UTC* holding **zero** non-crypto positions overnight,
closing anything below 0.25R and cutting the rest by 75%. That is load-bearing,
not a no-op, and it is very likely a large part of why the drawdown is
controlled. Port the caller at `main_live_bot_backtest.py:1938-2000`.

**4.2 The cumulative risk cap is contradictory across the two files.**
`main_live_bot.py:5001` reads *"NO cumulative risk check - removed to match
simulator. Simulator has no cumulative risk limits."* The backtest at line 3557
reads *"Env `CFG_MAX_CUM_RISK` (default 3.0 = live)"*. Both cannot be true. The
live bot does pass `max_cumulative_risk_pct` into `ChallengeRiskManager`
(line 2941, default 5.0), so a cap may be enforced on a different path. Resolve
which file is correct before trusting either comment; the winner wants 7.0.

**4.3 Live defaults differ sharply from the tuned values.** In `ftmo_config.py`:

| Field | Live default | Winner wants |
|---|---|---|
| `risk_per_trade_pct` | 0.6 | **2.7** |
| `daily_loss_halt_pct` | 3.2 | **2.50** |
| `max_cumulative_risk_pct` | 5.0 | **7.0** |
| `max_risk_conservative_pct` | 0.4 | **0.25** |
| `max_concurrent_trades` | 100 | **20** |

The risk-per-trade gap is 4.5×. The live bot is configured for a far more
conservative account than the one validated here. The TDD-tier mapping
(`CFG_TDD_CAUTION_PCT` / `CFG_TDD_WARNING_PCT`) is **not** a clean 1:1 onto the
live `total_dd_*` fields and needs checking rather than transcribing.

Until 4.1-4.3 are closed, the live bot will not reproduce these results, and the
backtest numbers should not be read as predictions of live performance.

---

## 5. Reproducing

```bash
uv run python3 backtest/src/w5_holdout100.py           # 100 fresh starts 2015-2025
uv run python3 backtest/src/w5_continuous_chunked.py   # continuous decade, level carried
uv run python3 backtest/src/w5_scaling_dd_probe.py     # climbing vs capped
uv run python3 backtest/src/w5_wall_enforcement_test.py# is the 5% wall live at the cap
uv run python3 backtest/src/w5_cap_sweep.py            # does a lower cap buy safety
```

Results land in `backtest/output/doe/wall5/` as JSON keyed by run, so any script
can be interrupted and resumed without losing completed work.
