#!/usr/bin/env python3
"""
ACCEPTANCE TEST — does the live bot resolve the same configuration as the
backtest that produced the validated results?

What this is NOT. It is not a behavioural replay. main_live_bot.py cannot be run
against historical data — that is why main_live_bot_backtest.py exists as a fork
— so "run the live bot over the decade and compare" is not available. Anyone
reading a green result here should know that limit.

What it IS. Every bug this port actually produced was a configuration-layer bug:

  * editing ftmo_config.py silently rewrote the BACKTEST, because
    main_live_bot_backtest.py:165 imports the same object — it flipped a known
    breach into a 28-day pass and was only caught by chance
  * the wall-guard first reached for challenge_manager.starting_balance, the
    backtest's attribute name; live calls it initial_balance, so it would have
    read 0 and disabled the guard with no error
  * TDD_EMERGENCY_HALT was never ported at all, leaving live with the
    unconditional halt the backtest found CAUSES breaches
  * CFG_DAILY_HALT_PCT resolved to 3.2 live against the validated 2.50, and a
    third enforcement path in ChallengeRiskManager disagreed with both

Not one of those would show up in a syntax check or a code review skim. All four
are exactly what this test catches: for the frozen configuration, does every
parameter resolve to the same value on both sides?

Method. The live helpers are extracted from source and executed in isolation
rather than by importing main_live_bot, which would run module-level broker and
logger setup that needs credentials. Their resolved values are compared against
the frozen baseline and against what the backtest reads for the same key.

Exit code is non-zero on any mismatch so this can gate a deployment.

Run:  uv run python3 backtest/src/w5_acceptance.py
"""
import importlib.util, json, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)

LIVE = REPO / "main_live_bot.py"
BT = REPO / "backtest" / "src" / "main_live_bot_backtest.py"

# live helper -> (frozen env key, expected type)
CHECKS = [
    ("_w5_excluded_symbols",          "EXCLUDE_SYMBOLS",        "list"),
    ("_w5_corr_group_cap",            "CORR_GROUP_CAP",         "int"),
    ("_w5_max_total_positions",       "MAX_TOTAL_POSITIONS",    "int"),
    ("_w5_max_cum_risk_pct",          "CFG_MAX_CUM_RISK",       "float"),
    ("_w5_tdd_caution",               "CFG_TDD_CAUTION_PCT",    "float"),
    ("_w5_risk_cautious",             "CFG_RISK_CAUTIOUS",      "float"),
    ("_w5_tdd_emergency_pct",         "CFG_TDD_EMERGENCY_PCT",  "float"),
    ("_w5_wall_safety",               "TDD_WALL_SAFETY",        "float"),
    ("_w5_daily_halt_pct",            "CFG_DAILY_HALT_PCT",     "float"),
]


def load_live_helpers():
    """Exec the _w5_* module-level helpers in isolation.

    Importing main_live_bot would run broker/logger setup requiring credentials,
    so the functions are lifted out by source extraction instead.
    """
    src = LIVE.read_text()
    ns = {"os": os}
    for name in [c[0] for c in CHECKS] + ["_w5_tdd_emergency_halt_enabled"]:
        m = re.search(r"^def " + name + r"\(\):.*?(?=\n\ndef |\n\n# |\nclass )",
                      src, re.S | re.M)
        if not m:
            raise SystemExit(f"FATAL: live helper {name} not found in main_live_bot.py")
        exec(m.group(0), ns)
    return ns


