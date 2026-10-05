#!/usr/bin/env python3
"""
Controleer op de ECHTE 5ers-server of de bot de klok goed heeft.

Draai dit op de Windows-machine waar MT5 en de bot staan:

    python scripts/verify_server_clock.py

Alleen lezen: logt in, leest de laatste tick, logt uit. Plaatst niets.

WAT HET MEET. MT5 geeft de tijd van een tick als seconden-sinds-1970 IN
SERVERTIJD (alsof de serverklok UTC was). Het verschil met de echte UTC-tijd,
afgerond op het hele uur, is dus de offset van de server. Die wordt vergeleken
met wat de bot zelf uitrekent in _w5_server_tz().

WAAROM. De bot draaide op een vaste UTC+2 "no DST". Aan elf jaar data gemeten
schakelt de broker wel om, op AMERIKAANSE data: UTC+2 in de winter, UTC+3 in de
zomer. De code is daarop aangepast. Dit script bevestigt dat op jouw server, in
plaats van dat je het van de data moet aannemen.

Draai het bij voorkeur twee keer per jaar: eens in de winter en eens in de
zomer. En zeker in de weken tussen de Amerikaanse en de Europese omschakeling
(tweede helft van maart, eind oktober/begin november) — daar zou een verkeerde
aanname zich het eerst laten zien.
"""
import os, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import MetaTrader5 as mt5
except ImportError:
    sys.exit("MetaTrader5 niet geinstalleerd — dit moet op de Windows-machine met MT5.")

LOGIN = os.getenv("MT5_LOGIN"); PWD = os.getenv("MT5_PASSWORD"); SRV = os.getenv("MT5_SERVER")
if not (LOGIN and PWD and SRV):
    sys.exit("MT5_LOGIN, MT5_PASSWORD en MT5_SERVER moeten gezet zijn.")

if not mt5.initialize():
    sys.exit(f"MT5 initialize mislukt: {mt5.last_error()}")
try:
    if not mt5.login(int(LOGIN), password=PWD, server=SRV):
        sys.exit(f"Inloggen mislukt: {mt5.last_error()}")
    offsets = []
    for sym in ("EURUSD", "GBPUSD", "USDJPY"):
        mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        if tick and tick.time:
            utc_now = time.time()
            offsets.append(round((tick.time - utc_now) / 3600))
    if not offsets:
        sys.exit("Geen ticks ontvangen — is de markt open? (niet in het weekend draaien)")
    server_off = max(set(offsets), key=offsets.count)
finally:
    mt5.shutdown()

import main_live_bot as lb
bot_off = int(lb._w5_server_tz().utcoffset(None).total_seconds() // 3600)
now = datetime.now(timezone.utc)

print("=" * 60)
print(f"Server           : {SRV}")
print(f"Nu (UTC)         : {now:%Y-%m-%d %H:%M}")
print(f"Server zegt      : UTC{server_off:+d}")
print(f"Bot rekent       : UTC{bot_off:+d}")
print(f"Rolvenster nu    : {'JA' if lb._w5_in_rollover() else 'nee'}")
print(f"De-risk nu       : {'JA' if lb._w5_derisk_now() else 'nee'}")
print("=" * 60)
if server_off == bot_off:
    print("PASS — de bot heeft dezelfde klok als de server.")
    sys.exit(0)
print("FAIL — de bot zit er een of meer uren naast.")
print("Zet W5_BROKER_TZ zo dat 'Bot rekent' gelijk wordt aan 'Server zegt',")
print("en meld het: dan volgt deze broker niet de New Yorkse klok.")
sys.exit(1)
