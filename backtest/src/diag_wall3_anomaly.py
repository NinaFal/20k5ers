#!/usr/bin/env python3
"""Isolate the 0.4%-risk breach found by wall3pct_risk_probe.py: which start,
what caused it (regime mult stacking vs corr cap vs a single bad trade),
under the corrected 3% wall."""
import importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("probe", str(HERE / "wall3pct_risk_probe.py"))
p = importlib.util.module_from_spec(_s); _s.loader.exec_module(p)

for start in p.PROBE_STARTS:
    tp = {**p.ENTRY, **p.BANK_FAST, "risk_per_trade_pct": 0.4}
    r = p.cs.run_step(p.SKELETON, tp, start, p.cs.STEP1_TARGET, 30)
    tag = "BREACH" if r["breach"] else ("PASS" if r["pass_day"] is not None else "slow")
    print(f"{start}: {tag}  breach_day={r.get('breach_day')}  trades={r.get('trades')}")
