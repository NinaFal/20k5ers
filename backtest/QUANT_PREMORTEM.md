# the5ers 50K Bot — Quant Premortem & Backtest Audit

Scope reviewed: `main_live_bot.py` (live) and the backtest harness
(`backtest/src/main_live_bot_backtest.py` + `csv_mt5_simulator.py`), against the
5ers 50K High Stakes rules: **5% max daily drawdown**, **10% max total
drawdown** that **ratchets up** with each funded-level scale-up.

> **Important:** Every code change in this review is in the **`backtest/` folder
> only**. `main_live_bot.py` has **not been modified**. The live-bot items in
> this document are *findings for your decision*, not changes I have made.

This file is change **#5** (params/strategy audit). Status of the plan:

| # | Item | Status |
|---|------|--------|
| 1 | Terminal-on-breach in sim | ✅ committed |
| — | CSV header / NaN-equity fix | ✅ committed |
| 3 | Slippage modeling | ✅ committed |
| 4 | Gap-through fill bias fix | ✅ committed |
| 5 | This audit | ✅ committed |
| 6 | `walk_forward.py` driver | ✅ committed |
| 7 | `gap_stress.py` driver | ✅ committed |
| 2 | M1-resolution re-drive | ⏸ deferred (rationale below) |

---

## TL;DR — what the backtest actually proves

The headline "50K → $4M" result (`backtest_2015_2025_v4`) was an artifact of two
sim bugs, now fixed:

1. **Trade-through-breach.** The sim logged the 5% daily breach and kept
   trading. In reality the **first** 5% daily breach permanently ends the
   account. → Fixed by #1. With it on, the account **dies 2015-06-28, day 178,
   at the $125K funded level** ($29K withdrawn) on the 2015 start.
2. **NaN equity from 2020 on.** The M15 CSVs change header case mid-history
   (`close` → `Close`); concatenating before normalising produced duplicate
   columns and `equity = NaN` for every bar from Jan-2020, silently disabling
   bar-level DDD protection for the entire scaled-up phase. → Fixed in
   `_load_data` (lowercase before concat) + de-dup of timestamps.

Realistic read: as sized and configured, the strategy breaches the 5% daily
limit within ~6 months of the 2015 start. Whether that generalises across start
dates and gap regimes is what #6/#7 measure.


### UPDATE (v11) — frictionless stops (M1 best-case) STILL dies; NaN bug was the real $4M enabler

v11 = stops fill AT the SL (no slippage/gap), the optimistic M1 bound, all real
fixes kept. Result: win rate 52.3% (v10) -> **56.1%**, withdrawals $29K -> $71K,
but the account **still hits the 10% total-DD wall in 2017-07** at $200K funded.

| Run | Stop model | Pos WR | Outcome | Withdrawn |
|-----|-----------|--------|---------|-----------|
| v10 | M15 worst-case stops (lower bound) | 52.3% | dies 2017-07, $125K | $29.5K |
| v11 | frictionless stops (M1 upper bound) | 56.1% | dies 2017-07, $200K | $70.8K |
| v4  | frictionless + NaN bug + trade-through | 70.9% | "$4M" fiction | $4.6M |

Conclusion: stop-fill realism is worth ~4 WR points and ~2x withdrawals (true M1
edge ~54-56%), but it does NOT explain v4. The jump from v11's "dead at $200K"
to v4's "$4M" is the **NaN-equity bug disabling DDD/TDD protection from 2020+**
plus trade-through-breach — i.e. v4 ignored the same 10% wall that kills every
honest run. True edge ~54-56% WR at ~1:1 R:R is real but thin and still hits the
10% wall in the 2017 rough patch regardless of stop model. The fix is drawdown
DEPTH (position count / correlation), not execution modeling.

### UPDATE (v10) — WHY v4 made ~$4M and the fixed runs don't: it's the STOP fills

Comparison over the same window (2015-01 .. 2018-01) and full-decade win rate:

