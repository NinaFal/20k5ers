#!/usr/bin/env python3
"""
Option 2 — does looser CHALLENGE-phase entry (higher trade throughput) lift the
<=20-day full 2-step pass rate without raising breaches?

The 20-day ceiling is throughput-limited: a selective HTF strategy can't bank +8%
closed fast enough in most windows. This loosens the entry gates
(trend_min_confluence / range_min_confluence / min_quality_factors) so more
setups fire, and measures the effect on: avg trades, <=20-day full-2-step pass
rate, and breach rate. Ladder fixed to bank_fast, risk 3.5%, t49 skeleton, CHF on.

Run:  uv run python3 backtest/src/challenge_throughput_test.py
"""
import concurrent.futures, importlib.util, json, os, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
from pathlib import Path
from statistics import median, mean

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "challenge_throughput_test.json"
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)
_c = importlib.util.spec_from_file_location("chal", str(HERE / "challenge_eval.py"))
ce = importlib.util.module_from_spec(_c); _c.loader.exec_module(ce)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

ACCOUNT = 100_000
STEP_HORIZON = 25
RISK = 3.5
CLEAN_YEARS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
STARTS = [f"{y}-{m:02d}-01" for y in CLEAN_YEARS for m in (1, 7)]  # 16 starts

SKELETON = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "2.25",
            "CFG_TDD_CAUTION_PCT": "3.5", "CFG_RISK_CAUTIOUS": "0.65", "CFG_TDD_WARNING_PCT": "4.5",
            "CFG_RISK_CONSERVATIVE": "0.6", "CFG_TDD_EMERGENCY_PCT": "8.0", "CFG_RISK_ULTRASAFE": "0.4",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3"}

BANK_FAST = {
    "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
    "tp4_r_multiple": 2.0, "tp5_r_multiple": 3.0,
    "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
    "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
    "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8}

# Entry-gate configs (looser = more setups fire). Base = the t39/Stage-1 winner.
ENTRIES = {
    "E_base":   {"trend_min_confluence": 6, "range_min_confluence": 3, "min_quality_factors": 3},
    "E_loose":  {"trend_min_confluence": 5, "range_min_confluence": 3, "min_quality_factors": 2},
    "E_looser": {"trend_min_confluence": 4, "range_min_confluence": 2, "min_quality_factors": 2},
    "E_max":    {"trend_min_confluence": 3, "range_min_confluence": 2, "min_quality_factors": 1},
}
# Full entry block from the pinned skeleton, with the gate keys overridden per config.
BASE_ENTRY = {k: v for k, v in scr.PINNED_ENTRY.items()}


def _run_step(entry_over, start, step1):
    s = date.fromisoformat(start)
    end = (s + timedelta(days=STEP_HORIZON)).isoformat()
    env = dict(os.environ); env.update(dh.BASE_ENV); env.update(SKELETON)
    tp = {**BASE_ENTRY, **entry_over, **BANK_FAST, "risk_per_trade_pct": RISK}
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
        trades = int(r.get("total_trades") or 0)
        bday = None
        if r.get("account_failed") and fi.get("time"):
            try: bday = (date.fromisoformat(str(fi["time"])[:10]) - s).days
            except ValueError: pass
        d5, d8 = ce.days_to_target(Path(td) / "trades.csv", start)
        dt = d8 if step1 else d5
        if bday is not None and (dt is None or bday < dt):
            return True, None, trades
        return False, dt, trades
    finally:
        shutil.rmtree(td, ignore_errors=True)


def eval_cell(cell):
    name, start = cell
    eo = ENTRIES[name]
    b1, d1, t1 = _run_step(eo, start, True)
    if d1 is None:
        return {"entry": name, "start": start, "pass20": False, "d1": None, "d2": None,
                "total": None, "breach": b1, "why": "step1", "trades1": t1}
    s2 = (date.fromisoformat(start) + timedelta(days=d1 + 1)).isoformat()
    b2, d2, t2 = _run_step(eo, s2, False)
    if d2 is None:
        return {"entry": name, "start": start, "pass20": False, "d1": d1, "d2": None,
                "total": None, "breach": b2, "why": "step2", "trades1": t1}
    total = d1 + 1 + d2
    return {"entry": name, "start": start, "pass20": total <= 20, "d1": d1, "d2": d2,
            "total": total, "breach": False, "why": "" if total <= 20 else "slow", "trades1": t1}


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try: done = {(d["entry"], d["start"]): d for d in json.loads(OUT.read_text())}
        except Exception: pass
    cells = [(n, s) for n in ENTRIES for s in STARTS if (n, s) not in done]
    print(f"[thru] risk={RISK}% bank_fast  {len(cells)} cells ({len(ENTRIES)} entries x {len(STARTS)} starts)", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(eval_cell, cells):
            results.append(o); OUT.write_text(json.dumps(results, indent=2, default=str))
            tag = "PASS<=20" if o["pass20"] else f"FAIL({o['why']})"
            print(f"[thru] {o['entry']:>9} {o['start']} {tag} d1={o['d1']} d2={o['d2']} total={o['total']} trades1={o['trades1']}"
                  f"{' BREACH' if o['breach'] else ''}", flush=True)
    print(f"\n=== throughput sweep: <=20-day full 2-step (bank_fast, risk {RISK}%, 16 starts) ===", flush=True)
    print(f"{'entry':>9}{'gates(T/R/Q)':>14}{'avgTrades1':>11}{'pass<=20':>9}{'rate':>7}{'breach':>8}", flush=True)
    for name in ENTRIES:
        rows = [d for d in results if d["entry"] == name]
        if not rows: continue
        p = [d for d in rows if d["pass20"]]; br = [d for d in rows if d["breach"]]
        g = ENTRIES[name]
        gates = f"{g['trend_min_confluence']}/{g['range_min_confluence']}/{g['min_quality_factors']}"
        avgt = mean(d["trades1"] for d in rows)
        print(f"{name:>9}{gates:>14}{avgt:>11.1f}{len(p):>9}{len(p)/len(rows)*100:>6.0f}%{len(br):>8}", flush=True)
    print("[challenge_throughput_test] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
