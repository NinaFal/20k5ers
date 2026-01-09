#!/usr/bin/env python3
"""
H1-Based Trade Simulator with ACCURATE Drawdown Tracking

This is the FULL VERSION that simulates:
- Multiple trades open simultaneously
- Floating P&L calculated every H1 bar for ALL open trades
- Equity = Balance + Total Floating P&L
- Daily DD check every hour (5% of previous day HWM)
- Total DD check every hour (10% of initial balance - CONSTANT)

The simulator processes ALL H1 bars chronologically and:
1. Opens trades when their entry_time is reached
2. Updates floating P&L for all open trades each bar
3. Closes trades when SL/TP is hit
4. Checks drawdown limits EVERY HOUR

Usage:
    python scripts/validate_with_h1_dd.py --run run_017
    python scripts/validate_with_h1_dd.py --run run_017 --balance 60000 --risk-pct 0.65
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict
import argparse
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# ═══════════════════════════════════════════════════════════════════════════
# TIMEZONE CONFIGURATION - 5ers/MT5 uses UTC+3 (EET/EEST)
# ═══════════════════════════════════════════════════════════════════════════
UTC_PLUS_3 = timezone(timedelta(hours=3))


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PropFirmRules:
    """5ers prop firm rules."""
    initial_balance: float = 60_000
    daily_dd_pct: float = 0.05      # 5% daily drawdown
    total_dd_pct: float = 0.10      # 10% total drawdown (from initial!)
    risk_per_trade_pct: float = 0.65  # Risk per trade as % of initial
    
    @property
    def stop_out_level(self) -> float:
        """Total DD stop-out level - CONSTANT from initial balance."""
        return self.initial_balance * (1 - self.total_dd_pct)
    
    @property
    def risk_per_trade(self) -> float:
        """Dollar risk per 1R."""
        return self.initial_balance * (self.risk_per_trade_pct / 100)


@dataclass
class OpenTrade:
    """Represents an open trade being tracked."""
    trade_id: str
    symbol: str
    direction: str  # 'bullish' or 'bearish'
    entry_time: datetime
    entry_price: float
    stop_loss: float
    risk: float  # |entry - sl|
    
    # TP levels (prices) - Only 3 TPs for simplicity
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    
    # Current state
    trailing_sl: float = 0.0
    current_price: float = 0.0
    floating_r: float = 0.0
    realized_r: float = 0.0
    remaining_pct: float = 1.0
    
    # TP tracking - Only 3 TPs
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    
    # Exit
    exit_time: Optional[datetime] = None
    exit_reason: str = ""
    is_closed: bool = False


@dataclass
class DailyState:
    """Track daily drawdown state."""
    date: date
    start_of_day_balance: float
    start_of_day_equity: float
    high_water_mark: float  # max(balance, equity) at start of day
    daily_dd_limit: float   # HWM * 5%
    min_equity_allowed: float  # HWM - daily_dd_limit
    
    # Intraday tracking
    lowest_equity: float = float('inf')
    highest_equity: float = 0.0
    max_open_trades: int = 0
    max_floating_pnl: float = 0.0
    min_floating_pnl: float = 0.0
    
    # Breach info
    daily_dd_breached: bool = False
    breach_time: Optional[datetime] = None
    breach_equity: float = 0.0
    breach_floating: float = 0.0
    breach_open_trades: int = 0
    
    # End of day
    end_of_day_balance: float = 0.0
    end_of_day_equity: float = 0.0
    trades_opened: int = 0
    trades_closed: int = 0
    realized_pnl: float = 0.0


@dataclass
class DrawdownEvent:
    """Record of a drawdown breach."""
    timestamp: datetime
    breach_type: str  # 'DAILY' or 'TOTAL'
    equity: float
    balance: float
    floating_pnl: float
    limit: float
    deficit: float
    open_trades: int
    open_trade_symbols: List[str]


@dataclass 
class HourlySnapshot:
    """Snapshot of account state at each hour."""
    timestamp: datetime
    balance: float
    equity: float
    floating_pnl: float
    open_trades: int
    daily_limit: float
    total_limit: float
    daily_buffer: float  # equity - daily_limit
    total_buffer: float  # equity - total_limit


# ═══════════════════════════════════════════════════════════════════════════
# FULL H1 SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

class FullH1Simulator:
    """
    Full H1-based trade simulator with accurate drawdown tracking.
    
    Processes ALL H1 bars chronologically and tracks:
    - Multiple open trades simultaneously
    - Floating P&L every hour
    - Daily and Total drawdown every hour
    
    Note: Uses UTC+3 timezone for day boundaries (5ers/MT5 server time)
    """
    
    def __init__(
        self,
        rules: PropFirmRules,
        h1_data_dir: str = 'data/ohlcv',
        tp_levels: Dict[str, float] = None,
        close_pcts: Dict[str, float] = None,
    ):
        self.rules = rules
        self.h1_data_dir = Path(h1_data_dir)
        
        # TP configuration - Simplified to 3 TPs only
        self.tp_r_levels = tp_levels or {
            'tp1': 0.6, 'tp2': 1.2, 'tp3': 2.0
        }
        self.close_pcts = close_pcts or {
            'tp1': 0.35, 'tp2': 0.30, 'tp3': 0.35  # TP3 closes all remaining
        }
        
        # H1 data cache: symbol -> DataFrame
        self._h1_cache: Dict[str, pd.DataFrame] = {}
        
        # Build unified H1 timeline: timestamp -> {symbol: {open, high, low, close}}
        self._h1_timeline: Dict[datetime, Dict[str, dict]] = {}
        
        # Account state
        self.balance = rules.initial_balance
        self.equity = rules.initial_balance
        self.floating_pnl = 0.0
        
        # Trade tracking
        self.open_trades: Dict[str, OpenTrade] = {}  # trade_id -> OpenTrade
        self.closed_trades: List[OpenTrade] = []
        self.pending_entries: List[dict] = []  # Trades waiting to be opened
        
        # Drawdown tracking
        self.daily_states: List[DailyState] = []
        self.current_day: Optional[DailyState] = None
        self.dd_events: List[DrawdownEvent] = []
        self.hourly_snapshots: List[HourlySnapshot] = []
        
        # Day tracking (using server time UTC+3)
        self.last_server_date: Optional[date] = None
        
        # Stats
        self.max_concurrent_trades = 0
        self.total_bars_processed = 0
        
    def load_h1_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load H1 data for a symbol."""
        if symbol in self._h1_cache:
            return self._h1_cache[symbol]
        
        patterns = [
            f"{symbol}_H1_*.csv",
            f"{symbol}_H1.csv",
            f"{symbol}_h1_*.csv",
            f"{symbol}_h1.csv",
            f"{symbol.replace('_', '')}_H1*.csv",
        ]
        
        for pattern in patterns:
            files = list(self.h1_data_dir.glob(pattern))
            if files:
                df = pd.read_csv(files[0])
                
                # Find timestamp column
                ts_col = None
                for col in ['timestamp', 'time', 'datetime', 'date', 'Time']:
                    if col in df.columns:
                        ts_col = col
                        break
                
                if ts_col:
                    df['timestamp'] = pd.to_datetime(df[ts_col])
                    df = df.sort_values('timestamp').reset_index(drop=True)
                    
                    # Normalize column names
                    df.columns = df.columns.str.lower()
                    
                    self._h1_cache[symbol] = df
                    return df
        
        return None
    
    def build_timeline(self, symbols: Set[str], start_date: datetime, end_date: datetime):
        """Build unified H1 timeline for all symbols."""
        print(f"  Building H1 timeline for {len(symbols)} symbols...")
        
        self._h1_timeline = defaultdict(dict)
        loaded = 0
        
        # Make dates timezone-naive for comparison with H1 data
        start_naive = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
        end_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
        
        for symbol in symbols:
            df = self.load_h1_data(symbol)
            if df is None:
                print(f"    ⚠️  No H1 data for {symbol}")
                continue
            
            # Ensure timestamps are timezone-naive
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            
            # Filter to date range
            mask = (df['timestamp'] >= start_naive) & (df['timestamp'] <= end_naive)
            df_filtered = df[mask]
            
            for _, row in df_filtered.iterrows():
                ts = row['timestamp']
                self._h1_timeline[ts][symbol] = {
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                }
            
            loaded += 1
        
        print(f"    Loaded {loaded}/{len(symbols)} symbols")
        print(f"    Timeline: {len(self._h1_timeline)} unique hours")
    
    def prepare_trades(self, trades_df: pd.DataFrame) -> List[dict]:
        """Prepare trades for simulation."""
        trades = []
        
        for idx, row in trades_df.iterrows():
            # Normalize column names
            trade = {}
            
            # Symbol
            trade['symbol'] = row.get('symbol', row.get('pair', row.get('Symbol', '')))
            
            # Direction
            direction = row.get('direction', row.get('signal_type', row.get('Direction', 'bullish')))
            trade['direction'] = direction.lower() if isinstance(direction, str) else 'bullish'
            
            # Entry time - make timezone-naive for comparison with H1 data
            entry_time = row.get('entry_time', row.get('entry_date', row.get('Entry_Time', '')))
            entry_dt = pd.to_datetime(entry_time)
            # Remove timezone if present
            if entry_dt.tzinfo is not None:
                entry_dt = entry_dt.tz_localize(None)
            trade['entry_time'] = entry_dt
            
            # Prices
            trade['entry_price'] = float(row.get('entry_price', row.get('entry', row.get('Entry_Price', 0))))
            trade['stop_loss'] = float(row.get('stop_loss', row.get('sl', row.get('Stop_Loss', 0))))
            
            # Trade ID
            trade['trade_id'] = str(row.get('trade_id', f"{trade['symbol']}_{idx}"))
            
            trades.append(trade)
        
        # Sort by entry time
        trades.sort(key=lambda x: x['entry_time'])
        
        return trades
    
    def create_open_trade(self, trade_data: dict) -> OpenTrade:
        """Create an OpenTrade from trade data."""
        entry = trade_data['entry_price']
        sl = trade_data['stop_loss']
        risk = abs(entry - sl)
        direction = trade_data['direction']
        
        # Calculate TP prices - Only 3 TPs
        if direction == 'bullish':
            tp1 = entry + risk * self.tp_r_levels['tp1']
            tp2 = entry + risk * self.tp_r_levels['tp2']
            tp3 = entry + risk * self.tp_r_levels['tp3']
        else:
            tp1 = entry - risk * self.tp_r_levels['tp1']
            tp2 = entry - risk * self.tp_r_levels['tp2']
            tp3 = entry - risk * self.tp_r_levels['tp3']
        
        return OpenTrade(
            trade_id=trade_data['trade_id'],
            symbol=trade_data['symbol'],
            direction=direction,
            entry_time=trade_data['entry_time'],
            entry_price=entry,
            stop_loss=sl,
            risk=risk,
            tp1=tp1, tp2=tp2, tp3=tp3,
            trailing_sl=sl,
            current_price=entry,
        )
    
    def _get_server_date(self, timestamp: datetime) -> date:
        """Convert UTC timestamp to server date (UTC+3)."""
        # Assume timestamp is UTC, convert to server time
        if timestamp.tzinfo is None:
            utc_time = timestamp.replace(tzinfo=timezone.utc)
        else:
            utc_time = timestamp
        
        server_time = utc_time.astimezone(UTC_PLUS_3)
        return server_time.date()
    
    def start_new_day(self, server_date: date):
        """Initialize tracking for a new trading day."""
        # Finalize previous day if exists
        if self.current_day:
            self.current_day.end_of_day_balance = self.balance
            self.current_day.end_of_day_equity = self.equity
            self.daily_states.append(self.current_day)
        
        # Calculate high water mark (max of balance and equity)
        hwm = max(self.balance, self.equity)
        daily_dd_limit = hwm * self.rules.daily_dd_pct
        
        self.current_day = DailyState(
            date=server_date,
            start_of_day_balance=self.balance,
            start_of_day_equity=self.equity,
            high_water_mark=hwm,
            daily_dd_limit=daily_dd_limit,
            min_equity_allowed=hwm - daily_dd_limit,
        )
    
    def calculate_floating_pnl(self, bar_data: Dict[str, dict]) -> float:
        """Calculate total floating P&L from all open trades."""
        total_floating = 0.0
        
        for trade_id, trade in self.open_trades.items():
            if trade.symbol not in bar_data:
                # Use last known price
                continue
            
            bar = bar_data[trade.symbol]
            current_price = bar['close']
            trade.current_price = current_price
            
            # Calculate floating R
            if trade.direction == 'bullish':
                floating_r = (current_price - trade.entry_price) / trade.risk
            else:
                floating_r = (trade.entry_price - current_price) / trade.risk
            
            # Account for partially closed position
            floating_r *= trade.remaining_pct
            
            # Add already realized R
            trade.floating_r = floating_r + trade.realized_r
            
            # Convert to dollars
            total_floating += trade.floating_r * self.rules.risk_per_trade
        
        return total_floating
    
    def check_trade_exits(self, timestamp: datetime, bar_data: Dict[str, dict]) -> List[OpenTrade]:
        """Check if any open trades hit SL or TP."""
        closed_this_bar = []
        
        for trade_id, trade in list(self.open_trades.items()):
            if trade.symbol not in bar_data:
                continue
            
            bar = bar_data[trade.symbol]
            high = bar['high']
            low = bar['low']
            
            exit_this_bar = False
            
            # ═══════════════════════════════════════════════════════════════
            # BULLISH TRADE
            # ═══════════════════════════════════════════════════════════════
            if trade.direction == 'bullish':
                # Check SL/Trailing first
                if low <= trade.trailing_sl:
                    trail_r = (trade.trailing_sl - trade.entry_price) / trade.risk
                    trade.realized_r += trade.remaining_pct * trail_r
                    trade.remaining_pct = 0
                    trade.exit_reason = self._get_exit_reason(trade, 'Trail')
                    exit_this_bar = True
                
                # Check TPs (only if not exited)
                if not exit_this_bar:
                    # TP1
                    if not trade.tp1_hit and high >= trade.tp1:
                        trade.tp1_hit = True
                        trade.realized_r += trade.remaining_pct * self.close_pcts['tp1'] * self.tp_r_levels['tp1']
                        trade.remaining_pct *= (1 - self.close_pcts['tp1'])
                        trade.trailing_sl = trade.entry_price  # Move to breakeven
                    
                    # TP2
                    if trade.tp1_hit and not trade.tp2_hit and high >= trade.tp2:
                        trade.tp2_hit = True
                        trade.realized_r += trade.remaining_pct * self.close_pcts['tp2'] * self.tp_r_levels['tp2']
                        trade.remaining_pct *= (1 - self.close_pcts['tp2'])
                        trade.trailing_sl = trade.tp1 + 0.5 * trade.risk
                    
                    # TP3 - FINAL TARGET, close all remaining
                    if trade.tp2_hit and not trade.tp3_hit and high >= trade.tp3:
                        trade.tp3_hit = True
                        trade.realized_r += trade.remaining_pct * self.tp_r_levels['tp3']
                        trade.remaining_pct = 0
                        trade.exit_reason = 'TP3'
                        exit_this_bar = True
            
            # ═══════════════════════════════════════════════════════════════
            # BEARISH TRADE
            # ═══════════════════════════════════════════════════════════════
            else:
                # Check SL/Trailing first
                if high >= trade.trailing_sl:
                    trail_r = (trade.entry_price - trade.trailing_sl) / trade.risk
                    trade.realized_r += trade.remaining_pct * trail_r
                    trade.remaining_pct = 0
                    trade.exit_reason = self._get_exit_reason(trade, 'Trail')
                    exit_this_bar = True
                
                if not exit_this_bar:
                    # TP1
                    if not trade.tp1_hit and low <= trade.tp1:
                        trade.tp1_hit = True
                        trade.realized_r += trade.remaining_pct * self.close_pcts['tp1'] * self.tp_r_levels['tp1']
                        trade.remaining_pct *= (1 - self.close_pcts['tp1'])
                        trade.trailing_sl = trade.entry_price
                    
                    # TP2
                    if trade.tp1_hit and not trade.tp2_hit and low <= trade.tp2:
                        trade.tp2_hit = True
                        trade.realized_r += trade.remaining_pct * self.close_pcts['tp2'] * self.tp_r_levels['tp2']
                        trade.remaining_pct *= (1 - self.close_pcts['tp2'])
                        trade.trailing_sl = trade.tp1 - 0.5 * trade.risk
                    
                    # TP3 - FINAL TARGET, close all remaining
                    if trade.tp2_hit and not trade.tp3_hit and low <= trade.tp3:
                        trade.tp3_hit = True
                        trade.realized_r += trade.remaining_pct * self.tp_r_levels['tp3']
                        trade.remaining_pct = 0
                        trade.exit_reason = 'TP3'
                        exit_this_bar = True
            
            # Close trade if fully exited
            if exit_this_bar or trade.remaining_pct <= 0.001:
                trade.exit_time = timestamp
                trade.is_closed = True
                
                # Update balance
                pnl = trade.realized_r * self.rules.risk_per_trade
                self.balance += pnl
                
                # Track
                if self.current_day:
                    self.current_day.trades_closed += 1
                    self.current_day.realized_pnl += pnl
                
                closed_this_bar.append(trade)
                del self.open_trades[trade_id]
        
        return closed_this_bar
    
    def _get_exit_reason(self, trade: OpenTrade, suffix: str) -> str:
        """Generate exit reason based on TPs hit."""
        if trade.tp3_hit:
            return f"TP3+{suffix}"
        elif trade.tp2_hit:
            return f"TP2+{suffix}"
        elif trade.tp1_hit:
            return f"TP1+{suffix}"
        else:
            return "SL"
    
    def check_drawdowns(self, timestamp: datetime):
        """Check both daily and total drawdowns."""
        if not self.current_day:
            return
        
        # Update tracking
        self.current_day.lowest_equity = min(self.current_day.lowest_equity, self.equity)
        self.current_day.highest_equity = max(self.current_day.highest_equity, self.equity)
        self.current_day.max_open_trades = max(self.current_day.max_open_trades, len(self.open_trades))
        self.current_day.max_floating_pnl = max(self.current_day.max_floating_pnl, self.floating_pnl)
        self.current_day.min_floating_pnl = min(self.current_day.min_floating_pnl, self.floating_pnl)
        
        open_symbols = [t.symbol for t in self.open_trades.values()]
        
        # ═══════════════════════════════════════════════════════════════════
        # CHECK DAILY DD (5% of previous day HWM)
        # ═══════════════════════════════════════════════════════════════════
        if self.equity < self.current_day.min_equity_allowed:
            if not self.current_day.daily_dd_breached:
                self.current_day.daily_dd_breached = True
                self.current_day.breach_time = timestamp
                self.current_day.breach_equity = self.equity
                self.current_day.breach_floating = self.floating_pnl
                self.current_day.breach_open_trades = len(self.open_trades)
                
                self.dd_events.append(DrawdownEvent(
                    timestamp=timestamp,
                    breach_type='DAILY',
                    equity=self.equity,
                    balance=self.balance,
                    floating_pnl=self.floating_pnl,
                    limit=self.current_day.min_equity_allowed,
                    deficit=self.current_day.min_equity_allowed - self.equity,
                    open_trades=len(self.open_trades),
                    open_trade_symbols=open_symbols,
                ))
        
        # ═══════════════════════════════════════════════════════════════════
        # CHECK TOTAL DD (10% of initial balance - CONSTANT!)
        # ═══════════════════════════════════════════════════════════════════
        if self.equity < self.rules.stop_out_level:
            # Only log once per day to avoid spam
            already_logged_today = any(
                e.breach_type == 'TOTAL' and 
                e.timestamp.date() == timestamp.date()
                for e in self.dd_events
            )
            
            if not already_logged_today:
                self.dd_events.append(DrawdownEvent(
                    timestamp=timestamp,
                    breach_type='TOTAL',
                    equity=self.equity,
                    balance=self.balance,
                    floating_pnl=self.floating_pnl,
                    limit=self.rules.stop_out_level,
                    deficit=self.rules.stop_out_level - self.equity,
                    open_trades=len(self.open_trades),
                    open_trade_symbols=open_symbols,
                ))
    
    def run_simulation(self, trades_df: pd.DataFrame, progress: bool = True) -> pd.DataFrame:
        """
        Run FULL hour-by-hour simulation.
        
        This processes every H1 bar and:
        1. Opens trades when entry_time is reached
        2. Updates floating P&L for all open trades
        3. Checks for SL/TP exits
        4. Checks drawdown limits
        
        Note: Uses UTC+3 for day boundaries (5ers/MT5 server time)
        """
        # Prepare trades
        pending_trades = self.prepare_trades(trades_df)
        print(f"  Prepared {len(pending_trades)} trades for simulation")
        
        if len(pending_trades) == 0:
            return pd.DataFrame()
        
        # Get date range
        min_date = pending_trades[0]['entry_time']
        max_date = pending_trades[-1]['entry_time'] + timedelta(days=30)
        
        # Get unique symbols
        symbols = set(t['symbol'] for t in pending_trades)
        
        # Build H1 timeline
        self.build_timeline(symbols, min_date, max_date)
        
        if len(self._h1_timeline) == 0:
            print("  ❌ No H1 data available!")
            return pd.DataFrame()
        
        # Get sorted timestamps
        all_timestamps = sorted(self._h1_timeline.keys())
        print(f"  Simulating {len(all_timestamps)} H1 bars...")
        print(f"  Using UTC+3 (server time) for day boundaries")
        
        # Index for pending trades
        pending_idx = 0
        
        # Process each H1 bar
        for bar_idx, timestamp in enumerate(all_timestamps):
            if progress and bar_idx % 1000 == 0:
                print(f"    Bar {bar_idx}/{len(all_timestamps)}, "
                      f"Open trades: {len(self.open_trades)}, "
                      f"Closed: {len(self.closed_trades)}")
            
            bar_data = self._h1_timeline[timestamp]
            
            # ═══════════════════════════════════════════════════════════════
            # CHECK FOR NEW DAY (using UTC+3 server time)
            # ═══════════════════════════════════════════════════════════════
            server_date = self._get_server_date(timestamp)
            
            if self.last_server_date is None or server_date > self.last_server_date:
                self.start_new_day(server_date)
                self.last_server_date = server_date
            
            # ═══════════════════════════════════════════════════════════════
            # 1. OPEN NEW TRADES
            # ═══════════════════════════════════════════════════════════════
            while pending_idx < len(pending_trades):
                trade_data = pending_trades[pending_idx]
                
                if trade_data['entry_time'] <= timestamp:
                    # Open the trade
                    new_trade = self.create_open_trade(trade_data)
                    self.open_trades[new_trade.trade_id] = new_trade
                    
                    if self.current_day:
                        self.current_day.trades_opened += 1
                    
                    pending_idx += 1
                else:
                    break
            
            # Track max concurrent
            self.max_concurrent_trades = max(self.max_concurrent_trades, len(self.open_trades))
            
            # ═══════════════════════════════════════════════════════════════
            # 2. CHECK EXITS (SL/TP)
            # ═══════════════════════════════════════════════════════════════
            closed_trades = self.check_trade_exits(timestamp, bar_data)
            self.closed_trades.extend(closed_trades)
            
            # ═══════════════════════════════════════════════════════════════
            # 3. CALCULATE FLOATING P&L
            # ═══════════════════════════════════════════════════════════════
            self.floating_pnl = self.calculate_floating_pnl(bar_data)
            self.equity = self.balance + self.floating_pnl
            
            # ═══════════════════════════════════════════════════════════════
            # 4. CHECK DRAWDOWNS
            # ═══════════════════════════════════════════════════════════════
            self.check_drawdowns(timestamp)
            
            # ═══════════════════════════════════════════════════════════════
            # 5. SAVE HOURLY SNAPSHOT (every 4 hours to save memory)
            # ═══════════════════════════════════════════════════════════════
            if bar_idx % 4 == 0 and self.current_day:
                self.hourly_snapshots.append(HourlySnapshot(
                    timestamp=timestamp,
                    balance=self.balance,
                    equity=self.equity,
                    floating_pnl=self.floating_pnl,
                    open_trades=len(self.open_trades),
                    daily_limit=self.current_day.min_equity_allowed,
                    total_limit=self.rules.stop_out_level,
                    daily_buffer=self.equity - self.current_day.min_equity_allowed,
                    total_buffer=self.equity - self.rules.stop_out_level,
                ))
            
            self.total_bars_processed += 1
        
        # Close remaining trades as TIMEOUT
        for trade_id, trade in list(self.open_trades.items()):
            trade.exit_time = all_timestamps[-1] if all_timestamps else datetime.now()
            trade.exit_reason = 'TIMEOUT'
            trade.is_closed = True
            self.closed_trades.append(trade)
        
        self.open_trades.clear()
        
        # Finalize last day
        if self.current_day:
            self.current_day.end_of_day_balance = self.balance
            self.current_day.end_of_day_equity = self.equity
            self.daily_states.append(self.current_day)
        
        # Convert to DataFrame
        results = []
        for trade in self.closed_trades:
            results.append({
                'trade_id': trade.trade_id,
                'symbol': trade.symbol,
                'direction': trade.direction,
                'entry_time': trade.entry_time,
                'entry_price': trade.entry_price,
                'stop_loss': trade.stop_loss,
                'risk': trade.risk,
                'exit_time': trade.exit_time,
                'exit_reason': trade.exit_reason,
                'rr': round(trade.realized_r, 4),
                'pnl_dollars': round(trade.realized_r * self.rules.risk_per_trade, 2),
                'is_winner': trade.realized_r > 0,
                'tp1_hit': trade.tp1_hit,
                'tp2_hit': trade.tp2_hit,
                'tp3_hit': trade.tp3_hit,
                'hours_in_trade': int((trade.exit_time - trade.entry_time).total_seconds() / 3600) if trade.exit_time else 0,
            })
        
        return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def find_run_directory(run_spec: str) -> Path:
    """Find run directory from various input formats."""
    if Path(run_spec).exists():
        return Path(run_spec)
    
    search_paths = [
        f"ftmo_analysis_output/TPE/history/{run_spec}",
        f"ftmo_analysis_output/VALIDATE/history/{run_spec}",
        f"ftmo_analysis_output/TPE/{run_spec}",
    ]
    
    for path in search_paths:
        if Path(path).exists():
            return Path(path)
    
    for pattern in [
        f"ftmo_analysis_output/*/history/{run_spec}*",
        f"ftmo_analysis_output/*/{run_spec}*",
    ]:
        matches = list(Path('.').glob(pattern))
        if matches:
            return matches[0]
    
    raise FileNotFoundError(f"Could not find run: {run_spec}")


