#!/usr/bin/env python3
"""
Where should the scaling cap sit? Is it better to stop climbing early, bank
profit, and never reach $500k?

The premise behind the question is sound: every account this project has killed
died while CLIMBING, and the continuous decade's worst day (4.73%) was 2016, its
only climbing year — capped years ran 1.78%-2.91%. So the climb is the risk.

The inference that a LOWER cap is therefore safer is the thing to test, because
the risk model is entirely percentage-based: risk_per_trade_pct is a percentage
of balance, the daily wall is a percentage of day-start equity, the milestone is
a percentage of the funded level. If that holds, percentage drawdown at a $200k
cap and at a $500k cap should be indistinguishable, and a low cap buys no safety
at all — it only shortens the climb that precedes it.

What a low cap definitely does cost is income. Each milestone cycle pays
0.10 * level * split, and 5ers' split worsens as the level drops (100% at
$350k+, 90% at $250k+, 85% at $175k+, 80% below). Cycles per year should be
roughly level-independent, again because +10% is a percentage. So payout should
fall faster than linearly as the cap comes down.

This runs the full continuous 2016-2025 account — funded level carried forward,
exactly as w5_continuous_chunked does — at four caps, and reports what each one
actually earns and actually risks. FIVEERS_MAX_SCALE is the real knob; every cap
below is an actual rung on the 5ers ladder, which matters because the simulator
only stops cleanly when funded_level == max_balance.

$500k is already measured ($3,400,723, worst DDD 4.73%) and is re-stated from
the existing run rather than recomputed.

Run:  uv run python3 backtest/src/w5_cap_sweep.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

CAPS = ("150000", "250000", "350000")   # $500k already measured; all are rungs
SPLIT_AT = {"150000": "80%", "250000": "90%", "350000": "100%", "500000": "100%"}


def winner():
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    return b["env"], b["tp"]


def run_year(env_over, tp_over, cap, year, balance):
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(env_over)
    e["FIVEERS_MAX_SCALE"] = cap
    tp = dict(w5.BASE_TP); tp.update(tp_over)
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"cap_{cap}_{year}"
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
            "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
            "account_failed": r.get("account_failed"),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    env, tp = winner()
    out = w5.W5_DIR / "cap_sweep.json"
    res = w5.load_json(out)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    for cap in CAPS:
        slot = res.setdefault(cap, {"years": {}})
        if slot.get("dead"):
            print(f"[cap] {cap}: already dead — skipping", flush=True); continue
        bal = 100_000.0
        for y in w5.DECADE_YEARS:
            if str(y) in slot["years"]:
                bal = slot["years"][str(y)].get("funded_level_end") or bal
                continue
            r = run_year(env, tp, cap, y, bal)
            slot["years"][str(y)] = r
            w5.atomic_write(out, res)
            if r.get("error"):
                print(f"[cap] {cap} {y}: ERROR {r['error']}", flush=True); break
            tot = sum((v.get("withdrawn") or 0) for v in slot["years"].values())
            print(f"[cap] ${int(cap)//1000}k {y}: payout ${r['withdrawn']:,.0f} "
                  f"(cum ${tot:,.0f}) DDD {r['max_ddd_pct']}% TDD {r['max_tdd_pct']}% "
                  f"rungs {r['scale_ups']}"
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
        print(f"[cap] ${int(cap)//1000}k: {'SURVIVED' if slot['survived'] else 'DIED'} "
              f"total ${slot['total_withdrawn']:,.0f}", flush=True)

    # $500k comes from the existing continuous run rather than being re-run.
    cc = w5.load_json(w5.W5_DIR / "continuous_chunked.json").get("t65rescue_wc")
    print("\n" + "=" * 78, flush=True)
    print("[cap] SCALING CAP SWEEP — same config, same decade, only the cap differs", flush=True)
    print("  {:>8}{:>8}{:>16}{:>12}{:>12}{:>10}".format(
        "cap", "split", "10y withdrawn", "worst DDD", "worst TDD", "status"), flush=True)
    rows = [(c, res.get(c)) for c in CAPS]
    if cc:
        rows.append(("500000", cc))
    for cap, slot in rows:
        if not slot:
            continue
        ys = [v for v in slot["years"].values() if not v.get("error")]
        if not ys:
            continue
        wd = max((v.get("max_ddd_pct") or 0) for v in ys)
        wt = max((v.get("max_tdd_pct") or 0) for v in ys)
        status = "survived" if slot.get("survived") else f"DIED {slot.get('dead', {}).get('year', '?')}"
        print("  {:>8}{:>8}{:>16}{:>12}{:>12}{:>10}".format(
            f"${int(cap)//1000}k", SPLIT_AT.get(cap, "?"),
            f"${slot.get('total_withdrawn', 0):,.0f}",
            f"{wd}%", f"{wt}%", status), flush=True)
    print("\n  If percentage drawdown is flat across caps, a lower cap buys no safety\n"
          "  and only costs income. If it falls with the cap, the climb is not the\n"
          "  whole story and the cap itself is a risk dial.", flush=True)
    print("[w5_cap_sweep] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
