#!/usr/bin/env python3
"""
E4 — the fastest ZERO-BREACH config, by focused grid instead of wide search.

Why a grid. E3 searched 11 dimensions with TPE at ~20 min/trial; 150 trials is
~50 hours, and the container reaps the process group whenever the session
idles, so it was never going to finish. The evidence already narrows what
matters, so a small deterministic grid answers the question in hours:

  * E2: risk is the dominant speed knob — 1.0% gave breach 6.2% / fastest 31d,
    1.6% gave p40 31.2% / fastest 18d but breach 25%. The answer is between.
  * E0: breaches are overnight events, so the overnight book size
    (max-per-group, max-total) is the knob that buys the breach back.

So: sweep risk DESCENDING within each overnight setting, tightest book first.
The first risk level that stays breach-free is the fastest safe config for that
book — exactly the user's question, and the descending order means we find it
without evaluating everything below it.

Other knobs stay at the values E3 t0 validated (hour 21, r_close_losing 0.0,
r_new 0.5, reduce 0.5).

Run:  uv run python3 backtest/src/e4_fastest_safe_grid.py
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
WORKERS = int(os.environ.get("E4_WORKERS", str(os.cpu_count() or 2)))

BASE_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_DAILY_HALT_PCT": "2.0", "CFG_MAX_CUM_RISK": "3.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15",
            "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
            "BROKER_TYPE": "fiveers_live", "CFG_DAILY_WALL_PCT": "3.0",
            "NIGHTLY_DERISK": "1", "NIGHTLY_DERISK_HOUR": "21",
            "NIGHTLY_R_CLOSE_LOSING": "0.0", "NIGHTLY_R_NEW": "0.5",
            "NIGHTLY_REDUCE_PCT": "0.5"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

# tightest overnight book first — a tighter book should support a higher risk
BOOKS = [(1, 2), (1, 3), (2, 4), (2, 5)]
RISKS = [1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0]      # descending: first clean one wins


def evaluate(env, tp, horizon, starts):
    """All starts, aborting on the first breach (breach is a hard reject)."""
    rows = []
    chunk = max(2, WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i in range(0, len(starts), chunk):
            futs = [ex.submit(cs.full_two_step, env, tp, s, horizon)
                    for s in starts[i:i + chunk]]
            for fut in futs:
                r = fut.result(); r.pop("detail", None); rows.append(r)
            if any(r["breach"] for r in rows):
                return {"breach_rate": round(sum(1 for r in rows if r["breach"]) / len(rows), 3),
                        "complete_rate": 0.0, "median_days": None, "fastest_days": None,
                        "p30": 0.0, "p40": 0.0, "p60": 0.0,
                        "aborted_after": len(rows)}
    n = len(rows)
    totals = sorted(r["total"] for r in rows if r["total"] is not None)
    return {"breach_rate": 0.0,
            "complete_rate": round(len(totals) / n, 3),
            "median_days": (totals[len(totals) // 2] if totals else None),
            "fastest_days": (totals[0] if totals else None),
            "p30": round(sum(1 for t in totals if t <= 30) / n, 3),
            "p40": round(sum(1 for t in totals if t <= 40) / n, 3),
            "p60": round(sum(1 for t in totals if t <= 60) / n, 3),
            "totals": totals, "aborted_after": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--holdout", action="store_true",
                    help="evaluate on HOLDOUT starts instead of TRAIN")
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    starts = cs.HOLDOUT_STARTS if args.holdout else cs.TRAIN_STARTS
    tag = "HOLDOUT" if args.holdout else "TRAIN"
    out = DOE_DIR / f"e4_grid_{tag.lower()}.json"
    res = json.loads(out.read_text()) if out.exists() else {}

    print(f"[E4] fastest-safe grid on {tag} ({len(starts)} starts), "
          f"horizon {args.horizon}d/step, {WORKERS} workers", flush=True)
    print(f"{'book':>8} {'risk':>5} {'breach':>7} {'p30':>6} {'p40':>6} "
          f"{'median':>7} {'fastest':>8} {'complete':>9}", flush=True)

    best = None
    for mpg, mtot in BOOKS:
        for risk in RISKS:
            key = f"{mpg}-{mtot}/{risk}"
            if key in res:
                m = res[key]
            else:
                env = dict(BASE_ENV)
                env.update({"NIGHTLY_MAX_PER_GROUP": str(mpg),
                            "NIGHTLY_MAX_TOTAL": str(mtot)})
                tp = dict(TP); tp["risk_per_trade_pct"] = risk
                m = evaluate(env, tp, args.horizon, starts)
                res[key] = m
                out.write_text(json.dumps(res, indent=2))
            md = "-" if m["median_days"] is None else m["median_days"]
            fd = "-" if m["fastest_days"] is None else m["fastest_days"]
            note = "" if m.get("aborted_after") is None else f"  (abort@{m['aborted_after']})"
            print(f"{mpg}/{mtot:>5} {risk:5.1f} {m['breach_rate']*100:6.1f}% "
                  f"{m['p30']*100:5.1f}% {m['p40']*100:5.1f}% {md:>7} {fd:>8} "
                  f"{m['complete_rate']*100:8.1f}%{note}", flush=True)
            if m["breach_rate"] == 0.0 and m["median_days"] is not None:
                cand = (m["p40"], m["p30"], -m["median_days"], key, m)
                if best is None or cand[:3] > best[:3]:
                    best = cand
                # descending risk: first clean level is the fastest for this book
                break

    print("", flush=True)
    if best:
        _, _, _, key, m = best
        print(f"[E4] BEST zero-breach: book/risk {key} — p30={m['p30']*100:.1f}% "
              f"p40={m['p40']*100:.1f}% median={m['median_days']}d "
              f"fastest={m['fastest_days']}d complete={m['complete_rate']*100:.0f}%", flush=True)
    else:
        print("[E4] no zero-breach cell completed", flush=True)
    print("[e4_fastest_safe_grid] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
