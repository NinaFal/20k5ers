#!/usr/bin/env python3
"""
C0 — single source of truth for scoring the 100k 2-step challenge.

Models the REAL pass rules (5%ers High-Stakes, per challenge_rules.py):
  - Step 1: +8% CLOSED balance on a fresh $100k;  Step 2: +5% on a fresh $100k.
  - Each step also needs >= 3 profitable days (realized day PnL >= 0.5% = $500).
  - Walls: 5% daily / 10% total on EQUITY (engine-enforced) — a breach before
    the step's pass-day fails the whole attempt.
  - Step 2 starts fresh the day AFTER Step 1's pass-day.
  - A step's pass-day = max(day target reached, day of 3rd profitable day).

Train/holdout split (anti-overfit — stages optimize ONLY on TRAIN):
  TRAIN   = 2016, 2018, 2021, 2023  x  Jan/Apr/Jul/Oct   (16 starts, incl toxic)
  HOLDOUT = 2017, 2019, 2022, 2024  x  Jan/Apr/Jul/Oct   (16 starts)

Used by stages C1..C5. Import via importlib like the other stage modules.
"""
import csv as _csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DOE_DIR = HERE.parent / "output" / "doe"

_spec = importlib.util.spec_from_file_location("doe_harness", str(HERE / "doe_harness.py"))
dh = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dh)

ACCOUNT = 100_000
STEP1_TARGET = 0.08 * ACCOUNT          # $8,000 closed
STEP2_TARGET = 0.05 * ACCOUNT          # $5,000 closed
PROFITABLE_DAY_USD = 0.005 * ACCOUNT   # $500 realized/day counts as profitable
MIN_PROFITABLE_DAYS = 3
# User target: ~20 days ideal, up to a MONTH (30 days total) is still a pass.
# Per-step horizon widened to 60 (was 40) so a start that genuinely finishes at
# e.g. day 45-50 total is measured, not truncated into a false "step1 fail" —
# the prior 40-day cutoff was hiding real (if slow) completions.
STEP_HORIZON = 60

# 5%ers "Summer Edition" 100k: daily wall is 3% of EOD equity-or-balance
# (whichever is higher), NOT the classic 5%. Total wall unchanged at 10%.
# Forced into every challenge-scored run so callers can't accidentally score
# against the wrong wall by forgetting the env var.
DAILY_WALL_PCT = "3.0"

TRAIN_STARTS = [f"{y}-{m:02d}-01" for y in (2016, 2018, 2021, 2023) for m in (1, 4, 7, 10)]
HOLDOUT_STARTS = [f"{y}-{m:02d}-01" for y in (2017, 2019, 2022, 2024) for m in (1, 4, 7, 10)]


def _daily_pnl(trades_csv: Path) -> dict:
    """Realized PnL (pnl+swap) per close date."""
    by_day = defaultdict(float)
    if not trades_csv.exists():
        return by_day
    with open(trades_csv, newline="") as f:
        for row in _csv.DictReader(f):
            d = (row.get("close_time") or "")[:10]
            if not d:
                continue
            try:
                by_day[d] += float(row.get("pnl") or 0) + float(row.get("swap") or 0)
            except ValueError:
                pass
    return by_day


