#!/usr/bin/env python3
"""
Quick diagnostic: what base risk is even viable under the corrected 3% daily
wall (5%ers Summer Edition)? All prior C1/C2/C3 work used risk 2.5-5.0%, sized
for a 5% wall -- likely far too hot for 3%. Cheap probe (8 TRAIN starts, one
step only -- Step 1) across a risk ladder, C1 winner entry + bank_fast ladder,
before committing to a full C1 restart at the right risk level.

Run:  uv run python3 backtest/src/wall3pct_risk_probe.py
"""
import concurrent.futures, importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)

SKELETON = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "1.25",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "6.0", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "2"}  # tighter cap+halt for the tighter wall
BANK_FAST = {
    "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
    "tp4_r_multiple": 2.0, "tp5_r_multiple": 3.0,
    "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
    "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
    "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8}
ENTRY = dict(scr.PINNED_ENTRY)
ENTRY.update({"entry_fib_level": 0.65, "entry_fib_level_volatile": 0.65,
              "fib_vol_ratio_threshold": 1.15})

PROBE_STARTS = cs.TRAIN_STARTS[:8]
RISKS = [0.4, 0.6, 0.8, 1.0, 1.25, 1.5]


def probe(risk):
    tp = {**ENTRY, **BANK_FAST, "risk_per_trade_pct": risk}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(cs.run_step, SKELETON, tp, s, cs.STEP1_TARGET, 30) for s in PROBE_STARTS]
        rows = [f.result() for f in futs]
    n = len(rows)
    passed = [r for r in rows if r["pass_day"] is not None]
    breached = [r for r in rows if r["breach"]]
    days = sorted(r["pass_day"] for r in passed)
    med = days[len(days)//2] if days else None
    print(f"risk={risk:>5}%  pass {len(passed)}/{n}  breach {len(breached)}/{n}"
          f"  medDay1={med}  days={days}", flush=True)
    return risk, len(passed), len(breached)


if __name__ == "__main__":
    print(f"[probe] 3% wall, {len(PROBE_STARTS)} TRAIN starts, Step 1 (+8%) only, 30d horizon", flush=True)
    for r in RISKS:
        probe(r)
    print("[wall3pct_risk_probe] DONE_MARKER", flush=True)
