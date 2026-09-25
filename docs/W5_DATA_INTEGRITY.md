# Data-integriteit — wat er echt in de M15-bestanden zit

Aanleiding: de vraag waarom er voor BTC en ETH alleen data vanaf 2023 is. Het
antwoord bleek breder dan crypto. Onderstaande is gemeten met
`backtest/src/w5_data_audit.py`, niet afgelezen van bestandsnamen.

---

## De kern

Verschillende bestanden heten `*_M15_*` maar bevatten geen M15-data, en
verschillende heten `_2020_2025` maar beginnen in 2023.

| bestand | naam belooft | inhoud | gevolg |
|---|---|---|---|
| `BTC_USD_M15_2020_2025.csv` | M15 vanaf 2020 | **H1** vanaf **2023**, 47% dekking, gat van 48 dagen | crypto handelt alleen 2023+, op uurbars |
| `ETH_USD_M15_2020_2025.csv` | idem | idem | idem |
| `UK100_USD_M15_2020_2025.csv` | M15 | **dagbars**, 251 per jaar | UK100 staat in de universe maar handelt nooit |
| `SPX500_USD_M15_2020_2025.csv` | M15 | dagbars | niet in de 5ers-universe, dus onschadelijk |
| `NAS100_USD_M15_2020_2025.csv` | M15 | dagbars, 751 stuks | **vervangt echte M15-bars — zie hieronder** |
| FX en metals `_2020_2025` | vanaf 2020 | vanaf 2023 | onschadelijk: het `_2015_2025`-bestand dekt alles |

Daarnaast: **XRP_USD en ADA_USD staan in de verhandelbare lijst maar hebben geen
enkel databestand.** Ze worden stil overgeslagen — 2 van de 35 symbolen bestaan
in de backtest niet. Live handelt de bot ze wel, want MT5 heeft de data. Dat is
een verschil tussen backtest en live dat nergens gelogd wordt.

En **olie handelt nooit**: XBR/XTI hebben data van 2015 tot 2025, maar
`get_tradable_symbols()` levert voor `fiveers_live` geen enkel oliesymbool op.
De data ligt er ongebruikt.

---

## De enige die stille schade doet: NAS100

De loader plakt alle bestanden die op `{symbool}_M15_*` matchen aan elkaar
(`csv_mt5_simulator.py:756`) en gooit daarna dubbele tijdstempels weg met
`drop_duplicates(subset='time', keep='last')` (`:479`).

Voor FX en metals is dat onschadelijk: de overlappende rijen uit beide bestanden
zijn identiek (gecontroleerd, 0 van de 74.583 dubbele EUR_USD-tijdstempels heeft
een afwijkende close), dus welke wint maakt niet uit.

Voor NAS100 wél. Het `_2020_2025`-bestand bevat 751 **dagbars** op 00:00, precies
de tijdstempels waarop het goede `_2015_2025`-bestand een echte M15-bar heeft.
`keep='last'` laat de dagbar winnen. Gemeten via de echte laadroute:

```
NAS100_USD  3848 bars in januari 2023, spacing 15 min, mediane range 0,148%
   maar de bar op 2023-01-03 00:00:00 heeft een range van 2,966%
```

Een echte NAS100-M15-bar heeft een mediane range van 0,107%; een dagbar 1,226%.
Er zit dus één keer per handelsdag een bar in de reeks met de hoogte en diepte
van een hele dag, vermomd als vijftien minuten. Met `TDD_WORST_CASE=1` — de
standaard van deze ronde, die drawdown intrabar markeert tegen high en low —
markeert die ene bar tegen het bereik van een volledige dag. Stops en targets
binnen dat bereik worden op dat moment geraakt.

Omvang: 751 bars van de 186.722 (0,4%), en NAS100 levert 21 tot 27 trades per
jaar van de ~1.600. Klein, maar het is geen ruis in de data, het is verkeerde
data die de goede overschrijft.

**Wat het waard is om te doen:** `NAS100_USD_M15_2020_2025.csv` weghalen (en
`UK100_USD_M15_2020_2025.csv` en `SPX500_USD_M15_2020_2025.csv` mee, die bevatten
niets dan dagbars). Dat verandert de backtestresultaten en dus de bevroren
baseline, hoe klein ook — daarom is het hier gedocumenteerd en niet gedaan.
Het effect hoort eerst gemeten te worden op een jaar met en zonder.

---

## Wat dit betekent voor de resultaten die er al liggen

* **De FX- en metalenresultaten zijn niet geraakt.** Dat is het overgrote deel:
  in 2023 kwamen 1.604 van de 1.653 trades uit FX en 91 uit metals.
* **Crypto is nauwelijks getest.** 24 trades in 2023, op uurbars met 47%
  dekking. Elke uitspraak over hoe de strategie zich op crypto gedraagt rust
  daarop. De margemeting op crypto (zwaarste positie ETH 21,7%) rust op dezelfde
  24 trades.
* **De decade-resultaten 2015-2019 bevatten geen crypto**, simpelweg omdat er
  geen data is. Live zou de bot daar wel crypto verhandeld hebben.
* **NAS100 draagt 0,4% besmette bars.** Richting onbekend zonder meting.

---

## Reproduceren

