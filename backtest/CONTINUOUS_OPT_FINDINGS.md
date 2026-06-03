# Continuous-run optimization — findings

## Objective
Max profit, hard 0-breach gate, scored on the REAL continuous 2015-2024
compounding+scaling run (a breach terminates the account). Cold-start sums were
abandoned because they hide death (a config can be 0-breach cold-start yet die
in the continuous run after the account scales up and the high-water ratchets).

## Pipeline (optimize_continuous.py)
safety (60) -> tp (80) -> volrefine (24) -> validate. Each scored on the single
continuous 2015-2024 path with a wall-hugging penalty for survivors.

## Result: the single-path winner is OVERFIT
Locked config: vol 1.3/0.6, TP 0.9/1.7/2.4/3.4/4.7R, rungs 5.5/7.5/8.5 @ .45/.25/.25.

| Test | Result |
|------|--------|
| Continuous 2015->2024 | SURVIVED $1.86M, TDD 7.89%, 19 scalings |
| Shifted-start 2016->2024 | BREACH 2017-07 (TDD 9.99%) |
| Shifted-start 2017->2024 | BREACH 2017-11 (TDD 10.0%) |
| Cold-start 2017 | FAIL (TDD 10.0%) |
| Cold-start 2022 | FAIL (DDD 5.52%) |
| Cold-start (other 8 yrs) | OK |

## Lesson
Optimizing on a SINGLE continuous path curve-fits to that path. The profit
engine (sizing up in calm regimes, vol-low 1.3-1.7) is also the fragility: 2017
was an unusually calm year, so oversized positions breached a scaled-up account.
A config that survives ANY start date will earn materially less than the
single-path $1.9M. Next: re-optimize with a multi-start robust objective.
