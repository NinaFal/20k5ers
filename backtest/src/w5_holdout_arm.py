#!/usr/bin/env python3
"""
Dezelfde 100 challenge-vensters, maar met een instelbare symbolenlijst.

Waarom dit los van w5_holdout3.py staat. Die draait de configuratie die je
werkelijk gaat handelen. Dit draait varianten daarop om te kunnen TOEWIJZEN:
holdout3 laat op de eerste 26 vensters 3 breaches zien met de drie FX-paren aan
tegen 1 met ze uit. Als dat standhoudt is de vraag meteen: komt het door alle
drie of door een?

Opzet is LEAVE-ONE-OUT vanaf de huidige configuratie, niet add-one-in. Dat is de
vraag die je kunt uitvoeren: als ik dit ene paar eruit haal, verdwijnen die
breaches dan? Add-one-in beantwoordt een vraag die niemand stelt.

Cruciaal: alle armen delen dezelfde honderd vensters. Daardoor is het verschil
gepaard en valt de steekproefruis grotendeels tegen zichzelf weg — met honderd
vensters en een handvol breaches is dat het verschil tussen een meting en een
gok.

  W5_ARM=base       de huidige configuratie (identiek aan holdout3)
  W5_ARM=no_audnzd  zonder AUD_NZD
  W5_ARM=no_eurnzd  zonder EUR_NZD
  W5_ARM=no_audjpy  zonder AUD_JPY
  W5_ARM=no_nas100  zonder NAS100_USD (het enige symbool dat in beide helften
                    verlies maakt: -$41/trade vroeg, -$122/trade laat)

Draaien:  W5_ARM=no_audnzd uv run python3 backtest/src/w5_holdout_arm.py
"""
import concurrent.futures, importlib.util, json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

BASE = "XRP_USD,ADA_USD,BTC_USD,ETH_USD"          # de huidige uitsluitingen
ARMS = {
    "base":      BASE,
    "no_audnzd": BASE + ",AUD_NZD",
    "no_eurnzd": BASE + ",EUR_NZD",
    "no_audjpy": BASE + ",AUD_JPY",
    "no_nas100": BASE + ",NAS100_USD",
}
ARM = os.getenv("W5_ARM", "")
if ARM not in ARMS:
    raise SystemExit(f"zet W5_ARM op een van {sorted(ARMS)}")

STARTS_FILE = w5.DOE_DIR / "THIRD_100_STARTS.json"
OUT = w5.W5_DIR / f"holdout_arm_{ARM}.json"


def main():
    starts = json.loads(STARTS_FILE.read_text())["starts"]
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = dict(w5.BASE_ENV); env.update(b["env"])
    env["EXCLUDE_SYMBOLS"] = ARMS[ARM]
    tp = dict(w5.BASE_TP); tp.update(b["tp"])

    res = w5.load_json(OUT)
    todo = [s for s in starts if s not in res]
    print(f"[{ARM}] uitgesloten: {ARMS[ARM]}", flush=True)
    print(f"[{ARM}] {len(res)} gecached, {len(todo)} te gaan | {w5.WORKERS} workers", flush=True)

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
            print(f"[{ARM}] {len(res)}/{len(starts)}  breaches {br}", flush=True)

    br = [s for s in starts if res.get(s, {}).get("breach")]
    tot = sorted(v["total"] for v in res.values() if v.get("total") is not None)
    print(f"\n[{ARM}] {len(res)} starts | {len(tot)} geslaagd | {len(br)} breach | "
          f"mediaan {tot[len(tot)//2] if tot else '-'}d", flush=True)
    print(f"[{ARM}] breachende starts: {sorted(br)}", flush=True)
    print(f"\n[w5_holdout_arm] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
