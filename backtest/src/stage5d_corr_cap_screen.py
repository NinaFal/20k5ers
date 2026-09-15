#!/usr/bin/env python3
"""
Stage 5d — CORRELATION-CAP OOS screen.

Root-cause finding (see backtest/STAGE5C_BREACH_DIAGNOSIS.md): every Stage-5c
survivor breaches the full 2015-2024 continuous window because the strategy
stacks 15-19 highly-correlated positions (e.g. 6 GBP crosses + 6 CHF crosses)
that gap together on flash/news events (2015 CHF, 2019 JPY, 2020 COVID, 2022
gilt). The engine's `CORR_GROUP_CAP` lever bounds concurrent open+pending
positions per correlation group but was OFF (0) for the ENTIRE Stage-5c pool.

Diagnostic proof on trial 170 (full 2015-2024 window):
    cap off -> BREACH @ 2020-03 COVID  (DDD 13.51%)  net $618k
    cap 4   -> BREACH @ 2015-01 CHF    (DDD 10.72%)  net -$4k
    cap 3   -> BREACH @ 2024-12-27 last week (DDD 8.14%)  net $625k
    cap 2   -> SURVIVE full window     (DDD  3.87%)  net  $67k

So the cap is the missing breach lever. This screen sweeps it across the
existing top trials on the same 5 OOS windows the Stage-5c screen used, to find
(trial, cap) pairs that pass ALL windows including the full continuous run.

Reads  : backtest/output/doe/stage5c_oos_screen.json  (per-trial resolved env)
Writes : backtest/output/doe/stage5d_corr_cap_screen.json
         backtest/output/doe/stage5d_corr_cap_screen_windows.json  (checkpoint)
         backtest/output/doe/stage5d_corr_cap_screen_report.txt

Resumable: checkpoints every window, keyed "<tid>|<cap>|<start>". Safe to kill
and relaunch (via keepalive / run_in_background) — completed windows are skipped.
"""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOE_DIR = REPO / "backtest" / "output" / "doe"

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s)
_s.loader.exec_module(scr)

SCREEN_IN  = DOE_DIR / "stage5c_oos_screen.json"
JSON_OUT   = DOE_DIR / "stage5d_corr_cap_screen.json"
WINDOWS_OUT = DOE_DIR / "stage5d_corr_cap_screen_windows.json"
REPORT_OUT = DOE_DIR / "stage5d_corr_cap_screen_report.txt"

# Same window set as the Stage-5c screen: 4 OOS starts + the full continuous run.
OOS_TASKS  = scr.OOS_TASKS
FULL_START = scr.FULL_START
N_WINDOWS  = len(OOS_TASKS)
TP_OVER    = scr.TP_OVER

os.environ.setdefault("RUN_TIMEOUT_S", "999999")


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_candidates(only: set[int] | None) -> dict[int, dict]:
    """Return {trial_id: env} from the Stage-5c screen JSON."""
    data = json.loads(SCREEN_IN.read_text())
    out = {}
    for r in data:
        tid = int(r["trial"])
        if only and tid not in only:
            continue
        out[tid] = r["env"]
    return out


def verdict_for(windows: list[dict]) -> dict:
    oos = [w for w in windows if w["start"] != FULL_START]
    full = next((w for w in windows if w["start"] == FULL_START), None)
    n_pass_oos = sum(1 for w in oos if not w.get("failed"))
    pass_full = bool(full and not full.get("failed"))
    all_pass = (n_pass_oos == len(oos)) and pass_full
    return {
        "verdict":  "PASS" if all_pass else "FAIL",
        "oos_pass": n_pass_oos,
        "oos_total": len(oos),
        "full_pass": pass_full,
        "peak_ddd": round(max((w.get("max_ddd", 0) or 0) for w in windows), 2),
        "peak_tdd": round(max((w.get("max_tdd", 0) or 0) for w in windows), 2),
        "full_net": next((w.get("net", 0) for w in windows
                          if w["start"] == FULL_START), 0),
    }


