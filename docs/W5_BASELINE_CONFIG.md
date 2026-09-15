# BASELINE CONFIG — t65 + TDD tiers (FROZEN)

> **⚠ ONDER HERVALIDATIE — cijfers hieronder zijn van vóór de datawissel.**
> De cryptodata is vervangen (Yahoo-uurbars vanaf 2023 → Binance M15 vanaf
> 2017/2018, vier symbolen in plaats van twee). Crypto handelde 24 keer in de
> hele backtest; nu doet het mee in elk jaar. Een rooktest op 2021 gaf 81
> cryptotrades en een slechtste dag van 4,92% tegen een muur van 5,0%.
> Elk getal over slaagkans, breaches, doorlooptijd en drawdown in dit document
> is gemeten zonder die data en moet als voorlopig gelezen worden.
> Zie `W5_DATA_INTEGRITY.md`; hermeting loopt via `w5_revalidate.py`.

This is the confirmed baseline. Frozen copy:
`backtest/output/doe/wall5/BASELINE_t65_tdd_FROZEN.json`, which is immutable —
future optimisation rounds write to `current_best.json` and must never touch it.

Identity: **nightly-stage trial 65**, plus the TDD-tier tightening from the 2025
rescue (variant `halt2.50+tdd`). Account: 5ers **classic**, Step 1 8%, Step 2 5%,
**5% daily wall**, **10% total wall**, 3 profitable days at 0.5% of balance.

---

## 1. Settings

### Environment

| Variable | Value |
|---|---|
| `RISK_VOLATILE_MULT` | `1.0` |
| `CFG_MAX_CUM_RISK` | `7.0` |
| `CORR_GROUP_CAP` | `6` |
| `MAX_TOTAL_POSITIONS` | `20` |
| `NIGHTLY_DERISK` | `1`  ← master gate; whole nightly block is dead without it |
| `NIGHTLY_DERISK_HOUR` | `22` |
| `NIGHTLY_MAX_PER_GROUP` | `0` |
| `NIGHTLY_MAX_TOTAL` | `0` |
| `NIGHTLY_R_CLOSE_LOSING` | `0.25` |
| `NIGHTLY_R_NEW` | `0.5` |
| `NIGHTLY_REDUCE_PCT` | `0.75` |
| `CFG_DAILY_HALT_PCT` | `2.50` |
| `TDD_WALL_SAFETY` | `5.5` |
| `CFG_TDD_CAUTION_PCT` | `1.5` |
| `CFG_RISK_CAUTIOUS` | `0.4` |
| `CFG_TDD_WARNING_PCT` | `2.5` |
| `CFG_RISK_CONSERVATIVE` | `0.25` |
| `CFG_DAILY_WALL_PCT` | `5.0` |
| `FIVEERS_MAX_SCALE` | `500000` |
| `DDD_CLOSE_AT_TRIGGER` | `1` |
| `TDD_WORST_CASE` | `1` (measurement only — no live equivalent) |
| `EXCLUDE_SYMBOLS` | `XRP_USD,ADA_USD,BTC_USD,ETH_USD` — see §3b |
| `BROKER_TYPE` | `fiveers_live` |

### Trade parameters

| Parameter | Value |
|---|---|
| `risk_per_trade_pct` | **2.7** (base — see §2b for what is actually risked) |
| `tp1_r_multiple` / `tp1_close_pct` | 0.65 / 0.25 |
| `tp2_r_multiple` / `tp2_close_pct` | 1.85 / 0.60 |
| `tp3_r_multiple` / `tp3_close_pct` | 2.75 / 0.15 |
| `sl_after_tp1_r` | −0.10 |
| `sl_after_tp2_r` | 0.90 |
| `sl_after_tp3_r` | 1.70 |
| all six entry filters | disabled |

---

## 3b. Why crypto is switched off

Three groups are excluded, for three different reasons.

| symbols | reason | reversible |
|---|---|---|
| XRP_USD, ADA_USD | 5ers does not offer them | no |
| BTC_USD, ETH_USD | measured: no profit, more daily drawdown | **yes — a judgment call** |

