#!/usr/bin/env python3
"""
E5 — validation gauntlet for the E4 winner, on the Summer Edition (3% wall).

Four independent checks. Each can fail the config on its own; passing TRAIN is
not evidence of anything until these are done.

  holdout   16 start windows the search never saw (2017/19/22/24 x quarterly).
            Catches overfitting to TRAIN. If the config only works on the
            windows it was tuned on, it is worthless.

  tenyear   One continuous 2015-2024 run as a FUNDED account, scaling capped at
            $175k. This is the real-money question: does it survive a decade —
            COVID, the 2019 JPY flash, the 2022 gilt crisis — without touching
            the 3% daily or 10% total wall, and what does it actually pay?
            The challenge runs are 60-day sprints; this is the marathon.

  random    40 randomly drawn start dates rather than the quarterly grid. The
            fixed Jan/Apr/Jul/Oct grid is only 16 samples and always begins at
            a quarter boundary; random starts test whether the result is an
            artifact of that calendar alignment.

  robust    Parameter perturbation around the winner. A config that only works
            at exactly risk 1.1 / book 1-2 is a knife edge, not an edge — the
            neighbours have to work too, because live conditions never match
            the backtest exactly.

Run:  uv run python3 backtest/src/e5_validate_winner.py --checks holdout tenyear random robust
"""
import argparse, concurrent.futures, importlib.util, json, os, random, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")
WORKERS = int(os.environ.get("E5_WORKERS", str(os.cpu_count() or 2)))

# ── E4 winner: book 1/2 @ risk 1.1%, zero breach, p30 6.2% / p40 18.8% ──
WINNER_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
              "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
              "VOL_REGIME_DD_OFF": "5.0", "CFG_DAILY_HALT_PCT": "2.0", "CFG_MAX_CUM_RISK": "3.0",
              "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
              "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
              "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15",
              "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
              "BROKER_TYPE": "fiveers_live", "CFG_DAILY_WALL_PCT": "3.0",
              "NIGHTLY_DERISK": "1", "NIGHTLY_DERISK_HOUR": "21",
              "NIGHTLY_MAX_PER_GROUP": "1", "NIGHTLY_MAX_TOTAL": "2",
              "NIGHTLY_R_CLOSE_LOSING": "0.0", "NIGHTLY_R_NEW": "0.5",
              "NIGHTLY_REDUCE_PCT": "0.5",
              "FIVEERS_MAX_SCALE": "4000000"}
WINNER_RISK = 1.1
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})

SCALE_CAP = os.environ.get("E5_SCALE_CAP", "175000")   # funded account stops scaling here


def _load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def _save(path, obj):
    path.write_text(json.dumps(obj, indent=2))


