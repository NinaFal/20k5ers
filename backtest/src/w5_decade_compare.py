#!/usr/bin/env python3
"""
Legt alle gedraaide decade-armen naast elkaar.

Elke arm is elf jaar $50.000, dezelfde bevroren configuratie, dezelfde code, en
verschilt alleen in welke symbolen worden uitgesloten. Wat de armen betekenen
staat in w5_decade_crypto.py.

TWEE DINGEN DIE JE HIER NIET MOET AFLEZEN.

Opgenomen bedrag per jaar is misleidend. Op de cap vuurt een uitbetaling zodra
de balans +10% raakt; of dat op 28 december of 3 januari valt, verschuift een
blok van $50.000 tussen twee jaren zonder dat er iets verdiend is. Alleen
opgenomen PLUS eindbalans zegt iets, en dat is de kolom 'totaal'.

En een hoger totaal is niet automatisch beter. Een arm die verder komt op de
scalingladder verdient meer omdat hij met meer kapitaal handelt, niet
noodzakelijk omdat hij per trade beter is. Daarom staan het bereikte niveau en
de drawdown ernaast: dat is de prijs die voor dat kapitaal betaald is.

Draaien:  uv run python3 backtest/src/w5_decade_compare.py
"""
import importlib.util, json, statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

ORDER = ["nocrypto", "crypto", "fxpairs", "allon"]
LABEL = {
    "nocrypto": "referentie (huidige config)",
    "crypto":   "+ BTC/ETH",
    "fxpairs":  "+ AUD_NZD, EUR_NZD, AUD_JPY",
    "allon":    "+ beide",
}
YEARS = [str(y) for y in range(2015, 2026)]


def load(arm):
    p = w5.W5_DIR / f"decade_{arm}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    ys = d.get("years", {})
    done = [y for y in YEARS if y in ys and not ys[y].get("error")]
    return {"years": ys, "done": done, "dead": d.get("dead"),
            "complete": len(done) == len(YEARS)}


def main():
    arms = {a: load(a) for a in ORDER}
    have = {a: v for a, v in arms.items() if v}
    if not have:
        print("nog geen enkele arm gedraaid"); return

    print("=" * 92)
    print("DECADE-ARMEN NAAST ELKAAR — $50.000, 2015-2025, alleen de symbolenlijst verschilt")
    print("=" * 92)

    ref = have.get("nocrypto")
    print(f"\n  {'arm':<32}{'jaren':>7}{'totaal':>14}{'vs ref':>13}"
          f"{'ergste dag':>12}{'ergste tot':>12}{'niveau eind':>13}")
    for a in ORDER:
        v = have.get(a)
        if not v or not v["done"]:
            print(f"  {LABEL.get(a, a):<32}{'-':>7}   (nog niet gedraaid)")
            continue
        ys = v["years"]
        w = sum(ys[y]["withdrawn"] or 0 for y in v["done"])
        fb = ys[v["done"][-1]]["final_balance"] or 0
        tot = w + fb
        wd = max(ys[y]["max_ddd_pct"] or 0 for y in v["done"])
        wt = max(ys[y]["max_tdd_pct"] or 0 for y in v["done"])
        lvl = ys[v["done"][-1]].get("funded_level_end") or 0
        delta = ""
        if ref and ref["done"] and a != "nocrypto" and len(v["done"]) == len(ref["done"]):
            rw = sum(ref["years"][y]["withdrawn"] or 0 for y in ref["done"])
            rfb = ref["years"][ref["done"][-1]]["final_balance"] or 0
            delta = f"{(tot - rw - rfb) / (rw + rfb) * 100:+.1f}%"
        flag = "  ONVOLLEDIG" if not v["complete"] else ("  DOOD" if v["dead"] else "")
        print(f"  {LABEL.get(a, a):<32}{len(v['done']):>7}${tot:>13,.0f}{delta:>13}"
              f"{wd:>11.2f}%{wt:>11.2f}%${lvl:>12,.0f}{flag}")

    if not ref or not ref["done"]:
        print("\n[w5_decade_compare] DONE_MARKER"); return

    print(f"\n  Per jaar, TOTAAL verschil met de referentie (opgenomen, in duizenden $):")
    print(f"  {'jaar':<6}" + "".join(f"{LABEL.get(a,a).split('(')[0].strip()[:14]:>16}"
                                     for a in ORDER if have.get(a)))
    for y in YEARS:
        cells = ""
        for a in ORDER:
            v = have.get(a)
            if not v or y not in v["years"] or v["years"][y].get("error"):
                cells += f"{'-':>16}"; continue
            wv = (v["years"][y]["withdrawn"] or 0) / 1000
            if a == "nocrypto":
                cells += f"{wv:>15.0f}k"
            else:
                rv = (ref["years"].get(y, {}).get("withdrawn") or 0) / 1000
                cells += f"{wv - rv:>+15.0f}k"
        print(f"  {y:<6}{cells}")

    print(f"\n  Drawdown per jaar (slechtste dag %, muur 5%):")
    print(f"  {'jaar':<6}" + "".join(f"{a:>12}" for a in ORDER if have.get(a)))
    for y in YEARS:
        cells = ""
        for a in ORDER:
            v = have.get(a)
            if not v or y not in v["years"] or v["years"][y].get("error"):
                cells += f"{'-':>12}"; continue
            cells += f"{v['years'][y]['max_ddd_pct']:>12}"
        print(f"  {y:<6}{cells}")

    print(f"\n  {'arm':<32}{'gem. dag':>11}{'trades':>9}{'winst/trade':>13}")
    for a in ORDER:
        v = have.get(a)
        if not v or not v["done"]:
            continue
        ys = v["years"]
        dd = st.mean(ys[y]["max_ddd_pct"] or 0 for y in v["done"])
        tr = sum(ys[y]["trades"] or 0 for y in v["done"])
        w = sum(ys[y]["withdrawn"] or 0 for y in v["done"])
        fb = ys[v["done"][-1]]["final_balance"] or 0
        print(f"  {LABEL.get(a, a):<32}{dd:>10.2f}%{tr:>9}${(w + fb - 50_000) / tr:>12,.0f}")

    print("\n[w5_decade_compare] DONE_MARKER")


if __name__ == "__main__":
    main()
