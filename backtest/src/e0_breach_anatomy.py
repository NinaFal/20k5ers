#!/usr/bin/env python3
"""
E0 — breach anatomy. What ACTUALLY blows the 3% wall?

Every 3%-wall search so far has treated a breach as a scalar (breach_rate) and
tuned parameters against it. That mapped a frontier but never asked *what the
losing day looked like*. Whether a structural fix exists depends entirely on
that anatomy:

  * If breach days are dominated by positions carried OVERNIGHT, an EOD
    de-risking rule attacks the cause directly and is not a frontier move —
    it removes a risk the strategy is not being paid for.
  * If breach days are dominated by MANY SMALL correlated losses, the fix is
    exposure-aware sizing (a portfolio risk cap), not a position count cap:
    count caps treat 3 correlated pairs the same as 3 unrelated ones.
  * If breach days are dominated by ONE position, it is a stop-placement /
    single-trade sizing problem and neither of the above helps.

These three imply different mechanisms, so measuring first is worth more than
another parameter search. Keeps trades.csv (challenge_score deletes its temp
dir) and reports the split.

Run:  uv run python3 backtest/src/e0_breach_anatomy.py [--starts N] [--risk R]
"""
import argparse, csv, importlib.util, json, os, shutil, subprocess, sys, tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOE_DIR = HERE.parent / "output" / "doe"
OUT_DIR = DOE_DIR / "e0_anatomy"
_s = importlib.util.spec_from_file_location("cs", str(HERE / "challenge_score.py"))
cs = importlib.util.module_from_spec(_s); _s.loader.exec_module(cs)
_p = importlib.util.spec_from_file_location("scr5c", str(HERE / "stage5c_oos_screen.py"))
scr = importlib.util.module_from_spec(_p); _p.loader.exec_module(scr)
sys.path.insert(0, str(REPO))
from weekend_gap_manager import get_correlation_group  # noqa: E402

os.environ.setdefault("RUN_TIMEOUT_S", "999999")

# The C1-wall3 skeleton, at a risk level that DOES breach — we need breach days
# to dissect, so this deliberately runs hot rather than at the safe D2 t117.
BASE_ENV = {"RISK_REGIME_ENABLE": "1", "VOL_SIZE_ENABLE": "0", "VOL_REGIME_DD_MULT": "1.0",
            "FIVEERS_MAX_SCALE": "4000000", "RISK_CALM_MULT": "1.45", "RISK_VOLATILE_MULT": "0.64",
            "VOL_REGIME_DD_OFF": "5.0", "CFG_DAILY_HALT_PCT": "2.0",
            "CFG_TDD_CAUTION_PCT": "2.0", "CFG_RISK_CAUTIOUS": "0.5", "CFG_TDD_WARNING_PCT": "3.0",
            "CFG_RISK_CONSERVATIVE": "0.3", "CFG_TDD_EMERGENCY_PCT": "5.5", "CFG_RISK_ULTRASAFE": "0.15",
            "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3", "MAX_TOTAL_POSITIONS": "15",
            "EXCLUDE_SYMBOLS": "AUD_NZD,EUR_NZD,AUD_JPY",
            "BROKER_TYPE": "fiveers_live", "CFG_DAILY_WALL_PCT": "3.0"}
TP = dict(scr.PINNED_ENTRY)
TP.update({"entry_fib_level": 0.45, "entry_fib_level_volatile": 0.80,
           "fib_vol_ratio_threshold": 1.05,
           "tp1_r_multiple": 0.5, "tp2_r_multiple": 1.0, "tp3_r_multiple": 1.5,
           "tp4_r_multiple": 2.5, "tp5_r_multiple": 3.5,
           "tp1_close_pct": 0.45, "tp2_close_pct": 0.35, "tp3_close_pct": 0.20,
           "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
           "sl_after_tp2_r": 0.5, "sl_after_tp3_r": 1.2, "sl_after_tp4_r": 1.8})