def main():
    frozen = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    env = {**w5.cs.dh.BASE_ENV, **w5.BASE_ENV, **frozen["env"]}
    tp = {**w5.BASE_TP, **frozen["tp"]}
    live = load_live_helpers()
    bt_src = BT.read_text()
    fails, notes = [], []

    print("=" * 74)
    print("ACCEPTANCE: live configuration vs the frozen t65+TDD baseline")
    print("=" * 74)

    # 1 ── live helpers resolve to the frozen values, with NO env set.
    # Unset is the deployment default, so the built-in defaults must already be
    # correct; relying on an operator to export 20 variables is a failure mode.
    for name, key, kind in CHECKS:
        for k in list(os.environ):
            if k in (c[1] for c in CHECKS):
                del os.environ[k]
        got = live[name]()
        want = env.get(key)
        if kind == "list":
            ok = got == [s for s in str(want).replace(" ", "").split(",") if s]
        elif kind == "int":
            ok = int(got) == int(float(want))
        else:
            ok = abs(float(got) - float(want)) < 1e-9
        print(f"  {'OK ' if ok else 'FAIL'}  {name:<28} -> {got!r:<28} frozen {key}={want}")
        if not ok:
            fails.append(f"{name} resolved {got!r}, frozen config says {key}={want}")

    # 2 ── TDD_EMERGENCY_HALT must default OFF (frozen config sets 0)
    os.environ.pop("TDD_EMERGENCY_HALT", None)
    halt_on = live["_w5_tdd_emergency_halt_enabled"]()
    want_on = str(env.get("TDD_EMERGENCY_HALT", "1")).lower() not in ("0", "false", "no", "off")
    ok = halt_on == want_on
    print(f"  {'OK ' if ok else 'FAIL'}  {'TDD emergency halt enabled':<28} -> {halt_on!r:<28} "
          f"frozen TDD_EMERGENCY_HALT={env.get('TDD_EMERGENCY_HALT')}")
    if not ok:
        fails.append(f"TDD emergency halt is {halt_on}, frozen config wants {want_on}")

    # 3 ── the live params file must carry the validated ladder
    print("\n  --- params/current_params.json vs frozen tp ---")
    pf = json.loads((REPO / "params" / "current_params.json").read_text())["parameters"]
    for k in sorted(frozen["tp"]):
        got, want = pf.get(k), frozen["tp"][k]
        ok = (abs(got - want) < 1e-9) if isinstance(want, (int, float)) and isinstance(got, (int, float)) else got == want
        print(f"  {'OK ' if ok else 'FAIL'}  {k:<28} -> {got!r:<20} frozen {want!r}")
        if not ok:
            fails.append(f"params {k} = {got!r}, frozen says {want!r}")
    for k in ("tp4_close_pct", "tp5_close_pct"):
        got = pf.get(k)
        ok = got == 0.0
        print(f"  {'OK ' if ok else 'FAIL'}  {k:<28} -> {got!r:<20} must be 0.0 (3-leg ladder)")
        if not ok:
            fails.append(f"params {k} = {got!r}, must be 0.0 or the ladder is not 3-leg")

    # 4 ── ftmo_config behavioural fields must be UNCHANGED from pre-port.
    # The backtest imports this object; any edit rewrites the tested engine.
    print("\n  --- ftmo_config.py must stay at pre-port values (backtest imports it) ---")
    sys.path.insert(0, str(REPO))
    import ftmo_config
    for field, pre in (("risk_per_trade_pct", 0.6), ("daily_loss_halt_pct", 3.2),
                       ("total_dd_emergency_pct", 7.0), ("total_dd_warning_pct", 5.0),
                       ("max_concurrent_trades", 100)):
        got = getattr(ftmo_config.FIVEERS_CONFIG, field)
        ok = abs(float(got) - float(pre)) < 1e-9
        print(f"  {'OK ' if ok else 'FAIL'}  {field:<28} -> {got!r:<20} pre-port {pre!r}")
        if not ok:
            fails.append(f"ftmo_config.{field} = {got!r}, must stay {pre!r} — the backtest imports it")

    # 5 ── every env var the frozen config sets is read by live, or justified
    BTV = set(re.findall(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']', bt_src))
    # Live leest niet alles in main_live_bot.py. Het handelsuniversum komt uit
    # broker_config.get_tradable_symbols(), dus een variabele die daar gelezen
    # wordt is wel degelijk geport — alleen in een ander bestand. Zonder deze
    # regel meldde de controle OIL_ENABLE als niet-geport terwijl live er
    # aantoonbaar op reageert.
    LVV = set(re.findall(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']', LIVE.read_text()))
    _bc = REPO / "broker_config.py"
    if _bc.exists():
        LVV |= set(re.findall(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']', _bc.read_text()))
    BACKTEST_ONLY = {
        "TDD_WORST_CASE": "measurement convention; no live meaning",
        "TERMINAL_ON_BREACH": "harness control; no live meaning",
        "CFG_DAILY_WALL_PCT": "the broker enforces the real wall",
        "DDD_CLOSE_AT_TRIGGER": "simulator fill fidelity",
        "VOL_SIZE_ENABLE": "disabled in the frozen config (0)",
        "VOL_SIZE_MULT_HIGH": "inert while VOL_SIZE_ENABLE=0",
        "VOL_SIZE_MULT_LOW": "inert while VOL_SIZE_ENABLE=0",
        "SPX500_ENABLE": "read by config.py, which builds INDICES for both engines",
    }
    print("\n  --- env vars set by the config, read by backtest, not by live ---")
    for k in sorted(env):
        if k in BTV and k not in LVV:
            why = BACKTEST_ONLY.get(k)
            print(f"  {'OK ' if why else 'FAIL'}  {k:<28} {why or 'UNPORTED — no justification'}")
            if not why:
                fails.append(f"{k} is read by the backtest and not by live, with no justification")

    # 5b ── de kostenknoppen van de simulator staan uit.
    #
    # SLIPPAGE_PIPS, SLIPPAGE_MAP, COST_LIMIT_ENTRIES en GAP_FILLS zitten NIET in
    # de bevroren configuratie, dus stap 5 kijkt er niet naar — die loopt alleen
    # langs wat de configuratie zet. Precies daarom horen ze hier: een van deze
    # variabelen die per ongeluk in de shell blijft staan maakt een "bevroren"
    # run stilletjes een kostenrun, en het verschil is aan de uitvoer niet te
    # zien. Dat is exact de vorm van de zes stille configuratiebugs die dit
    # project al heeft opgeleverd.
    #
    # GAP_FILLS is de omgekeerde: die hoort juist AAN te staan (1 is de default),
    # want hij vult een gegapte stop op de open in plaats van op de trigger. Uit
    # zetten maakt de resultaten optimistischer, niet pessimistischer.
    print("\n  --- kostenknoppen van de simulator (moeten uit staan) ---")
    # De SHELL is niet de hele waarheid. challenge_score.run_step bouwt de
    # child-omgeving als dict(os.environ) + doe_harness.BASE_ENV, en die zet
    # SLIPPAGE_PIPS op 0,5. Alleen os.getenv opvragen gaf hier dus een groene
    # OK op een vraag die niet gesteld werd. Wat de backtest ECHT ziet is de
    # samengestelde waarde, dus die wordt hier getoond.
    _dh_env = getattr(getattr(w5.cs, "dh", None), "BASE_ENV", {}) or {}
    if "SLIPPAGE_PIPS" in _dh_env:
        print(f"  NOTE  {'SLIPPAGE_PIPS (harnas)':<28} -> {_dh_env['SLIPPAGE_PIPS']:<12} "
              f"doe_harness.BASE_ENV zet dit; elke run heeft deze opslag op "
              f"stop-entries en SL-exits")
        notes.append(
            f"SLIPPAGE_PIPS staat op {_dh_env['SLIPPAGE_PIPS']} in doe_harness.BASE_ENV, niet op 0. "
            "Elke 'kosteloze' meting in dit project bevat die opslag al op stop-entries en "
            "SL-exits. Limit-entries bleven wel frictieloos, en dat is waar deze bot "
            "binnenkomt, dus de ENTRY-spread was werkelijk ongemodelleerd.")
    for var, want, why in (
            ("SLIPPAGE_PIPS", "0", "vlakke opslag in pips (shell; zie NOTE hierboven)"),
            ("SLIPPAGE_MAP", "", "opslag per instrument"),
            ("COST_LIMIT_ENTRIES", "0", "rekent de spread ook op limit-fills"),
            ("SL_SLIPPAGE_OFF", "0", "zet de opslag op SL-exits uit"),
            ("SL_SLIPPAGE_PIPS", "", "vaste opslag op SL-exits"),
    ):
        got = os.getenv(var)
        ok_ = got is None or got.strip() in ("", "0", "false", "no", "off")
        print(f"  {'OK ' if ok_ else 'FAIL'}  {var:<28} -> {str(got):<12} {why}")
        if not ok_:
            fails.append(f"{var}={got} staat in de omgeving — dit is geen bevroren run")
    _gf = os.getenv("GAP_FILLS")
    ok_ = _gf is None or _gf.strip().lower() not in ("0", "false", "no", "off")
    print(f"  {'OK ' if ok_ else 'FAIL'}  {'GAP_FILLS':<28} -> {str(_gf):<12} "
          f"moet AAN: gegapte stops vullen op de open, niet op de trigger")
    if not ok_:
        fails.append("GAP_FILLS staat uit — gegapte stops vullen dan optimistisch")

    # 6 ── known deliberate divergences, reported not failed
    notes.append(
        "NACHTELIJKE DE-RISK draait live op de BROKERKLOK, de backtest op UTC. "
        "Live: NIGHTLY_DERISK_BROKER_HOUR=23 (EET/EEST), dus 21:00-21:29 UTC in de "
        "winter en 20:00-20:29 UTC in de zomer, en nooit binnen het rolvenster. "
        "De backtest houdt NIGHTLY_DERISK_HOUR in UTC aan, want zijn simulator "
        "kent geen spreadverbreding rond de rollover en zou van een uur verzetten "
        "alleen een andere bar zien, geen andere kosten — elk opgeslagen resultaat "
        "zou dan ongeldig worden zonder dat er iets beters voor terugkomt. "
        "W5_DERISK_UTC=1 zet live terug op het oude UTC-gedrag om backtests exact "
        "te reproduceren.")
    notes.append(
        "ROLVENSTER stond op drie plekken hardgecodeerd als 21:30-22:30 UTC. Dat "
        "klopt alleen in de winter: de broker draait op EET/EEST, dus zijn "
        "middernacht ligt op 22:00 UTC (winter) en 21:00 UTC (zomer). In de zomer "
        "vuurde de rolklem daardoor een uur te laat en dumpte de de-risk het boek "
        "precies op het rolmoment. Nu berekend vanuit de brokerklok.")

    # 6 ── DEPLOYMENT PRE-FLIGHT: environment, not code.
    # Everything above is verified with NO env set, on the principle that a
    # config depending on an operator exporting twenty variables correctly is
    # itself a failure mode. BROKER_TYPE is the one value where that principle
    # breaks down: unset, broker_config.py:291 resolves to forexcom_demo, so the
    # bot would run the validated config against a different broker entirely —
    # different symbols, spreads and account size. It must be set explicitly.
    print("\n  --- deployment pre-flight (environment, not code) ---")
    deploy = []

    bt_env = os.getenv("BROKER_TYPE")
    ok = bt_env is not None and bt_env.lower() in ("fiveers_live", "5ers_live", "5ers", "fiveers")
    print(f"  {'OK ' if ok else 'FAIL'}  {'BROKER_TYPE':<26} -> {str(bt_env):<22} "
          f"must be fiveers_live; unset = forexcom_demo")
    if not ok:
        deploy.append("BROKER_TYPE is not fiveers_live — the bot would trade the wrong broker")

    for var, why in (("MT5_LOGIN", "5ers account number"),
                     ("MT5_PASSWORD", "password"),
                     ("MT5_SERVER", "confirm against what 5ers issued")):
        val = os.getenv(var)
        present = bool(val) and val not in ("0", "")
        shown = "<set>" if (present and var == "MT5_PASSWORD") else (val or "<unset>")
        print(f"  {'OK ' if present else 'FAIL'}  {var:<26} -> {shown:<22} {why}")
        if not present:
            deploy.append(f"{var} is unset")

    try:
        import MetaTrader5  # noqa: F401
        print(f"  OK    {'MetaTrader5 package':<26} -> importable")
    except Exception:
        print(f"  FAIL  {'MetaTrader5 package':<26} -> NOT importable (Windows host)")
        deploy.append("MetaTrader5 not importable — run this on the Windows trading host")

    print("\n" + "=" * 74)
    if notes:
        print("DELIBERATE DIVERGENCES:")
        for n in notes:
            print(f"  * {n}")
    if fails:
        print(f"\nCONFIG: FAIL — {len(fails)} mismatch(es)")
        for f in fails:
            print(f"  - {f}")
        print("\nThe live bot would NOT trade the validated configuration.")
        sys.exit(1)
    print("\nCONFIG: PASS — every checked parameter resolves to the frozen baseline.")
    if deploy:
        print(f"\nDEPLOYMENT: NOT READY — {len(deploy)} item(s)")
        for d in deploy:
            print(f"  - {d}")
        print("\nExpected on a dev box; re-run on the Windows trading host.")
        sys.exit(2)
    print("DEPLOYMENT: pre-flight clear.")
    print("\nScope: configuration and environment only. This does NOT prove behavioural")
    print("equivalence — the live bot cannot be replayed against history. Demo first.")
    sys.exit(0)


if __name__ == "__main__":
    main()
