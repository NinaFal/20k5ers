#!/usr/bin/env python3
"""
Survival optimizer — minimise FAILED ATTEMPTS, on windows that actually fail.

The round's seven stages all optimised for speed and all reported
breach_rate = 0.000 for their best trials. That was not a weak penalty term; it
was an empty sample. The canonical 25 screen starts span 2016-01-18..2018-02-15,
and across the full 100-start holdout that period produced ZERO breaches in 37
starts. Four of the five stalls sit in early 2015, also outside it. The screen
could not see either failure mode, so no objective defined on it could reduce
them.

This screens on 2019+ windows instead, where all 7 holdout breaches occurred.

OBJECTIVE. In the challenge phase a breach and a stall cost the same thing — the
fee — so both are counted as failures. Breaches are weighted more heavily anyway,
because a config that breaches during a challenge is the same config that will
later hold a funded account, where a breach costs the account rather than the
entry fee. Speed still matters, but as a tiebreaker rather than the target:

    score = 100*passes - 250*breaches - 100*stalls - median_days

so one avoided breach outweighs two-and-a-half extra passes, and no amount of
speed buys back a lost account.

COST, stated honestly. Resolving a ~10% failure rate needs many windows per
trial and there is no way around that: at 30 starts the baseline shows roughly
3 breaches, so an arm reaching 1 is suggestive and an arm reaching 0 is worth
confirming — but 3 vs 2 is noise. Each trial is 30 full two-step challenges with
no early abort until the config is clearly worse than baseline, which is roughly
40 minutes. This is a long run. It caches per (config, start) and commits as it
goes, so restarts cost one start, not the study.

WHAT IT CANNOT DO. Selecting the best of N trials on 30 shared windows is the
same winner's curse that put the baseline at 0/25 and then 7/100. Anything this
produces is a CANDIDATE and must be re-measured on the 33 held-out 2019+ starts
plus the 37 pre-2019 ones before it replaces the frozen baseline.

Run:  uv run python3 backtest/src/w5_survival.py [--trials 80]
"""
import argparse, csv, importlib.util, json, random
from pathlib import Path

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

SEED = 20260812
N_SCREEN = 30
# Stop a trial once it is clearly WORSE than the incumbent. The screen is
# case-enriched with all 7 known-breaching windows, so the incumbent scores 7 —
# an earlier value of 5 aborted the incumbent itself, leaving the study with a
# penalised score as its only reference point.
ABORT_AT = 8
CACHE = w5.W5_DIR / "survival_runcache.json"
CSV = w5.W5_DIR / "survival_trials.csv"
DB = str(w5.W5_DIR / "survival.db")
SPLIT = w5.W5_DIR / "survival_split.json"


def screen_and_holdout():
    """30 screen starts: ALL 7 known-breaching windows plus 23 random 2019+ ones.

    A plain random draw from the 63 hard starts caught 1 of the 7 breaching
    windows against an expected 3.3, and the incumbent duly scored 1 breach on
    it. At one event the optimizer can only go 1 -> 0, which is noise, and the
    study would have burned hours measuring nothing — the same mistake as the
    original 25-start screen, one layer deeper.

    So the screen is CASE-ENRICHED: every window the baseline is known to breach
    is included by construction. That buys the power to tell 7 -> 1 from 7 -> 6.

    The price, which must be carried into every reading of the results:
      * The breach COUNT here is not a rate. It is inflated by construction and
        must never be quoted as one.
      * Optimising to survive seven specific windows invites overfitting to
        exactly those windows.

    Both are handled by validating in two further stages rather than one:
      HOLDOUT   33 remaining 2019+ starts plus 37 pre-2019, all of which the
                baseline survives — so this catches a candidate that trades the
                known failures for NEW ones.
      FRESH     CONFIRM_100_STARTS.json, seed 20260810, disjoint from every list
                used anywhere in this project, for an unbiased breach rate.
    """
    if SPLIT.exists():
        d = json.loads(SPLIT.read_text())
        return d["screen"], d["holdout"]
    allst = json.loads((w5.DOE_DIR / "HOLDOUT_100_STARTS_2015.json").read_text())["starts"]
    res = json.loads((w5.W5_DIR / "holdout100.json").read_text())
    hard = [s for s in allst if s[:4] >= "2019"]
    breaching = [s for s in hard if res.get(s, {}).get("breach")]
    rest = [s for s in hard if s not in breaching]
    rng = random.Random(SEED)
    screen = sorted(breaching + rng.sample(rest, N_SCREEN - len(breaching)))
    holdout = sorted(set(allst) - set(screen))
    w5.atomic_write(SPLIT, {"seed": SEED, "screen": screen, "holdout": holdout,
                            "enriched_with_breaching": breaching,
                            "note": "screen is case-enriched; breach COUNT is not a rate"})
    return screen, holdout


