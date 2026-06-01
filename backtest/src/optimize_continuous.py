#!/usr/bin/env python3
"""
Continuous-run optimizer — MAX PROFIT with ZERO breaches over the real
2015-2024 compounding + 5%ers-scaling path.

WHY THIS EXISTS (the lesson that killed the cold-start sweeps)
--------------------------------------------------------------
Every earlier sweep scored COLD-START years (each Jan-Dec fresh at $50k). A
config can be 0-breach across all 10 cold-start years and still DIE in the real
continuous run: continuously the account scales $50k -> $250k+ (high-water mark
ratchets up), positions grow with it, and a drawdown that is survivable on a
$50k base breaches the 10% wall measured from the ratcheted floor. Verified:
opt#40 + vol 1.3/0.3 was 0-breach cold-start but breached the continuous run on
2021-06-03 (TDD 10.01%, funded $250k), forfeiting 2022-2024 (~$290k of profit).

So the ONLY honest objective is the continuous run, where a breach TERMINATES
the account (TERMINAL_ON_BREACH) and truncates the timeline. Surviving is what
unlocks the >$1M compounding; dying in year 6 is what makes the "cold-start
sum" look bigger than the continuous total.

OBJECTIVE
---------
  • Hard gate: any breach (TDD>=10% or DDD>=5% -> account_failed) is floored
    deeply negative, less-bad the longer it survived (gradient toward survival).
  • Survivor score: real account value (net_pnl, which already includes 5%ers
    withdrawals) MINUS a quadratic penalty for hugging the wall past
    WALL_MARGIN_START (discourages fragile near-wall winners that would breach
    on a slightly different path -> also buys out-of-sample robustness).

STAGES (sequential, safety-first; see --stage)
  safety    : sweep drawdown rungs + vol multipliers (the breach-control levers),
              TP fixed at opt#40. Carve out the 0-breach feasible region first.
  tp        : sweep the TP ladder + trailing stops (the profit lever), safety
              envelope LOCKED from the safety stage. Maximize profit inside it.
  volrefine : re-tune the 2 vol multipliers now that TP changed the size/return
              profile (converges the coupling). Everything else locked.
  validate  : no optimization — robustness cross-check of the locked winner:
              cold-start all 10 years + shifted-start continuous (2016->, 2017->).

State (locked params from each stage) is passed via a JSON file (--state).

Usage:
  python3 backtest/src/optimize_continuous.py --stage safety   --trials 100 --jobs 4
  python3 backtest/src/optimize_continuous.py --stage tp       --trials 150 --jobs 4
  python3 backtest/src/optimize_continuous.py --stage volrefine --trials 30 --jobs 4
  python3 backtest/src/optimize_continuous.py --stage validate
"""
import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path
import optuna

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"
REPO = HERE.parent.parent

START, END, BAL = "2015-01-01", "2024-12-31", "50000"

# Fixed engine realism + settled levers (CORR_GROUP_CAP off = prior verdict).
BASE_ENV = {
    "TERMINAL_ON_BREACH": "1", "SLIPPAGE_PIPS": "0.5", "GAP_FILLS": "1",
    "CORR_GROUP_CAP": "0",
}

# opt#40 TP ladder — the Step-1 baseline (Step-2 sweeps these).
TP40 = {
    "tp1_r_multiple": 0.5, "tp2_r_multiple": 0.9, "tp3_r_multiple": 1.2,
    "tp4_r_multiple": 1.5, "tp5_r_multiple": 5.2,
    "tp1_close_pct": 0.10, "tp2_close_pct": 0.40, "tp3_close_pct": 0.15,
    "tp4_close_pct": 0.15, "tp5_close_pct": 0.20,
    "sl_after_tp2_r": 0.20, "sl_after_tp3_r": 0.35, "sl_after_tp4_r": 0.35,
}

# Default safety envelope — current swept values (Step-1 sweeps these).
SAFETY_DEFAULT = {
    "CFG_TDD_CAUTION_PCT": "4.5", "CFG_RISK_CAUTIOUS": "0.4",
    "CFG_TDD_WARNING_PCT": "6.5", "CFG_RISK_CONSERVATIVE": "0.4",
    "CFG_TDD_EMERGENCY_PCT": "7.0", "CFG_RISK_ULTRASAFE": "0.25",
    "TDD_WALL_SAFETY": "3.0",
    "VOL_SIZE_ENABLE": "1", "VOL_SIZE_MULT_LOW": "1.3", "VOL_SIZE_MULT_HIGH": "0.3",
}

