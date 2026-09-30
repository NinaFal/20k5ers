#!/usr/bin/env python3
"""
$50k start, 2015-2025, with scaling and without — plus the 5ers fixed payouts
kept on their own line.

Two arms, both starting from a $50,000 funded account and running eleven
calendar years, chunked by year so a container restart costs one year:

  scaled   The real 5ers High Stakes ladder. Funded level advances at each +10%
           milestone (50k -> 60k -> 70k -> 80k -> 100k -> 125k -> 150k -> 175k ->
           200k -> 250k -> 300k -> 350k -> 400k -> 450k -> 500k), profit is
           withdrawn at the tier's split, and the level is carried into the next
           year. Capped at $500k as requested. The 10% total-drawdown floor
           ratchets up with the level, which is what makes the climb the
           dangerous phase.

  compound Scaling disabled outright (FIVEERS_SCALING_OFF=1). No level advances,
           no withdrawals; balance compounds from $50k and is carried forward.
           This is NOT a 5ers-realistic account — with the funded level frozen at
           $50k the total-drawdown floor stops chasing equity, so the 10% wall
           effectively falls away once the account is meaningfully above its
           start. Read it as the strategy's raw compounding capacity, not as an
           account you could actually hold. The 5% daily wall still applies.

FIXED PAYOUTS (from the5ers.com/high-stakes): at the top tiers the split is
100/0 AND a fixed cash bonus is paid on each milestone:

    level $350k (target $385k)   100%  + $4,000
    level $400k (target $440k)   100%  + $4,000
    level $450k (target $495k)   100%  + $4,000
    level $500k (max tier)       100%  + $10,000

The simulator does not model these — csv_mt5_simulator.py:367 says so in a
comment. They are reconstructed here from the scaling log and reported on their
OWN line, never folded into trading profit, so the two sources of income stay
legible separately.

A breach ends the account and the remaining years are not run.

Run:  uv run python3 backtest/src/w5_50k_decade.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

START_BALANCE = 50_000.0
YEARS = list(range(2015, 2026))          # 2015-2025 inclusive, 11 years
SCALE_CAP = "500000"
OUT = w5.W5_DIR / "fiftyk_decade.json"

ARMS = (
    ("scaled",   {"FIVEERS_MAX_SCALE": SCALE_CAP}),
    ("compound", {"FIVEERS_SCALING_OFF": "1"}),
)


def fixed_bonus_for_level(level: float) -> int:
    """5ers High Stakes fixed cash payout for a milestone paid AT `level`."""
    if level >= 500_000:
        return 10_000
    if level >= 350_000:
        return 4_000
    return 0


def run_year(over, year, balance, tag):
    b = json.loads((w5.W5_DIR / "current_best.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(b["env"]); e.update(over)
    e["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"k50_{tag}_{year}"
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
        bonus, bonus_events = 0, []
        for ev in log:
            lvl = ev.get("old_level") or 0
            amt = fixed_bonus_for_level(lvl)
            if amt:
                bonus += amt
                bonus_events.append({"time": ev.get("time"), "level": lvl, "amount": amt})
        return {
            "start_balance": balance,
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
            "fixed_bonus": bonus,
            "fixed_bonus_events": bonus_events,
            "final_balance": r.get("final_balance"),
            "funded_level_end": (log[-1]["new_level"] if log else balance),
            "scale_ups": len(log),
            "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
            "account_failed": r.get("account_failed"),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def carry(arm, r, prev):
    """What the next year starts from."""
    if arm == "compound":
        # No withdrawals: the account simply continues at its closing balance.
        return r.get("final_balance") or prev
    return r.get("funded_level_end") or prev


def main():
    res = w5.load_json(OUT)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    for arm, over in ARMS:
        slot = res.setdefault(arm, {"years": {}})
        if slot.get("dead"):
            print(f"[50k] {arm}: already dead — skipping", flush=True); continue
        bal = START_BALANCE
        for y in YEARS:
            if str(y) in slot["years"]:
                bal = carry(arm, slot["years"][str(y)], bal); continue
            print(f"[50k] {arm} {y}: starting at ${bal:,.0f}", flush=True)
            r = run_year(over, y, bal, arm)
            slot["years"][str(y)] = r
            w5.atomic_write(OUT, res)
            if r.get("error"):
                print(f"[50k] {arm} {y}: ERROR {r['error']}", flush=True); break
            cw = sum((v.get("withdrawn") or 0) for v in slot["years"].values())
            cb = sum((v.get("fixed_bonus") or 0) for v in slot["years"].values())
            print(f"[50k] {arm} {y}: payout ${r['withdrawn']:,.0f} "
                  f"bonus ${r['fixed_bonus']:,.0f} "
                  f"(cum trading ${cw:,.0f} + bonus ${cb:,.0f}) "
                  f"bal ${(r.get('final_balance') or 0):,.0f} "
                  f"lvl ${(r.get('funded_level_end') or 0):,.0f} "
                  f"DDD {r['max_ddd_pct']}% TDD {r['max_tdd_pct']}% win {r['win_rate']}%"
                  + (f"  <-- DIED: {r['fail_reason']}" if r.get("account_failed") else ""),
                  flush=True)
            if r.get("account_failed"):
                slot["dead"] = {"year": y, "reason": r.get("fail_reason")}
                w5.atomic_write(OUT, res); break
            bal = carry(arm, r, bal)
        ys = slot["years"]
        slot["total_withdrawn"] = sum((v.get("withdrawn") or 0) for v in ys.values())
        slot["total_fixed_bonus"] = sum((v.get("fixed_bonus") or 0) for v in ys.values())
        slot["survived"] = not slot.get("dead") and len(ys) == len(YEARS)
        w5.atomic_write(OUT, res)

    print("\n" + "=" * 78, flush=True)
    print("[50k] $50,000 START — 2015-2025 — TRADING PROFIT AND FIXED PAYOUTS SEPARATE",
          flush=True)
    for arm, _ in ARMS:
        slot = res.get(arm) or {}
        ys = [v for v in slot.get("years", {}).values() if not v.get("error")]
        if not ys:
            continue
        wd = max((v.get("max_ddd_pct") or 0) for v in ys)
        wt = max((v.get("max_tdd_pct") or 0) for v in ys)
        trading = slot.get("total_withdrawn", 0)
        bonus = slot.get("total_fixed_bonus", 0)
        final = ys[-1].get("final_balance") or 0
        print(f"\n  --- {arm} ---  {'SURVIVED' if slot.get('survived') else 'DIED ' + str(slot.get('dead', {}).get('year', '?'))}"
              f"  ({len(ys)}/{len(YEARS)} years)", flush=True)
        print(f"    trading profit withdrawn   ${trading:>14,.0f}", flush=True)
        print(f"    fixed payouts (350k+)      ${bonus:>14,.0f}", flush=True)
        print(f"    ---------------------------{'-' * 15}", flush=True)
        print(f"    combined                   ${trading + bonus:>14,.0f}", flush=True)
        print(f"    closing balance            ${final:>14,.0f}", flush=True)
        print(f"    worst daily {wd}% / 5%     worst total {wt}% / 10%", flush=True)
    print("\n[w5_50k_decade] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
