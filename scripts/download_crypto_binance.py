#!/usr/bin/env python3
"""
Haalt BTC en ETH op bij Binance: M15, D1, W1 en MN, volledige historie.

WAAROM DIT NODIG WAS. De bestaande cryptobestanden komen van Yahoo Finance
(`download_m15_data.py` gebruikt Yahoo als fallback voor crypto). Yahoo levert
intraday maar een beperkt venster: ongeveer 60 dagen op 15 minuten en 730 dagen
op een uur. Het script schreef die uitkomst weg onder de naam
`BTC_USD_M15_2020_2025.csv`, maar wat erin staat zijn UURbars vanaf 2023 met 47%
dekking en een gat van 48 dagen. `BTC_USD_H1.csv` bevat zelfs DAGbars. De naam
van het bestand zegt dus niets over de inhoud, en niets waarschuwde daarvoor.

Gevolg tot nu toe: crypto handelde in de hele backtest 24 keer, allemaal in 2023
of later, op uurbars. Elke uitspraak over hoe de strategie zich op crypto
gedraagt rust daarop.

BRON. data.binance.vision, de publieke archieven van Binance. Geen sleutel
nodig, maandelijkse zips per symbool en interval, tijden in UTC.
BTCUSDT en ETHUSDT beginnen allebei in augustus 2017.

BTCUSDT IS NIET BTCUSD. 5ers noteert tegen USD, Binance tegen USDT. Die twee
lopen in de praktijk binnen een fractie van een procent uit elkaar, maar het is
een proxy en geen identiek instrument. Voor een strategie die op structuur en
ATR handelt is dat verwaarloosbaar; voor de exacte instapprijs van een
individuele trade niet. Dit staat hier zodat niemand later denkt dat dit
5ers-data is.

WAT ER NIET UIT KOMT. Voor augustus 2017 bestaat er geen Binance-data. BTC
handelde toen al wel. De bestaande `BTCUSD_D1_2003_2025.csv` gaat terug tot
september 2014 en is echte dagdata; die wordt hier niet overschreven maar apart
gehouden, zodat de afweging tussen langere historie en een consistente bron
achteraf te maken is in plaats van nu stilzwijgend.

H4 ZIT ER OOK BIJ, hoewel er niet om gevraagd is. De confluentie leest
maandelijks, wekelijks, dagelijks EN H4 (`main_live_bot_backtest.py:3042-3045`).
Zonder H4 valt hij terug op `daily_candles[-20:]` — twintig dagbars in plaats van
vierhonderd vier-uursbars. Dat werkt, maar het is een andere invoer dan bedoeld.

Draaien:  uv run python3 scripts/download_crypto_binance.py
"""
import csv, io, sys, time, urllib.request, zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ohlcv"
BASE = "https://data.binance.vision/data/spot/monthly/klines"

SYMBOLS = {"BTCUSDT": "BTC_USD", "ETHUSDT": "ETH_USD"}
# Binance-interval -> onze timeframe-naam zoals csv_mt5_simulator hem zoekt.
INTERVALS = {"15m": "M15", "4h": "H4", "1d": "D1", "1w": "W1", "1mo": "MN"}
START = date(2017, 8, 1)
END = date(2025, 12, 1)


def months(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1; y += 1


def fetch(sym, interval, y, m):
    url = f"{BASE}/{sym}/{interval}/{sym}-{interval}-{y}-{m:02d}.zip"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            blob = r.read()
    except Exception as e:
        code = getattr(e, "code", None)
        if code == 404:
            return None                      # maand bestaat niet, normaal aan de randen
        raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        return list(csv.reader(io.TextIOWrapper(z.open(name), "utf-8")))


def to_row(rec):
    """Binance-kline -> onze kolommen. open_time staat in milliseconden UTC.

    Sinds begin 2025 levert Binance de tijd in microseconden in plaats van
    milliseconden. Zonder deze correctie belanden die maanden in het jaar 57000
    en verdwijnen ze stil uit elke datumfilter.
    """
    t = int(rec[0])
    if t > 10 ** 14:
        t //= 1000
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t / 1000))
    return [f"{ts}+00:00", rec[1], rec[2], rec[3], rec[4], rec[5]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for sym, ours in SYMBOLS.items():
        for interval, tf in INTERVALS.items():
            rows, missing = [], 0
            for y, m in months(START, END):
                got = fetch(sym, interval, y, m)
                if got is None:
                    missing += 1
                    continue
                rows.extend(to_row(r) for r in got if r and r[0].isdigit())
            if not rows:
                print(f"  {ours} {tf}: NIETS opgehaald", flush=True)
                continue
            rows.sort(key=lambda r: r[0])
            # Ontdubbelen: maandarchieven overlappen soms op de grens.
            seen, clean = set(), []
            for r in rows:
                if r[0] in seen:
                    continue
                seen.add(r[0]); clean.append(r)
            first, last = clean[0][0][:10], clean[-1][0][:10]
            path = OUT / f"{ours}_{tf}_{first[:4]}_{last[:4]}.csv"
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["time", "open", "high", "low", "close", "volume"])
                w.writerows(clean)
            print(f"  {path.name:<32}{len(clean):>8} bars  {first} .. {last}"
                  f"  ({missing} maanden zonder data)", flush=True)
    print("\n[download_crypto_binance] DONE_MARKER", flush=True)


if __name__ == "__main__":
    main()
