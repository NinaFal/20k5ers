#!/usr/bin/env python3
"""
MAIN LIVE BOT SIMULATOR - Exact Replication of main_live_bot.py

This script simulates EXACTLY what main_live_bot.py would do on historical data.
It's the final assessment to project realistic performance.

KEY FEATURES (matching main_live_bot.py):
1. Signal generation on daily close (00:10 server time)
2. Entry queue - wait for price proximity before placing limit order
3. Limit orders fill when H1 price touches entry
4. Lot sizing calculated at FILL moment (not signal moment)
5. Dynamic lot sizing with confluence scaling
6. 3-TP partial close system with trailing stop
7. 5ers safety: DDD halt, TDD stop-out
8. Compounding: 0.6% of current balance
9. Commissions: $4/lot forex

DIFFERENCES FROM validate_h1_realistic.py:
- Entry queue system (signals wait for proximity)
- Lot sizing at fill moment
- More accurate DDD tracking per H1 bar
- Matches exact main_live_bot.py logic

Author: AI Assistant
Date: January 6, 2026
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
import pandas as pd
import numpy as np
from tqdm import tqdm

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from params.params_loader import load_strategy_params
from strategy_core import StrategyParams


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION (matching ftmo_config.py and main_live_bot.py)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SimConfig:
    """Configuration matching main_live_bot.py exactly."""
    # Account
    initial_balance: float = 60_000
    
    # Risk
    risk_per_trade_pct: float = 0.6
    max_pending_orders: int = 100
    
    # Entry queue
    limit_order_proximity_r: float = 0.3  # Place limit when within 0.3R
    max_entry_distance_r: float = 1.5  # Remove if beyond 1.5R
    max_entry_wait_hours: int = 120  # 5 days max wait
    entry_check_interval_minutes: int = 5  # Check every 5 min (but we use H1)
    
    # Market order threshold
    immediate_entry_r: float = 0.05  # Market order if within 0.05R
    
    # DDD Safety (5ers rules)
    daily_loss_warning_pct: float = 2.0
    daily_loss_reduce_pct: float = 3.0
    daily_loss_halt_pct: float = 3.5
    reduced_risk_pct: float = 0.4  # Risk after DDD reduce
    
    # TDD (static from initial balance)
    max_total_dd_pct: float = 10.0
    
    # Scaling
    use_dynamic_scaling: bool = True
    confluence_base_score: int = 4
    confluence_scale_per_point: float = 0.15
    max_confluence_multiplier: float = 1.5
    min_confluence_multiplier: float = 0.6


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT SPECS (from tradr/risk/position_sizing.py)
# ═══════════════════════════════════════════════════════════════════════════

# pip_value = price movement for 1 pip
# pip_value_per_lot = how much $ moves per pip per lot
CONTRACT_SPECS = {
    # Forex - $4 commission per lot, pip value = 0.0001 (4 decimal), $10/pip/lot
    "EURUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "GBPUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "AUDUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "NZDUSD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    
    # JPY pairs - pip = 0.01
    "USDJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "EURJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "GBPJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "AUDJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "NZDJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "CADJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "CHFJPY": {"pip_size": 0.01, "contract_size": 100000, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    
    # Other forex pairs
    "USDCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "USDCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "EURGBP": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 12.5, "commission_per_lot": 4.0},
    "EURAUD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "EURCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "EURNZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "EURCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "GBPAUD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "GBPCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "GBPNZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "GBPCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "AUDCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "AUDNZD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "AUDCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "NZDCAD": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "NZDCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "CADCHF": {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    
    # Metals - CRITICAL: pip = 0.01 for gold, pip value = $1/pip/lot (100oz)
    "XAUUSD": {"pip_size": 0.01, "contract_size": 100, "pip_value_per_lot": 1.0, "commission_per_lot": 4.0},
    # Silver: pip = 0.01, 5000oz/lot, pip value = $50/pip/lot
    "XAGUSD": {"pip_size": 0.01, "contract_size": 5000, "pip_value_per_lot": 50.0, "commission_per_lot": 4.0},
    
    # Indices - NO commission, pip = 0.1 for display but we use $1/point
    "SPX500USD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0, "commission_per_lot": 0.0},
    "NAS100USD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0, "commission_per_lot": 0.0},
    
    # Crypto - use point value, 1 BTC contract
    "BTCUSD": {"pip_size": 1.0, "contract_size": 1, "pip_value_per_lot": 1.0, "commission_per_lot": 0.0},
    "ETHUSD": {"pip_size": 0.01, "contract_size": 1, "pip_value_per_lot": 0.01, "commission_per_lot": 0.0},
}

DEFAULT_SPEC = {"pip_size": 0.0001, "contract_size": 100000, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol format (remove underscores)."""
    return symbol.replace("_", "").replace(".", "").replace("/", "").upper()