def space(trial, env, tp):
    """Every lever that plausibly acts on survival, searched together.

    One-at-a-time was already tried in w5_safety_sweep and produced a
    non-monotonic mess (risk 2.7->7 breaches, 2.2->2, 1.8->4). If the levers
    interact — and exposure levers plausibly do — a joint search is the only way
    to see it.
    """
    tp["risk_per_trade_pct"] = trial.suggest_float("risk_per_trade_pct", 1.6, 2.9, step=0.1)
    env["CFG_MAX_CUM_RISK"] = str(trial.suggest_float("cum_risk", 4.0, 9.0, step=0.5))
    env["MAX_TOTAL_POSITIONS"] = str(trial.suggest_int("max_pos", 10, 24))
    env["CORR_GROUP_CAP"] = str(trial.suggest_int("corr_cap", 3, 8))
    env["CFG_TDD_CAUTION_PCT"] = str(trial.suggest_float("tdd_caution", 1.0, 3.0, step=0.25))
    env["CFG_RISK_CAUTIOUS"] = str(trial.suggest_float("risk_cautious", 0.2, 0.8, step=0.05))
    env["TDD_WALL_SAFETY"] = str(trial.suggest_float("wall_safety", 3.0, 7.0, step=0.5))
    env["NIGHTLY_REDUCE_PCT"] = str(trial.suggest_float("nightly_reduce", 0.5, 1.0, step=0.05))
    env["NIGHTLY_R_CLOSE_LOSING"] = str(trial.suggest_float("nightly_close_r", 0.0, 0.5, step=0.05))
    return env, tp


def evaluate(env, tp, starts):
    """Full evaluation — NO early abort until ABORT_AT breaches.

    w5.evaluate aborts on the first breach, which is right when a breach is a
    hard reject but useless here: it censors the count, and the count IS the
    objective. Aborting only once a config is clearly worse than baseline keeps
    the cost down without blinding the measurement.
    """
    import concurrent.futures
    store = w5.load_json(CACHE)
    ck = w5.config_key(env, tp)
    mine = store.setdefault(ck, {})
    rows = [mine[s] for s in starts if s in mine]
    if sum(1 for r in rows if r.get("breach")) >= ABORT_AT:
        return rows, True
    todo = [s for s in starts if s not in mine]
    chunk = max(2, w5.WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                rows.append(r); mine[futs[f]] = r
            w5.atomic_write(CACHE, store)
            if sum(1 for r in rows if r.get("breach")) >= ABORT_AT:
                return rows, True
    return rows, False


def score_rows(rows):
    n = max(len(rows), 1)
    br = sum(1 for r in rows if r.get("breach"))
    tot = sorted(r["total"] for r in rows if r.get("total") is not None)
    st = n - br - len(tot)
    med = tot[len(tot) // 2] if tot else 2 * w5.HORIZON
    score = 100 * len(tot) - 250 * br - 100 * st - med
    return score, {"breaches": br, "stalls": st, "passes": len(tot), "median": med,
                   "p30": round(sum(1 for t in tot if t <= 30) / n, 3), "n": n}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--trials", type=int, default=80)
    args = ap.parse_args()
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    screen, holdout = screen_and_holdout()
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    base_env = dict(w5.BASE_ENV); base_env.update(b["env"])
    base_tp = dict(w5.BASE_TP); base_tp.update(b["tp"])
    print(f"[surv] screen {len(screen)} starts {screen[0]}..{screen[-1]} (2019+)", flush=True)
    print(f"[surv] holdout {len(holdout)} reserved for confirmation", flush=True)

    study = optuna.create_study(direction="maximize", study_name="w5_survival",
                                storage=f"sqlite:///{DB}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=7, multivariate=True))
    if not [t for t in study.trials if t.state != optuna.trial.TrialState.FAIL]:
        study.enqueue_trial({                       # the incumbent, measured first
            "risk_per_trade_pct": 2.7, "cum_risk": 7.0, "max_pos": 20, "corr_cap": 6,
            "tdd_caution": 1.5, "risk_cautious": 0.4, "wall_safety": 5.5,
            "nightly_reduce": 0.75, "nightly_close_r": 0.25})

    def objective(trial):
        env, tp = space(trial, dict(base_env), dict(base_tp))
        rows, aborted = evaluate(env, tp, screen)
        sc, m = score_rows(rows)
        if aborted:
            sc -= 5000                              # clearly worse than baseline
        for k, v in m.items():
            trial.set_user_attr(k, v)
        trial.set_user_attr("aborted", aborted)
        print(f"[surv] t{trial.number:>3} score {sc:>7} | breach {m['breaches']} "
              f"stall {m['stalls']} pass {m['passes']}/{m['n']} median {m['median']}d"
              + ("  ABORTED" if aborted else ""), flush=True)
        new = not CSV.exists()
        with open(CSV, "a", newline="") as fh:
            wtr = csv.writer(fh)
            if new:
                wtr.writerow(["trial", "score", "breaches", "stalls", "passes",
                              "median", "p30", "n", "aborted"] + sorted(trial.params))
            wtr.writerow([trial.number, sc, m["breaches"], m["stalls"], m["passes"],
                          m["median"], m["p30"], m["n"], aborted]
                         + [trial.params[k] for k in sorted(trial.params)])
        return sc

    study.optimize(objective, n_trials=args.trials)
    print(f"\n[surv] best score {study.best_value} params {study.best_params}", flush=True)
    print("[w5_survival] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
