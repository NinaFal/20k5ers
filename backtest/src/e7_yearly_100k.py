#!/usr/bin/env python3
"""
E7 — every year restarted as a FRESH $100k account, month-by-month.

Different question from E6. E6 carried balance forward, so later years traded a
bigger account and the numbers compound. Here each year starts at $100k with no
memory of the previous one, which makes the years directly comparable and shows
what a single funded account actually earns in a given market year.

Reports per year: monthly realized P&L, max daily drawdown vs the 3% wall, max
total drawdown vs the 10% wall, and whether either wall was breached.

Scaling stays on with the user's $175k cap, so within a year the account can
still scale — it just resets to $100k each January.

Resumable per year (this container restarts constantly).

Run:  uv run python3 backtest/src/e7_yearly_100k.py
"""
import argparse, importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_e = importlib.util.spec_from_file_location("e5", str(HERE / "e5_validate_winner.py"))
e5 = importlib.util.module_from_spec(_e); _e.loader.exec_module(e5)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

SCALE_CAP = os.environ.get("E7_SCALE_CAP", "175000")
START_BAL = 100_000.0


def run_year(env, tp, start, end):
    e = dict(os.environ); e.update(cs.dh.BASE_ENV); e.update(env)
    e["FIVEERS_MAX_SCALE"] = str(SCALE_CAP)
    e["OPT_PARAMS"] = json.dumps({**cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        subprocess.run([sys.executable, str(cs.dh.BACKTEST), "--start", start,
                        "--end", end, "--balance", f"{START_BAL:.2f}",
                        "--output", td, "--quiet"],
                       env=e, cwd=str(cs.dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=7200)
        rj = Path(td) / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        return {"net_pnl": r.get("net_pnl"), "final_balance": r.get("final_balance"),
                "withdrawn": r.get("fiveers_total_withdrawn"),
                "final_funded_level": r.get("fiveers_final_funded_level"),
                "scaling_events": r.get("fiveers_scaling_events"),
                "max_tdd_pct": r.get("max_tdd_pct"), "max_ddd_pct": r.get("max_ddd_pct"),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "account_failed": r.get("account_failed"), "fail_info": r.get("fail_info"),
                "monthly_stats": r.get("monthly_stats") or {}}
    finally:
        shutil.rmtree(td, ignore_errors=True)


MONTHS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int,
                    default=list(range(2015, 2025)))
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    out = DOE_DIR / "e7_yearly_100k.json"
    res = json.loads(out.read_text()) if out.exists() else {}

    env = dict(e5.WINNER_ENV)
    tp = dict(e5.TP); tp["risk_per_trade_pct"] = e5.WINNER_RISK

    print(f"[E7] every year a fresh $100k account, scaling cap ${SCALE_CAP}", flush=True)
    for y in args.years:
        key = str(y)
        if key not in res:
            res[key] = run_year(env, tp, f"{y}-01-01", f"{y}-12-31")
            out.write_text(json.dumps(res, indent=2))
        m = res[key]
        if m.get("error"):
            print(f"{y}: ERROR {m['error']}", flush=True); continue
        fail = ""
        if m["account_failed"]:
            fail = f"  *** FAILED: {(m.get('fail_info') or {}).get('reason','')}"
        print(f"\n{y}: net ${m['net_pnl']:,.0f} | payout ${(m.get('withdrawn') or 0):,.0f} "
              f"| maxDDD {m['max_ddd_pct']:.2f}% (3% wall) "
              f"| maxTDD {m['max_tdd_pct']:.2f}% (10% wall) "
              f"| {m['trades']} trades{fail}", flush=True)
        ms = m.get("monthly_stats") or {}
        cells = []
        for mo in MONTHS:
            k = f"{y}-{mo}"
            v = ms.get(k) or {}
            cells.append(f"{mo}:{(v.get('pnl') or 0):>9,.0f}")
        print("   " + "  ".join(cells[:6]), flush=True)
        print("   " + "  ".join(cells[6:]), flush=True)

    done = [res[str(y)] for y in args.years
            if str(y) in res and not res[str(y)].get("error")]
    if done:
        print(f"\n[E7] {len(done)} years | mean net ${sum(x['net_pnl'] for x in done)/len(done):,.0f}"
              f" | mean payout ${sum((x.get('withdrawn') or 0) for x in done)/len(done):,.0f}",
              flush=True)
        print(f"  worst daily DD across years : {max(x['max_ddd_pct'] for x in done):.2f}%  (wall 3%)",
              flush=True)
        print(f"  worst total DD across years : {max(x['max_tdd_pct'] for x in done):.2f}%  (wall 10%)",
              flush=True)
        print(f"  years failed                : {sum(1 for x in done if x['account_failed'])}",
              flush=True)
    print("[e7_yearly_100k] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
