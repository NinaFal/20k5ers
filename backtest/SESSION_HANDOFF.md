# Backtest & optimization — full handoff for the next AI session

This document explains the 5%ers backtest engine, every change made in this
session, the findings (and dead-ends), how to run things in THIS environment
(important gotchas), and what's still open. Read it fully before continuing.

> **➡️ FORWARD PLAN LIVES IN [`OPTIMIZATION_ROADMAP.md`](OPTIMIZATION_ROADMAP.md).**
> That file is the plan of record for the staged optimization (entry → sizing/risk
> → TP/runners → Pareto), the objective hierarchy, the validation gauntlet, and the
> premortem guards. Read it alongside this handoff. This §0 is the current snapshot;
> §1–§7 below are the engine reference + the earlier continuous-run findings.

---

## 0. LATEST SESSION — Stage 2 RUNNING

**Last updated:** 2026-06-09 ~21:00 UTC

### Stage 1 COMPLETE ✅

All 710 cells (692 Stage 1c + 18 Stage 1d) swept. MFE/MAE report run on top-16
survivors. Stage 1d (c=0.35, 0.40) did NOT beat Stage 1c winners in runner
potential — deep-volatile entries won.

**Two finalists carried into Stage 2:**

| Tag | Entry config | Avg net | Maximin | MFE-p75 | Why |
|-----|-------------|---------|---------|---------|-----|
| **A** | c=0.55 v=0.80 thr=1.05 adx=0 | $59.8K | $28.7K | **1.74R** | best runner potential + robust |
| **B** | c=0.45 v=0.80 thr=1.15 adx=0 | **$70.0K** | $18.7K | 1.65R | best raw net |

Report: `output/doe/stage1c_entry_quality_report.csv` (16 finalists, all survived)

**Key finding:** TP1-hit% near-flat 76–81% (TP1=0.9R, trivial bar). Real
discriminators: MFE-p75 (runner potential) and maximin. Win-rate = diagnostic.

### Stage 2 RUNNING (regime-coherent risk)

**Design:** `_regime_risk_multiplier()` added to engine — uses ATR(14)/ATR(50)
same signal as entry fib switch. RISK_CALM_MULT/RISK_VOLATILE_MULT env vars scale
the 1.1% BASE_RISK independently per regime. VOL_SIZE (ATR percentile) retired
(different signal, two competing vol signals = incoherent).

**What's running now:**
```
keepalive_stage2.sh (run_in_background:true — NO & ever)
  └─ stage2_sizing_risk.py --entry A --trials 100
       (then B when A complete)
```

Log: `output/doe/stage2_run.log`
DBs: `output/doe/stage2_A.db`, `output/doe/stage2_B.db` (Optuna sqlite, resumable)
Best JSON: `output/doe/stage2_A_best.json` (written at end of each entry)

**How to relaunch if Stage 2 dies:**
```bash
# In Claude Code: Bash tool with run_in_background:true, NO &:
STAGE2_TRIALS=100 STAGE2_JOBS=1 bash /home/user/20k5ers/backtest/src/keepalive_stage2.sh
```

**Stage 2 objective:** maximin(net_pnl across 5 windows) − MARGIN_K × max(0, worst_TDD − 8.0)²
Any breach = hard veto: score = −1e9 + n_survived×1e6

**Search space:**
- `RISK_CALM_MULT` [0.50–1.50] × `RISK_VOLATILE_MULT` [0.40–1.80] (regime risk)
- `VOL_REGIME_DD_OFF` [2.0–5.0] (gate size-up when drawing down)
- TDD ladder: CAUTION/WARNING/EMERGENCY thresholds + risk values
- `CFG_DAILY_HALT_PCT` [1.5–3.5], `CFG_MAX_CUM_RISK` [2.5–5.0]
- 3 seed trials: {calm=1.0, vol=1.0} anchor + brackets

**After Stage 2:** pick winner (entry A or B) by post-sizing maximin + no-breach.
Lock into Stage 3 (TP ladder Optuna).

### Engine changes since last handoff

- `_regime_risk_multiplier()` — new method after `_vol_size_multiplier()`.
  ATR(14)/ATR(50) vs fib_vol_ratio_threshold → RISK_CALM_MULT or RISK_VOLATILE_MULT.
  Memoized (symbol, day). Gated by VOL_REGIME_DD_OFF. Default off (RISK_REGIME_ENABLE=0).
- MFE/MAE tracking: `_mark_mfe_mae()` (TRACK_MFE_MAE=1 gate), results in results dict.
  Already merged from worktree branch.

**Branch:** `claude/awesome-maxwell-50dMF`

---

## 1. What the backtest is

