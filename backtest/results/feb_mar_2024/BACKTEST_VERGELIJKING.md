# BACKTEST VERGELIJKING - Feb/Mrt 2024

## 📊 RESULTATEN OVERZICHT

### HUIDIGE PARAMETERS (current_params.json)
```
Return:      +19.0% ($20,000 → $23,803.50)
Trades:      103
Win Rate:    49.5%
Max DDD:     3.68%
Max TDD:     0.00%
DDD Halts:   1
```

**Maandelijkse Breakdown:**
- Februari: 54 trades, 44.4% WR, $1,686 profit
- Maart: 49 trades, 55.1% WR, $2,117 profit

---

### BESTE OPTIMIZER TRIAL #26
```
Return:      +23.3% ($20,000 → $24,660)
Trades:      112
Win Rate:    50.0%
Max DDD:     3.29%
Max TDD:     0.00%
DDD Halts:   0
```

---

## 🎯 VERGELIJKING

| Metric | Huidige Params | Trial #26 | Verschil |
|--------|---------------|-----------|----------|
| **Return** | +19.0% | +23.3% | **+4.3%** ✅ |
| **Final Balance** | $23,803 | $24,660 | **+$857** ✅ |
| **Trades** | 103 | 112 | +9 |
| **Win Rate** | 49.5% | 50.0% | +0.5% |
| **Max DDD** | 3.68% | 3.29% | **-0.39%** ✅ |
| **DDD Halts** | 1 | 0 | **-1** ✅ |

---

## ✅ CONCLUSIE

**Trial #26 is BETER dan de huidige parameters:**

1. ✅ **Hogere return**: 23.3% vs 19.0% (+4.3% verschil)
2. ✅ **Betere risk**: 3.29% DDD vs 3.68% DDD
3. ✅ **Geen DDD halts**: 0 vs 1
4. ✅ **Iets hogere winrate**: 50.0% vs 49.5%
5. ✅ **Meer trades**: 112 vs 103 (betere opportunity capture)

---

## 🔄 AANBEVELING

**Implementeer Trial #26 parameters in main_live_bot.py:**

### Trial #26 Parameters:
```json
{
  "tp1_r_multiple": 0.4,
  "tp2_r_multiple": 1.1,
  "tp3_r_multiple": 2.4,
  "tp4_r_multiple": 3.9,
  "tp5_r_multiple": 5.0,
  "tp1_close_pct_weight": 0.55,
  "tp2_close_pct_weight": 0.35,
  "tp3_close_pct_weight": 0.30,
  "tp4_close_pct_weight": 0.25,
  "tp5_close_pct_weight": 0.35,
  "trail_activation_r": 1.1,
  "atr_trail_multiplier": 3.7,
  "use_atr_trailing": true,
  "trend_min_confluence": 4,
  "range_min_confluence": 7,
  "min_quality_factors": 2,
  "risk_per_trade_pct": 1.4,
  "compound_threshold_pct": 9.5
}
```

### Belangrijkste Verschillen met Huidige Params:
1. **5 TP levels** vs 3 TP levels (meer granulaire exits)
2. **Lagere trend confluence** (4 vs 6) = meer trade opportunities
3. **Hogere range confluence** (7 vs 4) = betere quality filtering
4. **Hogere compound threshold** (9.5% vs lager) = minder frequente lot updates

---

## 📝 VOLGENDE STAPPEN

1. ✅ Trial #26 parameters opgeslagen in `best_trial_26_params.json`
2. ⏳ Valideer met volledige 2023-2025 backtest
3. ⏳ Update `params/current_params.json` met Trial #26 parameters
4. ⏳ Test live met Trial #26 op demo account
5. ⏳ Deploy naar productie

---

**Gegenereerd:** 5 februari 2026