def get_specs(symbol: str) -> dict:
    """Get contract specifications."""
    return CONTRACT_SPECS.get(normalize_symbol(symbol), DEFAULT_SPEC)


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """Trading signal from daily scan."""
    symbol: str
    direction: str  # 'bullish' or 'bearish'
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    confluence: int
    quality_factors: int
    signal_time: datetime
    risk: float = 0.0  # |entry - sl|
    
    def __post_init__(self):
        self.risk = abs(self.entry - self.stop_loss)


@dataclass
class PendingOrder:
    """Limit order waiting to fill."""
    signal: Signal
    created_at: datetime
    order_type: str = 'LIMIT'  # or 'MARKET'


@dataclass
class Position:
    """Open position."""
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
    remaining_pct: float = 1.0
    
    # Track partial profits
    partial_pnl: float = 0.0  # Accumulated partial close profits
    
    # Trailing
    trailing_sl: float = 0.0
    
    # Result
    closed: bool = False
    exit_time: Optional[datetime] = None
    exit_price: float = 0.0
    realized_pnl: float = 0.0
    realized_r: float = 0.0


@dataclass
class DailySnapshot:
    """Daily state snapshot."""
    date: str
    day_start_balance: float
    day_end_balance: float
    equity_low: float
    equity_high: float
    daily_pnl: float
    daily_dd_pct: float
    total_dd_pct: float
    trades_opened: int
    trades_closed: int
    safety_triggered: bool = False
    safety_reason: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# LOT SIZE CALCULATION
# ═══════════════════════════════════════════════════════════════════════════

def calculate_lot_size(
    symbol: str,
    balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    confluence: int = 4,
    config: SimConfig = None,
) -> Tuple[float, float]:
    """
    Calculate lot size - SIMPLIFIED and CORRECT.
    
    Returns: (lot_size, risk_usd)
    """
    config = config or SimConfig()
    specs = get_specs(symbol)
    
    pip_size = specs["pip_size"]
    pip_value_per_lot = specs["pip_value_per_lot"]
    
    # Stop distance in price
    stop_distance = abs(entry - stop_loss)
    
    # Stop distance in pips
    stop_pips = stop_distance / pip_size
    
    if stop_pips <= 0:
        return 0.01, 0.0
    
    # Apply confluence scaling
    if config.use_dynamic_scaling:
        confluence_diff = confluence - config.confluence_base_score
        multiplier = 1.0 + (confluence_diff * config.confluence_scale_per_point)
        multiplier = max(config.min_confluence_multiplier, 
                        min(config.max_confluence_multiplier, multiplier))
        risk_pct = risk_pct * multiplier
    
    # Risk in USD
    risk_usd = balance * (risk_pct / 100)
    
    # Risk per lot at this stop distance
    risk_per_lot = stop_pips * pip_value_per_lot
    
    if risk_per_lot <= 0:
        return 0.01, risk_usd
    
    # Lot size
    lot_size = risk_usd / risk_per_lot
    lot_size = max(0.01, min(100.0, round(lot_size, 2)))
    
    # Actual risk
    actual_risk = lot_size * risk_per_lot
    
    return lot_size, actual_risk


def calculate_commission(symbol: str, lot_size: float) -> float:
    """Calculate round-trip commission."""
    specs = get_specs(symbol)
    return lot_size * specs.get("commission_per_lot", 4.0)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

