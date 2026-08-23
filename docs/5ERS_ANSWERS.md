# 5ers support — antwoorden en wat ze veranderen

Beantwoord op 2026-08-23. De vier vragen staan in `5ERS_QUESTIONS_EMAIL.md`.
Wat hieronder staat is de letterlijke reactie plus wat er met de cijfers gebeurt.

---

## 1. Dagelijkse verlieslimiet en uitbetalingen

> "Daily loss will reset after withdrawal according to the balance after
> withdrawal."

De uitbetaling telt dus niet als handelsverlies. Dat was de aanname en die
klopt. Het verschil met het model zit in het detail: 5ers **verlegt het
ijkpunt** naar de balans na de opname, het model laat `day_start_equity` op de
waarde van voor de opname staan en trekt het uitbetaalde bedrag van de teller af
(`main_live_bot_backtest.py:6085`).

Twee gevolgen, allebei klein en ze wijzen tegengesteld:

* **Iets ruimer bij ons.** De toegestane 5% wordt bij ons over de hogere balans
  van voor de opname berekend. Bij een cap van $500.000 en een balans van
  $533.000 is dat $26.650 tegen $25.000 bij 5ers — $1.650 verschil, en alleen op
  uitbetaaldagen.
* **Iets krapper bij ons.** Bij 5ers wist het resetten ook het verlies dat je
  die dag voor de opname al had gemaakt. Bij ons blijft dat staan.

De slechtste dag over elf jaar was 4,09%. Zelfs als die dag toevallig een
uitbetaaldag was en je hem tegen de laagste noemer legt, komt hij op
ongeveer 4,4% uit — onder de muur. **Geen aanpassing nodig.**

---

## 2. Vaste uitbetaling — hier zat het model er wel naast

> "Once you reach the 500K level. You can withdraw 100% profit + $10,000 fixed
> amount every month."

Het model kende $10.000 toe bij **elke uitbetaling** zodra het niveau 500K was,
plus $4.000 per uitbetaling tussen 350K en 500K. Het aantal uitbetalingen lag
tussen 5 en 9 per jaar, dus het antwoord van **$672.000 hing aan de
uitbetaalcadans van de simulator in plaats van aan de kalender**. Dat is de
verkeerde as, en het bedrag was daarmee betekenisloos. De $4.000-tier onder 500K
komt bovendien uit het oude model en wordt in het antwoord van support niet
genoemd.

Herberekend met `w5_payout_fix.py`, 500K-niveau bereikt in juni 2016, laatste
maand december 2025 — 115 kalendermaanden:

| | vast bedrag | met handelswinst $3.622.756 |
|---|---|---|
| oud, fout | $672.000 | $4.294.756 |
| **bovengrens** — elke maand op 500K | **$1.150.000** | **$4.772.756** |
| ondergrens — alleen maanden met winstuitbetaling (60) | $600.000 | $4.222.756 |

De bovengrens klopt als het vaste bedrag onvoorwaardelijk is zodra je op 500K
zit. De ondergrens klopt als het aan een winstuitbetaling hangt. Support zegt
"every month" zonder voorwaarde, wat naar de bovengrens wijst, maar de zin staat
in dezelfde adem als "withdraw 100% profit", dus het is niet waterdicht.

**Werkgetal: $120.000 per jaar zodra het account op 500K staat.** Dat is
ongeveer een kwart bovenop de $360.000 gemiddelde handelswinst per jaar op de
cap, en het is de enige inkomstenstroom in dit hele model die niet van de markt
afhangt.

---

## 3. Hefboom per activaklasse — dit maakte de vorige margeberekening ongeldig

> "Forex - 1:100 / Indices and Metals - 1:25 / Commodities - 1:5 / Crypto - 1:2"

Elke margeberekening tot nu toe ging uit van 1:100 op alles en kwam op 69,4%
piekgebruik. Metals en indices vragen vier keer zoveel, crypto vijftig keer. Dat
cijfer was dus te laag en de vraag was of het echte cijfer boven 100% uitkwam —
want dan houdt de backtest een boek aan dat het account niet kan dragen.

Marge per lot bij de echte hefbomen:

| instrument | klasse | hefboom | notional | marge per lot |
|---|---|---|---|---|
| EUR_USD | FX | 1:100 | $110.000 | $1.100 |
| USD_JPY | FX | 1:100 | $100.000 | $1.000 |
| XAU_USD | metaal | 1:25 | $200.000 | $8.000 |
| XAG_USD | metaal | 1:25 | $125.000 | $5.000 |
| NAS100_USD | index | 1:25 | $20.000 | $800 |
| BTC_USD | crypto | 1:2 | $60.000 | $30.000 |

Gemeten over 2019 (klimjaar, geen cryptodata) en 2023 (het enige volledige jaar
mét crypto — M15-cryptodata begint pas in 2020), marge afgezet tegen de balans
**op het moment zelf**:

