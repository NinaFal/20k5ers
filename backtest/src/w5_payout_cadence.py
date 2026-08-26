#!/usr/bin/env python3
"""
Is elke twee weken winst nemen beter dan wachten op de +10%-mijlpaal?

Het huidige model betaalt alleen uit op een mijlpaal: zodra de balans het
gefinancierde niveau x 1,10 raakt, gaat alle winst eraf en schuift het niveau
een sport op. Dat gebeurde 5 tot 9 keer per jaar, dus gemiddeld om de twee
maanden — niet om de twee weken.

De split verandert niet met de timing. 5ers betaalt hetzelfde percentage of je
nu na twee weken of na twee maanden opneemt. Wat wel verandert:

  ONDER DE CAP kost vroeg opnemen een sport. De ladder schuift pas op bij +10%,
  en een sport is meer waard dan het geld: van $50k naar $60k lever je $5.000
  winst in (waarvan je er $4.000 houdt) en zet 5ers je account $10.000 hoger.
  Elke dollar die je er eerder afhaalt, duwt die sport verder weg.

  OP DE CAP is er niets meer te winnen met wachten. Er zijn geen sporten meer.
  Winst die op het account blijft staan is winst die je nog kunt verliezen —
  maar het is ook de buffer tussen je equity en de 10%-muur, die op $450.000
  vastligt zolang het niveau $500.000 is. Vaker opnemen betekent dus een dunnere
  buffer. Welke van die twee wint is een empirische vraag, geen redenering.

Drie armen, allemaal $50.000 start, 2015-2025, jaar voor jaar doorgerold:

  milestone     het huidige model. Uit fiftyk_decade.json, niet opnieuw gedraaid.
  biweekly_all  elke 14 dagen alles boven het niveau eraf, op elk niveau.
  biweekly_cap  elke 14 dagen, maar pas zodra het account op de cap staat;
                daaronder gewoon de mijlpaal. Dit is de kandidaat die het beste
                van beide zou moeten combineren.

Draaien:  uv run python3 backtest/src/w5_payout_cadence.py
"""
import hashlib, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

START_BALANCE = 50_000.0
YEARS = list(range(2015, 2026))
SCALE_CAP = "500000"
OUT = w5.W5_DIR / "payout_cadence.json"
BASELINE = w5.W5_DIR / "fiftyk_decade.json"

ARMS = (
    ("biweekly_all", {"FIVEERS_MAX_SCALE": SCALE_CAP, "FIVEERS_PAYOUT_DAYS": "14"}),
    ("biweekly_cap", {"FIVEERS_MAX_SCALE": SCALE_CAP, "FIVEERS_PAYOUT_DAYS": "14",
                      "FIVEERS_PAYOUT_AT_CAP_ONLY": "1"}),
)

MONTHLY_FIXED = 10_000


