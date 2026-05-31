#!/usr/bin/env python3
"""
Stop-loss distance optimizer with OUT-OF-SAMPLE validation.

Optimizes atr_sl_multiplier (the stop distance = N x ATR) on an in-sample
window, then re-tests the best value on a later out-of-sample window to guard
against curve-fitting.

KEY: judged on EXPECTANCY + SURVIVAL, never win rate. A wider stop almost always
*raises* win rate (fewer pierce-and-recover stop-outs) while making each loss
bigger and pushing the account into the 10% total-DD wall faster — so win rate
is exactly the wrong metric here.

Score per run:
  survivor: 1e6 + final_funded + withdrawn
  death:    survived_days*100 + funded_at_failure

Usage:
  python3 backtest/src/optimize_stoploss.py --trials 30 --jobs 3
"""
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path
import optuna

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"
REPO = HERE.parent.parent

IS_START, IS_END = os.getenv("IS_START", "2015-01-01"), os.getenv("IS_END", "2017-12-31")
OS_START, OS_END = os.getenv("OS_START", "2018-01-01"), os.getenv("OS_END", "2021-12-31")
BAL = os.getenv("OPT_BAL", "50000")


def run(sl_mult, start, end):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["TERMINAL_ON_BREACH"] = "1"
        env["SLIPPAGE_PIPS"] = "0.5"
        env["GAP_FILLS"] = "1"
        env["OPT_PARAMS"] = json.dumps({"atr_sl_multiplier": sl_mult})
        cmd = [sys.executable, str(BACKTEST), "--start", start, "--end", end,
               "--balance", BAL, "--output", td]
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
        rj = Path(td) / "results.json"
        if p.returncode != 0 or not rj.exists():
            return None
        return json.loads(rj.read_text())


def score(r):
    if r is None:
        return -1e9, {}
    fi = r.get("fail_info") or {}
    funded = float(r.get("fiveers_final_funded_level") or 0)
    withdrawn = float(r.get("fiveers_total_withdrawn") or 0)
    attrs = {"failed": bool(r.get("account_failed")),
             "final_funded": funded, "withdrawn": withdrawn,
             "max_tdd": r.get("max_tdd_pct"), "win_rate": r.get("win_rate"),
             "net_pnl": r.get("net_pnl"), "trades": r.get("total_trades"),
             "survived_days": fi.get("survived_days"),
             "funded_at_failure": fi.get("funded_level_at_failure")}
    if not attrs["failed"]:
        return 1_000_000.0 + funded + withdrawn, attrs
    return float(fi.get("survived_days") or 0) * 100.0 + float(fi.get("funded_level_at_failure") or 0), attrs


def objective(trial):
    sl = trial.suggest_float("atr_sl_multiplier", 1.0, 2.5, step=0.1)
    r = run(sl, IS_START, IS_END)
    sc, attrs = score(r)
    for k, v in attrs.items():
        trial.set_user_attr(k, v)
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=16)  # 16 steps cover 1.0-2.5
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_sl.db")
    ap.add_argument("--study", default="sl_opt")
    ap.add_argument("--out", default="/tmp/optuna_sl_results.json")
    args = ap.parse_args()

    study = optuna.create_study(direction="maximize", study_name=args.study,
                                storage=args.storage, load_if_exists=True,
                                sampler=optuna.samplers.GridSampler(
                                    {"atr_sl_multiplier": [round(1.0+0.1*i, 1) for i in range(16)]}))
    study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs)

    print("\n" + "=" * 70)
    print("IN-SAMPLE (2015-2017) ranking by score")
    print("=" * 70)
    done = [t for t in study.trials if t.value is not None]
    for t in sorted(done, key=lambda t: t.value, reverse=True):
        a = t.user_attrs
        print(f"  SL {t.params['atr_sl_multiplier']:.1f}x | "
              f"{'SURVIVE' if not a.get('failed') else 'die@'+str(a.get('survived_days'))+'d'} | "
              f"funded ${a.get('final_funded') or a.get('funded_at_failure') or 0:,.0f} | "
              f"net ${a.get('net_pnl') or 0:,.0f} | maxTDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    best_sl = study.best_trial.params["atr_sl_multiplier"]
    print(f"\nBEST IN-SAMPLE SL = {best_sl}x  → validating OUT-OF-SAMPLE (2018-2021)...")

    # OOS check: best vs the current default (1.5) on the unseen window
    results = {}
    for label, sl in [("best", best_sl), ("default_1.5", 1.5)]:
        r = run(sl, OS_START, OS_END)
        sc, attrs = score(r)
        results[label] = {"sl": sl, "score": sc, **attrs}
        print(f"  OOS {label} (SL {sl}x): "
              f"{'SURVIVE' if not attrs.get('failed') else 'die@'+str(attrs.get('survived_days'))+'d'} | "
              f"net ${attrs.get('net_pnl') or 0:,.0f} | maxTDD {attrs.get('max_tdd')}% | WR {attrs.get('win_rate')}%")

    out = {"in_sample_best_sl": best_sl,
           "in_sample": [{"sl": t.params["atr_sl_multiplier"], "score": t.value, **t.user_attrs} for t in done],
           "out_of_sample": results}
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nWritten to {args.out}")
    # Verdict
    b, d = results["best"], results["default_1.5"]
    if b["score"] > d["score"]:
        print(f"\n✅ OOS CONFIRMS: optimized SL {best_sl}x beats default 1.5x out-of-sample.")
    else:
        print(f"\n⚠️ OOS REJECTS: optimized SL {best_sl}x does NOT beat default 1.5x out-of-sample (likely overfit).")


if __name__ == "__main__":
    main()
