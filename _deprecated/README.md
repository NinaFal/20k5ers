# Deprecated Code

Deze folder bevat code die niet meer actief gebruikt wordt.
De code is NIET verwijderd voor het geval we het later nodig hebben.

## Datum: 2026-01-03

## Reden voor deprecatie:

### tradr_data/
- `dukascopy.py` - Alternatieve data provider, niet gebruikt
- `oanda.py` - Data komt uit CSV files, niet via API

### tradr_mt5/
- `bridge_client.py` - `client.py` wordt gebruikt in plaats hiervan

### tradr_utils/
- `state.py` - Nergens geïmporteerd

### root/
- `strategy.py` - Wrapper rond strategy_core.py, ScanResult verplaatst naar strategy_core.py

## Herstel instructies:
Als je deze code nodig hebt, kopieer het terug naar de originele locatie
en update de imports.