#!/usr/bin/env python3
"""
E8 — does more halt headroom save the two December deaths?

The 2019 and 2020 failures were 3.29% and 3.17% against a 3.0% wall, both
detected `[bar]` — i.e. at a 15-minute boundary. The user's argument is that on
M15 data the engine can only react at bar close, so an intrabar excursion gets
booked as a breach where a live bot polling continuously would have halted
earlier and survived. That is a fair point about granularity.

It cannot be tested directly (M15 is the finest data available), but it has an
actionable equivalent: a live bot reacting sooner is behaviourally the same as
a backtest bot halting at a LOWER threshold. If dropping CFG_DAILY_HALT_PCT
from 2.0% to 1.75/1.5/1.25% converts 2019 and 2020 into survivors, then the
overshoot is within the range faster reaction would plausibly absorb, and the
deaths are partly an artifact. If they die even at 1.25%, the loss is arriving
in one move too large for any reaction speed to help, and the granularity
argument does not save them.

Also reports what the extra headroom costs in payout, since a tighter halt
stops trading earlier on ordinary days too.

Run:  uv run python3 backtest/src/e8_halt_headroom.py
"""
import argparse, importlib.util, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"
_e = importlib.util.spec_from_file_location("e5", str(HERE / "e5_validate_winner.py"))
e5 = importlib.util.module_from_spec(_e); _e.loader.exec_module(e5)
_x = importlib.util.spec_from_file_location("e7", str(HERE / "e7_yearly_100k.py"))
e7 = importlib.util.module_from_spec(_x); _x.loader.exec_module(e7)
os.environ.setdefault("RUN_TIMEOUT_S", "999999")

HALTS = ["2.0", "1.75", "1.5", "1.25"]
YEARS = [2019, 2020]          # the two daily-wall deaths
CONTROL_YEARS = [2017, 2021]  # survivors — to price what the tighter halt costs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=YEARS + CONTROL_YEARS)
    ap.add_argument("--halts", nargs="*", default=HALTS)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    out = DOE_DIR / "e8_halt_headroom.json"
    res = json.loads(out.read_text()) if out.exists() else {}

    tp = dict(e5.TP); tp["risk_per_trade_pct"] = e5.WINNER_RISK
    print(f"[E8] halt headroom vs the 3% wall — {args.halts}", flush=True)
    print(f"{'year':>5} {'halt':>6} {'net':>11} {'payout':>10} {'maxDDD':>7} "
          f"{'maxTDD':>7} {'survived':>9}", flush=True)

    for y in args.years:
        for h in args.halts:
            key = f"{y}/{h}"
            if key not in res:
                env = dict(e5.WINNER_ENV)
                env["CFG_DAILY_HALT_PCT"] = h
                res[key] = e7.run_year(env, tp, f"{y}-01-01", f"{y}-12-31")
                out.write_text(json.dumps(res, indent=2))
            m = res[key]
            if m.get("error"):
                print(f"{y:>5} {h:>6}  ERROR {m['error']}", flush=True); continue
            print(f"{y:>5} {h:>6} {m['net_pnl']:>11,.0f} "
                  f"{(m.get('withdrawn') or 0):>10,.0f} {m['max_ddd_pct']:>6.2f}% "
                  f"{m['max_tdd_pct']:>6.2f}% {str(not m['account_failed']):>9}", flush=True)
        print("", flush=True)

    print("[e8_halt_headroom] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
