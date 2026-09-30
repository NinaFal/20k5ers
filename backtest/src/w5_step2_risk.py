#!/usr/bin/env python3
"""
Stap 2 van de challenge met lager risico, op dezelfde 100 startdatums.

In w5_random_study vallen 5 van de 6 breaches in stap 2, terwijl dat doel maar
5% is tegen 8% in stap 1. Deze studie laat stap 1 exact zoals hij was (de
uitkomst en de slaagdag komen uit random_study.json) en draait alleen stap 2
opnieuw met een lager risico per trade. Zo is elk verschil gepaard: dezelfde
startdag, dezelfde stap-1-uitkomst, alleen het risico in stap 2 verschilt.

Live is dit geen codewijziging: je zet risk_per_trade_pct lager zodra stap 1
gehaald is.

Draaien:  uv run python3 backtest/src/w5_step2_risk.py [--risks 1.8,2.2]
"""
import argparse, concurrent.futures, importlib.util, json
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_r = importlib.util.spec_from_file_location("rs", str(HERE / "w5_random_study.py"))
rs = importlib.util.module_from_spec(_r); _r.loader.exec_module(rs)
w5 = rs.w5
OUT = w5.W5_DIR / "step2_risk.json"


def step2(risk, start, d1):
    env, tp = rs.live_config()
    tp = dict(tp); tp["risk_per_trade_pct"] = risk
    s2start = (date.fromisoformat(start) + timedelta(days=d1 + 1)).isoformat()
    r = w5.cs.run_step(env, tp, s2start, w5.cs.STEP2_TARGET, w5.HORIZON)
    r.pop("detail", None)
    return {"pass_day": r.get("pass_day"), "breach": bool(r.get("breach")),
            "total": (d1 + 1 + r["pass_day"]) if r.get("pass_day") is not None else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--risks", default="1.8,2.2")
    a = ap.parse_args()
    base = w5.load_json(rs.OUT)["challenges"]
    s1ok = {s: r["d1"] for s, r in base.items() if r.get("d1") is not None}
    for risk in [float(x) for x in a.risks.split(",")]:
        key = f"{risk:.2f}"
        store = w5.load_json(OUT)
        todo = [s for s in s1ok if s not in store.get(key, {})]
        print(f"[s2] risico {key}: {len(todo)} van {len(s1ok)} te gaan", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=rs.WORKERS) as ex:
            futs = {ex.submit(step2, risk, s, s1ok[s]): s for s in todo}
            for f in concurrent.futures.as_completed(futs):
                store = w5.load_json(OUT)
                store.setdefault(key, {})[futs[f]] = f.result()
                w5.atomic_write(OUT, store)
    report(base)


def report(base=None):
    base = base or w5.load_json(rs.OUT)["challenges"]
    store = w5.load_json(OUT)
    n = len(base)

    def stats(rows):
        tot = sorted(r["total"] for r in rows.values() if r.get("total"))
        br = sum(1 for r in rows.values() if r.get("breach"))
        return len(tot), br, n - len(tot) - br, (tot[len(tot) // 2] if tot else None), sum(1 for t in tot if t <= 30)

    print(f"\n{'stap-2 risico':>14} {'geslaagd':>9} {'breach':>7} {'traag':>6} {'mediaan':>8} {'<=30d':>6}")
    print(f"{'2.70 (nu)':>14} {stats(base)[0]:>9} {stats(base)[1]:>7} {stats(base)[2]:>6} {stats(base)[3]:>8} {stats(base)[4]:>6}")
    for key in sorted(store):
        merged = {s: (store[key][s] if s in store[key] else base[s]) for s in base}
        p, b, st, med, le30 = stats(merged)
        print(f"{key:>14} {p:>9} {b:>7} {st:>6} {med:>8} {le30:>6}")
    print("\n[w5_step2_risk] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
