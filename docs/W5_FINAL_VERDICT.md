# Eindoordeel — de configuratie die gehandeld gaat worden

Datum: 2026-08-28. Alles hieronder is gemeten op de huidige code en de huidige
data. Wat er sinds de vorige verdictversie is veranderd staat in §5.

---

## 1. De configuratie

Bevroren in `backtest/output/doe/wall5/BASELINE_t65_tdd_FROZEN.json`, met
`EXCLUDE_SYMBOLS` uit `w5_common.py` / `_w5_excluded_symbols`.

| | |
|---|---|
| account | 5ers High Stakes classic, $50.000 |
| stap 1 / stap 2 | +8% / +5%, 5% dagmuur, 10% totale muur |
| risico per trade | 2,7% basis (3,92% in kalme regimes; 0,87% op de cap) |
| TP-ladder | 0,65R/25% — 1,85R/60% — 2,75R/15% |
| verhandeld | **30 symbolen** — 27 FX, XAU, XAG, UK100 |
| uitgesloten | XRP_USD, ADA_USD (5ers biedt ze niet), BTC_USD, ETH_USD (geen winst), NAS100_USD (negatief in beide helften) |
| niet beschikbaar | olie — `trade_oil=False` én hardgecodeerd uit in de engine |

UK100 staat in de lijst maar handelt feitelijk niet: het enige databestand
bevat dagbars, geen M15 (`W5_DATA_INTEGRITY.md`). Effectief **29 symbolen**, en
in de praktijk dus puur FX plus goud en zilver.

**NAS100 is uitgezet.** Het was het enige symbool dat in beide helften geld kost
— $-41 per trade over 2015-2019, $-122 over 2020-2025, profit factor 0,72 over
164 trades. Het wint vaak (61,6%) maar verliest dubbel zo groot als het wint:
gemiddelde winst $329 tegen gemiddeld verlies $-731.

Bijvangst: daarmee verdwijnt ook de laatst overgebleven datavervuiling. Naast
het echte M15-bestand lag `NAS100_USD_M15_2020_2025.csv` met 751 DAGbars die na
ontdubbelen de echte M15-bar om 00:00 verdrongen. Een uitgesloten symbool wordt
niet geladen, dus dat is opgelost in plaats van verplaatst.

---

## 2. De challenge — 100 verse vensters

`THIRD_100_STARTS.json`, disjunct van alle 293 eerder gebruikte vensters,
gegenereerd uit een vaste seed en gecommit vóór de meting.

| | |
|---|---|
| **geslaagd** | **88 van 100** |
| **breach — account weg** | **8** |
| vastgelopen — fee weg, account intact | 4 |
| mediaan | **19 dagen** |
| binnen 20 / 30 / 40 dagen | 49 / 68 / 75 |
| snelste / traagste | 6 / 85 dagen |

> **Deze meting is van vóór het uitzetten van NAS100.** De arm `no_nas100`
> draait dezelfde honderd vensters op de nieuwe configuratie en vervangt deze
> tabel zodra hij af is. Op de eerste 36 vensters staan beide op 3 breaches, dus
> een grote verschuiving is niet te verwachten — maar dat is een deelmeting en
> die hebben in deze ronde al een keer niet standgehouden.

Breaches per jaar: 2015, 2016, 2017, 2019 elk 1; 2020 en 2022 elk 2. Gespreid,
geen cluster in één regime.

**Wat dit praktisch betekent.** Ongeveer 1 op 12 pogingen kost het account, en
ongeveer 1 op 25 kost alleen de fee. Twee op de drie geslaagde pogingen zijn
binnen 30 dagen klaar. Reken op meerdere pogingen, niet op één.

---

## 3. Het gefunde account — elf jaar

$50.000 start, 2015-2025, doorgerold, cap op $500.000.

| | |
|---|---|
| opgenomen | $4.035.328 |
| eindbalans | $515.132 |
| **totaal** | **$4.550.460** |
| slechtste dag | **4,19%** van 5% |
| slechtste totaal | **4,60%** van 10% |
| trades | 12.555 |
| gemiddelde win rate | 57,2% |
| cap bereikt | 2016 |

Geen enkel jaar verloren. Daarbovenop komt de vaste uitbetaling van $10.000 per
maand zodra het account op 500K staat — vanaf 2016 zijn dat 115 maanden, dus
$600.000 tot $1.150.000 afhankelijk van of die onvoorwaardelijk is
(`5ERS_ANSWERS.md` §2).

---

## 4. Wat er onderzocht is en niet aangepast hoeft te worden

**Crypto: uit.** Over elf jaar $4.069.877 met tegen $4.107.981 zonder, dus
-0,93%, terwijl het 0,32 punt meer dagelijkse drawdown kost en op 1:2 hefboom
staat waar FX 1:100 krijgt. Data blijft staan, terugzetten is één regel.

