#!/usr/bin/env python3
"""
Generic stage runner for the 100k / 5%-wall round.

One script for every stage, so all stages share identical scoring, caching and
selection rules. A stage differs only in which parameters it opens up; nothing
else changes, which is what makes stage-to-stage comparisons meaningful.

Stages (run in this order):
  ladder   TP levels, close fractions, all three stop-trails (incl.
           sl_after_tp1_r, never searched). S0 showed the binding constraint is
           dollars per active day, and the ladder is the only lever that acts on
           conversion of existing edge into CLOSED balance rather than on the
           edge itself.
  filters  the six use_* selectivity switches — all False and never tested.
  entry    confluence / quality / ADX / ATR gates, frozen since before any of
           the wall work.
  fib      three-way calm/neutral/volatile entry depth.
  nightly  the four untuned overnight knobs plus the hour.
  risk     risk per trade, cumulative cap, position caps.
  halt     daily halt + TDD ladder tiers. LAST on purpose: it is a pure safety
           dial that trades speed for margin, so tuning it earlier would make
           every later stage optimize inside an artificially slowed system.

Each stage starts from the previous stage's surviving winner (wall5/current_best.json),
so improvements compound.

Run:  uv run python3 backtest/src/w5_stage.py --stage ladder [--trials 120] [--screen 25]
"""
import argparse, csv, importlib.util, json, os
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)


# ── per-stage search spaces ──────────────────────────────────────────────────
def space_ladder(trial, env, tp):
    tp1 = trial.suggest_float("tp1_r_multiple", 0.25, 0.90, step=0.05)
    tp2 = trial.suggest_float("tp2_r_multiple", tp1 + 0.2, 2.00, step=0.10)
    tp3 = trial.suggest_float("tp3_r_multiple", tp2 + 0.2, 3.20, step=0.10)
    c1 = trial.suggest_float("tp1_close_pct", 0.20, 0.65, step=0.05)
    c2 = trial.suggest_float("tp2_close_pct", 0.15, min(0.60, 0.95 - c1), step=0.05)
    s1 = trial.suggest_float("sl_after_tp1_r", -0.20, 0.50, step=0.10)
    s2 = trial.suggest_float("sl_after_tp2_r", max(s1, 0.0), 1.30, step=0.10)
    s3 = trial.suggest_float("sl_after_tp3_r", max(s2, 0.5), 2.40, step=0.10)
    tp.update({"tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
               "tp1_close_pct": c1, "tp2_close_pct": c2,
               "tp3_close_pct": round(1.0 - c1 - c2, 4),
               "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
               "sl_after_tp1_r": s1, "sl_after_tp2_r": s2, "sl_after_tp3_r": s3})
    return env, tp


def space_filters(trial, env, tp):
    for f in ("use_htf_filter", "use_structure_filter", "use_confirmation_filter",
              "use_fib_filter", "use_displacement_filter", "use_candle_rejection"):
        tp[f] = trial.suggest_categorical(f, [False, True])
    return env, tp


def space_entry(trial, env, tp):
    tp["trend_min_confluence"] = trial.suggest_int("trend_min_confluence", 4, 8)
    tp["range_min_confluence"] = trial.suggest_int("range_min_confluence", 2, 6)
    tp["min_quality_factors"] = trial.suggest_int("min_quality_factors", 2, 5)
    tp["atr_min_percentile"] = trial.suggest_float("atr_min_percentile", 20.0, 60.0, step=5.0)
    tp["atr_vol_ratio_range"] = trial.suggest_float("atr_vol_ratio_range", 1.0, 2.0, step=0.1)
    tp["adx_min_entry"] = trial.suggest_float("adx_min_entry", 0.0, 25.0, step=5.0)
    return env, tp


