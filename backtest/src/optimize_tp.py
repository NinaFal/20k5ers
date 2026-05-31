#!/usr/bin/env python3
"""
Risk-aware, multi-year cold-start TP-structure + trailing-stop optimizer.

WHY THIS REPLACED THE OLD SINGLE-PERIOD SWEEP
---------------------------------------------
The previous optimizer (a) trained only on a single continuous 2015-2017 run,
(b) scored survivors as `1e6 + funded + withdrawn` with NO reward for drawdown
margin, and (c) ran on an engine that didn't flag 10% total-DD breaches as
failures. The result: it selected a config that lives at the 10% wall and blows
up on a cold-start 2020 (and the live baseline blows up cold-start 2024) — the
killer regimes were never in training, and nothing in the objective punished
wall-hugging.

This version:
  • Trains across MULTIPLE cold-start years (each Jan1-Dec31 from a fresh $50k),
    including the regimes that actually breach, so the optimizer sees them.
  • Scores each year risk-adjusted: net P&L MINUS a quadratic penalty for how
    close max-TDD/max-DDD pressed their walls. Margin is rewarded, not ignored.
  • Aggregates with WORST-CASE emphasis (min year + small mean), so a config must
    survive every regime with margin — one breach sinks the whole trial.
  • Relies on the fixed engine where a 10% total-DD breach sets account_failed.

In-sample = regime-diverse year set (incl. 2020 crisis). OOS = held-out years
(incl. 2024, the live-baseline killer) validated vs both the live baseline and
the old aggressive "winner", with a CONFIRM/REJECT verdict on risk-adjusted OOS.

Usage: python3 backtest/src/optimize_tp.py --trials 48 --jobs 4
"""
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path
import optuna

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"
REPO = HERE.parent.parent

# Cold-start year sets (each year is an independent fresh-$50k run). IS includes
# the 2020 crisis that killed the old winner; OOS holds out 2024 (live killer).
IS_YEARS = [int(y) for y in os.getenv("IS_YEARS", "2016,2018,2020,2022,2023").split(",")]
OOS_YEARS = [int(y) for y in os.getenv("OOS_YEARS", "2015,2017,2019,2021,2024").split(",")]
BAL = os.getenv("OPT_BAL", "50000")

# Risk-margin penalty knobs. Penalty kicks in past the target and grows
# quadratically, so a survivor at 9.9% TDD scores far below one at 6%.
TDD_TARGET = float(os.getenv("TDD_TARGET", "6.0"))   # % TDD with no penalty
DDD_TARGET = float(os.getenv("DDD_TARGET", "3.5"))   # % DDD with no penalty
MARGIN_K = float(os.getenv("MARGIN_K", "8000"))      # $/pp² past TDD target
DDD_K = float(os.getenv("DDD_K", "10000"))           # $/pp² past DDD target
BREACH_FLOOR = -1_000_000.0                          # any breach => deeply negative

# Surviving drawdown-recovery base (cfg#2) baked in.
BASE_ENV = {
    "TERMINAL_ON_BREACH": "1", "SLIPPAGE_PIPS": "0.5", "GAP_FILLS": "1",
    "CORR_GROUP_CAP": "0", "CFG_TDD_CAUTION_PCT": "4.5", "CFG_RISK_CAUTIOUS": "0.4",
    "CFG_TDD_WARNING_PCT": "6.5", "CFG_RISK_CONSERVATIVE": "0.4",
    "CFG_TDD_EMERGENCY_PCT": "7.0", "CFG_RISK_ULTRASAFE": "0.25", "TDD_EMERGENCY_HALT": "0",
}

# Live current_params.json baseline (blows up cold-start 2024).
DEFAULT_TP = {
    "tp1_r_multiple": 0.6, "tp2_r_multiple": 0.9, "tp3_r_multiple": 1.3,
    "tp4_r_multiple": 2.0, "tp5_r_multiple": 3.5,
    "tp1_close_pct": 0.277, "tp2_close_pct": 0.295, "tp3_close_pct": 0.117,
    "tp4_close_pct": 0.284, "tp5_close_pct": 0.027,
    "sl_after_tp2_r": 0.65, "sl_after_tp3_r": 0.95, "sl_after_tp4_r": 0.95,
}

