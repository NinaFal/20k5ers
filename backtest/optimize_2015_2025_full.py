#!/usr/bin/env python3
"""
Full Parameter Optimizer – January 2015 to May 2015
=====================================================

Optimizes ALL key trading parameters:
  - TP1..TP5 R-multiples        (where to take partials)
  - TP1..TP5 close-percentages  (how much to close at each TP)
  - SL after TP1/TP2/TP3/TP4/TP5 (trailing stop levels)
  - risk_per_trade_pct           (risk per trade)
  - min_confluence               (minimum confluence score)
  - min_quality_factors          (minimum quality factors)
  - adx_trend_threshold          (ADX trend detection)
  - adx_range_threshold          (ADX range detection)
  - trend_min_confluence         (confluence for trend mode)
  - range_min_confluence         (confluence for range mode)
  - atr_vol_ratio_range          (ATR volatility ratio for range)
  - atr_min_percentile           (minimum ATR percentile filter)
  - volatile_asset_boost         (scoring boost for volatile assets)
  - entry_fib_level              (Fibonacci retracement entry level)
  - entry_limit_offset_atr       (ATR offset for limit entry)
  - compound_threshold_pct       (compounding profit threshold)

Settings:
  - 100 trials (default)
  - 4 parallel workers (default)
  - No timeout
  - Progress update every 60 seconds

Starts from current params (trial 0 = current_params.json values).

Usage:
    python backtest/optimize_2015_2025_full.py
    python backtest/optimize_2015_2025_full.py --trials 100 --parallel 4
    python backtest/optimize_2015_2025_full.py --apply backtest/optimization_results/2015_2025_full/optimization_YYYYMMDD_HHMMSS.json
"""

import sys
import json
import argparse
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import optuna
    from optuna.samplers import TPESampler, NSGAIISampler
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    print("ERROR: optuna not installed. Run: pip install optuna")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

START_DATE     = "2015-01-01"
END_DATE       = "2015-05-31"
BALANCE        = 20_000.0
NUM_TPS        = 5
UPDATE_EVERY_S = 60   # print progress update every 60 seconds

OUTPUT_DIR = Path(__file__).parent / "optimization_results" / "2015_jan_may"
LOG_FILE   = OUTPUT_DIR / "optimizer.log"


# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETER SEARCH RANGES
# ═══════════════════════════════════════════════════════════════════════════════

# Take Profit R-Multiples
TP_R_RANGES = {
    'tp1_r_multiple': (0.3, 1.2),
    'tp2_r_multiple': (0.8, 2.6),
    'tp3_r_multiple': (1.2, 3.2),
    'tp4_r_multiple': (1.6, 4.2),
    'tp5_r_multiple': (2.2, 6.0),
}

# Strategy & Risk Parameter Ranges: (low, high) = int,  (low, high, step) = float
STRATEGY_RANGES = {
    'risk_per_trade_pct':     (0.4, 1.5, 0.05),   # Current: 0.9
    'min_confluence':         (2, 6),               # Current: 3  (int)
    'min_quality_factors':    (2, 7),               # Current: 5  (int)
    'adx_trend_threshold':    (15.0, 30.0, 1.0),   # Current: 21.0
    'adx_range_threshold':    (8.0, 20.0, 1.0),    # Current: 14.0
    'trend_min_confluence':   (3, 7),               # Current: 4  (int)
    'range_min_confluence':   (2, 6),               # Current: 5  (int)
    'atr_vol_ratio_range':    (0.4, 1.5, 0.1),     # Current: 0.8
    'atr_min_percentile':     (15.0, 60.0, 1.0),   # Current: 35.0
    'volatile_asset_boost':   (1.0, 2.0, 0.05),    # Current: 1.3
    'entry_fib_level':        (0.382, 0.786, 0.01), # Current: 0.560
    'entry_limit_offset_atr': (0.0, 0.5, 0.01),    # Current: 0.14
    'compound_threshold_pct': (2.0, 15.0, 0.5),    # Current: 5.5
}


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGER
# ═══════════════════════════════════════════════════════════════════════════════

