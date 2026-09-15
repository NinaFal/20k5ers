#!/usr/bin/env python3
"""
5%ers 2-STEP CHALLENGE evaluator — pass fast AND safely.

Different objective from every prior backtest (which measured funded long-run
profit): here we only care about the EVALUATION phase —
  Step 1: reach +8% (=$8,000 on 100k) before any 5% daily / 10% total breach
  Step 2: reach +5% (=$5,000) from a fresh 100k, same walls
Step 2 is strictly easier than Step 1, so Step 1 is the binding constraint; we
report both.

Metric per config = across MANY start dates: median/worst calendar-days to pass
Step 1, and the BREACH RATE (fraction of starts that hit a wall before passing).
"Best fast+safe" = lowest median days with ~0 breach rate.

Method: run the strategy from a fresh $100k at each start (bounded horizon),
persist trades.csv, rebuild the daily realized-balance curve, find the first day
it crosses +8% / +5%. A run that breaches (results.json account_failed) before
crossing = a challenge FAIL for that start.

Config = t39/cap=3 winner skeleton, CHF pairs excluded (real black swan out),
CORR_GROUP_CAP=3. Sweeps base risk. Resumable per (risk,start) cell.

Run:  uv run python3 backtest/src/challenge_eval.py
"""
import concurrent.futures, csv, importlib.util, json, os, shutil, subprocess, sys, tempfile
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT = DOE_DIR / "challenge_eval.json"

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)
_s = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_s); _s.loader.exec_module(scr)

ACCOUNT = 100_000.0
STEP1 = 0.08 * ACCOUNT     # +$8,000
STEP2 = 0.05 * ACCOUNT     # +$5,000
CHF = "USD_CHF,EUR_CHF,GBP_CHF,AUD_CHF,NZD_CHF,CAD_CHF,CHF_JPY"
HORIZON_DAYS = 150         # cap each run; a viable challenge passes well inside this
RISKS = [1.0, 1.5, 2.0, 2.5]
# Quarterly starts across the black-swan-free years (2015 CHF & 2020 COVID out).
CLEAN_YEARS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
STARTS = [f"{y}-{m:02d}-01" for y in CLEAN_YEARS for m in (1, 4, 7, 10)]


def env39():
    data = json.loads((DOE_DIR / "stage5c_oos_screen.json").read_text())
    e = next(dict(r["env"]) for r in data if int(r["trial"]) == 39)
    e.update({"CORR_GROUP_CAP": "3", "FIVEERS_MAX_SCALE": "4000000", "EXCLUDE_SYMBOLS": CHF})
    return e


def ts(): return datetime.now().strftime("%H:%M:%S")


def days_to_target(trades_csv: Path, start: str):
    """Return (day_to_+5%, day_to_+8%) in calendar days from start, or None if
    not reached. Uses cumulative realized pnl+swap by close date."""
    if not trades_csv.exists():
        return None, None
    by_day = defaultdict(float)
    with open(trades_csv, newline="") as f:
        for row in csv.DictReader(f):
            ct = (row.get("close_time") or "")[:10]
            if not ct:
                continue
            try:
                by_day[ct] += float(row.get("pnl") or 0) + float(row.get("swap") or 0)
            except ValueError:
                pass
    s = date.fromisoformat(start)
    cum = 0.0
    d5 = d8 = None
    for day in sorted(by_day):
        cum += by_day[day]
        elapsed = (date.fromisoformat(day) - s).days
        if d5 is None and cum >= STEP2:
            d5 = elapsed
        if d8 is None and cum >= STEP1:
            d8 = elapsed
            break
    return d5, d8


def run_cell(cell):
    risk, start = cell
    s = date.fromisoformat(start)
    end = (s + timedelta(days=HORIZON_DAYS)).isoformat()
    env = dict(os.environ); env.update(dh.BASE_ENV); env.update(env39())
    tp = dict(scr.TP_OVER); tp["risk_per_trade_pct"] = risk
    env["OPT_PARAMS"] = json.dumps({**dh.BASE_TP, **tp}); env["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        cmd = [sys.executable, str(dh.BACKTEST), "--start", start, "--end", end,
               "--balance", str(int(ACCOUNT)), "--output", td, "--quiet"]
        subprocess.run(cmd, env=env, cwd=str(REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=1800)
        rj = Path(td) / "results.json"
        r = json.loads(rj.read_text()) if rj.exists() else {}
        fi = r.get("fail_info") or {}
        breached = bool(r.get("account_failed"))
        breach_day = None
        if breached and fi.get("time"):
            try:
                breach_day = (date.fromisoformat(str(fi["time"])[:10]) - s).days
            except ValueError:
                pass
        d5, d8 = days_to_target(Path(td) / "trades.csv", start)
        # A start PASSES step1 only if it crossed +8% AND did not breach earlier.
        pass1 = d8 is not None and (breach_day is None or breach_day >= d8)
        out = {"risk_pct": risk, "start": start, "breached": breached,
               "breach_day": breach_day, "day_to_5pct": d5, "day_to_8pct": d8,
               "pass_step1": pass1}
        st = "PASS" if pass1 else ("BREACH" if breached else "slow")
        print(f"[{ts()}] risk={risk:>3}% {start}  {st:>6}"
              f"  +8% in {d8 if d8 is not None else '  -'} d"
              f"  +5% in {d5 if d5 is not None else '  -'} d"
              f"  {'breach@'+str(breach_day)+'d' if breached else ''}", flush=True)
        return out
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    done = {}
    if OUT.exists():
        try:
            done = {(d["risk_pct"], d["start"]): d for d in json.loads(OUT.read_text())}
        except Exception:
            pass
    cells = [(r, s) for r in RISKS for s in STARTS if (r, s) not in done]
    print(f"[{ts()}] challenge eval: {len(cells)} cells "
          f"({len(RISKS)} risks x {len(STARTS)} starts)", flush=True)
    results = list(done.values())
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for o in ex.map(run_cell, cells):
            results.append(o)
            results.sort(key=lambda d: (d["risk_pct"], d["start"]))
            OUT.write_text(json.dumps(results, indent=2, default=str))
    _summary(results)
    print("[challenge_eval] DONE_MARKER", flush=True)


def _summary(results):
    print("\n=== 5%ers 2-step challenge — Step 1 (+8%) speed vs base risk ===", flush=True)
    print("(CHF excluded, cap=3, 100k; quarterly starts across 2016-19 & 2021-24)\n", flush=True)
    print(f"{'risk%':>6}{'starts':>7}{'passed':>8}{'breached':>9}"
          f"{'med days':>9}{'worst':>7}{'breachRate':>11}", flush=True)
    for risk in RISKS:
        rows = [d for d in results if d["risk_pct"] == risk]
        if not rows:
            continue
        passed = [d for d in rows if d["pass_step1"]]
        br = [d for d in rows if d["breached"]]
        days = sorted(d["day_to_8pct"] for d in passed if d["day_to_8pct"] is not None)
        med = days[len(days)//2] if days else None
        worst = days[-1] if days else None
        print(f"{risk:>6}{len(rows):>7}{len(passed):>8}{len(br):>9}"
              f"{(med if med is not None else '-'):>9}{(worst if worst is not None else '-'):>7}"
              f"{len(br)/len(rows)*100:>10.0f}%", flush=True)


if __name__ == "__main__":
    main()