# Old aggressive winner (blows up cold-start 2020) — kept for OOS comparison.
WINNER = {
    "tp1_r_multiple": 0.9, "tp2_r_multiple": 1.8, "tp3_r_multiple": 2.5,
    "tp4_r_multiple": 3.2, "tp5_r_multiple": 5.0,
    "tp1_close_pct": 0.15, "tp2_close_pct": 0.15, "tp3_close_pct": 0.10,
    "tp4_close_pct": 0.10, "tp5_close_pct": 0.50,
    "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 0.55, "sl_after_tp4_r": 0.7,
}


def run(params, start, end):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ); env.update(BASE_ENV)
        env["OPT_PARAMS"] = json.dumps(params)
        cmd = [sys.executable, str(BACKTEST), "--start", start, "--end", end,
               "--balance", BAL, "--output", td, "--quiet"]
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
        rj = Path(td) / "results.json"
        if p.returncode != 0 or not rj.exists():
            return None
        return json.loads(rj.read_text())


def year_score(r):
    """Risk-adjusted score for one cold-start year: net P&L minus a quadratic
    penalty for pressing the TDD/DDD walls. A breach is floored deeply negative,
    less-bad the longer the account survived before dying."""
    if r is None:
        return -1e9, {}
    failed = bool(r.get("account_failed"))
    tdd = float(r.get("max_tdd_pct") or 0)
    ddd = float(r.get("max_ddd_pct") or 0)
    net = float(r.get("net_pnl") or 0)
    fi = r.get("fail_info") or {}
    a = {"failed": failed, "max_tdd": tdd, "max_ddd": ddd, "net_pnl": round(net),
         "survived_days": fi.get("survived_days"),
         "final_funded": r.get("fiveers_final_funded_level"),
         "win_rate": r.get("win_rate"), "trades": r.get("total_trades")}
    if failed:
        return BREACH_FLOOR + float(fi.get("survived_days") or 0), a
    tdd_pen = MARGIN_K * max(0.0, tdd - TDD_TARGET) ** 2
    ddd_pen = DDD_K * max(0.0, ddd - DDD_TARGET) ** 2
    return net - tdd_pen - ddd_pen, a


def eval_config(params, years):
    """Score a config across cold-start years. Worst year dominates (forces
    every regime to survive with margin); mean breaks ties on profitability."""
    scores, attrs = [], {}
    for y in years:
        s, a = year_score(run(params, f"{y}-01-01", f"{y}-12-31"))
        scores.append(s); attrs[y] = a
    agg = min(scores) + 0.25 * (sum(scores) / len(scores))
    return agg, scores, attrs


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
    agg, scores, attrs = eval_config(p, IS_YEARS)
    trial.set_user_attr("params", p)
    trial.set_user_attr("per_year", {y: {"score": round(s), **a}
                                     for (y, a), s in zip(attrs.items(), scores)})
    trial.set_user_attr("n_breached", sum(1 for a in attrs.values() if a.get("failed")))
    trial.set_user_attr("worst_tdd", max((a.get("max_tdd") or 0) for a in attrs.values()))
    trial.set_user_attr("worst_ddd", max((a.get("max_ddd") or 0) for a in attrs.values()))
    trial.set_user_attr("sum_net", round(sum((a.get("net_pnl") or 0) for a in attrs.values())))
    return agg


