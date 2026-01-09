# PROPOSED CHANGES
Generated: 2026-01-03
Analyst: Claude Opus 4.5

## ⚠️ STATUS: PENDING APPROVAL

**GEEN van deze wijzigingen is uitgevoerd!**
Dit document is alleen een VOORSTEL.

---

## 1. FILES TO MOVE TO _deprecated/

### Rationale
Deze bestanden lijken niet actief gebruikt te worden OF zijn duplicates.
Ze worden NIET verwijderd, maar verplaatst naar `_deprecated/` folder.

| File | Reason | Confidence | Action |
|------|--------|------------|--------|
| `strategy.py` | Wrapper rond `strategy_core.py`, alleen `ScanResult` class wordt gebruikt door `trade_state.py` | MEDIUM | Move `ScanResult` to `strategy_core.py`, then deprecate |
| `trade_state.py` | Niet geïmporteerd door main entry points | HIGH | Verify if used at all, possible deprecate |
| `challenge_risk_manager.py` | Functions `can_trade`, `get_adjusted_risk_pct`, `record_trade`, `create_challenge_manager` niet gebruikt | MEDIUM | Review which functions are dead code |
| `tradr/data/dukascopy.py` | Niet geïmporteerd, alternatieve data provider | HIGH | Move to deprecated |
| `tradr/data/oanda.py` | Niet geïmporteerd, data komt uit CSV files | HIGH | Move to deprecated |
| `tradr/mt5/bridge_client.py` | Niet geïmporteerd, `client.py` wordt gebruikt | HIGH | Move to deprecated |
| `tradr/utils/state.py` | Niet geïmporteerd door andere modules | HIGH | Move to deprecated |
| `indicators.py` | Klein bestand (159 lines), alleen door `strategy_core.py` geïmporteerd | LOW | Keep - actively used |

### Scripts folder - KEEP (entry points)
| File | Status | Reason |
|------|--------|--------|
| `scripts/check_optuna_status.py` | ✅ KEEP | Entry point script |
| `scripts/download_oanda_data.py` | ✅ KEEP | Entry point script |
| `scripts/download_yahoo_data.py` | ✅ KEEP | Entry point script |
| `scripts/update_csvs.py` | ✅ KEEP | Entry point script |
| `scripts/update_docs.py` | ✅ KEEP | Entry point script |
| `scripts/validate_broker_symbols.py` | ✅ KEEP | Entry point script |
| `scripts/debug_validation_trades.py` | ✅ KEEP | Debug script |
| `scripts/quick_test_trades.py` | ✅ KEEP | Test script |

### Commands (DO NOT RUN YET)
```bash
mkdir -p _deprecated/tradr_data
mkdir -p _deprecated/tradr_mt5
mkdir -p _deprecated/tradr_utils

# After approval:
# mv tradr/data/dukascopy.py _deprecated/tradr_data/
# mv tradr/data/oanda.py _deprecated/tradr_data/
# mv tradr/mt5/bridge_client.py _deprecated/tradr_mt5/
# mv tradr/utils/state.py _deprecated/tradr_utils/
```

---

## 2. DUPLICATE CODE TO CONSOLIDATE

### 2.1 strategy.py vs strategy_core.py

**Analysis:**
- `strategy.py`: 211 lines, 9 definitions
- `strategy_core.py`: 3102 lines, 50 definitions
- `strategy.py` imports FROM `strategy_core.py` and wraps it

**Import chain:**
```
strategy_core.py  ← ftmo_challenge_analyzer.py (direct)
strategy_core.py  ← main_live_bot.py (direct)
strategy_core.py  ← strategy.py ← trade_state.py (indirect via ScanResult)
```

**Conclusion:**
- `strategy_core.py` is de KERN - behouden
- `strategy.py` is een wrapper die alleen `ScanResult` class toevoegt
- `ScanResult` wordt ALLEEN gebruikt door `trade_state.py`

**Aanbevolen actie:**
1. [ ] Verifieer of `trade_state.py` actief gebruikt wordt
2. [ ] Als niet gebruikt: deprecate beide `strategy.py` EN `trade_state.py`
3. [ ] Als wel gebruikt: move `ScanResult` naar `strategy_core.py`, deprecate `strategy.py`

### 2.2 Duplicate Functions in Code

De volgende functies zijn GEDUPLICEERD tussen files:

| Function | Files | Severity | Action |
|----------|-------|----------|--------|
| `_atr` | `ftmo_challenge_analyzer.py`, `strategy_core.py` | 🔴 HIGH | Consolidate to one location |
| `_calculate_atr_percentile` | `ftmo_challenge_analyzer.py`, `strategy_core.py` | 🔴 HIGH | Consolidate |
| `calculate_adx` | `ftmo_challenge_analyzer.py`, `strategy_core.py` | 🔴 HIGH | Consolidate |
| `daily_loss_pct` | `ftmo_challenge_analyzer.py`, `tradr/risk/manager.py` | 🟡 MEDIUM | Review if same logic |
| `get_contract_specs` | `symbol_mapping.py`, `tradr/risk/position_sizing.py` | 🟡 MEDIUM | Consolidate |
| `close_position` | `tradr/mt5/bridge_client.py`, `tradr/mt5/client.py` | 🟢 LOW | One is deprecated |

**Aanbevolen consolidatie:**
1. Maak `indicators.py` de centrale locatie voor: `_atr`, `_calculate_atr_percentile`, `calculate_adx`
2. Laat andere files van daaruit importeren

---