**AUD_NZD, EUR_NZD, AUD_JPY: terug aan.** Ze stonden uit als "structureel
net-negatief in beide helften". Dat klopte niet meer op de huidige engine —
+10,8% over elf jaar, $335 winst per trade tegen $318 bij gelijk kapitaal. In de
tweede helft staan EUR_NZD (+$197/trade) en AUD_NZD (+$285/trade) juist bovenin.
Prijs: dagelijkse drawdown hoger in 8 van 9 vergelijkbare jaren, en de ergste
totale drawdown gaat van 3,60% naar 4,60%.

**Marge bindt nergens.** Bij de echte 5ers-hefbomen gebruikt het krapste moment
in een challenge 28,6% van wat beschikbaar is, en geen enkele order komt boven
22% van het symboolplafond.

**Risico differentiëren per symbool: niet doen.** De verwachtingswaarde per
symbool correleert +0,52 tussen 2015-2019 en 2020-2025. Genoeg om een
structurele verliezer weg te doen, niet genoeg om zwaarder in te zetten op wie
het vorige decennium won.

---

## 5. Wat er sinds het vorige oordeel is veranderd

Deze vier maken de oude cijfers ongeldig, niet alleen achterhaald:

1. **Het 50-lots plafond werkt nu ook in de backtest** (`4e71041`). De engine
   las `max_lot` terwijl `get_symbol_info` `volume_max` teruggeeft, miste dus
   altijd en viel terug op 100 lots — het dubbele van wat 5ers toestaat. Alle
   eerdere holdouts draaiden met die verruimde limiet.
2. **Cryptodata vervangen.** Wat "M15 vanaf 2020" heette waren uurbars vanaf
   2023 met 47% dekking en een gat van 48 dagen.
3. **XRP en ADA weg** — ze stonden in de universe terwijl 5ers ze niet aanbiedt.
4. **De drie FX-paren terug.**

---

## 5b. Twee metingen die tegen de verwachting in gingen

**NAS100 uitzetten helpt de challenge niet.** Dezelfde honderd vensters, gepaard:

| | met NAS100 | zonder |
|---|---|---|
| geslaagd | 88 | 88 |
| breach | **8** | **9** |
| mediaan | 19d | 20d |
| <=30 dagen | 68 | 65 |

Alle acht oorspronkelijke breaches blijven staan en er komt er een bij
(2022-05-17). Beide dingen zijn dus waar: op het gefunde account is NAS100
aantoonbaar schadelijk (enig symbool negatief in beide helften, profit factor
0,72 over 164 trades), en in de challengefase verandert uitzetten niets ten
goede. Een breach verschil op honderd vensters is ruis — dezelfde maat die
hierboven is aangelegd bij AUD_NZD.

Het blijft uit, maar op de expectancy-onderbouwing, niet omdat het gemeten de
challenge verbetert. Dat onderscheid hoort hier te staan.

**Brent heeft geen bruikbare historie voor 2022.** Een eerdere versie van dit
document zei dat Brent volledige data had. Dat was gebaseerd op het M15-bestand
alleen; de hogere timeframes zijn niet gecontroleerd:

| bestand | dekking |
|---|---|
| `XBR_USD_M15` | 2015 → 2025 |
| `XBR_USD_H4` | 2015 → 2025 |
| `XBR_USD_W1` | 2015 → 2025 |
| **`XBR_USD_D1`** | **2022 → 2025** |

De confluentie eist minstens 50 dagbars (`main_live_bot_backtest.py:3842`), dus
Brent kan voor 2022 geen signaal geven. De arm bevestigt dat: 2015 tot en met
2021 zijn cent voor cent identiek aan de arm zonder olie.

Over de vier jaar dat Brent wel handelde: $4.678.411 tegen $4.550.460 over het
hele decennium (+2,8%), en de ergste totale drawdown over 2022-2025 zakt van
4,60% naar 3,41%. Positief, maar het rust op vier jaar en twee van de vier
jaarverschillen zijn de bekende uitbetaling die over een jaargrens schuift. Om
dit te kunnen wegen is D1-data vanaf 2015 nodig — net als bij UK100 dus een
download, niet een configuratiewijziging.

---

## 6. Wat nog niet af is

* **Toewijzing van de 8 breaches.** AUD_NZD eruit halen verandert er niets aan
  (8 blijft 8, 7 van de 8 vensters gedeeld). EUR_NZD, AUD_JPY en NAS100 lopen
  nog. NAS100 is de enige met een echte hypothese: het is het enige symbool dat
  in beide helften verliest, en het verslechtert (-$41 naar -$122 per trade,
  profit factor 0,72).
* **Kostengevoeligheid.** Alles is gemeten op een vlakke spread van 1,0 pip over
  alle instrumenten. De sweep bij 0,5 / 1,0 / 2,0 pip is half af.
* **Nachtelijke de-risk om 22:00 UTC** is getuned onder datzelfde vlakke model,
  dat de spreadverbreding rond de rollover niet ziet. Live staat op 21:00.
* **Geen demoperiode gedraaid.** De configuratiecontrole is groen op vijf lagen,
  maar dat bewijst dat de instellingen kloppen, niet dat de code zich live
  identiek gedraagt.