- **Engine:** `backtest/src/main_live_bot_backtest.py` — a port of the live
  trading bot that replays history bar-by-bar. It is kept aligned with
  `main_live_bot.py` (the live bot).
- **Market simulator:** `backtest/src/csv_mt5_simulator.py` (`CSVMT5Simulator`),
  drop-in for the live MT5 client. Data is **M15 OHLCV** in `data/ohlcv/*.csv`.
  There is **no M1/tick data** — this matters for breach fidelity (see §6).
- **Run it:**
  ```
  OPT_PARAMS='{...TP/SL json...}' <ENV_LEVERS> \
  python3 backtest/src/main_live_bot_backtest.py \
    --start 2015-01-01 --end 2024-12-31 --balance 50000 --output <dir> --quiet
  ```
  Writes `<dir>/results.json` (+ trades.csv, tdd_series.csv). Key result fields:
  `account_failed`, `net_pnl`, `max_tdd_pct`, `max_ddd_pct`,
  `fiveers_total_withdrawn`, `fiveers_final_funded_level`, `fiveers_scaling_log`,
  `fail_info` (breach_type total/daily, time, funded_level_at_failure).

### The 5%ers funded-account model (in the simulator)
- **Funded-level ladder:** 50k→60k→70k→80k→100k→125k→150k→175k→200k→250k→300k→
  350k→400k→450k→500k→600k→700k→800k→1M→…→4M.
- **Scaling:** at each **+10% profit** on the current level, the account advances
  to the next level and a **profit split** is withdrawn.
- **Profit split tiers:** <175k=80%, 175k+=85%, 250k+=90%, **350k+=100%** (you
  keep all profit; there's also a fixed payout bonus 5ers adds that is NOT
  modeled). → **400k is the sweet spot: 100% split, no reason to scale higher.**
- **Walls:** **TDD (total) = 10%** measured from the funded floor;
  **DDD (daily) = 5%** measured from day-start equity. Either = account dead
  (`TERMINAL_ON_BREACH=1`).
- **CRITICAL — the TDD floor RATCHETS:** on each scaling event the engine sets
  `initial_balance = new funded level` (main_live_bot_backtest.py ~line 5554),
  so the 10% wall re-anchors UP to each new level. This is the single biggest
  driver of high-level breaches (see §5).
- **Costs (all modeled, deducted from P&L):** commission **$4/lot round-trip**
  forex/metals, **$0** on indices (NAS100/UK100/US500/GER40); spread (via
  `SLIPPAGE_PIPS`); overnight swap.

---

## 2. Env levers (the knobs — all gated, defaults shown)

