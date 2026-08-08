# W5 — final verdict

Config: **t65 + TDD tiers**, frozen at
`backtest/output/doe/wall5/BASELINE_t65_tdd_FROZEN.json`.
Account: 5ers classic — Step 1 8%, Step 2 5%, 5% daily wall, 10% total wall.

## Challenge economics — 200 out-of-sample starts

| outcome | count | rate |
|---|---|---|
| eventually passes | 191/200 | **95.5%** |
| loses the account | 9/200 | **4.5%** (95% CI 1.6–7.4%) |

Speed: median **19 days**. Within 20d 52%, **30d 64%**, 45d 71%, 75d 86%, 120d 93%.

Two independent samples, different seeds, no shared windows: 7 breaches and 2.
Fisher two-tailed p = 0.170 — one common rate, so pool them; neither number
stands alone.

**Stalls are not failures.** 5ers publish "Max Trading Period: Unlimited"; the
75-day horizon was a measurement choice. Re-run at 250 days, **all 13 stalled
starts passed, none breached** (median 111d, range 82–156). Earlier per-attempt
figures in this project counted stalls as losses and were pessimistic by ~6.5
points.

All nine breaches fall in **2019 or later**; zero in ~75 pre-2019 starts. The
second sample did not generate that hypothesis, so it corroborates rather than
restates it.

## Funded account

| start | period | trading profit | fixed payouts | worst daily | worst total |
|---|---|---|---|---|---|
| $50k | 2015–2025 | $3,622,756 | $672,000 | 4.09% | 6.33% |
| $100k | 2016–2025 | $3,400,723 | not computed | 4.73% | 4.27% |

Zero breaches in either. Once both reach the $500k cap they are bit-for-bit
identical — starting at $50k costs one extra year of climbing and nothing else.

**Cap at $500k.** $350k survives with an identical 4.73% worst day but earns
~$1M less; $150k and $250k both die in 2016.

## Actual risk per trade

`risk_per_trade_pct = 2.7` is a base, modified by a funded-level cap
(`main_live_bot_backtest.py:3331`) and a regime multiplier (`:3385`, ×1.45 in
calm):

| funded level | volatile | calm |
|---|---|---|
| below $300k — the challenge | 2.70% | **3.92%** |
| $300k–$1M — includes the cap | 0.60% | **0.87%** |

Total open risk is separately capped at 7% (`CFG_MAX_CUM_RISK`), so 3.92% is a
first-trade ceiling, not a per-trade norm.

## Known gaps — read before trading

1. **The live port is unverified.** All seven features are ported but the
   acceptance test has not run. Until the backtest reproduces these numbers from
   the live config sources, the deployed system is not the tested system.
2. **Costs are optimistic.** Every result used a flat **1.0 pip** spread across
   all instruments including XAU, XAG, NAS100 and crypto. Live costs are higher
   by an unmeasured margin.
3. **No margin model.** `csv_mt5_simulator.py:557-559` hardcodes `margin: 0.0`.
   Measured peak exposure is 69.4% of equity while climbing at 1:100 — and that
   assumes 1:100 on indices and metals too, which is unlikely.
4. **Nightly de-risk hour.** Tested at 22:00 UTC under a flat-spread model that
   cannot see the 21:30–22:30 rollover window. Live defaults to 21:00.

## Questions for 5ers

- Is the $10k fixed payout per milestone, monthly, or one-off? (~$500k/decade)
- Per-asset-class leverage — 1:100 on indices and metals too?
- Any aggregate exposure cap beyond the 50-lot per-position limit?
- Are withdrawals charged against the daily loss limit? The capped-year results
  assume they are not.