```
uv run python3 backtest/src/w5_data_audit.py
```

Draait over alle `*_M15*.csv`, vergelijkt de belofte in de bestandsnaam met de
werkelijke eerste datum, de mediane afstand tussen bars en de tijdzone, en
markeert alles wat afwijkt.

---

## De per-symbool-studie meet niet wat hij lijkt te meten

`w5_per_symbol.py` draait elk jaar los op $50.000, om te voorkomen dat late
jaren zwaarder wegen puur doordat het account groter is. Dat lost een echt
probleem op en introduceert een ergere.

Zonder de scalingladder die een gefund account beschermt, loopt een slecht
begin tegen de 10%-muur en is de rekening dood voor de rest van dat jaar:

| jaar | trades | laatste trade |
|---|---|---|
| 2015 | 1.616 | 31 dec |
| **2016** | **311** | **10 maart** |
| 2017 | 1.661 | 29 dec |
| 2018 | 1.795 | 30 dec |
| **2019** | **174** | **13 februari** |
| 2020 | 1.970 | 31 dec |
| 2021 | 1.948 | 30 dec |
| **2022** | **1.077** | **10 augustus** |
| 2023 | 1.752 | 29 dec |
| 2024 | 1.648 | 31 dec |

Drie van de tien jaren duren zes weken tot acht maanden. De blootstelling is dus
ongeveer 4,3 jaar waar het er zes lijken, en welk symbool toevallig actief was
in zo'n kort venster weegt onevenredig zwaar.

**Dat is niet theoretisch.** UK100 kwam op $20 per trade uit over 2015-2017 en op
$144 over 2015-2020. Dat verschil is geen nieuwe informatie over UK100 — het is
dat de toegevoegde jaren vol waren terwijl twee van de eerste zes dat niet
waren. Op dat eerste cijfer is UK100 uitgezet; dat besluit rust dus op een
artefact.

De vervanger rolt de balans door zoals `w5_decade_crypto.py`, waar het account
de cap bereikt en alle elf jaar overleeft. Pas dan is elk jaar even lang en zijn
symbolen onderling vergelijkbaar.

**Wat hier algemener uit volgt:** een meting per jaar is pas vergelijkbaar als
elk jaar even lang duurt, en dat is bij een strategie die het account kan
verliezen niet vanzelfsprekend. Het aantal trades per jaar naast het resultaat
zetten is de goedkoopste manier om dit te zien — 174 tegen 1.970 valt op, een
verkeerd gemiddelde niet.

---

## Gedeelde werkmap tussen gelijktijdige armen — gevonden, gerepareerd, gecontroleerd

`w5_decade_crypto.run_year` gebruikte `tmp/dec_<jaar>` en `w5_per_symbol.run_year`
`tmp/psym_<jaar>`, beide zonder de arm in de naam, en beide beginnen met
`rmtree`. De toezichthouder draait de armen tegelijk. Twee armen die op hetzelfde
moment aan hetzelfde jaar werken wissen dus elkaars werkmap halverwege, schrijven
allebei `results.json` op dezelfde plek en lezen allebei wat er toevallig als
laatste staat. Dat faalt niet zichtbaar — het levert stil het verkeerde getal.
Beide zijn nu op de arm gesleuteld.

**Aanleiding.** Bij het nalopen van de drie index-armen was de ergste dagelijkse
drawdown in 8 van de 11 jaren tot op twee decimalen gelijk tussen `geen_index`
en `met_spx`, terwijl er ongeveer 45 SP500-trades per jaar bij kwamen.

**Uitkomst: de opgeslagen armen kloppen.** 2023 van `met_spx` is los herhaald via
dezelfde `run_year`, en komt cent voor cent terug op alle zeven velden:

| veld | opgeslagen | herhaald |
|---|---|---|
| opgenomen | $465.974,98 | $465.974,98 |
| eindbalans | $516.600,25 | $516.600,25 |
| niveau eind | $500.000 | $500.000 |
| trades | 1292 | 1292 |
| win rate | 57,1% | 57,1% |
| ergste dag | 1,85% | 1,85% |
| ergste totaal | 1,78% | 1,78% |

De gelijke drawdowns hadden de onschuldige verklaring: vanaf 2016 staat de balans
in beide armen op de $500.000-cap en wordt de winst bij elke mijlpaal
teruggenomen tot dat niveau, dus de noemer van het percentage is identiek. In de
jaren waarin SP500 wél op de slechtste dag in het boek zat lopen ze wel uiteen
(2020: 3,44% tegen 3,19%; 2021: 2,61 tegen 2,62; 2024: 2,62 tegen 2,63).

**Waarom dit toch een bug was.** De race bestond; hij is deze keer niet
afgegaan omdat de armen uit de pas liepen. Dat is geluk, geen veiligheid.

**En een waarschuwing over de controle zelf.** De eerste poging bouwde de
omgeving met de hand na en vergat de helft van `BASE_ENV` — de risicoregimes, de
noodtiers, de nachtelijke de-risk. Resultaat: 327 trades waar er 1292 hoorden te
staan, wat eruitzag als bewijs van datavervuiling en het niet was. Een
reproductiecontrole die de productiecode niet AANROEPT meet zijn eigen script.
