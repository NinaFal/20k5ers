# W5 — final verdict

> **⚠ ONDER HERVALIDATIE — cijfers hieronder zijn van vóór de datawissel.**
> De cryptodata is vervangen (Yahoo-uurbars vanaf 2023 → Binance M15 vanaf
> 2017/2018, vier symbolen in plaats van twee). Crypto handelde 24 keer in de
> hele backtest; nu doet het mee in elk jaar. Een rooktest op 2021 gaf 81
> cryptotrades en een slechtste dag van 4,92% tegen een muur van 5,0%.
> Elk getal over slaagkans, breaches, doorlooptijd en drawdown in dit document
> is gemeten zonder die data en moet als voorlopig gelezen worden.
> Zie `W5_DATA_INTEGRITY.md`; hermeting loopt via `w5_revalidate.py`.

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
| $50k | 2015–2025 | $3,622,756 | $600k–$1,150,000 | 4.09% | 6.33% |
| $100k | 2016–2025 | $3,400,723 | not computed | 4.73% | 4.27% |

The fixed-payout figure was **$672,000 and that was wrong** — the model paid
$10k per withdrawal event, so the answer tracked the simulator's payout cadence
rather than the calendar. 5ers confirmed $10,000 **per month** once the account
is at the 500K level. The account reaches 500K in June 2016, giving 115
calendar months to end-2025: $1,150,000 if the payment is unconditional,
$600,000 if it requires a profitable month. Working figure **$120,000/year at
the cap**. Detail and per-year breakdown in `5ERS_ANSWERS.md`.

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
3. **No margin model, but now measured.** `csv_mt5_simulator.py:557-559` still
   hardcodes `margin: 0.0`, so the backtest can open a book a broker would
   refuse. Re-measured at the real 5ers leverages (FX 1:100, indices/metals
   1:25, commodities 1:5, crypto 1:2) over 2019 and 2023, margin peaks at
   **28.6% of balance during the challenge phase** and 72.4% at the highest
   point of a full year after the account has grown. No single position exceeds
   22%. Margin does not bind for this configuration. It is two years of eleven,
   and the measurement must be redone if `MAX_TOTAL_POSITIONS`, `CORR_GROUP_CAP`
   or `risk_per_trade_pct` go up.
4. **Nightly de-risk hour.** Tested at 22:00 UTC under a flat-spread model that
   cannot see the 21:30–22:30 rollover window. Live defaults to 21:00.

## Questions for 5ers — answered 2026-08-23

All four came back; full text and consequences in `5ERS_ANSWERS.md`.

- **Fixed payout** — $10,000 per month at the 500K level. Corrected above.
- **Leverage** — FX 1:100, indices and metals 1:25, commodities 1:5, crypto
  1:2. Prompted the margin re-measurement in gap 3.
- **Aggregate exposure cap** — none. "As many positions as you wish as long as
  the account leverage allows you"; margin is the only ceiling.
- **Withdrawals and the daily limit** — not charged as a loss. 5ers resets the
  baseline to the post-withdrawal balance; the model keeps the pre-withdrawal
  `day_start_equity` and nets the payout out of the numerator. The two differ
  by about $1,650 of allowance on payout days at the cap, against a worst
  observed day of 4.09%. No change needed.

Still open: whether the $10,000 is unconditional or tied to a profitable month
($1.15M against $600k over the decade), and whether the 50-lot per-position
limit the bot enforces is real — support did not mention it and measured sizes
top out at 16-35 lots.