def space_fib(trial, env, tp):
    calm = trial.suggest_float("entry_fib_level_calm", 0.20, 0.55, step=0.05)
    base = trial.suggest_float("entry_fib_level", 0.35, 0.70, step=0.05)
    vol = trial.suggest_float("entry_fib_level_volatile", base, 0.90, step=0.05)
    tp["entry_fib_level_calm"] = calm
    tp["entry_fib_level"] = base
    tp["entry_fib_level_volatile"] = vol
    tp["fib_calm_ratio_threshold"] = trial.suggest_float("fib_calm_ratio_threshold", 0.70, 1.00, step=0.05)
    tp["fib_vol_ratio_threshold"] = trial.suggest_float("fib_vol_ratio_threshold", 1.00, 1.35, step=0.05)
    return env, tp


def space_nightly(trial, env, tp):
    env["NIGHTLY_DERISK_HOUR"] = str(trial.suggest_categorical("NIGHTLY_DERISK_HOUR", [17, 19, 20, 21, 22]))
    env["NIGHTLY_MAX_PER_GROUP"] = str(trial.suggest_int("NIGHTLY_MAX_PER_GROUP", 0, 3))
    env["NIGHTLY_MAX_TOTAL"] = str(trial.suggest_int("NIGHTLY_MAX_TOTAL", 0, 8))
    env["NIGHTLY_R_CLOSE_LOSING"] = str(trial.suggest_float("NIGHTLY_R_CLOSE_LOSING", -0.5, 0.5, step=0.25))
    env["NIGHTLY_R_NEW"] = str(trial.suggest_float("NIGHTLY_R_NEW", 0.25, 1.5, step=0.25))
    env["NIGHTLY_REDUCE_PCT"] = str(trial.suggest_float("NIGHTLY_REDUCE_PCT", 0.25, 1.0, step=0.25))
    return env, tp


def space_risk(trial, env, tp):
    tp["risk_per_trade_pct"] = trial.suggest_float("risk_per_trade_pct", 0.8, 3.0, step=0.1)
    env["CFG_MAX_CUM_RISK"] = str(trial.suggest_float("CFG_MAX_CUM_RISK", 2.0, 8.0, step=0.5))
    env["CORR_GROUP_CAP"] = str(trial.suggest_int("CORR_GROUP_CAP", 2, 6))
    env["MAX_TOTAL_POSITIONS"] = str(trial.suggest_categorical("MAX_TOTAL_POSITIONS", [6, 8, 10, 12, 15, 20]))
    env["RISK_CALM_MULT"] = str(trial.suggest_float("RISK_CALM_MULT", 1.0, 1.8, step=0.05))
    env["RISK_VOLATILE_MULT"] = str(trial.suggest_float("RISK_VOLATILE_MULT", 0.4, 1.0, step=0.05))
    return env, tp


def space_halt(trial, env, tp):
    env["CFG_DAILY_HALT_PCT"] = str(trial.suggest_float("CFG_DAILY_HALT_PCT", 2.0, 4.5, step=0.25))
    env["CFG_TDD_CAUTION_PCT"] = str(trial.suggest_float("CFG_TDD_CAUTION_PCT", 1.5, 4.0, step=0.5))
    env["CFG_RISK_CAUTIOUS"] = str(trial.suggest_float("CFG_RISK_CAUTIOUS", 0.3, 0.9, step=0.1))
    env["CFG_TDD_WARNING_PCT"] = str(trial.suggest_float("CFG_TDD_WARNING_PCT", 2.5, 6.0, step=0.5))
    env["CFG_RISK_CONSERVATIVE"] = str(trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.2, 0.7, step=0.1))
    env["TDD_WALL_SAFETY"] = str(trial.suggest_float("TDD_WALL_SAFETY", 2.0, 6.0, step=0.5))
    return env, tp


SPACES = {"ladder": space_ladder, "filters": space_filters, "entry": space_entry,
          "fib": space_fib, "nightly": space_nightly, "risk": space_risk,
          "halt": space_halt}


