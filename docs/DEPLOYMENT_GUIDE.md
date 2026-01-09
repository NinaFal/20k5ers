# Deployment Guide

**Last Updated**: 2025-12-31

---

## Prerequisites

### Development Environment (Linux/Mac)
- Python 3.11+
- Git
- 8GB+ RAM
- SSD storage recommended

### Production Environment (Windows VM)
- Windows Server 2016+ or Windows 10/11 (64-bit)
- Python 3.11+
- MetaTrader 5 terminal
- Broker account credentials (Forex.com or 5ers)
- 24/7 uptime (VPS recommended)

---

## Installation Steps

### 1. Clone Repository
```bash
git clone https://github.com/TheTradrBot/ftmotrial.git
cd ftmotrial
```

### 2. Install Dependencies

**Linux/Mac** (optimizer):
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows** (live bot):
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install MetaTrader5  # Windows only
```

### 3. Configure Environment

Create `.env` file in project root:

**For Forex.com Demo**:
```bash
BROKER_TYPE=forexcom_demo
MT5_SERVER=Forex.comGlobal-Demo
MT5_LOGIN=your_login_number
MT5_PASSWORD=your_password
```

**For 5ers Live**:
```bash
BROKER_TYPE=fiveers_live
MT5_SERVER=5ers-Live
MT5_LOGIN=your_login_number
MT5_PASSWORD=your_password
```

### 4. Verify Setup
```bash
python -c "from params.params_loader import load_strategy_params; p = load_strategy_params(); print(f'Params loaded: min_confluence={p.min_confluence}')"
```

Expected output:
```
Params loaded: min_confluence=2
```

---

## Running the Live Bot

### Manual Start
```bash
cd C:\Users\Administrator\ftmotrial
venv\Scripts\activate
python main_live_bot.py
```

### Windows Task Scheduler (24/7 Operation)

1. Open Task Scheduler
2. Create New Task: `FTMO_Live_Bot`
3. Trigger: At startup
4. Action: Start a program
   - Program: `C:\Users\Administrator\ftmotrial\venv\Scripts\python.exe`
   - Arguments: `main_live_bot.py`
   - Start in: `C:\Users\Administrator\ftmotrial`
5. Settings:
   - ✅ Run whether user is logged on or not
   - ✅ Run with highest privileges
   - ✅ If the task fails, restart every 1 minute

### Restart After Code Update
```cmd
cd C:\Users\Administrator\ftmotrial
git pull
schtasks /End /TN "FTMO_Live_Bot"
schtasks /Run /TN "FTMO_Live_Bot"
```

---

## Running Optimization

### Local Run
```bash
# Single run (100 trials)
python ftmo_challenge_analyzer.py --single --trials 100

# Check progress
python ftmo_challenge_analyzer.py --status

# Show current configuration
python ftmo_challenge_analyzer.py --config
```

### Background Run (Recommended)
```bash
# TPE single-objective
./run_optimization.sh --single --trials 100

# NSGA-II multi-objective
./run_optimization.sh --multi --trials 100

# Monitor progress
tail -f ftmo_analysis_output/TPE/run.log
```

### Validation Mode
```bash
# Test parameters on different date range
python ftmo_challenge_analyzer.py --validate --start 2020-01-01 --end 2022-12-31
```

---

## Live Bot Features

### Scan Timing
- **22:05 UTC**: Daily close scan (only time)
- Ensures complete daily candles
- Matches backtest exactly

### Spread Monitoring
- Fresh signals saved to `awaiting_spread.json` if spread too wide
- Every 10 minutes: check if spread improved
- Good spread → Execute with MARKET ORDER
- Signals expire after 12 hours

### Entry Filter: Spread Quality Only
- **No session filter** - signals checked for spread only
- Spread OK → Execute immediately with market order
- Spread wide → Save to `awaiting_spread.json` for retry

### 3-Tier Graduated Risk
| Tier | Daily DD | Action |
|------|----------|--------|
| 1 | ≥2.0% | Reduce risk: 0.6% → 0.4% |
| 2 | ≥3.5% | Cancel all pending orders |
| 3 | ≥4.5% | Emergency close positions |

### Partial Take Profits
- **TP1**: Close 45% at 0.8-1R, move SL to BE+buffer
- **TP2**: Close 30% at 2R
- **TP3**: Close 25% at 3-4R
- All closes use MARKET ORDERS
- Checked every 30 seconds

---

## Persistence Files

| File | Purpose | Location |
|------|---------|----------|
| `pending_setups.json` | Pending limit orders | Project root |
| `awaiting_spread.json` | Signals waiting for spread | Project root |
| `challenge_state.json` | Risk manager state | Project root |
| `trading_days.json` | Profitable days tracking | Project root |

---

## Troubleshooting

### Bot Not Starting
1. Check MT5 is installed and terminal is running
2. Verify `.env` credentials
3. Check Task Scheduler logs

### No Trades Being Placed
1. Check logs in `logs/tradr_live.log`
2. Verify session hours (08:00-22:00 UTC)
3. Check spread requirements

### Connection Issues
```bash
# Test MT5 connection
python -c "from tradr.mt5.client import MT5Client; c = MT5Client('server', 'login', 'pass'); print(c.connect())"
```

### Symbol Mapping Issues
```bash
# Verify symbol mapping
python -c "from symbol_mapping import get_broker_symbol; print(get_broker_symbol('EUR_USD', 'forexcom'))"
```

---

## Monitoring

### Log Files
- `logs/tradr_live.log` - Main bot log
- `ftmo_analysis_output/TPE/run.log` - Optimization output
- `ftmo_analysis_output/TPE/optimization.log` - Trial results

### Key Log Messages
```
DAILY CLOSE SCAN (22:05 UTC)     # Scanning for signals
[EUR_USD] Signal found: BUY      # Signal detected
[EUR_USD] MARKET ORDER FILLED    # Trade executed
TP1 HIT! Closing 45%             # Partial profit taken
TIER 1 WARNING: Daily Loss 2%   # Risk reduction activated
```

---

## Multi-Broker Configuration

### Forex.com Demo ($50K)
```python
# broker_config.py settings:
account_size=50000
risk_per_trade_pct=0.6
excluded_symbols=['JPY pairs', 'XAG_USD']  # Min lot issues
```

### 5ers Live ($60K)
```python
# broker_config.py settings:
account_size=60000
risk_per_trade_pct=0.6
excluded_symbols=[]  # All symbols available
```

---

**Last Updated**: 2025-12-31
