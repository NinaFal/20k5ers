#!/usr/bin/env python3
"""
Stage 5c OOS Screener — flat-pool design.

Reads  : backtest/output/doe/stage5c.csv
Writes : backtest/output/doe/stage5c_oos_screen.json
         backtest/output/doe/stage5c_oos_screen_report.txt
"""
import argparse
import concurrent.futures
import csv
import importlib.util
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dh)

DOE_DIR    = REPO / "backtest" / "output" / "doe"
CSV_IN     = DOE_DIR / "stage5c.csv"
JSON_OUT   = DOE_DIR / "stage5c_oos_screen.json"
WINDOWS_OUT = DOE_DIR / "stage5c_oos_screen_windows.json"
REPORT_OUT = DOE_DIR / "stage5c_oos_screen_report.txt"

FULL_END   = "2024-12-31"
FULL_START = "2015-01-01"
OOS_STARTS = [
    "2015-02-01",
    "2018-01-01",
    "2021-01-01",
    "2023-01-01",
    "2023-07-01",
]
OOS_TASKS = [(s, FULL_END) for s in OOS_STARTS] + [(FULL_START, FULL_END)]
N_WINDOWS  = len(OOS_TASKS)

PARAM_COLS = [
    "RISK_CALM_MULT", "RISK_VOLATILE_MULT", "VOL_REGIME_DD_OFF",
    "CFG_MAX_CUM_RISK", "CFG_DAILY_HALT_PCT",
    "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS",
    "CFG_TDD_WARNING_PCT", "CFG_RISK_CONSERVATIVE",
    "CFG_TDD_EMERGENCY_PCT", "CFG_RISK_ULTRASAFE", "TDD_WALL_SAFETY",
]
FIXED_ENV = {
    "RISK_REGIME_ENABLE": "1",
    "VOL_SIZE_ENABLE":    "0",
    "VOL_REGIME_DD_MULT": "1.0",
}
PINNED_ENTRY = {
    "trend_min_confluence":     6,
    "range_min_confluence":     3,
    "min_quality_factors":      3,
    "atr_min_percentile":       41.0,
    "atr_vol_ratio_range":      1.4,
    "use_fib_filter":           False,
    "fib_zone_type":            "golden_only",
    "entry_limit_offset_atr":   0.0,
    "entry_fib_level":          0.55,
    "entry_fib_level_volatile": 0.80,
    "fib_vol_ratio_threshold":  1.05,
    "use_trend_quality_gate":   False,
    "adx_min_entry":            0.0,
}
WINNER_LADDER = {
    "tp1_r_multiple": 0.6,  "tp2_r_multiple": 1.6,  "tp3_r_multiple": 2.8,
    "tp4_r_multiple": 3.4,  "tp5_r_multiple": 4.3,
    "tp1_close_pct":  0.10, "tp2_close_pct":  0.30, "tp3_close_pct": 0.20,
    "tp4_close_pct":  0.15, "tp5_close_pct":  0.25,
    "sl_after_tp2_r": 0.70, "sl_after_tp3_r": 1.40, "sl_after_tp4_r": 2.00,
    "risk_per_trade_pct": 1.0,
}
TP_OVER = {**PINNED_ENTRY, **WINNER_LADDER}