class Logger:
    """Writes to stdout and optionally to a log file."""
    def __init__(self, log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_path, "a", buffering=1)
        self._is_tty = sys.stdout.isatty()

    def __call__(self, msg: str = ""):
        print(msg, flush=True)
        if self._is_tty:
            self._log.write(msg + "\n")
            self._log.flush()

    def close(self):
        self._log.close()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BTResult:
    params: Dict[str, Any]
    net_return_pct: float
    total_trades: int
    win_rate: float
    max_tdd_pct: float
    max_ddd_pct: float
    final_balance: float
    ddd_halts: int
    safety_events: int
    tdd_warnings: int
    valid: bool
    monthly_stats: Dict[str, Any] = None


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def load_base_params() -> Dict[str, Any]:
    from params.params_loader import load_params_dict
    raw = load_params_dict()
    return raw.get("parameters", raw)


def create_temp_params(params: Dict[str, Any]) -> Path:
    tmp_dir = Path(tempfile.gettempdir()) / "opt2015_2025_params"
    tmp_dir.mkdir(exist_ok=True)
    path = tmp_dir / f"p_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    with open(path, "w") as f:
        json.dump({"optimization_mode": "OPTIMIZER_2015_2025",
                   "timestamp": datetime.now().isoformat(),
                   "parameters": params}, f, indent=2)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# BACKTEST RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_backtest(params: Dict[str, Any], log) -> BTResult:
    tmp_params = create_temp_params(params)
    out_dir = Path(tempfile.gettempdir()) / "opt2015_2025_results" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "src" / "main_live_bot_backtest.py"),
            "--start", START_DATE,
            "--end",   END_DATE,
            "--balance", str(BALANCE),
            "--output", str(out_dir),
            "--params-file", str(tmp_params),
            "--quiet",
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            cwd=str(Path(__file__).parent.parent),
        )

        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")[-400:] if proc.stderr else ""
            log(f"  [BACKTEST ERROR] returncode={proc.returncode} stderr={err!r}")
            return BTResult(params=params, net_return_pct=-100, total_trades=0, win_rate=0,
                            max_tdd_pct=100, max_ddd_pct=100, final_balance=BALANCE,
                            ddd_halts=0, safety_events=0, tdd_warnings=0, valid=False, monthly_stats={})

        rf = out_dir / "results.json"
        if not rf.exists():
            log(f"  [BACKTEST ERROR] results.json not found in {out_dir}")
            return BTResult(params=params, net_return_pct=-100, total_trades=0, win_rate=0,
                            max_tdd_pct=100, max_ddd_pct=100, final_balance=BALANCE,
                            ddd_halts=0, safety_events=0, tdd_warnings=0, valid=False, monthly_stats={})

        d = json.loads(rf.read_text())
        return BTResult(
            params=params,
            net_return_pct=d.get("return_pct", 0),
            total_trades=d.get("total_trades", 0),
            win_rate=d.get("win_rate", 0),
            max_tdd_pct=d.get("max_tdd_pct", 100),
            max_ddd_pct=d.get("max_ddd_pct", 100),
            final_balance=d.get("final_balance", BALANCE),
            ddd_halts=d.get("ddd_halts", 0),
            safety_events=d.get("safety_events", d.get("ddd_halts", 0)),
            tdd_warnings=d.get("tdd_warnings", 0),
            valid=(d.get("max_tdd_pct", 100) < 10 and d.get("max_ddd_pct", 100) < 5),
            monthly_stats=d.get("monthly_stats", {}),
        )

    except Exception as e:
        log(f"  [BACKTEST EXCEPTION] {type(e).__name__}: {e}")
        return BTResult(params=params, net_return_pct=-100, total_trades=0, win_rate=0,
                        max_tdd_pct=100, max_ddd_pct=100, final_balance=BALANCE,
                        ddd_halts=0, safety_events=0, tdd_warnings=0, valid=False, monthly_stats={})
    finally:
        if tmp_params.exists():
            tmp_params.unlink()


# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETER SAMPLERS
# ═══════════════════════════════════════════════════════════════════════════════

