# Pre-mortem — it is 12 months on and this has gone badly. What happened?

Written before deployment, deliberately. The question is not "is the config
good" — the 200-start evidence says it is. The question is what the evidence
does **not** cover, because that is where the loss comes from.

Two things to state first.

**This is not established as the best configuration.** Three lines of enquiry
were opened and none finished:

| lead | what it showed | why it stopped |
|---|---|---|
| 5-leg TP ladder | never tested at all — `space_ladder` hardcoded `tp4_close_pct: 0.0, tp5_close_pct: 0.0`, so every stage of every round inherited a 3-leg assumption. The position is flat at 2.75R and nothing ever rides a trend further. **Still true**: the frozen config closes 25% at 0.65R, 60% at 1.85R and 15% at 2.75R — 100% in three legs. The engine itself supports five (`main_live_bot_backtest.py:5084` handles TP4 and TP5); only the config zeroes them. **Landmine if anyone turns them on:** `tp4_r_multiple` is 2.5 and `tp3_r_multiple` is 2.75, so TP4 would fire BEFORE TP3. Inert while the close percentages are zero, wrong the moment they are not | stopped by request after 17 trials, ties unresolved |
| survival optimizer | 3 of 5 trials **halved** total failures vs the incumbent (5 vs 9 per 30) via mutually contradictory parameters | paused, 5 of 80 trials |
| risk 2.2% | 7 breaches → 2 on the hard sample, McNemar p=0.062 | confirmation cancelled midway |

None is proven better. But "we did not find better" is different from "better
does not exist", and here we mostly stopped looking rather than exhausted the
search.

**And the profit figure has no error bars.** 196 samples for the challenge; for
the funded decade, **one path per config**. The $4,294,756 is a single draw.
Nobody has run 100 random-start funded decades, so the spread around that number
is completely unknown. Treat it as an existence proof, not an expectation.

---

## Ranked by probability x cost

### 1. Trading costs eat the edge — HIGH probability
Every result assumed a **flat 1.0 pip spread** on every instrument, including
XAU, XAG, NAS100 and crypto, where real spreads are multiples of that. The
strategy took **12,054 trades** across the 11-year run — roughly 1,100 a year.
An average extra 1.5 pips on a third of those is a large, permanent drag that
compounds against every figure in this project.

Unmeasured. This is the single most likely reason live comes in below backtest,
and it is measurable *before* trading: re-run one holdout with per-instrument
spreads.

### 2. A seventh port bug — MODERATE-HIGH
Nine port steps produced **six** silent configuration bugs, every one found only
because a *new* checking method was tried: a shared config object that rewrote
the backtest, an attribute-name mismatch that would have disabled the
wall-guard, an unported halt leaving live with breach-causing behaviour, a halt
threshold reading 3.2 against 2.50, a lot cap of 100 against 50, and halt
tightening that no env-var scan could have found.

The base rate of "one more method finds one more bug" is 6 for 6. There is no
basis for believing the seventh does not exist. Only the demo period tests this.

### 3. A 5ers rule assumption is wrong — MODERATE, one is catastrophic
Four unanswered questions, all cheap to resolve:

- **Are withdrawals charged against the daily loss limit?** If yes, every payout
  day at the cap is an instant breach and the entire capped-year result — which
  is 10 of the 11 years — is void. This is the one that kills the thesis, not
  just the number.
- Fixed payout cadence: $672k / $1.2M / $22k depending on the reading.
- Per-asset leverage: margin at 69.4% during the climb assumes 1:100 on
  indices and metals. At 1:20 for indices the climb may be *at* the ceiling.
- Any aggregate exposure cap beyond 50 lots per position.

### 4. The recent regime is harder, and 2026 resembles it — MODERATE
All **9 breaches fell in 2019 or later**; zero in 37 pre-2019 starts in the
first holdout, and both breaches in the second sample were also 2019+. Two
independent samples agree.