os.environ.setdefault("RUN_TIMEOUT_S", "999999")


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_top_trials(n: int) -> list[dict]:
    rows = []
    with open(CSV_IN, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("breached", "True").strip().lower() in ("true", "1"):
                continue
            try:
                obj = float(row["objective"])
            except (ValueError, KeyError):
                continue
            rows.append({"obj": obj, "row": row})
    rows.sort(key=lambda x: x["obj"], reverse=True)
    return [r["row"] for r in rows[:n]]


def env_from_row(row: dict) -> dict:
    env = dict(FIXED_ENV)
    for k in PARAM_COLS:
        v = row.get(k, "")
        if v:
            env[k] = str(float(v))
    return env


def trial_summary(trial_id: int, row: dict, windows: list[dict]) -> dict:
    oos_wins   = [w for w in windows if w["start"] != FULL_START]
    full_win   = next((w for w in windows if w["start"] == FULL_START), None)
    n_pass_oos = sum(1 for w in oos_wins if not w.get("failed"))
    pass_full  = bool(full_win and not full_win.get("failed"))
    all_pass   = (n_pass_oos == len(oos_wins)) and pass_full
    max_ddd    = max((w.get("max_ddd", 0) or 0) for w in windows)
    max_tdd    = max((w.get("max_tdd", 0) or 0) for w in windows)
    return {
        "trial":     trial_id,
        "obj":       float(row.get("objective", 0)),
        "calm":      float(row.get("RISK_CALM_MULT", 0)),
        "vol":       float(row.get("RISK_VOLATILE_MULT", 0)),
        "halt":      float(row.get("CFG_DAILY_HALT_PCT", 0)),
        "verdict":   "PASS" if all_pass else "FAIL",
        "oos_pass":  n_pass_oos,
        "oos_total": len(oos_wins),
        "full_pass": pass_full,
        "peak_ddd":  round(max_ddd, 2),
        "peak_tdd":  round(max_tdd, 2),
        "windows":   windows,
        "env":       env_from_row(row),
    }


def write_report(results: list[dict], top_n: int):
    lines = [
        f"Stage 5c OOS Screen — top {top_n} trials  [{ts()}]",
        f"OOS windows: {len(OOS_STARTS)} starts + 1 full (2015-2024)",
        "",
        f"{'Rank':<5}{'Trial':<7}{'Verdict':<9}{'OOS pass':<11}{'Full':<6}"
        f"{'peakDDD%':>9}{'peakTDD%':>9}{'Obj':>13}{'calm':>7}{'vol':>6}{'halt':>6}",
        "-" * 84,
    ]
    for i, r in enumerate(results, 1):
        full_s = "PASS" if r["full_pass"] else "FAIL"
        lines.append(
            f"  {i:<4}{r['trial']:<7}{r['verdict']:<9}"
            f"{r['oos_pass']}/{r['oos_total']}        {full_s:<6}"
            f"{r['peak_ddd']:>8.2f}  {r['peak_tdd']:>8.2f}"
            f"  {r['obj']:>11,.0f}  {r['calm']:>5.2f}  {r['vol']:>5.2f}  {r['halt']:>4.2f}"
        )
    passing = [r for r in results if r["verdict"] == "PASS"]
    lines += ["", f"Passing: {len(passing)}/{len(results)}"]
    if passing:
        best = passing[0]
        lines += [
            "",
            "── Best passing trial ──",
            f"  Trial {best['trial']}  obj={best['obj']:,.0f}  calm={best['calm']}  vol={best['vol']}  halt={best['halt']}",
            "  OOS windows:",
        ]
        for w in best["windows"]:
            label  = "[FULL]" if w["start"] == FULL_START else "[OOS ]"
            status = "BREACH" if w.get("failed") else "ok"
            lines.append(f"    {label} {w['start']}  {status:<8}"
                         f"  net={w.get('net',0):>10,.0f}"
                         f"  tdd={w.get('max_tdd',0):>5.2f}%  ddd={w.get('max_ddd',0):>5.2f}%")
        lines += ["", "  WINNER_ENV:"]
        for k, v in best["env"].items():
            lines.append(f"    {k} = {v}")
    lines += ["", "[stage5c_oos_screen] STAGE5C_OOS_SCREEN_DONE_MARKER"]
    text = "\n".join(lines) + "\n"
    REPORT_OUT.write_text(text)
    print(text, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top",     type=int, default=20)
    ap.add_argument("--workers", type=int, default=int(os.getenv("VAL_WORKERS", "6")))
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)

    done_results: list[dict] = []
    done_ids: set[int] = set()
    if JSON_OUT.exists():
        try:
            done_results = json.loads(JSON_OUT.read_text())
            done_ids = {r["trial"] for r in done_results}
            print(f"[{ts()}] Checkpoint: {len(done_ids)} trials already done: {sorted(done_ids)}",
                  flush=True)
        except Exception:
            pass

    # Per-window checkpoint — survives a container restart mid-trial.
    # Keyed by "<tid>|<start>" so completed windows are never re-run.
    trial_windows: dict[int, list] = defaultdict(list)
    done_windows: set[str] = set()
    if WINDOWS_OUT.exists():
        try:
            saved = json.loads(WINDOWS_OUT.read_text())
            for tid_s, wins in saved.items():
                tid = int(tid_s)
                if tid in done_ids:
                    continue
                trial_windows[tid] = wins
                for w in wins:
                    done_windows.add(f"{tid}|{w['start']}")
            if done_windows:
                print(f"[{ts()}] Window checkpoint: {len(done_windows)} windows already done",
                      flush=True)
        except Exception:
            pass

    trials = load_top_trials(args.top)
    pending = [r for r in trials if int(r.get("trial", -1)) not in done_ids]

    trial_rows: dict[int, dict] = {}
    for row in pending:
        tid = int(row.get("trial", -1))
        trial_rows[tid] = row

    # Only enqueue windows that have not already been computed.
    tasks = [(row, s, e) for row in pending for (s, e) in OOS_TASKS
             if f"{int(row.get('trial', -1))}|{s}" not in done_windows]
    print(f"[{ts()}] Flat-pool OOS screen: {len(pending)} pending trials × {N_WINDOWS} windows"
          f" = {len(tasks)} tasks remaining  workers={args.workers}", flush=True)

    results = list(done_results)

    # A restart may have left some trials with all 6 windows already saved but
    # no summary written — finalize those before launching the pool.
    for tid, wins in list(trial_windows.items()):
        if len(wins) == N_WINDOWS and not any(r["trial"] == tid for r in results):
            results.append(trial_summary(tid, trial_rows[tid], wins))

    if not tasks:
        print(f"[{ts()}] All windows already done.", flush=True)
        results.sort(key=lambda x: (x["verdict"] != "PASS", -x["obj"]))
        JSON_OUT.write_text(json.dumps(results, indent=2, default=str))
        write_report(results, args.top)
        print("[stage5c_oos_screen] STAGE5C_OOS_SCREEN_DONE_MARKER", flush=True)
        return

    import threading
    _lock = threading.Lock()

    def save_windows():
        with _lock:
            WINDOWS_OUT.write_text(
                json.dumps({str(k): v for k, v in trial_windows.items()},
                           indent=2, default=str))

    def run_task(args_tuple):
        row, start, end = args_tuple
        tid      = int(row.get("trial", -1))
        env_over = env_from_row(row)
        r = dh.run_single(env_over, TP_OVER, start, end)
        a = dh.extract_attrs(r)
        win = {"start": start, "end": end, **a}
        label  = "[FULL]" if start == FULL_START else "[OOS ]"
        status = "BREACH" if a.get("failed") else "ok   "
        print(f"[{ts()}] t{tid:3d} {label} {start}  {status}"
              f"  net={a.get('net',0):>10,.0f}"
              f"  tdd={a.get('max_tdd',0):.2f}%  ddd={a.get('max_ddd',0):.2f}%",
              flush=True)
        return tid, win

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_task, t): t for t in tasks}
        for fut in concurrent.futures.as_completed(futs):
            try:
                tid, win = fut.result()
            except Exception as exc:
                row, start, end = futs[fut]
                tid = int(row.get("trial", -1))
                print(f"[{ts()}] t{tid:3d} ERROR {start}: {exc}", flush=True)
                win = {"start": start, "end": end, "failed": True,
                       "net": 0, "max_tdd": 0, "max_ddd": 0}

            trial_windows[tid].append(win)
            save_windows()  # checkpoint every window — survives mid-trial restart

            if len(trial_windows[tid]) == N_WINDOWS:
                summary = trial_summary(tid, trial_rows[tid], trial_windows[tid])
                results.append(summary)
                verdict = summary["verdict"]
                print(f"[{ts()}] t{tid:3d} {verdict}  "
                      f"OOS {summary['oos_pass']}/{summary['oos_total']}"
                      f"  full={'PASS' if summary['full_pass'] else 'FAIL'}"
                      f"  peak_ddd={summary['peak_ddd']:.2f}%"
                      f"  peak_tdd={summary['peak_tdd']:.2f}%", flush=True)
                JSON_OUT.write_text(json.dumps(results, indent=2, default=str))

    results.sort(key=lambda x: (x["verdict"] != "PASS", -x["obj"]))
    JSON_OUT.write_text(json.dumps(results, indent=2, default=str))
    write_report(results, args.top)
    print("[stage5c_oos_screen] STAGE5C_OOS_SCREEN_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
