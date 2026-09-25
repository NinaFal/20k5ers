#!/usr/bin/env python3
"""
Genereert een DERDE set van 100 challenge-startdata, los van de vorige twee.

Waarom een nieuwe set en niet dezelfde honderd opnieuw. Die twee vragen zijn
niet hetzelfde:

  DEZELFDE honderd opnieuw draaien is een gepaarde meting. Die heeft veel meer
  onderscheidend vermogen om te zien WAT MIJN WIJZIGINGEN HEBBEN GEDAAN, omdat
  de steekproefruis wegvalt tegen zichzelf.

  NIEUWE honderd beantwoorden 'wat is de slaagkans nu', zonder dat de vensters
  ooit een configuratiekeuze hebben beinvloed. Voor een getal waar je een
  inschrijfgeld op baseert is dat het eerlijke getal.

Deze set doet het tweede. De vorige twee sets zijn samen 200 vensters die
allemaal al een rol hebben gespeeld in beslissingen in dit project; deze niet.

De set is disjunct van beide voorgangers en wordt VOOR de meting vastgelegd en
gecommit, zodat er achteraf niets aan te schuiven valt.

Draaien:  uv run python3 backtest/src/w5_gen_starts3.py
"""
import json, random
from datetime import date, timedelta
from pathlib import Path

DOE = Path(__file__).resolve().parents[1] / "output" / "doe"
OUT = DOE / "THIRD_100_STARTS.json"
SEED = 20260828
N = 100
# Ruimte laten voor een challenge van maximaal 75 handelsdagen per stap.
FIRST, LAST = date(2015, 1, 2), date(2025, 6, 30)


def main():
    prev = set()
    for f in ("HOLDOUT_100_STARTS_2015.json", "CONFIRM_100_STARTS.json",
              "CANONICAL_100_STARTS.json"):
        p = DOE / f
        if p.exists():
            prev |= set(json.loads(p.read_text())["starts"])
    print(f"{len(prev)} vensters al gebruikt in eerdere sets")

    pool = []
    d = FIRST
    while d <= LAST:
        if d.weekday() < 5:                      # alleen handelsdagen
            s = d.isoformat()
            if s not in prev:
                pool.append(s)
        d += timedelta(days=1)
    print(f"{len(pool)} kandidaten over")

    rng = random.Random(SEED)
    starts = sorted(rng.sample(pool, N))
    assert not (set(starts) & prev), "overlap met een eerdere set"

    OUT.write_text(json.dumps(
        {"seed": SEED, "n": N, "generated": "2026-08-28",
         "disjoint_from": ["HOLDOUT_100_STARTS_2015.json", "CONFIRM_100_STARTS.json",
                           "CANONICAL_100_STARTS.json"],
         "note": "Derde onafhankelijke set. Vastgelegd voor de meting.",
         "starts": starts}, indent=1))
    yrs = {}
    for s in starts:
        yrs[s[:4]] = yrs.get(s[:4], 0) + 1
    print(f"geschreven: {OUT.name}  {starts[0]} .. {starts[-1]}")
    print(f"per jaar: {dict(sorted(yrs.items()))}")


if __name__ == "__main__":
    main()
