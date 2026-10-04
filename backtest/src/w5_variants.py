#!/usr/bin/env python3
"""
Varianten op dezelfde startdatums als w5_random_study (gepaard vergelijkbaar).

  challenges   100 willekeurige 2-staps challenges; stap 2 altijd op 1,8%
               (zoals live nu). Varianten verschillen in stap 1 of nieuws.
  funded       20 gefunde accounts, 3 jaar aan een stuk.

Varianten:
  s1_22      stap 1 op 2,2%
  s1_18      stap 1 op 1,8%
  news_half  nieuws op New Yorkse tijd + halve posities sluiten 15 min vooraf
  news_all   idem, maar alles in die munt sluiten
  climb18    gefund: maximaal 1,8% zolang het niveau onder $300.000 ligt

Referentie: challenges = random_study 'challenges' met stap 2 uit
step2_risk.json (1,80); funded = random_study 'funded_3y'.

Draaien:  uv run python3 backtest/src/w5_variants.py challenges s1_22
          uv run python3 backtest/src/w5_variants.py funded climb18
          uv run python3 backtest/src/w5_variants.py report
"""
import concurrent.futures, importlib.util, json, sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
_r = importlib.util.spec_from_file_location("rs", str(HERE / "w5_random_study.py"))
rs = importlib.util.module_from_spec(_r); _r.loader.exec_module(rs)
w5 = rs.w5
OUT = w5.W5_DIR / "variants.json"
STEP2_RISK = 1.8

VARIANTS = {
    "s1_22": ({}, 2.2),
    "s1_18": ({}, 1.8),
    "news_half": ({"NEWS_NY": "1", "NEWS_FLAT": "half"}, None),
    "news_all": ({"NEWS_NY": "1", "NEWS_FLAT": "all"}, None),
    "climb18": ({"FUNDED_CLIMB_RISK_PCT": "1.8"}, None),
}


def challenge_one(var, start):
    env_x, r1 = VARIANTS[var]
    env, tp = rs.live_config(); env.update(env_x)
    tp1 = dict(tp)
    if r1 is not None:
        tp1["risk_per_trade_pct"] = r1
    s1 = w5.cs.run_step(env, tp1, start, w5.cs.STEP1_TARGET, w5.HORIZON)
    if s1.get("pass_day") is None:
        return {"total": None, "d1": None, "breach": bool(s1.get("breach")), "why": "step1"}
    d1 = s1["pass_day"]
    tp2 = dict(tp); tp2["risk_per_trade_pct"] = STEP2_RISK
    s2start = (date.fromisoformat(start) + timedelta(days=d1 + 1)).isoformat()
    s2 = w5.cs.run_step(env, tp2, s2start, w5.cs.STEP2_TARGET, w5.HORIZON)
    if s2.get("pass_day") is None:
        return {"total": None, "d1": d1, "breach": bool(s2.get("breach")), "why": "step2"}
    return {"total": d1 + 1 + s2["pass_day"], "d1": d1, "breach": False, "why": ""}


def funded_one(var, start):
    env_x, _ = VARIANTS[var]
    orig = rs.live_config

    def patched():
        env, tp = orig(); env.update(env_x); return env, tp
    rs.live_config = patched
    try:
        return rs.run_funded_one(3, start)
    finally:
        rs.live_config = orig


def run(kind, var):
    starts = rs.challenge_starts(100) if kind == "challenges" else rs.funded_starts(3, 20)
    key = f"{kind}:{var}"
    store = w5.load_json(OUT)
    todo = [s for s in starts if s not in store.get(key, {}) or store[key][s].get("error")]
    print(f"[var] {key}: {len(todo)} van {len(starts)} te gaan", flush=True)
    fn = challenge_one if kind == "challenges" else funded_one
    with concurrent.futures.ThreadPoolExecutor(max_workers=rs.WORKERS) as ex:
        futs = {ex.submit(fn, var, s): s for s in todo}
        for f in concurrent.futures.as_completed(futs):
            try:
                r = f.result()
            except Exception as e:
                r = {"error": repr(e)}
            store = w5.load_json(OUT)
            store.setdefault(key, {})[futs[f]] = r
            w5.atomic_write(OUT, store)


def _ref_challenges():
    base = w5.load_json(rs.OUT)["challenges"]
    s2 = w5.load_json(w5.W5_DIR / "step2_risk.json").get("1.80", {})
    return {s: (s2[s] if s in s2 else base[s]) for s in base}


def report():
    store = w5.load_json(OUT)
    print(f"\nCHALLENGES (100, stap 2 op {STEP2_RISK}%)")
    print(f"  {'variant':12} {'geslaagd':>9} {'breach':>7} {'traag':>6} {'mediaan':>8} {'<=30d':>6}")
    rows = {"referentie": _ref_challenges()}
    rows.update({k.split(":")[1]: v for k, v in store.items() if k.startswith("challenges:")})
    for name, d in rows.items():
        v = [r for r in d.values() if not r.get("error")]
        tot = sorted(r["total"] for r in v if r.get("total"))
        br = sum(1 for r in v if r.get("breach"))
        print(f"  {name:12} {len(tot):>6}/{len(v):<3} {br:>6} {len(v)-len(tot)-br:>6} "
              f"{(tot[len(tot)//2] if tot else '-'):>8} {sum(1 for t in tot if t <= 30):>6}")
    print("\nGEFUND 3 JAAR (20 accounts)")
    print(f"  {'variant':12} {'overleeft':>10} {'opgenomen gem/mnd':>18} {'mediaan totaal':>15} {'ergste dag':>11}")
    frows = {"referentie": w5.load_json(rs.OUT).get("funded_3y", {})}
    frows.update({k.split(":")[1]: v for k, v in store.items() if k.startswith("funded:")})
    for name, d in frows.items():
        v = [r for r in d.values() if not r.get("error")]
        if not v:
            continue
        w = sorted(r["withdrawn"] for r in v)
        alive = sum(1 for r in v if not r["died"])
        print(f"  {name:12} {alive:>7}/{len(v):<3} ${sum(w)/len(w)/36:>16,.0f} ${w[len(w)//2]:>14,.0f} "
              f"{max(r['max_ddd_pct'] or 0 for r in v):>10.2f}%")
    print("\n[w5_variants] DONE_MARKER", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "report":
        report()
    else:
        run(sys.argv[1], sys.argv[2])
        report()
