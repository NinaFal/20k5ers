#!/usr/bin/env python3
"""
Continuous 2016-2025 account, CHUNKED by year so it survives container restarts.

The single-process version (w5_continuous.py) is the cleanest model of one
account but caches nothing on the way, and this container has killed it three
times at ~40-60 minutes in. This runs year by year instead, carrying the 5ers
FUNDED LEVEL forward, and persists after every year — so a restart costs one
year, not the whole decade.

Why carrying the funded level is a fair model rather than a fudge: the 5ers
total-drawdown floor is anchored to the funded level, and the level ratchets at
each +10% milestone. Starting year N+1 at the level reached in year N therefore
reproduces the rule the account actually lives under, which is exactly what the
fresh-$100k gauntlet destroys every January.

Two honest limitations:
  * Unpaid profit sitting above the funded level at 31 Dec is dropped (balance
    is re-seeded at the level). That UNDERSTATES the account slightly.
  * A drawdown spanning the year boundary is split in two, so the worst TOTAL
    drawdown can be understated if a slide runs through December into January.

A breach ENDS the account: remaining years are not run.

Run:  uv run python3 backtest/src/w5_continuous_chunked.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

ARMS = ("t65rescue_wc", "t105_wc", "t61_incumbent_wc")


def load_cfg(name):
    if name == "t65rescue_wc":
        # t65 (nightly stage) + the TDD-tier tightening that made it survive the
        # decade. Best config of the round: $2,771,302 fresh-$100k, p30 0.84.
        c = [x for x in json.loads((w5.W5_DIR / "nightly_top20.json").read_text())
             if str(x["trial"]) == "65"][0]
        e = dict(c["env"]); e["TDD_WORST_CASE"] = "1"
        e.update({"CFG_DAILY_HALT_PCT": "2.50", "TDD_WALL_SAFETY": "5.5",
                  "CFG_TDD_CAUTION_PCT": "1.5", "CFG_RISK_CAUTIOUS": "0.4",
                  "CFG_TDD_WARNING_PCT": "2.5", "CFG_RISK_CONSERVATIVE": "0.25"})
        return e, c["tp"]
    if name == "t105_wc":
        c = [x for x in json.loads((w5.W5_DIR / "riskwc_top20.json").read_text())
             if str(x["trial"]) == "105"][0]
        e = dict(c["env"]); e["TDD_WORST_CASE"] = "1"
        return e, c["tp"]
    if name == "t61_incumbent_wc":
        b = json.loads((w5.W5_DIR / "ladder_survivors.json").read_text())[0]
        e = dict(b["env"]); e["TDD_WORST_CASE"] = "1"
        return e, b["tp"]
    raise SystemExit(f"unknown config {name}")


def run_year(env_over, tp_over, year, balance, tag):
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(env_over)
    tp = dict(w5.BASE_TP); tp.update(tp_over)
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"chunk_{tag}_{year}"
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
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
            "funded_level_end": (log[-1]["new_level"] if log else balance),
            "scale_ups": len(log),
            "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"),
            "win_rate": r.get("win_rate"),
            "win_rate_final_leg": r.get("win_rate_final_leg"),
            "account_failed": r.get("account_failed"),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    out = w5.W5_DIR / "continuous_chunked.json"
    res = w5.load_json(out)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    for name in ARMS:
        env, tp = load_cfg(name)
        slot = res.setdefault(name, {"years": {}})
        if slot.get("dead"):
            print(f"[cc] {name}: already dead — skipping", flush=True); continue
        bal = 100_000.0
        for y in w5.DECADE_YEARS:
            if str(y) in slot["years"]:
                bal = slot["years"][str(y)].get("funded_level_end") or bal
                continue
            print(f"[cc] {name} {y}: starting at ${bal:,.0f}", flush=True)
            r = run_year(env, tp, y, bal, name)
            slot["years"][str(y)] = r
            w5.atomic_write(out, res)
            if r.get("error"):
                print(f"[cc] {name} {y}: ERROR {r['error']}", flush=True); break
            tot = sum((v.get("withdrawn") or 0) for v in slot["years"].values())
            print(f"[cc] {name} {y}: level ${(r['funded_level_end'] or 0):,.0f} "
                  f"payout ${r['withdrawn']:,.0f} (cum ${tot:,.0f}) "
                  f"DDD {r['max_ddd_pct']}% TDD {r['max_tdd_pct']}% win {r['win_rate']}%"
                  + (f"  <-- DIED: {r['fail_reason']}" if r.get("account_failed") else ""),
                  flush=True)
            if r.get("account_failed"):
                slot["dead"] = {"year": y, "reason": r.get("fail_reason")}
                w5.atomic_write(out, res); break
            bal = r["funded_level_end"] or bal
        slot["total_withdrawn"] = sum((v.get("withdrawn") or 0)
                                      for v in slot["years"].values())
        slot["survived"] = not slot.get("dead") and len(slot["years"]) == len(w5.DECADE_YEARS)
        w5.atomic_write(out, res)
        print(f"[cc] {name}: {'SURVIVED' if slot['survived'] else 'DIED'} "
              f"total withdrawn ${slot['total_withdrawn']:,.0f}", flush=True)
    print("[w5_continuous_chunked] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
