#!/usr/bin/env python3
"""
Robustness suite for the CONFIRMED TP+trail winner before any live consideration.

Three tests, all on the winning config (not re-optimizing anything):
  1. Walk-forward: run each calendar year independently (2015..2024) and report
     survival / net / max-TDD per year. Edge must show up across regimes, not one.
  2. Monte-Carlo trade-order shuffle: reconstruct the equity curve from daily PnL
     aggregates in random orders, build the distribution of max-TDD, and measure
     P(TDD breaches the 10% wall). This is the headline risk number.
  3. Summary verdict vs the live baseline's risk profile.

Reuses the same backtest engine + BASE_ENV as optimize_tp.py so results are
apples-to-apples. Writes JSON to /tmp/robustness_tp.json.

Usage: python3 backtest/src/robustness_tp.py --mc 5000
"""
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKTEST = HERE / "main_live_bot_backtest.py"
REPO = HERE.parent.parent
BAL = float(os.getenv("OPT_BAL", "50000"))
WALL_PCT = 10.0  # 5%ers total-drawdown wall

BASE_ENV = {
    "TERMINAL_ON_BREACH": "1", "SLIPPAGE_PIPS": "0.5", "GAP_FILLS": "1",
    "CORR_GROUP_CAP": "0", "CFG_TDD_CAUTION_PCT": "4.5", "CFG_RISK_CAUTIOUS": "0.4",
    "CFG_TDD_WARNING_PCT": "6.5", "CFG_RISK_CONSERVATIVE": "0.4",
    "CFG_TDD_EMERGENCY_PCT": "7.0", "CFG_RISK_ULTRASAFE": "0.25", "TDD_EMERGENCY_HALT": "0",
}

# CONFIRMED winner from optimize_tp.py OOS validation.
WINNER = {
    "tp1_r_multiple": 0.9, "tp2_r_multiple": 1.8, "tp3_r_multiple": 2.5,
    "tp4_r_multiple": 3.2, "tp5_r_multiple": 5.0,
    "tp1_close_pct": 0.15, "tp2_close_pct": 0.15, "tp3_close_pct": 0.10,
    "tp4_close_pct": 0.10, "tp5_close_pct": 0.50,
    "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 0.55, "sl_after_tp4_r": 0.7,
}
# Live baseline (current_params.json), for risk-profile comparison.
LIVE = {
    "tp1_r_multiple": 0.6, "tp2_r_multiple": 0.9, "tp3_r_multiple": 1.3,
    "tp4_r_multiple": 2.0, "tp5_r_multiple": 3.5,
    "tp1_close_pct": 0.277, "tp2_close_pct": 0.295, "tp3_close_pct": 0.117,
    "tp4_close_pct": 0.284, "tp5_close_pct": 0.027,
    "sl_after_tp2_r": 0.65, "sl_after_tp3_r": 0.95, "sl_after_tp4_r": 0.95,
}


def run(params, start, end):
    """Run engine, return (results_dict, trades_DataFrame)."""
    td = tempfile.mkdtemp()
    env = dict(os.environ); env.update(BASE_ENV)
    env["OPT_PARAMS"] = json.dumps(params)
    cmd = [sys.executable, str(BACKTEST), "--start", start, "--end", end,
           "--balance", str(BAL), "--output", td, "--quiet"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(REPO))
    rj, tj = Path(td) / "results.json", Path(td) / "trades.csv"
    if p.returncode != 0 or not rj.exists():
        return None, None
    res = json.loads(rj.read_text())
    trades = pd.read_csv(tj) if tj.exists() else pd.DataFrame()
    return res, trades


def daily_pnl(trades):
    """Aggregate partial-aware trade PnL into a daily series (calendar UTC days)."""
    if trades is None or trades.empty:
        return pd.Series(dtype=float)
    t = trades.copy()
    t["close_time"] = pd.to_datetime(t["close_time"], utc=True)
    t["day"] = t["close_time"].dt.date
    return t.groupby("day")["pnl"].sum().sort_index()


def max_tdd_pct(daily, start_bal):
    """5%ers total drawdown: max drop from the running equity HIGH-WATER peak,
    as % of that peak. Mirrors the engine's max_tdd_pct definition."""
    eq = start_bal + np.cumsum(daily.values)
    eq = np.concatenate([[start_bal], eq])
    peak = np.maximum.accumulate(eq)
    dd_pct = (peak - eq) / peak * 100.0
    return float(dd_pct.max())


