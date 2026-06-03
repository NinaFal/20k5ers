#!/usr/bin/env python3
"""
Stop-distance optimizer (REAL knobs) with out-of-sample validation.

The stop = wider of (ATR-stop, structural-swing-stop). The structural stop
usually dominates, so the genuine stop-distance levers are:
  - structure_sl_lookback   (StrategyParams, default 35) via OPT_PARAMS
  - CFG_STRUCT_SL_BUFFER     (ATR buffer beyond the swing, default 0.4) via env

Optimizes both on an in-sample window, then re-tests the best pair on a later
out-of-sample window vs the current default (lb=35, buf=0.4) and prints a
CONFIRM/REJECT verdict. Judged on EXPECTANCY+SURVIVAL, never win rate.

Usage: python3 backtest/src/optimize_stoploss.py --jobs 3
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

LOOKBACKS = [15, 20, 25, 35, 45, 60]
BUFFERS = [0.2, 0.4, 0.6, 0.9, 1.2]


def run(lookback, buffer, start, end):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["TERMINAL_ON_BREACH"] = "1"
        env["SLIPPAGE_PIPS"] = "0.5"
        env["GAP_FILLS"] = "1"
        env["CFG_STRUCT_SL_BUFFER"] = str(buffer)
        env["OPT_PARAMS"] = json.dumps({"structure_sl_lookback": int(lookback)})
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
    return float(fi.get("survived_days") or 0) * 100.0 + float(fi.get("funded_at_failure") or 0), attrs


def objective(trial):
    lb = trial.suggest_categorical("structure_sl_lookback", LOOKBACKS)
    buf = trial.suggest_categorical("struct_sl_buffer", BUFFERS)
    r = run(lb, buf, IS_START, IS_END)
    sc, attrs = score(r)
    for k, v in attrs.items():
        trial.set_user_attr(k, v)
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_sl2.db")
    ap.add_argument("--study", default="sl_real")
    ap.add_argument("--out", default="/tmp/optuna_sl2_results.json")
    args = ap.parse_args()

    n = len(LOOKBACKS) * len(BUFFERS)
    study = optuna.create_study(direction="maximize", study_name=args.study,
                                storage=args.storage, load_if_exists=True,
                                sampler=optuna.samplers.GridSampler(
                                    {"structure_sl_lookback": LOOKBACKS,
                                     "struct_sl_buffer": BUFFERS}))
    study.optimize(objective, n_trials=n, n_jobs=args.jobs)

    done = [t for t in study.trials if t.value is not None]
    print("\n" + "=" * 78)
    print(f"IN-SAMPLE ({IS_START}..{IS_END}) — top 10 by score")
    print("=" * 78)
    for t in sorted(done, key=lambda t: t.value, reverse=True)[:10]:
        a = t.user_attrs
        f = a.get('final_funded') or a.get('funded_at_failure') or 0
        print(f"  lb={t.params['structure_sl_lookback']:>2} buf={t.params['struct_sl_buffer']:.1f} | "
              f"{'SURV' if not a.get('failed') else 'die@'+str(a.get('survived_days'))+'d':>8} | "
              f"funded ${f:>9,.0f} | net ${a.get('net_pnl') or 0:>9,.0f} | "
              f"maxTDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    best = study.best_trial.params
    print(f"\nBEST IN-SAMPLE: lb={best['structure_sl_lookback']} buf={best['struct_sl_buffer']}")
    print(f"Validating OUT-OF-SAMPLE ({OS_START}..{OS_END}) vs default (lb=35, buf=0.4)...")

    res = {}
    for label, lb, buf in [("best", best['structure_sl_lookback'], best['struct_sl_buffer']),
                           ("default", 35, 0.4)]:
        r = run(lb, buf, OS_START, OS_END)
        sc, a = score(r)
        res[label] = {"lb": lb, "buf": buf, "score": sc, **a}
        f = a.get('final_funded') or a.get('funded_at_failure') or 0
        print(f"  OOS {label:8} (lb={lb} buf={buf}): "
              f"{'SURV' if not a.get('failed') else 'die@'+str(a.get('survived_days'))+'d'} | "
              f"funded ${f:,.0f} | net ${a.get('net_pnl') or 0:,.0f} | maxTDD {a.get('max_tdd')}% | WR {a.get('win_rate')}%")

    out = {"in_sample": [{**t.params, "score": t.value, **t.user_attrs} for t in done],
           "oos": res}
    Path(args.out).write_text(json.dumps(out, indent=2))
    verdict = "✅ CONFIRM: optimized beats default OOS" if res["best"]["score"] > res["default"]["score"] \
        else "⚠️ REJECT: optimized does NOT beat default OOS (overfit)"
    print(f"\n{verdict}")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
