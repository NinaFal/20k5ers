#!/usr/bin/env python3
"""
TP / Close% / SL Optimizer – Januari 2016 t/m Mei 2016
=======================================================

Optimaliseert ALLEEN:
  - TP1..TP5  R-multiples        (waar neem je partials)
  - TP1..TP5  close-percentages  (hoeveel % sluit je per TP)
  - SL na TP2 / TP3 / TP4 / TP5 (trailing stop levels)

Hardcoded (niet geoptimaliseerd):
  - SL na TP1 = 0.05R  (breakeven + fees)
  - Alle andere params komen uit current_params.json

Features:
  - Geen timeout  (loopt totdat alle trials klaar zijn)
  - Periodieke updates  elke UPDATE_INTERVAL trials
  - Volledig eindrapport  na afloop
  - Resultaten opgeslagen in backtest/optimization_results/

Usage (direct):
    python backtest/optimize_2016_jan_may.py [--trials 100] [--parallel 4]

Launch via setsid (aanbevolen):
    bash run_optimizer_2016.sh
"""

import sys
import os
import json
import argparse
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    import optuna
    from optuna.samplers import TPESampler
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    print("ERROR: optuna niet geïnstalleerd. Run: pip install optuna")
    sys.exit(1)

# ── Constants ─────────────────────────────────────────────────────────────────
START_DATE      = "2016-01-01"
END_DATE        = "2016-05-31"
BALANCE         = 20_000.0
NUM_TPS         = 5
SAMPLER         = "tpe"
UPDATE_INTERVAL = 5          # print update every N trials
STARTUP_TRIALS  = 15         # random exploration trials before TPE

OUTPUT_DIR = ROOT / "backtest" / "optimization_results" / "2016_jan_may"
LOG_FILE   = ROOT / "backtest" / "optimization_results" / "2016_jan_may" / "optimizer.log"

# ── Parameter search ranges ───────────────────────────────────────────────────
TP_R_RANGES = {
    "tp1_r_multiple": (0.3, 1.2),
    "tp2_r_multiple": (0.8, 2.6),
    "tp3_r_multiple": (1.2, 3.2),
    "tp4_r_multiple": (1.6, 4.2),
    "tp5_r_multiple": (2.2, 6.0),
}

TP_CLOSE_RANGES = {
    "tp1_close_pct": (0.05, 0.45),
    "tp2_close_pct": (0.10, 0.70),
    "tp3_close_pct": (0.05, 0.45),
    "tp4_close_pct": (0.03, 0.30),
    "tp5_close_pct": (0.03, 0.25),
}


# ─────────────────────────────────────────────────────────────────────────────
# Logging helper  (schrijft naar console EN logfile tegelijk)
# ─────────────────────────────────────────────────────────────────────────────
class Tee:
    """Write to both stdout and a log file."""
    def __init__(self, log_path: Path):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_path, "a", buffering=1)

    def print(self, *args, **kwargs):
        msg = " ".join(str(a) for a in args)
        print(msg, **kwargs)
        self._log.write(msg + "\n")
        self._log.flush()

    def close(self):
        self._log.close()


tee = Tee(LOG_FILE)
log = tee.print  # shorthand


# ─────────────────────────────────────────────────────────────────────────────
# Params helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_base_params() -> Dict[str, Any]:
    from params.params_loader import load_params_dict
    raw = load_params_dict()
    return raw.get("parameters", raw)


def create_temp_params(params: Dict[str, Any]) -> Path:
    tmp_dir = Path(tempfile.gettempdir()) / "opt2016_params"
    tmp_dir.mkdir(exist_ok=True)
    path = tmp_dir / f"p_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    with open(path, "w") as f:
        json.dump({"optimization_mode": "OPTIMIZER_2016", "timestamp": datetime.now().isoformat(),
                   "parameters": params}, f, indent=2)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Backtest runner
# ─────────────────────────────────────────────────────────────────────────────
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


