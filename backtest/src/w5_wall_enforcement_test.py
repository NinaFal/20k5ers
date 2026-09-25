#!/usr/bin/env python3
"""
Is the 5% daily wall actually ENFORCED once the account sits at the $500k cap?

The doubt is reasonable. At the cap, main_live_bot_backtest.py:6078 subtracts
scaling payouts from the daily-drawdown measure:

    _payout_today = (self.mt5._payout_balance_removed - _day_start_payout_removed)
    ddd_pct = max(0, (day_start_equity - equity - _payout_today) / day_start_equity * 100)

That subtraction is necessary — a $50k milestone sweep is a balance removal, not
a trading loss, and without it every payout day would register a phantom 10%
breach. But a subtraction that can zero out the measure is exactly the shape a
loophole takes, and "the reported number looks plausible" is not proof that the
kill path still fires.

Reading the code only shows there is no level condition on line 6088. This
tests the behaviour instead, by bracketing the wall around a known drawdown.

2019 at the cap reports a worst daily drawdown of 2.24%. So, holding the year,
the config and the starting level fixed and moving ONLY the wall:

    wall 3.0%  ->  must SURVIVE   (2.24 < 3.0)
    wall 2.0%  ->  must BREACH    (2.24 > 2.0)
    wall 1.5%  ->  must BREACH    (2.24 > 1.5)

If the wall were bypassed at the cap, all three survive and the reported 2.24%
is cosmetic. If the bracket comes out as predicted, the measure is real, the
kill path fires at the cap, and the 2.24% is a number the account genuinely
lived under.

Run:  uv run python3 backtest/src/w5_wall_enforcement_test.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

YEAR = "2019"
LEVEL = 500_000.0
OBSERVED_DDD = 2.24
# (wall pct, expectation) — expectation is what MUST happen for the wall to be
# considered enforced at the cap.
ARMS = (("3.0", "survive"), ("2.0", "breach"), ("1.5", "breach"))


def winner():
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    return b["env"], b["tp"]


def run(env_over, tp_over, wall):
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(env_over)
    e["CFG_DAILY_WALL_PCT"] = wall
    tp = dict(w5.BASE_TP); tp.update(tp_over)
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"wall_{wall.replace('.', '')}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", f"{YEAR}-01-01", "--end", f"{YEAR}-12-31",
                        "--balance", f"{LEVEL:.2f}", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        return {
            "wall_pct": wall,
            "account_failed": bool(r.get("account_failed")),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
            "max_ddd_pct": r.get("max_ddd_pct"),
            "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"),
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    env, tp = winner()
    out = w5.W5_DIR / "wall_enforcement.json"
    res = w5.load_json(out)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    print(f"[wall] {YEAR} at ${LEVEL:,.0f} (capped, no rungs to cross); "
          f"observed DDD {OBSERVED_DDD}%", flush=True)
    for wall, expect in ARMS:
        if wall in res:
            continue
        print(f"[wall] wall={wall}%  expecting {expect}", flush=True)
        res[wall] = run(env, tp, wall)
        w5.atomic_write(out, res)
        r = res[wall]
        if r.get("error"):
            print(f"[wall] wall={wall}%: ERROR {r['error']}", flush=True); continue
        got = "breach" if r["account_failed"] else "survive"
        print(f"[wall] wall={wall}%: {got.upper()}  DDD {r['max_ddd_pct']}%  "
              f"reason {r['fail_reason']}  trades {r['trades']}", flush=True)

    print("\n" + "=" * 62, flush=True)
    print(f"[wall] IS THE {5.0}% DAILY WALL ENFORCED AT THE $500k CAP?", flush=True)
    ok = True
    for wall, expect in ARMS:
        r = res.get(wall) or {}
        if not r or r.get("error"):
            print(f"  wall {wall:>4}%  expected {expect:<8} -> NOT RUN"); ok = False; continue
        got = "breach" if r["account_failed"] else "survive"
        verdict = "OK" if got == expect else "MISMATCH"
        if got != expect:
            ok = False
        print(f"  wall {wall:>4}%  expected {expect:<8} got {got:<8} "
              f"DDD {r['max_ddd_pct']}%   [{verdict}]", flush=True)
    print(f"\n  VERDICT: {'ENFORCED at the cap' if ok else 'NOT CONFIRMED — investigate'}",
          flush=True)
    print("[w5_wall_enforcement_test] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