def challenge_arm(env, tp, starts, horizon=60, cache=None, cache_key=None, out=None):
    """Two-step challenge over `starts`; no early abort — we want the true rate.

    Results are cached PER START. The container restarts periodically and kills
    everything; caching only after a whole 16-window check completed meant every
    restart threw away the entire check and it never finished. Per-start caching
    caps the loss at one window.
    """
    store = None
    if cache is not None and cache_key is not None:
        store = cache.setdefault("_starts", {}).setdefault(cache_key, {})

    rows = []
    todo = [s for s in starts if not (store is not None and s in store)]
    if store is not None:
        rows.extend(store[s] for s in starts if s in store)

    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(cs.full_two_step, env, tp, s, horizon): s for s in todo}
        for fut in concurrent.futures.as_completed(futs):
            s = futs[fut]
            r = fut.result(); r.pop("detail", None)
            rows.append(r)
            if store is not None:
                store[s] = r
                if out is not None:
                    _save(out, cache)
    n = len(rows)
    totals = sorted(r["total"] for r in rows if r["total"] is not None)
    return {"n": n,
            "breach_rate": round(sum(1 for r in rows if r["breach"]) / n, 3),
            "complete_rate": round(len(totals) / n, 3),
            "median_days": (totals[len(totals) // 2] if totals else None),
            "fastest_days": (totals[0] if totals else None),
            "p30": round(sum(1 for t in totals if t <= 30) / n, 3),
            "p40": round(sum(1 for t in totals if t <= 40) / n, 3),
            "p60": round(sum(1 for t in totals if t <= 60) / n, 3)}


def continuous_run(env, tp, start, end, balance, scale_cap):
    """One long funded-account run. Returns the wall/profit summary."""
    e = dict(os.environ); e.update(cs.dh.BASE_ENV); e.update(env)
    e["FIVEERS_MAX_SCALE"] = str(scale_cap)
    e["OPT_PARAMS"] = json.dumps({**cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        subprocess.run([sys.executable, str(cs.dh.BACKTEST), "--start", start,
                        "--end", end, "--balance", str(balance),
                        "--output", td, "--quiet"],
                       env=e, cwd=str(cs.dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=14400)
        rj = Path(td) / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        return {"net_pnl": r.get("net_pnl"), "return_pct": r.get("return_pct"),
                "final_balance": r.get("final_balance"),
                "withdrawn": r.get("fiveers_total_withdrawn"),
                "final_funded_level": r.get("fiveers_final_funded_level"),
                "scaling_events": r.get("fiveers_scaling_events"),
                "max_tdd_pct": r.get("max_tdd_pct"), "max_ddd_pct": r.get("max_ddd_pct"),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "account_failed": r.get("account_failed"), "fail_info": r.get("fail_info"),
                "ddd_halts": r.get("ddd_halts"), "tdd_stopouts": r.get("tdd_stopouts")}
    finally:
        shutil.rmtree(td, ignore_errors=True)


def check_holdout(out):
    res = _load(out)
    if "holdout" not in res:
        env = dict(WINNER_ENV); tp = dict(TP); tp["risk_per_trade_pct"] = WINNER_RISK
        res["holdout"] = challenge_arm(env, tp, cs.HOLDOUT_STARTS,
                                       cache=res, cache_key="holdout", out=out)
        _save(out, res)
    m = res["holdout"]
    print(f"\n=== HOLDOUT (16 unseen starts) ===", flush=True)
    print(f"  breach={m['breach_rate']*100:.1f}%  p30={m['p30']*100:.1f}%  "
          f"p40={m['p40']*100:.1f}%  p60={m['p60']*100:.1f}%  "
          f"median={m['median_days']}  fastest={m['fastest_days']}  "
          f"complete={m['complete_rate']*100:.0f}%", flush=True)
    print("  TRAIN was: breach=0.0% p30=6.2% p40=18.8% median=63 fastest=30", flush=True)


def check_tenyear(out, start="2015-01-01", key="tenyear"):
    res = _load(out)
    if key not in res:
        env = dict(WINNER_ENV); tp = dict(TP); tp["risk_per_trade_pct"] = WINNER_RISK
        res[key] = continuous_run(env, tp, start, "2024-12-31", 100_000, SCALE_CAP)
        _save(out, res)
    m = res[key]
    print(f"\n=== CONTINUOUS {start}..2024-12-31 (funded 100k, scaling cap ${SCALE_CAP}) ===",
          flush=True)
    if m.get("error"):
        print(f"  ERROR: {m['error']}", flush=True); return
    print(f"  net P&L        : ${m['net_pnl']:,.0f}   ({m['return_pct']}%)", flush=True)
    print(f"  withdrawn      : ${m['withdrawn']:,.0f}", flush=True)
    print(f"  funded level   : ${m['final_funded_level']:,.0f} "
          f"({m['scaling_events']} scaling events)", flush=True)
    print(f"  peak total DD  : {m['max_tdd_pct']}%   (10% wall)", flush=True)
    print(f"  peak daily DD  : {m['max_ddd_pct']}%   (3% wall)", flush=True)
    print(f"  trades         : {m['trades']}  win rate {m['win_rate']}%", flush=True)
    print(f"  ACCOUNT FAILED : {m['account_failed']}  {m.get('fail_info') or ''}", flush=True)


def check_random(out, n_starts, seed):
    res = _load(out)
    key = f"random_{n_starts}_{seed}"
    if key not in res:
        rng = random.Random(seed)
        lo, hi = date(2015, 1, 1), date(2024, 6, 30)   # leave room for a 2-step run
        span = (hi - lo).days
        starts = sorted({(lo + timedelta(days=rng.randrange(span))).isoformat()
                         for _ in range(n_starts * 2)})[:n_starts]
        env = dict(WINNER_ENV); tp = dict(TP); tp["risk_per_trade_pct"] = WINNER_RISK
        m = challenge_arm(env, tp, starts, cache=res, cache_key=key, out=out)
        m["starts"] = starts
        res[key] = m
        _save(out, res)
    m = res[key]
    print(f"\n=== RANDOM STARTS ({m['n']} random dates 2015-2024, seed {seed}) ===", flush=True)
    print(f"  breach={m['breach_rate']*100:.1f}%  p30={m['p30']*100:.1f}%  "
          f"p40={m['p40']*100:.1f}%  p60={m['p60']*100:.1f}%  "
          f"median={m['median_days']}  fastest={m['fastest_days']}  "
          f"complete={m['complete_rate']*100:.0f}%", flush=True)


PERTURB = [
    ("baseline",           {}, WINNER_RISK),
    ("risk -0.1",          {}, round(WINNER_RISK - 0.1, 2)),
    ("risk +0.1",          {}, round(WINNER_RISK + 0.1, 2)),
    ("night book 1/3",     {"NIGHTLY_MAX_TOTAL": "3"}, WINNER_RISK),
    ("night book 2/2",     {"NIGHTLY_MAX_PER_GROUP": "2"}, WINNER_RISK),
    ("derisk hour 19",     {"NIGHTLY_DERISK_HOUR": "19"}, WINNER_RISK),
    ("derisk hour 22",     {"NIGHTLY_DERISK_HOUR": "22"}, WINNER_RISK),
    ("reduce 0.75",        {"NIGHTLY_REDUCE_PCT": "0.75"}, WINNER_RISK),
    ("r_close +0.25",      {"NIGHTLY_R_CLOSE_LOSING": "0.25"}, WINNER_RISK),
    ("corr cap 2",         {"CORR_GROUP_CAP": "2"}, WINNER_RISK),
]


def check_robust(out):
    res = _load(out)
    r = res.setdefault("robust", {})
    print(f"\n=== ROBUSTNESS (perturbations around the winner, TRAIN) ===", flush=True)
    print(f"  {'variant':18} {'breach':>7} {'p30':>6} {'p40':>6} {'median':>7} {'fastest':>8}",
          flush=True)
    for name, over, risk in PERTURB:
        if name not in r:
            env = dict(WINNER_ENV); env.update(over)
            tp = dict(TP); tp["risk_per_trade_pct"] = risk
            r[name] = challenge_arm(env, tp, cs.TRAIN_STARTS,
                                    cache=res, cache_key=f"robust/{name}", out=out)
            _save(out, res)
        m = r[name]
        md = "-" if m["median_days"] is None else m["median_days"]
        fd = "-" if m["fastest_days"] is None else m["fastest_days"]
        flag = "" if m["breach_rate"] == 0.0 else "  <-- BREACHES"
        print(f"  {name:18} {m['breach_rate']*100:6.1f}% {m['p30']*100:5.1f}% "
              f"{m['p40']*100:5.1f}% {md:>7} {fd:>8}{flag}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checks", nargs="*",
                    default=["holdout", "tenyear", "random", "robust"])
    ap.add_argument("--random-starts", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260725)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    out = DOE_DIR / "e5_validation.json"

    print(f"[E5] validating E4 winner: risk {WINNER_RISK}%, nightly book "
          f"{WINNER_ENV['NIGHTLY_MAX_PER_GROUP']}/{WINNER_ENV['NIGHTLY_MAX_TOTAL']} "
          f"@{WINNER_ENV['NIGHTLY_DERISK_HOUR']}h, 3% wall, {WORKERS} workers", flush=True)
    if "holdout" in args.checks: check_holdout(out)
    if "tenyear" in args.checks: check_tenyear(out)
    # The 2015-01-15 CHF unpeg is a designated black swan the user asked to
    # exclude; this arm measures the decade without it.
    if "postchf" in args.checks: check_tenyear(out, "2015-02-01", "tenyear_postchf")
    if "random"  in args.checks: check_random(out, args.random_starts, args.seed)
    if "robust"  in args.checks: check_robust(out)
    print("\n[e5_validate_winner] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
