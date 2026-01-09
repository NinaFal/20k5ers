# Data Fetching in Live Bot

## ✅ Correct: MT5 API wordt gebruikt

De live bot haalt **GEEN** data van OANDA. Alle real-time data komt direct van de broker via MT5 API.

### Data Flow:

```
┌─────────────────────────────────────────────────────────────┐
│  BACKTESTING (Offline)                                      │
│  - Uses pre-downloaded data from data/ohlcv/               │
│  - Downloaded via OANDA API (scripts/download_h1_data.py)  │
│  - Yahoo Finance fallback for metals/indices/crypto        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  LIVE TRADING (Real-time)                                   │
│  - Uses MT5 API ONLY (mt5.copy_rates_from_pos())           │
│  - Data comes directly from broker (Forex.com or 5ers)     │
│  - OANDA is NOT used in live trading                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Code Verification

### [main_live_bot.py](../main_live_bot.py#L1000-L1021)
```python
def get_candle_data(self, symbol: str) -> Dict[str, List[Dict]]:
    """Get multi-timeframe candle data for a symbol."""
    broker_symbol = self.symbol_map.get(symbol, symbol)
    
    data = {
        "monthly": self.mt5.get_ohlcv(broker_symbol, "MN1", 24),
        "weekly": self.mt5.get_ohlcv(broker_symbol, "W1", 104),
        "daily": self.mt5.get_ohlcv(broker_symbol, "D1", 500),
        "h4": self.mt5.get_ohlcv(broker_symbol, "H4", 500),
    }
    return data
```

### [tradr/mt5/client.py](../tradr/mt5/client.py#L291-L330)
```python
def get_ohlcv(self, symbol: str, timeframe: str = "D1", count: int = 100):
    """Get OHLCV candle data."""
    mt5 = self._import_mt5()
    tf = timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_D1)
    
    # ✅ Direct MT5 API call
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    
    return candles
```

---

## Symbol Mapping

### Internal Format (OANDA-style)
- Used in strategy code: `EUR_USD`, `XAU_USD`, `SPX500_USD`
- Consistent with backtest data naming

### Broker Format
Automatically converted based on `BROKER_TYPE` environment variable:

| Internal | Forex.com Demo | 5ers Live |
|----------|----------------|-----------|
| EUR_USD | EURUSD | EURUSD |
| XAU_USD | XAUUSD | XAUUSD |
| SPX500_USD | US500 | US500.cash |
| NAS100_USD | USTEC | US100.cash |

### Mapping Logic
```python
# symbol_mapping.py provides broker-aware conversion
broker_symbol = get_broker_symbol("EUR_USD", broker="forexcom")  # -> "EURUSD"
broker_symbol = get_broker_symbol("SPX500_USD", broker="forexcom")  # -> "US500"
broker_symbol = get_broker_symbol("SPX500_USD", broker="fiveers")  # -> "US500.cash"
```

---

## Verification Steps

### 1. Verify Forex.com Symbol Names
```bash
# Edit .env and add Forex.com credentials first
python scripts/verify_forexcom_symbols.py
```

This will:
- Connect to Forex.com demo MT5
- List all available symbols
- Check which symbols match our mappings
- Suggest corrections if needed

### 2. Test Symbol Mapping
```python
from symbol_mapping import get_broker_symbol, print_broker_comparison

# Show differences between brokers
print_broker_comparison()
```

### 3. Test Live Connection
```bash
# Switch to Forex.com demo
python scripts/switch_broker.py demo

# Test connection (dry run)
python -c "
from broker_config import get_broker_config
config = get_broker_config()
config.print_summary()
"
```

---

## Common Issues

### ❌ "Symbol not found"
**Cause**: Symbol name differs between backtest data and broker

**Solution**: 
1. Run `verify_forexcom_symbols.py` to find correct name
2. Update `OANDA_TO_FOREXCOM` in `symbol_mapping.py`
3. Re-test connection

### ❌ "No data returned"
**Cause**: Symbol exists but no historical data available

**Solution**:
- Check if symbol is tradable (some demo accounts have limited symbols)
- Verify symbol is enabled in broker config (`trade_forex`, `trade_metals`, etc.)
- Try another timeframe (some symbols only have D1 data)

### ❌ "Connection refused"
**Cause**: MT5 terminal not running or credentials wrong

**Solution**:
1. Open MT5 terminal manually
2. Login with same credentials in MT5 GUI first
3. Verify `.env` has correct `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`

---

## Why MT5 API is Better than OANDA for Live Trading

| Feature | OANDA API | MT5 API |
|---------|-----------|---------|
| **Real-time** | ✅ Yes | ✅ Yes |
| **Broker-specific** | ❌ No | ✅ Yes (exact broker data) |
| **Spread accuracy** | ❌ Practice spreads | ✅ Real broker spreads |
| **Latency** | ~100-500ms | ~10-50ms (local) |
| **Reliability** | ⚠️ API rate limits | ✅ No limits |
| **Cost** | Free (practice) | Free |

**Bottom Line**: For live trading, **always use MT5 API** to get exact broker data with correct spreads and prices.

---

## Summary

✅ **Live bot uses MT5 API ONLY**  
✅ **Symbol mapping auto-detects broker**  
✅ **OANDA is only used for downloading backtest data**  
✅ **No API rate limits or latency issues**  
✅ **Real broker spreads and prices**  

Run `verify_forexcom_symbols.py` na het configureren van `.env` om te verifiëren dat alle symbols correct gemapped zijn!