def sample_tp_and_sl_params(trial: optuna.Trial) -> Dict[str, Any]:
    """Sample TP R-multiples, close percentages, and SL-after-TP levels."""
    params = {}

    # ── TP R-multiples (strictly increasing) ──────────────────────────────────
    prev_r = 0.3
    tp_r_values = []
    for i in range(1, NUM_TPS + 1):
        key = f'tp{i}_r_multiple'
        lo, hi = TP_R_RANGES.get(key, (prev_r + 0.3, prev_r + 2.0))
        lo = max(lo, prev_r + 0.1)
        r_val = trial.suggest_float(key, lo, hi, step=0.1)
        params[key] = r_val
        tp_r_values.append(r_val)
        prev_r = r_val

    tp1_r, tp2_r, tp3_r, tp4_r, tp5_r = tp_r_values

    # ── Close percentages (normalized to sum 1.0) ─────────────────────────────
    # Weights sampled freely from [0.01, 1.0] – no per-TP range bias.
    # Normalization gives a truly random distribution over the simplex.
    weights = []
    for i in range(1, NUM_TPS + 1):
        w = trial.suggest_float(f'tp{i}_close_pct_weight', 0.01, 1.0, step=0.01)
        weights.append(w)
    total = sum(weights)
    assigned = []
    for i, w in enumerate(weights[:-1], 1):
        v = round(w / total, 3)
        params[f'tp{i}_close_pct'] = v
        assigned.append(v)
    params[f'tp{NUM_TPS}_close_pct'] = round(1.0 - sum(assigned), 3)

    # ── SL levels after each TP ───────────────────────────────────────────────
    def sl_range(lo, hi):
        return lo, hi if hi - lo >= 0.1 else lo + 0.1

    params['sl_after_tp1_r'] = trial.suggest_float('sl_after_tp1_r', 0.0, max(tp1_r, 0.1), step=0.05)
    params['sl_after_tp2_r'] = trial.suggest_float('sl_after_tp2_r', *sl_range(tp1_r, tp2_r), step=0.05)
    params['sl_after_tp3_r'] = trial.suggest_float('sl_after_tp3_r', *sl_range(tp1_r, tp3_r), step=0.05)
    params['sl_after_tp4_r'] = trial.suggest_float('sl_after_tp4_r', *sl_range(tp2_r, tp4_r), step=0.05)
    params['sl_after_tp5_r'] = trial.suggest_float('sl_after_tp5_r', *sl_range(tp3_r, tp5_r), step=0.05)

    return params


def sample_strategy_params(trial: optuna.Trial) -> Dict[str, Any]:
    """Sample strategy & risk parameters."""
    params = {}
    for key, bounds in STRATEGY_RANGES.items():
        if len(bounds) == 2:
            params[key] = trial.suggest_int(key, bounds[0], bounds[1])
        else:
            lo, hi, step = bounds
            params[key] = trial.suggest_float(key, lo, hi, step=step)
    return params


# ═══════════════════════════════════════════════════════════════════════════════
# OBJECTIVE
# ═══════════════════════════════════════════════════════════════════════════════

