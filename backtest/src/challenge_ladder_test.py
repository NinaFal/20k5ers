#!/usr/bin/env python3
"""
Does a fast-banking TP ladder crack the <=20-day full 2-step (CLOSED balance)?

The runner ladder banks realized profit slowly (big held runners), so realized
+8%/+5% arrives too late for a 20-day full 2-step. Hypothesis: a challenge-only
ladder that closes most of each position at LOW R banks +8% fast enough.

Compares the runner ladder (control) vs fast-banking ladders on the full 2-step
(Step1 +8% -> reset -> Step2 +5%, total <=20 days, closed balance, no breach),
across starts, at a chosen risk. Same t49 regime skeleton + CHF on. Resumable.

Run:  uv run python3 backtest/src/challenge_ladder_test.py
"""
import concurrent.futures, importlib.util, json, os, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "challenge_ladder_test.json"
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)
_c = importlib.util.spec_from_file_location("chal", str(HERE / "challenge_eval.py"))
ce = importlib.util.module_from_spec(_c); _c.loader.exec_module(ce)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

ACCOUNT = 100_000
STEP_HORIZON = 25
RISK = float(os.getenv("LADDER_RISK", "2.5"))
CLEAN_YEARS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
STARTS = [f"{y}-{m:02d}-01" for y in CLEAN_YEARS for m in (1, 7)]  # 16 starts (quick screen)

SKELETON = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "2.25",
            "CFG_TDD_CAUTION_PCT": "3.5", "CFG_RISK_CAUTIOUS": "0.65", "CFG_TDD_WARNING_PCT": "4.5",
            "CFG_RISK_CONSERVATIVE": "0.6", "CFG_TDD_EMERGENCY_PCT": "8.0", "CFG_RISK_ULTRASAFE": "0.4",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3"}

# Entry stays the t39 skeleton; only the TP ladder changes.
ENTRY = {k: v for k, v in scr.PINNED_ENTRY.items()}

# Ladders (close pcts must sum to 1.0). sl_after_* trail the stop after each TP.
LADDERS = {
    "runner_control": scr.WINNER_LADDER,   # the funded-phase ladder (baseline)
    "bank_fast": {  # close 80% by 1.0R
        "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
        "tp4_r_multiple": 2.0, "tp5_r_multiple": 3.0,
        "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
        "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
        "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8},
    "bank_med": {   # close 60% by 1.2R, keep a little runner
        "tp1_r_multiple": 0.6, "tp2_r_multiple": 1.2, "tp3_r_multiple": 2.0,
        "tp4_r_multiple": 3.0, "tp5_r_multiple": 4.0,
        "tp1_close_pct": 0.35, "tp2_close_pct": 0.30, "tp3_close_pct": 0.20,
        "tp4_close_pct": 0.15, "tp5_close_pct": 0.0,
        "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.3, "sl_after_tp4_r": 2.0},
}


def _run_step(ladder_tp, start, step1):
    s = date.fromisoformat(start)
    end = (s + timedelta(days=STEP_HORIZON)).isoformat()
    env = dict(os.environ); env.update(dh.BASE_ENV); env.update(SKELETON)
    tp = {**ENTRY, **ladder_tp, "risk_per_trade_pct": RISK}
    env["OPT_PARAMS"] = json.dumps({**dh.BASE_TP, **tp}); env["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        cmd = [sys.executable, str(dh.BACKTEST), "--start", start, "--end", end,
               "--balance", str(ACCOUNT), "--output", td, "--quiet"]
        subprocess.run(cmd, env=env, cwd=str(dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=900)
        rj = Path(td) / "results.json"
        r = json.loads(rj.read_text()) if rj.exists() else {}
        fi = r.get("fail_info") or {}
        bday = None
        if r.get("account_failed") and fi.get("time"):
            try: bday = (date.fromisoformat(str(fi["time"])[:10]) - s).days
            except ValueError: pass
        d5, d8 = ce.days_to_target(Path(td) / "trades.csv", start)
        dt = d8 if step1 else d5
        if bday is not None and (dt is None or bday < dt):
            return True, None
        return False, dt
    finally:
        shutil.rmtree(td, ignore_errors=True)


def eval_cell(cell):
    name, start = cell
    ladder = LADDERS[name]
    b1, d1 = _run_step(ladder, start, True)
    if d1 is None:
        return {"ladder": name, "start": start, "pass20": False, "d1": None, "d2": None,
                "total": None, "breach": b1, "why": "step1"}
    s2 = (date.fromisoformat(start) + timedelta(days=d1 + 1)).isoformat()
    b2, d2 = _run_step(ladder, s2, False)
    if d2 is None:
        return {"ladder": name, "start": start, "pass20": False, "d1": d1, "d2": None,
                "total": None, "breach": b2, "why": "step2"}
    total = d1 + 1 + d2
    return {"ladder": name, "start": start, "pass20": total <= 20, "d1": d1, "d2": d2,
            "total": total, "breach": False, "why": "" if total <= 20 else "slow"}


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try: done = {(d["ladder"], d["start"]): d for d in json.loads(OUT.read_text())}
        except Exception: pass
    cells = [(n, s) for n in LADDERS for s in STARTS if (n, s) not in done]
    print(f"[ladder] risk={RISK}%  {len(cells)} cells ({len(LADDERS)} ladders x {len(STARTS)} starts)", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(eval_cell, cells):
            results.append(o); OUT.write_text(json.dumps(results, indent=2, default=str))
            tag = "PASS<=20" if o["pass20"] else f"FAIL({o['why']})"
            print(f"[ladder] {o['ladder']:>14} {o['start']} {tag} d1={o['d1']} d2={o['d2']} total={o['total']}"
                  f"{' BREACH' if o['breach'] else ''}", flush=True)
    print(f"\n=== full 2-step <=20 days by ladder (risk {RISK}%, 16 starts) ===", flush=True)
    print(f"{'ladder':>16}{'pass<=20':>9}{'rate':>7}{'breach':>8}{'medTotal':>9}", flush=True)
    for name in LADDERS:
        rows = [d for d in results if d["ladder"] == name]
        if not rows: continue
        p = [d for d in rows if d["pass20"]]; br = [d for d in rows if d["breach"]]
        tots = sorted(d["total"] for d in rows if d["total"] is not None)
        med = median(tots) if tots else None
        print(f"{name:>16}{len(p):>9}{len(p)/len(rows)*100:>6.0f}%{len(br):>8}{(med if med is not None else '-'):>9}", flush=True)
    print("[challenge_ladder_test] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