**AUD_NZD, EUR_NZD and AUD_JPY were excluded and are now back in.** They were
dropped as "structurally net-negative in both halves". That verdict does not
survive remeasurement on the current data and engine — in particular on an
engine where the 50-lot cap actually applies, which it did not when the original
exclusion was decided. Measured with the `fxpairs` arm over eleven years:

| $50k, 2015-2025 | with the three pairs | without |
|---|---|---|
| withdrawn + closing balance | **$4,550,460** | $4,107,981 |
| 2017-2025 only, both at the $500k cap | **$3,464,804** | $3,104,669 |
| profit per trade, 2017+ | **$335** | $318 |
| worst single day | 4.19% | 4.09% |
| average worst day, 2017+ | 2.57% | **2.39%** |
| worst total drawdown, 2017+ | 4.60% | **3.60%** |

+10.8% over the decade, and the per-trade edge is genuine rather than an artefact
of trading more — but it is **not** a free improvement. Daily drawdown is higher
in 8 of the 9 comparable years, and peak total drawdown over 2017+ goes from
3.60% to 4.60%. The trade was taken deliberately: more profit for more daily
drawdown, with room left to the 5% wall.

Two things worth not misreading. Over the full eleven years the arm shows worst
total drawdown of 4.60% against 6.33%, which looks like an improvement — but
that 6.33% comes from 2015, where the arms sat at different funded levels and
are not comparable. And there is no pattern of the pairs helping in bad years:
correlation between how poor the reference year was and how much they added is
+0.22, essentially nothing. Six years gain roughly $50,000 and three gain
nothing; that is on-or-off behaviour, not a regime effect.

The crypto decision rests on a paired eleven-year run, both arms on the same
engine, differing only in whether BTC and ETH are excluded
(`w5_decade_crypto.py`, arms `crypto` and `nocrypto`):

| $50k, 2015-2025 | with crypto | without |
|---|---|---|
| withdrawn + closing balance | $4,069,877 | **$4,107,981** |
| worst day (5% wall) | 4.09% | 4.09% |
| worst total (10% wall) | 6.33% | 6.33% |
| trades | 11,918 | 11,843 |
| profit per trade | $296 | **$301** |

Crypto costs **0.93% over the decade** — noise, but it earns nothing either,
across 300 trades.

**Read the per-year table with care.** Most yearly gaps land within a few
percent of exactly one $50,000 payout (2017 +1.10, 2019 −1.01, 2020 +1.09,
2022 +1.08, 2023 −1.00, 2024 −1.02, 2025 −1.08). At the cap a payout fires the
moment balance touches +10%; whether that lands on 28 December or 3 January
moves a whole block between years without anything being earned or lost. Only
withdrawn **plus** closing balance is meaningful.

What is consistent is drawdown. Across the nine years crypto actually trades in:

| | with | without |
|---|---|---|
| average worst day | 2.70% | **2.39%** |
| worse in | **5 of 9 years** | |

That is +0.32 points on a 5% wall. Total drawdown moves the other way (1.70%
against 1.97%), so the effect is not uniformly bad.

**This is a thin argument on its own** — nine years and a 5-4 split support no
statistical claim, and 0.93% is inside the noise of any run. What tips it is
leverage: 5ers gives crypto 1:2 against 1:100 for FX, so a single ETH position
consumed 21.7% of the margin ceiling where an FX position takes about 2%
(`5ERS_ANSWERS.md` §3). Paying that for a return the measurement cannot find is
the reason it is off.

Both arms survived all eleven years with no wall touched, and in both the worst
day and worst total come from 2015, where neither trades crypto.

**To turn it back on:** remove `BTC_USD,ETH_USD` from `EXCLUDE_SYMBOLS` in
`backtest/src/w5_common.py` and the `_w5_excluded_symbols` default in
`main_live_bot.py`, regenerate `deploy/start_live.bat` with `w5_gen_env.py`, and
rerun both arms. The data stays in `data/ohlcv/` precisely so this stays a one
-line change; the XRP and ADA files were moved to `_quarantine` instead, because
those are not coming back.

## 2b. ACTUAL risk per trade — not 2.7%

`risk_per_trade_pct = 2.7` is a base that two mechanisms then modify.

**A hard cap by funded level** (`main_live_bot_backtest.py:3331`):