def load_trades(run_dir: Path) -> pd.DataFrame:
    """Load trades from run directory."""
    patterns = ['best_trades_final.csv', '*trades_final*.csv', '*trades*.csv']
    
    for pattern in patterns:
        files = list(run_dir.glob(pattern))
        if files:
            df = pd.read_csv(files[0])
            print(f"📄 Loaded {len(df)} trades from {files[0].name}")
            return df
    
    raise FileNotFoundError(f"No trade file in {run_dir}")


def load_params(run_dir: Path) -> dict:
    """Load parameters from current_params.json (single source of truth)."""
    # Always use current_params.json for validation
    current_params = Path('params/current_params.json')
    if current_params.exists():
        with open(current_params) as f:
            data = json.load(f)
            params = data.get('parameters', data)
            # Unwrap nested structure like {"parameters": {"parameters": {...}}}
            if isinstance(params, dict) and 'parameters' in params and isinstance(params['parameters'], dict):
                params = params['parameters']
            print(f"✓ Using params/current_params.json")
            return params
    
    # Fallback to run directory if current_params.json doesn't exist
    for pf in ['best_params.json', 'params.json']:
        path = run_dir / pf
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                params = data.get('parameters', data)
                if isinstance(params, dict) and 'parameters' in params and isinstance(params['parameters'], dict):
                    params = params['parameters']
                print(f"⚠️  params/current_params.json not found; using {path}")
                return params
    return {}


