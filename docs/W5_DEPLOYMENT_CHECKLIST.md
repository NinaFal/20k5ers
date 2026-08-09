# Deployment checklist — 5ers 50K, Windows host

Run top to bottom. Nothing here is optional, and the ordering matters: the
verification steps only mean something once the steps above them are done.

Validated configuration: `backtest/output/doe/wall5/BASELINE_t65_tdd_FROZEN.json`
Expected performance: `docs/W5_VERDICT.md`

---

## 1. Environment (Windows trading host)

```bat
set BROKER_TYPE=fiveers_live
set MT5_LOGIN=<your 5ers account number>
set MT5_PASSWORD=<password>
set MT5_SERVER=<server name from 5ers — default guess is 5ersLtd-Server>
set MT5_PATH=<path to terminal64.exe, if not auto-detected>
```

**`BROKER_TYPE` is the one that will silently ruin everything.** Unset, it
resolves to `forexcom_demo` (`broker_config.py:291`) and the bot trades a
different broker with different symbols and spreads, while every configuration
check still reports PASS.

Do **not** export the frozen config wholesale. It records
`NIGHTLY_DERISK_HOUR=22`, which is what was tested but wrong for live — see §4.

## 2. Verify

```bat
uv run python3 backtest/src/w5_acceptance.py
```

Exit **0** = config and environment both clear. Exit **1** = a config mismatch,
the bot would trade the wrong settings, **stop**. Exit **2** = deployment items
outstanding.

This checks configuration only. It cannot prove the live bot *behaves* like the
backtest — `main_live_bot.py` cannot be replayed against history, which is why
`main_live_bot_backtest.py` exists as a fork. §5 is what covers that.

## 3. Ask 5ers before funding anything

Four questions, in descending order of what they cost you:

1. **Are withdrawals charged against the daily loss limit?** The entire
   capped-year result assumes not. If they are, every payout day at the cap is
   an instant breach and the $4.29M decade is void.
2. **Is the $10k fixed payout per milestone, monthly, or one-off?** Worth
   roughly $500k across a decade — the three readings give $672k, $1.2M and
   $22k.
3. **Per-asset-class leverage.** 1:100 is the headline FX figure. This config
   trades XAU, XAG and NAS100; if indices are 1:20 they consume five times the
   margin credited, and the climbing phase may be at the ceiling rather than at
   69% of it.
4. **Any aggregate exposure cap** beyond the 50-lot per-position limit.

## 4. Known deliberate divergence

`NIGHTLY_DERISK_HOUR` defaults to **21**, not the tested 22. 22:00 UTC sits
inside the 21:30–22:30 rollover window where spreads widen 5–50x; the simulator
applies a flat spread (`csv_mt5_simulator.py:199`) and cannot see that cost,
while the config holds zero non-crypto positions overnight and would flatten the
whole book there every night. Set 22 only to reproduce backtest numbers.

## 5. Demo first — two weeks minimum

On a **5ers demo** account, then compare against the backtest on the same dates:

- do the same symbols trigger on the same days?
- are lot sizes within a few percent?
- does the nightly de-risk fire at 21:00 and flatten non-crypto positions?
- do the TDD tiers engage at 1.5% and 5.5%?

This is the only step that can catch behavioural divergence. This port produced
**five** silent configuration bugs that no code review caught — a shared config
object that rewrote the backtest, an attribute-name mismatch that would have
disabled the wall-guard, an unported halt that left live with breach-causing
behaviour, a halt threshold reading 3.2 against 2.50, and a lot cap of 100
against 50. Expect the demo to find something.

## 6. Expectations, and what they rest on

Over 200 out-of-sample starts: **95.5% eventually pass, 4.5% lose the account**,
median 19 days, 64% inside 30 days.

Two things make live likely to come in **below** this:

**Costs.** Every result used a flat **1.0 pip** spread across all instruments
including XAU, XAG, NAS100 and crypto, where real spreads are multiples of that,
on a strategy taking ~1,000 trades a year. The gap is real and unmeasured.

**Margin.** The simulator models none — `csv_mt5_simulator.py:557-559` hardcodes
`margin: 0.0` and `margin_free: equity` — so it opens positions a broker may
reject. Measured peak exposure is 69.4% of equity while climbing at $100k
(12.6% at the $500k cap), assuming 1:100 on everything. Question 3 in §3 decides
whether that is comfortable or at the ceiling.

## 7. Risk you are actually taking

`risk_per_trade_pct` is 2.7, but that is a base, not what gets risked:

| funded level | volatile | calm (×1.45) |
|---|---|---|
| below $300k — **the challenge** | 2.70% | **3.92%** |
| $300k–$1M — includes the $500k cap | 0.60% | 0.87% |

Total open risk is capped at 7% of balance across all positions, so 3.92% is a
ceiling for the first trade into an empty book, not what every trade risks.

The challenge is where the real risk sits. Once funded and scaled, the bot
becomes roughly 4.5x more conservative on its own.