class MainLiveBotSimulator:
    """
    Simulates main_live_bot.py EXACTLY on historical H1 data.
    
    This is the definitive test of expected performance.
    """
    
    def __init__(
        self,
        trades_df: pd.DataFrame,
        h1_data: Dict[str, pd.DataFrame],
        params: StrategyParams,
        config: SimConfig = None,
    ):
        self.trades_df = trades_df
        self.h1_data = h1_data
        self.params = params
        self.config = config or SimConfig()
        
        # Preprocess trades by entry date
        self._prepare_trades()
        
        # Build unified H1 timeline
        self._build_timeline()
        
        # State
        self.balance = self.config.initial_balance
        self.day_start_balance = self.config.initial_balance
        self.current_date = None
        
        # Queues and positions
        self.awaiting_entry: Dict[str, Tuple[Signal, datetime]] = {}  # symbol -> (signal, created_at)
        self.pending_orders: Dict[str, PendingOrder] = {}
        self.open_positions: Dict[str, Position] = {}
        
        # Tracking
        self.closed_trades: List[Position] = []
        self.daily_snapshots: List[DailySnapshot] = []
        self.safety_events: List[Dict] = []
        
        # Stats
        self.total_commissions = 0.0
        self.win_streak = 0
        self.loss_streak = 0
        self.trading_halted_today = False
        
    def _prepare_trades(self):
        """Prepare trades indexed by entry date."""
        self.trades_by_date: Dict[str, List[Dict]] = defaultdict(list)
        
        for _, row in self.trades_df.iterrows():
            entry_dt = pd.to_datetime(row['entry_date'])
            if entry_dt.tzinfo:
                entry_dt = entry_dt.tz_localize(None)
            date_str = entry_dt.strftime('%Y-%m-%d')
            
            self.trades_by_date[date_str].append({
                'symbol': row['symbol'],
                'direction': row['direction'],
                'entry_price': row['entry_price'],
                'stop_loss': row['stop_loss'],
                'take_profit': row.get('take_profit', 0),
                'confluence_score': row.get('confluence_score', 4),
                'quality_factors': row.get('quality_factors', 0),
                'result_r': row.get('result_r', 0),
                'entry_date': entry_dt,
            })
    
    def _build_timeline(self):
        """Build unified H1 timeline across all symbols."""
        all_times = set()
        
        for symbol, df in self.h1_data.items():
            df['time'] = pd.to_datetime(df['time'])
            all_times.update(df['time'].tolist())
        
        self.timeline = sorted(all_times)
        print(f"  Timeline: {len(self.timeline)} H1 bars")
        
        # Index H1 data for fast lookup using dict of dicts
        self.h1_indexed: Dict[str, Dict[datetime, dict]] = {}
        for symbol, df in self.h1_data.items():
            norm = normalize_symbol(symbol)
            # Pre-convert to dict for O(1) lookup
            self.h1_indexed[norm] = {}
            for _, row in df.iterrows():
                self.h1_indexed[norm][row['time']] = {
                    'High': row.get('High', row.get('high')),
                    'Low': row.get('Low', row.get('low')),
                    'Close': row.get('Close', row.get('close')),
                    'Open': row.get('Open', row.get('open')),
                }
        
        # Pre-compute signal dates for O(1) lookup
        self.signal_dates = set(self.trades_by_date.keys())
    
    def get_h1_bar(self, symbol: str, time: datetime) -> Optional[dict]:
        """Get H1 bar for symbol at time."""
        norm = normalize_symbol(symbol)
        if norm not in self.h1_indexed:
            return None
        return self.h1_indexed[norm].get(time)
    
    def get_current_price(self, symbol: str, time: datetime, direction: str) -> Optional[float]:
        """Get current price (bid for sell, ask for buy approximation)."""
        bar = self.get_h1_bar(symbol, time)
        if not bar:
            return None
        # Use close as current price (simplified)
        return bar.get('Close', bar.get('close'))
    
    def calculate_equity(self, current_time: datetime) -> float:
        """Calculate current equity including floating PnL."""
        equity = self.balance
        
        for pos in self.open_positions.values():
            bar = self.get_h1_bar(pos.signal.symbol, current_time)
            if not bar:
                continue
            
            current_price = bar.get('Close', bar.get('close'))
            if current_price is None:
                continue
            
            # Calculate floating PnL
            if pos.signal.direction == 'bullish':
                price_diff = current_price - pos.fill_price
            else:
                price_diff = pos.fill_price - current_price
            
            # PnL in R
            r_pnl = price_diff / pos.signal.risk if pos.signal.risk > 0 else 0
            
            # PnL in USD (simplified - use risk_usd as base)
            usd_pnl = r_pnl * pos.risk_usd * pos.remaining_pct
            equity += usd_pnl
        
        return equity
    
    def check_ddd(self, equity: float) -> Tuple[float, str]:
        """Check Daily DrawDown. Returns (dd_pct, action)."""
        if self.day_start_balance <= 0:
            return 0.0, 'ok'
        
        dd_pct = (self.day_start_balance - equity) / self.day_start_balance * 100
        
        if dd_pct >= self.config.daily_loss_halt_pct:
            return dd_pct, 'halt'
        elif dd_pct >= self.config.daily_loss_reduce_pct:
            return dd_pct, 'reduce'
        elif dd_pct >= self.config.daily_loss_warning_pct:
            return dd_pct, 'warning'
        return dd_pct, 'ok'
    
    def check_tdd(self, equity: float) -> Tuple[float, bool]:
        """Check Total DrawDown (static from initial). Returns (dd_pct, breached)."""
        dd_pct = (self.config.initial_balance - equity) / self.config.initial_balance * 100
        breached = dd_pct >= self.config.max_total_dd_pct
        return dd_pct, breached
    
    def close_all_positions(self, current_time: datetime, reason: str):
        """Emergency close all positions."""
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            bar = self.get_h1_bar(symbol, current_time)
            if bar:
                exit_price = bar.get('Close', bar.get('close'))
                self._close_position(pos, current_time, exit_price, reason)
        
        # Clear pending orders too
        self.pending_orders.clear()
        self.awaiting_entry.clear()
    
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
        final_pnl_remaining = final_r * pos.risk_usd * pos.remaining_pct
        
        # Total PnL = partial closes + final close - commission
        pos.realized_pnl = pos.partial_pnl + final_pnl_remaining - pos.commission
        
        # Total R is more complex - but for simplicity use weighted average
        # This is approximate but good enough for assessment
        pos.realized_r = pos.realized_pnl / pos.risk_usd if pos.risk_usd > 0 else 0
        
        # Update balance
        self.balance += pos.realized_pnl
        self.total_commissions += pos.commission
        
        # Update streaks
        if pos.realized_pnl > 0:
            self.win_streak += 1
            self.loss_streak = 0
        else:
            self.loss_streak += 1
            self.win_streak = 0
        
        # Move to closed
        self.closed_trades.append(pos)
        if pos.signal.symbol in self.open_positions:
            del self.open_positions[pos.signal.symbol]
    
    def process_new_signals(self, current_time: datetime):
        """Process new signals from daily scan (at 00:00-01:00 bar)."""
        date_str = current_time.strftime('%Y-%m-%d')
        
        if date_str not in self.trades_by_date:
            return
        
        trades_today = self.trades_by_date[date_str]
        
        for trade in trades_today:
            symbol = trade['symbol']
            
            # Skip if already have position or order for this symbol
            if symbol in self.open_positions:
                continue
            if symbol in self.pending_orders:
                continue
            if symbol in self.awaiting_entry:
                continue
            
            # Get current price
            current_price = self.get_current_price(symbol, current_time, trade['direction'])
            if current_price is None:
                continue
            
            entry = trade['entry_price']
            sl = trade['stop_loss']
            risk = abs(entry - sl)
            
            if risk <= 0:
                continue
            
            # Calculate entry distance
            entry_distance_r = abs(current_price - entry) / risk
            
            # Calculate TP levels from params
            if trade['direction'] == 'bullish':
                tp1 = entry + risk * self.params.tp1_r_multiple
                tp2 = entry + risk * self.params.tp2_r_multiple
                tp3 = entry + risk * self.params.tp3_r_multiple
            else:
                tp1 = entry - risk * self.params.tp1_r_multiple
                tp2 = entry - risk * self.params.tp2_r_multiple
                tp3 = entry - risk * self.params.tp3_r_multiple
            
            signal = Signal(
                symbol=symbol,
                direction=trade['direction'],
                entry=entry,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                confluence=trade['confluence_score'],
                quality_factors=trade['quality_factors'],
                signal_time=current_time,
            )
            
            # Check proximity - add to appropriate queue
            if entry_distance_r <= self.config.immediate_entry_r:
                # Market order - fill immediately
                self._fill_order(signal, current_time, current_price)
            elif entry_distance_r <= self.config.limit_order_proximity_r:
                # Place limit order
                self.pending_orders[symbol] = PendingOrder(
                    signal=signal,
                    created_at=current_time,
                    order_type='LIMIT',
                )
            else:
                # Add to entry queue - wait for proximity
                self.awaiting_entry[symbol] = (signal, current_time)
    
    def check_entry_queue(self, current_time: datetime):
        """Check awaiting_entry queue for signals that are now close enough."""
        to_remove = []
        
        for symbol, (signal, created_at) in list(self.awaiting_entry.items()):
            # Check expiry
            hours_waiting = (current_time - created_at).total_seconds() / 3600
            if hours_waiting > self.config.max_entry_wait_hours:
                to_remove.append(symbol)
                continue
            
            # Get current price
            current_price = self.get_current_price(symbol, current_time, signal.direction)
            if current_price is None:
                continue
            
            entry_distance_r = abs(current_price - signal.entry) / signal.risk if signal.risk > 0 else 999
            
            # Check if too far now
            if entry_distance_r > self.config.max_entry_distance_r:
                to_remove.append(symbol)
                continue
            
            # Check if close enough for limit order
            if entry_distance_r <= self.config.limit_order_proximity_r:
                # Move to pending orders
                self.pending_orders[symbol] = PendingOrder(
                    signal=signal,
                    created_at=current_time,
                    order_type='LIMIT',
                )
                to_remove.append(symbol)
        
        for symbol in to_remove:
            if symbol in self.awaiting_entry:
                del self.awaiting_entry[symbol]
    
    def check_pending_orders(self, current_time: datetime):
        """Check if any pending limit orders should fill."""
        to_remove = []
        
        for symbol, order in list(self.pending_orders.items()):
            bar = self.get_h1_bar(symbol, current_time)
            if not bar:
                continue
            
            high = bar.get('High', bar.get('high'))
            low = bar.get('Low', bar.get('low'))
            
            if high is None or low is None:
                continue
            
            signal = order.signal
            entry = signal.entry
            
            # Check fill
            filled = False
            fill_price = entry
            
            if signal.direction == 'bullish':
                # Buy limit fills when price drops to entry
                if low <= entry:
                    filled = True
            else:
                # Sell limit fills when price rises to entry
                if high >= entry:
                    filled = True
            
            if filled:
                self._fill_order(signal, current_time, fill_price)
                to_remove.append(symbol)
        
        for symbol in to_remove:
            if symbol in self.pending_orders:
                del self.pending_orders[symbol]
    
    def _fill_order(self, signal: Signal, fill_time: datetime, fill_price: float):
        """Fill an order and create position."""
        # Check max positions
        total_exposure = len(self.open_positions) + len(self.pending_orders)
        if total_exposure >= self.config.max_pending_orders:
            return
        
        # Calculate lot size at FILL moment (key difference!)
        equity = self.calculate_equity(fill_time)
        
        # Check DDD - reduce risk if needed
        ddd_pct, ddd_action = self.check_ddd(equity)
        if ddd_action == 'halt':
            return  # Don't open new positions
        
        risk_pct = self.config.risk_per_trade_pct
        if ddd_action == 'reduce':
            risk_pct = self.config.reduced_risk_pct
        
        lot_size, risk_usd = calculate_lot_size(
            symbol=signal.symbol,
            balance=self.balance,  # Use current balance for compounding
            risk_pct=risk_pct,
            entry=fill_price,
            stop_loss=signal.stop_loss,
            confluence=signal.confluence,
            config=self.config,
        )
        
        commission = calculate_commission(signal.symbol, lot_size)
        
        position = Position(
            signal=signal,
            fill_time=fill_time,
            fill_price=fill_price,
            lot_size=lot_size,
            risk_usd=risk_usd,
            commission=commission,
            trailing_sl=signal.stop_loss,
        )
        
        self.open_positions[signal.symbol] = position
    
    def manage_positions(self, current_time: datetime):
        """Manage open positions - check SL, TP, trailing."""
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            if pos.closed:
                continue
            
            bar = self.get_h1_bar(symbol, current_time)
            if not bar:
                continue
            
            high = bar.get('High', bar.get('high'))
            low = bar.get('Low', bar.get('low'))
            close_price = bar.get('Close', bar.get('close'))
            
            if high is None or low is None:
                continue
            
            signal = pos.signal
            risk = signal.risk
            
            # Check SL hit
            sl = pos.trailing_sl if pos.trailing_sl else signal.stop_loss
            
            if signal.direction == 'bullish':
                if low <= sl:
                    self._close_position(pos, current_time, sl, "SL")
                    continue
            else:
                if high >= sl:
                    self._close_position(pos, current_time, sl, "SL")
                    continue
            
            # Calculate current R
            if signal.direction == 'bullish':
                current_r = (close_price - pos.fill_price) / risk
            else:
                current_r = (pos.fill_price - close_price) / risk
            
            # Check TP levels and apply partial closes
            self._check_tp_levels(pos, current_time, high, low, close_price)
    
    def _check_tp_levels(self, pos: Position, current_time: datetime, high: float, low: float, close_price: float):
        """Check TP levels and apply partial closes with profit booking."""
        signal = pos.signal
        risk = signal.risk
        
        # TP1
        if not pos.tp1_hit:
            tp1_hit = (signal.direction == 'bullish' and high >= signal.tp1) or \
                      (signal.direction == 'bearish' and low <= signal.tp1)
            if tp1_hit:
                pos.tp1_hit = True
                close_pct = self.params.tp1_close_pct
                
                # Book partial profit at TP1
                tp1_r = self.params.tp1_r_multiple
                partial_profit = tp1_r * pos.risk_usd * close_pct
                pos.partial_pnl += partial_profit
                self.balance += partial_profit
                
                pos.remaining_pct -= close_pct
                
                # Move SL to breakeven
                pos.trailing_sl = pos.fill_price
        
        # TP2
        elif not pos.tp2_hit:
            tp2_hit = (signal.direction == 'bullish' and high >= signal.tp2) or \
                      (signal.direction == 'bearish' and low <= signal.tp2)
            if tp2_hit:
                pos.tp2_hit = True
                close_pct = self.params.tp2_close_pct
                
                # Book partial profit at TP2
                tp2_r = self.params.tp2_r_multiple
                partial_profit = tp2_r * pos.risk_usd * close_pct
                pos.partial_pnl += partial_profit
                self.balance += partial_profit
                
                pos.remaining_pct -= close_pct
                
                # Trail SL to TP1 + 0.5R
                if signal.direction == 'bullish':
                    pos.trailing_sl = signal.entry + risk * (self.params.tp1_r_multiple + 0.5)
                else:
                    pos.trailing_sl = signal.entry - risk * (self.params.tp1_r_multiple + 0.5)
        
        # TP3 - Close all remaining
        elif not pos.tp3_hit:
            tp3_hit = (signal.direction == 'bullish' and high >= signal.tp3) or \
                      (signal.direction == 'bearish' and low <= signal.tp3)
            if tp3_hit:
                pos.tp3_hit = True
                self._close_position(pos, current_time, signal.tp3, "TP3")
    
    def simulate(self) -> Dict[str, Any]:
        """Run the full simulation (optimized)."""
        print(f"\n{'='*70}")
        print("MAIN LIVE BOT SIMULATION")
        print(f"{'='*70}")
        print(f"  Initial balance: ${self.config.initial_balance:,.0f}")
        print(f"  Trades to process: {len(self.trades_df)}")
        print(f"  H1 bars: {len(self.timeline)}")
        print(f"  Entry proximity: {self.config.limit_order_proximity_r}R")
        print(f"  DDD halt: {self.config.daily_loss_halt_pct}%")
        print(f"{'='*70}\n")
        
        equity_low = self.balance
        equity_high = self.balance
        max_tdd = 0.0
        max_ddd = 0.0
        
        # Use tqdm with larger update interval for speed
        pbar = tqdm(self.timeline, desc="Simulating", mininterval=1.0)
        
        for current_time in pbar:
            # New day?
            date_str = current_time.strftime('%Y-%m-%d')
            if date_str != self.current_date:
                # Save previous day snapshot
                if self.current_date:
                    equity = self.calculate_equity(current_time)
                    ddd_pct, _ = self.check_ddd(equity)
                    tdd_pct, _ = self.check_tdd(equity)
                    
                    self.daily_snapshots.append(DailySnapshot(
                        date=self.current_date,
                        day_start_balance=self.day_start_balance,
                        day_end_balance=self.balance,
                        equity_low=equity_low,
                        equity_high=equity_high,
                        daily_pnl=self.balance - self.day_start_balance,
                        daily_dd_pct=ddd_pct,
                        total_dd_pct=tdd_pct,
                        trades_opened=0,
                        trades_closed=0,
                        safety_triggered=self.trading_halted_today,
                    ))
                
                # Reset for new day - use EQUITY (includes floating) not balance
                self.current_date = date_str
                # Calculate equity at start of day
                day_start_equity = self.calculate_equity(current_time)
                self.day_start_balance = day_start_equity
                self.trading_halted_today = False
                equity_low = day_start_equity
                equity_high = day_start_equity
            
            # Skip weekends
            if current_time.weekday() >= 5:
                continue
            
            # OPTIMIZATION: Skip if nothing to do
            has_work = (
                self.open_positions or 
                self.pending_orders or 
                self.awaiting_entry or 
                date_str in self.signal_dates
            )
            
            if not has_work:
                continue
            
            # Calculate equity only when we have positions
            if self.open_positions:
                equity = self.calculate_equity(current_time)
                equity_low = min(equity_low, equity)
                equity_high = max(equity_high, equity)
                
                # Check TDD stop-out
                tdd_pct, tdd_breached = self.check_tdd(equity)
                max_tdd = max(max_tdd, tdd_pct)
                if tdd_breached:
                    print(f"\n🚨 TDD STOP-OUT at {current_time}: {tdd_pct:.1f}%")
                    self.close_all_positions(current_time, "TDD_STOP_OUT")
                    break
                
                # Check DDD
                ddd_pct, ddd_action = self.check_ddd(equity)
                max_ddd = max(max_ddd, ddd_pct)
                
                if ddd_action == 'halt' and not self.trading_halted_today:
                    print(f"\n🚨 DDD HALT at {current_time}: {ddd_pct:.1f}%")
                    self.close_all_positions(current_time, f"DDD_{ddd_pct:.1f}%")
                    self.trading_halted_today = True
                    self.safety_events.append({
                        'time': current_time.isoformat(),
                        'type': 'DDD_HALT',
                        'ddd_pct': ddd_pct,
                        'equity': equity,
                    })
                    continue
            
            if self.trading_halted_today:
                continue
            
            # Process signals at 00:00-01:00 bar (daily scan time)
            if current_time.hour == 0 and date_str in self.signal_dates:
                self.process_new_signals(current_time)
            
            # Check entry queue
            if self.awaiting_entry:
                self.check_entry_queue(current_time)
            
            # Check pending order fills
            if self.pending_orders:
                self.check_pending_orders(current_time)
            
            # Manage positions
            if self.open_positions:
                self.manage_positions(current_time)
        
        # Close any remaining positions at end
        if self.timeline:
            last_time = self.timeline[-1]
            for symbol in list(self.open_positions.keys()):
                pos = self.open_positions[symbol]
                bar = self.get_h1_bar(symbol, last_time)
                if bar:
                    self._close_position(pos, last_time, bar.get('Close', bar.get('close')), "END")
        
        # Calculate results
        total_trades = len(self.closed_trades)
        winners = sum(1 for t in self.closed_trades if t.realized_pnl > 0)
        losers = total_trades - winners
        win_rate = winners / total_trades * 100 if total_trades > 0 else 0
        
        total_r = sum(t.realized_r for t in self.closed_trades)
        gross_pnl = sum(t.realized_pnl + t.commission for t in self.closed_trades)
        net_pnl = self.balance - self.config.initial_balance
        
        return_pct = net_pnl / self.config.initial_balance * 100
        
        results = {
            'initial_balance': self.config.initial_balance,
            'final_balance': self.balance,
            'net_pnl': net_pnl,
            'return_pct': return_pct,
            'total_trades': total_trades,
            'winners': winners,
            'losers': losers,
            'win_rate': win_rate,
            'total_r': total_r,
            'gross_pnl': gross_pnl,
            'total_commissions': self.total_commissions,
            'max_tdd_pct': max_tdd,
            'max_ddd_pct': max_ddd,
            'safety_events': len(self.safety_events),
            'trades_in_entry_queue': len(self.awaiting_entry),
            'pending_orders': len(self.pending_orders),
        }
        
        # Print results
        print(f"\n{'='*70}")
        print("SIMULATION RESULTS")
        print(f"{'='*70}")
        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total trades: {total_trades}")
        print(f"   Winners: {winners} ({win_rate:.1f}%)")
        print(f"   Losers: {losers}")
        print(f"   Total R: {total_r:+.2f}R")
        
        print(f"\n💰 PROFIT/LOSS:")
        print(f"   Gross PnL: ${gross_pnl:,.2f}")
        print(f"   Commissions: ${self.total_commissions:,.2f}")
        print(f"   Net PnL: ${net_pnl:,.2f}")
        
        print(f"\n📈 ACCOUNT:")
        print(f"   Starting: ${self.config.initial_balance:,.0f}")
        print(f"   Final: ${self.balance:,.2f}")
        print(f"   Return: {return_pct:+.1f}%")
        
        print(f"\n📉 DRAWDOWN:")
        print(f"   Max TDD: {max_tdd:.2f}% (limit: {self.config.max_total_dd_pct}%)")
        print(f"   Max DDD: {max_ddd:.2f}% (limit: 5%)")
        
        print(f"\n🚨 SAFETY:")
        print(f"   DDD halt events: {len(self.safety_events)}")
        
        print(f"\n{'='*70}")
        
        return results


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_trades(path: str) -> pd.DataFrame:
    """Load trades from CSV."""
    df = pd.read_csv(path)
    print(f"✓ Loaded {len(df)} trades from {path}")
    return df