def write_report(results: list[dict]):
    results.sort(key=lambda r: (r["verdict"] != "PASS", -r.get("full_net", 0)))
    lines = [
        f"Stage 5d CORR-CAP OOS Screen  [{ts()}]",
        f"windows: {N_WINDOWS} (4 OOS + full 2015-2024)",
        "",
        f"{'trial':>6}{'cap':>5}{'verdict':>9}{'OOSpass':>9}{'full':>6}"
        f"{'peakDDD%':>10}{'peakTDD%':>10}{'fullNet':>12}",
        "-" * 67,
    ]
    for r in results:
        lines.append(
            f"{r['trial']:>6}{r['cap']:>5}{r['verdict']:>9}"
            f"{r['oos_pass']:>4}/{r['oos_total']:<4}"
            f"{('PASS' if r['full_pass'] else 'FAIL'):>6}"
            f"{r['peak_ddd']:>10.2f}{r['peak_tdd']:>10.2f}{r.get('full_net',0):>12,.0f}")
    n_pass = sum(1 for r in results if r["verdict"] == "PASS")
    lines += ["", f"Passing (trial,cap): {n_pass}/{len(results)}"]
    REPORT_OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", default="2,3",
                    help="comma-separated CORR_GROUP_CAP values to sweep")
    ap.add_argument("--trials", default="",
                    help="comma-separated trial ids to restrict to "
                         "(default: trials that fail ONLY the full window)")
    ap.add_argument("--workers", type=int, default=int(os.getenv("VAL_WORKERS", "2")))
    args = ap.parse_args()

    DOE_DIR.mkdir(parents=True, exist_ok=True)
    (DOE_DIR / "tmp").mkdir(exist_ok=True)
    caps = [int(c) for c in args.caps.split(",") if c.strip()]

    # Default candidate set: trials whose ONLY Stage-5c failure was the full
    # continuous window (all 4 OOS windows already passed) — the cheapest path
    # to a clean PASS once the continuous-run clustering is capped.
    only = None
    if args.trials.strip():
        only = {int(t) for t in args.trials.split(",") if t.strip()}
    else:
        data = json.loads(SCREEN_IN.read_text())
        only = set()
        for r in data:
            oos_fail = [w for w in r["windows"]
                        if w["start"] != FULL_START and w.get("failed")]
            if not oos_fail:  # only the full window failed
                only.add(int(r["trial"]))

    cands = load_candidates(only)
    print(f"[{ts()}] Stage 5d: {len(cands)} candidate trials × caps {caps}"
          f" × {N_WINDOWS} windows  workers={args.workers}", flush=True)

    # Resume checkpoint.
    key_windows: dict[str, list] = defaultdict(list)   # "tid|cap" -> [win,...]
    done_windows: set[str] = set()                     # "tid|cap|start"
    if WINDOWS_OUT.exists():
        try:
            for k, wins in json.loads(WINDOWS_OUT.read_text()).items():
                key_windows[k] = wins
                for w in wins:
                    done_windows.add(f"{k}|{w['start']}")
        except Exception:
            pass

    tasks = []
    for tid, env in cands.items():
        for cap in caps:
            for (s, e) in OOS_TASKS:
                if f"{tid}|{cap}|{s}" not in done_windows:
                    tasks.append((tid, env, cap, s, e))
    print(f"[{ts()}] {len(tasks)} window-runs remaining", flush=True)

    lock = threading.Lock()

    def save():
        with lock:
            WINDOWS_OUT.write_text(json.dumps(dict(key_windows), indent=2, default=str))

    def run_task(t):
        tid, env, cap, start, end = t
        env_over = dict(env)
        env_over["CORR_GROUP_CAP"] = str(cap)
        r = dh.run_single(env_over, TP_OVER, start, end)
        a = dh.extract_attrs(r)
        win = {"start": start, "end": end, **a}
        tag = "[FULL]" if start == FULL_START else "[OOS ]"
        st = "BREACH" if a.get("failed") else "ok   "
        print(f"[{ts()}] t{tid:>3} cap{cap} {tag} {start} {st}"
              f" net={a.get('net',0):>10,.0f} tdd={a.get('max_tdd',0):.2f}%"
              f" ddd={a.get('max_ddd',0):.2f}%", flush=True)
        return f"{tid}|{cap}", win

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_task, t): t for t in tasks}
        for fut in concurrent.futures.as_completed(futs):
            try:
                key, win = fut.result()
            except Exception as exc:
                tid, env, cap, start, end = futs[fut]
                key = f"{tid}|{cap}"
                win = {"start": start, "end": end, "failed": True,
                       "net": 0, "max_tdd": 0, "max_ddd": 0}
                print(f"[{ts()}] t{tid} cap{cap} ERROR {start}: {exc}", flush=True)
            key_windows[key].append(win)
            save()

    # Build results.
    results = []
    for key, wins in key_windows.items():
        if len(wins) < N_WINDOWS:
            continue
        tid, cap = key.split("|")
        results.append({"trial": int(tid), "cap": int(cap),
                        **verdict_for(wins), "windows": wins})
    results.sort(key=lambda r: (r["verdict"] != "PASS", -r.get("full_net", 0)))
    JSON_OUT.write_text(json.dumps(results, indent=2, default=str))
    write_report(results)
    print("[stage5d_corr_cap_screen] STAGE5D_CORR_CAP_SCREEN_DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