def run_backtest(params: Dict[str, Any]) -> BTResult:
    import subprocess

    tmp_params = create_temp_params(params)
    out_dir = Path(tempfile.gettempdir()) / "opt2016_results" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            sys.executable,
            str(ROOT / "backtest" / "src" / "main_live_bot_backtest.py"),
            "--start", START_DATE,
            "--end",   END_DATE,
            "--balance", str(BALANCE),
            "--output", str(out_dir),
            "--params-file", str(tmp_params),
            "--quiet",
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(ROOT))

        rf = out_dir / "results.json"
        if rf.exists():
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
        log(f"  [BACKTEST ERROR] {e}")
    finally:
        if tmp_params.exists():
            tmp_params.unlink()

    return BTResult(params=params, net_return_pct=-100, total_trades=0, win_rate=0,
                    max_tdd_pct=100, max_ddd_pct=100, final_balance=BALANCE,
                    ddd_halts=0, safety_events=0, tdd_warnings=0, valid=False, monthly_stats={})


# ─────────────────────────────────────────────────────────────────────────────
# Trial parameter sampler
# ─────────────────────────────────────────────────────────────────────────────
def sample_tp_sl_params(trial: optuna.Trial) -> Dict[str, Any]:
    params: Dict[str, Any] = {}

    # TP R-multiples (strict ascending)
    prev_r = 0.3
    tp_r = []
    for i in range(1, NUM_TPS + 1):
        key = f"tp{i}_r_multiple"
        lo, hi = TP_R_RANGES.get(key, (prev_r + 0.3, prev_r + 2.0))
        lo = max(lo, prev_r + 0.1)
        r_val = trial.suggest_float(key, lo, hi, step=0.1)
        params[key] = r_val
        tp_r.append(r_val)
        prev_r = r_val

    tp1_r, tp2_r, tp3_r, tp4_r, tp5_r = tp_r[0], tp_r[1], tp_r[2], tp_r[3], tp_r[4]

    # Close percentages as weights, then normalize to sum=1.0
    weights = []
    for i in range(1, NUM_TPS + 1):
        key = f"tp{i}_close_pct"
        lo, hi = TP_CLOSE_RANGES.get(key, (0.05, 0.40))
        w = trial.suggest_float(f"{key}_weight", lo, hi, step=0.05)
        weights.append(w)
    total = sum(weights)
    for i, w in enumerate(weights, 1):
        params[f"tp{i}_close_pct"] = round(w / total, 3)

    # SL levels after each TP (independent, within logical bounds)
    def sl_range(lo, hi):
        if hi - lo < 0.1:
            hi = lo + 0.1
        return lo, hi

    params["sl_after_tp2_r"] = trial.suggest_float("sl_after_tp2_r", *sl_range(tp1_r, tp2_r), step=0.05)
    params["sl_after_tp3_r"] = trial.suggest_float("sl_after_tp3_r", *sl_range(tp1_r, tp3_r), step=0.05)
    params["sl_after_tp4_r"] = trial.suggest_float("sl_after_tp4_r", *sl_range(tp2_r, tp4_r), step=0.05)
    params["sl_after_tp5_r"] = trial.suggest_float("sl_after_tp5_r", *sl_range(tp3_r, tp5_r), step=0.05)

    return params


# ─────────────────────────────────────────────────────────────────────────────
# Objective
# ─────────────────────────────────────────────────────────────────────────────
def objective(trial: optuna.Trial, base_params: Dict[str, Any]) -> float:
    params = dict(base_params)
    params.update(sample_tp_sl_params(trial))

    p = params
    log(f"\n  Trial {trial.number:>3}: "
        f"TPs={p.get('tp1_r_multiple',0):.1f}/{p.get('tp2_r_multiple',0):.1f}/"
        f"{p.get('tp3_r_multiple',0):.1f}/{p.get('tp4_r_multiple',0):.1f}/{p.get('tp5_r_multiple',0):.1f}R  "
        f"Close={p.get('tp1_close_pct',0):.0%}/{p.get('tp2_close_pct',0):.0%}/"
        f"{p.get('tp3_close_pct',0):.0%}/{p.get('tp4_close_pct',0):.0%}/{p.get('tp5_close_pct',0):.0%}  "
        f"SL@TP2={p.get('sl_after_tp2_r',0):.2f}R SL@TP3={p.get('sl_after_tp3_r',0):.2f}R "
        f"SL@TP4={p.get('sl_after_tp4_r',0):.2f}R SL@TP5={p.get('sl_after_tp5_r',0):.2f}R")

    r = run_backtest(params)

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

    # Scoring
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