| Env var | Default | What it does |
|---|---|---|
| `OPT_PARAMS` | (live params) | JSON overlay of TP R-multiples, close %s, trailing SLs |
| `CFG_TDD_CAUTION_PCT` / `CFG_RISK_CAUTIOUS` | 3.0 / 0.60 | drawdown ladder: caution band threshold + risk% |
| `CFG_TDD_WARNING_PCT` / `CFG_RISK_CONSERVATIVE` | 5.0(live) / — | warning band |
| `CFG_TDD_EMERGENCY_PCT` / `CFG_RISK_ULTRASAFE` | 7.0 / 0.25 | emergency band |
| `VOL_SIZE_ENABLE` / `VOL_SIZE_MULT_LOW` / `VOL_SIZE_MULT_HIGH` | 0 / 1.0 / 1.0 | volatility-scaled sizing: size up in calm (LOW mult), down in turbulent (HIGH mult), by ATR percentile |
| **`VOL_REGIME_DD_OFF`** / `VOL_REGIME_DD_MULT` | 100(off) / 1.0 | **REGIME GATE (key breakthrough):** collapse the vol size-UP to MULT once TDD/DDD ≥ this %. i.e. only size up while healthy |
| **`CFG_MAX_CUM_RISK`** | 3.0 | **cumulative open-risk cap** (% of balance). Bounds worst single-day loss. Faithful to live (live enforces this; backtest had it removed). 100 = off |
| `CFG_DAILY_HALT_PCT` | 3.2 | daily close-all circuit-breaker threshold |
| `DDD_CLOSE_AT_TRIGGER` | 0 | **faithful daily close model:** close at the trigger (like live's 5s thread) instead of the bar's worst wick. SET TO 1 — see §6 |
| `TDD_WORST_CASE` | 0 | conservative breach DETECTION: mark open positions to bar high/low for the wall check. For final validation only |
| **`FIVEERS_MAX_SCALE`** | 4000000 | **scaling cap** — stop scaling at this funded level; floor freezes |
| `TDD_WALL_SAFETY` | 3.0 | emergency wall-guard room-cap divisor |
| `CORR_GROUP_CAP` | 0(off) | max concurrent positions per correlation group |
| `TDD_EMERGENCY_HALT` | 1 | 7% TDD scan-block (causes a deadlock in continuous runs — keep 0 for continuous) |
| `EXCLUDE_SYMBOLS` | "" | comma-list of tickers to drop |
| `TERMINAL_ON_BREACH` / `SLIPPAGE_PIPS` / `GAP_FILLS` | 1 / 0 / 1 | realism |

---

## 3. Engine changes/fixes made this session (all committed)

1. **TDD breach now sets `account_failed`** — previously a 10% total-DD breach
   broke the loop but didn't flag failure, so the optimizer was blind to total
   breaches. `_register_breach(..., kind='total')`.
2. **Regime gate** (`VOL_REGIME_DD_OFF`) — the breakthrough. The static vol
   size-up sized UP into calm-but-choppy regimes (2017) and bled to the wall,
   fighting the drawdown ladder. Gating it off while drawing down fixed 2017
   (went from dead@10% to $2.2M @ 5.78% TDD).
3. **Faithful daily close model** (`DDD_CLOSE_AT_TRIGGER`) — the M15 close-all was
   marking remaining positions to the bar's WORST wick, which both overstated
   daily breaches AND destroyed profit (2016→ run: $265k → $1.88M when closing
   at the trigger like live does).
4. **Cumulative open-risk cap** (`CFG_MAX_CUM_RISK`) — live enforces a 3% cap via
   `risk_manager.check_trade`; the backtest had it removed ("to match
   simulator"). Re-added (faithful) — bounds worst-case daily loss.
5. **Worst-case breach detection** (`TDD_WORST_CASE`) — for final validation.
6. **Scaling cap** (`FIVEERS_MAX_SCALE`) — freeze the ratcheting TDD floor.
7. **Deleted the flat-before-entry "wall-guard"** — it trapped the account at the
   wall instead of letting it recover (turned a survivable 9.4% draw into a 10%
   breach). Kept only the principled room-cap.
8. **Gated the 7% TDD scan-block** behind `TDD_EMERGENCY_HALT` (it deadlocked
   continuous runs — froze trading for 9.7 years once TDD hit 7%).

## 4. Optimizers / tools (all committed)
- `backtest/src/optimize_continuous.py` — scores the REAL continuous run with a
  hard 0-breach gate. Has `run()`, `attrs()`, `score()`, `BASE_ENV`, `TP40`.
  Other scripts import it.
- `backtest/src/optimize_multistart.py` — scores the WORST of multiple START
  dates (the right robustness objective). Latest version is centered on the
  regime gate. Studies in sqlite (see file).
- `backtest/src/optimize_tp.py` — cold-start TP-ladder sweep (produced "opt#40":
  TP 0.5/0.9/1.2/1.5/5.2). **Note: cold-start ≠ continuous; see §5.**
- `backtest/src/robustness_tp.py` — walk-forward + Monte-Carlo validator.

---

## 5. FINDINGS — the journey (read this to avoid repeating dead-ends)

1. **Cold-start sum ≠ continuous survival.** A config 0-breach across 10
   independent cold-start years can still DIE in the continuous run, because the
   account scales up and the ratcheting floor + bigger positions breach at high
   levels. Always validate on the continuous run and across multiple START dates.
2. **The regime gate is the one unambiguous win** — size up only while healthy.
   Fixed the 2017 total bleed. The static "always size up in calm" was a trap
   (looked great on the lucky 2015 path, breached elsewhere).
3. **The scaling ratchet causes high-level total breaches.** 2016-start died at
   the **$700k** funded level in 2022 because the floor had ratcheted to $630k.
   Capping scaling at 400k drops max TDD from ~10% to ~6-8% (cap fixes total-DD).
4. **The cumulative-risk cap fixes the daily-gap (Sept-2022) BUT over-constrains
   choppy years.** With cum-risk 3.5% + daily-halt 2.5%, the 2016→2022 run
   survived (TDD 8.15%, DDD 3.82%, $537k net) — looked like victory. But the
   full 2015→ run then bled to a TOTAL breach in Dec 2015 (the tight controls
   strangled recovery in a choppy year). **THE LEVERS TRADE OFF: loosen → 2022
   daily gap kills you; tighten → choppy years bleed out. No free lunch found.**
5. **The CHF black swan (2015-01-15, SNB franc unpeg)** is un-hedgeable — franc
   pairs gapped 20-30% past all stops. Any 2015-start with CHF exposure dies in
   13 days (net -$1,887). The strategy trades CHF pairs (NZD_CHF, AUD_CHF…).
   **Recommend excluding CHF pairs** via `EXCLUDE_SYMBOLS` to remove this.
6. **Best account to scale to ≈ 400k** — reaches the 100% profit-split tier;
   scaling higher only adds floor-ratchet breach risk for no better split.
7. **Honest bottom line:** the strategy is a strong PROFIT engine in favorable
   multi-year windows ($537k–$2.2M depending on start) but is **NOT breach-proof
   over an arbitrary 10-year path.** The "robust $1M+" goal was not achieved;
   the daily-gap vs choppy-bleed tension is real and unresolved.

### Best config found (NOT fully robust — see finding #4)
Regime gate `VOL_REGIME_DD_OFF=3.0`, vol 1.7/0.6, scaling cap 400k,
`DDD_CLOSE_AT_TRIGGER=1`, NEWTP ladder (0.9/1.7/2.4/3.4/4.7 R, closes
.10/.35/.15/.10/.30, trail .7/1.6/2.0), rungs 5.5/7.5/8.5 @ .45/.25/.25.
Adding `CFG_MAX_CUM_RISK=3.5` + `CFG_DAILY_HALT_PCT=2.5` fixes the 2022 gap but
breaks choppy years. See `backtest/RECOMMENDED_CONFIG.md`.

---

## 6. ENVIRONMENT GOTCHAS (these wasted hours — do not repeat)

- **`/tmp` is UNSTABLE** — it gets wiped mid-session, so scripts/logs/results
  written there vanish and processes "run" but produce nothing. **Use a stable
  dir in the repo** (this session used `.work/`, gitignored). Optuna sqlite DBs
  in /tmp DID persist across some recycles, but don't rely on it.
- **CRITICAL — Firecracker init reaps orphaned processes.** PID 1 is
  `/process_api --firecracker-init`, a custom VM init that **kills any process
  that becomes an orphan** (parent dies). `setsid`, `nohup`, `disown`, and
  trailing `&` ALL cause processes to be re-parented to PID 1 and then killed
  within seconds. **The only safe way to keep long-running background jobs alive
  is to run them WITHOUT `&` via the harness's `run_in_background:true` on the
  Bash tool.** This keeps the harness shell alive as the parent. For multi-layer
  daemons (keepalive → watchdog → grid), run only the outermost (`keepalive.sh`)
  this way; it in turn launches children with `&`, which is fine because the
  keepalive parent is itself alive and attached.
- **`setsid`-detached background jobs die immediately here.** Same reason as above.
- **Container recycles frequently on idle** — every recycle kills all background
  processes. Jobs MUST be resumable (write results incrementally to a stable
  dir + skip-if-done). The container stays alive while actively computing.
- **A full 10-year M15 run takes ~8–11 min**; the Bash tool's max timeout is
  10 min, so a 10yr run does NOT fit foreground — use background. A ~7yr run
  (e.g. 2016→2022) does fit and captures the key 2017+2022 risks.
- **Memory:** ~4.7GB per run; 16GB box → **max 2 concurrent** (4 = OOM kills).
- **Killing processes:** `kill -9 <pid>` often fails on the multithreaded
  Python runs (Sl state). Kill by **process group**: `kill -9 -<pgid>`.
- **grep self-matching:** `ps|grep optimize_x` counts your own shell/eval too;
  use `grep -v eval` / exact patterns to get true counts.

## 7. TODO / open questions for the next session

> **The active program is the staged entry→sizing→TP→Pareto plan in
> [`OPTIMIZATION_ROADMAP.md`](OPTIMIZATION_ROADMAP.md) — see §0 for live status.**
> The items below are the still-open continuous-run problems from the earlier
> session; several are now folded into Stage 2/3 of the roadmap (risk sizing, the
> 4-rung TDD, CHF exclusion, withdrawal policy).

1. **Resolve the daily-gap vs choppy-bleed tension** (finding #4) — the central
   unsolved problem. Maybe a *time-decaying* cum-risk cap, or vol-aware daily
   sizing, or a different daily protection that doesn't whipsaw choppy years.
2. **Exclude CHF pairs** and re-measure (removes the 2015 black swan).
3. **Quantify the realistic expectation** properly: run several staggered start
   dates (CHF excluded) to 2024 in the background (resumable) and report the
   distribution of outcomes, not single lucky runs.
4. **Withdrawal policy:** model periodic % withdrawals (every 2 weeks/monthly)
   with scaling capped at 400k, and find max safe payout vs cushion.
5. **Reconcile live vs backtest:** the swept drawdown rungs (0.4@4.5) differ
   from live defaults (0.6@3.0); the cumulative cap is 3.0 live vs whatever we
   sweep. Align before any live port.