def make_objective(base_params: Dict[str, Any], log):
    def objective(trial: optuna.Trial) -> float:
        params = dict(base_params)
        params.update(sample_tp_and_sl_params(trial))
        params.update(sample_strategy_params(trial))

        p = params
        log(f"\n  Trial {trial.number:>3}: "
            f"TPs={p.get('tp1_r_multiple',0):.1f}/{p.get('tp2_r_multiple',0):.1f}/"
            f"{p.get('tp3_r_multiple',0):.1f}/{p.get('tp4_r_multiple',0):.1f}/{p.get('tp5_r_multiple',0):.1f}R  "
            f"Close={p.get('tp1_close_pct',0):.0%}/{p.get('tp2_close_pct',0):.0%}/"
            f"{p.get('tp3_close_pct',0):.0%}/{p.get('tp4_close_pct',0):.0%}/{p.get('tp5_close_pct',0):.0%}")
        log(f"         SL@TP1={p.get('sl_after_tp1_r',0):.2f}R  SL@TP2={p.get('sl_after_tp2_r',0):.2f}R  "
            f"SL@TP3={p.get('sl_after_tp3_r',0):.2f}R  SL@TP4={p.get('sl_after_tp4_r',0):.2f}R  "
            f"SL@TP5={p.get('sl_after_tp5_r',0):.2f}R")
        log(f"         Risk={p.get('risk_per_trade_pct',0):.2f}%  Confl={p.get('min_confluence',0)}  "
            f"QF={p.get('min_quality_factors',0)}  ADX-T={p.get('adx_trend_threshold',0):.0f}  "
            f"ADX-R={p.get('adx_range_threshold',0):.0f}  Fib={p.get('entry_fib_level',0):.3f}  "
            f"Offset={p.get('entry_limit_offset_atr',0):.2f}  Compound={p.get('compound_threshold_pct',0):.1f}%")

        r = run_backtest(params, log)

        trial.set_user_attr("net_return_pct",  r.net_return_pct)
        trial.set_user_attr("total_trades",    r.total_trades)
        trial.set_user_attr("win_rate",        r.win_rate)
        trial.set_user_attr("max_tdd_pct",     r.max_tdd_pct)
        trial.set_user_attr("max_ddd_pct",     r.max_ddd_pct)
        trial.set_user_attr("ddd_halts",       r.ddd_halts)
        trial.set_user_attr("final_balance",   r.final_balance)
        trial.set_user_attr("safety_events",   r.safety_events)
        trial.set_user_attr("tdd_warnings",    r.tdd_warnings)
        trial.set_user_attr("valid",           r.valid)
        trial.set_user_attr("monthly_stats",   r.monthly_stats or {})

        log(f"         => Return={r.net_return_pct:+.1f}%  Trades={r.total_trades}  WR={r.win_rate:.1f}%  "
            f"TDD={r.max_tdd_pct:.2f}%  DDD={r.max_ddd_pct:.2f}%  Halts={r.ddd_halts}  Valid={r.valid}")

        # ── Scoring ───────────────────────────────────────────────────────────
        if not r.valid:
            return -1000 - r.max_ddd_pct * 10
        if r.max_ddd_pct >= 5.0:
            return -500 - r.max_ddd_pct * 20
        if r.total_trades < 10:
            return -500 + r.total_trades

        wr = r.win_rate / 100.0
        wr_mult = 0.5 + (wr * 1.5) if wr >= 0.5 else wr
        trade_bonus = min(r.total_trades / 5, 20)
        score = r.net_return_pct * wr_mult + trade_bonus

        if r.max_tdd_pct > 5.0:
            score -= (r.max_tdd_pct - 5.0) * 15
        if r.ddd_halts == 0 and r.max_ddd_pct < 2.5:
            score += 10

        return score

    return objective


# ═══════════════════════════════════════════════════════════════════════════════
# TIME-BASED PROGRESS CALLBACK
# ═══════════════════════════════════════════════════════════════════════════════

