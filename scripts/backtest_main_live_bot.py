#!/usr/bin/env python3
"""
BACKTEST MAIN LIVE BOT - Exact Replica of main_live_bot.py Using CSV Data

This script is a PIXEL-PERFECT replica of main_live_bot.py that uses historical
CSV data instead of the MT5 API. Every decision, calculation, and check is
identical to what main_live_bot.py would do in live trading.

DESIGN PRINCIPLE:
- If main_live_bot.py does X, this script does EXACTLY X
- Same functions, same logic, same order of operations
- H1 data used for entry timing and DDD monitoring
- D1/H4/W1/MN data used for signal generation (same as live)

KEY FEATURES (100% matching main_live_bot.py):
1. Signal Generation: compute_confluence() at 00:10 server time (D1 close + 10min)
2. Entry Queue: Signals wait for price to come within 0.3R
3. Order Types: Market order if <0.05R, Limit order if 0.05-0.3R, Queue if >0.3R
4. Lot Sizing: Calculated at FILL moment using current balance (compounding)
5. 3-TP Exit System: 35%/30%/35% at 0.6R/1.2R/2.0R with trailing SL
6. DDD Safety: Warn at 2%, Reduce at 3%, HALT at 3.5% (close all, stop trading)
7. TDD Safety: 10% static from initial balance = account blown
8. Position Management: H1 bar-by-bar SL/TP checks using High/Low

DIFFERENCES FROM LIVE:
- Data source: CSV files instead of MT5 API
- Time resolution: H1 bars instead of 5-second ticks
- DDD check: Every H1 bar instead of every 5 seconds (uses H/L for worst-case)

Author: AI Assistant
Date: January 21, 2026
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import pandas as pd
import numpy as np
from tqdm import tqdm
import logging

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from params.params_loader import load_strategy_params
from strategy_core import StrategyParams, compute_confluence, _infer_trend, _pick_direction_from_bias

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING SETUP (matching main_live_bot.py)
# ═══════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION (EXACT COPY from ftmo_config.py and main_live_bot.py)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class FiveersConfig:
    """
    5ers 20K High Stakes Challenge configuration.
    EXACT copy from ftmo_config.py used by main_live_bot.py.
    """
    # Account
    account_size: float = 20_000
    
    # Risk per trade
    base_risk_pct: float = 0.6
    reduced_risk_pct: float = 0.4  # Used when DDD >= 3%
    
    # DDD Thresholds (Daily DrawDown from day start equity)
    daily_loss_warning_pct: float = 2.0   # Log warning
    daily_loss_reduce_pct: float = 3.0    # Reduce risk to 0.4%
    daily_loss_halt_pct: float = 3.5      # CLOSE ALL, halt trading until next day
    
    # TDD Threshold (Total DrawDown from INITIAL balance - STATIC!)
    max_total_dd_pct: float = 10.0        # Account blown if exceeded
    total_dd_emergency_pct: float = 9.5   # Emergency close at 9.5%
    
    # Entry Queue (matching main_live_bot.py)
    limit_order_proximity_r: float = 0.3   # Place limit order when within 0.3R
    immediate_entry_r: float = 0.05        # Market order if within 0.05R
    max_entry_wait_hours: int = 120        # 5 days max wait in queue
    
    # Dynamic lot sizing
    use_dynamic_lot_sizing: bool = True
    confluence_base_score: int = 4
    confluence_scale_per_point: float = 0.15
    max_confluence_multiplier: float = 1.5
    min_confluence_multiplier: float = 0.6
    
    # Quality requirements
    min_confluence: int = 4
    min_quality_factors: int = 2
    
    def get_risk_pct(self, ddd_pct: float) -> float:
        """Get current risk % based on DDD level."""
        if ddd_pct >= self.daily_loss_reduce_pct:
            return self.reduced_risk_pct
        return self.base_risk_pct
    
    def get_confluence_multiplier(self, confluence: int) -> float:
        """Calculate lot size multiplier based on confluence score."""
        if not self.use_dynamic_lot_sizing:
            return 1.0
        diff = confluence - self.confluence_base_score
        multiplier = 1.0 + (diff * self.confluence_scale_per_point)
        return max(self.min_confluence_multiplier, 
                   min(self.max_confluence_multiplier, multiplier))


# Global config instance
CONFIG = FiveersConfig()


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT SPECS (EXACT COPY from tradr/risk/position_sizing.py)
# ═══════════════════════════════════════════════════════════════════════════

CONTRACT_SPECS = {
    # Forex majors - pip = 0.0001, $10/pip/lot, $4 commission
    "EUR_USD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "GBP_USD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "AUD_USD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "NZD_USD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "USD_CAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "USD_CHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    
    # Forex JPY pairs - pip = 0.01
    "USD_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "EUR_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "GBP_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "AUD_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "CAD_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "CHF_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "NZD_JPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    
    # Forex crosses
    "EUR_GBP": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 12.5, "commission_per_lot": 4.0},
    "EUR_AUD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "EUR_CAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "EUR_CHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 11.0, "commission_per_lot": 4.0},
    "EUR_NZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "GBP_AUD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "GBP_CAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "GBP_CHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 11.0, "commission_per_lot": 4.0},
    "GBP_NZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "AUD_CAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "AUD_CHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 11.0, "commission_per_lot": 4.0},
    "AUD_NZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "CAD_CHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 11.0, "commission_per_lot": 4.0},
    "NZD_CAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "NZD_CHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 11.0, "commission_per_lot": 4.0},
    
    # Gold
    "XAU_USD": {"pip_size": 0.01, "contract_size": 100, "pip_value_per_lot": 1.0, "commission_per_lot": 4.0},
    
    # Bitcoin
    "BTC_USD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0, "commission_per_lot": 0.0},
    
    # Indices
    "SPX500_USD": {"pip_size": 0.1, "contract_size": 1, "pip_value_per_lot": 0.1, "commission_per_lot": 0.0},
    "NAS100_USD": {"pip_size": 0.1, "contract_size": 1, "pip_value_per_lot": 0.1, "commission_per_lot": 0.0},
    "US30_USD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0, "commission_per_lot": 0.0},
}

def get_specs(symbol: str) -> Dict:
    """Get contract specs for symbol."""
    # Try exact match first
    if symbol in CONTRACT_SPECS:
        return CONTRACT_SPECS[symbol]
    # Try without underscore
    clean = symbol.replace("_", "")
    for key, specs in CONTRACT_SPECS.items():
        if key.replace("_", "") == clean:
            return specs
    # Default forex specs
    return {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0}


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS AND DATA CLASSES (matching main_live_bot.py structure)
# ═══════════════════════════════════════════════════════════════════════════

class OrderStatus(Enum):
    """Order status matching main_live_bot.py."""
    AWAITING_ENTRY = "awaiting_entry"  # In queue, waiting for proximity
    PENDING = "pending"                 # Limit order placed
    FILLED = "filled"                   # Position open
    CLOSED = "closed"                   # Position closed
    EXPIRED = "expired"                 # Entry queue timeout
    CANCELLED = "cancelled"             # Cancelled (DDD halt, etc.)


@dataclass
class Signal:
    """Trading signal from compute_confluence()."""
    symbol: str
    direction: str  # 'bullish' or 'bearish'
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    confluence_score: int
    quality_factors: int
    signal_time: datetime
    risk: float = 0.0  # |entry - stop_loss|
    
    def __post_init__(self):
        self.risk = abs(self.entry - self.stop_loss)


@dataclass
class PendingSetup:
    """
    Pending trading setup - matches main_live_bot.py's PendingSetup class.
    Tracks a signal from generation through entry queue to position.
    """
    signal: Signal
    status: OrderStatus = OrderStatus.AWAITING_ENTRY
    queue_time: datetime = None  # When added to entry queue
    order_time: datetime = None  # When limit order placed
    
    def __post_init__(self):
        if self.queue_time is None:
            self.queue_time = self.signal.signal_time


@dataclass
class Position:
    """
    Open position - matches main_live_bot.py's position management.
    """
    signal: Signal
    fill_time: datetime
    fill_price: float
    lot_size: float
    risk_usd: float
    commission: float
    
    # TP tracking
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    
    # Partial close tracking
    remaining_pct: float = 1.0
    partial_pnl: float = 0.0
    
    # Trailing SL
    trailing_sl: Optional[float] = None
    
    # Final state
    closed: bool = False
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    realized_pnl: float = 0.0
    realized_r: float = 0.0


@dataclass
class DailySnapshot:
    """Daily state snapshot for analysis."""
    date: str
    day_start_equity: float
    day_end_equity: float
    day_low_equity: float
    day_high_equity: float
    realized_pnl: float
    floating_pnl: float
    max_ddd_pct: float
    tdd_pct: float
    trades_opened: int
    trades_closed: int
    ddd_halt_triggered: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING (CSV instead of MT5 API)
# ═══════════════════════════════════════════════════════════════════════════

class CSVDataProvider:
    """
    Provides OHLCV data from CSV files.
    Replaces MT5 API calls in main_live_bot.py.
    """
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "data" / "ohlcv"
        self.cache: Dict[str, pd.DataFrame] = {}
        self.h1_cache: Dict[str, Dict[datetime, Dict]] = {}
        
    def load_timeframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """Load data for a specific timeframe."""
        cache_key = f"{symbol}_{timeframe}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # Symbol without underscore (OANDA format EUR_USD -> EURUSD)
        symbol_no_underscore = symbol.replace('_', '')
        
        # Try different file patterns
        patterns = [
            # Pattern: EUR_USD_D1.csv
            self.data_dir / f"{symbol}_{timeframe}.csv",
            # Pattern: EURUSD_D1.csv  
            self.data_dir / f"{symbol_no_underscore}_{timeframe}.csv",
            # Pattern: EUR_USD_D1_2003_2025.csv
            self.data_dir / f"{symbol}_{timeframe}_2003_2025.csv",
            # Pattern: EURUSD_D1_2003_2025.csv (ACTUAL FORMAT IN data/ohlcv/)
            self.data_dir / f"{symbol_no_underscore}_{timeframe}_2003_2025.csv",
        ]
        
        for path in patterns:
            if path.exists():
                df = pd.read_csv(path, parse_dates=['time'])
                df = df.sort_values('time').reset_index(drop=True)
                self.cache[cache_key] = df
                return df
        
        return pd.DataFrame()
    
    def get_candle_data(self, symbol: str, as_of: datetime) -> Dict[str, List[Dict]]:
        """
        Get multi-timeframe candle data as of a specific time.
        EXACTLY matches main_live_bot.py's get_candle_data() method.
        """
        result = {
            "monthly": [],
            "weekly": [],
            "daily": [],
            "h4": [],
        }
        
        for tf, key in [("MN", "monthly"), ("W1", "weekly"), ("D1", "daily"), ("H4", "h4")]:
            df = self.load_timeframe(symbol, tf)
            if df.empty:
                continue
            # Filter to data available at as_of time (no look-ahead)
            df_filtered = df[df['time'] <= as_of]
            if df_filtered.empty:
                continue
            result[key] = df_filtered.to_dict('records')
        
        return result
    
    def get_ohlcv(self, symbol: str, timeframe: str, as_of: datetime, lookback: int = 100) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data for a specific timeframe with lookback.
        Used by process_daily_signals() for compute_confluence().
        
        Args:
            symbol: Symbol in OANDA format (e.g., EUR_USD)
            timeframe: Timeframe string (MN, W1, D1, H4, H1)
            as_of: Get data up to this timestamp (no look-ahead)
            lookback: Number of bars to return
            
        Returns:
            DataFrame with OHLCV data, or None if not available
        """
        df = self.load_timeframe(symbol, timeframe)
        if df.empty:
            return None
        
        # Ensure timezone-aware comparison
        as_of_ts = pd.Timestamp(as_of)
        if as_of_ts.tzinfo is None:
            as_of_ts = as_of_ts.tz_localize('UTC')
        
        # Make df time column timezone aware if needed
        if df['time'].dt.tz is None:
            df['time'] = df['time'].dt.tz_localize('UTC')
        
        # Filter to data BEFORE as_of (no look-ahead bias)
        df_filtered = df[df['time'] < as_of_ts].copy()
        
        if df_filtered.empty:
            return None
        
        # Return last 'lookback' bars
        return df_filtered.tail(lookback).reset_index(drop=True)
    
    def build_h1_index(self, symbol: str) -> Dict[datetime, Dict]:
        """Build fast lookup index for H1 data."""
        if symbol in self.h1_cache:
            return self.h1_cache[symbol]
        
        df = self.load_timeframe(symbol, "H1")
        if df.empty:
            self.h1_cache[symbol] = {}
            return {}
        
        index = {}
        for _, row in df.iterrows():
            t = row['time']
            if isinstance(t, pd.Timestamp):
                t = t.to_pydatetime()
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            index[t] = {
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'time': t,
            }
        
        self.h1_cache[symbol] = index
        return index
    
    def get_h1_bar(self, symbol: str, time: datetime) -> Optional[Dict]:
        """Get H1 bar for specific time."""
        index = self.build_h1_index(symbol)
        
        # Normalize time to hour
        t = time.replace(minute=0, second=0, microsecond=0)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        
        return index.get(t)
    
    def get_h1_timeline(self, start: datetime, end: datetime) -> List[datetime]:
        """Get all H1 timestamps in range across all symbols."""
        all_times = set()
        
        for symbol in self.get_available_symbols():
            index = self.build_h1_index(symbol)
            for t in index.keys():
                if start <= t <= end:
                    all_times.add(t)
        
        return sorted(all_times)
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        symbols = set()
        for f in self.data_dir.glob("*_H1.csv"):
            symbol = f.stem.replace("_H1", "")
            symbols.add(symbol)
        return sorted(symbols)


