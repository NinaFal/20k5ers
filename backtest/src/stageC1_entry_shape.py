#!/usr/bin/env python3
"""
Stage C1 — entry SHAPE vs the 2-step challenge objective.

Entry gates proved non-binding, so speed must come from entry shape: WHERE the
limit order sits (fib retracement depth per regime) and the calm/volatile switch
threshold. These set win-rate x R per unit time — the binding constraint on
banking +8% closed fast.

Grid over (entry_fib_level, entry_fib_level_volatile, fib_vol_ratio_threshold),
scored by challenge_score.full_two_step on the 16 TRAIN starts. Everything else
fixed: bank_fast ladder, risk 3.5%, t49 regime skeleton, cap 3, CHF on.

Resumable per (config,start). Run:
    uv run python3 backtest/src/stageC1_entry_shape.py
"""
import concurrent.futures
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "stageC1_entry_shape.json"

_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

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
RISK = 3.5
BASE_ENTRY = dict(scr.PINNED_ENTRY)

# 12 entry shapes. Baseline (Stage-1 winner: c=0.55 v=0.80 thr=1.05) is included.
GRID = [
    {"entry_fib_level": c, "entry_fib_level_volatile": v, "fib_vol_ratio_threshold": t}
    for c in (0.45, 0.55, 0.65)
    for v in (0.65, 0.80)
    for t in (1.05, 1.15)
]


def cfg_name(g):
    return f"c{g['entry_fib_level']}_v{g['entry_fib_level_volatile']}_t{g['fib_vol_ratio_threshold']}"


def ts():
    return datetime.now().strftime("%H:%M:%S")


def eval_cell(cell):
    g, start = cell
    tp = {**BASE_ENTRY, **g, **BANK_FAST, "risk_per_trade_pct": RISK}
    r = cs.full_two_step(SKELETON, tp, start)
    r.pop("detail", None)
    r["config"] = cfg_name(g)
    tag = f"total={r['total']}" if r["total"] is not None else f"FAIL({r['why']})"
    print(f"[C1] {r['config']:>18} {start}  {tag}"
          f"{' BREACH' if r['breach'] else ''}", flush=True)
    return r


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try:
            done = {(d["config"], d["start"]): d for d in json.loads(OUT.read_text())}
        except Exception:
            pass
    cells = [(g, s) for g in GRID for s in cs.TRAIN_STARTS
             if (cfg_name(g), s) not in done]
    print(f"[{ts()}] C1 entry-shape grid: {len(cells)} cells "
          f"({len(GRID)} configs x {len(cs.TRAIN_STARTS)} train starts)", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(eval_cell, cells):
            results.append(o)
            OUT.write_text(json.dumps(results, indent=2, default=str))

    print(f"\n=== C1 entry shape — challenge score (TRAIN, {len(cs.TRAIN_STARTS)} starts) ===", flush=True)
    print(f"{'config':>20}{'score':>8}{'p20':>6}{'p40':>6}{'breach':>8}{'medTot':>8}", flush=True)
    ranked = []
    for g in GRID:
        name = cfg_name(g)
        rows = [r for r in results if r["config"] == name]
        if len(rows) < len(cs.TRAIN_STARTS):
            continue
        sc = cs.score_results(rows)
        ranked.append((sc["score"], name, sc))
    for score, name, sc in sorted(ranked, reverse=True):
        print(f"{name:>20}{sc['score']:>8.1f}{sc['p20']:>6.2f}{sc['p40']:>6.2f}"
              f"{sc['breach_rate']:>8.2f}{sc['median_total']:>8}", flush=True)
    print("[stageC1_entry_shape] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
