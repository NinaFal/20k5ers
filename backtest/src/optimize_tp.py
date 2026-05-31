#!/usr/bin/env python3
"""
Reward:Risk / TP-structure optimizer with out-of-sample validation.

The strategy is ~52% WR at ~1:1 R:R (near break-even). The TP ladder closes 60%
of every position at just 1.1R, which caps average reward. This sweep tunes the
TP R-multiples and the close-percentage distribution to lift EXPECTANCY (R per
trade) — the only lever that can push past break-even.

Tuned (all valid StrategyParams, set via OPT_PARAMS):
  tp1_r_multiple, tp2_r_multiple, tp3_r_multiple   (TP4=tp3+1, TP5=tp3+2 derived)
  tp1_close_pct, tp2_close_pct, tp3_close_pct      (TP4/TP5 split the remainder)

Constraints: TP levels strictly increasing; close pcts sum < 1.0 (remainder
rides to TP5). Judged on EXPECTANCY+SURVIVAL, validated OOS.

Usage: python3 backtest/src/optimize_tp.py --trials 50 --jobs 3
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

# Best drawdown-recovery config (cfg#2) baked in so we tune TP on top of a
# survivable risk ladder, not the fragile default.
BASE_ENV = {
    "TERMINAL_ON_BREACH": "1", "SLIPPAGE_PIPS": "0.5", "GAP_FILLS": "1",
    "CORR_GROUP_CAP": "0", "CFG_TDD_CAUTION_PCT": "4.5", "CFG_RISK_CAUTIOUS": "0.4",
    "CFG_TDD_WARNING_PCT": "6.5", "CFG_RISK_CONSERVATIVE": "0.4",
    "CFG_TDD_EMERGENCY_PCT": "7.0", "CFG_RISK_ULTRASAFE": "0.25", "TDD_EMERGENCY_HALT": "0",
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
    tp1 = trial.suggest_float("tp1_r_multiple", 0.4, 1.2, step=0.1)
    tp2 = trial.suggest_float("tp2_r_multiple", tp1 + 0.3, 2.5, step=0.1)
    tp3 = trial.suggest_float("tp3_r_multiple", tp2 + 0.3, 4.0, step=0.1)
    c1 = trial.suggest_float("tp1_close_pct", 0.10, 0.50, step=0.05)
    c2 = trial.suggest_float("tp2_close_pct", 0.10, 0.50, step=0.05)
    c3 = trial.suggest_float("tp3_close_pct", 0.05, 0.30, step=0.05)
    if c1 + c2 + c3 > 0.90:   # leave >=10% to ride to TP4/TP5
        raise optuna.TrialPruned()
    rem = round(1.0 - c1 - c2 - c3, 4)
    return {"tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
            "tp1_close_pct": c1, "tp2_close_pct": c2, "tp3_close_pct": c3,
            "tp4_close_pct": round(rem / 2, 4), "tp5_close_pct": round(rem / 2, 4)}


def objective(trial):
    p = make_params(trial)
    r = run(p, IS_START, IS_END)
    sc, a = score(r)
    for k, v in a.items():
        trial.set_user_attr(k, v)
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_tp.db")
    ap.add_argument("--study", default="tp_opt")
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
    for t in sorted(done, key=lambda t: t.value, reverse=True)[:10]:
        a = t.user_attrs; p = t.params
        f = a.get("final_funded") or a.get("funded_at_failure") or 0
        print(f"  TP {p['tp1_r_multiple']:.1f}/{p['tp2_r_multiple']:.1f}/{p['tp3_r_multiple']:.1f}R "
              f"close {p['tp1_close_pct']:.2f}/{p['tp2_close_pct']:.2f}/{p['tp3_close_pct']:.2f} | "
              f"{'SURV' if not a.get('failed') else 'die'} | funded ${f:,.0f} | "
              f"net ${a.get('net_pnl') or 0:,.0f} | TDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    bp = make_params_from(study.best_trial.params)
    print(f"\nBEST IN-SAMPLE → validating OOS ({OS_START}..{OS_END}) vs DEFAULT TP...")
    res = {}
    default_tp = {"tp1_r_multiple": 0.6, "tp2_r_multiple": 1.1, "tp3_r_multiple": 1.8,
                  "tp1_close_pct": 0.20, "tp2_close_pct": 0.60, "tp3_close_pct": 0.10,
                  "tp4_close_pct": 0.05, "tp5_close_pct": 0.05}
    for label, p in [("best", bp), ("default", default_tp)]:
        r = run(p, OS_START, OS_END); sc, a = score(r)
        res[label] = {"score": sc, **a, "params": p}
        f = a.get("final_funded") or a.get("funded_at_failure") or 0
        print(f"  OOS {label:8}: {'SURV' if not a.get('failed') else 'die@'+str(a.get('survived_days'))+'d'} | "
              f"funded ${f:,.0f} | net ${a.get('net_pnl') or 0:,.0f} | TDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    Path(args.out).write_text(json.dumps(
        {"in_sample": [{**t.params, "score": t.value, **t.user_attrs} for t in done], "oos": res}, indent=2))
    print("\n" + ("✅ CONFIRM: optimized TP beats default OOS" if res["best"]["score"] > res["default"]["score"]
                  else "⚠️ REJECT: optimized TP does NOT beat default OOS (overfit)"))
    print(f"Written to {args.out}")


def make_params_from(prm):
    c1, c2, c3 = prm["tp1_close_pct"], prm["tp2_close_pct"], prm["tp3_close_pct"]
    rem = round(1.0 - c1 - c2 - c3, 4)
    return {"tp1_r_multiple": prm["tp1_r_multiple"], "tp2_r_multiple": prm["tp2_r_multiple"],
            "tp3_r_multiple": prm["tp3_r_multiple"], "tp1_close_pct": c1, "tp2_close_pct": c2,
            "tp3_close_pct": c3, "tp4_close_pct": round(rem / 2, 4), "tp5_close_pct": round(rem / 2, 4)}


if __name__ == "__main__":
    main()