def print_summary(simulator: FullH1Simulator, rules: PropFirmRules):
    """Print comprehensive summary."""
    print("\n" + "=" * 80)
    print("H1 SIMULATION SUMMARY WITH FULL DRAWDOWN ANALYSIS")
    print("=" * 80)
    
    results_df = pd.DataFrame([{
        'rr': t.realized_r,
        'is_winner': t.realized_r > 0,
        'exit_reason': t.exit_reason,
        'symbol': t.symbol,
        'tp1_hit': t.tp1_hit,
        'tp2_hit': t.tp2_hit,
        'tp3_hit': t.tp3_hit,
    } for t in simulator.closed_trades])
    
    if len(results_df) == 0:
        print("❌ No trades simulated!")
        return
    
    # Basic stats
    print(f"\n📊 TRADE STATISTICS:")
    print(f"   Total trades: {len(results_df)}")
    
    winners = results_df['is_winner'].sum()
    win_rate = winners / len(results_df) * 100
    print(f"   Winners: {winners} ({win_rate:.1f}%)")
    print(f"   Losers: {len(results_df) - winners} ({100-win_rate:.1f}%)")
    
    total_rr = results_df['rr'].sum()
    print(f"   Total R: {total_rr:+.2f}R")
    print(f"   Total P&L: ${total_rr * rules.risk_per_trade:+,.2f}")
    
    avg_win = results_df[results_df['is_winner']]['rr'].mean() if winners > 0 else 0
    avg_loss = results_df[~results_df['is_winner']]['rr'].mean() if len(results_df) - winners > 0 else 0
    print(f"   Avg Win: {avg_win:+.2f}R | Avg Loss: {avg_loss:.2f}R")
    
    # Exit reasons
    print(f"\n📊 EXIT REASONS:")
    for reason, count in results_df['exit_reason'].value_counts().items():
        print(f"   {reason}: {count} ({count/len(results_df)*100:.1f}%)")
    
    # TP hits
    print(f"\n📊 TP HIT DISTRIBUTION:")
    for tp in ['tp1', 'tp2', 'tp3']:
        hits = results_df[f'{tp}_hit'].sum()
        print(f"   {tp.upper()}: {hits} ({hits/len(results_df)*100:.1f}%)")
    
    # Max concurrent
    print(f"\n📊 CONCURRENT TRADES:")
    print(f"   Maximum open at once: {simulator.max_concurrent_trades}")
    print(f"   H1 bars processed: {simulator.total_bars_processed}")
    
    # DRAWDOWN ANALYSIS
    print(f"\n" + "=" * 80)
    print("🚨 DRAWDOWN ANALYSIS")
    print("=" * 80)
    
    print(f"\n📊 PROP FIRM RULES:")
    print(f"   Initial Balance: ${rules.initial_balance:,.0f}")
    print(f"   Total DD Stop-out: ${rules.stop_out_level:,.0f} (CONSTANT)")
    print(f"   Daily DD Limit: {rules.daily_dd_pct*100:.0f}% of previous day HWM")
    print(f"   Risk per Trade: ${rules.risk_per_trade:,.0f} ({rules.risk_per_trade_pct}%)")
    
    daily_breaches = [e for e in simulator.dd_events if e.breach_type == 'DAILY']
    total_breaches = [e for e in simulator.dd_events if e.breach_type == 'TOTAL']
    
    print(f"\n📊 BREACH SUMMARY:")
    print(f"   Daily DD Breaches: {len(daily_breaches)}")
    print(f"   Total DD Breaches: {len(total_breaches)}")
    
    if daily_breaches:
        print(f"\n   ⚠️  DAILY DD BREACH DETAILS:")
        for i, b in enumerate(daily_breaches[:15], 1):
            print(f"      {i}. {b.timestamp}")
            print(f"         Equity: ${b.equity:,.0f} < Limit: ${b.limit:,.0f}")
            print(f"         Balance: ${b.balance:,.0f} | Floating: ${b.floating_pnl:+,.0f}")
            print(f"         Open trades: {b.open_trades} ({', '.join(b.open_trade_symbols[:5])}{'...' if len(b.open_trade_symbols) > 5 else ''})")
        if len(daily_breaches) > 15:
            print(f"      ... and {len(daily_breaches)-15} more")
    
    if total_breaches:
        print(f"\n   🚨 TOTAL DD BREACH DETAILS:")
        for i, b in enumerate(total_breaches[:10], 1):
            print(f"      {i}. {b.timestamp}")
            print(f"         Equity: ${b.equity:,.0f} < Stop-out: ${b.limit:,.0f}")
            print(f"         Open trades: {b.open_trades}")
    
    # Daily stats
    if simulator.daily_states:
        print(f"\n📊 DAILY PERFORMANCE:")
        print(f"   Trading days: {len(simulator.daily_states)}")
        
        profitable = sum(1 for d in simulator.daily_states if d.realized_pnl > 0)
        breached = sum(1 for d in simulator.daily_states if d.daily_dd_breached)
        
        print(f"   Profitable days: {profitable} ({profitable/len(simulator.daily_states)*100:.1f}%)")
        print(f"   Days with DD breach: {breached}")
        
        max_dd_day = min(simulator.daily_states, key=lambda d: d.lowest_equity - d.high_water_mark)
        print(f"   Worst intraday DD: ${max_dd_day.lowest_equity - max_dd_day.high_water_mark:,.0f} on {max_dd_day.date}")
        
        max_open = max(d.max_open_trades for d in simulator.daily_states)
        print(f"   Max open trades (any day): {max_open}")
    
    # Final
    print(f"\n📊 FINAL RESULTS:")
    print(f"   Starting: ${rules.initial_balance:,.0f}")
    print(f"   Final: ${simulator.balance:,.0f}")
    print(f"   Net P&L: ${simulator.balance - rules.initial_balance:+,.0f}")
    print(f"   Return: {(simulator.balance/rules.initial_balance - 1)*100:+.1f}%")
    
    print(f"\n" + "=" * 80)
    if len(total_breaches) > 0:
        print("❌ RESULT: WOULD HAVE BREACHED TOTAL DRAWDOWN - ACCOUNT BLOWN")
    elif len(daily_breaches) > 0:
        print(f"⚠️  RESULT: PASSED TOTAL DD BUT BREACHED DAILY DD {len(daily_breaches)} TIMES")
        print("   In live trading, these would terminate the account!")
    else:
        print("✅ RESULT: PASSED ALL DRAWDOWN CHECKS!")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='Full H1 validation with drawdown checks')
    parser.add_argument('--run', type=str, required=True, help='Run name (e.g., run_017)')
    parser.add_argument('--balance', type=float, default=60000)
    parser.add_argument('--risk-pct', type=float, default=0.65)
    parser.add_argument('--daily-dd', type=float, default=0.05)
    parser.add_argument('--total-dd', type=float, default=0.10)
    parser.add_argument('--h1-dir', type=str, default='data/ohlcv')
    parser.add_argument('--output', type=str, default=None)
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("FULL H1 SIMULATION WITH DRAWDOWN TRACKING")
    print("=" * 80)
    
    # Find run
    try:
        run_dir = find_run_directory(args.run)
        print(f"📁 Run: {run_dir}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Load
    trades_df = load_trades(run_dir)
    params = load_params(run_dir)
    
    # Setup
    rules = PropFirmRules(
        initial_balance=args.balance,
        daily_dd_pct=args.daily_dd,
        total_dd_pct=args.total_dd,
        risk_per_trade_pct=args.risk_pct,
    )
    
    tp_levels = {
        'tp1': params.get('tp1_r_multiple', 0.6),
        'tp2': params.get('tp2_r_multiple', 1.2),
        'tp3': params.get('tp3_r_multiple', 2.0),
    }
    
    close_pcts = {
        'tp1': params.get('tp1_close_pct', 0.35),
        'tp2': params.get('tp2_close_pct', 0.30),
        'tp3': params.get('tp3_close_pct', 0.35),
    }
    
    print(f"\n📊 Configuration:")
    print(f"   Balance: ${rules.initial_balance:,.0f}")
    print(f"   Risk/trade: {rules.risk_per_trade_pct}% (${rules.risk_per_trade:,.0f})")
    print(f"   Daily DD: {rules.daily_dd_pct*100}%")
    print(f"   Total DD: {rules.total_dd_pct*100}% (stop-out: ${rules.stop_out_level:,.0f})")
    print(f"\n   TP Levels: {tp_levels}")
    print(f"   Day boundaries: UTC+3 (5ers/MT5 server time)")
    
    # Run simulation
    simulator = FullH1Simulator(
        rules=rules,
        h1_data_dir=args.h1_dir,
        tp_levels=tp_levels,
        close_pcts=close_pcts,
    )
    
    start = datetime.now()
    results_df = simulator.run_simulation(trades_df, progress=True)
    elapsed = (datetime.now() - start).total_seconds()
    
    print(f"\n  ✅ Simulation complete in {elapsed:.1f}s")
    
    # Summary
    print_summary(simulator, rules)
    
    # Save
    output_path = Path(args.output) if args.output else Path(f"analysis/h1_full_{run_dir.name}.csv")
    output_path.parent.mkdir(exist_ok=True)
    
    results_df.to_csv(output_path, index=False)
    print(f"\n✅ Trades: {output_path}")
    
    # DD events
    if simulator.dd_events:
        dd_df = pd.DataFrame([{
            'timestamp': e.timestamp,
            'type': e.breach_type,
            'equity': e.equity,
            'balance': e.balance,
            'floating_pnl': e.floating_pnl,
            'limit': e.limit,
            'deficit': e.deficit,
            'open_trades': e.open_trades,
            'symbols': ','.join(e.open_trade_symbols[:10]),
        } for e in simulator.dd_events])
        dd_path = output_path.with_name(output_path.stem + '_dd_events.csv')
        dd_df.to_csv(dd_path, index=False)
        print(f"✅ DD Events: {dd_path}")
    
    # Daily stats
    if simulator.daily_states:
        daily_df = pd.DataFrame([{
            'date': d.date,
            'start_balance': d.start_of_day_balance,
            'end_balance': d.end_of_day_balance,
            'hwm': d.high_water_mark,
            'min_equity_allowed': d.min_equity_allowed,
            'lowest_equity': d.lowest_equity,
            'highest_equity': d.highest_equity,
            'max_open_trades': d.max_open_trades,
            'trades_opened': d.trades_opened,
            'trades_closed': d.trades_closed,
            'realized_pnl': d.realized_pnl,
            'daily_dd_breached': d.daily_dd_breached,
        } for d in simulator.daily_states])
        daily_path = output_path.with_name(output_path.stem + '_daily.csv')
        daily_df.to_csv(daily_path, index=False)
        print(f"✅ Daily Stats: {daily_path}")
    
    # Snapshots
    if simulator.hourly_snapshots:
        snap_df = pd.DataFrame([{
            'timestamp': s.timestamp,
            'balance': s.balance,
            'equity': s.equity,
            'floating_pnl': s.floating_pnl,
            'open_trades': s.open_trades,
            'daily_buffer': s.daily_buffer,
            'total_buffer': s.total_buffer,
        } for s in simulator.hourly_snapshots])
        snap_path = output_path.with_name(output_path.stem + '_snapshots.csv')
        snap_df.to_csv(snap_path, index=False)
        print(f"✅ Snapshots: {snap_path}")


if __name__ == '__main__':
    main()
