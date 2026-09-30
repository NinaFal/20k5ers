#!/usr/bin/env python3
"""
Can t65 be saved? Sweep the safety dials against the year that killed it.

t65 (nightly stage) is the most profitable config this round has produced:
nine clean years, $2,433,990 withdrawn, then 6.24% daily drawdown in 2025 —
1.24 points over the wall. Everything else about it is better than the
incumbent: p30 0.84 vs 0.60, median 17d vs 28d, win rate 52-59% vs ~46%.

Stage 7 cannot rescue it: that stage compounds on t105, so it never revisits
t65's overnight-flat settings. This tests t65 directly.

Two phases, cheapest first:
  1. 2025 ONLY, across a ladder of halt settings. One year per config (~4 min)
     rather than ten, because a config that still breaches 2025 is dead and
     there is no reason to pay for the other nine years.
  2. Full decade for anything that survives 2025 — a fix that saves 2025 by
     making every other year unprofitable is not a fix.

The dials, in the order they bite:
  CFG_DAILY_HALT_PCT   stop trading for the day at this drawdown. The direct
                       lever: t65 reached 6.24%, so halting at 2.5-3.0% should
                       cut the day off well before the wall.
  TDD_WALL_SAFETY      how far from the total wall the size-reduction starts.
  CFG_TDD_*_PCT        the drawdown tiers that shrink risk as losses build.

Run:  uv run python3 backtest/src/w5_rescue_t65.py
"""
import importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

KILL_YEAR = 2025

# halt / safety ladders, loosest first so the cheapest acceptable fix is visible
VARIANTS = [
    ("baseline",      {}),
    ("halt3.00",      {"CFG_DAILY_HALT_PCT": "3.00"}),
    ("halt2.75",      {"CFG_DAILY_HALT_PCT": "2.75"}),
    ("halt2.50",      {"CFG_DAILY_HALT_PCT": "2.50"}),
    ("halt2.25",      {"CFG_DAILY_HALT_PCT": "2.25"}),
    ("halt2.00",      {"CFG_DAILY_HALT_PCT": "2.00"}),
    ("halt2.50+tdd",  {"CFG_DAILY_HALT_PCT": "2.50", "TDD_WALL_SAFETY": "5.5",
                       "CFG_TDD_CAUTION_PCT": "1.5", "CFG_RISK_CAUTIOUS": "0.4",
                       "CFG_TDD_WARNING_PCT": "2.5", "CFG_RISK_CONSERVATIVE": "0.25"}),
    ("halt2.75+cum",  {"CFG_DAILY_HALT_PCT": "2.75", "CFG_MAX_CUM_RISK": "5.0"}),
    ("halt2.75+pos",  {"CFG_DAILY_HALT_PCT": "2.75", "MAX_TOTAL_POSITIONS": "15"}),
]


def t65_config():
    c = [x for x in json.loads((w5.W5_DIR / "nightly_top20.json").read_text())
         if str(x["trial"]) == "65"][0]
    env = dict(w5.BASE_ENV); env.update(c["env"]); env["TDD_WORST_CASE"] = "1"
    tp = dict(w5.BASE_TP); tp.update(c["tp"])
    return env, tp


def main():
    out = w5.W5_DIR / "rescue_t65.json"
    res = w5.load_json(out)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    base_env, tp = t65_config()

    print(f"[rescue] phase 1 — {KILL_YEAR} only, {len(VARIANTS)} halt settings", flush=True)
    for name, over in VARIANTS:
        key = f"{name}|{KILL_YEAR}"
        if key in res:
            print(f"[rescue] {name}: cached", flush=True); continue
        env = dict(base_env); env.update(over)
        r = w5.decade_run(env, tp, KILL_YEAR)
        res[key] = {"variant": name, "over": over, **r}
        w5.atomic_write(out, res)
        ok = not r.get("account_failed")
        print(f"[rescue] {name:14} {KILL_YEAR}: {'SURVIVES' if ok else 'BREACH'} "
              f"DDD {r.get('max_ddd_pct')}%  payout ${(r.get('withdrawn') or 0):,.0f}  "
              f"trades {r.get('trades')}  win {r.get('win_rate')}%", flush=True)

    survivors = [n for n, _ in VARIANTS
                 if not res.get(f"{n}|{KILL_YEAR}", {}).get("account_failed", True)]
    print(f"\n[rescue] {len(survivors)} of {len(VARIANTS)} survive {KILL_YEAR}: {survivors}", flush=True)

    # phase 2: full decade for the survivors, cheapest fix first
    for name in survivors:
        over = dict(next(o for n, o in VARIANTS if n == name))
        env = dict(base_env); env.update(over)
        slot = res.setdefault(f"{name}|decade", {"variant": name, "over": over, "years": {}})
        if slot.get("done"):
            continue
        for y in w5.DECADE_YEARS:
            if str(y) in slot["years"]:
                continue
            if any(v.get("account_failed") for v in slot["years"].values()):
                break
            slot["years"][str(y)] = w5.decade_run(env, tp, y)
            w5.atomic_write(out, res)
        yrs = slot["years"]
        failed = [y for y, v in yrs.items() if v.get("account_failed")]
        slot["clean"] = len(yrs) == len(w5.DECADE_YEARS) and not failed
        slot["payout"] = sum((v.get("withdrawn") or 0) for v in yrs.values())
        slot["done"] = True
        w5.atomic_write(out, res)
        print(f"[rescue] {name:14} decade: {'CLEAN' if slot['clean'] else f'FAILED {failed}'}  "
              f"payout ${slot['payout']:,.0f}  "
              f"worstDDD {max((v.get('max_ddd_pct') or 0) for v in yrs.values()):.2f}%", flush=True)
    print("[w5_rescue_t65] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
