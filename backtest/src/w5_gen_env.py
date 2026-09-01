#!/usr/bin/env python3
"""
Genereert het Windows-startbestand uit BASELINE_t65_tdd_FROZEN.json.

Waarom genereren en niet met de hand schrijven: een handgeschreven .bat loopt
uit de pas zodra de config verandert, en niemand merkt dat. Dit leest de frozen
config en zet er precies die variabelen in die de LIVE bot leest — niet de
backtest-only vlaggen (TDD_WORST_CASE, TERMINAL_ON_BREACH), want die hebben
live geen betekenis en zouden alleen verwarren.

Eén bewuste afwijking wordt expliciet gezet in plaats van overgenomen:
NIGHTLY_DERISK_HOUR staat in de frozen config op 22 (wat getest is) maar moet
live op 21, omdat 22:00 UTC midden in het rollover-venster valt waar spreads
5-50x uitlopen — kosten die de vlakke-spread simulator niet ziet.

Credentials worden NIET in het bestand gezet. Die horen in de omgeving van de
machine, niet in een bestand dat in git staat.

Draaien:  uv run python3 backtest/src/w5_gen_env.py
"""
import importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

# Alleen wat main_live_bot.py daadwerkelijk uitleest.
LIVE_KEYS = [
    "CFG_MAX_CUM_RISK", "CORR_GROUP_CAP", "MAX_TOTAL_POSITIONS", "EXCLUDE_SYMBOLS",
    "CFG_TDD_CAUTION_PCT", "CFG_RISK_CAUTIOUS", "CFG_TDD_EMERGENCY_PCT",
    "TDD_WALL_SAFETY", "CFG_DAILY_HALT_PCT", "TDD_EMERGENCY_HALT",
    "NIGHTLY_DERISK", "NIGHTLY_DERISK_HOUR", "NIGHTLY_MAX_PER_GROUP",
    "NIGHTLY_MAX_TOTAL", "NIGHTLY_R_CLOSE_LOSING", "NIGHTLY_R_NEW",
    "NIGHTLY_REDUCE_PCT", "RISK_REGIME_ENABLE", "RISK_CALM_MULT",
    "RISK_VOLATILE_MULT", "VOL_REGIME_DD_OFF", "VOL_REGIME_DD_MULT",
]
OVERRIDES = {
    "NIGHTLY_DERISK_HOUR": ("21", "getest op 22, maar 22:00 UTC valt in het "
                                  "rollover-venster (21:30-22:30) waar spreads "
                                  "5-50x uitlopen"),
    "BROKER_TYPE": ("fiveers_live", "KRITIEK: ongezet = forexcom_demo"),
}


def main():
    frozen = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    eff = {**w5.cs.dh.BASE_ENV, **w5.BASE_ENV, **frozen["env"]}
    lines = [
        "@echo off",
        "REM ===================================================================",
        "REM  5ers live bot — W5 baseline (t65 + TDD tiers)",
        "REM  GEGENEREERD door backtest/src/w5_gen_env.py — niet met de hand",
        "REM  aanpassen; draai het script opnieuw als de config verandert.",
        "REM ===================================================================",
        "",
        "REM --- broker ---",
    ]
    for k, (v, why) in OVERRIDES.items():
        lines += [f"REM {why}", f"set {k}={v}", ""]
    lines.append("REM --- gevalideerde strategie-instellingen ---")
    for k in LIVE_KEYS:
        if k in OVERRIDES:
            continue
        v = eff.get(k)
        if v is None:
            continue
        lines.append(f"set {k}={v}")
    lines += [
        "",
        "REM --- credentials: NIET hier invullen, zet ze in de omgeving ---",
        "if \"%MT5_LOGIN%\"==\"\" echo [FOUT] MT5_LOGIN niet gezet && exit /b 1",
        "if \"%MT5_PASSWORD%\"==\"\" echo [FOUT] MT5_PASSWORD niet gezet && exit /b 1",
        "if \"%MT5_SERVER%\"==\"\" echo [FOUT] MT5_SERVER niet gezet && exit /b 1",
        "",
        "REM --- verificatie: bot start NIET als de config afwijkt ---",
        "python backtest\\src\\w5_acceptance.py",
        "if errorlevel 1 (",
        "  echo.",
        "  echo [AFGEBROKEN] Config wijkt af van de gevalideerde baseline.",
        "  echo De bot is NIET gestart.",
        "  exit /b 1",
        ")",
        "",
        "echo [OK] Config komt overeen met de gevalideerde baseline.",
        "python main_live_bot.py %*",
    ]
    out = REPO / "deploy" / "start_live.bat"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    print(f"geschreven: {out}")
    print(f"  {len([k for k in LIVE_KEYS if eff.get(k) is not None])} strategie-variabelen")
    print(f"  {len(OVERRIDES)} bewuste overrides")


if __name__ == "__main__":
    main()