The holdouts were out-of-sample in *start date* but not in *time period* — the
config was optimised across 2015-2025 and validated on 2015-2025. If the next
year behaves like 2019-2025 rather than the full decade, the realised breach
rate sits at the upper end of the 1.7-7.5% interval, or above it.

### 5. The climb is the risk and you get exactly one — HIGH cost
2015, the only climbing year: worst total drawdown **6.33%** against ~2% for
every capped year, and worst daily 4.09%. Risk per trade is 3.92% below $300k
against 0.87% at the cap; margin usage 69.4% against 12.6%.

Every breach in this project happened while climbing. You will do the
$50k -> $500k climb **once, live, with real money**, and the 4.6% figure does
not describe it — that is a per-*challenge* rate, a different and shorter
exposure.

### 6. Execution reality — MODERATE
The simulator models **no margin at all** (`csv_mt5_simulator.py:557-559`
hardcodes `margin: 0.0`, `margin_free: equity`) and no slippage beyond a fixed
spread. The nightly de-risk flattens the entire non-crypto book in one pass —
up to 20 positions at once — with no market-impact model anywhere.

### 7. No validated fallback — MODERATE
One config, frozen. If live results diverge in month two there is no B-option
that has been through the same validation, and re-running the pipeline takes
days. The survival candidates are the natural fallback and none is confirmed.

---

## What would change the odds most, cheapest first

1. **Email 5ers the four questions.** Free. One answer can void the thesis.
2. **Cost-realism run** — one holdout with per-instrument spreads. Quantifies
   the largest known unknown.
3. **Demo two weeks**, comparing fills against the backtest on the same dates.
   The only test that catches bug #7.
4. **Funded-decade distribution** — 20+ random-start funded runs to put error
   bars on the $4.29M.
5. **Finish the survival search**, so a validated fallback exists.

---

## Status of those five

| | wat | stand |
|---|---|---|
| 1 | 5ers gemaild | **AF.** Antwoorden in `docs/5ERS_ANSWERS.md`. De load-bearing vraag is goed afgelopen: de dagelijkse limiet reset naar de balans NA opname, dus een uitbetalingsdag is geen breach en de gecapte jaren blijven staan. Vaste uitbetaling is $10.000 per MAAND op $500k. Hefboom per klasse bevestigd (forex 1:100, indices en metalen 1:25, grondstoffen 1:5, crypto 1:2) en gemeten: de marge piekt op 28,6% in de challenge, geen order boven 22% van zijn symboolplafond |
| 2 | kostenrealisme | **GEMETEN, en het is de bindende beperking.** Zie §8 hieronder. In de challenge kost 1x de geschatte spreads één venster van de veertig; 2x kost er acht en vijf breaches. Op het GEFUNDE klimjaar 2015 gaat 1x al door de muur: ergste dag 6,13% tegen 4,76% zonder kosten, win rate 53,1% tegen 59,5%, account dood. De bracket die lokaliseert hoeveel daarvan aan de dubbele telling ligt, draait |
| 3 | demo twee weken | **NIET GEDAAN.** Kan hier niet — dat vraagt de Windows/MT5-machine. Dit blijft het enige punt dat bug nummer zeven kan vangen |
| 4 | foutmarges | **KLAAR OM TE DRAAIEN.** `w5_funded_dist.py`, 20 gefunde accounts van elk drie jaar. De vensters overlappen in kalendertijd en dat staat in de docstring: gevoeligheid voor de startdatum, geen zuiver betrouwbaarheidsinterval |
| 5 | survival-zoektocht | **DRAAIT,** 35 van 80 trials. Beste tot nu toe op de 30 case-enriched vensters: 1 breach en 29/30 geslaagd tegen 7 breaches en 21/30 voor de incumbent, ten koste van acht dagen doorlooptijd. Het patroon is kleiner handelen (risico 2,7% -> 1,8%, muurmarge 5,5 -> 6,0). Dit is een KANDIDAAT; `w5_confirm_candidate.py` toetst hem op 70 achtergehouden vensters en daarna op 100 verse, gepaard, met McNemar |


