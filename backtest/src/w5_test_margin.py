#!/usr/bin/env python3
"""Controleert _w5_margin_per_lot tegen de formule van 5ers support:
       Max Lot = (Balance x Leverage) / (Contract Size x Price)
   omgekeerd:  marge per lot = (Contract Size x Price) / Leverage
   met voor FX de notional in de basisvaluta, niet in de quote."""
import ast, sys, types, os
src = open(__import__('pathlib').Path(__file__).resolve().parents[2] / 'main_live_bot.py').read()
tree = ast.parse(src)
keep = []
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name.startswith("_w5_"):
        keep.append(n)
    elif isinstance(n, ast.Assign) and any(
            getattr(t, "id", "").startswith("W5_") for t in n.targets):
        keep.append(n)
mod = ast.Module(body=keep, type_ignores=[])
ns = {"os": os}
exec(compile(mod, "<w5>", "exec"), ns)
mpl = ns["_w5_margin_per_lot"]

# (symbool, prijs, verwachte marge per lot, waarom)
CASES = [
    ("EUR_USD",    1.10,   1_100.0, "FX quote=USD: 100k x 1,10 / 100"),
    ("USD_JPY",  110.00,   1_000.0, "FX base=USD: notional is 100k, NIET 100k x 110"),
    ("GBP_USD",    1.30,   1_300.0, "FX quote=USD"),
    ("XAU_USD", 2000.00,   8_000.0, "metaal: 100 oz x 2000 / 25"),
    ("XAG_USD",   25.00,   5_000.0, "metaal: 5000 oz x 25 / 25"),
    ("NAS100_USD", 20000.0,  800.0, "index: 1 x 20000 / 25"),
    ("BTC_USD",  60000.0, 30_000.0, "crypto: 1 x 60000 / 2"),
    ("XTI_USD",   75.00,   1_500.0, "commodity: 100 x 75 / 5"),
]
bad = 0
print(f"{'symbool':<12}{'prijs':>10}{'berekend':>12}{'verwacht':>12}  waarom")
for sym, price, exp, why in CASES:
    got = mpl(sym, price)
    ok = abs(got - exp) < 0.01
    bad += not ok
    print(f"{sym:<12}{price:>10,.2f}{got:>12,.0f}{exp:>12,.0f}  "
          f"{'' if ok else 'FOUT! '}{why}")

# Crossparen: de notional volgt de BASISvaluta, niet de genoteerde prijs.
for sym, price, exp, why in (
    ("EUR_GBP", 0.86, 1_100.0, "EUR-notional (1,10), niet 100k x 0,86 = $860"),
    ("GBP_JPY", 145.0, 1_280.0, "GBP-notional (1,28), niet 100k x 145 = $145.000"),
    ("AUD_CAD", 0.90,   680.0, "AUD-notional (0,68)"),
):
    got = mpl(sym, price)
    ok = abs(got - exp) < 1
    bad += not ok
    print(f"{sym:<12}{price:>10,.2f}{got:>12,.0f}{exp:>12,.0f}  "
          f"{'' if ok else 'FOUT! '}{why}")

# Sanity: de 5ers-formule andersom, max lot op $50.000.
print(f"\nMax lot op een balans van $50.000 (formule van 5ers):")
for sym, price, _, _ in CASES:
    print(f"  {sym:<12}{50_000 / mpl(sym, price):>10,.1f} lots")
sys.exit(1 if bad else 0)
