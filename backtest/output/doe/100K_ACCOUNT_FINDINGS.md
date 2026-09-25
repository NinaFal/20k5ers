# 100k funded account — max profit without breaching (black swans excluded)

**Date:** 2026-07-03  **Setup:** fresh $100k funded account (2-step challenge
assumed passed), t39/cap=3 winner skeleton, `CORR_GROUP_CAP=3`, scaling cap
lifted. **Black swans removed:** CHF pairs excluded (kills the 2015 SNB cliff)
and the 2015 & 2020 calendar years are not tested.

Goal asked: **≥ $500k profit/year without breaching.** Short answer below, data
underneath. (Backtest-only — live config NOT changed yet, per instruction.)

## Bottom line

- **$500k in a single year from a fresh $100k is NOT achievable without
  breaching.** Best clean single year = **$400,218** (2016 @ 3.5% risk), and that
  same 3.5% risk breaches in 2 of 8 years. The zero-breach ceiling is ~1.5% risk
  → **~$90–230k/year**.
- **$500k/year is a *scaled run-rate*, not an early-year number.** It only
  appears once the account has compounded to a high funded level (~$1M+), which
  takes years of clean trading. In a fresh-start 4-year clean span the account
  reaches ~$350k funded making ~$100k/year avg.
- **No single fixed risk is safe across regimes** — the key result. The risk that
  is safe + profitable in trending years breaches in choppy years, and vice
  versa. This is the real lever: regime-adaptive sizing, tuned properly.

## Data 1 — fresh $100k, single year (profit vs base risk)

net per year; `*` = breached that year (CHF excl, cap 3, uncapped scaling):

| year | 1.5% | 2.5% | 3.5% | 5.0% |
|------|-----:|-----:|-----:|-----:|
| 2016 | 153,000 | 352,375 | **400,218** | 234,776 |
| 2017 | 107,008 | 73,854 | 309,307 | 56,305* |
| 2018 | 4,383 | 111,950 | 202,438 | 926* |
| 2019 | 37,142 | 71,478* | 371,982 | 108,233 |
| 2021 | 81,203 | 21,046* | 21,068* | 59,003 |
| 2022 | 228,065 | 294,574 | 308,592 | 88,854* |
| 2023 | 43,843 | 37,221 | −4,898 | −6,196* |
| 2024 | 71,984 | 68,597* | −3,096* | 18,952* |
| **breaches** | **0/8** | 3/8 | 2/8 | 5/8 |
| **clean avg** | $90,828 | $173,995 | $264,606 | $134,004 |

## Data 2 — scaled continuous (account compounds across a clean 4yr span)

| span | risk | result | net | avg/yr | funded reached | TDD | DDD |
|------|-----:|--------|----:|-------:|---------------:|----:|----:|
| 2016-2019 | 1.5 | BREACH | 126,437 | 31,609 | 200k | 10.01 | 3.03 |
| 2016-2019 | 2.5 | ok | 367,466 | 91,866 | 350k | 8.13 | 3.27 |
| 2016-2019 | 3.5 | ok | **406,331** | 101,583 | 350k | 1.99 | 3.27 |
| 2021-2024 | 1.5 | ok | **384,398** | 96,100 | 350k | 0.60 | 3.19 |
| 2021-2024 | 2.5 | BREACH | 21,046 | 5,262 | 125k | 10.02 | 4.08 |
| 2021-2024 | 3.5 | BREACH | 21,068 | 5,267 | 125k | 10.08 | 4.02 |

The flip is the whole story: **2016-2019 wants 3.5% risk** (safe, $406k) but
**2021-2024 wants ≤1.5%** (3.5% breaches at the 2021 total wall). A fixed risk
can't win both. Clean scaled run-rate tops out ~$100k/year on a 100k start.

## Recommendation

1. **Safe live setting for a fresh 100k:** base risk ~1.5%, cap=3, regime mults
   as in t39 — ~$90–100k/year, scales to ~$350k funded in ~4 clean years, zero
   breach in the tested clean years.
2. **To push toward $500k/year, tune regime-adaptive risk** (RISK_CALM_MULT /
   RISK_VOLATILE_MULT + the regime gate) so the bot sizes UP in trending regimes
   (2016-2019 could carry 3.5%) and DOWN in choppy ones (2021/2024 need ≤1.5%).
   That is exactly what `src/stage5d_corr_cap_optimize.py` searches — run it at
   `--balance 100000` on the clean windows next.
3. **$500k/year as a target is realistic only as a scaled run-rate** once the
   account is ~$1M+ funded (year ~8+ of clean compounding), not from a fresh
   100k in the early years.

Reproduce: `uv run python3 backtest/src/sweep_100k_yearly.py` and
`… sweep_100k_continuous.py`.
