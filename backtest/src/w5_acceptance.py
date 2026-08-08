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
    LVV = set(re.findall(r'os\.getenv\(\s*["\']([A-Z0-9_]+)["\']', LIVE.read_text()))
    BACKTEST_ONLY = {
        "TDD_WORST_CASE": "measurement convention; no live meaning",
        "TERMINAL_ON_BREACH": "harness control; no live meaning",
        "CFG_DAILY_WALL_PCT": "the broker enforces the real wall",
        "DDD_CLOSE_AT_TRIGGER": "simulator fill fidelity",
        "VOL_SIZE_ENABLE": "disabled in the frozen config (0)",
        "VOL_SIZE_MULT_HIGH": "inert while VOL_SIZE_ENABLE=0",
        "VOL_SIZE_MULT_LOW": "inert while VOL_SIZE_ENABLE=0",
    }
    print("\n  --- env vars set by the config, read by backtest, not by live ---")
    for k in sorted(env):
        if k in BTV and k not in LVV:
            why = BACKTEST_ONLY.get(k)
            print(f"  {'OK ' if why else 'FAIL'}  {k:<28} {why or 'UNPORTED — no justification'}")
            if not why:
                fails.append(f"{k} is read by the backtest and not by live, with no justification")

    # 6 ── known deliberate divergences, reported not failed
    notes.append("NIGHTLY_DERISK_HOUR: live defaults 21, frozen config says 22. "
                 "Deliberate — 22:00 sits inside the 21:30-22:30 rollover window "
                 "where spreads widen 5-50x, which the flat-spread simulator "
                 "cannot see. Set 22 to reproduce backtest results exactly.")

    print("\n" + "=" * 74)
    if notes:
        print("DELIBERATE DIVERGENCES:")
        for n in notes:
            print(f"  * {n}")
    if fails:
        print(f"\nRESULT: FAIL — {len(fails)} mismatch(es)")
        for f in fails:
            print(f"  - {f}")
        print("\nThe live bot would NOT trade the validated configuration.")
        sys.exit(1)
    print("\nRESULT: PASS — every checked parameter resolves to the frozen baseline.")
    print("Scope: configuration only. This does NOT prove behavioural equivalence;")
    print("the live bot cannot be replayed against history. Demo-trade before a fee.")
    sys.exit(0)


if __name__ == "__main__":
    main()
