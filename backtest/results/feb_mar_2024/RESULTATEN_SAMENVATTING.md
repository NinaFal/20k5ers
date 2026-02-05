# Feb/Mar 2024 Optimizer Resultaten - Samenvatting

**Datum:** 5 februari 2026  
**Periode:** 2024-02-01 tot 2024-03-31 (2 maanden)  
**Startbalans:** $20,000  
**Totaal voltooide trials:** 27 van 50 (optimizer gestopt)

---

## 🏆 BESTE TRIAL: #26

**Prestaties:**
- Return: **+23.3%** ($24,660)
- Trades: **112**
- Win Rate: **50.0%**
- Max Daily DD: **3.29%** (binnen 5% limiet)
- Max Total DD: **0.00%**
- DDD Halts: **0** ✅
- Score: 55.28

**Parameters:**

### Take Profit Structuur (5 levels)
| Level | R-Multiple | Close % |
|-------|-----------|---------|
| TP1 | 0.4R | 55% |
| TP2 | 1.1R | 35% |
| TP3 | 2.4R | 30% |
| TP4 | 3.9R | 25% |
| TP5 | 5.0R | 35% |

### Trailing Stop
- Activation: **1.1R**
- ATR Multiplier: **3.7x**
- Use ATR Trailing: **Yes**

### Entry Filters
- Trend Min Confluence: **4**
- Range Min Confluence: **7**
- Min Quality Factors: **2**

### Risk Management
- Risk per Trade: **1.40%**
- Compound Threshold: **9.5%**

---

## 📊 TOP 5 TRIALS (gesorteerd op return)

| Trial | Return | Trades | Win% | DDD% | Halts | Score |
|-------|--------|--------|------|------|-------|-------|
| #26 | 23.3% | 112 | 50.0% | 3.29% | 0 | 55.3 |
| #19 | 22.6% | 100 | 53.0% | 2.68% | 0 | 56.5 |
| #23 | 21.9% | 104 | 51.9% | 2.73% | 0 | 52.3 |
| #24 | 21.4% | 109 | 49.5% | 2.87% | 0 | 62.0 |
| #25 | 21.4% | 109 | 51.9% | 2.73% | 0 | 60.6 |

---

## 📈 ALGEMENE STATISTIEKEN  

**Van 27 trials:**
- Trials met trades: **24**
- Trials met 0 trades: **3** (te strenge filters)

**Van 24 trials met trades:**
- Gemiddeld return: **16.7%**
- Gemiddeld winrate: **54.0%**
- Return ≥20%: **5 trials** (21%)
- Trials met DDD halts: **13** (54%)

**Return distributie:**
- ≥20%: 5 trials
- 15-20%: 7 trials
- 10-15%: 10 trials
- <10%: 2 trials

---

## 🎯 TOP 5 OP WINRATE

| Trial | Win% | Return | Trades | DDD% |
|-------|------|--------|--------|------|
| #9 | 62.5% | 13.8% | 64 | 3.08% |
| #6 | 60.2% | 13.5% | 88 | 3.61% |
| #8 | 60.0% | 14.7% | 70 | 2.60% |
| #7 | 58.9% | 13.8% | 90 | 3.50% |
| #14 | 57.0% | 12.9% | 86 | 3.84% |

*Opmerking: Trials met hoge winrate hebben lagere returns - trade-off tussen winrate en R-multiples*

---

## ⚠️ BELANGRIJKE OBSERVATIES

1. **Score vs Return Discrepantie**
   - Hoogste score (Trial #20): 63.4 score maar slechts 10.3% return met 1 halt
   - Hoogste return (Trial #26): 55.3 score maar 23.3% return zonder halts
   - **Conclusie:** Huidige scoring formule bevoordeelt trials met lage risk, maar het is beter om te focussen op return zonder halts

2. **DDD Halts Frequentie**
   - 54% van trials had 1+ DDD halts
   - Trials zonder halts hadden gemiddeld hogere returns
   - **Conclusie:** Aggressive risk (1.4-1.5%) werkt goed met juiste confluence filters

3. **Confluence Sweet Spot**
   - Beste trial: Trend=4, Range=7
   - Dit geeft 112 trades in 2 maanden (56/maand)
   - **Conclusie:** Lagere trend confluence (4-5) met hogere range confluence (7) genereert genoeg trades met quality

4. **TP Structuur Inzicht**
   - Beste trial gebruikt 5 niveaus met vroege exit op 0.4R (55%)
   - Grotere delen blijven open voor hogere R-multiples (2.4R, 3.9R, 5.0R)
   - **Conclusie:** Quick scalp + runners strategie werkt beter dan 3-TP systeem

---

## ✅ AANBEVELING

**Implementeer Trial #26 parameters** voor live trading omdat:
1. ✅ Hoogste return (23.3%) zonder DDD halts
2. ✅ Redelijke winrate (50%) met goed aantal trades (112)
3. ✅ Max DDD 3.29% (ruim binnen 5% limiet)
4. ✅ Compound threshold 9.5% = regelmatig lot size updates

**Volgende stappen:**
1. Run volledige backtest met Trial #26 parameters over 2023-2025
2. Valideer performance metrics
3. Sla parameters op in `params/current_params.json`

---

## 📁 BESTANDEN

- `trials_summary.json` - Alle 27 trials met metrics
- `best_trial_26_params.json` - Parameters van beste trial
- `optimizer_live.log` - Volledige optimizer log
- Dit rapport: Samenvatting en analyse

---

**Gegenereerd:** 5 februari 2026
