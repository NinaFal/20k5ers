# Forex.com Demo Testing Guide

**Last Updated**: 2025-12-31  
**Purpose**: Test live bot functionality before 5ers deployment

---

## 📋 Overview

We use a **Forex.com MT5 demo account ($50,000)** to verify all bot functionality before going live with 5ers 60K High Stakes.

### Test Goals

| Feature | What to Verify |
|---------|----------------|
| Signal Generation | Signals match backtest logic |
| Order Execution | Orders placed correctly |
| Partial Exits | Market orders at TP levels |
| Trailing Stops | SL modification works |
| Risk Management | DD tracking, position sizing |
| Position Management | Multi-position handling |
| Logging | Complete, readable logs |

---

## ⚙️ Configuration

### 1. Environment Setup

Copy the example environment file:

```bash
cp .env.forexcom.example .env
```

Edit `.env` with your Forex.com credentials:

```bash
BROKER_TYPE=forexcom_demo
MT5_LOGIN=YOUR_FOREXCOM_DEMO_LOGIN
MT5_PASSWORD=YOUR_FOREXCOM_DEMO_PASSWORD
MT5_SERVER=FOREX.com-Demo
ACCOUNT_SIZE=50000
```

### 2. Risk Comparison

| Metric | Forex.com Demo ($50K) | 5ers Live ($60K) |
|--------|----------------------|------------------|
| Account | $50,000 | $60,000 |
| Risk % | 0.6% | 0.6% |
| Risk $ | $300 per R | $360 per R |
| Max Daily DD | $2,500 (5%) | $3,000 (5%) |
| Max Total DD | $5,000 (10%) | $6,000 (10%) |

---

## 🧪 Testing Workflow

### Phase 1: Connection Test (5 min)

```bash
# 1. Validate symbols
python scripts/validate_broker_symbols.py

# 2. Check output for:
# - All forex pairs found (28 symbols)
# - Metals found (XAU, XAG)
# - Indices found (US500, USTEC)
# - Crypto status (may not be available)

# 3. Update symbol_mapping.py if needed
```

### Phase 2: Dry Run (24 hours)

```bash
# Run without executing real trades
DRY_RUN=true python main_live_bot.py

# Monitor:
# - Signals generated at 22:05 UTC
# - No errors in logs
# - Memory stable
```

### Phase 3: Single Trade Test (1-2 days)

```bash
# Temporarily limit trading
# Edit broker_config.py: MAX_TRADES_PER_DAY = 1

python main_live_bot.py

# Verify:
# [ ] Order executed correctly
# [ ] SL set correctly
# [ ] Partial exits trigger at correct prices
# [ ] Trailing stop activates
```

### Phase 4: Full Test (1 week minimum)

```bash
# Enable all symbols and normal limits
python main_live_bot.py

# Daily checklist:
# [ ] Bot running without crashes
# [ ] Trades executed as expected
# [ ] Partial exits working
# [ ] Trailing stops working
# [ ] Risk manager updating correctly
# [ ] Logs readable and complete
```

---

## 📊 Expected Results

Based on backtest performance:

| Metric | Backtest | Expected Demo |
|--------|----------|---------------|
| Win Rate | 48.8% | ~48.8% |
| Monthly R | ~63R | ~63R |
| Monthly $ | - | ~$6,250 |

---

## ⚠️ Known Differences: Forex.com vs 5ers

### Symbol Names

| Asset | Forex.com | 5ers |
|-------|-----------|------|
| S&P 500 | US500 | US500.cash |
| Nasdaq | USTEC | US100.cash |
| Bitcoin | BTCUSD (may not exist) | BTCUSD |
| Ethereum | ETHUSD (may not exist) | ETHUSD |

### Spreads

- Forex.com demo may have wider spreads
- Set `MAX_SPREAD_PIPS = 5.0` in broker_config.py for demo

### Execution

- Demo execution faster than live
- Don't rely on demo slippage as indicator

---

## 🔄 Switching to 5ers Live

When demo testing is complete:

### 1. Update .env

```bash
BROKER_TYPE=fiveers_live
MT5_LOGIN=YOUR_5ERS_LIVE_LOGIN
MT5_PASSWORD=YOUR_5ERS_LIVE_PASSWORD
MT5_SERVER=5ersLtd-Server
ACCOUNT_SIZE=60000
```

### 2. Validate Symbols

```bash
python scripts/validate_broker_symbols.py
```

### 3. Start Live Trading

```bash
python main_live_bot.py
```

---

## ✅ Pre-Live Checklist

```
DEMO TESTING:
[ ] Forex.com MT5 demo account created
[ ] MT5 terminal installed on Windows VM
[ ] Bot code deployed
[ ] .env configured with Forex.com credentials

SYMBOL VALIDATION:
[ ] validate_broker_symbols.py executed
[ ] All expected symbols found
[ ] SYMBOL_MAP updated with correct names

FUNCTIONAL TESTING:
[ ] Connection test passed
[ ] Dry run completed (24h, no errors)
[ ] Single trade test successful
[ ] Full test completed (1 week)
[ ] Partial exits verified
[ ] Trailing stops verified
[ ] Risk manager verified

BEFORE 5ERS LIVE:
[ ] All demo tests passed
[ ] Trade logs reviewed
[ ] Performance matches backtest expectations
[ ] Config updated for 5ers
[ ] 5ers symbols validated
```

---

## 🛠️ Troubleshooting

### MT5 Connection Failed

```
Error: MT5 initialization failed
```

1. Is MT5 terminal running on Windows VM?
2. Are credentials correct?
3. Is server name exact (case-sensitive)?
4. Try setting `MT5_PATH` in .env

### Symbol Not Found

```
Warning: EUR_USD -> NOT FOUND
```

1. Run `validate_broker_symbols.py` to see available symbols
2. Update `OANDA_TO_FOREXCOM` in symbol_mapping.py
3. Add to `excluded_symbols` in broker_config.py if not available

### Spread Too Wide

```
Warning: Spread too wide for EURUSD (5.2 > 3.0 pips)
```

1. This is normal for demo accounts
2. Increase `max_spread_pips` in broker_config.py for testing
3. Reset to 3.0 for live trading

---

## 📁 Related Files

| File | Purpose |
|------|---------|
| [broker_config.py](../broker_config.py) | Multi-broker configuration |
| [symbol_mapping.py](../symbol_mapping.py) | Symbol name mapping |
| [.env.forexcom.example](../.env.forexcom.example) | Environment template |
| [validate_broker_symbols.py](../scripts/validate_broker_symbols.py) | Symbol validation script |
