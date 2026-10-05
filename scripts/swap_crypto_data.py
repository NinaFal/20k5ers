#!/usr/bin/env python3
"""
Zet de nieuwe Binance-cryptodata in gebruik en zet de oude apart.

WAAROM DIT NIET GEWOON KOPIEREN IS. De loader zoekt met een glob op
`{symbool}_{tf}_*.csv` EN `{symboolzonderstreep}_{tf}_*.csv` en PLAKT alles wat
matcht aan elkaar (`csv_mt5_simulator.py:756-770`). Daarna gooit hij dubbele
tijdstempels weg met `keep='last'`. Als het oude uurbestand naast het nieuwe
kwartierbestand blijft staan, botsen ze op elk heel uur en beslist de
sorteervolgorde welke wint — en `sort_values` is niet stabiel gespecificeerd.
Dan handel je op een reeks die per run kan verschillen.

Precies dat gebeurt nu al met NAS100 (zie W5_DATA_INTEGRITY.md): 751 dagbars uit
een `_2020_2025`-bestand overschrijven de echte M15-bar om 00:00. Die fout wordt
hier niet herhaald: oude bestanden gaan naar `data/ohlcv/_quarantine/`, ze
verdwijnen niet.

Draait niets weg zonder `--apply`. Zonder die vlag laat hij alleen zien wat er
zou gebeuren.
"""
import shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data" / "ohlcv"
Q = D / "_quarantine"

# Bestanden van Yahoo waarvan gemeten is dat de inhoud niet bij de naam past.
# Reden staat erbij zodat later niemand ze terugzet zonder te weten waarom.
RETIRE = {
    "BTC_USD_M15_2020_2025.csv": "uurbars vanaf 2023, 47% dekking, gat van 48 dagen",
    "ETH_USD_M15_2020_2025.csv": "uurbars vanaf 2023, 47% dekking, gat van 48 dagen",
    "BTC_USD_H1.csv":            "DAGbars in een bestand dat H1 heet",
    "ETH_USD_H1.csv":            "DAGbars in een bestand dat H1 heet",
}

# Deze zijn inhoudelijk in orde maar botsen met de Binance-bestanden op dezelfde
# timeframe. Welke bron wint is een keuze, geen fout — zie compare_d1.py.
CONFLICT = ["BTCUSD_D1_2003_2025.csv", "BTCUSD_W1_2003_2025.csv",
            "BTCUSD_MN_2003_2025.csv", "BTCUSD_H4_2003_2025.csv",
            "ETHUSD_D1_2003_2025.csv", "ETHUSD_W1_2003_2025.csv",
            "ETHUSD_MN_2003_2025.csv", "ETHUSD_H4_2003_2025.csv"]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("OUDE CRYPTOBESTANDEN NAAR QUARANTAINE" if apply else "PROEFDRAAI — er wordt niets verplaatst")
    print("=" * 74)

    print("\nNieuwe Binance-bestanden die klaarstaan:")
    new = sorted(D.glob("BTC_USD_*_2017_*.csv")) + sorted(D.glob("ETH_USD_*_2017_*.csv"))
    for f in new:
        print(f"  {f.name:<34}{f.stat().st_size/1e6:>8.1f} MB")
    if not new:
        print("  GEEN — draai eerst scripts/download_crypto_binance.py")
        return 1

    print("\nNaar quarantaine (inhoud past niet bij de naam):")
    for name, why in RETIRE.items():
        p = D / name
        print(f"  {name:<34}{'aanwezig' if p.exists() else 'al weg':<10}{why}")
        if apply and p.exists():
            Q.mkdir(exist_ok=True)
            shutil.move(str(p), str(Q / name))

    print("\nBotst met een Binance-bestand op dezelfde timeframe:")
    for name in CONFLICT:
        p = D / name
        tf = name.split("_")[1]
        rival = list(D.glob(f"{name[:3]}_USD_{tf}_2017_*.csv"))
        if not p.exists():
            print(f"  {name:<34}al weg")
            continue
        if rival:
            print(f"  {name:<34}botst met {rival[0].name} -> quarantaine")
            if apply:
                Q.mkdir(exist_ok=True)
                shutil.move(str(p), str(Q / name))
        else:
            print(f"  {name:<34}geen Binance-tegenhanger -> blijft staan")

    if not apply:
        print("\nDraai opnieuw met --apply om dit uit te voeren.")
    else:
        print(f"\nVerplaatst naar {Q}")
        print("LET OP: dit verandert de backtestresultaten. De bevroren baseline")
        print("is gemeten zonder deze data en moet opnieuw gevalideerd worden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
