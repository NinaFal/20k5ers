#!/usr/bin/env python3
"""
DoE harness — shared infrastructure for the phased sweep program.

All stages import this. It provides:
  run_single       — invoke one backtest subprocess, return raw dict
  run_multistart   — run on a list of starts, optional early-exit on breach
  extract_attrs    — flatten result dict to clean scalars
  maximin_score    — hard breach floor + worst-start net P&L (the objective)
  late_monthly_avg — avg monthly P&L in the final 2 years of a run
  validate_top5    — run top-N configs on test starts + full 10yr, write report
  print_table      — formatted results table

Scoring philosophy (Maximin-robust):
  • ANY breach on ANY start → score = -1e9 + survived_days*100 (gradient only)
  • All survived → score = min(net_pnl) across all starts (worst-case profit)
  This prevents any breach-survivor from ever beating a zero-breach config,
  and among survivors naturally targets robust $1-2M instead of fragile $4M.

Start date sets:
  TRAIN (5): 2016, 2017, 2019-07, 2020, 2022  — used for sweep scoring
  TEST  (5): 2015-02, 2018, 2021, 2023-01, 2023-07 — out-of-sample validation
  FULL  (1): 2015-01-01 → 2024-12-31           — full truth gate
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE  = Path(__file__).resolve().parent
REPO  = HERE.parent.parent
BACKTEST = HERE / "main_live_bot_backtest.py"

# Stable output dir for all DoE artifacts (not /tmp — it gets wiped)
DOE_DIR = REPO / "backtest" / "output" / "doe"
DOE_DIR.mkdir(parents=True, exist_ok=True)
(DOE_DIR / "tmp").mkdir(exist_ok=True)

END           = "2024-12-31"
FULL_START    = "2015-01-01"
RUN_TIMEOUT_S = int(os.getenv("RUN_TIMEOUT_S", "2400"))  # 40 min max per run

# 5 regime-spanning train starts  (these drive sweep scoring)
TRAIN_STARTS = [
    "2016-01-01",   # choppy + leads into 2017 bleed risk
    "2017-01-01",   # confirmed calm-bleed killer
    "2020-01-01",   # COVID crash
    "2022-01-01",   # rate shock / daily-gap event
    "2019-07-01",   # mid-cycle baseline
]

# Worst-first subset used for cheap early-exit inside Optuna trials
KILLER_STARTS = ["2016-01-01", "2017-01-01", "2022-01-01"]

# 5 out-of-sample test starts  (never seen during sweeps)
TEST_STARTS = [
    "2015-02-01",   # post-SNB (avoids Jan 15 black-swan date)
    "2018-01-01",   # USD strength year
    "2021-01-01",   # post-COVID bull run
    "2023-01-01",   # recent normalisation
    "2023-07-01",   # second half 2023
]

# ── Locked best config from the previous session ─────────────────────────────
# These are the SETTLED levers — we don't re-sweep them in Stage 1.
# Stage 2 will re-examine them on the improved pipeline.
BASE_ENV = {
    "TERMINAL_ON_BREACH":    "1",
    "SLIPPAGE_PIPS":         "0.5",
    "GAP_FILLS":             "1",
    "TDD_EMERGENCY_HALT":    "0",
    "DDD_CLOSE_AT_TRIGGER":  "1",
    "VOL_SIZE_ENABLE":       "1",
    "VOL_SIZE_MULT_LOW":     "1.7",
    "VOL_SIZE_MULT_HIGH":    "0.6",
    "VOL_REGIME_DD_OFF":     "3.0",
    "VOL_REGIME_DD_MULT":    "1.0",
    "FIVEERS_MAX_SCALE":     "400000",
    "CFG_MAX_CUM_RISK":      "3.5",
    "CFG_DAILY_HALT_PCT":    "2.5",
    "CFG_TDD_CAUTION_PCT":   "5.5",
    "CFG_RISK_CAUTIOUS":     "0.45",
    "CFG_TDD_WARNING_PCT":   "7.5",
    "CFG_RISK_CONSERVATIVE": "0.25",
    "CFG_TDD_EMERGENCY_PCT": "8.5",
    "CFG_RISK_ULTRASAFE":    "0.25",
    "TDD_WALL_SAFETY":       "4.5",
}

# NEWTP — best profit ladder found in the previous session
BASE_TP = {
    "tp1_r_multiple": 0.9,  "tp2_r_multiple": 1.7,  "tp3_r_multiple": 2.4,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.7,
    "tp1_close_pct":  0.10, "tp2_close_pct":  0.35, "tp3_close_pct": 0.15,
    "tp4_close_pct":  0.10, "tp5_close_pct":  0.30,
    "sl_after_tp2_r": 0.7,  "sl_after_tp3_r": 1.6,  "sl_after_tp4_r": 2.0,
}


# ── Core runner ───────────────────────────────────────────────────────────────

def run_single(env_over: dict, tp_over: dict, start: str,
               end: str = END, balance: str = "50000") -> dict | None:
    """
    Run one backtest. Returns raw results dict or None on crash/timeout.
    env_over  — env-var overrides (on top of BASE_ENV)
    tp_over   — OPT_PARAMS overrides (merged into BASE_TP)
    """
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    env = dict(os.environ)
    env.update(BASE_ENV)
    env.update(env_over)
    env["OPT_PARAMS"] = json.dumps({**BASE_TP, **tp_over})
    cmd = [sys.executable, str(BACKTEST),
           "--start", start, "--end", end,
           "--balance", balance, "--output", td, "--quiet"]
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                           cwd=str(REPO), timeout=RUN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None
    rj = Path(td) / "results.json"
    if p.returncode != 0 or not rj.exists():
        return None
    return json.loads(rj.read_text())


def extract_attrs(r: dict | None) -> dict:
    """Flatten result dict to clean scalar attrs."""
    if r is None:
        return {"failed": True, "net": 0, "max_tdd": 0, "max_ddd": 0,
                "win_rate": 0, "trades": 0, "survived_days": 0,
                "final_funded": 0, "scalings": 0, "withdrawn": 0,
                "breach_type": "timeout"}
    fi = r.get("fail_info") or {}
    return {
        "failed":        bool(r.get("account_failed")),
        "net":           round(float(r.get("net_pnl") or 0)),
        "max_tdd":       float(r.get("max_tdd_pct") or 0),
        "max_ddd":       float(r.get("max_ddd_pct") or 0),
        "win_rate":      float(r.get("win_rate") or 0),
        "trades":        int(r.get("total_trades") or 0),
        "survived_days": int(fi.get("survived_days") or 0),
        "final_funded":  r.get("fiveers_final_funded_level") or 0,
        "scalings":      int(r.get("fiveers_scaling_events") or 0),
        "withdrawn":     round(float(r.get("fiveers_total_withdrawn") or 0)),
        "breach_type":   fi.get("breach_type") or "",
    }


def maximin_score(runs: dict) -> float:
    """
    Hard breach floor (any start fails → negative) then min(net_pnl).
    runs: {start_str: result_dict_or_None}
    """
    nets = []
    for start, r in runs.items():
        a = extract_attrs(r)
        if a["failed"]:
            return -1e9 + float(a["survived_days"]) * 100
        nets.append(a["net"])
    return float(min(nets)) if nets else -2e9


def late_monthly_avg(r: dict | None) -> float:
    """
    Average monthly P&L over the final 24 months of the run.
    Proxy for whether the account has reached meaningful scale.
    """
    if not r:
        return 0.0
    monthly = r.get("monthly_stats") or {}
    months = sorted(monthly.keys())
    tail = months[-24:] if len(months) >= 24 else months
    if not tail:
        return 0.0
    return sum(monthly[m]["pnl"] for m in tail) / len(tail)


# ── Multi-start runner ────────────────────────────────────────────────────────

def run_multistart(env_over: dict, tp_over: dict, starts: list,
                   end: str = END, max_workers: int = 2,
                   early_exit: bool = False) -> dict:
    """
    Run on multiple starts. Returns {start: result}.
    early_exit=True: runs sequentially, aborts after first breach.
    early_exit=False: runs all starts in parallel (max_workers processes).
    """
    if early_exit:
        results = {}
        for s in starts:
            r = run_single(env_over, tp_over, s, end)
            results[s] = r
            if (r is None) or r.get("account_failed"):
                break
        return results
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(run_single, env_over, tp_over, s, end): s
                       for s in starts}
            return {futures[f]: f.result()
                    for f in concurrent.futures.as_completed(futures)}


# ── Reporting ─────────────────────────────────────────────────────────────────

def _row(label, a):
    status = "BREACH" if a["failed"] else "OK"
    return (f"  {label:<14} {status:<7} net={a['net']:>10,}  "
            f"tdd={a['max_tdd']:>5.2f}%  ddd={a['max_ddd']:>5.2f}%  "
            f"wr={a['win_rate']:>5.1f}%  trades={a['trades']:>4}  "
            f"funded={a['final_funded']:>8,}")


def print_run_table(label: str, runs: dict):
    score = maximin_score(runs)
    print(f"\n{'='*78}")
    print(f"  {label}   maximin_score={score:,.0f}")
    print(f"{'='*78}")
    for start, r in sorted(runs.items()):
        print(_row(start, extract_attrs(r)))


# ── Top-N validation (train survivors → test starts + full 10yr) ──────────────

def validate_configs(configs: list, tag: str = "validation",
                     max_workers: int = 2) -> list:
    """
    configs: list of {"env": {...}, "tp": {...}, "label": "..."}
    Runs each on TEST_STARTS + full 10yr. Returns enriched list with results.
    Writes a report to DOE_DIR/<tag>_report.txt.
    """
    (DOE_DIR / "tmp").mkdir(exist_ok=True)
    out = []
    lines = [f"Validation report: {tag}\n{'='*78}\n"]
    for cfg in configs:
        label = cfg.get("label", "?")
        env, tp = cfg["env"], cfg["tp"]
        lines.append(f"\n{'─'*60}\n  Config: {label}\n{'─'*60}")
        all_runs = {}

        # Test starts (out-of-sample)
        for s in TEST_STARTS:
            r = run_single(env, tp, s)
            all_runs[f"test:{s}"] = r
            a = extract_attrs(r)
            lines.append(_row(f"test:{s}", a))

        # Full 10yr
        r = run_single(env, tp, FULL_START)
        all_runs[f"full:{FULL_START}"] = r
        a = extract_attrs(r)
        lines.append(_row(f"full:{FULL_START}", a))
        lma = late_monthly_avg(r)
        lines.append(f"    late_monthly_avg={lma:,.0f}")

        cfg["validation"] = all_runs
        cfg["full_result"] = r
        cfg["late_monthly_avg"] = lma
        out.append(cfg)

    report = "\n".join(lines)
    print(report)
    (DOE_DIR / f"{tag}_report.txt").write_text(report)
    return out
