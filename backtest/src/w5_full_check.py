#!/usr/bin/env python3
"""
VOLLEDIGE vergelijking backtest <-> live. Alle lagen, niet alleen env-vars.

Eerdere controles keken telkens naar één as en misten daardoor iets: de
env-var-scan vond de niet-geporte halt-verkrapping niet (die is niet
env-gestuurd), en de methode-diff vond de gedeelde ftmo_config niet. Dit
controleert alle vijf lagen tegelijk.

VERWACHTE verschillen worden apart gerapporteerd en tellen niet als fout:
live haalt koersen uit MT5 en de backtest uit opgeslagen CSV's, dus alles rond
dataverwerving, orderplaatsing en herstel-na-crash hoort te verschillen.

Draaien:  uv run python3 backtest/src/w5_full_check.py
"""
import ast, importlib.util, json, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
_w = importlib.util.spec_from_file_location("w5", str(HERE / "w5_common.py"))
w5 = importlib.util.module_from_spec(_w); _w.loader.exec_module(w5)
LIVE, BT = REPO / "main_live_bot.py", HERE / "main_live_bot_backtest.py"

# Methoden die HOREN te verschillen: dataverwerving, orderplaatsing, herstel.
EXPECTED_LIVE_ONLY = {
    "_calculate_mid_equity", "_check_missed_tps_on_startup", "_dedup_and_rescale_mt5_orders",
    "_detect_fiveers_scaling", "_ensure_ddd_thread_alive", "_fix_zero_entry_prices",
    "_load_scan_state", "_place_rollover_queued_setups", "_recover_orphaned_pending_orders",
    "_recover_orphaned_positions", "_save_scan_state", "_sync_tp_levels_to_current_params",
    "_update_ticket_after_partial_close", "get_early_close_utc",
    "handle_holiday_position_closing", "is_holiday_affected_instrument", "is_market_holiday",
}
EXPECTED_BT_ONLY = {
    "_base_ticket", "_hit_priority", "_mark_mfe_mae", "_median", "_percentile",
    "_register_breach", "record_tdd", "run_backtest", "set_simulator_for_logging",
    "formatTime", "_positions_count", "_is_rollover_window", "_is_news_blackout",
    "_news_affected_currencies", "_protection_block", "_total_open_risk_usd",
    "_regime_risk_multiplier", "_dynamic_halt_pct",     # live heeft _w5_-equivalenten
    "_vol_size_multiplier", "_trend_risk_multiplier", "_params_for_symbol",
    "handle_max_hold",                                   # env-uit in deze config
}