def make_timed_callback(interval_s: int, log):
    """Returns a callback that prints a progress update every `interval_s` seconds."""
    state = {"last_update": time.time()}

    def callback(study: optuna.Study, trial: optuna.Trial):
        now = time.time()
        if now - state["last_update"] < interval_s:
            return
        state["last_update"] = now

        done = len(study.trials)
        valid_trials = [t for t in study.trials
                        if t.value is not None and t.user_attrs.get("valid", False)]
        best = study.best_trial if study.best_value is not None else None

        log("\n" + "─" * 70)
        log(f"  UPDATE  –  {done} trials voltooid  ({len(valid_trials)} valid)  –  "
            f"{datetime.now().strftime('%H:%M:%S')}")
        log("─" * 70)

        if best:
            ba = best.user_attrs
            bp = best.params
            log(f"  Beste tot nu toe  (trial #{best.number}):")
            log(f"    Score:   {best.value:.2f}")
            log(f"    Return:  {ba.get('net_return_pct', 0):+.1f}%  |  "
                f"Trades: {ba.get('total_trades', 0)}  |  WR: {ba.get('win_rate', 0):.1f}%")
            log(f"    TDD:     {ba.get('max_tdd_pct', 0):.2f}%  |  "
                f"DDD: {ba.get('max_ddd_pct', 0):.2f}%  |  Halts: {ba.get('ddd_halts', 0)}")
            log(f"    TPs:     {bp.get('tp1_r_multiple','?'):.1f}R / {bp.get('tp2_r_multiple','?'):.1f}R / "
                f"{bp.get('tp3_r_multiple','?'):.1f}R / {bp.get('tp4_r_multiple','?'):.1f}R / "
                f"{bp.get('tp5_r_multiple','?'):.1f}R")
            log(f"    Risk:    {bp.get('risk_per_trade_pct','?'):.2f}%  |  "
                f"Confl: {bp.get('min_confluence','?')}  |  "
                f"Fib: {bp.get('entry_fib_level','?'):.3f}")

        if valid_trials:
            top5 = sorted(valid_trials, key=lambda t: t.value, reverse=True)[:5]
            log(f"\n  Top-5 valid trials:")
            log(f"  {'#':>3}  {'Score':>8}  {'Return':>8}  {'Trades':>7}  {'WR%':>6}  {'DDD':>6}")
            log("  " + "-" * 48)
            for t in top5:
                ua = t.user_attrs
                log(f"  {t.number:>3}  {t.value:>8.1f}  {ua.get('net_return_pct',0):>+7.1f}%  "
                    f"{ua.get('total_trades',0):>7}  {ua.get('win_rate',0):>5.1f}%  "
                    f"{ua.get('max_ddd_pct',0):>5.2f}%")
        log("─" * 70)

    return callback


# ═══════════════════════════════════════════════════════════════════════════════
# SEED TRIAL 0 WITH CURRENT PARAMS
# ═══════════════════════════════════════════════════════════════════════════════

def enqueue_current_params(study: optuna.Study, base_params: Dict[str, Any]) -> None:
    enqueue: Dict[str, Any] = {}

    # TP R-multiples
    prev_r = 0.3
    tp_r_vals = []
    for i in range(1, NUM_TPS + 1):
        key = f"tp{i}_r_multiple"
        val = base_params.get(key)
        if val:
            enqueue[key] = val
            tp_r_vals.append(val)
            prev_r = val
        else:
            tp_r_vals.append(prev_r + 0.5)

    # Close percentages: enqueue raw values as weights (range [0.01, 1.0],
    # always within bounds – no scaling needed).
    for i in range(1, NUM_TPS + 1):
        key = f"tp{i}_close_pct"
        if key in base_params:
            enqueue[f"{key}_weight"] = max(0.01, round(base_params[key], 4))

    tp1_r = tp_r_vals[0] if tp_r_vals else 0.6
    tp2_r = tp_r_vals[1] if len(tp_r_vals) > 1 else 1.1
    tp3_r = tp_r_vals[2] if len(tp_r_vals) > 2 else 1.8

    enqueue["sl_after_tp1_r"] = base_params.get("sl_after_tp1_r", 0.05)
    enqueue["sl_after_tp2_r"] = base_params.get("sl_after_tp2_r", tp1_r)
    enqueue["sl_after_tp3_r"] = base_params.get("sl_after_tp3_r", tp1_r)
    enqueue["sl_after_tp4_r"] = base_params.get("sl_after_tp4_r", tp2_r)
    enqueue["sl_after_tp5_r"] = base_params.get("sl_after_tp5_r", tp3_r)

    # Strategy params
    for key in STRATEGY_RANGES:
        if key in base_params:
            enqueue[key] = base_params[key]

    if enqueue:
        study.enqueue_trial(enqueue)


