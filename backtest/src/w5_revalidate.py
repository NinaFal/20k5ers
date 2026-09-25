#!/usr/bin/env python3
"""
Draait de holdout van 100 starts opnieuw op de NIEUWE cryptodata.

Waarom dit moet. De cijfers die dit project draagt — 86 geslaagd, 7 breaches, 7
vastgelopen, mediaan 16 dagen — zijn gemeten toen crypto in de hele backtest 24
trades deed, allemaal in 2023 of later, op uurbars vermomd als M15. Nu handelen
vier cryptosymbolen vanaf 2017-2018 in elk jaar. Een rooktest op 2021 gaf 81
cryptotrades waar er eerst nul waren, en een slechtste dag van 4,92% tegen een
muur van 5,0%. Dat is te dicht bij de rand om op het oude getal te blijven
leunen.

Zelfde 100 starts, zelfde bevroren configuratie, alleen andere data. Het
resultaat wordt naast de opgeslagen versie gelegd zodat het verschil per start
te zien is en niet alleen in het totaal — twee samenvattingen die toevallig
gelijk uitkomen kunnen onderliggend flink verschoven zijn.

Geen vroegtijdige afbreking: elke start loopt af, zodat het aantal breaches het
echte aantal is en niet afgekapt bij de eerste.

Draaien:  uv run python3 backtest/src/w5_revalidate.py
"""
import concurrent.futures, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

OLD = w5.W5_DIR / "_pre_crypto" / "holdout100.json"
OUT = w5.W5_DIR / "holdout100_crypto.json"


def summarise(d, starts):
    rows = [d[s] for s in starts if s in d]
    br = [s for s in starts if d.get(s, {}).get("breach")]
    tot = sorted(v["total"] for v in rows if v.get("total") is not None)
    return {"n": len(rows), "pass": len(tot), "breach": len(br),
            "stall": len(rows) - len(br) - len(tot),
            "median": tot[len(tot) // 2] if tot else None,
            "le30": sum(1 for t in tot if t <= 30),
            "breaches": br}


def main():
    old = json.loads(OLD.read_text())
    starts = sorted(old.keys())
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])

    res = w5.load_json(OUT)
    todo = [s for s in starts if s not in res]
    print(f"[reval] {len(starts)} starts | {len(res)} klaar, {len(todo)} te gaan "
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
            n = len(res)
            br = sum(1 for v in res.values() if v.get("breach"))
            print(f"[reval] {n}/{len(starts)}  breaches {br}", flush=True)

    a, c = summarise(old, starts), summarise(res, starts)
    print("\n" + "=" * 74, flush=True)
    print("[reval] ZELFDE 100 STARTS, ANDERE DATA", flush=True)
    print("=" * 74, flush=True)
    print(f"\n  {'':<12}{'oud (geen crypto)':>20}{'nieuw (met crypto)':>21}{'verschil':>12}", flush=True)
    for k, lbl in (("pass", "geslaagd"), ("breach", "breach"), ("stall", "vastgelopen"),
                   ("median", "mediaan d"), ("le30", "<=30 dagen")):
        av, cv = a[k], c[k]
        if av is None or cv is None:
            print(f"  {lbl:<12}{str(av):>20}{str(cv):>21}{'':>12}", flush=True); continue
        print(f"  {lbl:<12}{av:>20}{cv:>21}{cv - av:>+12}", flush=True)

    ob, nb = set(a["breaches"]), set(c["breaches"])
    print(f"\n  breaches die bleven   {len(ob & nb):>3}  {sorted(ob & nb)}", flush=True)
    print(f"  breaches die weg zijn {len(ob - nb):>3}  {sorted(ob - nb)}", flush=True)
    print(f"  NIEUWE breaches       {len(nb - ob):>3}  {sorted(nb - ob)}", flush=True)

    flips = [s for s in starts
             if (old.get(s, {}).get("breach") or False) != (res.get(s, {}).get("breach") or False)
             or (old.get(s, {}).get("total") is None) != (res.get(s, {}).get("total") is None)]
    print(f"\n  starts met een andere UITKOMST: {len(flips)} van {len(starts)}", flush=True)
    same = sum(1 for s in starts
               if old.get(s, {}).get("total") is not None
               and old.get(s, {}).get("total") == res.get(s, {}).get("total"))
    print(f"  starts met exact dezelfde doorlooptijd: {same}", flush=True)
    print("\n[w5_revalidate] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
