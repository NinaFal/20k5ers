# E0 — breach anatomy: overnight exposure is the breach mechanism

**Date:** 2026-07-25. Branch `claude/3pct-challenge-rd`.

## Why this was run

Every prior 3%-wall search treated a breach as a scalar (`breach_rate`) and
tuned parameters against it. That mapped a speed/safety frontier but never
asked *what a losing day was actually made of*. Three possible anatomies imply
three different mechanisms:

| if breach days are mostly… | fix | structural? |
|---|---|---|
| positions held **overnight** | EOD/nightly de-risking | **yes** — removes risk not being paid for |
| **many small correlated** losses | exposure-aware portfolio cap | **yes** — count caps can't see correlation |
| **one big** loser | stop placement / single-trade sizing | no — frontier movement |

## Method

C1-wall3 skeleton, `fiveers_live`, 3% wall, run deliberately hot (risk 1.6%) so
breaches occur and can be dissected. Trade log kept (the scorer normally deletes
its temp dir) and every loss realized on the breach day attributed.

## Result — 6 dissectable breaches of 16 TRAIN starts

| start | breach day | day loss | trades | overnight | worst single | top corr group |
|---|---|---|---|---|---|---|
| 2016-10-01 | 2016-11-09 | $-3,551 | 4 | **73%** | 72% | USD_INVERSE 73% |
| 2018-01-01 | 2018-02-07 | $-3,054 | 5 | **100%** | 45% | METALS 51% |
| 2018-10-01 | 2018-10-19 | $-3,302 | 5 | **100%** | 49% | USD_MAJORS 51% |
| 2021-01-01 | 2021-01-27 | $-2,049 | 6 | **100%** | 46% | USD_INVERSE 46% |
| 2023-01-01 | 2023-01-03 | $-3,179 | 3 | **100%** | 74% | USD_MAJORS 74% |
| 2023-10-01 | 2023-11-01 | $-1,890 | 2 | **100%** | 86% | EUR_CROSSES 86% |

**Means across the 6 breaches:**

- overnight share of loss: **95.5%**
- worst single position's share: 62.1%
- top correlation group's share: 63.4%
- losing trades per breach: 4.2
- distinct correlation groups: 3.0

**Five of six breaches were 100% overnight.** Not one was primarily intraday.

## Consequence

This is the first of the three anatomies — the structural case. Position-count
caps (`CORR_GROUP_CAP`, `MAX_TOTAL_POSITIONS`) bound how many trades are open;
they do not bound how much gap risk rides unattended through the night. That is
why ~2,700 backtests of sizing and count levers could not escape the frontier:
none of them addressed the actual mechanism.

Acted on via the `NIGHTLY_DERISK` lever — see `E2_FINDINGS.md`.
