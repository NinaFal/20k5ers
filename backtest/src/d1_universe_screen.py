#!/usr/bin/env python3
"""
D1-full — does the EXPANDED universe change the challenge frontier?

Two pipeline fixes just landed (D0_D1_FINDINGS.md):
  1. BROKER_TYPE=fiveers_live in challenge_score (default forexcom_demo had
     trade_metals=False — XAU/XAG silently excluded from every prior backtest
     despite being tradable on the real 5ers account);
  2. tz-normalization in the M15 loader (NAS100_USD failed to load: one
     tz-aware + one tz-naive file crashed concat/sort).
Universe grows 27 -> 30 effective symbols (gold, silver, NAS100 — gold/NAS
being strong trenders). D1-lite also found 3 structural bleeders (AUD_NZD
-$55/trade, EUR_NZD, AUD_JPY).

This screens the CURRENT best 3%-wall config on the 16 TRAIN starts:
  A "expanded"          : new universe as-is
  B "expanded_no_bleed" : new universe minus the 3 bleeders
against the known old-universe baseline (score ~5.7 / -0.5, p30=0, med ~52d
when completing). Resumable per (variant,start).

Run:  uv run python3 backtest/src/d1_universe_screen.py
"""
import concurrent.futures, importlib.util, json, os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "d1_universe_screen.json"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

SKELETON = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "2.5", "CFG_DAILY_HALT_PCT": "2.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8,
           "risk_per_trade_pct": 1.0})

VARIANTS = {
    "expanded": {},
    "expanded_no_bleed": {"EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY"},
}


def ts():
    return datetime.now().strftime("%H:%M:%S")


def eval_cell(cell):
    name, start = cell
    env = dict(SKELETON); env.update(VARIANTS[name])
    r = cs.full_two_step(env, TP, start)
    r.pop("detail", None)
    r["variant"] = name
    tag = f"total={r['total']}" if r["total"] is not None else f"FAIL({r['why']})"
    print(f"[D1] {name:>18} {start}  {tag}{' BREACH' if r['breach'] else ''}", flush=True)
    return r


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try:
            done = {(d["variant"], d["start"]): d for d in json.loads(OUT.read_text())}
        except Exception:
            pass
    cells = [(v, s) for v in VARIANTS for s in cs.TRAIN_STARTS if (v, s) not in done]
    print(f"[{ts()}] D1 universe screen: {len(cells)} cells", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(eval_cell, cells):
            results.append(o)
            OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n=== D1 universe screen (16 TRAIN starts; old-universe baseline: score -0.5..5.7, p30=0, p60=0.06) ===", flush=True)
    print(f"{'variant':>20}{'score':>8}{'p20':>6}{'p30':>6}{'p40':>6}{'p60':>6}{'breach':>8}{'medTot':>8}", flush=True)
    for name in VARIANTS:
        rows = [r for r in results if r["variant"] == name]
        if len(rows) < len(cs.TRAIN_STARTS):
            continue
        sc = cs.score_results(rows)
        print(f"{name:>20}{sc['score']:>8.1f}{sc['p20']:>6.2f}{sc['p30']:>6.2f}{sc['p40']:>6.2f}"
              f"{sc['p60']:>6.2f}{sc['breach_rate']:>8.2f}{sc['median_total']:>8}", flush=True)
    print("[d1_universe_screen] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