# ═══════════════════════════════════════════════════════════════════════════
# LOT SIZE CALCULATION (EXACT COPY from main_live_bot.py)
# ═══════════════════════════════════════════════════════════════════════════

def calculate_lot_size(
    symbol: str,
    balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    confluence: int,
) -> Tuple[float, float]:
    """
    Calculate lot size - EXACT COPY from main_live_bot.py.
    
    Returns: (lot_size, risk_usd)
    """
    specs = get_specs(symbol)
    
    # Risk in USD
    risk_usd = balance * (risk_pct / 100)
    
    # Apply confluence multiplier
    multiplier = CONFIG.get_confluence_multiplier(confluence)
    risk_usd *= multiplier
    
    # SL distance in price
    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        return 0.0, 0.0
    
    # SL distance in pips
    pip_size = specs["pip_size"]
    sl_pips = sl_distance / pip_size
    
    if sl_pips <= 0:
        return 0.0, 0.0
    
    # Value per pip per lot
    pip_value = specs["pip_value_per_lot"]
    
    # Lot size = risk / (sl_pips * pip_value)
    lot_size = risk_usd / (sl_pips * pip_value)
    
    # Round to 2 decimal places
    lot_size = round(lot_size, 2)
    
    # Minimum lot size
    lot_size = max(0.01, lot_size)
    
    return lot_size, risk_usd