def data_fingerprint():
    """Vingerafdruk van de koersdata waarop een resultaat gemeten is.

    Deze cache wordt jaar voor jaar opgebouwd en kan dagen beslaan. Als de
    onderliggende data intussen verandert — zoals bij het vervangen van de
    Yahoo-cryptobestanden door Binance — dan zijn de oude jaren gemeten in een
    andere wereld dan de nieuwe, en levert hervatten een vergelijking op tussen
    twee dingen die niet vergelijkbaar zijn. Zonder deze controle gebeurt dat
    stil: het script hervat gewoon en de tabel ziet er net zo overtuigend uit.

    Naam plus grootte van elk M15-bestand is genoeg. De inhoud hashen zou een
    gigabyte lezen bij elke start voor een zekerheid die hier niet nodig is.
    """
    d = w5.cs.dh.REPO / "data" / "ohlcv"
    parts = sorted(f"{f.name}:{f.stat().st_size}" for f in d.glob("*_M15*.csv"))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def check_vintage(res):
    """Weigert te hervatten als de data sinds de vorige run veranderd is.

    Een ontbrekende vingerafdruk op een cache die AL jaren bevat betekent niet
    "in orde", het betekent "onbekend" — die cache is opgebouwd voordat deze
    controle bestond en er is niets dat zegt op welke data. Een eerdere versie
    hiervan stempelde in dat geval gewoon de huidige vingerafdruk en liet de run
    doorgaan, precies het stille scenario dat de controle moest afvangen.
    """
    now = data_fingerprint()
    was = res.get("_data_fingerprint")
    has_work = any(isinstance(v, dict) and v.get("years") for v in res.values())
    if not has_work:
        res["_data_fingerprint"] = now
        return True
    if was == now:
        return True
    if was is None:
        was = "ONBEKEND (cache van voor deze controle)"
    print("=" * 78, flush=True)
    print("GESTOPT — de koersdata is veranderd sinds deze cache is opgebouwd.", flush=True)
    print(f"  cache gemeten op data {was}", flush=True)
    print(f"  huidige data          {now}", flush=True)
    print("", flush=True)
    print("De opgeslagen jaren zijn gemeten op andere data dan de jaren die nu", flush=True)
    print("zouden volgen. Hervatten levert een vergelijking op tussen twee", flush=True)
    print("verschillende werelden, en dat is aan de uitkomst niet te zien.", flush=True)
    print("", flush=True)
    print("Ook de referentiearm komt uit fiftyk_decade.json en is op de OUDE", flush=True)
    print("data gemeten; die moet dus net zo goed opnieuw.", flush=True)
    print("", flush=True)
    print(f"  verplaats {OUT.name} en start opnieuw, of", flush=True)
    print("  draai met --resume-anyway als je bewust een gemengde run wilt.", flush=True)
    print("=" * 78, flush=True)
    return False


def run_year(over, year, balance, tag):
    b = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    e = dict(os.environ); e.update(w5.cs.dh.BASE_ENV)
    e.update(w5.BASE_ENV); e.update(b["env"]); e.update(over)
    e["CFG_DAILY_WALL_PCT"] = w5.BASE_ENV.get("CFG_DAILY_WALL_PCT", "5.0")
    e.setdefault("BROKER_TYPE", "fiveers_live")
    tp = dict(w5.BASE_TP); tp.update(b["tp"])
    e["OPT_PARAMS"] = json.dumps({**w5.cs.dh.BASE_TP, **tp})
    e["PYTHONUTF8"] = "1"
    d = w5.DOE_DIR / "tmp" / f"cad_{tag}_{year}"
    shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, str(w5.cs.dh.BACKTEST),
                        "--start", f"{year}-01-01", "--end", f"{year}-12-31",
                        "--balance", f"{balance:.2f}", "--output", str(d), "--quiet"],
                       env=e, cwd=str(w5.cs.dh.REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=14400)
        rj = d / "results.json"
        if not rj.exists():
            return {"error": "no results.json"}
        r = json.loads(rj.read_text())
        log = r.get("fiveers_scaling_log") or r.get("scaling_log") or []
        return {
            "start_balance": balance,
            "withdrawn": r.get("fiveers_total_withdrawn") or 0.0,
            "final_balance": r.get("final_balance"),
            "funded_level_end": (log[-1]["new_level"] if log else balance),
            "scale_ups": len(log),
            "max_ddd_pct": r.get("max_ddd_pct"), "max_tdd_pct": r.get("max_tdd_pct"),
            "trades": r.get("total_trades"), "win_rate": r.get("win_rate"),
            "account_failed": r.get("account_failed"),
            "fail_reason": (r.get("fail_info") or {}).get("reason"),
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)


def months_at_cap(years_dict):
    """Kalendermaanden waarin het niveau op de cap stond — voor de vaste $10k."""
    n = 0
    for y in sorted(years_dict):
        r = years_dict[y]
        if r.get("error"):
            continue
        if (r.get("funded_level_end") or 0) >= 500_000:
            n += 12 if (r.get("start_balance") or 0) >= 500_000 else 6
    return n