def load_current_best():
    """Start from the previous stage's survivor so improvements compound."""
    p = w5.W5_DIR / "current_best.json"
    if p.exists():
        d = json.loads(p.read_text())
        env = dict(w5.BASE_ENV); env.update(d.get("env", {}))
        tp = dict(w5.BASE_TP); tp.update(d.get("tp", {}))
        return env, tp, d.get("from_stage")
    return dict(w5.BASE_ENV), dict(w5.BASE_TP), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=list(SPACES))
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--screen", type=int, default=25)
    args = ap.parse_args()
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    st = args.stage
    cache = w5.W5_DIR / f"{st}_runcache.json"
    csv_path = w5.W5_DIR / f"{st}_trials.csv"
    db = str(w5.W5_DIR / f"{st}.db")
    screen = w5.CANON[:args.screen]
    base_env, base_tp, prev = load_current_best()

    study = optuna.create_study(direction="maximize", study_name=f"w5_{st}",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))

    def objective(trial):
        env, tp = SPACES[st](trial, dict(base_env), dict(base_tp))
        m = w5.evaluate(env, tp, screen, cache)
        for k, v in m.items():
            trial.set_user_attr(k, v)
        trial.set_user_attr("cfg_env", {k: v for k, v in env.items() if w5.BASE_ENV.get(k) != v})
        trial.set_user_attr("cfg_tp", {k: v for k, v in tp.items() if w5.BASE_TP.get(k) != v})
        return w5.score_of(m)

    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        ua = trial.user_attrs
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               **{k: ua.get(k) for k in ("p_target", "p30", "p40", "p50",
                                         "complete_rate", "median_days",
                                         "fastest", "breach_rate", "n")}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=list(row))
            if new: wr.writeheader()
            wr.writerow(row)
        flag = "SAFE" if ua.get("breach_rate") == 0.0 else f"br={ua.get('breach_rate')}"
        print(f"[{st}] t{trial.number:3d} {flag:>9} p{w5.TARGET_DAYS}={ua.get('p_target')} "
              f"p40={ua.get('p40')} p50={ua.get('p50')} "
              f"median={ua.get('median_days')} fastest={ua.get('fastest')} "
              f"n={ua.get('n')}", flush=True)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    print(f"[{st}] 5% wall | target <={w5.TARGET_DAYS}d | base from stage '{prev}' | screen {len(screen)} starts "
          f"| {done} done, {max(0, args.trials - done)} left | {w5.WORKERS} workers", flush=True)
    if args.trials > done:
        study.optimize(objective, n_trials=args.trials - done, n_jobs=1,
                       callbacks=[cb], catch=(Exception,))

    safe = [t for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
            and t.user_attrs.get("breach_rate") == 0.0
            and t.user_attrs.get("median_days") is not None]
    safe.sort(key=lambda t: (-(t.user_attrs.get("p_target") or 0), t.user_attrs["median_days"]))
    top = safe[:20]
    out = w5.W5_DIR / f"{st}_top20.json"
    w5.atomic_write(out, [{"trial": t.number, "score": t.value,
                           "p_target": t.user_attrs.get("p_target"),
                           "p30": t.user_attrs.get("p30"), "p40": t.user_attrs.get("p40"),
                           "p50": t.user_attrs.get("p50"),
                           "median_days": t.user_attrs.get("median_days"),
                           "complete_rate": t.user_attrs.get("complete_rate"),
                           "env": t.user_attrs.get("cfg_env", {}),
                           "tp": t.user_attrs.get("cfg_tp", {})} for t in top])
    print(f"\n[{st}] {len(safe)} zero-breach configs; wrote top {len(top)} -> {out.name}", flush=True)
    for t in top[:10]:
        ua = t.user_attrs
        print(f"   t{t.number:3d} p{w5.TARGET_DAYS}={ua['p_target']} p40={ua.get('p40')} "
              f"p50={ua.get('p50')} median={ua['median_days']}d fastest={ua['fastest']}d", flush=True)
    print(f"[w5_stage:{st}] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