# ─────────────────────────────────────────────────────────────────────────────
# Periodic update callback
# ─────────────────────────────────────────────────────────────────────────────
def make_update_callback(interval: int):
    """Returns an Optuna callback that prints progress every `interval` trials."""
    def callback(study: optuna.Study, trial: optuna.Trial):
        done = len(study.trials)
        if done % interval != 0:
            return

        valid_trials = [t for t in study.trials
                        if t.value is not None and t.user_attrs.get("valid", False)]
        best_so_far = study.best_trial if study.best_value is not None else None

        log("\n" + "─" * 70)
        log(f"  UPDATE  –  {done} trials voltooid  "
            f"({len(valid_trials)} valid)  –  {datetime.now().strftime('%H:%M:%S')}")
        log("─" * 70)
        if best_so_far:
            ba = best_so_far.user_attrs
            log(f"  Beste tot nu toe  (trial #{best_so_far.number}):")
            log(f"    Score:   {best_so_far.value:.2f}")
            log(f"    Return:  {ba.get('net_return_pct', 0):+.1f}%  |  "
                f"Trades: {ba.get('total_trades', 0)}  |  WR: {ba.get('win_rate', 0):.1f}%")
            log(f"    TDD:     {ba.get('max_tdd_pct', 0):.2f}%  |  "
                f"DDD: {ba.get('max_ddd_pct', 0):.2f}%  |  Halts: {ba.get('ddd_halts', 0)}")
            bp = best_so_far.params
            log(f"    TPs:     {bp.get('tp1_r_multiple','?'):.1f}R / {bp.get('tp2_r_multiple','?'):.1f}R / "
                f"{bp.get('tp3_r_multiple','?'):.1f}R / {bp.get('tp4_r_multiple','?'):.1f}R / "
                f"{bp.get('tp5_r_multiple','?'):.1f}R")

        # Top-5 valid trials
        if valid_trials:
            top5 = sorted(valid_trials, key=lambda t: t.value, reverse=True)[:5]
            log(f"\n  Top-5 valid trials:")
            log(f"  {'#':>3}  {'Score':>8}  {'Return':>8}  {'Trades':>7}  {'WR%':>6}  {'DDD':>5}")
            log("  " + "-" * 46)
            for t in top5:
                ua = t.user_attrs
                log(f"  {t.number:>3}  {t.value:>8.1f}  {ua.get('net_return_pct',0):>+7.1f}%  "
                    f"{ua.get('total_trades',0):>7}  {ua.get('win_rate',0):>5.1f}%  "
                    f"{ua.get('max_ddd_pct',0):>5.2f}%")
        log("─" * 70)
    return callback