def methods(p):
    return {n.name for n in ast.walk(ast.parse(p.read_text()))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def envvars(p):
    return set(re.findall(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']', p.read_text()))


def main():
    frozen = json.loads((w5.W5_DIR / "BASELINE_t65_tdd_FROZEN.json").read_text())
    eff = {**w5.cs.dh.BASE_ENV, **w5.BASE_ENV, **frozen["env"]}
    problems, expected = [], []

    print("=" * 72)
    print("VOLLEDIGE CHECK — backtest vs live")
    print("=" * 72)

    # LAAG 1: params/current_params.json
    print("\n[1] params/current_params.json — gedeeld bestand")
    pf = json.loads((REPO / "params" / "current_params.json").read_text())["parameters"]
    optp = {**w5.cs.dh.BASE_TP, **{**w5.BASE_TP, **frozen["tp"]}}
    bt_reads = "current_params" in BT.read_text()
    lv_reads = "current_params" in LIVE.read_text()
    print(f"    gelezen door backtest: {bt_reads} | door live: {lv_reads}")
    if not (bt_reads and lv_reads):
        problems.append("current_params.json wordt niet door beide engines gelezen")
    from_file = sorted(k for k in pf if k not in optp)
    print(f"    {len(pf)} params; {len(pf)-len(from_file)} overschreven door OPT_PARAMS "
          f"in de backtest, {len(from_file)} rechtstreeks uit het bestand:")
    for k in from_file:
        print(f"       {k} = {pf[k]}")
    print("    -> die laatste 12 sturen BEIDE engines direct aan.")

    # LAAG 2: env-vars
    print("\n[2] Environment-variabelen")
    BTV, LVV = envvars(BT), envvars(LIVE)
    JUSTIFIED = {"TDD_WORST_CASE", "TERMINAL_ON_BREACH", "CFG_DAILY_WALL_PCT",
                 "DDD_CLOSE_AT_TRIGGER", "VOL_SIZE_ENABLE", "VOL_SIZE_MULT_HIGH",
                 "VOL_SIZE_MULT_LOW"}
    gaps = [k for k in sorted(eff) if k in BTV and k not in LVV]
    for k in gaps:
        if k in JUSTIFIED:
            expected.append(f"env {k} — alleen backtest (meting/uit)")
        else:
            problems.append(f"env {k}={eff[k]} wel in backtest, niet in live")
    print(f"    {len(gaps)} alleen-backtest, waarvan {len(gaps)-len([g for g in gaps if g in JUSTIFIED])} onverklaard")

    # LAAG 3: methoden
    print("\n[3] Methoden")
    MB, ML = methods(BT), methods(LIVE)
    for m in sorted(MB - ML):
        (expected if m in EXPECTED_BT_ONLY else problems).append(
            f"methode {m} — alleen backtest" + ("" if m in EXPECTED_BT_ONLY else " (ONVERKLAARD)"))
    for m in sorted(ML - MB):
        if m in EXPECTED_LIVE_ONLY or m.startswith("_w5_"):
            expected.append(f"methode {m} — alleen live")
        else:
            problems.append(f"methode {m} — alleen live (ONVERKLAARD)")
    print(f"    backtest-only {len(MB-ML)} | live-only {len(ML-MB)}")

    # LAAG 4: gedeelde config-objecten
    print("\n[4] Gedeelde config-objecten (ftmo_config)")
    sys.path.insert(0, str(REPO))
    import ftmo_config
    shared_ok = True
    for f, pre in (("risk_per_trade_pct", 0.6), ("daily_loss_halt_pct", 3.2),
                   ("total_dd_emergency_pct", 7.0), ("total_dd_warning_pct", 5.0),
                   ("max_concurrent_trades", 100)):
        got = getattr(ftmo_config.FIVEERS_CONFIG, f)
        if abs(float(got) - float(pre)) > 1e-9:
            problems.append(f"ftmo_config.{f}={got}, moet {pre} blijven (backtest importeert dit)")
            shared_ok = False
    print(f"    5 gedragsvelden op pre-port waarden: {'OK' if shared_ok else 'AFGEWEKEN'}")

    # LAAG 5: databron — hoort te verschillen
    print("\n[5] Databron")
    print("    backtest: opgeslagen M15 CSV's via csv_mt5_simulator")
    print("    live:     MT5Client (tradr.mt5.client) tegen de 5ers-server")
    expected.append("databron MT5 vs CSV — fundamenteel, niet te uniformeren")

    print("\n" + "=" * 72)
    print(f"VERWACHTE VERSCHILLEN: {len(expected)}")
    for e in expected:
        print(f"    - {e}")
    if problems:
        print(f"\nONVERKLAARDE VERSCHILLEN: {len(problems)}")
        for p in problems:
            print(f"    ! {p}")
        print("\nRESULTAAT: NIET GELIJK")
        sys.exit(1)
    print("\nONVERKLAARDE VERSCHILLEN: 0")
    print("RESULTAAT: alle lagen komen overeen of zijn verklaard.")
    print("\nLet op: dit vergelijkt CONFIGURATIE en STRUCTUUR. Het bewijst niet dat")
    print("de code zich identiek GEDRAAGT — daarvoor is de demo-periode nodig.")
    sys.exit(0)


if __name__ == "__main__":
    main()
