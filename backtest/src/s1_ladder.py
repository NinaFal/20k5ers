#!/usr/bin/env python3
"""
S1 — TP ladder / banking rate. First stage of the new round.

S0 established the constraint precisely. Everything reduces to dollars per
active trading day, and that number decomposes as:

    partial closes (TP bankings)   +$334 / active day
    full closes (the losing tail)  -$ 92 / active day
    ------------------------------------------------
    net                            +$242 / active day

To clear both steps inside 50 calendar days needs about **$300/active day**,
i.e. ~25% more. Two ways to get it, and this stage searches both at once:

  * bank MORE, or EARLIER, from the winners (the +$334 term). Targets are on
    CLOSED balance — floating profit is worth nothing to the challenge — so
    where the TPs sit and how much each one closes is the direct lever.
  * lose LESS on the tail (the -$92 term). Full-close expectancy is negative:
    39.6% win rate, avg win $120, avg loss $144. Those losers are positions
    that never reached TP1 and stopped out near -1R, so TP1's placement decides
    how many trades convert from a full -1R loss into a partial-banker with a
    trailed stop. sl_after_tp1_r has NEVER been searched.

Searches the 3 live TP levels, their close fractions, and all three stop-trail
levels. Screens on the first 30 canonical starts; the winner is re-scored on
all 100 (a 30-start result sits inside the natural 8-75 day spread S0 measured,
so screening is for ranking only, never for the final claim).

Run:  uv run python3 backtest/src/s1_ladder.py [--trials 120]
"""
import argparse, concurrent.futures, csv, importlib.util, json, os
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_e = importlib.util.spec_from_file_location("e5", str(HERE / "e5_validate_winner.py"))
e5 = importlib.util.module_from_spec(_e); _e.loader.exec_module(e5)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")
WORKERS = int(os.environ.get("S1_WORKERS", str(os.cpu_count() or 2)))
CANON = json.loads((DOE_DIR / "CANONICAL_100_STARTS.json").read_text())["starts"]
TARGET_DAYS = 50


def _suggest(trial):
    tp1 = trial.suggest_float("tp1_r_multiple", 0.25, 0.80, step=0.05)
    tp2 = trial.suggest_float("tp2_r_multiple", tp1 + 0.2, 1.80, step=0.10)
    tp3 = trial.suggest_float("tp3_r_multiple", tp2 + 0.2, 3.00, step=0.10)
    # close fractions: search the first two, give the remainder to TP3 so the
    # ladder always closes 100% by TP3 and the sum constraint cannot be violated
    c1 = trial.suggest_float("tp1_close_pct", 0.20, 0.65, step=0.05)
    c2 = trial.suggest_float("tp2_close_pct", 0.15, min(0.60, 0.95 - c1), step=0.05)
    c3 = round(1.0 - c1 - c2, 4)
    s1 = trial.suggest_float("sl_after_tp1_r", -0.20, 0.50, step=0.10)   # never searched
    s2 = trial.suggest_float("sl_after_tp2_r", max(s1, 0.0), 1.20, step=0.10)
    s3 = trial.suggest_float("sl_after_tp3_r", max(s2, 0.5), 2.20, step=0.10)
    tp = dict(e5.TP)
    tp.update({"risk_per_trade_pct": e5.WINNER_RISK,
               "tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
               "tp1_close_pct": c1, "tp2_close_pct": c2, "tp3_close_pct": c3,
               "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
               "sl_after_tp1_r": s1, "sl_after_tp2_r": s2, "sl_after_tp3_r": s3})
    trial.set_user_attr("tp3_close_pct", c3)
    return tp