def _load_single_symbol(args):
    """Load H1 data for a single symbol (for parallel processing)."""
    symbol, data_path = args
    norm = normalize_symbol(symbol)
    filepath = Path(data_path) / f"{norm}_H1_2014_2025.csv"
    if filepath.exists():
        df = pd.read_csv(filepath)
        df['time'] = pd.to_datetime(df['time'])
        return symbol, df
    return symbol, None


def load_h1_data(data_dir: str, symbols: List[str], n_jobs: int = 4) -> Dict[str, pd.DataFrame]:
    """Load H1 data for symbols in parallel."""
    h1_data = {}
    
    args_list = [(s, data_dir) for s in symbols]
    
    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        futures = {executor.submit(_load_single_symbol, args): args[0] for args in args_list}
        for future in as_completed(futures):
            symbol, df = future.result()
            if df is not None:
                h1_data[symbol] = df
    
    print(f"✓ Loaded H1 data for {len(h1_data)}/{len(symbols)} symbols (parallel)")
    return h1_data


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Simulate main_live_bot.py on historical data')
    parser.add_argument('--trades', type=str, default='ftmo_analysis_output/VALIDATE/best_trades_final.csv')
    parser.add_argument('--h1-dir', type=str, default='data/ohlcv')
    parser.add_argument('--balance', type=float, default=60000)
    parser.add_argument('--output', type=str, default='ftmo_analysis_output/live_bot_simulation')
    
    args = parser.parse_args()
    
    # Load trades
    trades_df = load_trades(args.trades)
    
    # Get unique symbols
    symbols = trades_df['symbol'].unique().tolist()
    print(f"✓ Symbols in trades: {len(symbols)}")
    
    # Load H1 data
    h1_data = load_h1_data(args.h1_dir, symbols)
    
    if not h1_data:
        print("❌ No H1 data found!")
        return
    
    # Load params
    params = load_strategy_params()
    print(f"✓ Loaded params: TP1={params.tp1_r_multiple}R, TP2={params.tp2_r_multiple}R, TP3={params.tp3_r_multiple}R")
    
    # Create config
    config = SimConfig(initial_balance=args.balance)
    
    # Run simulation
    simulator = MainLiveBotSimulator(
        trades_df=trades_df,
        h1_data=h1_data,
        params=params,
        config=config,
    )
    
    results = simulator.simulate()
    
    # Save results
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'simulation_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    # Save closed trades
    trades_data = []
    for pos in simulator.closed_trades:
        trades_data.append({
            'symbol': pos.signal.symbol,
            'direction': pos.signal.direction,
            'fill_time': pos.fill_time.isoformat(),
            'fill_price': pos.fill_price,
            'exit_time': pos.exit_time.isoformat() if pos.exit_time else None,
            'exit_price': pos.exit_price,
            'lot_size': pos.lot_size,
            'risk_usd': pos.risk_usd,
            'commission': pos.commission,
            'realized_r': pos.realized_r,
            'realized_pnl': pos.realized_pnl,
        })
    
    pd.DataFrame(trades_data).to_csv(output_dir / 'closed_trades.csv', index=False)
    
    # Save daily snapshots
    if simulator.daily_snapshots:
        snapshots_data = [
            {
                'date': s.date,
                'day_start_balance': s.day_start_balance,
                'day_end_balance': s.day_end_balance,
                'daily_pnl': s.daily_pnl,
                'daily_dd_pct': s.daily_dd_pct,
                'total_dd_pct': s.total_dd_pct,
                'safety_triggered': s.safety_triggered,
            }
            for s in simulator.daily_snapshots
        ]
        pd.DataFrame(snapshots_data).to_csv(output_dir / 'daily_snapshots.csv', index=False)
    
    print(f"\n✅ Results saved to: {output_dir}")


if __name__ == '__main__':
    main()