def monte_carlo(daily, start_bal, n, seed=42):
    """Shuffle the order of daily PnLs n times; return TDD distribution + P(breach)."""
    rng = np.random.default_rng(seed)
    vals = daily.values.copy()
    tdds = np.empty(n)
    for i in range(n):
        rng.shuffle(vals)
        eq = start_bal + np.cumsum(vals)
        eq = np.concatenate([[start_bal], eq])
        peak = np.maximum.accumulate(eq)
        tdds[i] = ((peak - eq) / peak * 100.0).max()
    return {
        "p_breach_10pct": float((tdds >= WALL_PCT).mean()),
        "tdd_mean": float(tdds.mean()), "tdd_median": float(np.median(tdds)),
        "tdd_p95": float(np.percentile(tdds, 95)),
        "tdd_p99": float(np.percentile(tdds, 99)), "tdd_max": float(tdds.max()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", type=int, default=5000, help="Monte-Carlo iterations")
    ap.add_argument("--out", default="/tmp/robustness_tp.json")
    args = ap.parse_args()

    out = {"winner": WINNER, "walk_forward": {}, "monte_carlo": {}}

    # ---- 1. Walk-forward, year by year -------------------------------------
    print("=" * 78); print("WALK-FORWARD (winner, each year independent)"); print("=" * 78)
    print(f"  {'year':6} {'surv':5} {'net':>12} {'TDD%':>7} {'WR%':>6} {'trades':>7}")
    for yr in range(2015, 2025):
        res, _ = run(WINNER, f"{yr}-01-01", f"{yr}-12-31")
        if res is None:
            print(f"  {yr}: ENGINE ERROR"); out["walk_forward"][yr] = {"error": True}; continue
        surv = not res.get("account_failed")
        row = {"survived": surv, "net_pnl": res.get("net_pnl"),
               "max_tdd": res.get("max_tdd_pct"), "win_rate": res.get("win_rate"),
               "trades": res.get("total_trades")}
        out["walk_forward"][yr] = row
        print(f"  {yr:6} {'OK' if surv else 'FAIL':5} {row['net_pnl'] or 0:>12,.0f} "
              f"{row['max_tdd'] or 0:>7} {row['win_rate'] or 0:>6} {row['trades'] or 0:>7}")

    # ---- 2. Monte-Carlo on full OOS 2018-2021 ------------------------------
    print("\n" + "=" * 78); print(f"MONTE-CARLO TDD ({args.mc} shuffles, OOS 2018-2021)"); print("=" * 78)
    for label, params in [("winner", WINNER), ("live", LIVE)]:
        res, trades = run(params, "2018-01-01", "2021-12-31")
        d = daily_pnl(trades)
        if d.empty:
            print(f"  {label}: no trades"); continue
        actual = max_tdd_pct(d, BAL)
        mc = monte_carlo(d, BAL, args.mc)
        out["monte_carlo"][label] = {"actual_tdd": actual, "trading_days": int(len(d)), **mc}
        print(f"  {label:7}: actual TDD {actual:.2f}% | MC mean {mc['tdd_mean']:.2f}% "
              f"p95 {mc['tdd_p95']:.2f}% p99 {mc['tdd_p99']:.2f}% max {mc['tdd_max']:.2f}% "
              f"| P(breach 10%) = {mc['p_breach_10pct']*100:.1f}%")

    Path(args.out).write_text(json.dumps(out, indent=2, default=str))

    # ---- 3. Verdict --------------------------------------------------------
    wf = out["walk_forward"]
    yrs_ok = sum(1 for v in wf.values() if v.get("survived"))
    yrs_tot = sum(1 for v in wf.values() if not v.get("error"))
    pb = out["monte_carlo"].get("winner", {}).get("p_breach_10pct", 1.0)
    print("\n" + "=" * 78)
    print(f"Walk-forward survival: {yrs_ok}/{yrs_tot} years")
    print(f"Winner P(TDD breaches 10% wall): {pb*100:.1f}%")
    if yrs_ok == yrs_tot and pb < 0.05:
        print("✅ ROBUST: survives every year, breach risk <5% — strong candidate")
    elif yrs_ok >= yrs_tot - 1 and pb < 0.15:
        print("⚠️ MARGINAL: mostly robust but real wall-breach risk — needs a safety margin")
    else:
        print("❌ FRAGILE: fails some years or high breach risk — do NOT port as-is")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