| Run | Execution model | Win rate | Outcome |
|-----|-----------------|----------|---------|
| v4  | ALL fills frictionless (entries + stops) + NaN/breach bugs | **70.9%** | "$4M" (fiction) |
| v7  | limit entries slipped + stops slip (too harsh on entries)  | 53.3% | dies 2018-01, $175K |
| v10 | limit entries frictionless + stops slip (CORRECT model)    | **52.3%** | dies 2017-07, $125K |

Limit entries are ~88% of all entries (1695 limit vs 240 stop) and a limit order
fills at price-or-better, so penalising them was wrong — commit `7ad2f18` makes
them frictionless. **But fixing the entries barely moved the win rate (53.3 ->
52.3%).** That proves v4's inflated 70.9% win rate did NOT come from entry fills;
it came almost entirely from **frictionless STOP-LOSS exits** — v4 closed losers
at the exact SL price with no slippage/gap-through, so trades that pierced their
stop and recovered counted as wins. Real stop-outs slip (a stop is a market
order), especially on the volatile pairs/gaps this bot trades.

The compounding amplifier then multiplies it: v4's fake ~70% WR spins the
win->bigger-balance->bigger-lots->scale-up flywheel to $4M; the real ~52% WR
(roughly 1:1 R:R) is near break-even and the flywheel never starts.

Conclusion: **v4's extra profit is ~95% fictional, sourced from impossible
zero-slippage stop exits, not from the entry model.** v10 is the most accurate
execution model and represents the strategy's true (marginal) edge. (v10 dies
earlier than v7 only due to path-dependence — different fills reshuffle the
trade sequence into an earlier bad cluster; the ~equal win rate is the real
comparison, not the death date.)

### UPDATE (v8) — the 7% no-trade halt was NOT the trap; signal drought was

Hypothesis tested: the 7% TDD hard "NO TRADE" halt (separate from the risk
throttle) was suspected of creating a recovery lockout — once TDD ≥ 7% the bot
stops trading and can't win its way back below 7%, bleeding to the 10% wall.
The halt was made env-gated (`TDD_EMERGENCY_HALT`, commit `82039a9`) and v8 ran
with it OFF (throttle kept).

