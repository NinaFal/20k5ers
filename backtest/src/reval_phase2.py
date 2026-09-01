#!/usr/bin/env python3
"""
Revalidate the Phase-2 winner (Stage C2 "trial 4") on the LIVE-FAITHFUL universe.

Why: the recorded headline for this config — score 174.8, p20=37.5%, 0% breach
on a classic 5% daily wall — was measured BEFORE the two pipeline bugs found in
D0/D1 were fixed:
  * broker profile forexcom_demo has trade_metals=False → XAU/XAG silently
    excluded from every run
  * a tz-naive/tz-aware file mix crashed the concat → NAS100_USD silently dropped
Ten symbols were therefore missing from the backtest that produced 174.8. That
number is the basis of the "take the 5% account instead" recommendation, so it
has to be re-measured before anyone acts on it.

Runs three arms on both TRAIN and HOLDOUT, at the classic 5% wall:
  old_universe  — forexcom_demo, reproducing the original conditions (control)
  faithful      — fiveers_live: metals + NAS100 included (the real account)
  faithful_nobleed — faithful minus the 3 bleeders D1 identified

Run:  uv run python3 backtest/src/reval_phase2.py [--arms ...] [--splits ...]
"""
import argparse, concurrent.futures, importlib.util, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

WORKERS = int(os.environ.get("REVAL_WORKERS", str(os.cpu_count() or 2)))

# Stage C2 trial 4 — verbatim from STAGEC2_TRIAL4_BACKUP.md
BASE_ENV = {
    "RISK_REGIME_ENABLE": "1", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
    "VOL_REGIME_DD_OFF": "5.0", "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "2.25",
    "CFG_TDD_CAUTION_PCT": "3.5", "CFG_RISK_CAUTIOUS": "0.65",
    "CFG_TDD_WARNING_PCT": "4.5", "CFG_RISK_CONSERVATIVE": "0.6",
    "CFG_TDD_EMERGENCY_PCT": "8.0", "CFG_RISK_ULTRASAFE": "0.4",
    "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3",
    "FIVEERS_MAX_SCALE": "4000000",
    "CFG_DAILY_WALL_PCT": "5.0",          # classic account — the arm being revalidated
}
TP = {
    "entry_fib_level": 0.65, "entry_fib_level_volatile": 0.65,
    "fib_vol_ratio_threshold": 1.15,
    "tp1_r_multiple": 0.40, "tp1_close_pct": 0.50,
    "tp2_r_multiple": 0.75, "tp2_close_pct": 0.35,
    "tp3_r_multiple": 1.35, "tp3_close_pct": 0.15,
    "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
    "sl_after_tp2_r": 0.25, "sl_after_tp3_r": 0.60,
    "risk_per_trade_pct": 3.5,
}
BLEEDERS = "AUD_NZD,EUR_NZD,AUD_JPY"

ARMS = {
    # True reproduction of the conditions that produced 174.8: the tz bug
    # dropped NAS100 for BOTH broker profiles (trade_indices=True on each), so
    # "forexcom_demo" alone does NOT restore the original universe — NAS100 has
    # to be excluded explicitly as well.
    "orig_repro":       {"BROKER_TYPE": "forexcom_demo", "EXCLUDE_SYMBOLS": "NAS100_USD"},
    "old_universe":     {"BROKER_TYPE": "forexcom_demo"},
    "faithful":         {"BROKER_TYPE": "fiveers_live"},
    "faithful_nobleed": {"BROKER_TYPE": "fiveers_live", "EXCLUDE_SYMBOLS": BLEEDERS},
}
SPLITS = {"TRAIN": cs.TRAIN_STARTS, "HOLDOUT": cs.HOLDOUT_STARTS}


def run_arm(arm, starts):
    env = dict(BASE_ENV); env.update(ARMS[arm])
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(cs.full_two_step, env, TP, s) for s in starts]
        for fut in futs:
            r = fut.result(); r.pop("detail", None); rows.append(r)
    return cs.score_results(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=list(ARMS))
    ap.add_argument("--splits", nargs="*", default=list(SPLITS))
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    out, results = DOE_DIR / "reval_phase2.json", {}
    if out.exists():
        results = json.loads(out.read_text())     # resume across container reaps

    print(f"[reval2] C2-trial4 @ 5% wall, {WORKERS} workers", flush=True)
    print(f"{'arm':18} {'split':8} {'score':>8} {'p20':>7} {'p30':>7} "
          f"{'p40':>7} {'breach':>7} {'medTot':>7}", flush=True)
    for arm in args.arms:
        for split in args.splits:
            key = f"{arm}/{split}"
            if key in results:
                sc = results[key]
            else:
                sc = run_arm(arm, SPLITS[split])
                results[key] = sc
                out.write_text(json.dumps(results, indent=2))
            print(f"{arm:18} {split:8} {sc['score']:8.2f} {sc['p20']*100:6.1f}% "
                  f"{sc['p30']*100:6.1f}% {sc['p40']*100:6.1f}% "
                  f"{sc['breach_rate']*100:6.1f}% {sc['median_total']:>7}", flush=True)

    print("\n[reval2] recorded headline was: score 174.8, p20=37.5%, breach 0.0% "
          "(TRAIN, old universe)", flush=True)
    print("[reval_phase2] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