def oos_report(label, params):
    """Validate a config across the held-out OOS years (cold-start each)."""
    rows, scores = {}, []
    for y in OOS_YEARS:
        r = run(params, f"{y}-01-01", f"{y}-12-31")
        s, a = year_score(r)
        scores.append(s); rows[y] = a
    breaches = [y for y, a in rows.items() if a.get("failed")]
    summary = {
        "params": params, "per_year": rows,
        "breaches": breaches, "n_breached": len(breaches),
        "worst_tdd": max((a.get("max_tdd") or 0) for a in rows.values()),
        "worst_ddd": max((a.get("max_ddd") or 0) for a in rows.values()),
        "sum_net": round(sum((a.get("net_pnl") or 0) for a in rows.values())),
        "agg_score": round(min(scores) + 0.25 * (sum(scores) / len(scores))),
    }
    print(f"\n  OOS {label}:")
    print(f"    {'year':6}{'surv':>6}{'net':>11}{'TDD%':>7}{'DDD%':>7}")
    for y in OOS_YEARS:
        a = rows[y]
        sv = 'OK' if not a.get('failed') else f"FAIL@{a.get('survived_days')}d"
        print(f"    {y:<6}{sv:>6}{(a.get('net_pnl') or 0):>11,.0f}"
              f"{a.get('max_tdd') or 0:>7}{a.get('max_ddd') or 0:>7}")
    print(f"    => breaches {len(breaches)} | worst TDD {summary['worst_tdd']}% | "
          f"worst DDD {summary['worst_ddd']}% | sum net ${summary['sum_net']:,.0f}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=48)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_tp.db")
    ap.add_argument("--study", default="tp_trail_riskaware")
    ap.add_argument("--out", default="/tmp/optuna_tp_results.json")
    args = ap.parse_args()

    print(f"IS years: {IS_YEARS} | OOS years: {OOS_YEARS}")
    print(f"penalties: TDD>{TDD_TARGET}%*{MARGIN_K}/pp² | DDD>{DDD_TARGET}%*{DDD_K}/pp²")

    study = optuna.create_study(direction="maximize", study_name=args.study,
                                storage=args.storage, load_if_exists=True)
    study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs)

    done = [t for t in study.trials if t.value is not None]
    clean = [t for t in done if t.user_attrs.get("n_breached") == 0]
    print("\n" + "=" * 78)
    print(f"IN-SAMPLE {IS_YEARS}: {len(done)} trials, {len(clean)} survived ALL years")
    print("=" * 78)
    for t in sorted(done, key=lambda t: t.value, reverse=True)[:8]:
        a, p = t.user_attrs, t.params
        print(f"  TP {p['tp1_r_multiple']:.1f}/{p['tp2_r_multiple']:.1f}/{p['tp3_r_multiple']:.1f}/"
              f"{p['tp4_r_multiple']:.1f}/{p['tp5_r_multiple']:.1f}R | "
              f"breach {a.get('n_breached')} | worstTDD {a.get('worst_tdd')}% | "
              f"worstDDD {a.get('worst_ddd')}% | sumNet ${a.get('sum_net') or 0:,.0f} | "
              f"score {t.value:,.0f}")

    # Prefer the best trial that survived every IS year; fall back to best score.
    pool = clean or done
    best = max(pool, key=lambda t: t.value)
    bp = best.user_attrs["params"]
    print(f"\nBEST (survives all IS={best.user_attrs.get('n_breached')==0}) → OOS validation {OOS_YEARS}")

    res = {"best": oos_report("optimized", bp),
           "live_default": oos_report("live_default", DEFAULT_TP),
           "winner_old": oos_report("winner_old", WINNER)}

    Path(args.out).write_text(json.dumps({
        "is_years": IS_YEARS, "oos_years": OOS_YEARS,
        "in_sample": [{"score": t.value, **t.user_attrs} for t in done],
        "oos": res}, indent=2))

    b, l = res["best"], res["live_default"]
    confirm = (b["n_breached"] == 0 and b["worst_tdd"] <= l["worst_tdd"]
               and b["agg_score"] >= l["agg_score"])
    print("\n" + ("✅ CONFIRM: optimized survives all OOS years with better margin "
                  "and risk-adjusted score than the live baseline"
                  if confirm else
                  "⚠️ REJECT: optimized does not clearly beat live baseline on "
                  "risk-adjusted OOS (see breaches / worst-TDD above)"))
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
