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
import time
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

# ── MEMORY-SAFE CONCURRENCY (hard-won; see SESSION_HANDOFF §6) ────────────────
# A FULL-PATH run (start → 2024) holds ~4.6GB RSS. A SHORT 3-year window holds
# ~1.5GB. On a 16GB box that means:
#   • full-path (Stage 2 / validation):  MAX 2 concurrent  (2×4.6 = 9.2GB)
#   • short-window (Stage 1 screening):  4 concurrent OK   (4×1.5 = 6GB)
# Exceeding these triggers the OOM killer, which silently corrupts results
# (killed runs look like instant breaches). NEVER raise these without re-measuring.
WORKERS_FULL  = int(os.getenv("DOE_WORKERS_FULL", "2"))
WORKERS_SHORT = int(os.getenv("DOE_WORKERS_SHORT", "4"))

# 5 regime-spanning train starts  (these drive sweep scoring)
TRAIN_STARTS = [
    "2016-01-01",   # choppy + leads into 2017 bleed risk
    "2017-01-01",   # confirmed calm-bleed killer
    "2020-01-01",   # COVID crash
    "2022-01-01",   # rate shock / daily-gap event
    "2019-07-01",   # mid-cycle baseline
]

# Stage 1 ENTRY-PRICING windows: 3-year multi-regime slices (start, end).
# Short on purpose — entry pricing is judged on per-regime efficiency, NOT on
# surviving the full ratcheting-floor compounding path (that is Stage 2's job,
# and requires the safety levers we hold fixed here). Short runs are also
# memory-light → 4 workers, ~4× faster, and never OOM.
STAGE1_WINDOWS = [
    ("2016-01-01", "2018-12-31"),   # choppy / 2017 calm-bleed
    ("2017-01-01", "2019-12-31"),   # calm-bleed into recovery
    ("2019-07-01", "2022-06-30"),   # mid-cycle → COVID → early shock
    ("2020-01-01", "2022-12-31"),   # COVID crash + 2022 rate shock
    ("2022-01-01", "2024-12-31"),   # rate-shock + recent normalisation
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
               end: str = END, balance: str = "50000",
               retries: int = 2) -> dict | None:
    """
    Run one backtest. Returns raw results dict, or None after all retries.

    A None result means an INFRA failure (OOM kill / timeout / crash), NOT a
    strategy breach — a real breach returns a dict with account_failed=True.
    We retry None up to `retries` times with a short back-off, because the most
    common cause here is transient memory pressure from sibling runs. Callers
    MUST treat a final None as "incomplete / unknown", never as a breach.
    """
    last_clean = None
    for attempt in range(retries + 1):
        td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
        env = dict(os.environ)
        env.update(BASE_ENV)
        env.update(env_over)
        env["OPT_PARAMS"] = json.dumps({**BASE_TP, **tp_over})
        cmd = [sys.executable, str(BACKTEST),
               "--start", start, "--end", end,
               "--balance", balance, "--output", td, "--quiet"]
        try:
            env["PYTHONUTF8"] = "1"          # force UTF-8 in the subprocess
            p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               cwd=str(REPO), timeout=RUN_TIMEOUT_S)
            rj = Path(td) / "results.json"
            if p.returncode == 0 and rj.exists():
                return json.loads(rj.read_text())
        except (subprocess.TimeoutExpired, UnicodeDecodeError):
            pass
        # transient failure — back off (rising) and retry
        if attempt < retries:
            time.sleep(15 * (attempt + 1))
    return last_clean



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

def _val_task(args):
    """Worker: run one (config-index, start) full-path backtest."""
    ci, env, tp, start = args
    return ci, start, run_single(env, tp, start)


def validate_configs(configs: list, tag: str = "validation",
                     max_workers: int = None) -> list:
    """
    configs: list of {"env": {...}, "tp": {...}, "label": "..."}
    Runs each config on TEST_STARTS + full 10yr, then writes a report.

    All runs are FULL-PATH (~4.6GB each) so concurrency is capped at
    WORKERS_FULL (=2) to avoid the OOM killer. All (config, start) pairs are
    flattened into one pool so the 2 workers stay saturated.
    """
    (DOE_DIR / "tmp").mkdir(exist_ok=True)
    max_workers = max_workers or WORKERS_FULL
    starts = TEST_STARTS + [FULL_START]

    tasks = [(ci, cfg["env"], cfg["tp"], s)
             for ci, cfg in enumerate(configs) for s in starts]
    results = {ci: {} for ci in range(len(configs))}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for ci, start, r in ex.map(_val_task, tasks):
            results[ci][start] = r

    out, lines = [], [f"Validation report: {tag}\n{'='*78}\n"]
    for ci, cfg in enumerate(configs):
        lines.append(f"\n{'─'*60}\n  Config: {cfg.get('label','?')}\n{'─'*60}")
        runs = results[ci]
        all_runs = {}
        for s in TEST_STARTS:
            all_runs[f"test:{s}"] = runs.get(s)
            lines.append(_row(f"test:{s}", extract_attrs(runs.get(s))))
        full_r = runs.get(FULL_START)
        all_runs[f"full:{FULL_START}"] = full_r
        lines.append(_row(f"full:{FULL_START}", extract_attrs(full_r)))
        lma = late_monthly_avg(full_r)
        lines.append(f"    late_monthly_avg={lma:,.0f}")
        cfg["validation"] = all_runs
        cfg["full_result"] = full_r
        cfg["late_monthly_avg"] = lma
        out.append(cfg)

    report = "\n".join(lines)
    print(report)
    (DOE_DIR / f"{tag}_report.txt").write_text(report)
    return out
