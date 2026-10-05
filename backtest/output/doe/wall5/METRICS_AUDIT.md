# Metrics audit — what `win_rate` and `net_pnl` actually mean

Measured on a single reproducible run: the stage-1 winner (t61 ladder) over
calendar 2019, fresh $100k, 5% wall, scaling to $500k.
Reproduce with `--start 2019-01-01 --end 2019-12-31 --balance 100000`.

## 1. `win_rate` counts only the final closing leg, not the position

```
main_live_bot_backtest.py
    total_trades = len(full_trades)          # only full closes count as "trades"
    winners      = sum(1 for t in full_trades if t.get('pnl', 0) > 0)
```

Partial closes are written to `trades.csv` as their own rows, with a ticket of
the form `<ticket>_partial_<epoch>` and `partial=True`. The `pnl` on the final
row is that leg's P&L alone — the comment two lines below the calculation is
explicit that "Net PnL includes ALL closes (full + partial)".

So a position that banks 25% at TP1 and 60% at TP2, then gives a little back on
the last 15%, is recorded as a **loss**.

| measure | 2019 |
|---|---|
| engine `win_rate` (final leg only) | 184/632 = **29.1%** |
| whole-position P&L (all legs summed) | 275/632 = **43.5%** |

* 632 positions produced 1,419 closing legs; **358 positions scaled out**.
* **91 positions were profitable overall but counted as losses.**
* avg win **$762**, avg loss **$300**, payoff **2.54**, expectancy **+$162**/position.

Group legs by `ticket.split('_partial_')[0]` to get the position-level number.

Note when parsing `trades.csv`: `partial` is the string `"True"` or empty.
Do not coerce it with `bool()` — a blank cell read via pandas becomes NaN and
`bool(NaN)` is `True`, which silently inverts the classification.

## 2. `net_pnl` counts firm-allocated capital as profit

```
main_live_bot_backtest.py
    total_pnl = (final_balance + total_withdrawn) - original_balance

csv_mt5_simulator.py   (on each +10% scaling milestone)
    self._funded_level = next_level
    self._balance      = next_level          # <- firm capital, written into balance
```

Each scale-up resets balance to the new funded level, so the capital the firm
allocates lands inside `net_pnl`.

| 2019 | |
|---|---|
| realised trading P&L (sum of all legs) | **$102,691** |
| `fiveers_total_withdrawn` | **$62,898** |
| reported `net_pnl` | **$236,946** |

**Use `fiveers_total_withdrawn` as the profit measure.** It is real cash to the
trader. Ignore `net_pnl` — it is not trading profit.

This does not disturb any selection made so far: `w5_gauntlet.py` ranks
survivors by payout (then win rate), so the stage-1 winner t61 was chosen on
the sound number. Its **$602k decade payout stands**; the "net $2.06M" figure
reported alongside it does not.

## Status

Not patched yet, deliberately. The stage-2 sweep has ~120 backtest subprocesses
importing `main_live_bot_backtest.py`; editing it mid-run risks a partial read.
The position-level win rate should be added as an **additional** results field
between stages, so metrics already collected stay comparable.
