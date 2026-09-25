#!/usr/bin/env python3
"""
Can any surviving variant hold the 2019-08-20 edge case?

The holdout's one breach (start 2019-07-31) died on 2019-08-20 13:45 UTC, day 6
of Step 2, at 5.13% against the 5% daily wall. Bracketing it showed the same
window survives at 3.45% under bar-close marking, so the account sits on the
edge rather than clearly over it — but every headline number in this round was
produced under worst-case marking, and the consistent thing to do is fix the
window and vary the config, not relax the convention for the one result that
went against us.

What the diagnosis rules out: halt tuning. The kill is tagged [bar], meaning the
excursion happened inside a single M15 bar, and ddd_halts_midbar was 0 — there
was no intervening SL fill to trigger a mid-bar re-check. A halt that only
evaluates at bar boundaries cannot act inside a bar it never saw the middle of.
Six halt thresholds from 3.5% down to 2.00% were already shown byte-identical
earlier in this round, so the halt dial is inert here for a second reason.

That leaves one real defence against an intrabar gap: carry less exposure into
it. So this tests the configs that differ in exposure rather than in reaction
speed, on the exact window that killed the winner:

  t65_tdd   the promoted winner       decade \$2,771,302
  t65_pos   MAX_TOTAL_POSITIONS 15    decade \$2,618,740, also CLEAN
  t65_cum   CFG_MAX_CUM_RISK 5.0      decade \$1,405,484, FAILED 2021

t65_cum is included as a control, not a candidate — it already failed the
decade, so if it alone survives this window that tells us the window rewards
something the decade punishes.

A pass here does not make a config safe; one window is one window. A failure
here is the informative direction: it would mean exposure reduction does not
address this failure mode either, and the residual ~2 per 100 is the price of
the strategy rather than a tuning problem.

Run:  uv run python3 backtest/src/w5_edgecase_20190820.py
"""
import importlib.util, json, os, shutil, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

STEP2_START = "2019-08-14"
OUT = w5.W5_DIR / "edgecase_20190820.json"

VARIANTS = {
    "t65_tdd": {"CFG_DAILY_HALT_PCT": "2.50", "TDD_WALL_SAFETY": "5.5",
                "CFG_TDD_CAUTION_PCT": "1.5", "CFG_RISK_CAUTIOUS": "0.4",
                "CFG_TDD_WARNING_PCT": "2.5", "CFG_RISK_CONSERVATIVE": "0.25"},
    "t65_pos": {"CFG_DAILY_HALT_PCT": "2.75", "MAX_TOTAL_POSITIONS": "15"},
    "t65_cum": {"CFG_DAILY_HALT_PCT": "2.75", "CFG_MAX_CUM_RISK": "5.0"},
}


def base():
    c = [x for x in json.loads((w5.W5_DIR / "nightly_top20.json").read_text())
         if str(x["trial"]) == "65"][0]
    return c["env"], c["tp"]


def run(over, tp_over, tag):
    env = dict(os.environ); env.update(w5.cs.dh.BASE_ENV); env.update(w5.BASE_ENV)
    env.update(over)
    env["TDD_WORST_CASE"] = "1"          # the round's standard — held fixed
    env["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    env.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(tp_over)
    env["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    env["PYTHONUTF8"] = "1"
    end = (date.fromisoformat(STEP2_START) + timedelta(days=w5.HORIZON)).isoformat()
    d = w5.DOE_DIR / "tmp" / f"edge_{tag}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", STEP2_START, "--end", end,
                        "--balance", "100000", "--output", str(d), "--quiet"],
                       env=env, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=3600)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text()); fi = r.get("fail_info") or {}
        return {"account_failed": bool(r.get("account_failed")),
                "fail_reason": fi.get("reason"), "fail_time": fi.get("time"),
                "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
                "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
                "safety_events": r.get("safety_events"), "ddd_halts": r.get("ddd_halts"),
                "ddd_halts_midbar": r.get("ddd_halts_midbar")}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    env0, tp0 = base()
    res = w5.load_json(OUT)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    print(f"[edge] window {STEP2_START} +{w5.HORIZON}d, wall 5.0%, "
          f"TDD_WORST_CASE=1 held fixed", flush=True)
    for tag, over in VARIANTS.items():
        if tag in res:
            continue
        e = dict(env0); e.update(over)
        res[tag] = run(e, tp0, tag)
        w5.atomic_write(OUT, res)
        r = res[tag]
        if r.get("error"):
            print(f"[edge] {tag}: ERROR {r['error']}", flush=True); continue
        print(f"[edge] {tag:9} {'BREACHED' if r['account_failed'] else 'survived':9} "
              f"DDD {r['max_ddd_pct']}%  TDD {r['max_tdd_pct']}%  "
              f"trades {r['trades']}  halts {r['ddd_halts']}/{r['ddd_halts_midbar']}mid"
              + (f"  {r['fail_reason']}" if r.get("fail_reason") else ""), flush=True)
    surv = [t for t, r in res.items() if not r.get("error") and not r["account_failed"]]
    print(f"\n[edge] survive this window: {surv or 'NONE'}", flush=True)
    if not surv:
        print("  Exposure reduction does not address this failure mode either.\n"
              "  The residual breach rate is a property of the strategy on intrabar\n"
              "  gaps, not a tuning problem — treat ~2 per 100 as the floor.", flush=True)
    print("[w5_edgecase_20190820] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
