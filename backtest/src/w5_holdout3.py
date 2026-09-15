#!/usr/bin/env python3
"""
DERDE holdout: 100 verse challenge-starts op de definitieve configuratie.

Wat er sinds de vorige twee holdouts veranderd is en waarom die cijfers dus niet
meer gelden:

  * Cryptodata vervangen. Wat 'M15 vanaf 2020' heette waren uurbars vanaf 2023
    met 47% dekking. Nu echte M15 vanaf augustus 2017 — maar crypto staat
    inmiddels uit, zie hieronder.
  * XRP en ADA eruit: 5ers biedt ze niet aan.
  * BTC en ETH eruit: over elf jaar leverden ze -0,93% op en 0,32 punt meer
    dagelijkse drawdown, tegen een hefboom van 1:2.
  * Het 50-lots plafond werkt nu ook in de backtest (commit 4e71041). Dat alleen
    al verschoof een jaar met $1.013 zonder dat er een trade veranderde.

Die laatste is de belangrijkste reden om niet op de oude 7-van-100 te blijven
leunen: de vorige holdouts draaiden op een engine die posities tot 100 lots
toestond waar 5ers er 50 toestaat.

Verse vensters, disjunct van beide vorige sets, vastgelegd voordat er gemeten
werd. Geen vroegtijdige afbreking: elke start loopt af, zodat het aantal
breaches het echte aantal is en niet afgekapt bij de eerste.

Draaien:  uv run python3 backtest/src/w5_holdout3.py
"""
import concurrent.futures, importlib.util, json, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

STARTS_FILE = w5.DOE_DIR / "THIRD_100_STARTS.json"
OUT = w5.W5_DIR / "holdout3.json"


def main():
    starts = json.loads(STARTS_FILE.read_text())["starts"]
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])

    res = w5.load_json(OUT)
    todo = [s for s in starts if s not in res]
    print(f"[h3] {len(starts)} verse starts {starts[0]}..{starts[-1]}", flush=True)
    print(f"[h3] uitgesloten: {env.get('EXCLUDE_SYMBOLS')}", flush=True)
    print(f"[h3] {len(res)} gecached, {len(todo)} te gaan | {w5.WORKERS} workers "
          f"| geen vroegtijdige afbreking", flush=True)

    chunk = max(2, w5.WORKERS)
    with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
        for i in range(0, len(todo), chunk):
            futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                    for s in todo[i:i + chunk]}
            for f in concurrent.futures.as_completed(futs):
                r = f.result(); r.pop("detail", None)
                res[futs[f]] = r
            w5.atomic_write(OUT, res)
            br = sum(1 for v in res.values() if v.get("breach"))
            tot = sorted(v["total"] for v in res.values() if v.get("total") is not None)
            print(f"[h3] {len(res)}/{len(starts)}  breaches {br}  "
                  f"mediaan {tot[len(tot)//2] if tot else '-'}", flush=True)

    rows = [res[s] for s in starts if s in res]
    br = [s for s in starts if res.get(s, {}).get("breach")]
    tot = sorted(v["total"] for v in rows if v.get("total") is not None)
    stalls = len(rows) - len(br) - len(tot)
    print("\n" + "=" * 70, flush=True)
    print("[h3] DERDE HOLDOUT — definitieve configuratie, 100 verse vensters", flush=True)
    print("=" * 70, flush=True)
    print(f"  geslaagd      {len(tot):>3}/100      (holdout 1: 86, holdout 2: 88/96)", flush=True)
    print(f"  breach        {len(br):>3}/100      (holdout 1:  7, holdout 2:  2/96)", flush=True)
    print(f"  vastgelopen   {stalls:>3}/100      (holdout 1:  7)", flush=True)
    if tot:
        print(f"  mediaan       {tot[len(tot)//2]:>3}d       (holdout 1: 16d, holdout 2: 21d)", flush=True)
        print(f"  <=30 dagen    {sum(1 for t in tot if t <= 30):>3}/100      (holdout 1: 69)", flush=True)
        print(f"  snelste {tot[0]}d  traagste {tot[-1]}d", flush=True)
    if br:
        y = {}
        for s in br:
            y[s[:4]] = y.get(s[:4], 0) + 1
        print(f"  breachende starts: {br}", flush=True)
        print(f"  per jaar: {dict(sorted(y.items()))}", flush=True)
    print("\n[w5_holdout3] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
