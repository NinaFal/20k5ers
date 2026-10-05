#!/usr/bin/env python3
"""
Why is this round's p30 stuck at 0.08 when STAGEC2_TRIAL4_BACKUP.md records
p40 = 62.5% at the same 5% daily wall?

That config differs from this round's base in two ways that matter, and the
backup file names both: it ran at 3.5% risk per trade (this round: 1.1%) and
with no MAX_TOTAL_POSITIONS cap (this round: 15). It also used a completely
different ladder — bank fast and be flat by 1.35R — where stage 1 converged on
0.65R/1.85R/2.75R with runners.

The backup's numbers came from 16 TRAIN starts, not the 25 canonical ones, so
they are NOT directly comparable to anything in this round. This script puts
both on the same 25 starts so the comparison means something:

  A  backup config, reproduced as published (fast ladder + 3.5% risk, no cap)
  B  this round's incumbent with ONLY risk_per_trade_pct raised to 3.5%

B isolates the risk lever from the ladder. If B alone recovers most of the
gap, stage 6 will find it. If only A does, the ladder and the risk level are
interacting and optimizing them in separate stages cannot find the good basin
— which would be a finding about the method, not just the parameters.

Cached per (config, start) in a tracked json, like every other arm here.
"""
import importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

BEST = json.loads((w5.W5_DIR / "current_best.json").read_text())

# ── A: the backup config, as published (5% wall) ─────────────────────────────
A_ENV = dict(w5.BASE_ENV)
A_ENV.update({
    "CFG_MAX_CUM_RISK": "5.0", "CFG_DAILY_HALT_PCT": "2.25",
    "CFG_TDD_CAUTION_PCT": "3.5", "CFG_RISK_CAUTIOUS": "0.65",
    "CFG_TDD_WARNING_PCT": "4.5", "CFG_RISK_CONSERVATIVE": "0.6",
    "CFG_TDD_EMERGENCY_PCT": "8.0", "CFG_RISK_ULTRASAFE": "0.4",
    "TDD_WALL_SAFETY": "4.0", "CORR_GROUP_CAP": "3",
    "MAX_TOTAL_POSITIONS": "999",      # the backup had no cap at all
})
A_TP = dict(w5.BASE_TP)
A_TP.update({
    "entry_fib_level": 0.65, "entry_fib_level_volatile": 0.65,
    "fib_vol_ratio_threshold": 1.15,
    "tp1_r_multiple": 0.40, "tp1_close_pct": 0.50,
    "tp2_r_multiple": 0.75, "tp2_close_pct": 0.35,
    "tp3_r_multiple": 1.35, "tp3_close_pct": 0.15,
    "tp4_close_pct": 0.0, "tp5_close_pct": 0.0,
    "sl_after_tp1_r": 0.0, "sl_after_tp2_r": 0.25, "sl_after_tp3_r": 0.60,
    "risk_per_trade_pct": 3.5,
})

# ── B: this round's incumbent, risk lever only ───────────────────────────────
B_ENV = dict(w5.BASE_ENV); B_ENV.update(BEST["env"])
B_TP = dict(w5.BASE_TP); B_TP.update(BEST["tp"])
B_TP["risk_per_trade_pct"] = 3.5

# ── C: incumbent untouched, for a same-start baseline ────────────────────────
C_ENV = dict(w5.BASE_ENV); C_ENV.update(BEST["env"])
C_TP = dict(w5.BASE_TP); C_TP.update(BEST["tp"])

ARMS = [("A_backup_3.5pct", A_ENV, A_TP),
        ("B_incumbent_risk3.5", B_ENV, B_TP),
        ("C_incumbent_baseline", C_ENV, C_TP)]

if __name__ == "__main__":
    cache = w5.W5_DIR / "backup_compare_runcache.json"
    out = w5.W5_DIR / "backup_compare.json"
    res = w5.load_json(out)
    starts = w5.CANON[:25]
    print(f"[cmp] 3 arms x {len(starts)} canonical starts, 5% wall, "
          f"target <={w5.TARGET_DAYS}d", flush=True)
    for name, env, tp in ARMS:
        if name in res:
            print(f"[cmp] {name}: cached", flush=True)
            continue
        m = w5.evaluate(env, tp, starts, cache)
        res[name] = m
        w5.atomic_write(out, res)
        print(f"[cmp] {name}: breach={m['breach_rate']} p30={m['p30']} p40={m['p40']} "
              f"p50={m['p50']} median={m['median_days']} fastest={m['fastest']} "
              f"complete={m['complete_rate']} n={m['n']}", flush=True)
    print("\n[cmp] SUMMARY (same 25 starts, 5% wall)", flush=True)
    for name, _, _ in ARMS:
        m = res.get(name, {})
        print(f"  {name:24} breach={m.get('breach_rate')} p30={m.get('p30')} "
              f"p40={m.get('p40')} p50={m.get('p50')} median={m.get('median_days')}", flush=True)
    print("[w5_backup_compare] DONE_MARKER", flush=True)
