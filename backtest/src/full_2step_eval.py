#!/usr/bin/env python3
"""
FULL 5%ers 2-step challenge in <= 20 days — feasibility / speed evaluator.

The requirement: pass BOTH steps in <= 20 calendar days total, no breach.
  Step 1: fresh 100k, reach +8%.  Then account resets ->
  Step 2: fresh 100k, reach +5%.
Total days = (days to +8% from S1) + (days to +5% from S2), S2 = S1 + D1 + 1.
PASS_20 = total <= 20 AND no breach in either step.

Sweeps base risk on the t49 regime skeleton (calm 1.45 / vol 0.64, cap 3, CHF on)
across many starts, and reports the <=20-day full-pass rate + day distribution.
Runs are short (<=25-day horizons) so this is cheap.

Run:  uv run python3 backtest/src/full_2step_eval.py
"""
import concurrent.futures, importlib.util, json, os, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "full_2step_eval.json"
_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)
_c = importlib.util.spec_from_file_location("chal", str(HERE / "challenge_eval.py"))
ce = importlib.util.module_from_spec(_c); _c.loader.exec_module(ce)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

ACCOUNT = 100_000
STEP_HORIZON = 25          # per-step cap; anything >20 total already fails
CHF = "USD_CHF,EUR_CHF,GBP_CHF,AUD_CHF,NZD_CHF,CAD_CHF,CHF_JPY"
RISKS = [2.0, 2.5, 3.0]
CLEAN_YEARS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
STARTS = [f"{y}-{m:02d}-01" for y in CLEAN_YEARS for m in (1, 4, 7, 10)]  # 32 starts

# t49 skeleton (best fast 2-way config) — regime-adaptive sizing that won earlier.
SKELETON = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45",
            "RISK_VOLATILE_MULT": "0.64", "VOL_REGIME_DD_OFF": "5.0",
            "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "2.25",
            "CFG_TDD_CAUTION_PCT": "3.5", "CFG_RISK_CAUTIOUS": "0.65",
            "CFG_TDD_WARNING_PCT": "4.5", "CFG_RISK_CONSERVATIVE": "0.6",
            "CFG_TDD_EMERGENCY_PCT": "8.0", "CFG_RISK_ULTRASAFE": "0.4",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3"}  # CHF included below


def _run_step(risk, start, target_is_step1):
    """Run one fresh-100k step; return (breached_before_target, day_to_target|None)."""
    s = date.fromisoformat(start)
    end = (s + timedelta(days=STEP_HORIZON)).isoformat()
    env = dict(os.environ); env.update(dh.BASE_ENV); env.update(SKELETON)
    tp = dict(scr.TP_OVER); tp["risk_per_trade_pct"] = risk
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
            try:
                bday = (date.fromisoformat(str(fi["time"])[:10]) - s).days
            except ValueError:
                pass
        d5, d8 = ce.days_to_target(Path(td) / "trades.csv", start)
        dt = d8 if target_is_step1 else d5
        breached = bday is not None and (dt is None or bday < dt)
        if breached:
            dt = None
        return breached, dt
    finally:
        shutil.rmtree(td, ignore_errors=True)


def eval_start(args):
    risk, start = args
    b1, d1 = _run_step(risk, start, True)          # Step 1 -> +8%
    if d1 is None:
        return {"risk": risk, "start": start, "pass20": False, "why": "step1", "total": None,
                "d1": None, "d2": None, "breach": b1}
    s2 = (date.fromisoformat(start) + timedelta(days=d1 + 1)).isoformat()
    b2, d2 = _run_step(risk, s2, False)            # Step 2 -> +5%
    if d2 is None:
        return {"risk": risk, "start": start, "pass20": False, "why": "step2", "total": None,
                "d1": d1, "d2": None, "breach": b2}
    total = d1 + 1 + d2
    return {"risk": risk, "start": start, "pass20": total <= 20, "why": "" if total <= 20 else "slow",
            "total": total, "d1": d1, "d2": d2, "breach": False}


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    SKELETON_chf = dict(SKELETON)  # CHF included (no EXCLUDE_SYMBOLS)
    done = {}
    if OUT.exists():
        try:
            done = {(d["risk"], d["start"]): d for d in json.loads(OUT.read_text())}
        except Exception:
            pass
    cells = [(r, s) for r in RISKS for s in STARTS if (r, s) not in done]
    print(f"[2step] {len(cells)} cells ({len(RISKS)} risks x {len(STARTS)} starts), <=20d target", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(eval_start, cells):
            results.append(o)
            OUT.write_text(json.dumps(results, indent=2, default=str))
            tag = "PASS<=20" if o["pass20"] else f"FAIL({o['why']})"
            print(f"[2step] risk={o['risk']} {o['start']}  {tag}"
                  f"  d1={o['d1']} d2={o['d2']} total={o['total']}"
                  f"  {'BREACH' if o['breach'] else ''}", flush=True)
    print("\n=== full 2-step <=20 days — pass rate by risk (t49 skeleton, CHF on) ===", flush=True)
    print(f"{'risk':>5}{'starts':>7}{'pass<=20':>9}{'rate':>7}{'breach':>8}{'medTotal':>9}", flush=True)
    for risk in RISKS:
        rows = [d for d in results if d["risk"] == risk]
        if not rows:
            continue
        p = [d for d in rows if d["pass20"]]
        br = [d for d in rows if d["breach"]]
        totals = sorted(d["total"] for d in rows if d["total"] is not None)
        med = median(totals) if totals else None
        print(f"{risk:>5}{len(rows):>7}{len(p):>9}{len(p)/len(rows)*100:>6.0f}%"
              f"{len(br):>8}{(med if med is not None else '-'):>9}", flush=True)
    print("[full_2step_eval] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