def run_keep(env_over, tp_over, start, horizon, keep_dir):
    """challenge_score.run_step, but keeps trades.csv/results.json."""
    s = date.fromisoformat(start)
    end = (s + timedelta(days=horizon)).isoformat()
    env = dict(os.environ); env.update(cs.dh.BASE_ENV); env.update(env_over)
    env["OPT_PARAMS"] = json.dumps({**cs.dh.BASE_TP, **tp_over})
    env["PYTHONUTF8"] = "1"
    td = tempfile.mkdtemp(dir=str(DOE_DIR / "tmp"))
    try:
        subprocess.run([sys.executable, str(cs.dh.BACKTEST), "--start", start,
                        "--end", end, "--balance", str(cs.ACCOUNT),
                        "--output", td, "--quiet"],
                       env=env, cwd=str(cs.dh.REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=1800)
        keep_dir.mkdir(parents=True, exist_ok=True)
        for name in ("trades.csv", "results.json"):
            src = Path(td) / name
            if src.exists():
                shutil.copy(src, keep_dir / name)
        rj = keep_dir / "results.json"
        return json.loads(rj.read_text()) if rj.exists() else {}
    finally:
        shutil.rmtree(td, ignore_errors=True)


def anatomy(keep_dir, breach_day_str):
    """Dissect the trades that realized on the breach day."""
    tf = keep_dir / "trades.csv"
    if not tf.exists():
        return None
    rows = list(csv.DictReader(open(tf, newline="")))
    day = [r for r in rows if (r.get("close_time") or "")[:10] == breach_day_str]
    if not day:
        return None

    def fl(r, k):
        try:
            return float(r.get(k) or 0)
        except ValueError:
            return 0.0

    losers = [r for r in day if fl(r, "pnl") + fl(r, "swap") < 0]
    total_loss = sum(fl(r, "pnl") + fl(r, "swap") for r in losers)
    if not losers or total_loss == 0:
        return None

    # overnight = opened on an earlier calendar day than it closed
    overnight = [r for r in losers
                 if (r.get("open_time") or "")[:10] != (r.get("close_time") or "")[:10]]
    on_loss = sum(fl(r, "pnl") + fl(r, "swap") for r in overnight)

    worst = min(losers, key=lambda r: fl(r, "pnl") + fl(r, "swap"))
    worst_loss = fl(worst, "pnl") + fl(worst, "swap")

    by_group = defaultdict(float)
    for r in losers:
        by_group[get_correlation_group(r["symbol"])] += fl(r, "pnl") + fl(r, "swap")
    top_group, top_group_loss = min(by_group.items(), key=lambda kv: kv[1])

    by_dir = defaultdict(float)
    for r in losers:
        by_dir[r.get("type", "?")] += fl(r, "pnl") + fl(r, "swap")

    return {
        "breach_day": breach_day_str,
        "n_losers": len(losers),
        "total_loss": round(total_loss, 2),
        "overnight_share": round(on_loss / total_loss, 3),
        "n_overnight": len(overnight),
        "worst_single_share": round(worst_loss / total_loss, 3),
        "worst_symbol": worst["symbol"],
        "top_group": top_group,
        "top_group_share": round(top_group_loss / total_loss, 3),
        "n_groups": len(by_group),
        "dir_split": {k: round(v / total_loss, 3) for k, v in by_dir.items()},
        "symbols": sorted({r["symbol"] for r in losers}),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--starts", type=int, default=16)
    ap.add_argument("--risk", type=float, default=1.6,
                    help="base risk %% — run hot so breaches actually occur")
    ap.add_argument("--horizon", type=int, default=60)
    args = ap.parse_args()
    (DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    env = dict(BASE_ENV)
    tp = dict(TP); tp["risk_per_trade_pct"] = args.risk
    out_path = DOE_DIR / "e0_anatomy.json"
    found = json.loads(out_path.read_text()) if out_path.exists() else {}

    print(f"[E0] breach anatomy @ risk {args.risk}%, {args.starts} starts", flush=True)
    for start in cs.TRAIN_STARTS[:args.starts]:
        if start in found:
            continue
        kd = OUT_DIR / start
        r = run_keep(env, tp, start, args.horizon, kd)
        fi = r.get("fail_info") or {}
        if not (r.get("account_failed") and fi.get("time")):
            found[start] = {"breach": False}
            print(f"  {start}: no breach", flush=True)
        else:
            bd = str(fi["time"])[:10]
            a = anatomy(kd, bd) or {"breach_day": bd, "note": "no realized losses that day"}
            a["breach"] = True
            found[start] = a
            if "n_losers" in a:
                print(f"  {start}: BREACH {bd}  loss=${a['total_loss']:,.0f} "
                      f"across {a['n_losers']} trades | overnight {a['overnight_share']*100:.0f}% "
                      f"| worst-single {a['worst_single_share']*100:.0f}% "
                      f"| top-group {a['top_group']} {a['top_group_share']*100:.0f}%", flush=True)
            else:
                print(f"  {start}: BREACH {bd} (no realized losses — floating/equity breach)", flush=True)
        out_path.write_text(json.dumps(found, indent=2))

    b = [v for v in found.values() if v.get("breach") and "n_losers" in v]
    print(f"\n[E0] {len(b)} dissectable breaches of {len(found)} starts", flush=True)
    if b:
        n = len(b)
        print(f"  mean overnight share of loss : {sum(x['overnight_share'] for x in b)/n*100:5.1f}%")
        print(f"  mean worst-single share      : {sum(x['worst_single_share'] for x in b)/n*100:5.1f}%")
        print(f"  mean top-corr-group share    : {sum(x['top_group_share'] for x in b)/n*100:5.1f}%")
        print(f"  mean losing trades per breach: {sum(x['n_losers'] for x in b)/n:5.1f}")
        print(f"  mean distinct groups         : {sum(x['n_groups'] for x in b)/n:5.1f}")
    print("[e0_breach_anatomy] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