## 3. DATA NAMING TO NORMALIZE

### Current State
- **Files with OANDA format** (e.g., `EUR_USD_H4`): ~100 files
- **Files with MT5 format** (e.g., `EURUSD_H4`): ~224 files
- **Total files**: 324 CSV files
- **Confirmed DUPLICATES**: 9 symbols have BOTH formats (EUR_USD, GBP_USD, USD_JPY, USD_CAD, USD_CHF, AUD_USD, NZD_USD, GBP_JPY, EUR_JPY)

### Code Usage Analysis
```
EUR_USD (OANDA format): 16 occurrences in Python code
EURUSD (MT5 format): 14 occurrences in Python code
```

### Proposed Standard
**Use OANDA format with underscore: `EUR_USD`**

Rationale:
- Matches `symbol_mapping.py` internal format
- Matches documentation in `.github/copilot-instructions.md`
- Easier parsing (consistent delimiter)

### Duplicate Files to Remove (after verification)
| Keep (OANDA) | Remove (duplicate) |
|--------------|-------------------|
| `EUR_USD_H4_2003_2025.csv` | `EURUSD_H4_2003_2025.csv` |
| `GBP_USD_H4_2003_2025.csv` | `GBPUSD_H4_2003_2025.csv` |
| ... | ... |

**WAIT**: First verify both files contain same data!

---

## 4. CONFIG TO CONSOLIDATE

### Current Sources
| Config Source | Purpose | Keys | Status |
|---------------|---------|------|--------|
| `config.py` | General settings, symbols, contract specs | ~30 | ✅ Primary |
| `ftmo_config.py` | 5ers challenge rules, TP/SL settings | ~20 | ✅ Primary |
| `broker_config.py` | Multi-broker configuration | ~15 | ✅ Primary |
| `challenge_rules.py` | ChallengeRules dataclass | 1 class | 🟡 Could merge into ftmo_config |
| `params/current_params.json` | Optimized strategy parameters | 30 | ✅ Keep separate |
| `params/optimization_config.json` | Optimization mode settings | ~10 | ✅ Keep separate |

### Potential Conflicts Found
| Variable | Files | Resolution |
|----------|-------|------------|
| `ACCOUNT_SIZE` | `config.py`, `broker_config.py` | `config.py` uses from `ftmo_config`, broker_config is per-broker |
| `FOREX_PAIRS` | `config.py`, `broker_config.py` | Different purpose - config is master list, broker is available symbols |

### Proposed Hierarchy
```
ftmo_config.py        → 5ers rules (source of truth for limits)
       ↓
config.py            → General config, imports from ftmo_config
       ↓
broker_config.py     → Per-broker overrides
       ↓
params/*.json        → Runtime parameters (separate from code)
```

**Aanbevolen actie:**
1. [ ] Merge `challenge_rules.py` into `ftmo_config.py` (only 58 lines)
2. [ ] Document the config hierarchy in README

---

## 5. DEAD CODE TO REMOVE

Based on dead code analysis, these functions are NEVER called:

### HIGH CONFIDENCE (can remove)
| File | Function | Reason |
|------|----------|--------|
| `config.py` | `all_market_instruments()` | Not used anywhere |
| `ftmo_config.py` | `is_asset_whitelisted()` | Not used anywhere |
| `ftmo_config.py` | `should_halt_trading()` | Not used anywhere |
| `ftmo_config.py` | `get_adjusted_loss_streak()` | Not used anywhere |
| `challenge_risk_manager.py` | `can_trade()` | Not used anywhere |
| `challenge_risk_manager.py` | `get_adjusted_risk_pct()` | Not used anywhere |
| `challenge_risk_manager.py` | `record_trade()` | Not used anywhere |
| `challenge_risk_manager.py` | `create_challenge_manager()` | Not used anywhere |

### MEDIUM CONFIDENCE (verify first)
| File | Function | Reason |
|------|----------|--------|
| `ftmo_challenge_analyzer.py` | `check_adx_filter()` | May be called dynamically |
| `ftmo_challenge_analyzer.py` | `peak_to_trough_dd_pct()` | May be internal helper |

---

## 6. DOCUMENTATION TO UPDATE

| Document | Status | Issues Found |
|----------|--------|--------------|
| `README.md` | 🟡 Review | References correct files but may need architecture update |
| `docs/ARCHITECTURE.md` | 🟡 Review | May not reflect current duplicate situation |
| `docs/STRATEGY_GUIDE.md` | ✅ OK | Matches strategy_core.py |
| `.github/copilot-instructions.md` | ✅ OK | Accurate and detailed |

---

## APPROVAL REQUIRED

Before executing any changes:

1. [ ] Review this document completely
2. [ ] Confirm each HIGH CONFIDENCE item
3. [ ] Verify duplicate data files contain same data
4. [ ] Test that deprecated code is truly unused
5. [ ] Create backup (DONE: `backup-before-cleanup-20260103-202804`)
6. [ ] Execute changes one by one
7. [ ] Run tests after each change

---

## PRIORITY ORDER

If approved, execute in this order:

1. **P1 - Data cleanup**: Remove duplicate CSV files (after verification)
2. **P2 - Dead code**: Remove unused functions
3. **P3 - Deprecate modules**: Move unused modules to `_deprecated/`
4. **P4 - Consolidate duplicates**: Merge duplicate functions
5. **P5 - Config cleanup**: Merge `challenge_rules.py` into `ftmo_config.py`
6. **P6 - Documentation**: Update after all changes
