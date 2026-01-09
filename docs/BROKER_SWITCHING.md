# Broker Switching Guide

## Quick Start

### 1. Switch to Forex.com Demo (Testing)
```bash
python scripts/switch_broker.py demo
```

⚠️ **Account Size**: $50,000 (not $5,000)

Vul daarna je MT5 wachtwoord in `.env`:
```bash
MT5_PASSWORD=your_password_here
```

### 2. Test de verbinding
```bash
python -c "from broker_config import get_broker_config; get_broker_config().print_summary()"
```

### 3. Start de bot (eerste keer met --first-run)
```bash
python main_live_bot.py --first-run
```

---

## Switch to 5ers Live (Production)

⚠️ **ALLEEN NA SUCCESVOLLE DEMO TESTING!**

```bash
python scripts/switch_broker.py live
```

Je moet bevestigen door `YES` te typen.

Vul daarna je 5ers credentials in `.env`:
```bash
MT5_LOGIN=your_5ers_login
MT5_PASSWORD=your_5ers_password
MT5_SERVER=5ersLtd-Server
```

---

## Check Current Config

```bash
python scripts/switch_broker.py status
```

---

## Broker Comparison

| Metric | Forex.com Demo | 5ers Live |
|--------|----------------|-----------|
| Account Size | $50,000 | $60,000 |
| Is Demo | ✅ YES | ❌ NO (LIVE) |
| Risk per Trade | 0.6% ($300) | 0.6% ($360) |
| Max Daily DD | 5% ($2,500) | 5% ($3,000) |
| Max Total DD | 10% ($5,000) | 10% ($6,000) |
| Max Spread | 5 pips | 3 pips |
| Magic Number | 50000001 | 60000001 |
| Trade Crypto | ❌ NO | ✅ YES |

---

## Configuration Files

- `.env` - Active configuration (auto-switched)
- `.env.forexcom_demo` - Demo template
- `.env.fiveers_live` - Live template
- `.env.backup` - Previous config backup

---

## Testing Checklist (Demo)

Before switching to live:

1. ✅ Successful MT5 connection
2. ✅ Correct symbol mapping (verify with logs)
3. ✅ First-run scan completes
4. ✅ Spread checks working
5. ✅ 5-TP exit system correct
6. ✅ Drawdown monitor functioning
7. ✅ Weekend gap protection tested (Monday)
8. ✅ Daily scan timing correct (00:10 server time)

---

## Environment Variables

### Required for both brokers:
```bash
BROKER_TYPE=forexcom_demo  # or fiveers_live
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_server_name
ACCOUNT_SIZE=50000  # for Forex.com demo, or 60000 for 5ers
```

### Optional:
```bash
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
SCAN_INTERVAL_HOURS=4
SIGNAL_MODE=standard
```

**Note**: Forex.com demo uses $50,000 account size for realistic testing.

---

## Troubleshooting

### "MT5 connection failed"
- Verify MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in `.env`
- Check if MT5 terminal is running
- Try manually logging in to MT5 first

### "Symbol not found"
- Forex.com demo may have different symbol names
- Check `symbol_mapping.py` for correct broker format
- Some symbols may not be available on demo

### "First run scan takes long time"
- Normal! First scan analyzes all symbols
- Should complete within 5-10 minutes
- Next scans will be faster (4-hour interval)

---

## Safety Features

### Demo Mode Protections:
- Wider max spread (5 pips vs 3 pips)
- Same risk rules as 5ers for realistic testing
- Separate magic number (50000001)

### Live Mode Protections:
- Requires "YES" confirmation to switch
- Tighter max spread (3 pips)
- 5ers-compliant drawdown monitoring
- Fixed $60,000 account size

---

## Next Steps

1. **NOW**: Edit `.env` and add your Forex.com demo password
2. **Test**: Run `python main_live_bot.py --first-run`
3. **Monitor**: Check logs for any errors
4. **Verify**: Confirm all features working correctly
5. **Later**: When ready, switch to `fiveers_live`