# Wall-hugging penalty: profit minus K*(maxTDD - start)^2 once past the margin.
WALL_MARGIN_START = float(os.getenv("WALL_MARGIN_START", "8.5"))
MARGIN_K = float(os.getenv("MARGIN_K", "30000"))


def run(env_over, params, start=START, end=END):
    td = tempfile.mkdtemp()
    env = dict(os.environ); env.update(BASE_ENV); env.update(env_over)
    env["OPT_PARAMS"] = json.dumps(params)
    cmd = [sys.executable, str(BACKTEST), "--start", start, "--end", end,
           "--balance", BAL, "--output", td, "--quiet"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
    rj = Path(td) / "results.json"
    if p.returncode != 0 or not rj.exists():
        return None
    return json.loads(rj.read_text())


def attrs(r):
    fi = (r or {}).get("fail_info") or {}
    return {
        "failed": bool((r or {}).get("account_failed")),
        "net": round(float((r or {}).get("net_pnl") or 0)),
        "max_tdd": float((r or {}).get("max_tdd_pct") or 0),
        "max_ddd": float((r or {}).get("max_ddd_pct") or 0),
        "survived_days": fi.get("survived_days"),
        "breach_type": fi.get("breach_type"),
        "breach_time": str(fi.get("time")) if fi.get("time") else None,
        "withdrawn": round(float((r or {}).get("fiveers_total_withdrawn") or 0)),
        "final_funded": (r or {}).get("fiveers_final_funded_level"),
        "scalings": (r or {}).get("fiveers_scaling_events"),
        "trades": (r or {}).get("total_trades"), "win_rate": (r or {}).get("win_rate"),
    }


def score(r):
    """Hard 0-breach gate, then profit minus a wall-hugging penalty."""
    a = attrs(r)
    if r is None:
        return -2e9, a
    if a["failed"]:
        # Deeply negative; longer survival scores less-bad (gradient to survive).
        return -1e9 + float(a["survived_days"] or 0) * 100.0, a
    pen = MARGIN_K * max(0.0, a["max_tdd"] - WALL_MARGIN_START) ** 2
    return a["net"] - pen, a


# --------------------------------------------------------------------------- #
#  Stage param builders
# --------------------------------------------------------------------------- #
def suggest_safety(trial):
    """Drawdown rungs + vol multipliers (the breach-control levers)."""
    caution_t = trial.suggest_float("CFG_TDD_CAUTION_PCT", 3.0, 6.0, step=0.5)
    warning_t = trial.suggest_float("CFG_TDD_WARNING_PCT", caution_t + 0.5, 8.0, step=0.5)
    emerg_t = trial.suggest_float("CFG_TDD_EMERGENCY_PCT", warning_t + 0.5, 9.0, step=0.5)
    r_caut = trial.suggest_float("CFG_RISK_CAUTIOUS", 0.2, 0.8, step=0.05)
    r_cons = trial.suggest_float("CFG_RISK_CONSERVATIVE", 0.15, min(r_caut, 0.6), step=0.05)
    r_ultra = trial.suggest_float("CFG_RISK_ULTRASAFE", 0.10, min(r_cons, 0.4), step=0.05)
    wall_safety = trial.suggest_float("TDD_WALL_SAFETY", 2.0, 5.0, step=0.5)
    v_low = trial.suggest_float("VOL_SIZE_MULT_LOW", 1.0, 2.0, step=0.1)
    v_high = trial.suggest_float("VOL_SIZE_MULT_HIGH", 0.2, 1.0, step=0.1)
    if v_low < v_high:                       # thesis: calm sizing >= turbulent
        raise optuna.TrialPruned()
    return {
        "CFG_TDD_CAUTION_PCT": f"{caution_t}", "CFG_RISK_CAUTIOUS": f"{r_caut}",
        "CFG_TDD_WARNING_PCT": f"{warning_t}", "CFG_RISK_CONSERVATIVE": f"{r_cons}",
        "CFG_TDD_EMERGENCY_PCT": f"{emerg_t}", "CFG_RISK_ULTRASAFE": f"{r_ultra}",
        "TDD_WALL_SAFETY": f"{wall_safety}",
        "VOL_SIZE_ENABLE": "1", "VOL_SIZE_MULT_LOW": f"{v_low}", "VOL_SIZE_MULT_HIGH": f"{v_high}",
    }


def suggest_tp(trial):
    """TP ladder + trailing stops (the profit lever)."""
    tp1 = trial.suggest_float("tp1_r_multiple", 0.4, 1.0, step=0.1)
    tp2 = trial.suggest_float("tp2_r_multiple", tp1 + 0.2, 1.8, step=0.1)
    tp3 = trial.suggest_float("tp3_r_multiple", tp2 + 0.2, 2.8, step=0.1)
    tp4 = trial.suggest_float("tp4_r_multiple", tp3 + 0.3, 4.0, step=0.1)
    tp5 = trial.suggest_float("tp5_r_multiple", tp4 + 0.3, 6.0, step=0.1)
    c1 = trial.suggest_float("tp1_close_pct", 0.10, 0.45, step=0.05)
    c2 = trial.suggest_float("tp2_close_pct", 0.10, 0.45, step=0.05)
    c3 = trial.suggest_float("tp3_close_pct", 0.05, 0.30, step=0.05)
    c4 = trial.suggest_float("tp4_close_pct", 0.05, 0.30, step=0.05)
    if c1 + c2 + c3 + c4 > 0.92:
        raise optuna.TrialPruned()
    c5 = round(1.0 - c1 - c2 - c3 - c4, 4)
    s2 = trial.suggest_float("sl_after_tp2_r", 0.2, min(tp1, 1.0), step=0.05)
    s3 = trial.suggest_float("sl_after_tp3_r", s2, min(tp2, 1.6), step=0.05)
    s4 = trial.suggest_float("sl_after_tp4_r", s3, min(tp3, 2.2), step=0.05)
    return {"tp1_r_multiple": tp1, "tp2_r_multiple": tp2, "tp3_r_multiple": tp3,
            "tp4_r_multiple": tp4, "tp5_r_multiple": tp5,
            "tp1_close_pct": c1, "tp2_close_pct": c2, "tp3_close_pct": c3,
            "tp4_close_pct": c4, "tp5_close_pct": c5,
            "sl_after_tp2_r": s2, "sl_after_tp3_r": s3, "sl_after_tp4_r": s4}


def suggest_volrefine(trial):
    v_low = trial.suggest_float("VOL_SIZE_MULT_LOW", 1.0, 2.0, step=0.1)
    v_high = trial.suggest_float("VOL_SIZE_MULT_HIGH", 0.2, 1.0, step=0.1)
    if v_low < v_high:
        raise optuna.TrialPruned()
    return {"VOL_SIZE_ENABLE": "1", "VOL_SIZE_MULT_LOW": f"{v_low}", "VOL_SIZE_MULT_HIGH": f"{v_high}"}


# --------------------------------------------------------------------------- #
#  State plumbing (locked params carried between stages)
# --------------------------------------------------------------------------- #
def load_state(path):
    if path and Path(path).exists():
        return json.loads(Path(path).read_text())
    return {"safety": dict(SAFETY_DEFAULT), "tp": dict(TP40)}


def save_state(path, state):
    Path(path).write_text(json.dumps(state, indent=2))


def make_objective(stage, state):
    def objective(trial):
        env = dict(state["safety"]); params = dict(state["tp"])
        if stage == "safety":
            env = suggest_safety(trial)
        elif stage == "tp":
            params = suggest_tp(trial)
        elif stage == "volrefine":
            env.update(suggest_volrefine(trial))
        s, a = score(run(env, params))
        for k, v in a.items():
            trial.set_user_attr(k, v)
        trial.set_user_attr("env", env); trial.set_user_attr("params", params)
        return s
    return objective


def report_top(study, n=10):
    done = [t for t in study.trials if t.value is not None]
    surv = [t for t in done if not t.user_attrs.get("failed")]
    print(f"\n{len(done)} trials | {len(surv)} SURVIVED (0-breach)")
    print(f"{'':2}{'net':>12}{'TDD%':>7}{'DDD%':>7}{'funded':>10}{'scal':>5}{'score':>14}")
    for t in sorted(done, key=lambda t: t.value, reverse=True)[:n]:
        a = t.user_attrs
        tag = "OK" if not a.get("failed") else f"X{a.get('breach_type','')[:1]}"
        print(f"{tag:2}{a.get('net',0):>12,.0f}{a.get('max_tdd',0):>7}{a.get('max_ddd',0):>7}"
              f"{(a.get('final_funded') or 0):>10,.0f}{(a.get('scalings') or 0):>5}{t.value:>14,.0f}")
    best = max(surv or done, key=lambda t: t.value)
    return best


def stage_validate(state):
    print("=" * 78); print("VALIDATION — robustness of the locked winner"); print("=" * 78)
    env, params = state["safety"], state["tp"]

    print("\n[A] Continuous 2015-2024 (the optimized path):")
    a = attrs(run(env, params))
    print(f"    net ${a['net']:,.0f} | {'SURVIVED' if not a['failed'] else 'BREACH '+str(a['breach_time'])} "
          f"| TDD {a['max_tdd']}% DDD {a['max_ddd']}% | funded ${a['final_funded']:,} | {a['scalings']} scalings")

    print("\n[B] Shifted-start continuous (overfit check):")
    for s in ("2016-01-01", "2017-01-01"):
        a = attrs(run(env, params, start=s))
        print(f"    {s}->2024-12-31: net ${a['net']:,.0f} | "
              f"{'SURVIVED' if not a['failed'] else 'BREACH '+str(a['breach_time'])} | TDD {a['max_tdd']}%")

    print("\n[C] Cold-start each year (regime robustness):")
    br = []
    for y in range(2015, 2025):
        a = attrs(run(env, params, start=f"{y}-01-01", end=f"{y}-12-31"))
        if a["failed"]:
            br.append(y)
        print(f"    {y}: net ${a['net']:,.0f}  TDD {a['max_tdd']}%  DDD {a['max_ddd']}%  "
              f"{'OK' if not a['failed'] else 'FAIL'}")
    print(f"\n  Cold-start breaches: {br or 'NONE'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["safety", "tp", "volrefine", "validate"])
    ap.add_argument("--trials", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--state", default="/tmp/cont_opt_state.json")
    ap.add_argument("--storage", default="sqlite:////tmp/optuna_continuous.db")
    args = ap.parse_args()

    state = load_state(args.state)

    if args.stage == "validate":
        stage_validate(state)
        return

    study = optuna.create_study(direction="maximize", study_name=f"cont_{args.stage}",
                                storage=args.storage, load_if_exists=True)
    # Warm-start with known-good priors so early trials are productive (the
    # continuous run is expensive — don't waste the first batch on noise).
    if not study.trials:
        if args.stage == "safety":
            study.enqueue_trial({  # current default envelope
                "CFG_TDD_CAUTION_PCT": 4.5, "CFG_TDD_WARNING_PCT": 6.5, "CFG_TDD_EMERGENCY_PCT": 7.0,
                "CFG_RISK_CAUTIOUS": 0.4, "CFG_RISK_CONSERVATIVE": 0.4, "CFG_RISK_ULTRASAFE": 0.25,
                "TDD_WALL_SAFETY": 3.0, "VOL_SIZE_MULT_LOW": 1.3, "VOL_SIZE_MULT_HIGH": 0.3})
            study.enqueue_trial({  # tighter: throttle earlier + harder
                "CFG_TDD_CAUTION_PCT": 3.5, "CFG_TDD_WARNING_PCT": 5.5, "CFG_TDD_EMERGENCY_PCT": 6.5,
                "CFG_RISK_CAUTIOUS": 0.3, "CFG_RISK_CONSERVATIVE": 0.2, "CFG_RISK_ULTRASAFE": 0.15,
                "TDD_WALL_SAFETY": 4.0, "VOL_SIZE_MULT_LOW": 1.2, "VOL_SIZE_MULT_HIGH": 0.3})
            study.enqueue_trial({  # stronger turbulence cut, earlier caution
                "CFG_TDD_CAUTION_PCT": 4.0, "CFG_TDD_WARNING_PCT": 6.0, "CFG_TDD_EMERGENCY_PCT": 7.0,
                "CFG_RISK_CAUTIOUS": 0.4, "CFG_RISK_CONSERVATIVE": 0.3, "CFG_RISK_ULTRASAFE": 0.2,
                "TDD_WALL_SAFETY": 3.5, "VOL_SIZE_MULT_LOW": 1.3, "VOL_SIZE_MULT_HIGH": 0.2})
        elif args.stage == "tp":
            study.enqueue_trial({k: TP40[k] for k in TP40})  # opt#40 ladder
    t0 = time.time()
    study.optimize(make_objective(args.stage, state), n_trials=args.trials, n_jobs=args.jobs)
    best = report_top(study)
    dt = time.time() - t0
    print(f"\nstage {args.stage}: {dt/60:.1f} min, best survived={not best.user_attrs.get('failed')}")

    # Lock the best surviving config into state for the next stage.
    if args.stage == "safety":
        state["safety"] = best.user_attrs["env"]
    elif args.stage == "tp":
        state["tp"] = best.user_attrs["params"]
    elif args.stage == "volrefine":
        state["safety"].update(best.user_attrs["env"])
    save_state(args.state, state)
    print(f"locked -> {args.state}:\n  safety={state['safety']}\n  tp={state['tp']}")


if __name__ == "__main__":
    main()