| run | piekmarge / balans | zwaarste enkele positie |
|---|---|---|
| 2019, start $50k | 43,0% | XAU 13,5% |
| 2019, start $500k | 8,9% | XAU 2,5% |
| 2023, start $50k | 72,4% | ETH 21,7% |
| 2023, start $500k | 11,1% | ETH 2,2% |

En het stuk dat er voor de challenge toe doet, zolang de balans onder $55.000
blijft:

| run | piekmarge / balans | zwaarste enkele positie |
|---|---|---|
| 2019, $50k challengefase | 14,7% | 3,6% |
| 2019, $500k challengefase | 4,9% | 1,4% |
| 2023, $50k challengefase | **28,6%** | 7,4% |
| 2023, $500k challengefase | 9,7% | 1,6% |

**Marge bindt nergens.** Het krapste moment in de challenge gebruikt 28,6% van
wat beschikbaar is, ruim drie keer onder de limiet. Geen enkele losse positie
komt boven 22%. 5ers zou geen enkele trade in deze twee jaren geweigerd hebben.

Een eerdere versie van dit script zei 5.368% en dat was mijn fout: het rekende
de FX-notional als contractgrootte maal genoteerde prijs, waardoor USD_JPY op
$11 miljoen per lot uitkwam in plaats van $100.000. Voor FX is de notional de
contractgrootte in de basisvaluta omgerekend naar USD. Gecorrigeerd in
`w5_margin_real.py`.

Wat wél blijft staan: **de simulator modelleert marge helemaal niet.**
`csv_mt5_simulator.py:557-559` zet `margin: 0.0` en `margin_free: equity`. Dat
is nu gemeten onschadelijk voor deze configuratie, maar het is geen garantie —
het is twee jaar van de elf, en een configuratie met meer gelijktijdige posities
of meer crypto kan er anders uitkomen. De meting hoort opnieuw te gebeuren als
`MAX_TOTAL_POSITIONS`, `CORR_GROUP_CAP` of `risk_per_trade_pct` omhoog gaan.

---

## 4. Aantal posities

> "You can open as many positions as you wish as long as the account leverage
> allows you. The account will reject the trade if you already used all the
> leverage."
> "Max Lot Size = (Account Balance × Leverage) / (Contract Size × Current Price)"

Er is dus **geen aparte limiet op het aantal posities of op de totale exposure**
— de enige rem is marge, en die is hierboven gemeten op maximaal 28,6% in de
challenge. De open vraag uit `W5_BASELINE_CONFIG.md` §3 over een
aggregaatplafond is hiermee beantwoord: dat bestaat niet.

De formule van support is dezelfde als hierboven, alleen omgekeerd geschreven.
Let op dat "Contract Size × Current Price" voor FX de notional in de
basisvaluta is, niet contractgrootte maal quote; anders komt USD_JPY er honderd
keer te zwaar uit.

**Kan marge ooit bindend worden?** Nee, en niet omdat de backtest hem niet
modelleert maar omdat de drawdownbeveiliging zes keer eerder vuurt. Gebruikte
marge staat vast zodra een positie open is; het gebruik stijgt alleen doordat de
equity daalt. Vanaf het gemeten piekgebruik van 28,6% moet de equity **59%**
zakken om zelfs maar de eigen blokkade te raken, en 86% om een gebruikelijke
stop-out van 50% margeniveau te halen. Het account is dood bij 10%, en de bot
sluit zelf alles bij 2,50% op de dag. Daarom is er geen noodsluiting op marge:
die zou nooit als eerste aan de beurt zijn.

Wat 5ers als stop-outniveau hanteert staat nergens in de documentatie die ik
heb; `stop_out_level` in de backtest is de 10%-regel, niet een margeniveau. De
berekening hierboven gebruikt 50% als gangbare waarde. Het is de moeite waard
om het echte getal na te vragen, al verandert het de conclusie niet.

**Hoe de live bot met een weigering omgaat.** Er is geen margecontrole vooraf —
`main_live_bot.py` roept nergens `order_check` aan en kijkt niet naar
`margin_free`. De order wordt gestuurd en als MT5 hem weigert vangt
`tradr/mt5/client.py:1135` dat af, logt de retcode en geeft een foutresultaat
terug. De bot crasht niet en slaat de trade over. Dat is nette afhandeling, maar
het betekent ook dat een weigering **stil** een verschil met de backtest
oplevert. Zolang het gebruik onder 30% blijft is dat theoretisch; het is een
reden om de marge in de eerste weken live in de gaten te houden.

---

## Wat hier niet in stond en nog open is

* Of de $10.000 onvoorwaardelijk is of aan een winstuitbetaling hangt — het
  verschil tussen $1.150.000 en $600.000 over tien jaar.
* Of er een limiet per positie is (de bot hanteert 50 lots,
  `main_live_bot.py:4361`). Support noemt hem niet en de gemeten maxima liggen
  op 16-35 lots, dus hij bindt nergens, maar hij is niet bevestigd.
