#!/usr/bin/env python3
"""
E2 — validate NIGHTLY_DERISK across all 16 TRAIN starts (3% wall).

E0 showed 95.5% of breach-day loss comes from positions held overnight, and a
single A/B window turned a day-2 breach into a day-17 Step-1 pass. One window
proves nothing, so this runs the full two-step challenge on every TRAIN start
with the lever off vs on, at matched risk.

Arms are deliberately paired: the same skeleton, same risk, only the overnight
control differs — so any change in breach rate or speed is attributable to it.

Run:  uv run python3 backtest/src/e2_nightly_validate.py [--risk 1.0 1.6] [--horizon 90]
"""
import argparse, concurrent.futures, importlib.util, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")
WORKERS = int(os.environ.get("E2_WORKERS", str(os.cpu_count() or 2)))

BASE_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_DAILY_HALT_PCT": "2.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15",
            "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
            "BROKER_TYPE": "fiveers_live", "CFG_DAILY_WALL_PCT": "3.0"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

NIGHTLY_ON = {"NIGHTLY_DERISK": "1", "NIGHTLY_DERISK_HOUR": "21",
              "NIGHTLY_MAX_PER_GROUP": "2", "NIGHTLY_MAX_TOTAL": "5",
              "NIGHTLY_R_CLOSE_LOSING": "0.0", "NIGHTLY_R_NEW": "0.5",
              "NIGHTLY_REDUCE_PCT": "0.5"}


def evaluate(env, tp, horizon):
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(cs.full_two_step, env, tp, s, horizon) for s in cs.TRAIN_STARTS]
        for fut in futs:
            r = fut.result(); r.pop("detail", None); rows.append(r)
    n = len(rows)
    totals = sorted(r["total"] for r in rows if r["total"] is not None)
    return {
        "breach_rate": round(sum(1 for r in rows if r["breach"]) / n, 3),
        "complete_rate": round(len(totals) / n, 3),
        "median_days": (totals[len(totals) // 2] if totals else None),
        "fastest_days": (totals[0] if totals else None),
        "p30": round(sum(1 for t in totals if t <= 30) / n, 3),
        "p40": round(sum(1 for t in totals if t <= 40) / n, 3),
        "p60": round(sum(1 for t in totals if t <= 60) / n, 3),
        "totals": totals, "n": n,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--risk", type=float, nargs="*", default=[1.0, 1.6])
    ap.add_argument("--horizon", type=int, default=90)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    out = DOE_DIR / "e2_nightly_validate.json"
    res = json.loads(out.read_text()) if out.exists() else {}

    print(f"[E2] NIGHTLY_DERISK A/B, {len(cs.TRAIN_STARTS)} TRAIN starts, "
          f"horizon {args.horizon}d/step, {WORKERS} workers", flush=True)
    print(f"{'risk':>5} {'arm':>6} {'breach':>7} {'complete':>9} {'median':>7} "
          f"{'fastest':>8} {'p30':>6} {'p40':>6} {'p60':>6}", flush=True)
    for risk in args.risk:
        for arm in ("off", "on"):
            key = f"{risk}/{arm}"
            if key in res:
                m = res[key]
            else:
                env = dict(BASE_ENV)
                if arm == "on":
                    env.update(NIGHTLY_ON)
                tp = dict(TP); tp["risk_per_trade_pct"] = risk
                m = evaluate(env, tp, args.horizon)
                res[key] = m
                out.write_text(json.dumps(res, indent=2))
            md = "-" if m["median_days"] is None else m["median_days"]
            fd = "-" if m["fastest_days"] is None else m["fastest_days"]
            print(f"{risk:5.1f} {arm:>6} {m['breach_rate']*100:6.1f}% "
                  f"{m['complete_rate']*100:8.1f}% {md:>7} {fd:>8} "
                  f"{m['p30']*100:5.1f}% {m['p40']*100:5.1f}% {m['p60']*100:5.1f}%", flush=True)

    print("\n[e2_nightly_validate] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
