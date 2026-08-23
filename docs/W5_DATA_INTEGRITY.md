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