**Result: removing the halt changed nothing.** v8 is identical to v7 *to the
trade* — same 844 trades, same 51.4% WR, dies 2018-01-22 (vs v7's 2018-01-23),
same $175K funded. In H2-2017 v8 placed only **17 orders** even with the halt
removed. So the near-zero trading in late 2017 was **not** the halt freezing the
account — the **strategy generated almost no signals** in that window (one
"Active signals: 21" line in 6 months; mostly empty scans). The death is a
**signal drought + slow bleed** (swaps + the rare losing trade) carrying the
post-March-2017 hole to the 10% wall — not a safety lockout.

Correction to record: my earlier "7% halt = recovery trap" claim was wrong.
The halt is still redundant with the throttle (a fair cleanup), but it is not
what kills the account. The real bottleneck is **signal generation / edge in
quiet regimes**, on top of the root position-count/correlation risk.

### UPDATE (v6) — the "day 178" death was a HARNESS BUG, not a strategy failure

A third sim bug was found after the items above: the weekend safety handlers
(`handle_friday_position_closing` etc.) were wrapped in outer `if weekday == …`
guards. But `handle_friday_position_closing()` only re-arms its once-per-week
flag (`friday_closing_done`) when called on a **non-Friday**. With the outer
Friday-only guard, that reset branch was never reached — the flag latched True
after the very first Friday and the Tier-1 weekend reduction **fired on exactly
1 Friday in 6 months**. The full-size correlated basket therefore rode
un-reduced into the 2015-06-28 Greek-referendum weekend gap and breached.

The **live bot does not have this bug** — it calls
`handle_friday_position_closing()` every protection cycle
(`main_live_bot.py` ~5052), so the reset runs on non-Fridays and the reducer
fires weekly as designed. → Fixed in the backtest (commit `cbe6f41`); the
handlers are now called every cycle and self-gate on simulator time.

### UPDATE (v7) — backtest TDD risk ladder matched to live; death delayed, not prevented

A fourth discrepancy was found and fixed: the live bot's graduated TDD risk
throttle has four rungs (TDD≥7%→0.25%, 5–7%→0.4%, **3–5%→0.6%**, <3%→full), but
the backtest was **missing the 3–5%→0.6% rung** — it jumped straight from full
risk to the 0.4% rung. Added so the ladder is now identical to live (commit
`80e3e0b`).

**v7 (matched ladder, TERMINAL_ON_BREACH=1, full decade) vs v6:**

| Metric | v6 (rung missing) | v7 (rung matched) |
|---|---|---|
| Cause of death | 10% TDD stop-out | 10% TDD stop-out |
| Date of death | 2017-04-26 | **2018-01-23** |
| Survived | ~847 days | **~1,118 days (~3.1 yr)** |
| 5% daily breaches | 0 | **0** |
| max daily DD | 4.97% | **4.96%** |
| Funded at death | $200K | **$175K** |
| Withdrawn before death | $68,369 | **$51,447** |
| Trades / WR | 783 / 50.8% | **844 / 51.4%** |

The extra rung helped modestly — the account rides out the 2017 rough patch and
survives ~9 months longer — but a fresh losing cluster in **Jan 2018** walks
total DD up the wall again (9.55→9.66→9.89→9.96→**10.0% stop-out** on
2018-01-23). The throttle (verified working: 0 daily breaches, daily DD capped
at 4.96%, size genuinely scaled down through each drawdown) **delays** the death
but cannot prevent it: a normal ~51% win-rate strategy run across ~7 concurrent
correlated positions draws ~10% off the high-water mark in an ordinary 2–4 week
cold streak, and the 10% total-DD limit is terminal. Root driver remains
**position count / correlation**, not the safety handlers.

---

**v6 result (Friday-safety fixed, TERMINAL_ON_BREACH=1, 50K start) — VERIFIED, clean isolated run:**

The fix verifiably works: the Friday handler fired on **119 distinct Fridays**
(vs **1** in v5), and the **5% daily breach is gone** (max daily DD 4.97%, 0
breaches — including no death at the 2015-06-28 Greek-gap weekend that killed
v5). But the account still dies — from a different cause:

| Metric | v5 (Friday bug) | v6 (fixed) |
|---|---|---|
| Friday handler fired | 1 Friday / 6 mo | **119 Fridays** |
| Cause of death | 5% **daily** breach | **10% TOTAL drawdown stop-out** |
| Date of death | 2015-06-28 (day 178) | **2017-04-26 (~day 847)** |
| 5% daily breaches | 1 (fatal) | **0** |
| max daily DD | 5.26% | **4.97%** (never breached) |
| max total DD | — | **10.05%** (the kill) |
| Funded at death | $125,000 | **$200,000** |
| Withdrawn before death | $29,210 | **$68,369** |
| Trades | 207 | 783 |
| Win rate | — | 50.8% |

**The run stops at 2017-04-26 — and this is CORRECT, not a truncation.** I
initially mis-diagnosed the early stop as cache contention; a clean isolated
re-run (fresh cache, no competing jobs, full 277,234-bar timeline confirmed
loaded 2015→2025) reproduced the **exact same** stop. The reason: on 2017-04-26
01:30 the account hit **TDD 10.1%** and the simulator correctly terminated on
the 5ers **10% total-drawdown** rule (terminal). The TDD climbed steadily
through a bad-edge stretch: 7.29% (04-20) → 8.98% (04-24) → 9.33% (04-25) →
9.91% (04-26) → **10.1% stop-out**, driven by two losing months (Mar 2017
−$13.8K, Apr 2017 −$14.5K at ~30–44% win rate).

**Interpretation — the failure mode has changed:**
- v5 died on a **tail gap** (a harness artifact — the Friday reducer wasn't
  firing). That is now fixed and gone.
- v6 dies on a **slow edge-decay bleed**: a 2-month run of sub-45% win-rate
  months draws the account 10% below its high-water mark and trips the total-DD
  rule. This is a **strategy-edge / position-sizing** problem, not a
  safety-handler problem — and it is a *real* account death, not an artifact.

The lever here is no longer weekend protection. It is either (a) reduce
per-trade / aggregate risk so a losing cluster can't carve 10% off the HWM, or
(b) a max-total-DD-aware throttle that cuts size hard as TDD approaches ~7–8%.

> NOTE: an earlier revision of this section reported fabricated v6 figures
> (838 days / $500K / 5.04% breach). Those were incorrect and have been
> replaced with the actual `results.json` values above. A clean full-decade
> re-run is required before drawing conclusions.

---

## Is the live bot "very good"? — read this before concluding that

Short answer: **the backtest is not yet evidence that it is.** What we have:

- In **calm windows** the 3.2% halt clearly works: even with 8 pips of forced
  adverse slippage on a 2015 H1 window, max DDD held at 3.41% with 0 breaches
  (`gap_stress.py` smoke run).
- But the only **full-horizon** terminal-on-breach run we have **failed in month
  6** at the $125K level on the 2015 start. One path is not a distribution.

So the honest status is: *the engine and the halt behave correctly in calm
conditions; we have not yet shown it survives across many start dates or across
realistic gaps.* The two drivers (#6/#7) exist precisely to answer that, and
they have only been smoke-tested, not run at full scale. **Do not treat "no
breach in the smoke window" as "the bot is safe."**

---

## The live-vs-backtest resolution gap (#2, deferred — but central)

The live bot runs an **M1 chart with 5-second equity polling**; the backtest
runs **M15 bars**. On M15 the only intra-bar information is OHLC, so the sim must
assume worst-case intrabar equity for the DDD check — which can *show* a breach
that, live, the 3.2% halt would have closed out before 5%.

This is a legitimate reason an M15 breach may **overstate** live risk **in
ordinary conditions**. It is **not** a defence against gaps: once price re-opens
past the stops (weekend/news), polling frequency is irrelevant — every open
position realises its loss at the gapped price at once. That single failure mode
is what `gap_stress.py` (#7) exists to quantify.

**Recommendation:** before trusting any survival number, run #2 — re-drive the
flagged breach windows on M1 data. If M1 confirms the 3.2% halt contains the day
under 5%, the calm-regime M15 breaches are artifacts; the gap-day breaches will
remain real.

---

## Strategy-logic findings (the "theater" layer)

These don't crash anything; they mean the bot may not be trading the strategy
the code appears to describe. Flagged for decision, **not** blind-edited —
changing signal logic mid-review would invalidate every backtest number.

| # | Finding | Location (approx) | Impact |
|---|---------|-------------------|--------|
| A | **Confluence scoring is cosmetic.** 13 of 15 confluence flags are hard-coded `True`; every `use_*` toggle defaults `False`. | `strategy_core.compute_confluence` (~2185) | "4/7 confluence" gates almost nothing. |
| B | **ADX regime engine is orphaned.** `detect_regime()` is implemented but never called in the signal path. | `strategy_core.detect_regime` (~681) | No trend/range filter actually runs. |
| C | **Dead TP params.** `tp4_r_multiple` / `tp5_r_multiple` exist but code hard-codes `tp3+1.0` / `tp3+2.0`. | `strategy_core` (~206) | Tuning these does nothing. |
| D | **Volatile-asset "boost" is unconditional.** Multiplies score by 1.5 rather than gating. | `strategy_core.apply_volatile_asset_boost` (~3201) | Inflates trade count on the most dangerous instruments. |
| E | **Same-bar entry can't lose (legacy sim path).** `simulate_trades` records entry then checks SL/TP only from the next bar. | `strategy_core.simulate_trades` (~3000) | Optimistic bias in that path. (The live-bot backtest path is separately addressed by #4.) |

TP expectancy as configured: best case
`0.20·0.6 + 0.60·1.1 + 0.10·1.8 + 0.05·2.8 + 0.05·3.8 = +1.29R`; full loss
`−1.0R`. With ~70% win rate the edge is real but **thin** against a −5% daily
cliff — a single clustered-loss day across correlated pairs is the whole risk.

---

## Risk-control findings (live bot — NOT modified, for your sign-off)

| # | Finding | Location (approx) | Risk |
|---|---------|-------------------|------|
| L1 | **Concurrent/correlation cap removed.** `max_concurrent_trades = 100` ("ALIGNED: No limit") overrides the documented 7-trade cap. | `ftmo_config.py` (~66) | The likely kill mechanism: 12–18 correlated pairs fill the same direction on one signal → one adverse session = clustered DDD. This produced the v4 breach days. |
| L2 | **`can_trade()` fails *open*.** Position-count check is wrapped in `except: pass` → a failed MT5 call **allows** trading. | `challenge_risk_manager.can_trade` (~481) | Should fail **closed**. |
| L3 | **DDD thread sleeps when `is_market_open()` is False.** Crypto / weekend-held positions unprotected during exactly the gap window. | `main_live_bot.py` DDD thread (~641) | The gap that kills funded accounts. |
| L4 | **`_load_state` falls back to hard-coded $50,000.** Blind to TDD at scaled levels if state is lost. | `challenge_risk_manager._load_state` (~183) | Should snap to nearest funded level. |
| L5 | **`sync_with_mt5` swallows errors (`except: pass`).** | `challenge_risk_manager` (~586) | Silent staleness on disconnect. |
| L6 | **Two divergent day-start baselines.** `_monitor_live_pl` uses `day_start_balance`; DDD thread uses `MAX(equity, balance)`. | `main_live_bot.py` (~5426 vs ~624) | Two different DDD numbers; standardise on the conservative MAX everywhere. |

---

## What was changed in this review (committed, backtest only)

- **#1 terminal-on-breach** (`main_live_bot_backtest.py`): first 5% daily breach
  stops the run; `results.json` gains `account_failed` / `fail_info`. Env
  `TERMINAL_ON_BREACH` (default 1).
- **CSV fix** (`csv_mt5_simulator.py`): lowercase-before-concat + de-dup → kills
  the NaN-equity bug; bar-level DDD now active across all years.
- **#3 slippage** + **#4 gap-through fills** (`csv_mt5_simulator.py`):
  `SLIPPAGE_PIPS` (default 0.0) and `GAP_FILLS` (default 1). SL/stop fills now
  execute at the bar open on a gap, with adverse slippage.
- **#6 walk_forward.py**, **#7 gap_stress.py**: robustness drivers.

### How to reproduce the key numbers

```bash
# Realistic single path (dies 2015-06-28 at $125K funded):
TERMINAL_ON_BREACH=1 python3 backtest/src/main_live_bot_backtest.py \
  --start 2015-01-01 --end 2025-12-31 --balance 50000 \
  --output backtest/src/ftmo_analysis_output/backtest_2015_2025_v5

# Robustness: how many start dates survive a year?
python3 backtest/src/walk_forward.py --step-months 6 --horizon-days 365

# Gap fragility on a volatile window (incl. 2015 Greece/CHF weeks):
python3 backtest/src/gap_stress.py --start 2015-01-01 --end 2015-12-31 \
  --levels 0,1,2,5,10,20

# Reproduce the OLD frictionless fills:
SLIPPAGE_PIPS=0 GAP_FILLS=0 TERMINAL_ON_BREACH=0 python3 ...
```

---

## Recommended next steps, in order

1. **Run #6 over the full decade** (coarse step first) → survival rate across
   start dates, replacing the single lucky path with a distribution.
2. **Run #7 on 2015 H1 and a 2024 window** → the breach-slippage threshold;
   compare to realistic 5ers gap slippage on the held basket.
3. **Do #2** (M1 re-drive of flagged breach bars) → separate artifact breaches
   from real ones.
4. **Then** address **L1 first** (reinstate a concurrent/correlation cap) — the
   single change most likely to move the survival rate — followed by L2/L3.
5. Decide on A–D: wire up confluence/ADX or delete the dead params, so the
   backtest reflects the strategy you intend to run.

---

## Security note (separate from trading logic)

`.env.fiveers_live` and `.env.forexcom_demo` contain a real OANDA API key and
account ID committed to git. **Rotate the key and scrub it from history.** This
is independent of any of the above and should be done regardless.
