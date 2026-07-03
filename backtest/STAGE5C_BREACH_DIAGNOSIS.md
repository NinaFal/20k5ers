# Stage 5c — why 0/20 passed, and the fix (correlation cap)

**Session:** continue from `claude/awesome-maxwell-50dMF` (PR #36 merged).
**Input:** Stage 5c OOS screen finished **0/20 pass** — every top trial breached.
**Output of this session:** root-caused the breach and identified the single
missing breach-control lever, with proof. Next step wired and ready (Stage 5d).

---

## 1. The Stage 5c screen result, read correctly

The report line said "t217 & t78 control DDD<5% but TDD ~0.07% over wall", which
framed it as two near-misses on total DD. Looking at all 20 trials' **full
2015-2024 window** breaches tells a different, more useful story:

| failure mode | # trials | how they die |
|---|---|---|
| **DAILY gap breach** (DDD 7–19%) | **18/20** | survive ~5–9 yrs, scale to the 400k cap, then a flash/news gap blows past stops on a stack of correlated positions |
| **TOTAL slow bleed** (TDD ~10.07%) | 2/20 (t78, t217) | tight risk avoids the daily blow-up but grinds up to the 10% total wall |

The daily breaches cluster on specific **gap events**, hitting whichever config
is exposed when it arrives:

```
2020-03-18  COVID crash        t39, t170            DDD 6.9 / 13.5
2020-12     Brexit deadline    t14, t217            DDD 11.9 / (t217 total 10.07)
2022-06-15  FOMC 75bp week     t38,t249,t251,t301   DDD ~11–12
2022-09-21  UK gilt crisis     t113, t66            DDD 19.3 / 19.3
2022-10     gilt aftermath     t19, t3              DDD ~11
2023-04/05  regional-bank vol  t131,t201,t59,t8     DDD up to 17.9
2023-06/07  ...                t258, t104           DDD ~8–13
```

## 2. Root cause — uncapped correlated exposure

Diagnostic (`backtest/src/diag_full_breach.py`) dumps the positions open into
each breach. Two representative deaths:

- **t170, COVID 2020-03-19 (DDD 13.5%)** — **17 positions open at once**:
  6 CHF crosses (CHF_JPY×2, USD_CHF, EUR_CHF, NZD_CHF, GBP_CHF), 6 GBP crosses
  (GBP_NZD×2, GBP_JPY, GBP_CAD, GBP_AUD…), plus JPY/CAD/NZD/AUD crosses. In a
  risk-off crash these all move together → one session digs a 13.5% hole.
- **t217, Brexit weekend 2020-12-13 (TDD→10.07%)** — **19 positions, 9 of them
  GBP** (GBP_JPY×3, GBP_USD×3, GBP_NZD×3) into the deal-deadline gap.

The strategy's signal sweep fills many pairs in the **same correlation group**
in the same direction. DDD reaches 11–19% (not ~5%) because the gaps fill 2–4×
past the stops on a whole cluster at once. The engine even documents this
(`main_live_bot_backtest.py:4007`: "The root driver of the 10% total-DD death is
clustered exposure") — but the lever that bounds it, **`CORR_GROUP_CAP`, was 0
(OFF) for the entire Stage-5c pool.** It was never in the search space.

## 3. Proof — the correlation cap flips breaches to survivals

`CORR_GROUP_CAP=N` caps concurrent open+pending positions per correlation group
(groups defined in `weekend_gap_manager.py`: USD_MAJORS, GBP_CROSSES,
JPY_CROSSES, COMMODITY_FX, …). Full 2015-2024 window, all else equal:

| trial | cap | outcome | net | peak TDD | peak DDD |
|------:|----:|---------|----:|---------:|---------:|
| 170 | off | BREACH @ 2020-03 COVID    | $618k | 4.56 | **13.51** |
| 170 | 4   | BREACH @ 2015-01 CHF swan | −$4k  | 8.55 | 10.72 |
| 170 | 3   | BREACH @ 2024-12-27 (last wk) | $625k | 7.77 | 8.14 |
| 170 | **2** | **SURVIVE** | $67k | 7.20 | **3.87** |
| 113 | off | BREACH @ 2022-09 gilt     | $625k | 5.16 | **19.29** |
| 113 | 3   | BREACH @ 2024-05          | $578k | 3.48 | 12.57 |
| 113 | **2** | **SURVIVE** | **$208k** | 7.28 | **3.73** |
| 217 | off | BREACH total (bleed)      | $196k | 10.07 | 3.95 |
| 217 | 2   | BREACH @ 2019-01 JPY flash | $11k | 5.09 | 5.31 |

Read-outs:
1. **cap=2 converts the two big daily-gap deaths (t170, t113) into full-window
   survivors**, and crushes peak DDD from 13–19% to ~3.7%. The daily-gap risk is
   essentially neutralized once a config survives.
2. **The cap trades against profit** — fewer concurrent positions → less net
   (t170: $618k→$67k). t113 keeps a healthier $208k at cap=2 because its risk
   mults are looser. So the cap must be **co-optimized with the risk levers**,
   not bolted on: loosen per-trade/regime risk to refill the profit the cap
   removes, while the cap holds the gap wall.
3. **cap is path-dependent** — too loose (cap=4) leaves enough CHF stack to die
   at the 2015 SNB swan; too tight starves profit. cap=2–3 is the live zone.
4. cap=2 is not universal (t217 still dies at the 2019 JPY flash), so the winner
   is a *joint* (cap, risk) point, found by search — see Stage 5d.

## 4. Why the whole pool overfit (the deeper reason)

The Stage-5c optimizer (`stage5c_oos_robust.py`) selects on **six 3–4-year
windows** — none of which is the full 2015-2024 continuous run. Those short
windows never let the account scale to the 400k cap, so they never expose the
high-funded-level clustered-gap risk that the OOS screen's full window tests.
Classic finding #1 (cold-start ≠ continuous). Two fixes for Stage 5d:
add `CORR_GROUP_CAP` to the search space **and** put the full continuous window
in the selection set.

## 5. Next step — Stage 5d (wired, ready to run)

`backtest/src/stage5d_corr_cap_screen.py` sweeps `CORR_GROUP_CAP ∈ {2,3}` across
the trials that failed **only** the full window (`[14, 39, 66, 104, 217, 301]`)
on the same 5 OOS-screen windows, and reports which `(trial, cap)` pairs pass
all five. Resumable (per-window checkpoint), safe to relaunch.

```bash
# from repo root, keep alive via the Bash tool run_in_background (NO trailing &):
uv run python3 backtest/src/stage5d_corr_cap_screen.py --caps 2,3 --workers 2
# report -> backtest/output/doe/stage5d_corr_cap_screen_report.txt
```

If a `(trial, cap=2)` pair passes the screen, that is the **first breach-free
config over OOS + the full continuous run** — lock it and move to a Stage 5d
*optimization* that co-optimizes the cap with looser risk mults to buy back net.
If none passes at the existing (tight) risk settings, run that joint
optimization directly: it is the profit-recovery step, with the cap holding the
gap wall the pool has been failing on.

## 6. Artifacts this session

- `backtest/src/diag_full_breach.py` — per-trial full-window breach diagnostic
  (dumps breach date/type + positions open into the breach; `--corr-cap`,
  `--exclude` levers). Run under `uv run` (needs the synced venv's pandas).
- `backtest/src/stage5d_corr_cap_screen.py` — the Stage 5d corr-cap OOS screen.
- Raw diagnostic runs live under `backtest/output/doe/diag_*` (gitignored — large
  trades.csv); the numbers are captured in §3 above.
