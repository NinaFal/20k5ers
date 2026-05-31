# Optuna Drawdown-Recovery Sweep — Results

Window: 2015-01-01 .. 2019-12-31 | realistic execution (limit entries clean, stops slip) | TERMINAL_ON_BREACH=1

**50 trials, 41 survivors, 9 died.**

Objective: survival dominates (survivor = 1e6 + funded + withdrawn), then growth.

## Top 10 survivors by 5-year total value

| # | Funded | Withdrawn | Total | MaxTDD | WR | corr_cap | caution | warn | emerg | halt |
|---|--------|-----------|-------|--------|----|----------|---------|------|-------|------|
| 2 | $200,000 | $69,766 | $269,766 | 9.86% | 51.1% | 0 | 4.5@0.4 | 6.5@0.4 | 7.0@0.25 | 0 |
| 7 | $200,000 | $68,476 | $268,476 | 9.67% | 51.0% | 6 | 4.0@0.8500000000000001 | 4.5@0.30000000000000004 | 7.5@0.2 | 1 |
| 23 | $200,000 | $67,877 | $267,877 | 10.02% | 50.7% | 0 | 2.0@0.75 | 6.5@0.5 | 6.5@0.25 | 1 |
| 24 | $200,000 | $67,877 | $267,877 | 10.02% | 50.7% | 0 | 2.0@0.75 | 6.5@0.45 | 6.5@0.25 | 1 |
| 25 | $200,000 | $67,877 | $267,877 | 10.02% | 50.7% | 0 | 2.0@0.75 | 6.5@0.45 | 6.5@0.25 | 1 |
| 43 | $200,000 | $67,877 | $267,877 | 10.02% | 50.7% | 0 | 2.0@0.75 | 6.5@0.5 | 6.5@0.2 | 1 |
| 44 | $200,000 | $67,877 | $267,877 | 10.02% | 50.7% | 0 | 2.0@0.75 | 6.5@0.5 | 6.5@0.2 | 1 |
| 9 | $200,000 | $67,013 | $267,013 | 10.12% | 51.8% | 0 | 2.0@0.75 | 7.0@0.5 | 7.0@0.45000000000000007 | 1 |
| 26 | $200,000 | $67,003 | $267,003 | 10.07% | 51.3% | 0 | 5.0@0.7 | 6.5@0.45 | 6.5@0.25 | 1 |
| 15 | $200,000 | $66,840 | $266,840 | 10.07% | 52.2% | 6 | 4.0@0.9 | 4.0@0.35000000000000003 | 7.0@0.30000000000000004 | 1 |

## Key findings

- **41/50 configs survive** — survival is tunable, not luck.
- **Correlation cap OFF or loose wins**; tight caps (2) cut growth (~$95K vs ~$270K).
- **Throttle early but gently** (de-risk at ~4.5% TDD to 0.4%, not a panic halt) + **7% no-trade halt OFF** = best survivors.
- Best realistic 5-yr outcome ~$270K total value from $50K. Real, rule-compliant — not v4's bug-driven $4M.
- All ~51% WR: the sweep tunes survival/risk, NOT edge. Edge work (validated OOS) is the separate next track.

_NOTE: optimized on ONE 2015-2019 path; robustness across start dates still needs walk_forward.py._