def run_step(env_over: dict, tp_over: dict, start: str, target_usd: float,
             horizon: int = STEP_HORIZON) -> dict:
    """One fresh-$100k step. Returns pass_day (calendar days from start) or the
    failure reason. pass_day honors BOTH the closed-balance target and the
    3-profitable-days rule; a breach before pass_day fails the step."""
    s = date.fromisoformat(start)
    end = (s + timedelta(days=horizon)).isoformat()
    env = dict(os.environ); env.update(dh.BASE_ENV); env.update(env_over)
    env["CFG_DAILY_WALL_PCT"] = DAILY_WALL_PCT  # force the 3% Summer Edition wall
    # Use the REAL target broker profile: the default (forexcom_demo) has
    # trade_metals=False, which silently removed XAU/XAG from every prior
    # backtest even though the live 5ers account trades them (D0_D1_FINDINGS.md).
    env.setdefault("BROKER_TYPE", "fiveers_live")
    env["OPT_PARAMS"] = json.dumps({**dh.BASE_TP, **tp_over})
    env["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        cmd = [sys.executable, str(dh.BACKTEST), "--start", start, "--end", end,
               "--balance", str(ACCOUNT), "--output", td, "--quiet"]
        subprocess.run(cmd, env=env, cwd=str(dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=1200)
        rj = Path(td) / "results.json"
        r = json.loads(rj.read_text()) if rj.exists() else {}
        fi = r.get("fail_info") or {}
        breach_day = None
        if r.get("account_failed") and fi.get("time"):
            try:
                breach_day = (date.fromisoformat(str(fi["time"])[:10]) - s).days
            except ValueError:
                pass
        by_day = _daily_pnl(Path(td) / "trades.csv")
        cum = 0.0
        target_day = None
        profit_days = 0
        third_profit_day = None
        for d in sorted(by_day):
            pnl = by_day[d]
            cum += pnl
            elapsed = (date.fromisoformat(d) - s).days
            if pnl >= PROFITABLE_DAY_USD:
                profit_days += 1
                if profit_days == MIN_PROFITABLE_DAYS and third_profit_day is None:
                    third_profit_day = elapsed
            if target_day is None and cum >= target_usd:
                target_day = elapsed
            if target_day is not None and third_profit_day is not None:
                break
        pass_day = None
        if target_day is not None and third_profit_day is not None:
            pass_day = max(target_day, third_profit_day)
        if breach_day is not None and (pass_day is None or breach_day <= pass_day):
            return {"pass_day": None, "breach": True, "breach_day": breach_day,
                    "target_day": target_day, "third_profit_day": third_profit_day,
                    "trades": int(r.get("total_trades") or 0)}
        return {"pass_day": pass_day, "breach": False, "breach_day": None,
                "target_day": target_day, "third_profit_day": third_profit_day,
                "trades": int(r.get("total_trades") or 0)}
    finally:
        shutil.rmtree(td, ignore_errors=True)


def full_two_step(env_over: dict, tp_over: dict, start: str) -> dict:
    """Sequential Step 1 then Step 2. total = d1 + 1 + d2 (calendar days)."""
    s1 = run_step(env_over, tp_over, start, STEP1_TARGET)
    if s1["pass_day"] is None:
        return {"start": start, "total": None, "d1": None, "d2": None,
                "breach": s1["breach"], "why": "step1",
                "detail": {"s1": s1}}
    d1 = s1["pass_day"]
    start2 = (date.fromisoformat(start) + timedelta(days=d1 + 1)).isoformat()
    s2 = run_step(env_over, tp_over, start2, STEP2_TARGET)
    if s2["pass_day"] is None:
        return {"start": start, "total": None, "d1": d1, "d2": None,
                "breach": s2["breach"], "why": "step2",
                "detail": {"s1": s1, "s2": s2}}
    total = d1 + 1 + s2["pass_day"]
    return {"start": start, "total": total, "d1": d1, "d2": s2["pass_day"],
            "breach": False, "why": "", "detail": {"s1": s1, "s2": s2}}


def score_results(rows: list[dict]) -> dict:
    """Roadmap score over a list of full_two_step results.

    User target (2026-07-21): ~20 days ideal, up to a MONTH (30 days total)
    still counts as a real pass. p30 is now the primary speed metric; p20 is
    tracked as the stretch goal, p40/p60 show how far the tail extends.
    """
    n = len(rows)
    if n == 0:
        return {"score": -1e9}
    p20 = sum(1 for r in rows if r["total"] is not None and r["total"] <= 20) / n
    p30 = sum(1 for r in rows if r["total"] is not None and r["total"] <= 30) / n
    p40 = sum(1 for r in rows if r["total"] is not None and r["total"] <= 40) / n
    p60 = sum(1 for r in rows if r["total"] is not None and r["total"] <= 60) / n
    pbr = sum(1 for r in rows if r["breach"]) / n
    totals = sorted(r["total"] for r in rows if r["total"] is not None)
    med = median(totals) if totals else 2 * STEP_HORIZON
    score = 2 * p20 * 100 + 3 * p30 * 100 + 1 * p60 * 100 - 10 * pbr * 100 - med / 100
    return {"score": round(score, 2), "p20": round(p20, 3), "p30": round(p30, 3),
            "p40": round(p40, 3), "p60": round(p60, 3),
            "breach_rate": round(pbr, 3), "median_total": med, "n": n}