# ─────────────────────────────────────────────────────────────────────────────
# Final report
# ─────────────────────────────────────────────────────────────────────────────
def print_final_report(study: optuna.Study, base_params: Dict[str, Any],
                        total_trials: int, elapsed_sec: float) -> Dict[str, Any]:
    """Print a comprehensive final report and return results dict."""
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
    log("  OPTIMALISATIE VOLLEDIG RAPPORT")
    log(f"  Periode: {START_DATE}  t/m  {END_DATE}  |  Balance: ${BALANCE:,.0f}")
    log(f"  Sampler: TPE  |  Trials: {len(study.trials)}  |  "
        f"Looptijd: {elapsed_h:02d}:{elapsed_m:02d}:{elapsed_s:02d}")
    log(f"  Gestart: {datetime.fromtimestamp(study.trials[0].datetime_start.timestamp()).strftime('%Y-%m-%d %H:%M')}"
        if study.trials else "")
    log(sep)

    # ── Beste resultaat ──────────────────────────────────────────────────────
    log("\n  BESTE TRIAL")
    log(f"  {'Trial #:':<22} {best.number}")
    log(f"  {'Score:':<22} {best.value:.4f}")
    log(f"  {'Net return:':<22} {ba.get('net_return_pct', 0):+.2f}%")
    log(f"  {'Final balance:':<22} ${ba.get('final_balance', BALANCE):>12,.2f}")
    log(f"  {'Totaal trades:':<22} {ba.get('total_trades', 0)}")
    log(f"  {'Win rate:':<22} {ba.get('win_rate', 0):.2f}%")
    log(f"  {'Max TDD:':<22} {ba.get('max_tdd_pct', 0):.4f}%  (limit: 10%)")
    log(f"  {'Max DDD:':<22} {ba.get('max_ddd_pct', 0):.4f}%  (limit: 5%)")
    log(f"  {'DDD halts:':<22} {ba.get('ddd_halts', 0)}")
    log(f"  {'Safety events:':<22} {ba.get('safety_events', 0)}")
    log(f"  {'5ers-compliant:':<22} {'JA' if ba.get('valid', False) else 'NEE'}")

    # ── Beste TP/SL parameters ───────────────────────────────────────────────
    log(f"\n  BESTE PARAMETERS")
    log(f"  TP R-multiples (waar partial close):")
    for i in range(1, NUM_TPS + 1):
        log(f"    tp{i}_r_multiple:   {bp.get(f'tp{i}_r_multiple', '?'):.2f}R")
    log(f"  Close-percentages (hoeveel % per TP):")
    for i in range(1, NUM_TPS + 1):
        log(f"    tp{i}_close_pct:    {best_close.get(f'tp{i}_close_pct', '?'):.1%}")
    log(f"  SL-levels na elke TP:")
    log(f"    sl_after_tp1_r:    0.05R  (hardcoded – breakeven)")
    for k in ["sl_after_tp2_r", "sl_after_tp3_r", "sl_after_tp4_r", "sl_after_tp5_r"]:
        log(f"    {k:<22} {bp.get(k, '?'):.2f}R")

    # ── Maandelijkse breakdown ────────────────────────────────────────────────
    monthly = ba.get("monthly_stats", {})
    if monthly:
        log(f"\n  MAANDELIJKSE BREAKDOWN (beste trial)")
        log("  " + "─" * 56)
        log(f"  {'Maand':<10} {'Trades':>8} {'Winners':>8} {'WR%':>7} {'PnL':>12}")
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
        log(f"  {'Totaal':<10} {'':>8} {'':>8} {'':>7}  ${total_pnl:>10,.2f}")

    # ── Top-20 trials ──────────────────────────────────────────────────────
    all_sorted = sorted([t for t in study.trials if t.value is not None],
                        key=lambda t: t.value, reverse=True)
    log(f"\n  TOP-20 TRIALS (van {len(study.trials)} totaal)")
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

    # ── Statistieken ──────────────────────────────────────────────────────────
    valid_trials = [t for t in study.trials if t.value is not None
                    and t.user_attrs.get("valid", False)]
    log(f"\n  STATISTIEKEN")
    log(f"  Totaal trials:           {len(study.trials)}")
    log(f"  Valid (TDD<10, DDD<5):   {len(valid_trials)}")
    log(f"  Invalid:                 {len(study.trials) - len(valid_trials)}")
    if valid_trials:
        returns = [t.user_attrs.get("net_return_pct", 0) for t in valid_trials]
        log(f"  Valid – Gem. return:     {sum(returns)/len(returns):+.2f}%")
        log(f"  Valid – Max return:      {max(returns):+.2f}%")
        log(f"  Valid – Min return:      {min(returns):+.2f}%")

    log(f"\n{sep}")
    log("  AANBEVOLEN VERVOLGSTAP")
    log(sep)
    log("  Pas de beste parameters toe op current_params.json:")
    log(f"    python backtest/optimize_main_live_bot.py --apply <results_file>")
    log("  Of voer een forward-test uit op 2016-06 t/m 2016-12:")
    log(f"    python backtest/src/main_live_bot_backtest.py --start 2016-06-01 --end 2016-12-31")
    log(sep)

    # ── JSON results ──────────────────────────────────────────────────────────
    results = {
        "optimizer_version":  "optimize_2016_jan_may.py",
        "timestamp":          datetime.now().isoformat(),
        "period":             {"start": START_DATE, "end": END_DATE},
        "balance":            BALANCE,
        "elapsed_seconds":    round(elapsed_sec, 1),
        "total_trials":       len(study.trials),
        "valid_trials":       len(valid_trials),
        "best_trial": {
            "number":      best.number,
            "score":       best.value,
            "metrics":     {k: v for k, v in ba.items() if k != "monthly_stats"},
            "monthly":     monthly,
            "parameters": {
                **{f"tp{i}_r_multiple": bp.get(f"tp{i}_r_multiple") for i in range(1, NUM_TPS + 1)},
                **best_close,
                "sl_after_tp1_r": 0.05,
                **{k: bp.get(k) for k in ["sl_after_tp2_r", "sl_after_tp3_r", "sl_after_tp4_r", "sl_after_tp5_r"]},
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
        "fixed_params": {k: v for k, v in base_params.items()
                         if not k.startswith("tp") and not k.startswith("sl_after_tp")},
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    rfile = OUTPUT_DIR / f"results_{ts}.json"
    with open(rfile, "w") as f:
        json.dump(results, f, indent=2)

    log(f"\n  Resultaten opgeslagen: {rfile}")
    log(f"  Log opgeslagen:        {LOG_FILE}")
    log(sep + "\n")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Seed trial 0 met huidige params
# ─────────────────────────────────────────────────────────────────────────────
def enqueue_current_params(study: optuna.Study, base_params: Dict[str, Any]) -> None:
    enqueue: Dict[str, Any] = {}
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

    for i in range(1, NUM_TPS + 1):
        key = f"tp{i}_close_pct"
        if key in base_params:
            enqueue[f"{key}_weight"] = base_params[key]

    tp1_r = tp_r_vals[0] if tp_r_vals else 0.6
    tp2_r = tp_r_vals[1] if len(tp_r_vals) > 1 else 1.1
    tp3_r = tp_r_vals[2] if len(tp_r_vals) > 2 else 1.8

    enqueue["sl_after_tp2_r"] = base_params.get("sl_after_tp2_r", tp1_r)
    enqueue["sl_after_tp3_r"] = base_params.get("sl_after_tp3_r", tp1_r)
    enqueue["sl_after_tp4_r"] = base_params.get("sl_after_tp4_r", tp2_r)
    enqueue["sl_after_tp5_r"] = base_params.get("sl_after_tp5_r", tp3_r)

    if enqueue:
        study.enqueue_trial(enqueue)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TP/SL Optimizer – Jan–Mei 2016")
    parser.add_argument("--trials",          type=int, default=100,
                        help="Aantal optimalisatie-trials (default: 100)")
    parser.add_argument("--parallel", "-j",  type=int, default=1,
                        help="Aantal parallelle workers (default: 1)")
    parser.add_argument("--startup-trials",  type=int, default=STARTUP_TRIALS,
                        help=f"Willekeurige verkenningstrials voor TPE (default: {STARTUP_TRIALS})")
    parser.add_argument("--update-interval", type=int, default=UPDATE_INTERVAL,
                        help=f"Update printen elke N trials (default: {UPDATE_INTERVAL})")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_params = load_base_params()

    log(f"\n{'═'*70}")
    log("  TP / CLOSE% / SL OPTIMIZER  –  JANUARI 2016 t/m MEI 2016")
    log(f"{'═'*70}")
    log(f"  Periode:           {START_DATE}  →  {END_DATE}")
    log(f"  Start balance:     ${BALANCE:,.0f}")
    log(f"  Trials:            {args.trials}")
    log(f"  Parallel workers:  {args.parallel}")
    log(f"  Startup trials:    {args.startup_trials}")
    log(f"  Update interval:   elke {args.update_interval} trials")
    log(f"  Timeout:           GEEN  (loopt tot alle trials klaar zijn)")
    log(f"  Sampler:           TPE (Tree-structured Parzen Estimator)")
    log(f"  Output dir:        {OUTPUT_DIR}")
    log(f"  Log:               {LOG_FILE}")
    log(f"{'─'*70}")

    # Huidig baseline
    current_tps   = [base_params.get(f"tp{i}_r_multiple", "?") for i in range(1, 6)]
    current_close = [base_params.get(f"tp{i}_close_pct",  "?") for i in range(1, 6)]
    log(f"  Baseline TPs:     {' / '.join(str(r) for r in current_tps)}")
    log(f"  Baseline Close%:  {' / '.join(str(c) for c in current_close)}")
    log(f"{'═'*70}\n")

    sampler = TPESampler(seed=42, n_startup_trials=args.startup_trials)
    study   = optuna.create_study(
        direction="maximize",
        sampler=sampler,
        study_name=f"tp_sl_2016_jan_may_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    # Trial 0 = huidige params als startpunt
    enqueue_current_params(study, base_params)

    start_time = datetime.now()
    callback   = make_update_callback(args.update_interval)

    log(f"  Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("  Optimalisatie gestart...\n")

    # Geen timeout → timeout=None
    study.optimize(
        lambda trial: objective(trial, base_params),
        n_trials=args.trials,
        n_jobs=args.parallel,
        timeout=None,           # <── GEEN tijdslimiet
        show_progress_bar=False,
        catch=(Exception,),
        callbacks=[callback],
    )

    elapsed = (datetime.now() - start_time).total_seconds()
    print_final_report(study, base_params, args.trials, elapsed)
    tee.close()


if __name__ == "__main__":
    main()
