# Master findings — 5%ers strategy work, three phases

**Last updated:** 2026-07-21. This is the top-level index across all
optimization work on this strategy. Three distinct phases, each with a
different objective and account assumption — do not mix their configs.

---

## Phase 1 — FUNDED ACCOUNT (once the challenge is passed and live)

**Goal:** maximize long-run net profit with zero breach, across OOS windows,
random starts, and the full continuous 10-year run. Account: starts at
whatever level you're funded to (tested at 50k/100k), scales via the 5%ers
funded ladder.

**Status: LOCKED.** Full detail: `output/doe/STAGE5D_WINNER.md`,
`OPTIMIZATION_ROADMAP.md`, `STAGE5C_BREACH_DIAGNOSIS.md`.

**Root finding:** the strategy stacks correlated positions (e.g. 6 CHF + 6 GBP
crosses) that gap together on flash/news events (2015 CHF/SNB, 2020 COVID,
2022 gilt crisis). `CORR_GROUP_CAP=3` is the fix — it converts the pool's
prior 0/20 OOS-screen pass rate into 4/6 clean passes.

**Two locked configs (both validated OOS + full continuous run, 0% breach):**

| config | net (10yr, 50k start) | peak TDD | peak DDD | funded reached | risk |
|---|---:|---:|---:|---:|---|
| **Primary winner** | $533,888 | 6.27% | 3.23% | $400k (capped) | 1.0% |
| **Backup (higher profit)** | **$743,277** | 9.12% | 3.64% | $500k (uncapped) | 1.5% |

Entry: t39 skeleton (Stage 1 winner), runner TP ladder (5 TPs, big trailing
runners — this is the FUNDED-phase ladder, opposite of the challenge-phase
fast-banking ladder in Phase 2/3). `CORR_GROUP_CAP=3`, `FIVEERS_MAX_SCALE`
capped at 400k (primary) or lifted (backup).

**Caveats not yet closed:** full validation gauntlet (gap/slippage stress,
`TDD_WORST_CASE=1`, Monte-Carlo trade-order shuffle, parameter-perturbation
robustness) not yet run on either config — see STAGE5D_WINNER.md.

---

## Phase 2 — CLASSIC 5% DAILY-LOSS 2-STEP CHALLENGE (100k)

**Goal:** pass Step 1 (+8%) then Step 2 (+5%) on a fresh $100k as fast as
possible, on an account with the CLASSIC 5% daily / 10% total wall (closed
balance target, ≥3 profitable days/step).

**Status: LOCKED — genuinely fast and safe.** Full detail:
`output/doe/STAGEC2_TRIAL4_BACKUP.md`, `output/doe/STAGEC1_WINNER.md`,
`output/doe/STAGEC2_WINNER.md`, `CHALLENGE_ROADMAP.md`.

**Locked config (trial 4):**

| metric | value |
|---|---|
| score | 174.8 |
| p(pass ≤20 days) | **37.5%** |
| p(pass ≤40 days) | 62.5% |
| breach rate | **0%** (16 TRAIN starts) |
| entry | c=0.65 / v=0.65 / thr=1.15 |
| ladder | fast-banking, 100% closed by TP3 (0.40R/0.75R/1.35R, 50/35/15%) |
| risk | 3.5% per trade |
| CORR_GROUP_CAP | 3 |

**This is a real, ready-to-use config** — if a classic 5%-wall account is
available, this is the fast path that was never achievable on the 3%-wall
account (see Phase 3).

---

## Phase 3 — 3% DAILY-LOSS 100k CHALLENGE ("Summer Edition") — ONGOING R&D

**Goal:** same as Phase 2, but the REAL account uses a 3% daily wall (EOD
equity-or-balance, whichever higher), not 5%. Discovered mid-Phase-2-work that
the engine had this hardcoded at 5% — fixed (`CFG_DAILY_WALL_PCT` env var).

**Status: OPEN R&D, continuing on branch `claude/3pct-challenge-rd`.**
Full detail: `output/doe/WALL3_FINDINGS.md`.

**Key findings so far (across ~1500 backtests, two full C1 restarts + a
129-trial C3 risk/regime search):**
1. Phase 2's fast config (trial 4) breaches **87.5%** of TRAIN starts under
   the real 3% wall — completely unsafe as-is (backed up for Phase-2-account
   use only).
2. A new lever was required and added: `MAX_TOTAL_POSITIONS` — breadth of
   small positions across DIFFERENT correlation groups can breach 3% even at
   low per-trade risk; `CORR_GROUP_CAP` alone doesn't catch this.
3. Even with the fix, **no config found is both fast (≤30 days) and safe
   (0% breach)** — best safe config reaches +8%/+5% in ~52 days median (when
   it completes at all; most starts don't finish within 60 days).
4. **High-frequency / different-timeframe entry models are explicitly OUT OF
   SCOPE** for this R&D per instruction — the fix must come from tuning the
   existing HTF strategy (risk, regime, position caps, entry shape), not a
   new entry system.

**Best config found so far (not yet "locked" — still R&D):**
c=0.35-0.45 / v=0.80 / thr=1.05, risk ~1.0%, `MAX_TOTAL_POSITIONS`~15,
fast-banking ladder. 0% breach on TRAIN, median ~52 days to complete (only
when it completes — most starts don't finish within 60 days).

**Open questions / next steps for the R&D branch:**
- Real median time-to-pass at a 90-180 day horizon (still not measured).
- Whether a different ladder shape (re-run C2 under the 3% wall + position
  cap, which has never been done — the current ladder is inherited from the
  Phase-2 C2 search) could improve speed without the HFT constraint.
- Joint C3-style risk/regime/position-cap search on TOP of the new C1 winner
  (the corrected-wall C3 run was done on the OLD entry ranking).

---

## Which config to use, right now

- **Have a funded account already?** → Phase 1 (primary winner for safety
  margin, backup for +$200k more profit at slightly thinner TDD margin).
- **Taking a 5%-wall challenge?** → Phase 2 (trial 4) — fast and proven safe.
- **Taking the 3%-wall "Summer Edition" challenge?** → Phase 3's current best
  (c=0.35-0.45/v=0.80/thr=1.05, risk 1.0%, maxpos 15) is the only 0%-breach
  option, but budget for a MULTI-MONTH timeline, not weeks. R&D continues on
  `claude/3pct-challenge-rd` to try to improve this.