```python
if   funded_level >= 2_000_000: base_risk = min(base_risk, 0.25)
elif funded_level >= 1_000_000: base_risk = min(base_risk, 0.40)
elif funded_level >=   300_000: base_risk = min(base_risk, 0.60)
```

**A regime multiplier** (`:3385`, `risk_pct = risk_pct * _rm`): ×1.45 when
ATR(14)/ATR(50) is below `fib_vol_ratio_threshold` (**1.05** in this config),
×1.0 otherwise. Collapses to ×1.0 past 5% drawdown.

| funded level | volatile | calm (×1.45) |
|---|---|---|
| below $300k — challenge and early climb | 2.70% | **3.92%** |
| $300k–$1M — includes the $500k cap | 0.60% | **0.87%** |
| $1M+ | 0.40% | 0.58% |
| $2M+ | 0.25% | 0.36% |

**At the $500k cap the account risks 0.6–0.87% per trade, roughly 4.5x less than
during the challenge.** This is very likely the dominant reason capped years run
1.78-3.42% worst daily drawdown against 4.73% while climbing.

An earlier draft attributed that gap mainly to scaling-rung crossings — balance
jumping to the next funded level mid-day while `day_start_equity`, the daily
drawdown denominator, stayed anchored to the pre-jump figure. That effect is
real and was measured at ~1.8 points across three paired years, but **this cap
is the larger cause and was missed.** It also explains the margin profile: 69%
usage climbing at 3.9% risk, 12.6% at the cap at 0.87%.

Practical consequence: the challenge is where the real risk sits. Once funded
and scaled the bot becomes dramatically more conservative without being told to.

## 2. What it does — measured

**Challenge, 100 fresh random starts 2015-2025 (out of sample):**

| outcome | count |
|---|---|
| passed both steps | **86** |
| breached — account lost | **7** |
| stalled — fee lost, account intact | 7 |

Median **16 days**, fastest 5, slowest 115. Within 20d 58, **within 30d 69**,
within 40d 74, within 50d 76.

**Funded account, continuous, level carried forward** (both survived, zero
breaches, under strict intrabar marking):

| start | years | trading profit | fixed payouts | worst daily | worst total |
|---|---|---|---|---|---|
| $100k, 2016-2025 | 10 | $3,400,723 | not computed | 4.73% | 4.27% |
| $50k, 2015-2025 | 11 | $3,622,756 | $600k-$1.15M | 4.09% | 6.33% |

The fixed-payout column was $672,000 and that figure was wrong — see
`5ERS_ANSWERS.md` §2. 5ers pays $10,000 **per month** at the 500K level, not
per withdrawal; 115 months to end-2025 gives $1,150,000 unconditional or
$600,000 if a profitable month is required. Working figure $120,000/year.

Once both reach the $500k cap they are **bit-for-bit identical**; starting at
$50k costs one extra year of climbing and nothing else.

**Scaling cap:** keep it at **$500k**. $350k survives with an identical 4.73%
worst day but earns ~$1M less; $150k and $250k both die in 2016.

---

## 3. Position sizing and the 50-lot cap

**There is no per-trade risk limit at 5ers.** Confirmed by the account holder
and consistent with the5ers' published rules, which state the 5% daily wall, the
10% total wall and 1:100 leverage, and say nothing about risk per trade. The
`ftmo_config.py` guard that rejected anything above 2.5% was self-imposed and
had no basis; it is raised to 5.0 so it cannot reject the validated 2.7%
configuration. Changing an assertion is safe while the backtest runs — it either
raises or does not — unlike the behavioural fields in that file, which the
backtest imports and which must never be edited.

**The real constraint on size is margin, and 5ers has now confirmed the
leverages:** FX 1:100, indices and metals 1:25, commodities 1:5, crypto 1:2.
Every earlier figure in this document assumed 1:100 on everything and was
therefore too low. Margin per lot at the real schedule:

| instrument | class | leverage | notional | margin/lot |
|---|---|---|---|---|
| EUR_USD | FX | 1:100 | $110,000 | $1,100 |
| USD_JPY | FX | 1:100 | $100,000 | $1,000 |
| XAU_USD | metal | 1:25 | $200,000 | $8,000 |
| XAG_USD | metal | 1:25 | $125,000 | $5,000 |
| NAS100_USD | index | 1:25 | $20,000 | $800 |
| BTC_USD | crypto | 1:2 | $60,000 | $30,000 |

