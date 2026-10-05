#!/usr/bin/env python3
"""
Export every trade from t47's fastest challenge pass (start 2016-05-31, 9 days)
so the result can be checked against real market data.

Reproduces the two steps exactly as challenge_score.run_step ran them — same
env, same OPT_PARAMS, same fresh $100k, same 75-day horizon — then writes a
workbook with one row per closing leg and one row per position.

Each leg's realized R is computed from the position's own entry and initial
stop (R = |entry - sl|), so a leg that exited at TP1 shows ~+0.65R, TP2 ~+1.85R,
TP3 ~+2.75R and a stopped leg shows ~-1R. That is the number to check against a
chart: it does not depend on trusting the engine's own labels.

Run:  uv run python3 backtest/src/w5_export_t47.py
"""
import csv, importlib.util, json, os, subprocess, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

START = "2016-05-31"
D1 = 5                     # step 1 passed on day 5
OUT = w5.DOE_DIR / "reports"
WORK = w5.DOE_DIR / "tmp" / "t47_export"


def num(x):
    try:
        return float(x if x not in (None, "") else 0)
    except (TypeError, ValueError):
        return 0.0


def run_step(env, tp, start, tag):
    """One fresh-$100k step, exactly as challenge_score.run_step invokes it."""
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV); e.update(w5.BASE_ENV); e.update(env)
    e["CFG_DAILY_WALL_PCT"] = "5.0"
    e.setdefault("BROKER_TYPE", "fiveers_live")
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = WORK / tag; d.mkdir(parents=True, exist_ok=True)
    end = (date.fromisoformat(start) + timedelta(days=w5.HORIZON)).isoformat()
    subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST), "--start", start, "--end", end,
                    "--balance", "100000", "--output", str(d), "--quiet"],
                   env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=7200)
    return d


def legs_of(run_dir, start, pass_day):
    """One dict per closing leg, with realized R measured from entry and stop."""
    f = run_dir / "trades.csv"
    if not f.exists():
        return []
    rows = list(csv.DictReader(open(f)))
    base = lambda r: r["ticket"].split("_partial_")[0]
    # initial stop for a position: the stop recorded on its earliest leg
    first_sl, first_entry, side = {}, {}, {}
    for r in sorted(rows, key=lambda r: r["close_time"]):
        b = base(r)
        first_sl.setdefault(b, num(r.get("sl")))
        first_entry.setdefault(b, num(r.get("open_price")))
        side.setdefault(b, (r.get("type") or "").lower())
    seq = defaultdict(int)
    out = []
    s = date.fromisoformat(start)
    for r in sorted(rows, key=lambda r: (base(r), r["close_time"])):
        b = base(r); seq[b] += 1
        entry, sl = first_entry[b], first_sl[b]
        rr = abs(entry - sl)
        cp = num(r.get("close_price"))
        realized = ((cp - entry) if side[b] == "buy" else (entry - cp)) / rr if rr else None
        cd = (r.get("close_time") or "")[:10]
        day = (date.fromisoformat(cd) - s).days if cd else None
        out.append({
            "position": b, "leg": seq[b], "symbol": r.get("symbol"),
            "side": side[b], "volume": num(r.get("volume")),
            "entry_time": r.get("open_time"), "entry_price": entry,
            "initial_sl": sl, "risk_distance": round(rr, 6) if rr else None,
            "exit_time": r.get("close_time"), "exit_price": cp,
            "realized_R": round(realized, 2) if realized is not None else None,
            "exit_kind": ("PARTIAL/TP" if str(r.get("partial")).strip() == "True"
                          else "FINAL"),
            "pnl": round(num(r.get("pnl")), 2), "swap": round(num(r.get("swap")), 2),
            "day_from_start": day,
            "counted_toward_pass": (day is not None and day <= pass_day),
            "mfe_r": r.get("mfe_r"), "mae_r": r.get("mae_r"),
        })
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((w5.W5_DIR / "t47_config.json").read_text())
    env = dict(cfg["env"]); tp = dict(w5.BASE_TP); tp.update(cfg["tp"])
    start2 = (date.fromisoformat(START) + timedelta(days=D1 + 1)).isoformat()

    print(f"[t47] step 1 from {START} (passed day {D1})", flush=True)
    d1 = run_step(env, tp, START, "step1")
    print(f"[t47] step 2 from {start2}", flush=True)
    d2 = run_step(env, tp, start2, "step2")

    l1 = legs_of(d1, START, D1)
    l2 = legs_of(d2, start2, 3)
    for r in l1: r["step"] = 1
    for r in l2: r["step"] = 2
    allrows = l1 + l2
    csv_path = OUT / "t47_9day_challenge_trades.csv"
    if allrows:
        with open(csv_path, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=["step"] + [k for k in allrows[0] if k != "step"])
            wr.writeheader(); wr.writerows(allrows)
    print(f"[t47] wrote {len(allrows)} legs -> {csv_path}", flush=True)
    for tag, rows, pd_ in (("step1", l1, D1), ("step2", l2, 3)):
        cnt = sum(1 for r in rows if r["counted_toward_pass"])
        pnl = sum(r["pnl"] + r["swap"] for r in rows if r["counted_toward_pass"])
        pos = len({r["position"] for r in rows if r["counted_toward_pass"]})
        print(f"  {tag}: {cnt} legs / {pos} positions closed by day {pd_}, "
              f"realized ${pnl:,.2f}", flush=True)
    print("[w5_export_t47] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
