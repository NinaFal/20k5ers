#!/usr/bin/env python3
"""
Why is drawdown LOWER at the $500k cap than while climbing to it?

The observation: on the same config, capped years run 1.7-3.4% worst daily
drawdown while climbing years run 4.7-4.9%. That looks backwards — a bigger
account "should" be riskier, and risk here is a percentage of balance, so the
level alone should cancel out.

The hypothesis, from csv_mt5_simulator._apply_fiveers_scaling:

    if self._funded_level < self._max_balance:
        next_level = self._next_fiveers_level(self._funded_level)
        self._funded_level = next_level
        self._balance = next_level          # <-- line 386

Crossing a rung does NOT just bank profit; 5ers hands you the next account
size, so BALANCE JUMPS UPWARD by more than you earned. Off the $100k rung you
reach the milestone at $110k and land at $125k — position sizing instantly
grows ~14% mid-day, while the daily-drawdown yardstick (day_start_equity, fixed
at the day's open) stays anchored to the pre-jump number. Ten rungs, ten jumps
of +11% to +25%, all taken while climbing.

At the cap there is no next rung: balance is reset DOWN to $500k and that
removal is explicitly excluded from the daily-drawdown measure. No upward jump,
no denominator mismatch, sizing stays in a narrow band.

If that is right, the driver is the ACT of scaling, not the LEVEL. This probe
isolates it: the same calendar year, same config, same price data, run once
from $100k (crosses every rung) and once from $500k (already capped, crosses
none). Market conditions are held identical, so any gap in worst daily
drawdown is attributable to the rung crossings alone.

Run:  uv run python3 backtest/src/w5_scaling_dd_probe.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

YEARS = ("2016", "2019", "2021")     # 2016 climbs in the continuous run; the
                                     # other two are capped there, so running
                                     # them from $100k gives the mirror image.
ARMS = (("climb_100k", 100_000.0), ("capped_500k", 500_000.0))


def winner():
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    return b["env"], b["tp"]


def run(env_over, tp_over, year, balance, tag):
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(env_over)
    tp = dict(w5.BASE_TP); tp.update(tp_over)
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"probe_{tag}_{year}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", f"{year}-01-01", "--end", f"{year}-12-31",
                        "--balance", f"{balance:.2f}", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        return {
            "start_balance": balance,
            "scale_ups": len(log),
            "rungs": [f"{int(x['old_level']/1000)}k->{int(x['new_level']/1000)}k" for x in log],
            "max_ddd_pct": r.get("max_ddd_pct"),
            "max_tdd_pct": r.get("max_tdd_pct"),
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
            "trades": r.get("total_trades"),
            "win_rate": r.get("win_rate"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    env, tp = winner()
    out = w5.W5_DIR / "scaling_dd_probe.json"
    res = w5.load_json(out)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    for year in YEARS:
        for tag, bal in ARMS:
            key = f"{year}_{tag}"
            if key in res:
                continue
            print(f"[probe] {key}: running", flush=True)
            res[key] = run(env, tp, year, bal, tag)
            w5.atomic_write(out, res)
            r = res[key]
            if r.get("error"):
                print(f"[probe] {key}: ERROR {r['error']}", flush=True); continue
            print(f"[probe] {key}: DDD {r['max_ddd_pct']}%  TDD {r['max_tdd_pct']}%  "
                  f"scale-ups {r['scale_ups']}  trades {r['trades']}", flush=True)

    print("\n" + "=" * 66, flush=True)
    print("[probe] SAME YEAR, SAME CONFIG, ONLY THE STARTING LEVEL DIFFERS", flush=True)
    print("  {:<6}{:>26}{:>26}{:>10}".format("year", "climb $100k", "capped $500k", "delta"),
          flush=True)
    for year in YEARS:
        a = res.get(f"{year}_climb_100k", {}); b = res.get(f"{year}_capped_500k", {})
        if not a or not b or a.get("error") or b.get("error"):
            continue
        la = "DDD {}%  ({} rungs)".format(a["max_ddd_pct"], a["scale_ups"])
        lb = "DDD {}%  ({} rungs)".format(b["max_ddd_pct"], b["scale_ups"])
        try:
            delta = "{:+.2f}pp".format(b["max_ddd_pct"] - a["max_ddd_pct"])
        except TypeError:
            delta = "-"
        print("  {:<6}{:>26}{:>26}{:>10}".format(year, la, lb, delta), flush=True)
    print("[w5_scaling_dd_probe] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