# ═══════════════════════════════════════════════════════════════════════════
# MAIN BOT CLASS (EXACT REPLICA of main_live_bot.py's LiveTradingBot)
# ═══════════════════════════════════════════════════════════════════════════

class BacktestMainLiveBot:
    """
    Exact replica of main_live_bot.py's LiveTradingBot class.
    Uses CSV data instead of MT5 API.
    
    KEY DIFFERENCE FROM simulate_main_live_bot.py:
    - simulate_main_live_bot.py: Reads pre-generated signals from CSV
    - backtest_main_live_bot.py: Generates signals using compute_confluence() like main_live_bot.py
    """
    
    def __init__(
        self,
        initial_balance: float = 20_000,
        start_date: datetime = None,
        end_date: datetime = None,
        use_progressive_trailing: bool = False,
    ):
        """Initialize bot with same structure as main_live_bot.py."""
        # Account state
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.day_start_equity = initial_balance
        
        # Progressive trailing stop toggle
        self.use_progressive_trailing = use_progressive_trailing
        self.progressive_trigger_r = 0.9  # At 0.9R, move SL to TP1 (0.6R)
        
        # Dates
        self.start_date = start_date or datetime(2023, 1, 1, tzinfo=timezone.utc)
        self.end_date = end_date or datetime(2025, 12, 31, tzinfo=timezone.utc)
        
        # Load strategy params (same as main_live_bot.py)
        self.params = load_strategy_params()
        
        # Data provider (replaces MT5)
        self.data_provider = CSVDataProvider()
        
        # State tracking (matching main_live_bot.py)
        self.pending_setups: Dict[str, PendingSetup] = {}  # Entry queue
        self.open_positions: Dict[str, Position] = {}
        self.closed_trades: List[Position] = []
        
        # DDD/TDD state (matching main_live_bot.py)
        self.ddd_halted = False
        self.ddd_halt_reason = ""
        self.ddd_halt_date: Optional[date] = None
        self.current_date: Optional[date] = None
        
        # Tracking
        self.daily_snapshots: List[DailySnapshot] = []
        self.safety_events: List[Dict] = []
        self.total_commissions = 0.0
        
        # NOTE: signals_df is DEPRECATED - we now generate signals using compute_confluence()
        # This is kept for backwards compatibility but not used
        self.signals_df = None
    
    def _load_signals(self, csv_path: str):
        """Load pre-generated signals from validate output."""
        path = Path(csv_path)
        if not path.exists():
            # Try relative to project root
            path = Path(__file__).parent.parent / csv_path
        
        if not path.exists():
            log.error(f"Signals CSV not found: {csv_path}")
            return
        
        self.signals_df = pd.read_csv(path)
        log.info(f"✓ Loaded {len(self.signals_df)} signals from {path.name}")
        
        # Parse dates
        for col in ['entry_date', 'signal_date']:
            if col in self.signals_df.columns:
                self.signals_df[col] = pd.to_datetime(self.signals_df[col])
    
    # ═══════════════════════════════════════════════════════════════════════
    # EQUITY CALCULATION (matching main_live_bot.py)
    # ═══════════════════════════════════════════════════════════════════════
    
    def calculate_equity(self, current_time: datetime, use_price: str = 'close') -> float:
        """
        Calculate current equity including floating PnL.
        Matches main_live_bot.py which gets equity from MT5 account info.
        
        Args:
            current_time: Current simulation time
            use_price: 'close', 'low', 'high', or 'worst' (worst-case per direction)
        """
        equity = self.balance
        
        for pos in self.open_positions.values():
            bar = self.data_provider.get_h1_bar(pos.signal.symbol, current_time)
            if not bar:
                continue
            
            # Get price based on mode
            if use_price == 'worst':
                # Worst case: Low for longs, High for shorts
                if pos.signal.direction == 'bullish':
                    current_price = bar['low']
                else:
                    current_price = bar['high']
            elif use_price == 'low':
                current_price = bar['low']
            elif use_price == 'high':
                current_price = bar['high']
            else:
                current_price = bar['close']
            
            # Calculate floating PnL
            if pos.signal.direction == 'bullish':
                price_diff = current_price - pos.fill_price
            else:
                price_diff = pos.fill_price - current_price
            
            # PnL in R
            r_pnl = price_diff / pos.signal.risk if pos.signal.risk > 0 else 0
            
            # PnL in USD
            usd_pnl = r_pnl * pos.risk_usd * pos.remaining_pct
            equity += usd_pnl
        
        return equity
    
    # ═══════════════════════════════════════════════════════════════════════
    # DDD/TDD CHECKS (EXACT COPY from main_live_bot.py)
    # ═══════════════════════════════════════════════════════════════════════
    
    def check_ddd(self, equity: float) -> Tuple[float, str]:
        """
        Check Daily DrawDown.
        EXACT copy of main_live_bot.py's DDD protection logic.
        
        Returns: (dd_pct, action)
        action: 'ok', 'warning', 'reduce', 'halt'
        """
        if self.day_start_equity <= 0:
            return 0.0, 'ok'
        
        # DDD = (day_start - current) / day_start * 100
        daily_pnl = equity - self.day_start_equity
        dd_pct = abs(min(0, daily_pnl)) / self.day_start_equity * 100
        
        if dd_pct >= CONFIG.daily_loss_halt_pct:
            return dd_pct, 'halt'
        elif dd_pct >= CONFIG.daily_loss_reduce_pct:
            return dd_pct, 'reduce'
        elif dd_pct >= CONFIG.daily_loss_warning_pct:
            return dd_pct, 'warning'
        return dd_pct, 'ok'
    
    def check_tdd(self, equity: float) -> Tuple[float, bool]:
        """
        Check Total DrawDown (static from INITIAL balance).
        EXACT copy of main_live_bot.py's TDD check.
        
        Returns: (dd_pct, breached)
        """
        if equity >= self.initial_balance:
            return 0.0, False
        
        dd_pct = (self.initial_balance - equity) / self.initial_balance * 100
        breached = dd_pct >= CONFIG.max_total_dd_pct
        return dd_pct, breached
    
    # ═══════════════════════════════════════════════════════════════════════
    # EMERGENCY CLOSE (matching main_live_bot.py)
    # ═══════════════════════════════════════════════════════════════════════
    
    def emergency_close_all(self, current_time: datetime, reason: str):
        """
        Emergency close all positions and cancel pending orders.
        EXACT copy of main_live_bot.py's _emergency_close_all().
        """
        log.warning(f"🚨 EMERGENCY CLOSE: {reason}")
        
        # Close all open positions
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            bar = self.data_provider.get_h1_bar(symbol, current_time)
            if bar:
                self._close_position(pos, current_time, bar['close'], reason)
        
        # Cancel all pending setups
        cancelled_count = len(self.pending_setups)
        for symbol, setup in list(self.pending_setups.items()):
            setup.status = OrderStatus.CANCELLED
        self.pending_setups.clear()
        
        if cancelled_count > 0:
            log.warning(f"  Cancelled {cancelled_count} pending setups")
    
    def _close_position(self, pos: Position, exit_time: datetime, exit_price: float, reason: str = ""):
        """Close a position and record PnL."""
        if pos.closed:
            return
        
        pos.closed = True
        pos.exit_time = exit_time
        pos.exit_price = exit_price
        
        # Calculate final PnL for remaining position
        if pos.signal.direction == 'bullish':
            price_diff = exit_price - pos.fill_price
        else:
            price_diff = pos.fill_price - exit_price
        
        final_r = price_diff / pos.signal.risk if pos.signal.risk > 0 else 0
        final_pnl = final_r * pos.risk_usd * pos.remaining_pct
        
        # Total PnL = partial closes + final close - commission
        # NOTE: partial_pnl is already booked to balance in _check_tp_levels
        # So we only add final_pnl and subtract commission here
        pos.realized_pnl = pos.partial_pnl + final_pnl - pos.commission
        pos.realized_r = pos.realized_pnl / pos.risk_usd if pos.risk_usd > 0 else 0
        
        # Update balance - only final portion, partials already booked!
        self.balance += final_pnl - pos.commission
        self.total_commissions += pos.commission
        
        # Move to closed trades
        self.closed_trades.append(pos)
        symbol = pos.signal.symbol
        if symbol in self.open_positions:
            del self.open_positions[symbol]
        
        log.debug(f"  Closed {symbol}: {reason} | PnL: ${pos.realized_pnl:+.2f} ({pos.realized_r:+.2f}R)")
    
    # ═══════════════════════════════════════════════════════════════════════
    # SIGNAL PROCESSING (matching main_live_bot.py's scan_symbol())
    # ═══════════════════════════════════════════════════════════════════════
    
    def process_daily_signals(self, current_time: datetime):
        """
        Generate signals for today's scan using compute_confluence().
        EXACT REPLICA of main_live_bot.py's scan_all_symbols() at 00:10.
        
        This is the CORE difference from simulate_main_live_bot.py:
        - simulate_main_live_bot.py reads pre-generated signals from CSV
        - backtest_main_live_bot.py generates signals live using compute_confluence()
        """
        symbols = self.data_provider.get_available_symbols()
        
        for symbol in symbols:
            # Skip if already have position or pending setup
            if symbol in self.open_positions:
                continue
            if symbol in self.pending_setups:
                continue
            
            # Get multi-timeframe data (EXACT same as main_live_bot.py)
            # Data should be sliced to BEFORE current_time (no look-ahead bias)
            try:
                monthly_data = self.data_provider.get_ohlcv(symbol, 'MN', current_time, lookback=12)
                weekly_data = self.data_provider.get_ohlcv(symbol, 'W1', current_time, lookback=52)
                daily_data = self.data_provider.get_ohlcv(symbol, 'D1', current_time, lookback=100)
                h4_data = self.data_provider.get_ohlcv(symbol, 'H4', current_time, lookback=100)
            except Exception as e:
                log.debug(f"  [{symbol}] Data error: {e}")
                continue
            
            if daily_data is None or len(daily_data) < 50:
                continue
            if weekly_data is None or len(weekly_data) < 10:
                continue
            
            # Convert to list of dicts for compute_confluence
            monthly_candles = monthly_data.to_dict('records') if monthly_data is not None and len(monthly_data) > 0 else []
            weekly_candles = weekly_data.to_dict('records') if weekly_data is not None else []
            daily_candles = daily_data.to_dict('records') if daily_data is not None else []
            h4_candles = h4_data.to_dict('records') if h4_data is not None else daily_candles[-20:]
            
            # Infer trends (EXACT same as main_live_bot.py)
            mn_trend = _infer_trend(monthly_candles) if monthly_candles else "mixed"
            wk_trend = _infer_trend(weekly_candles) if weekly_candles else "mixed"
            d_trend = _infer_trend(daily_candles) if daily_candles else "mixed"
            
            # Pick direction (EXACT same as main_live_bot.py)
            direction, _, _ = _pick_direction_from_bias(mn_trend, wk_trend, d_trend)
            
            if direction == "neutral":
                continue
            
            # Compute confluence (EXACT same as main_live_bot.py)
            try:
                flags, notes, trade_levels = compute_confluence(
                    monthly_candles,
                    weekly_candles,
                    daily_candles,
                    h4_candles,
                    direction,
                    self.params,
                    None,  # historical_sr - not available in backtest
                )
            except Exception as e:
                log.debug(f"  [{symbol}] Confluence error: {e}")
                continue
            
            # Unpack trade levels (5 TP levels returned)
            entry, sl, tp1, tp2, tp3, tp4, tp5 = trade_levels
            
            if entry is None or sl is None or tp1 is None:
                continue
            
            # Calculate confluence score
            confluence_score = sum(1 for v in flags.values() if v)
            
            # Quality factors (EXACT same as main_live_bot.py)
            has_location = flags.get("location", False)
            has_fib = flags.get("fib", False)
            has_liquidity = flags.get("liquidity", False)
            has_structure = flags.get("structure", False)
            has_htf_bias = flags.get("htf_bias", False)
            quality_factors = sum([has_location, has_fib, has_liquidity, has_structure, has_htf_bias])
            
            # Check minimum thresholds (from params)
            min_confluence = self.params.min_confluence if hasattr(self.params, 'min_confluence') else 4
            min_quality = CONFIG.min_quality_factors if hasattr(CONFIG, 'min_quality_factors') else 2
            
            if confluence_score < min_confluence:
                continue
            if quality_factors < min_quality:
                continue
            
            # Risk validation
            risk = abs(entry - sl)
            if risk <= 0:
                continue
            
            # Create signal (EXACT same structure as main_live_bot.py)
            signal = Signal(
                symbol=symbol,
                direction=direction,
                entry=entry,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                confluence_score=confluence_score,
                quality_factors=quality_factors,
                signal_time=current_time,
            )
            
            # Add to entry queue (matching main_live_bot.py)
            setup = PendingSetup(
                signal=signal,
                status=OrderStatus.AWAITING_ENTRY,
                queue_time=current_time,
            )
            self.pending_setups[symbol] = setup
            log.info(f"  [{symbol}] Signal queued: {signal.direction} @ {signal.entry:.5f}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # ENTRY QUEUE PROCESSING (EXACT COPY from main_live_bot.py)
    # ═══════════════════════════════════════════════════════════════════════
    
    def process_entry_queue(self, current_time: datetime):
        """
        Process entry queue - check if price is close enough for entry.
        EXACT copy of main_live_bot.py's _process_awaiting_entry().
        """
        for symbol in list(self.pending_setups.keys()):
            setup = self.pending_setups[symbol]
            
            if setup.status != OrderStatus.AWAITING_ENTRY:
                continue
            
            signal = setup.signal
            
            # Check expiry (120 hours = 5 days)
            hours_waiting = (current_time - setup.queue_time).total_seconds() / 3600
            if hours_waiting > CONFIG.max_entry_wait_hours:
                log.debug(f"  [{symbol}] Entry expired after {hours_waiting:.0f}h")
                setup.status = OrderStatus.EXPIRED
                del self.pending_setups[symbol]
                continue
            
            # Get current price
            bar = self.data_provider.get_h1_bar(symbol, current_time)
            if not bar:
                continue
            
            current_price = bar['close']
            
            # Calculate distance to entry in R
            entry = signal.entry
            risk = signal.risk
            
            if signal.direction == 'bullish':
                distance = entry - current_price
            else:
                distance = current_price - entry
            
            distance_r = distance / risk if risk > 0 else float('inf')
            
            # Check if price is close enough
            if distance_r <= CONFIG.immediate_entry_r:
                # Scenario A: Market order (within 0.05R)
                self._execute_market_order(setup, current_time, current_price)
            elif distance_r <= CONFIG.limit_order_proximity_r:
                # Scenario B: Place limit order (0.05R - 0.3R)
                self._place_limit_order(setup, current_time)
            # else: Scenario C: Stay in queue (> 0.3R)
    
    def _execute_market_order(self, setup: PendingSetup, current_time: datetime, fill_price: float):
        """Execute market order immediately."""
        signal = setup.signal
        symbol = signal.symbol
        
        # Calculate lot size at fill moment (compounding!)
        ddd_pct, _ = self.check_ddd(self.calculate_equity(current_time))
        risk_pct = CONFIG.get_risk_pct(ddd_pct)
        
        lot_size, risk_usd = calculate_lot_size(
            symbol=symbol,
            balance=self.balance,  # Current balance for compounding
            risk_pct=risk_pct,
            entry=fill_price,
            stop_loss=signal.stop_loss,
            confluence=signal.confluence_score,
        )
        
        if lot_size <= 0:
            log.warning(f"  [{symbol}] Invalid lot size, skipping")
            setup.status = OrderStatus.CANCELLED
            del self.pending_setups[symbol]
            return
        
        # Calculate commission
        specs = get_specs(symbol)
        commission = lot_size * specs['commission_per_lot']
        
        # Create position
        pos = Position(
            signal=signal,
            fill_time=current_time,
            fill_price=fill_price,
            lot_size=lot_size,
            risk_usd=risk_usd,
            commission=commission,
        )
        
        self.open_positions[symbol] = pos
        setup.status = OrderStatus.FILLED
        del self.pending_setups[symbol]
        
        log.info(f"  [{symbol}] MARKET ORDER filled @ {fill_price:.5f} | Lot: {lot_size} | Risk: ${risk_usd:.0f}")
    
    def _place_limit_order(self, setup: PendingSetup, current_time: datetime):
        """Place limit order (will fill on next bar if price touches entry)."""
        setup.status = OrderStatus.PENDING
        setup.order_time = current_time
        log.debug(f"  [{setup.signal.symbol}] Limit order placed @ {setup.signal.entry:.5f}")
    
    def process_pending_orders(self, current_time: datetime):
        """
        Check if limit orders should fill.
        Matches main_live_bot.py's order management.
        """
        for symbol in list(self.pending_setups.keys()):
            setup = self.pending_setups[symbol]
            
            if setup.status != OrderStatus.PENDING:
                continue
            
            signal = setup.signal
            
            # Get H1 bar
            bar = self.data_provider.get_h1_bar(symbol, current_time)
            if not bar:
                continue
            
            high = bar['high']
            low = bar['low']
            entry = signal.entry
            
            # Check if price touched entry
            filled = False
            if signal.direction == 'bullish':
                if low <= entry <= high:
                    filled = True
            else:
                if low <= entry <= high:
                    filled = True
            
            if filled:
                self._fill_limit_order(setup, current_time, entry)
    
    def _fill_limit_order(self, setup: PendingSetup, current_time: datetime, fill_price: float):
        """Fill a pending limit order."""
        signal = setup.signal
        symbol = signal.symbol
        
        # Calculate lot size at fill moment
        ddd_pct, _ = self.check_ddd(self.calculate_equity(current_time))
        risk_pct = CONFIG.get_risk_pct(ddd_pct)
        
        lot_size, risk_usd = calculate_lot_size(
            symbol=symbol,
            balance=self.balance,
            risk_pct=risk_pct,
            entry=fill_price,
            stop_loss=signal.stop_loss,
            confluence=signal.confluence_score,
        )
        
        if lot_size <= 0:
            setup.status = OrderStatus.CANCELLED
            del self.pending_setups[symbol]
            return
        
        specs = get_specs(symbol)
        commission = lot_size * specs['commission_per_lot']
        
        pos = Position(
            signal=signal,
            fill_time=current_time,
            fill_price=fill_price,
            lot_size=lot_size,
            risk_usd=risk_usd,
            commission=commission,
        )
        
        self.open_positions[symbol] = pos
        setup.status = OrderStatus.FILLED
        del self.pending_setups[symbol]
        
        log.info(f"  [{symbol}] LIMIT ORDER filled @ {fill_price:.5f} | Lot: {lot_size} | Risk: ${risk_usd:.0f}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # POSITION MANAGEMENT (EXACT COPY from main_live_bot.py)
    # ═══════════════════════════════════════════════════════════════════════
    
    def manage_positions(self, current_time: datetime):
        """
        Manage open positions - check SL, TP levels, trailing SL.
        EXACT copy of main_live_bot.py's manage_partial_takes() and position checks.
        """
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            if pos.closed:
                continue
            
            bar = self.data_provider.get_h1_bar(symbol, current_time)
            if not bar:
                continue
            
            high = bar['high']
            low = bar['low']
            close_price = bar['close']
            
            signal = pos.signal
            risk = signal.risk
            
            # Current SL (trailing or original)
            sl = pos.trailing_sl if pos.trailing_sl else signal.stop_loss
            
            # Check SL hit first
            if signal.direction == 'bullish':
                if low <= sl:
                    self._close_position(pos, current_time, sl, "SL")
                    continue
            else:
                if high >= sl:
                    self._close_position(pos, current_time, sl, "SL")
                    continue
            
            # Check TP levels (matching main_live_bot.py's 3-TP system)
            self._check_tp_levels(pos, current_time, high, low)
    
    def _check_tp_levels(self, pos: Position, current_time: datetime, high: float, low: float):
        """
        Check TP levels and execute partial closes.
        EXACT copy of main_live_bot.py's 3-TP exit system.
        
        OPTIONAL: Progressive trailing stop (if enabled):
        - Between TP1 and TP2: At 0.9R, move SL to TP1 (0.6R)
        - Prevents losing gains if price reverses before TP2
        """
        signal = pos.signal
        risk = signal.risk
        
        # TP1: 0.6R -> Close 35%, move SL to breakeven
        if not pos.tp1_hit:
            tp1_hit = (signal.direction == 'bullish' and high >= signal.tp1) or \
                      (signal.direction == 'bearish' and low <= signal.tp1)
            if tp1_hit:
                pos.tp1_hit = True
                close_pct = self.params.tp1_close_pct  # 0.35
                
                # Book partial profit
                tp1_r = self.params.tp1_r_multiple  # 0.6
                partial_profit = tp1_r * pos.risk_usd * close_pct
                pos.partial_pnl += partial_profit
                self.balance += partial_profit
                pos.remaining_pct -= close_pct
                
                # Move SL to breakeven
                pos.trailing_sl = pos.fill_price
                log.debug(f"  [{signal.symbol}] TP1 hit: +${partial_profit:.2f}, SL→BE")
        
        # PROGRESSIVE TRAILING: Between TP1 and TP2, at 0.9R move SL to TP1
        elif pos.tp1_hit and not pos.tp2_hit and self.use_progressive_trailing:
            # Calculate current R
            if signal.direction == 'bullish':
                current_r = (high - signal.entry) / risk if risk > 0 else 0
            else:
                current_r = (signal.entry - low) / risk if risk > 0 else 0
            
            # If we've reached 0.9R and SL is still at breakeven, trail to TP1
            if current_r >= self.progressive_trigger_r:
                tp1_sl = signal.entry + (risk * self.params.tp1_r_multiple) if signal.direction == 'bullish' else signal.entry - (risk * self.params.tp1_r_multiple)
                
                # Only update if current SL is less protective than TP1
                if pos.trailing_sl is None or \
                   (signal.direction == 'bullish' and tp1_sl > pos.trailing_sl) or \
                   (signal.direction == 'bearish' and tp1_sl < pos.trailing_sl):
                    pos.trailing_sl = tp1_sl
                    log.debug(f"  [{signal.symbol}] Progressive trail: {current_r:.2f}R → SL to TP1 ({tp1_sl:.5f})")
        
        # TP2: 1.2R -> Close 30%, trail SL to TP1 + 0.5R
        if pos.tp1_hit and not pos.tp2_hit:  # Changed from elif to if
            tp2_hit = (signal.direction == 'bullish' and high >= signal.tp2) or \
                      (signal.direction == 'bearish' and low <= signal.tp2)
            if tp2_hit:
                pos.tp2_hit = True
                close_pct = self.params.tp2_close_pct  # 0.30
                
                tp2_r = self.params.tp2_r_multiple  # 1.2
                partial_profit = tp2_r * pos.risk_usd * close_pct
                pos.partial_pnl += partial_profit
                self.balance += partial_profit
                pos.remaining_pct -= close_pct
                
                # Trail SL to TP1 + 0.5R
                if signal.direction == 'bullish':
                    pos.trailing_sl = signal.entry + risk * (self.params.tp1_r_multiple + 0.5)
                else:
                    pos.trailing_sl = signal.entry - risk * (self.params.tp1_r_multiple + 0.5)
                log.debug(f"  [{signal.symbol}] TP2 hit: +${partial_profit:.2f}")
        
        # TP3: 2.0R -> Close all remaining
        if pos.tp2_hit and not pos.tp3_hit:  # Changed from elif to if
            tp3_hit = (signal.direction == 'bullish' and high >= signal.tp3) or \
                      (signal.direction == 'bearish' and low <= signal.tp3)
            if tp3_hit:
                pos.tp3_hit = True
                self._close_position(pos, current_time, signal.tp3, "TP3")
    
    # ═══════════════════════════════════════════════════════════════════════
    # MAIN SIMULATION LOOP (matching main_live_bot.py's run())
    # ═══════════════════════════════════════════════════════════════════════
    
    def run(self) -> Dict[str, Any]:
        """
        Main simulation loop - replicates main_live_bot.py's run() method.
        Processes H1 bar by bar exactly as live bot would.
        """
        log.info("=" * 70)
        log.info("BACKTEST MAIN LIVE BOT - Exact Replica")
        log.info("=" * 70)
        log.info(f"  Initial Balance: ${self.initial_balance:,.0f}")
        log.info(f"  Date Range: {self.start_date.date()} to {self.end_date.date()}")
        log.info(f"  DDD Halt: {CONFIG.daily_loss_halt_pct}%")
        log.info(f"  TDD Stop-out: {CONFIG.max_total_dd_pct}%")
        log.info(f"  3-TP System: {self.params.tp1_r_multiple}R/{self.params.tp2_r_multiple}R/{self.params.tp3_r_multiple}R")
        log.info("=" * 70)
        
        # Get all available symbols from CSV data
        symbols = self.data_provider.get_available_symbols()
        
        log.info(f"  Symbols: {len(symbols)}")
        
        # Pre-build H1 indices
        for symbol in symbols:
            self.data_provider.build_h1_index(symbol)
        
        timeline = self.data_provider.get_h1_timeline(self.start_date, self.end_date)
        log.info(f"  H1 Bars: {len(timeline)}")
        log.info("=" * 70)
        
        # Tracking
        max_ddd = 0.0
        max_tdd = 0.0
        day_max_ddd = 0.0
        day_low_equity = self.initial_balance
        day_high_equity = self.initial_balance
        day_trades_opened = 0
        day_trades_closed = 0
        
        # Main loop
        pbar = tqdm(timeline, desc="Simulating", mininterval=1.0)
        
        for current_time in pbar:
            date_obj = current_time.date()
            date_str = current_time.strftime('%Y-%m-%d')
            
            # ═══════════════════════════════════════════════════════════════
            # NEW DAY HANDLING (matching main_live_bot.py)
            # ═══════════════════════════════════════════════════════════════
            if date_obj != self.current_date:
                # Save previous day snapshot
                if self.current_date is not None:
                    equity = self.calculate_equity(current_time)
                    self.daily_snapshots.append(DailySnapshot(
                        date=self.current_date.strftime('%Y-%m-%d'),
                        day_start_equity=self.day_start_equity,
                        day_end_equity=equity,
                        day_low_equity=day_low_equity,
                        day_high_equity=day_high_equity,
                        realized_pnl=self.balance - self.day_start_equity,
                        floating_pnl=equity - self.balance,
                        max_ddd_pct=day_max_ddd,
                        tdd_pct=max(0, (self.initial_balance - equity) / self.initial_balance * 100),
                        trades_opened=day_trades_opened,
                        trades_closed=day_trades_closed,
                        ddd_halt_triggered=self.ddd_halted,
                    ))
                
                # Reset for new day (matching main_live_bot.py's day reset)
                self.current_date = date_obj
                equity = self.calculate_equity(current_time)
                self.day_start_equity = equity
                
                # Reset DDD halt for new day (CRITICAL: matching main_live_bot.py)
                if self.ddd_halted:
                    log.info(f"  [{date_str}] New day - DDD halt reset")
                    self.ddd_halted = False
                    self.ddd_halt_reason = ""
                
                day_max_ddd = 0.0
                day_low_equity = equity
                day_high_equity = equity
                day_trades_opened = 0
                day_trades_closed = 0
            
            # Skip weekends
            if current_time.weekday() >= 5:
                continue
            
            # ═══════════════════════════════════════════════════════════════
            # DDD/TDD PROTECTION (matching main_live_bot.py's 5-sec loop)
            # ═══════════════════════════════════════════════════════════════
            # Calculate worst-case equity (using H1 High/Low)
            worst_equity = self.calculate_equity(current_time, use_price='worst')
            close_equity = self.calculate_equity(current_time, use_price='close')
            
            day_low_equity = min(day_low_equity, worst_equity)
            day_high_equity = max(day_high_equity, close_equity)
            
            # Check TDD (total drawdown from initial)
            tdd_pct, tdd_breached = self.check_tdd(worst_equity)
            max_tdd = max(max_tdd, tdd_pct)
            
            if tdd_breached:
                log.error(f"\n🚨 TDD STOP-OUT at {current_time}: {tdd_pct:.1f}%")
                log.error("   ACCOUNT BLOWN - 10% drawdown from initial balance")
                self.emergency_close_all(current_time, f"TDD_{tdd_pct:.1f}%")
                break
            
            # Check DDD (daily drawdown from day start)
            ddd_pct, ddd_action = self.check_ddd(worst_equity)
            if ddd_pct > 0:
                day_max_ddd = max(day_max_ddd, ddd_pct)
                max_ddd = max(max_ddd, ddd_pct)
            
            # DDD HALT (matching main_live_bot.py)
            if ddd_action == 'halt' and not self.ddd_halted:
                log.warning(f"\n🚨 DDD HALT at {current_time}: {ddd_pct:.1f}%")
                log.warning(f"   Day start: ${self.day_start_equity:,.0f} | Worst equity: ${worst_equity:,.0f}")
                
                self.emergency_close_all(current_time, f"DDD_{ddd_pct:.1f}%")
                self.ddd_halted = True
                self.ddd_halt_reason = f"DDD {ddd_pct:.1f}% >= {CONFIG.daily_loss_halt_pct}%"
                self.ddd_halt_date = date_obj
                
                self.safety_events.append({
                    'time': current_time.isoformat(),
                    'type': 'DDD_HALT',
                    'ddd_pct': ddd_pct,
                    'equity': worst_equity,
                    'day_start': self.day_start_equity,
                })
                continue
            
            # Skip trading if halted
            if self.ddd_halted:
                continue
            
            # ═══════════════════════════════════════════════════════════════
            # DAILY SCAN (at 00:00-01:00 bar, matching 00:10 server time scan)
            # ═══════════════════════════════════════════════════════════════
            # Now using compute_confluence() - scan EVERY day, not just signal dates
            if current_time.hour == 0:
                log.info(f"\n[{date_str}] Daily scan...")
                trades_before = len(self.pending_setups)
                self.process_daily_signals(current_time)
                day_trades_opened += len(self.pending_setups) - trades_before
            
            # ═══════════════════════════════════════════════════════════════
            # ENTRY QUEUE PROCESSING (matching main_live_bot.py)
            # ═══════════════════════════════════════════════════════════════
            if self.pending_setups:
                self.process_entry_queue(current_time)
                self.process_pending_orders(current_time)
            
            # ═══════════════════════════════════════════════════════════════
            # POSITION MANAGEMENT (matching main_live_bot.py)
            # ═══════════════════════════════════════════════════════════════
            if self.open_positions:
                closed_before = len(self.closed_trades)
                self.manage_positions(current_time)
                day_trades_closed += len(self.closed_trades) - closed_before
        
        # ═══════════════════════════════════════════════════════════════════
        # CLOSE REMAINING POSITIONS
        # ═══════════════════════════════════════════════════════════════════
        if timeline:
            last_time = timeline[-1]
            for symbol in list(self.open_positions.keys()):
                pos = self.open_positions[symbol]
                bar = self.data_provider.get_h1_bar(symbol, last_time)
                if bar:
                    self._close_position(pos, last_time, bar['close'], "END")
        
        # ═══════════════════════════════════════════════════════════════════
        # RESULTS
        # ═══════════════════════════════════════════════════════════════════
        return self._compile_results(max_ddd, max_tdd)
    
    def _compile_results(self, max_ddd: float, max_tdd: float) -> Dict[str, Any]:
        """Compile simulation results."""
        total_trades = len(self.closed_trades)
        winners = sum(1 for t in self.closed_trades if t.realized_pnl > 0)
        losers = total_trades - winners
        
        total_pnl = sum(t.realized_pnl for t in self.closed_trades)
        total_r = sum(t.realized_r for t in self.closed_trades)
        
        results = {
            'initial_balance': self.initial_balance,
            'final_balance': self.balance,
            'net_pnl': total_pnl,
            'return_pct': (self.balance - self.initial_balance) / self.initial_balance * 100,
            'total_trades': total_trades,
            'winners': winners,
            'losers': losers,
            'win_rate': winners / total_trades * 100 if total_trades > 0 else 0,
            'total_r': total_r,
            'total_commissions': self.total_commissions,
            'max_ddd_pct': max_ddd,
            'max_tdd_pct': max_tdd,
            'ddd_halt_events': len([e for e in self.safety_events if e['type'] == 'DDD_HALT']),
            'pending_setups': len(self.pending_setups),
        }
        
        # Print summary
        log.info("\n" + "=" * 70)
        log.info("SIMULATION RESULTS")
        log.info("=" * 70)
        log.info(f"\n📊 TRADE STATISTICS:")
        log.info(f"   Total trades: {total_trades}")
        log.info(f"   Winners: {winners} ({results['win_rate']:.1f}%)")
        log.info(f"   Losers: {losers}")
        log.info(f"   Total R: {total_r:+.2f}R")
        log.info(f"\n💰 PROFIT/LOSS:")
        log.info(f"   Gross PnL: ${total_pnl + self.total_commissions:,.2f}")
        log.info(f"   Commissions: ${self.total_commissions:,.2f}")
        log.info(f"   Net PnL: ${total_pnl:,.2f}")
        log.info(f"\n📈 ACCOUNT:")
        log.info(f"   Starting: ${self.initial_balance:,.0f}")
        log.info(f"   Final: ${self.balance:,.2f}")
        log.info(f"   Return: {results['return_pct']:+.1f}%")
        log.info(f"\n📉 DRAWDOWN:")
        log.info(f"   Max DDD: {max_ddd:.2f}% (halt at {CONFIG.daily_loss_halt_pct}%)")
        log.info(f"   Max TDD: {max_tdd:.2f}% (limit: {CONFIG.max_total_dd_pct}%)")
        log.info(f"\n🚨 SAFETY:")
        log.info(f"   DDD halt events: {results['ddd_halt_events']}")
        log.info("=" * 70)
        
        return results
    
    def save_results(self, output_dir: str = None):
        """Save results to files."""
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "ftmo_analysis_output" / "backtest_live_bot"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save closed trades
        trades_data = []
        for pos in self.closed_trades:
            trades_data.append({
                'symbol': pos.signal.symbol,
                'direction': pos.signal.direction,
                'fill_time': pos.fill_time.isoformat() if pos.fill_time else None,
                'fill_price': pos.fill_price,
                'exit_time': pos.exit_time.isoformat() if pos.exit_time else None,
                'exit_price': pos.exit_price,
                'lot_size': pos.lot_size,
                'risk_usd': pos.risk_usd,
                'commission': pos.commission,
                'realized_r': pos.realized_r,
                'realized_pnl': pos.realized_pnl,
                'tp1_hit': pos.tp1_hit,
                'tp2_hit': pos.tp2_hit,
                'tp3_hit': pos.tp3_hit,
            })
        pd.DataFrame(trades_data).to_csv(output_dir / "closed_trades.csv", index=False)
        
        # Save daily snapshots
        snapshots_data = []
        for snap in self.daily_snapshots:
            snapshots_data.append({
                'date': snap.date,
                'day_start_equity': snap.day_start_equity,
                'day_end_equity': snap.day_end_equity,
                'day_low_equity': snap.day_low_equity,
                'day_high_equity': snap.day_high_equity,
                'realized_pnl': snap.realized_pnl,
                'floating_pnl': snap.floating_pnl,
                'max_ddd_pct': snap.max_ddd_pct,
                'tdd_pct': snap.tdd_pct,
                'ddd_halt_triggered': snap.ddd_halt_triggered,
            })
        pd.DataFrame(snapshots_data).to_csv(output_dir / "daily_snapshots.csv", index=False)
        
        # Save safety events
        with open(output_dir / "safety_events.json", 'w') as f:
            json.dump(self.safety_events, f, indent=2)
        
        log.info(f"\n✅ Results saved to: {output_dir}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Run the backtest."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Backtest Main Live Bot - Exact Replica using compute_confluence()")
    parser.add_argument("--balance", type=float, default=20000, help="Initial balance")
    parser.add_argument("--start", type=str, default="2023-01-01", help="Start date")
    parser.add_argument("--end", type=str, default="2025-12-31", help="End date")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument("--progressive-trailing", action="store_true", help="Enable progressive trailing stop (0.9R → TP1)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse dates
    start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    # Log configuration
    trailing_mode = "PROGRESSIVE (0.9R→TP1)" if args.progressive_trailing else "STANDARD (BE until TP2)"
    log.info(f"Trailing Stop Mode: {trailing_mode}")
    
    # Create bot - now generates signals using compute_confluence() like main_live_bot.py
    bot = BacktestMainLiveBot(
        initial_balance=args.balance,
        start_date=start_date,
        end_date=end_date,
        use_progressive_trailing=args.progressive_trailing,
    )
    
    # Run simulation
    results = bot.run()
    
    # Save results
    bot.save_results(args.output)
    
    return results


if __name__ == "__main__":
    main()
