#!/usr/bin/env python3
"""
ONE continuous 2016-2025 account, scaling carried across years.

Why this exists: w5_gauntlet restarts every January at a fresh $100k. That
makes years comparable and lets the run survive a container restart, but it
means no year ever begins above $100k — so the decade numbers never show the
account operating at $350k or $500k, which is where a real 5ers account that
keeps scaling would spend most of its life. It also resets the TOTAL-drawdown
baseline every January, hiding any slow multi-year bleed.

This arm answers the other question: what does ONE account actually do over ten
years if the funded level is never reset?

Trade-offs, stated plainly:
  * It is a single long subprocess. Nothing is cached on the way, so a kill
    loses the whole run — the supervisor simply retries from the start.
  * A breach ENDS the account. The run stops there, which is the honest model
    of a real funded account and is exactly what the per-year arm cannot show.
  * Results are not comparable year-to-year (each year inherits the last), so
    read this for capacity and survival, not for ranking configs.

Run:  uv run python3 backtest/src/w5_continuous.py
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

START, END = "2016-01-01", "2025-12-31"


def load_cfg(name):
    """Return (env, tp) for a named config."""
    if name == "t61_incumbent":
        b = json.loads((w5.W5_DIR / "current_best.json").read_text())
        return b["env"], b["tp"]
    if name == "t4_risk2.9":
        c = json.loads((w5.W5_DIR / "riskt4_top20.json").read_text())[0]
        return c["env"], c["tp"]
    raise SystemExit(f"unknown config {name}")


def run_continuous(env_over, tp_over, tag):
    env = dict(os.environ); env.update(w5.cs.dh.BASE_ENV)
    env.update(w5.BASE_ENV); env.update(env_over)
    tp = dict(w5.BASE_TP); tp.update(tp_over)
    env["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    env["PYTHONUTF8"] = "1"
    out = w5.DOE_DIR / "tmp" / f"cont_{tag}"
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST), "--start", START, "--end", END,
                    "--balance", "100000", "--output", str(out), "--quiet"],
                   env=env, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                   encoding="utf-8", errors="replace", timeout=28800)
    rj = out / "results.json"
    if not rj.exists():
        return {"error": "no results.json"}
    r = json.loads(rj.read_text())
    log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
    return {
        "withdrawn": r.get("fiveers_total_withdrawn"),
        "final_balance": r.get("final_balance"),
        "funded_level_end": (log[-1]["new_level"] if log else 100000),
        "scale_ups": len(log),
        "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
        "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
        "account_failed": r.get("account_failed"),
        "fail_reason": (r.get("fail_info") or {}).get("reason"),
        "fail_time": str((r.get("fail_info") or {}).get("time") or "") or None,
        "scaling_log": [{"time": str(s.get("time"))[:10], "to": s.get("new_level"),
                         "payout": round(s.get("trader_payout") or 0, 2)} for s in log],
    }


if __name__ == "__main__":
    out_path = w5.W5_DIR / "continuous_decade.json"
    res = w5.load_json(out_path)
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    for name in ("t61_incumbent", "t4_risk2.9"):
        if name in res:
            print(f"[cont] {name}: cached", flush=True); continue
        print(f"[cont] {name}: running {START}..{END} as ONE account", flush=True)
        env, tp = load_cfg(name)
        res[name] = run_continuous(env, tp, name)
        w5.atomic_write(out_path, res)
        r = res[name]
        print(f"[cont] {name}: failed={r.get('account_failed')} "
              f"withdrawn=${(r.get('withdrawn') or 0):,.0f} "
              f"level_end=${(r.get('funded_level_end') or 0):,.0f} "
              f"scale_ups={r.get('scale_ups')} maxDDD={r.get('max_ddd_pct')}% "
              f"maxTDD={r.get('max_tdd_pct')}%"
              + (f"  <-- {r.get('fail_reason')} @ {r.get('fail_time')}"
                 if r.get('account_failed') else ""), flush=True)
    print("[w5_continuous] DONE_MARKER", flush=True)