def evaluate(tp, starts, horizon=75):
    """Two-step over `starts`, aborting on the first breach (hard reject)."""
    env = dict(e5.WINNER_ENV)
    rows = []
    chunk = max(2, WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i in range(0, len(starts), chunk):
            futs = [ex.submit(cs.full_two_step, env, tp, s, horizon)
                    for s in starts[i:i + chunk]]
            for f in futs:
                r = f.result(); r.pop("detail", None); rows.append(r)
            if any(r["breach"] for r in rows):
                return {"breach_rate": round(sum(1 for r in rows if r["breach"]) / len(rows), 3),
                        "p50": 0.0, "complete_rate": 0.0, "median_days": None,
                        "fastest": None, "aborted_after": len(rows)}
    n = len(rows)
    tot = sorted(r["total"] for r in rows if r.get("total") is not None)
    return {"breach_rate": 0.0,
            "complete_rate": round(len(tot) / n, 3),
            "p50": round(sum(1 for t in tot if t <= TARGET_DAYS) / n, 3),
            "median_days": (tot[len(tot) // 2] if tot else None),
            "fastest": (tot[0] if tot else None),
            "aborted_after": None}


def score_of(m):
    if m["breach_rate"] > 0:
        return -1e6 * m["breach_rate"]          # breach is a hard reject
    if not m["complete_rate"]:
        return -1000.0
    # the user's target first, then completions, then raw speed
    return 1000.0 * m["p50"] + 200.0 * m["complete_rate"] - float(m["median_days"])


PARAM_COLS = ["tp1_r_multiple", "tp2_r_multiple", "tp3_r_multiple",
              "tp1_close_pct", "tp2_close_pct",
              "sl_after_tp1_r", "sl_after_tp2_r", "sl_after_tp3_r"]
CSV_HEADER = ["trial", "score", "p50", "complete_rate", "median_days", "fastest",
              "breach_rate", "tp3_close_pct"] + PARAM_COLS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--screen", type=int, default=30)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    db = str(DOE_DIR / "stageS1.db"); csv_path = DOE_DIR / "stageS1.csv"
    screen = CANON[:args.screen]

    study = optuna.create_study(direction="maximize", study_name="stageS1",
                                storage=f"sqlite:///{db}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=42, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        # incumbent: the current ladder
        study.enqueue_trial({"tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
                             "tp1_close_pct": 0.45, "tp2_close_pct": 0.35,
                             "sl_after_tp1_r": 0.2, "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2})
        # earlier TP1 — the S0-indicated direction: convert -1R losers into bankers
        study.enqueue_trial({"tp1_r_multiple": 0.3, "tp2_r_multiple": 0.8, "tp3_r_multiple": 1.4,
                             "tp1_close_pct": 0.40, "tp2_close_pct": 0.35,
                             "sl_after_tp1_r": 0.1, "sl_after_tp2_r": 0.6, "sl_after_tp3_r": 1.2})
        # earlier still, with a breakeven-plus trail straight after TP1
        study.enqueue_trial({"tp1_r_multiple": 0.25, "tp2_r_multiple": 0.7, "tp3_r_multiple": 1.3,
                             "tp1_close_pct": 0.50, "tp2_close_pct": 0.30,
                             "sl_after_tp1_r": 0.2, "sl_after_tp2_r": 0.7, "sl_after_tp3_r": 1.3})

    def objective(trial):
        tp = _suggest(trial)
        m = evaluate(tp, screen)
        for k, v in m.items():
            trial.set_user_attr(k, v)
        return score_of(m)

    def cb(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        ua = trial.user_attrs
        row = {"trial": trial.number, "score": round(trial.value or 0, 2),
               **{k: ua.get(k) for k in ("p50", "complete_rate", "median_days",
                                         "fastest", "breach_rate", "tp3_close_pct")},
               **{k: trial.params.get(k, "") for k in PARAM_COLS}}
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADER)
            if new: w.writeheader()
            w.writerow(row)
        flag = "SAFE" if ua.get("breach_rate") == 0.0 else f"br={ua.get('breach_rate')}"
        print(f"[S1] t{trial.number:3d} {flag:>10} p50={ua.get('p50')} "
              f"median={ua.get('median_days')} fastest={ua.get('fastest')} "
              f"tp={trial.params.get('tp1_r_multiple')}/{trial.params.get('tp2_r_multiple')}"
              f"/{trial.params.get('tp3_r_multiple')} "
              f"close={trial.params.get('tp1_close_pct')}/{trial.params.get('tp2_close_pct')}"
              f"/{ua.get('tp3_close_pct')} "
              f"sl={trial.params.get('sl_after_tp1_r')}", flush=True)

    done = sum(1 for t in study.trials
               if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED))
    remaining = max(0, args.trials - done)
    print(f"[S1] ladder search — {done} done, {remaining} remaining, "
          f"screen {len(screen)} starts, target <={TARGET_DAYS}d, {WORKERS} workers", flush=True)
    if remaining:
        study.optimize(objective, n_trials=remaining, n_jobs=1,
                       callbacks=[cb], catch=(Exception,))

    safe = [t for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
            and t.user_attrs.get("breach_rate") == 0.0
            and t.user_attrs.get("median_days") is not None]
    print(f"\n[S1] {len(safe)} zero-breach configs that complete", flush=True)
    for t in sorted(safe, key=lambda t: (-(t.user_attrs.get("p50") or 0),
                                         t.user_attrs["median_days"]))[:10]:
        ua = t.user_attrs
        print(f"   t{t.number:3d} p50={ua['p50']} median={ua['median_days']}d "
              f"fastest={ua['fastest']}d complete={ua['complete_rate']}", flush=True)
    print("[s1_ladder] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
