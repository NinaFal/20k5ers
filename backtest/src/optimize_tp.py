#!/usr/bin/env python3
"""
Combined TP-structure + trailing-stop optimizer with out-of-sample validation.

Tunes the full 5-TP ladder AND the trailing-stop levels on top of the best
drawdown-recovery config (cfg#2), so we optimize reward capture + profit-locking
on a base that already survives the 10% wall.

Tuned (all valid StrategyParams via OPT_PARAMS):
  Levels:   tp1/tp2/tp3/tp4/tp5_r_multiple  (strictly increasing)
  Sizing:   tp1/tp2/tp3/tp4/tp5_close_pct   (sum ~ 1.0)
  Trailing: sl_after_tp2_r, sl_after_tp3_r, sl_after_tp4_r

Scored on EXPECTANCY+SURVIVAL (survivor = 1e6 + funded + withdrawn). In-sample
2015-2017, OOS-validated 2018-2021 vs the live current_params baseline, with a
CONFIRM/REJECT verdict.

Usage: python3 backtest/src/optimize_tp.py --trials 60 --jobs 3
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

# Surviving drawdown-recovery base (cfg#2) baked in.
BASE_ENV = {
    "TERMINAL_ON_BREACH": "1", "SLIPPAGE_PIPS": "0.5", "GAP_FILLS": "1",
    "CORR_GROUP_CAP": "0", "CFG_TDD_CAUTION_PCT": "4.5", "CFG_RISK_CAUTIOUS": "0.4",
    "CFG_TDD_WARNING_PCT": "6.5", "CFG_RISK_CONSERVATIVE": "0.4",
    "CFG_TDD_EMERGENCY_PCT": "7.0", "CFG_RISK_ULTRASAFE": "0.25", "TDD_EMERGENCY_HALT": "0",
}

# Live current_params.json baseline (for OOS comparison).
DEFAULT_TP = {
    "tp1_r_multiple": 0.6, "tp2_r_multiple": 0.9, "tp3_r_multiple": 1.3,
    "tp4_r_multiple": 2.0, "tp5_r_multiple": 3.5,
    "tp1_close_pct": 0.277, "tp2_close_pct": 0.295, "tp3_close_pct": 0.117,
    "tp4_close_pct": 0.284, "tp5_close_pct": 0.027,
    "sl_after_tp2_r": 0.65, "sl_after_tp3_r": 0.95, "sl_after_tp4_r": 0.95,
}


def run(params, start, end):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ); env.update(BASE_ENV)
        env["OPT_PARAMS"] = json.dumps(params)
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
    a = {"failed": bool(r.get("account_failed")), "final_funded": funded,
         "withdrawn": withdrawn, "max_tdd": r.get("max_tdd_pct"),
         "win_rate": r.get("win_rate"), "net_pnl": r.get("net_pnl"),
         "trades": r.get("total_trades"), "survived_days": fi.get("survived_days"),
         "funded_at_failure": fi.get("funded_level_at_failure")}
    if not a["failed"]:
        return 1_000_000.0 + funded + withdrawn, a
    return float(fi.get("survived_days") or 0) * 100.0 + float(fi.get("funded_at_failure") or 0), a


def make_params(trial):
    tp1 = trial.suggest_float("tp1_r_multiple", 0.4, 1.0, step=0.1)
    tp2 = trial.suggest_float("tp2_r_multiple", tp1 + 0.2, 1.8, step=0.1)
    tp3 = trial.suggest_float("tp3_r_multiple", tp2 + 0.2, 2.8, step=0.1)
    tp4 = trial.suggest_float("tp4_r_multiple", tp3 + 0.3, 4.0, step=0.1)
    tp5 = trial.suggest_float("tp5_r_multiple", tp4 + 0.3, 6.0, step=0.1)
    c1 = trial.suggest_float("tp1_close_pct", 0.10, 0.45, step=0.05)
    c2 = trial.suggest_float("tp2_close_pct", 0.10, 0.45, step=0.05)
    c3 = trial.suggest_float("tp3_close_pct", 0.05, 0.30, step=0.05)
    c4 = trial.suggest_float("tp4_close_pct", 0.05, 0.30, step=0.05)
    if c1 + c2 + c3 + c4 > 0.92:   # leave >=8% to ride to TP5
        raise optuna.TrialPruned()
    c5 = round(1.0 - c1 - c2 - c3 - c4, 4)
    # trailing levels: must stay below the TP they trail to, and increasing
    s2 = trial.suggest_float("sl_after_tp2_r", 0.2, min(tp1, 1.0), step=0.05)
    s3 = trial.suggest_float("sl_after_tp3_r", s2, min(tp2, 1.6), step=0.05)
    s4 = trial.suggest_float("sl_after_tp4_r", s3, min(tp3, 2.2), step=0.05)
    return {"tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
            "tp4_r_multiple": tp4, "tp5_r_multiple": tp5,
            "tp1_close_pct": c1, "tp2_close_pct": c2, "tp3_close_pct": c3,
            "tp4_close_pct": c4, "tp5_close_pct": c5,
            "sl_after_tp2_r": s2, "sl_after_tp3_r": s3, "sl_after_tp4_r": s4}


def objective(trial):
    p = make_params(trial)
    sc, a = score(run(p, IS_START, IS_END))
    for k, v in a.items():
        trial.set_user_attr(k, v)
    trial.set_user_attr("params", p)
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_tp.db")
    ap.add_argument("--study", default="tp_trail")
    ap.add_argument("--out", default="/tmp/optuna_tp_results.json")
    args = ap.parse_args()

    study = optuna.create_study(direction="maximize", study_name=args.study,
                                storage=args.storage, load_if_exists=True)
    study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs)

    done = [t for t in study.trials if t.value is not None]
    surv = [t for t in done if t.user_attrs.get("failed") is False]
    print("\n" + "=" * 78)
    print(f"IN-SAMPLE ({IS_START}..{IS_END}): {len(done)} trials, {len(surv)} survivors")
    print("=" * 78)
    for t in sorted(done, key=lambda t: t.value, reverse=True)[:8]:
        a = t.user_attrs; p = t.params
        f = a.get("final_funded") or a.get("funded_at_failure") or 0
        print(f"  TP {p['tp1_r_multiple']:.1f}/{p['tp2_r_multiple']:.1f}/{p['tp3_r_multiple']:.1f}/"
              f"{p['tp4_r_multiple']:.1f}/{p['tp5_r_multiple']:.1f}R | "
              f"{'SURV' if not a.get('failed') else 'die'} | funded ${f:,.0f} | "
              f"net ${a.get('net_pnl') or 0:,.0f} | TDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    bp = study.best_trial.user_attrs["params"]
    print(f"\nBEST IN-SAMPLE → validating OOS ({OS_START}..{OS_END}) vs live-params baseline...")
    res = {}
    for label, p in [("best", bp), ("live_default", DEFAULT_TP)]:
        sc, a = score(run(p, OS_START, OS_END))
        res[label] = {"score": sc, **a, "params": p}
        f = a.get("final_funded") or a.get("funded_at_failure") or 0
        print(f"  OOS {label:13}: {'SURV' if not a.get('failed') else 'die@'+str(a.get('survived_days'))+'d'} | "
              f"funded ${f:,.0f} | net ${a.get('net_pnl') or 0:,.0f} | TDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    Path(args.out).write_text(json.dumps(
        {"in_sample": [{"score": t.value, **t.user_attrs} for t in done], "oos": res}, indent=2))
    print("\n" + ("✅ CONFIRM: optimized TP+trail beats live baseline OOS"
                  if res["best"]["score"] > res["live_default"]["score"]
                  else "⚠️ REJECT: optimized does NOT beat live baseline OOS (overfit)"))
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