---

## 8. Wat de kostenmeting opleverde — dit verandert de rangorde

Post 1 stond hier als "hoogste waarschijnlijkheid, ongemeten". Hij is nu gemeten
en hij is niet alleen waarschijnlijk, hij is bindend.

**Het model.** Per-instrument spreads (majors 1,2 pip, JPY-crosses 2,5, dure
crosses 4,5, UK100 2,0 punt, olie 4,0 cent), gerekend op elke entry inclusief de
Fib-limitorders — waar bijna elke entry van deze bot zit en waar de simulator
tot nu toe frictieloos vulde — en nog eens op elke SL-exit. Die tweede is een
DUBBELE telling: de spread betaal je bij openen, niet nog eens bij sluiten. Ze
staat er als slippagebuffer, en dat maakt elk getal hieronder pessimistisch met
een bekende richting maar een onbekende omvang.

**De challenge: 40 gepaarde vensters.**

| | geen kosten | 1x | 2x |
|---|---|---|---|
| geslaagd | 37 | 36 | 29 |
| breach | 0 | 1 | 5 |
| vastgelopen | 3 | 3 | 6 |
| <=30 dagen | 28 | 27 | 21 |
| mediaan | 16d | 16d | 18d |
| McNemar tegen base | — | p=1,000 | p=0,062 |

De helling is niet vlak. Tussen 1x en 2x zit een klif. De 1x-kolom is dus geen
geruststelling: hij zegt dat we aan de goede kant van die klif zitten ALS de
spreadschattingen kloppen, en die zijn geschat, niet gemeten aan de feed van
5ers.

**Het gefunde klimjaar: 2015, gepaard, zelfde $50.000 start.**

| | zonder kosten | met kosten (1x) |
|---|---|---|
| trades | 1189 | 699 (stierf halverwege) |
| win rate | 59,5% | 53,1% |
| ergste dag | 4,76% | **6,13%** |
| niveau eind | $350.000 | $250.000 |
| opgenomen | $141.277 | $89.364 |
| uitkomst | overleeft | **DOOD** |

Dit is de tegenovergestelde uitkomst van de challengemeting op dezelfde kosten,
en het verschil is blootstelling. 2015 is het enige KLIMJAAR: risico per trade
rond 3,9% tegen 0,87% op de cap, en het duurt een jaar in plaats van zestien
dagen. Post 5 van deze pre-mortem zei al dat de klim de risicopost is en dat je
hem precies één keer doet. Dit zet er een getal op.

**Wat hieruit volgt.**

1. De belangrijkste ontbrekende informatie in dit project is niet een parameter
   maar een FEIT: de werkelijke spreads van 5ers per instrument. Alles hierboven
   hangt aan een schatting.
2. De demoperiode krijgt een tweede taak. Naast bug nummer zeven moet hij de
   echte spreads en de echte fills meten, en die terugvoeren in dit model.
3. De survival-kandidaat (risico 1,8% tegen 2,7%) wordt hierdoor interessanter
   dan hij op de challenge alleen leek. Kleiner handelen tijdens de klim is
   precies wat een te dunne marge boven de kosten vraagt. Dat is een hypothese,
   niet een meting — de kandidaat is nog niet onder kosten gedraaid.

---

## The honest summary

A config validated at 95.4% pass / 4.6% account loss over 196 out-of-sample
attempts, ported with configuration verified end to end.

Its profit figure rests on a single path. Its cost model is optimistic by an
unmeasured margin. Its rule assumptions are unconfirmed and one of them is
load-bearing. Its port has produced six silent bugs and has not been behaviourally
tested. And the search for something better was stopped rather than completed.

None of that means don't trade it. It means the fee is the right amount to risk
first, and the demo period is not a formality.
