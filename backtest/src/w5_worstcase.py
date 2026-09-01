#!/usr/bin/env python3
"""
Re-screen the risk stage's top configs with INTRABAR worst-case marking.

Every result in this round so far was measured on bar-CLOSE equity. That can
miss a wick that pierces the 5% daily wall inside an M15 bar and recovers
before the close — a false negative that would be a dead account live.

The engine already implements the strict version (TDD_WORST_CASE=1): every
open position is marked to its bar's adverse extreme (low for longs, high for
shorts, capped at its stop, since the stop would fill first) and that
worst-case equity is what the daily and total walls are checked against. It is
an UPPER bound — it assumes every position hits its worst tick simultaneously
— so surviving it means the config is robust regardless of bar resolution.

A config that is clean on close-mark and breaches here must not reach the
decade gauntlet, because the gauntlet would then rank it on a number that
overstates its safety.

Cache is separate from the close-mark runs: TDD_WORST_CASE is part of the env
diff, so config_key already separates them, but a distinct file keeps the two
regimes obviously apart.

Run:  uv run python3 backtest/src/w5_worstcase.py
"""
import importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

TOP_N = 10          # the leaders; the gauntlet only needs a handful of survivors


def main():
    cands = json.loads((w5.W5_DIR / "risk_top20.json").read_text())[:TOP_N]
    cache = w5.W5_DIR / "worstcase_runcache.json"
    out = w5.W5_DIR / "worstcase_screen.json"
    res = w5.load_json(out)
    starts = w5.CANON[:25]

    print(f"[wc] {len(cands)} configs x {len(starts)} starts, 5% wall, "
          f"INTRABAR worst-case marking", flush=True)
    for c in cands:
        key = str(c["trial"])
        if key in res:
            print(f"[wc] t{key}: cached", flush=True); continue
        env = dict(w5.BASE_ENV); env.update(c["env"])
        env["TDD_WORST_CASE"] = "1"
        tp = dict(w5.BASE_TP); tp.update(c["tp"])
        m = w5.evaluate(env, tp, starts, cache)
        m["close_mark_p30"] = c.get("p30")
        m["close_mark_median"] = c.get("median_days")
        res[key] = m
        w5.atomic_write(out, res)
        verdict = "SURVIVES" if m["breach_rate"] == 0.0 else "BREACHES"
        print(f"[wc] t{key:>4} {verdict}  breach={m['breach_rate']} "
              f"p30={m['p30']} (close-mark {m['close_mark_p30']}) "
              f"median={m['median_days']} (close-mark {m['close_mark_median']})", flush=True)

    clean = [k for k, v in res.items() if v["breach_rate"] == 0.0]
    print(f"\n[wc] {len(clean)} of {len(res)} survive intrabar worst-case: "
          f"{sorted(clean, key=lambda k: -(res[k]['p30'] or 0))}", flush=True)
    for k in sorted(clean, key=lambda k: -(res[k]["p30"] or 0)):
        v = res[k]
        print(f"   t{k:>4} p30={v['p30']} p40={v['p40']} p50={v['p50']} "
              f"median={v['median_days']} fastest={v['fastest']}", flush=True)
    w5.atomic_write(w5.W5_DIR / "worstcase_survivors.json", clean)
    print("[w5_worstcase] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
