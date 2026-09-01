#!/usr/bin/env python3
"""
Capacity report for the continuous 2016-2025 account.

Answers the question the per-year gauntlet cannot: once the account has climbed
100k -> 500k and the scaling ladder is CAPPED, what does it actually earn per
year, and how much of the decade is spent at full size?

Above the cap the 5ers model stops ratcheting the funded level: profit beyond
each +10% milestone is withdrawn instead, at a 100% split once the level is
>= 350k. So payouts after the cap date are the steady-state earning rate of a
$500k account — which is the number that matters for a real funded account and
which every fresh-$100k year in the gauntlet understates.

Run:  uv run python3 backtest/src/w5_capacity_report.py
"""
import importlib.util, json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

CAP = 500_000


def report(name, r):
    print(f"\n═══ {name} ═══")
    if r.get("error"):
        print(f"  no result: {r['error']}"); return
    log = r.get("scaling_log") or []
    withdrawn = r.get("withdrawn") or 0.0
    print(f"  scale-ups {r.get('scale_ups')}   funded level at end "
          f"${(r.get('funded_level_end') or 0):,.0f}")
    print(f"  total withdrawn ${withdrawn:,.0f}   worst daily DD {r.get('max_ddd_pct')}%   "
          f"worst total DD {r.get('max_tdd_pct')}%")
    if r.get("account_failed"):
        print(f"  ACCOUNT DIED: {r.get('fail_reason')} @ {r.get('fail_time')}")

    capped = [s for s in log if (s.get("to") or 0) >= CAP]
    if not capped:
        top = max((s.get("to") or 0) for s in log) if log else 100_000
        print(f"  never reached the ${CAP:,} cap — peak funded level ${top:,.0f}")
    else:
        cap_date = capped[0]["time"]
        pre = sum(s["payout"] for s in log if s["time"] < cap_date)
        post = withdrawn - pre
        d0 = date.fromisoformat(cap_date)
        end = date.fromisoformat((r.get("fail_time") or "2025-12-31")[:10])
        yrs = max((end - d0).days / 365.25, 1e-9)
        print(f"  reached ${CAP:,} on {cap_date} "
              f"({(d0 - date(2016, 1, 1)).days / 365.25:.1f} yrs from start)")
        print(f"  withdrawn while climbing   ${pre:,.0f}")
        print(f"  withdrawn at full size     ${post:,.0f} over {yrs:.1f} yrs "
              f"= ${post / yrs:,.0f}/yr")

    # payout by calendar year, from the scaling log
    by = {}
    for s in log:
        by[s["time"][:4]] = by.get(s["time"][:4], 0.0) + s["payout"]
    if by:
        print("  payout by year (from scale-up events):")
        for y in sorted(by):
            print(f"    {y}  ${by[y]:>12,.0f}")


if __name__ == "__main__":
    p = w5.W5_DIR / "continuous_decade.json"
    if not p.exists():
        raise SystemExit("continuous_decade.json not found — run w5_continuous.py first")
    res = json.loads(p.read_text())
    for name in ("t105_wc", "t61_incumbent_wc", "t61_incumbent", "t4_risk2.9"):
        if name in res:
            report(name, res[name])
    print()