# ═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def print_final_report(study: optuna.Study, base_params: Dict[str, Any],
                       elapsed_sec: float, log) -> Dict[str, Any]:
    best = study.best_trial
    ba   = best.user_attrs
    bp   = best.params

    # Reconstruct normalized close pcts
    weights = [bp.get(f"tp{i}_close_pct_weight", 1.0) for i in range(1, NUM_TPS + 1)]
    total_w = sum(weights) or 1.0
    best_close = {f"tp{i}_close_pct": round(w / total_w, 3) for i, w in enumerate(weights, 1)}

    elapsed_h = int(elapsed_sec // 3600)
    elapsed_m = int((elapsed_sec % 3600) // 60)
    elapsed_s = int(elapsed_sec % 60)

    sep = "═" * 70

    log(f"\n{sep}")
    log("  OPTIMIZATION COMPLETE – FULL REPORT")
    log(f"  Period: {START_DATE}  to  {END_DATE}  |  Balance: ${BALANCE:,.0f}")
    log(f"  Sampler: TPE  |  Trials: {len(study.trials)}  |  "
        f"Runtime: {elapsed_h:02d}:{elapsed_m:02d}:{elapsed_s:02d}")
    log(sep)

    log("\n  BEST TRIAL")
    log(f"  {'Trial #:':<24} {best.number}")
    log(f"  {'Score:':<24} {best.value:.4f}")
    log(f"  {'Net return:':<24} {ba.get('net_return_pct', 0):+.2f}%")
    log(f"  {'Final balance:':<24} ${ba.get('final_balance', BALANCE):>12,.2f}")
    log(f"  {'Total trades:':<24} {ba.get('total_trades', 0)}")
    log(f"  {'Win rate:':<24} {ba.get('win_rate', 0):.2f}%")
    log(f"  {'Max TDD:':<24} {ba.get('max_tdd_pct', 0):.4f}%  (limit: 10%)")
    log(f"  {'Max DDD:':<24} {ba.get('max_ddd_pct', 0):.4f}%  (limit: 5%)")
    log(f"  {'DDD halts:':<24} {ba.get('ddd_halts', 0)}")
    log(f"  {'5ers-compliant:':<24} {'YES' if ba.get('valid', False) else 'NO'}")

    log(f"\n  BEST TP/SL PARAMETERS")
    log(f"  TP R-multiples:")
    for i in range(1, NUM_TPS + 1):
        log(f"    tp{i}_r_multiple:    {bp.get(f'tp{i}_r_multiple', '?'):.2f}R")
    log(f"  Close percentages:")
    for i in range(1, NUM_TPS + 1):
        log(f"    tp{i}_close_pct:     {best_close.get(f'tp{i}_close_pct', '?'):.1%}")
    log(f"  SL after each TP:")
    for k in ["sl_after_tp1_r", "sl_after_tp2_r", "sl_after_tp3_r", "sl_after_tp4_r", "sl_after_tp5_r"]:
        log(f"    {k:<24} {bp.get(k, '?'):.2f}R")

    log(f"\n  BEST STRATEGY/RISK PARAMETERS")
    for key in STRATEGY_RANGES:
        val = bp.get(key, '?')
        if isinstance(val, float):
            log(f"    {key:<26} {val:.4f}")
        else:
            log(f"    {key:<26} {val}")

    # Monthly breakdown
    monthly = ba.get("monthly_stats", {})
    if monthly:
        log(f"\n  MONTHLY BREAKDOWN (best trial)")
        log("  " + "─" * 56)
        log(f"  {'Month':<10} {'Trades':>8} {'Winners':>8} {'WR%':>7} {'PnL':>12}")
        log("  " + "─" * 56)
        total_pnl = 0.0
        for month in sorted(monthly.keys()):
            m = monthly[month]
            trades  = m.get("trades", 0)
            winners = m.get("winners", 0)
            pnl     = m.get("pnl", 0.0)
            wr      = (winners / trades * 100) if trades > 0 else 0
            total_pnl += pnl
            log(f"  {month:<10} {trades:>8} {winners:>8} {wr:>6.1f}%  ${pnl:>10,.2f}")
        log("  " + "─" * 56)
        log(f"  {'Total':<10} {'':>8} {'':>8} {'':>7}  ${total_pnl:>10,.2f}")

    # Top-20 trials
    all_sorted = sorted([t for t in study.trials if t.value is not None],
                        key=lambda t: t.value, reverse=True)
    valid_trials = [t for t in study.trials if t.value is not None
                    and t.user_attrs.get("valid", False)]

    log(f"\n  TOP-20 TRIALS (of {len(study.trials)} total)")
    log("  " + "─" * 72)
    log(f"  {'#':>3}  {'Score':>8}  {'Return':>8}  {'Balance':>12}  "
        f"{'Trades':>7}  {'WR%':>6}  {'TDD':>6}  {'DDD':>6}  {'V':>3}")
    log("  " + "─" * 72)
    for t in all_sorted[:20]:
        ua = t.user_attrs
        bal_str = f"${ua.get('final_balance', 0):>9,.0f}"
        log(f"  {t.number:>3}  {t.value:>8.2f}  "
            f"{ua.get('net_return_pct',0):>+7.1f}%  {bal_str}  "
            f"{ua.get('total_trades',0):>7}  {ua.get('win_rate',0):>5.1f}%  "
            f"{ua.get('max_tdd_pct',0):>5.2f}%  {ua.get('max_ddd_pct',0):>5.2f}%  "
            f"{'Y' if ua.get('valid', False) else 'N':>3}")
    log("  " + "─" * 72)

    log(f"\n  STATISTICS")
    log(f"  Total trials:          {len(study.trials)}")
    log(f"  Valid (TDD<10, DDD<5): {len(valid_trials)}")
    log(f"  Invalid:               {len(study.trials) - len(valid_trials)}")
    if valid_trials:
        returns = [t.user_attrs.get("net_return_pct", 0) for t in valid_trials]
        log(f"  Valid – Avg return:    {sum(returns)/len(returns):+.2f}%")
        log(f"  Valid – Max return:    {max(returns):+.2f}%")
        log(f"  Valid – Min return:    {min(returns):+.2f}%")

    log(f"\n{sep}")
    log("  NEXT STEP")
    log(sep)
    log("  Apply best parameters to current_params.json:")
    log(f"    python backtest/optimize_2015_2025_full.py --apply <results_file>")
    log(sep)

    # Save JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {
        "optimizer_version":  "optimize_2015_2025_full.py",
        "timestamp":          datetime.now().isoformat(),
        "period":             {"start": START_DATE, "end": END_DATE},
        "balance":            BALANCE,
        "elapsed_seconds":    round(elapsed_sec, 1),
        "total_trials":       len(study.trials),
        "valid_trials":       len(valid_trials),
        "best_trial": {
            "number":     best.number,
            "score":      best.value,
            "metrics":    {k: v for k, v in ba.items() if k != "monthly_stats"},
            "monthly":    monthly,
            "parameters": {
                **{f"tp{i}_r_multiple": bp.get(f"tp{i}_r_multiple") for i in range(1, NUM_TPS + 1)},
                **best_close,
                **{k: bp.get(k) for k in ["sl_after_tp1_r", "sl_after_tp2_r", "sl_after_tp3_r",
                                           "sl_after_tp4_r", "sl_after_tp5_r"]},
                **{k: bp.get(k) for k in STRATEGY_RANGES},
            },
        },
        "all_trials": [
            {
                "trial":   t.number,
                "score":   t.value,
                "params":  t.params,
                "metrics": {k: v for k, v in t.user_attrs.items() if k != "monthly_stats"},
            }
            for t in study.trials if t.value is not None
        ],
    }

    rfile = OUTPUT_DIR / f"optimization_{ts}.json"
    with open(rfile, "w") as f:
        json.dump(results, f, indent=2)

    log(f"\n  Results saved: {rfile}")
    log(f"  Log saved:     {LOG_FILE}")
    log(sep + "\n")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# APPLY PARAMS
# ═══════════════════════════════════════════════════════════════════════════════

def apply_params(results_file: str, log):
    from params.params_loader import load_params_dict

    with open(results_file, 'r') as f:
        results = json.load(f)

    best_params_raw = results.get('best_trial', {}).get('parameters', {})

    current = load_params_dict()
    if 'parameters' in current:
        current['parameters'].update(best_params_raw)
    else:
        current.update(best_params_raw)

    current['optimization_mode'] = "OPTIMIZER_2015_2025_FULL"
    current['timestamp'] = datetime.now().isoformat()
    current['best_score'] = results.get('best_trial', {}).get('score', 0)
    current['optimization_period'] = f"{START_DATE} to {END_DATE}"

    params_file = Path(__file__).parent.parent / "params" / "current_params.json"
    with open(params_file, 'w') as f:
        json.dump(current, f, indent=2)

    log(f"✅ Applied best parameters to {params_file}")
    log("\nApplied parameters:")
    for key, value in sorted(best_params_raw.items()):
        if isinstance(value, float):
            log(f"  {key}: {value:.4f}")
        else:
            log(f"  {key}: {value}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Full Parameter Optimizer – Jan 2015 to May 2025")
    parser.add_argument("--trials",         type=int,   default=100,
                        help="Number of optimization trials (default: 100)")
    parser.add_argument("--parallel", "-j", type=int,   default=4,
                        help="Number of parallel workers (default: 4)")
    parser.add_argument("--startup-trials", type=int,   default=25,
                        help="Random exploration trials before TPE starts (default: 25)")
    parser.add_argument("--update-every",   type=int,   default=60,
                        help="Progress update interval in seconds (default: 60)")
    parser.add_argument("--sampler",        type=str,   default="tpe",
                        choices=["tpe", "nsga"],
                        help="Optuna sampler (default: tpe)")
    parser.add_argument("--apply",          type=str,   default=None,
                        help="Apply parameters from a results JSON file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _log = Logger(LOG_FILE)

    if args.apply:
        apply_params(args.apply, _log)
        _log.close()
        return

    base_params = load_base_params()

    _log(f"\n{'═'*70}")
    _log("  FULL PARAMETER OPTIMIZER  –  Jan 2015 to May 2025")
    _log(f"{'═'*70}")
    _log(f"  Period:            {START_DATE}  →  {END_DATE}")
    _log(f"  Start balance:     ${BALANCE:,.0f}")
    _log(f"  Trials:            {args.trials}")
    _log(f"  Parallel workers:  {args.parallel}")
    _log(f"  Startup trials:    {args.startup_trials}")
    _log(f"  Update interval:   every {args.update_every}s")
    _log(f"  Timeout:           NONE  (runs until all trials complete)")
    _log(f"  Sampler:           {args.sampler.upper()}")
    _log(f"  Output dir:        {OUTPUT_DIR}")
    _log(f"  Log:               {LOG_FILE}")
    _log(f"{'─'*70}")
    _log(f"  Baseline TPs:     {' / '.join(str(base_params.get(f'tp{i}_r_multiple', '?')) for i in range(1, 6))}")
    _log(f"  Baseline Close%:  {' / '.join(str(base_params.get(f'tp{i}_close_pct', '?')) for i in range(1, 6))}")
    _log(f"  Baseline risk:    {base_params.get('risk_per_trade_pct', '?')}%")
    _log(f"  Baseline confl:   {base_params.get('min_confluence', '?')}  QF: {base_params.get('min_quality_factors', '?')}")
    _log(f"  Baseline ADX:     T={base_params.get('adx_trend_threshold', '?')}  R={base_params.get('adx_range_threshold', '?')}")
    _log(f"  Baseline fib:     {base_params.get('entry_fib_level', '?')}  offset: {base_params.get('entry_limit_offset_atr', '?')}")
    _log(f"  Baseline compound:{base_params.get('compound_threshold_pct', '?')}%")
    _log(f"{'═'*70}\n")

    if args.sampler == "nsga":
        sampler = NSGAIISampler(seed=42)
    else:
        sampler = TPESampler(seed=42, n_startup_trials=args.startup_trials)

    study = optuna.create_study(
        direction="maximize",
        sampler=sampler,
        study_name=f"full_2015_2025_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    enqueue_current_params(study, base_params)

    start_time = datetime.now()

    study.optimize(
        make_objective(base_params, _log),
        n_trials=args.trials,
        n_jobs=args.parallel,
        timeout=None,
        show_progress_bar=False,
        catch=(Exception,),
        callbacks=[make_timed_callback(args.update_every, _log)],
    )

    elapsed = (datetime.now() - start_time).total_seconds()
    print_final_report(study, base_params, elapsed, _log)
    _log.close()


if __name__ == "__main__":
    main()