Re-measured over 2019 (a climbing year, no crypto data before 2020) and 2023
(the only full year that actually exercises the 1:2 crypto leverage), with used
margin divided by the balance **at that moment** rather than the starting
balance:

| run | peak margin / balance | heaviest single position |
|---|---|---|
| 2019, $50k start | 43.0% | XAU 13.5% |
| 2019, $500k start | 8.9% | XAU 2.5% |
| 2023, $50k start | 72.4% | ETH 21.7% |
| 2023, $500k start | 11.1% | ETH 2.2% |

Restricted to the challenge phase, while the balance is still under $55k and the
account is at its smallest:

| run | peak margin / balance | heaviest single position |
|---|---|---|
| 2019 | 14.7% | 3.6% |
| 2023 | **28.6%** | 7.4% |

**Margin never binds.** The tightest moment in a challenge uses 28.6% of what is
available, better than three times clear of the limit, and no individual
position exceeds 22%. 5ers would not have rejected a single trade in either
year. This retires the 69.4% figure and the open question about whether indices
at 1:20 would put the climb at the ceiling — they do not.

The simulator still models no margin at all (`csv_mt5_simulator.py:557-559`
hardcodes `margin: 0.0`, `margin_free: equity`), so the absence of a problem is
a measurement, not a guarantee. It covers two years of eleven. Redo it if
`MAX_TOTAL_POSITIONS`, `CORR_GROUP_CAP` or `risk_per_trade_pct` increase.

**Per-position cap: 50 lots** (`main_live_bot.py:4361`). Not published on the
High Stakes page either — reconfirm with support.

Realised sizes under this config are far below it:

| account | trades | max lot | mean lot |
|---|---|---|---|
| $100k climbing | 985 | 19.45 | 2.36 |
| $500k at cap | 891 | 28.07 | 2.92 |

So the cap never binds in normal operation.

**Answered:** there is no aggregate exposure cap. Support confirmed that any
number of positions may be open as long as margin allows, and that the account
rejects the trade once leverage is exhausted. The earlier worry — that a
total-exposure ceiling would bind where the per-position cap does not — does
not apply.

**Known defect, no impact on these results.** The backtest reads
`symbol_info.get('max_lot', 100.0)` (`main_live_bot_backtest.py:3454`) but
`get_symbol_info()` returns `volume_max`, not `max_lot`. The lookup always misses
and falls back to **100 lots**, double the real limit, and the symbol table's
`volume_max: 50.0` is never read. The live bot gets this right. It only bites
above 50 lots, which happens nowhere in the scaled or challenge results.

**Unexplained observation:** mean lot rose only 1.24× (2.36 → 2.92) for a 5×
larger account. Suspected cause is the TDD tiers throttling risk near the funded
floor, but unverified — and if true, some of the lower drawdown at the cap that
was attributed to the absence of rung crossings may belong to risk throttling
instead. Separating them needs a run with the TDD tiers disabled.

---

## 4. Before this can be traded

`W5_FINAL_SETTINGS.md` §4 described a state that no longer holds: it was written
before the live port. All tuned environment variables now reach `main_live_bot.py`
through the `_w5_*` bridge helpers, the nightly de-risk pass has a live
implementation, and the `ftmo_config.py` mismatch is handled by the bridge rather
than by editing that file — which must stay untouched, since the backtest imports
the same object and editing it silently changes backtest results.

Verify with `backtest/src/w5_acceptance.py` (config layer plus deployment
pre-flight) and `backtest/src/w5_full_check.py` (five layers, currently zero
unexplained differences). Launch through `deploy/start_live.bat`, which runs the
acceptance test first and refuses to start without credentials in the machine
environment.

What is still genuinely open before real money: costs are modelled at a flat
1.0 pip across all instruments and the sensitivity sweep is only part-done; the
nightly de-risk hour was tuned at 22:00 UTC under that flat-spread model and the
live default is 21:00; and none of this has run on a 5ers demo yet.