def main():
    res = w5.load_json(OUT)
    if not check_vintage(res) and "--resume-anyway" not in sys.argv:
        return 1
    (w5.DOE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
    for arm, over in ARMS:
        slot = res.setdefault(arm, {"years": {}})
        if slot.get("dead"):
            print(f"[cad] {arm}: al dood — overslaan", flush=True); continue
        bal = START_BALANCE
        for y in YEARS:
            if str(y) in slot["years"]:
                r = slot["years"][str(y)]
                bal = r.get("funded_level_end") or bal
                continue
            print(f"[cad] {arm} {y}: start op ${bal:,.0f}", flush=True)
            r = run_year(over, y, bal, arm)
            slot["years"][str(y)] = r
            w5.atomic_write(OUT, res)
            if r.get("error"):
                print(f"[cad] {arm} {y}: FOUT {r['error']}", flush=True); break
            cw = sum((v.get("withdrawn") or 0) for v in slot["years"].values())
            print(f"[cad] {arm} {y}: opgenomen ${r['withdrawn']:,.0f} "
                  f"(cum ${cw:,.0f})  bal ${(r.get('final_balance') or 0):,.0f} "
                  f"lvl ${(r.get('funded_level_end') or 0):,.0f} "
                  f"sporten {r['scale_ups']} "
                  f"DDD {r['max_ddd_pct']}% TDD {r['max_tdd_pct']}%"
                  + (f"  <-- DOOD: {r['fail_reason']}" if r.get("account_failed") else ""),
                  flush=True)
            if r.get("account_failed"):
                slot["dead"] = {"year": y, "reason": r.get("fail_reason")}
                w5.atomic_write(OUT, res); break
            bal = r.get("funded_level_end") or bal
        slot["total_withdrawn"] = sum((v.get("withdrawn") or 0)
                                      for v in slot["years"].values())
        slot["survived"] = not slot.get("dead") and len(slot["years"]) == len(YEARS)
        w5.atomic_write(OUT, res)

    print("\n" + "=" * 80, flush=True)
    print("[cad] UITBETAALCADANS — $50.000 start, 2015-2025", flush=True)
    print("=" * 80, flush=True)

    base = w5.load_json(BASELINE).get("scaled", {})
    table = [("milestone (huidig)", base)]
    table += [(arm, res.get(arm, {})) for arm, _ in ARMS]

    print(f"\n  {'arm':<22}{'handelswinst':>15}{'vast $10k/mnd':>16}"
          f"{'totaal':>15}{'ergste dag':>12}{'ergste TDD':>12}", flush=True)
    for name, slot in table:
        ys = {k: v for k, v in (slot.get("years") or {}).items() if not v.get("error")}
        if not ys:
            print(f"  {name:<22}(geen data)", flush=True); continue
        tw = slot.get("total_withdrawn", 0)
        fx = months_at_cap(ys) * MONTHLY_FIXED
        wd = max((v.get("max_ddd_pct") or 0) for v in ys.values())
        wt = max((v.get("max_tdd_pct") or 0) for v in ys.values())
        dead = slot.get("dead")
        tag = f"  DOOD {dead['year']}" if dead else ""
        print(f"  {name:<22}${tw:>14,.0f}${fx:>15,.0f}${tw + fx:>14,.0f}"
              f"{wd:>11.2f}%{wt:>11.2f}%{tag}", flush=True)

    print("\n  Jaar waarin de cap bereikt werd:", flush=True)
    for name, slot in table:
        ys = slot.get("years") or {}
        hit = next((y for y in sorted(ys)
                    if (ys[y].get("funded_level_end") or 0) >= 500_000), None)
        print(f"    {name:<22}{hit or 'nooit'}", flush=True)

    print("\n[w5_payout_cadence] DONE_MARKER", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
