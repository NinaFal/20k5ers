#!/usr/bin/env python3
"""
Kostengevoeligheid: hoeveel van de edge overleeft realistische handelskosten?

Elk resultaat in deze ronde draaide met een VLAKKE spread van 1,0 pip op elk
instrument — inclusief XAU, XAG, NAS100 en crypto, waar de echte spread een
veelvoud daarvan is — en met SLIPPAGE_PIPS ongezet, dus nul slippage. Over
12.054 trades in elf jaar is dat een structurele onderschatting van de kosten
met een onbekende omvang.

De simulator heeft al een SLIPPAGE_PIPS-knop: adverse pips op elke entry-fill en
elke SL-exit. Die wordt hier gebruikt om de gevoeligheid te meten zonder de
engine te wijzigen.

Wat dit WEL is: een gevoeligheidscurve. Hoeveel verslechtert slaagkans en
breach-rate per extra pip kosten?
Wat dit NIET is: een per-instrument kostenmodel. 1 pip extra op EUR/USD en 1 pip
extra op XAU zijn heel verschillende dingen in geld; dit behandelt ze gelijk.
De curve zegt "de strategie overleeft X pip" — niet welke X realistisch is per
symbool.

Als de resultaten al bij 0,5-1,0 pip instorten is het edge te dun om live te
handelen zonder eerst echte spreads te modelleren. Blijven ze staan tot 2 pip,
dan is de marge comfortabel.

Draaien:  uv run python3 backtest/src/w5_costs.py
"""
import concurrent.futures, importlib.util, json, os, random
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

SEED = 20260815
N = 60
LEVELS = ("0", "0.5", "1.0", "2.0")     # extra adverse pips per fill
OUT = w5.W5_DIR / "cost_sensitivity.json"


def starts():
    """60 starts, gestratificeerd over voor/na 2019 zodat beide regimes meetellen."""
    allst = json.loads((w5.DOE_DIR / "HOLDOUT_100_STARTS_2015.json").read_text())["starts"]
    pre = [s for s in allst if s[:4] < "2019"]
    post = [s for s in allst if s[:4] >= "2019"]
    rng = random.Random(SEED)
    return sorted(rng.sample(pre, min(24, len(pre))) + rng.sample(post, min(36, len(post))))


def main():
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env0 = dict(w5.BASE_ENV); env0.update(b["env"])
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    ss = starts()
    res = w5.load_json(OUT)
    print(f"[cost] {len(ss)} starts x {len(LEVELS)} kostenniveaus", flush=True)

    for lv in LEVELS:
        slot = res.setdefault(lv, {})
        todo = [s for s in ss if s not in slot]
        if todo:
            env = dict(env0); env["SLIPPAGE_PIPS"] = lv
            chunk = max(2, w5.WORKERS)
            with concurrent.futures.ThreadPoolExecutor(max_workers=w5.WORKERS) as ex:
                for i in range(0, len(todo), chunk):
                    futs = {ex.submit(w5.cs.full_two_step, env, tp, s, w5.HORIZON): s
                            for s in todo[i:i + chunk]}
                    for f in concurrent.futures.as_completed(futs):
                        r = f.result(); r.pop("detail", None)
                        slot[futs[f]] = r
                    w5.atomic_write(OUT, res)
                    print(f"[cost] slippage {lv}p: {len(slot)}/{len(ss)}", flush=True)
        rows = [slot[s] for s in ss if s in slot]
        br = sum(1 for r in rows if r.get("breach"))
        tot = sorted(r["total"] for r in rows if r.get("total") is not None)
        print(f"[cost] slippage {lv:>4}p  breach {br:>2}  pass {len(tot):>2}/{len(rows)}  "
              f"median {tot[len(tot)//2] if tot else '-'}d  "
              f"<=30d {sum(1 for t in tot if t<=30)}", flush=True)

    print("\n" + "=" * 64, flush=True)
    print("[cost] GEVOELIGHEID VOOR HANDELSKOSTEN", flush=True)
    print(f"  {'slippage':>10}{'breach':>9}{'pass':>8}{'median':>9}{'<=30d':>8}", flush=True)
    base = None
    for lv in LEVELS:
        rows = [res[lv][s] for s in ss if s in res.get(lv, {})]
        if not rows:
            continue
        br = sum(1 for r in rows if r.get("breach"))
        tot = sorted(r["total"] for r in rows if r.get("total") is not None)
        med = tot[len(tot)//2] if tot else 0
        p30 = sum(1 for t in tot if t <= 30)
        if base is None:
            base = (br, len(tot), med, p30)
        d = "" if lv == LEVELS[0] else \
            f"   ({br-base[0]:+d} breach, {len(tot)-base[1]:+d} pass, {med-base[2]:+d}d)"
        print(f"  {lv+'p':>10}{br:>9}{len(tot):>8}{str(med)+'d':>9}{p30:>8}{d}", flush=True)
    print("\n  Let op: dit is GELIJKE slippage op elk instrument. Realistisch is de", flush=True)
    print("  extra kost veel hoger op XAU/XAG/NAS100 dan op EUR/USD.", flush=True)
    print("[w5_costs] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
