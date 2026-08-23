@echo off
REM ===================================================================
REM  5ers live bot — W5 baseline (t65 + TDD tiers)
REM  GEGENEREERD door backtest/src/w5_gen_env.py — niet met de hand
REM  aanpassen; draai het script opnieuw als de config verandert.
REM ===================================================================

REM --- broker ---
REM getest op 22, maar 22:00 UTC valt in het rollover-venster (21:30-22:30) waar spreads 5-50x uitlopen
set NIGHTLY_DERISK_HOUR=21

REM KRITIEK: ongezet = forexcom_demo
set BROKER_TYPE=fiveers_live

REM --- gevalideerde strategie-instellingen ---
set CFG_MAX_CUM_RISK=7.0
set CORR_GROUP_CAP=6
set MAX_TOTAL_POSITIONS=20
set EXCLUDE_SYMBOLS=AUD_NZD,EUR_NZD,AUD_JPY
set CFG_TDD_CAUTION_PCT=1.5
set CFG_RISK_CAUTIOUS=0.4
set CFG_TDD_EMERGENCY_PCT=5.5
set TDD_WALL_SAFETY=5.5
set CFG_DAILY_HALT_PCT=2.50
set TDD_EMERGENCY_HALT=0
set NIGHTLY_DERISK=1
set NIGHTLY_MAX_PER_GROUP=0
set NIGHTLY_MAX_TOTAL=0
set NIGHTLY_R_CLOSE_LOSING=0.25
set NIGHTLY_R_NEW=0.5
set NIGHTLY_REDUCE_PCT=0.75
set RISK_REGIME_ENABLE=1
set RISK_CALM_MULT=1.45
set RISK_VOLATILE_MULT=1.0
set VOL_REGIME_DD_OFF=5.0
set VOL_REGIME_DD_MULT=1.0

REM --- credentials: NIET hier invullen, zet ze in de omgeving ---
if "%MT5_LOGIN%"=="" echo [FOUT] MT5_LOGIN niet gezet && exit /b 1
if "%MT5_PASSWORD%"=="" echo [FOUT] MT5_PASSWORD niet gezet && exit /b 1
if "%MT5_SERVER%"=="" echo [FOUT] MT5_SERVER niet gezet && exit /b 1

REM --- verificatie: bot start NIET als de config afwijkt ---
python backtest\src\w5_acceptance.py
if errorlevel 1 (
  echo.
  echo [AFGEBROKEN] Config wijkt af van de gevalideerde baseline.
  echo De bot is NIET gestart.
  exit /b 1
)

echo [OK] Config komt overeen met de gevalideerde baseline.
python main_live_bot.py %*
