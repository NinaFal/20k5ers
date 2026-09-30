# 5%ers 2-step challenge — fastest safe pass settings (100k)

**Date:** 2026-07-03. **Objective:** pass Step 1 (+8%) then Step 2 (+5%) from a
fresh $100k as fast as possible WITHOUT hitting the 5% daily / 10% total wall.
This is a different metric from every prior backtest (which measured funded
long-run profit). Evaluated with `src/challenge_eval.py` across 32 quarterly
starts in the black-swan-free years (CHF excluded, cap=3, t39 skeleton).

**Metric note:** "days to +8%" is measured on **realized/closed profit** (the
conservative reading of the target); the 5%/10% walls are checked on equity by
the engine. If 5%ers counts the target on floating equity, real pass times are
*faster* than shown. The relative ranking across risk levels is robust either way.

## Result — speed vs safety by base risk

| base risk | pass rate | breach rate | median days to +8% | fastest | never <150d |
|----------:|----------:|------------:|-------------------:|--------:|------------:|
| 1.0% | 53% | **3%** | 87 | 18 | 14 |
| 1.5% | 62% | 6% | 67 | 9 | 10 |
| 2.0% | 75% | 9% | 56 | 7 | 5 |
| **2.5%** | **81%** | 9% | **51** | 6 | 4 |

Monotonic: higher risk → passes faster and more often, but higher breach rate.
Note 2.0%→2.5% adds NO breaches (same 3) while getting faster and passing more —
so within the risky band, 2.5% dominates 2.0%.

## The key safety insight — breaches cluster in a few toxic start windows

The breaches are NOT spread evenly; they concentrate on specific start dates:

| breached start | 1.0% | 1.5% | 2.0% | 2.5% |
|----------------|:----:|:----:|:----:|:----:|
| **2023-10-01** | 68d | 67d | **2d** | **2d** | ← breaches at EVERY risk |
| 2017-04-01 | – | 69d | 109d | – |
| 2016-10-01 | – | – | 113d | – |
| 2021-10-01 | – | – | – | 75d |
| 2024-07-01 | – | – | – | 11d |

**2023-10-01 is toxic at any risk** (a gap event in that window kills even the
1.0% run, and blows up in 2 days at ≥2.0%). Most of the residual breach risk is
"you started the challenge right before a bad event," not "risk is generically
too high." Avoiding a launch immediately before major known risk events removes
most of it.

## Recommendation

**Fastest safe setting: base risk 2.0–2.5%, t39/cap=3 skeleton, CHF excluded.**
- Median ~7–8 weeks to +8% (often 1–2 weeks in a clean trend), 75–81% of starts
  pass, breach ~9% but concentrated in pre-event windows.
- Step 2 (+5%) is strictly easier than Step 1 (+8%), so a config that passes
  Step 1 clears Step 2 sooner — Step 1 is the binding constraint.

**Maximum-safety setting (paid challenge, protect the fee): base risk 1.0–1.5%.**
- Breach rate 3–6%, but slower (median 67–87 days) and more starts stall.

**Two levers to make it both faster AND safer (next work):**
1. **Cut risk hard near the target.** `challenge_risk_manager.py` already has an
   ULTRA_SAFE "near target → minimal risk" mode; it is NOT wired into the
   backtest challenge path. Dropping to ~0.3% once at +6–7% would protect the
   near-win and cut the breaches that happen at 67–75 days (close to passing).
2. **Don't launch right before known risk events** (the 2023-10 window). A simple
   "no new challenge start within N days of high-impact calendar risk" rule.

## Caveats

- Config is funded-tuned, not challenge-tuned. A challenge-specific optimization
  (objective = minimize days-to-+8% subject to breach-rate ≈ 0 across starts)
  would likely beat these numbers. `challenge_eval.py` is the scorer for it.
- Realized-profit target basis is conservative (see metric note). An equity-based
  target would show faster passes / higher pass rates.

Reproduce: `uv run python3 backtest/src/challenge_eval.py`
