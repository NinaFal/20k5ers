#!/usr/bin/env python3
"""
Corrigeert het vaste-uitbetalingsmodel na het antwoord van 5ers support.

Wat 5ers schreef: "Once you reach the 500K level. You can withdraw 100% profit
+ $10,000 fixed amount every month."

Wat het model deed: $10.000 toekennen bij ELKE uitbetaling zodra het niveau
500K was, en $4.000 bij elke uitbetaling tussen 350K en 500K. Het aantal
uitbetalingen per jaar lag tussen 5 en 9, dus het antwoord van $672.000 hing
volledig af van de uitbetalingscadans van de simulator in plaats van aan de
kalender. Dat is de verkeerde as.

Twee correcte grenzen, beide berekend uit dezelfde opgeslagen gebeurtenissen:

  BOVENGRENS  elke kalendermaand op 500K-niveau telt voor $10.000. Dit klopt
              als het vaste bedrag onvoorwaardelijk is zodra je op 500K zit.

  ONDERGRENS  alleen maanden waarin de simulator daadwerkelijk winst uitbetaalde
              tellen, maximaal een keer per maand. Dit klopt als het vaste
              bedrag aan een winstuitbetaling hangt: geen winst, geen $10.000.

De $4.000-tier tussen 350K en 500K komt uit het oude model en staat niet in het
antwoord van support. Support noemde alleen 500K. Hij wordt hier apart gehouden
en niet in het hoofdcijfer meegeteld.

Draaien:  uv run python3 backtest/src/w5_payout_fix.py
"""
import json
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "output" / "doe" / "wall5" / "fiftyk_decade.json"
MONTHLY = 10_000


def main():
    d = json.loads(SRC.read_text())
    slot = d["scaled"]
    years = slot["years"]

    events = []
    for y in sorted(years):
        for ev in (years[y].get("fixed_bonus_events") or []):
            events.append((ev["time"][:7], float(ev["level"]), ev["amount"]))

    at500 = [e for e in events if e[1] >= 500_000]
    first = min(e[0] for e in at500)
    last = max(y + "-12" for y in sorted(years))

    def months_between(a, b):
        ya, ma = int(a[:4]), int(a[5:7])
        yb, mb = int(b[:4]), int(b[5:7])
        return (yb - ya) * 12 + (mb - ma) + 1

    n_cal = months_between(first, last)
    paid_months = sorted({e[0] for e in at500})
    n_paid = len(paid_months)

    old = slot["total_fixed_bonus"]
    sub500 = sum(a for _, l, a in events if l < 500_000)

    print("=" * 74)
    print("VASTE UITBETALING — GECORRIGEERD NA ANTWOORD 5ERS")
    print("=" * 74)
    print(f"\n  500K-niveau bereikt   {first}   (gebeurtenis "
          f"{[e for e in events if e[1] >= 500_000][0]})")
    print(f"  laatste maand model   {last}")
    print(f"\n  OUD (fout)                 ${old:>12,.0f}"
          f"   = $10k per uitbetaling, {len(at500)} uitbetalingen op 500K"
          f" + ${sub500:,.0f} onder 500K")
    print(f"\n  BOVENGRENS  {n_cal} maanden  ${n_cal * MONTHLY:>12,.0f}"
          f"   = elke kalendermaand op 500K")
    print(f"  ONDERGRENS  {n_paid} maanden  ${n_paid * MONTHLY:>12,.0f}"
          f"   = alleen maanden met winstuitbetaling")

    print(f"\n  per jaar, bovengrens       ${12 * MONTHLY:>12,.0f}")
    print(f"  per jaar, ondergrens       ${n_paid / (n_cal / 12) * MONTHLY:>12,.0f}"
          f"   ({n_paid / (n_cal / 12):.1f} betaalde maanden per jaar)")

    trading = slot["total_withdrawn"]
    print(f"\n  {'':<26}{'handelswinst':>16}{'vast':>14}{'totaal':>16}")
    for lbl, bonus in (("OUD (fout)", old),
                       ("bovengrens", n_cal * MONTHLY),
                       ("ondergrens", n_paid * MONTHLY)):
        print(f"  {lbl:<26}${trading:>15,.0f}${bonus:>13,.0f}${trading + bonus:>15,.0f}")

    print("\n  Jaar voor jaar, betaalde maanden op 500K-niveau:")
    per_year = {}
    for m in paid_months:
        per_year[m[:4]] = per_year.get(m[:4], 0) + 1
    for y in sorted(years):
        pm = per_year.get(y, 0)
        cal = 0
        if y > first[:4]:
            cal = 12
        elif y == first[:4]:
            cal = 12 - int(first[5:7]) + 1
        print(f"    {y}   kalender {cal:>2}  betaald {pm:>2}   "
              f"boven ${cal * MONTHLY:>7,.0f}   onder ${pm * MONTHLY:>7,.0f}")

    print("\n[w5_payout_fix] DONE_MARKER")


if __name__ == "__main__":
    main()
