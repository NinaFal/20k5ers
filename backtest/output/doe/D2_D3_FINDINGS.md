# D2 + D3 findings — and a baseline correction

**Date:** 2026-07-22. Branch `claude/3pct-challenge-rd`.

## Baseline correction (important)

D2/D3 run on the NEW, live-account-faithful universe (fiveers_live profile:
metals + NAS100 unlocked, 3 bleeder symbols excluded). On THAT universe the
true floor is the D1 screen's `expanded_no_bleed`:
**score −56.93, 1/16 completes (day 68), 6.2% breach** — NOT the old
forex-only 5.73/0%-breach figure. Early reporting compared D2 against the old
floor and wrongly called it "negative"; corrected below.

## D2 (cushion ratchet), 120 trials — MODEST REAL WIN on safety

Best: **trial 117** — mild ratchet (T 3.0/3.75/5.75 → M 1.1/1.2/1.4,
risk 1.0%, cum 2.5, DD_OFF 1.5):

| | floor (no ratchet) | D2 t117 |
|---|---|---|
| completions ≤60d | 1/16 (day 68*) | 1/16 (day 68) |
| breach rate | **6.2%** | **0.0%** |

*floor's completion counted at day 68 via median; same single start (2021-01).

The mild cushion eliminated the one breach on this universe without losing the
completion → **trial 117 is currently the best-validated config for the real
(3% wall, fiveers_live) account.** Speed unchanged: attempts still rarely bank
enough for the ratchet to matter (p30 = 0 everywhere).

## D3 (trend-quality ADX controller), 120 trials — negative on speed

Best score −0.79 (risk 1.2, cum 3.5, ADX 24→34, mult 0.6→1.0): 0% breach but
**p60 = 0** — the chop-throttling that removes breaches also removes the one
completing window. No D3 trial achieved 0% breach AND a ≤60d completion.
The controller works as a *brake*, not an accelerator.

## Tally on the faithful universe

**Configs with 0% breach AND any ≤60d completion: exactly one — D2 trial117.**
(The 5-7 "hits" listed from earlier searches were all measured on the old
forex-only universe and do not transfer.)

## Next: D2+D3 combined search

The two levers are complementary brakes/boosters on different halves of the
attempt (trend controller shapes the front, cushion the back) and each helped
the breach side individually. A joint search (seeded from t117 and the D3
best) is the last in-scope parameter mechanism before D4 (event calendar) and
the final Phase-3 assessment.
