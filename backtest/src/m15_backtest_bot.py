#!/usr/bin/env python3
"""
M15 BACKTEST BOT - Simulates main_live_bot.py on M15 historical data

This script replicates EXACTLY what main_live_bot.py would do, but uses M15
CSV data instead of live MT5 feeds. It's the most granular backtest possible.

KEY FEATURES (matching main_live_bot.py EXACTLY):
1. Daily scan at 00:00 server time (end of D1 candle)
2. Signal generation using compute_confluence() from strategy_core.py
3. Entry queue system - wait for price proximity before limit order
4. Limit orders fill when M15 price touches entry
5. Lot sizing calculated at FILL moment (compounding)
6. Dynamic lot sizing with confluence scaling
7. 3-TP partial close system with trailing stop
8. 5ers safety: DDD halt, TDD stop-out
9. Commissions: $4/lot forex

USAGE:
    python backtest/m15_backtest_bot.py --start 2023-01-01 --end 2025-12-31
    python backtest/m15_backtest_bot.py --balance 20000 --start 2024-01-01

Author: AI Assistant
Date: January 2026
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import pandas as pd
import numpy as np
from tqdm import tqdm

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from params.params_loader import load_strategy_params
from strategy_core import (
    StrategyParams,
    compute_confluence,
    _infer_trend,
    _pick_direction_from_bias,
)
from ftmo_config import FIVEERS_CONFIG


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestConfig:
    """Configuration matching main_live_bot.py exactly."""
    # Account
    initial_balance: float = 20_000
    
    # Risk
    risk_per_trade_pct: float = 0.6
    max_open_positions: int = 15  # Real limit
    
    # Entry queue (from ftmo_config.py)
    limit_order_proximity_r: float = 0.3  # Place limit when within 0.3R
    max_entry_distance_r: float = 1.5  # Skip if entry beyond 1.5R from current
    max_entry_wait_hours: int = 120  # 5 days max wait
    immediate_entry_r: float = 0.05  # Market order if within 0.05R
    
    # DDD Safety (5ers rules)
    daily_loss_warning_pct: float = 2.0
    daily_loss_reduce_pct: float = 3.0
    daily_loss_halt_pct: float = 3.5
    reduced_risk_pct: float = 0.4
    
    # TDD (static from initial balance)
    max_total_dd_pct: float = 10.0
    
    # Confluence scaling
    use_dynamic_scaling: bool = True
    confluence_base_score: int = 4
    confluence_scale_per_point: float = 0.15
    max_confluence_multiplier: float = 1.5
    min_confluence_multiplier: float = 0.6
    
    # Min quality factors for active signal
    min_quality_factors: int = 3


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT SPECS
# ═══════════════════════════════════════════════════════════════════════════

CONTRACT_SPECS = {
    # Forex - $4 commission per lot
    "EURUSD": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "GBPUSD": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "AUDUSD": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "NZDUSD": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "USDCAD": {"pip_size": 0.0001, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "USDCHF": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "USDJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "EURJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "GBPJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "AUDJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "NZDJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "CADJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "CHFJPY": {"pip_size": 0.01, "pip_value_per_lot": 6.67, "commission_per_lot": 4.0},
    "EURGBP": {"pip_size": 0.0001, "pip_value_per_lot": 12.5, "commission_per_lot": 4.0},
    "EURAUD": {"pip_size": 0.0001, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "EURCAD": {"pip_size": 0.0001, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "EURNZD": {"pip_size": 0.0001, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "EURCHF": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "GBPAUD": {"pip_size": 0.0001, "pip_value_per_lot": 6.5, "commission_per_lot": 4.0},
    "GBPCAD": {"pip_size": 0.0001, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "GBPNZD": {"pip_size": 0.0001, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "GBPCHF": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "AUDCAD": {"pip_size": 0.0001, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "AUDNZD": {"pip_size": 0.0001, "pip_value_per_lot": 6.0, "commission_per_lot": 4.0},
    "AUDCHF": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "NZDCAD": {"pip_size": 0.0001, "pip_value_per_lot": 7.5, "commission_per_lot": 4.0},
    "NZDCHF": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    "CADCHF": {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0},
    # Metals
    "XAUUSD": {"pip_size": 0.01, "pip_value_per_lot": 1.0, "commission_per_lot": 4.0},
    "XAGUSD": {"pip_size": 0.01, "pip_value_per_lot": 50.0, "commission_per_lot": 4.0},
    # Indices
    "SPX500USD": {"pip_size": 1.0, "pip_value_per_lot": 10.0, "commission_per_lot": 0.0},
    "NAS100USD": {"pip_size": 1.0, "pip_value_per_lot": 20.0, "commission_per_lot": 0.0},
    "US30USD": {"pip_size": 1.0, "pip_value_per_lot": 10.0, "commission_per_lot": 0.0},
    "UK100GBP": {"pip_size": 1.0, "pip_value_per_lot": 10.0, "commission_per_lot": 0.0},
    # Crypto
    "BTCUSD": {"pip_size": 1.0, "pip_value_per_lot": 1.0, "commission_per_lot": 0.0},
    "ETHUSD": {"pip_size": 0.01, "pip_value_per_lot": 0.01, "commission_per_lot": 0.0},
}

DEFAULT_SPEC = {"pip_size": 0.0001, "pip_value_per_lot": 10.0, "commission_per_lot": 4.0}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol format."""
    return symbol.replace("_", "").replace(".", "").replace("/", "").upper()


def get_specs(symbol: str) -> dict:
    """Get contract specifications."""
    # Try OANDA format first
    norm = normalize_symbol(symbol)
    if norm in CONTRACT_SPECS:
        return CONTRACT_SPECS[norm]
    # Try with original
    if symbol in CONTRACT_SPECS:
        return CONTRACT_SPECS[symbol]
    return DEFAULT_SPEC


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
    regime: str = "trend"
    
    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop_loss)


@dataclass
class PendingOrder:
    """Limit order waiting to fill."""
    signal: Signal
    created_at: datetime


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
    remaining_pct: float = 1.0
    partial_pnl: float = 0.0
    
    # Trailing
    trailing_sl: float = 0.0
    
    # Result
    closed: bool = False
    exit_time: Optional[datetime] = None
    exit_price: float = 0.0
    exit_reason: str = ""
    realized_pnl: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# LOT SIZE CALCULATION
# ═══════════════════════════════════════════════════════════════════════════

def calculate_lot_size(
    symbol: str,
    balance: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    confluence: int,
    config: BacktestConfig,
) -> Tuple[float, float]:
    """
    Calculate lot size at FILL moment.
    Returns: (lot_size, risk_usd)
    """
    specs = get_specs(symbol)
    pip_size = specs["pip_size"]
    pip_value_per_lot = specs["pip_value_per_lot"]
    
    stop_distance = abs(entry - stop_loss)
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
    
    # Risk per lot
    risk_per_lot = stop_pips * pip_value_per_lot
    
    if risk_per_lot <= 0:
        return 0.01, risk_usd
    
    # Lot size (capped at 100.0 per 5ers spec)
    lot_size = risk_usd / risk_per_lot
    lot_size = max(0.01, min(100.0, round(lot_size, 2)))
    
    return lot_size, risk_usd


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADER
# ═══════════════════════════════════════════════════════════════════════════

class DataLoader:
    """Loads and caches OHLCV data from CSV files."""
    
    def __init__(self, data_dir: str = "data/ohlcv"):
        self.data_dir = Path(data_dir)
        self.cache: Dict[str, Dict[str, pd.DataFrame]] = {}  # {symbol: {tf: df}}
    
    def load(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load data for symbol and timeframe."""
        if symbol in self.cache and timeframe in self.cache[symbol]:
            return self.cache[symbol][timeframe]
        
        # Symbol formats: OANDA (AUD_USD) vs simple (AUDUSD)
        symbol_no_underscore = symbol.replace("_", "")
        
        # Try various file patterns (both OANDA and simple format)
        patterns = [
            f"{symbol}_{timeframe}.csv",
            f"{symbol}_{timeframe}_2003_2025.csv",
            f"{symbol}_{timeframe}_2020_2025.csv",
            f"{symbol}_{timeframe}_2014_2025.csv",
            f"{symbol_no_underscore}_{timeframe}.csv",
            f"{symbol_no_underscore}_{timeframe}_2003_2025.csv",
            f"{symbol_no_underscore}_{timeframe}_2020_2025.csv",
        ]
        
        filepath = None
        for pattern in patterns:
            path = self.data_dir / pattern
            if path.exists():
                filepath = path
                break
        
        if filepath is None:
            return None
        
        try:
            df = pd.read_csv(filepath, parse_dates=['time'])
            df.columns = [c.lower() for c in df.columns]
            df = df.sort_values('time').reset_index(drop=True)
            
            # Cache
            if symbol not in self.cache:
                self.cache[symbol] = {}
            self.cache[symbol][timeframe] = df
            
            return df
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return None
    
    def get_candles_before(
        self,
        symbol: str,
        timeframe: str,
        before_time: datetime,
        count: int,
    ) -> List[Dict]:
        """Get N candles BEFORE a specific time (no look-ahead)."""
        df = self.load(symbol, timeframe)
        if df is None:
            return []
        
        # Filter to before_time
        mask = df['time'] < before_time
        subset = df[mask].tail(count)
        
        return subset.to_dict('records')


# ═══════════════════════════════════════════════════════════════════════════
# MAIN BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class M15BacktestBot:
    """
    Simulates main_live_bot.py on M15 historical data.
    
    This is the most accurate backtest - processes every M15 bar.
    """
    
    def __init__(
        self,
        symbols: List[str],
        params: StrategyParams,
        config: BacktestConfig,
        data_dir: str = "data/ohlcv",
        start_date: datetime = None,
        end_date: datetime = None,
    ):
        self.symbols = symbols
        self.params = params
        self.config = config
        self.data_loader = DataLoader(data_dir)
        self.start_date = start_date or datetime(2023, 1, 1)
        self.end_date = end_date or datetime(2025, 12, 31)
        
        # Account state
        self.balance = config.initial_balance
        self.day_start_equity = config.initial_balance
        self.current_date: Optional[date] = None
        
        # Trading state
        self.awaiting_entry: Dict[str, Tuple[Signal, datetime]] = {}
        self.pending_orders: Dict[str, PendingOrder] = {}
        self.open_positions: Dict[str, Position] = {}
        
        # Tracking
        self.closed_trades: List[Position] = []
        self.daily_snapshots: List[Dict] = []
        self.safety_events: List[Dict] = []
        
        # Stats
        self.total_commissions = 0.0
        self.signals_generated = 0
        self.trading_halted_today = False
        
        # Build M15 timeline
        self._build_timeline()
    
    def _build_timeline(self):
        """Build unified M15 timeline."""
        print("Building M15 timeline...")
        all_times = set()
        
        for symbol in self.symbols:
            df = self.data_loader.load(symbol, "M15")
            if df is not None:
                # Filter to date range
                mask = (df['time'] >= pd.Timestamp(self.start_date)) & \
                       (df['time'] <= pd.Timestamp(self.end_date))
                times = df.loc[mask, 'time'].tolist()
                all_times.update(times)
        
        self.timeline = sorted(all_times)
        print(f"  Timeline: {len(self.timeline)} M15 bars")
        print(f"  From {self.timeline[0]} to {self.timeline[-1]}")
        
        # Index M15 data for fast lookup
        self.m15_indexed: Dict[str, Dict[datetime, dict]] = {}
        for symbol in self.symbols:
            df = self.data_loader.load(symbol, "M15")
            if df is not None:
                self.m15_indexed[symbol] = {}
                for _, row in df.iterrows():
                    self.m15_indexed[symbol][row['time']] = {
                        'open': row['open'],
                        'high': row['high'],
                        'low': row['low'],
                        'close': row['close'],
                    }
    
    def get_bar(self, symbol: str, time: datetime) -> Optional[Dict]:
        """Get M15 bar for symbol at time."""
        if symbol not in self.m15_indexed:
            return None
        return self.m15_indexed[symbol].get(time)
    
    def calculate_equity(self, current_time: datetime) -> float:
        """Calculate equity including floating PnL."""
        equity = self.balance
        
        for pos in self.open_positions.values():
            bar = self.get_bar(pos.signal.symbol, current_time)
            if not bar:
                continue
            
            current_price = bar['close']
            risk = pos.signal.risk
            if risk <= 0:
                continue
            
            if pos.signal.direction == 'bullish':
                price_diff = current_price - pos.fill_price
            else:
                price_diff = pos.fill_price - current_price
            
            r_pnl = price_diff / risk
            usd_pnl = r_pnl * pos.risk_usd * pos.remaining_pct
            equity += usd_pnl
        
        return equity
    
    def check_ddd(self, equity: float) -> Tuple[float, str]:
        """Check Daily DrawDown."""
        if self.day_start_equity <= 0:
            return 0.0, 'ok'
        
        dd_pct = max(0, (self.day_start_equity - equity) / self.day_start_equity * 100)
        
        if dd_pct >= self.config.daily_loss_halt_pct:
            return dd_pct, 'halt'
        elif dd_pct >= self.config.daily_loss_reduce_pct:
            return dd_pct, 'reduce'
        elif dd_pct >= self.config.daily_loss_warning_pct:
            return dd_pct, 'warning'
        return dd_pct, 'ok'
    
    def check_tdd(self, equity: float) -> Tuple[float, bool]:
        """Check Total DrawDown (static from initial)."""
        dd_pct = max(0, (self.config.initial_balance - equity) / self.config.initial_balance * 100)
        return dd_pct, dd_pct >= self.config.max_total_dd_pct
    
    def scan_symbol(self, symbol: str, scan_time: datetime) -> Optional[Signal]:
        """
        Scan a symbol for trading signal.
        EXACTLY matches main_live_bot.py scan_symbol() logic.
        """
        # Skip if we already have a position or order for this symbol
        if symbol in self.open_positions:
            return None
        if symbol in self.pending_orders:
            return None
        if symbol in self.awaiting_entry:
            return None
        
        # Get historical data BEFORE scan_time (no look-ahead!)
        monthly = self.data_loader.get_candles_before(symbol, "MN", scan_time, 24)
        weekly = self.data_loader.get_candles_before(symbol, "W1", scan_time, 52)
        daily = self.data_loader.get_candles_before(symbol, "D1", scan_time, 100)
        h4 = self.data_loader.get_candles_before(symbol, "H4", scan_time, 50)
        
        if len(daily) < 50:
            return None
        if len(weekly) < 10:
            return None
        
        # Determine trends
        mn_trend = _infer_trend(monthly) if monthly else "mixed"
        wk_trend = _infer_trend(weekly) if weekly else "mixed"
        d_trend = _infer_trend(daily) if daily else "mixed"
        
        direction, _, regime = _pick_direction_from_bias(mn_trend, wk_trend, d_trend)
        
        if direction == "neutral":
            return None
        
        # Compute confluence
        flags, notes, trade_levels = compute_confluence(
            monthly, weekly, daily, h4 if h4 else daily[-20:],
            direction, self.params, None
        )
        
        entry, sl, tp1, tp2, tp3, tp4, tp5 = trade_levels
        
        if entry is None or sl is None:
            return None
        
        risk = abs(entry - sl)
        if risk <= 0:
            return None
        
        # Calculate confluence score
        confluence_score = sum(1 for v in flags.values() if v)
        
        # Quality factors (same as main_live_bot.py)
        quality_factors = sum([
            flags.get("location", False),
            flags.get("fib", False),
            flags.get("liquidity", False),
            flags.get("structure", False),
            flags.get("htf_bias", False),
        ])
        
        # Dynamic min confluence based on regime (same as ftmo_challenge_analyzer.py --validate)
        if regime == "trend":
            min_conf = self.params.trend_min_confluence
        else:
            min_conf = self.params.range_min_confluence
        
        # Must meet minimum confluence AND quality
        if confluence_score < min_conf:
            return None
        if quality_factors < self.config.min_quality_factors:
            return None
        
        # Calculate TP levels using params
        if direction == "bullish":
            tp1 = entry + risk * self.params.tp1_r_multiple
            tp2 = entry + risk * self.params.tp2_r_multiple
            tp3 = entry + risk * self.params.tp3_r_multiple
        else:
            tp1 = entry - risk * self.params.tp1_r_multiple
            tp2 = entry - risk * self.params.tp2_r_multiple
            tp3 = entry - risk * self.params.tp3_r_multiple
        
        return Signal(
            symbol=symbol,
            direction=direction,
            entry=entry,
            stop_loss=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            confluence=confluence_score,
            quality_factors=quality_factors,
            signal_time=scan_time,
            regime=regime,
        )
    
    def run_daily_scan(self, scan_time: datetime):
        """Run daily scan for all symbols (at 00:00)."""
        for symbol in self.symbols:
            signal = self.scan_symbol(symbol, scan_time)
            if signal is None:
                continue
            
            self.signals_generated += 1
            
            # Get current price to determine placement
            bar = self.get_bar(symbol, scan_time)
            if bar is None:
                continue
            
            current_price = bar['close']
            entry_distance_r = abs(current_price - signal.entry) / signal.risk
            
            # Check max entry distance
            if entry_distance_r > self.config.max_entry_distance_r:
                continue
            
            # Determine order type based on proximity
            if entry_distance_r <= self.config.immediate_entry_r:
                # Market order - fill immediately
                self._fill_order(signal, scan_time, current_price)
            elif entry_distance_r <= self.config.limit_order_proximity_r:
                # Limit order
                self.pending_orders[symbol] = PendingOrder(signal=signal, created_at=scan_time)
            else:
                # Entry queue - wait for proximity
                self.awaiting_entry[symbol] = (signal, scan_time)
    
    def check_entry_queue(self, current_time: datetime):
        """Check awaiting_entry queue."""
        to_remove = []
        
        for symbol, (signal, created_at) in list(self.awaiting_entry.items()):
            # Check expiry
            hours_waiting = (current_time - created_at).total_seconds() / 3600
            if hours_waiting > self.config.max_entry_wait_hours:
                to_remove.append(symbol)
                continue
            
            # Get current price
            bar = self.get_bar(symbol, current_time)
            if bar is None:
                continue
            
            current_price = bar['close']
            entry_distance_r = abs(current_price - signal.entry) / signal.risk
            
            # Move to limit order if close enough
            if entry_distance_r <= self.config.limit_order_proximity_r:
                self.pending_orders[symbol] = PendingOrder(signal=signal, created_at=current_time)
                to_remove.append(symbol)
        
        for symbol in to_remove:
            del self.awaiting_entry[symbol]
    
    def check_pending_orders(self, current_time: datetime):
        """Check if pending orders should fill."""
        to_remove = []
        
        for symbol, order in list(self.pending_orders.items()):
            bar = self.get_bar(symbol, current_time)
            if bar is None:
                continue
            
            signal = order.signal
            high, low = bar['high'], bar['low']
            
            # Check if entry price was touched
            if signal.direction == 'bullish':
                if low <= signal.entry:
                    self._fill_order(signal, current_time, signal.entry)
                    to_remove.append(symbol)
            else:
                if high >= signal.entry:
                    self._fill_order(signal, current_time, signal.entry)
                    to_remove.append(symbol)
        
        for symbol in to_remove:
            del self.pending_orders[symbol]
    
    def _fill_order(self, signal: Signal, fill_time: datetime, fill_price: float):
        """Fill an order and create position."""
        # Check max positions
        if len(self.open_positions) >= self.config.max_open_positions:
            return
        
        # Check DDD
        equity = self.calculate_equity(fill_time)
        ddd_pct, ddd_action = self.check_ddd(equity)
        if ddd_action == 'halt':
            return
        
        risk_pct = self.config.risk_per_trade_pct
        if ddd_action == 'reduce':
            risk_pct = self.config.reduced_risk_pct
        
        # Calculate lot size at FILL moment (compounding!)
        lot_size, risk_usd = calculate_lot_size(
            symbol=signal.symbol,
            balance=self.balance,  # Current balance for compounding
            risk_pct=risk_pct,
            entry=fill_price,
            stop_loss=signal.stop_loss,
            confluence=signal.confluence,
            config=self.config,
        )
        
        specs = get_specs(signal.symbol)
        commission = lot_size * specs.get("commission_per_lot", 4.0)
        
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
        """Manage open positions - check SL/TP."""
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            if pos.closed:
                continue
            
            bar = self.get_bar(symbol, current_time)
            if bar is None:
                continue
            
            high, low = bar['high'], bar['low']
            signal = pos.signal
            risk = signal.risk
            
            # Check SL
            sl = pos.trailing_sl
            if signal.direction == 'bullish':
                if low <= sl:
                    self._close_position(pos, current_time, sl, "SL")
                    continue
            else:
                if high >= sl:
                    self._close_position(pos, current_time, sl, "SL")
                    continue
            
            # Check TP levels
            self._check_tp_levels(pos, current_time, high, low)
    
    def _check_tp_levels(self, pos: Position, current_time: datetime, high: float, low: float):
        """Check TP levels and apply partial closes."""
        signal = pos.signal
        risk = signal.risk
        
        # TP1
        if not pos.tp1_hit:
            hit = (signal.direction == 'bullish' and high >= signal.tp1) or \
                  (signal.direction == 'bearish' and low <= signal.tp1)
            if hit:
                pos.tp1_hit = True
                close_pct = self.params.tp1_close_pct
                
                # Book profit at TP1
                tp1_r = self.params.tp1_r_multiple
                partial_profit = tp1_r * pos.risk_usd * close_pct
                pos.partial_pnl += partial_profit
                self.balance += partial_profit
                
                pos.remaining_pct -= close_pct
                pos.trailing_sl = pos.fill_price  # Move to breakeven
        
        # TP2
        elif not pos.tp2_hit:
            hit = (signal.direction == 'bullish' and high >= signal.tp2) or \
                  (signal.direction == 'bearish' and low <= signal.tp2)
            if hit:
                pos.tp2_hit = True
                close_pct = self.params.tp2_close_pct
                
                tp2_r = self.params.tp2_r_multiple
                partial_profit = tp2_r * pos.risk_usd * close_pct
                pos.partial_pnl += partial_profit
                self.balance += partial_profit
                
                pos.remaining_pct -= close_pct
                
                # Trail to TP1 + 0.5R
                if signal.direction == 'bullish':
                    pos.trailing_sl = signal.entry + risk * (self.params.tp1_r_multiple + 0.5)
                else:
                    pos.trailing_sl = signal.entry - risk * (self.params.tp1_r_multiple + 0.5)
        
        # TP3 - Close all remaining
        else:
            hit = (signal.direction == 'bullish' and high >= signal.tp3) or \
                  (signal.direction == 'bearish' and low <= signal.tp3)
            if hit:
                self._close_position(pos, current_time, signal.tp3, "TP3")
    
    def _close_position(self, pos: Position, exit_time: datetime, exit_price: float, reason: str):
        """Close position and record P&L."""
        if pos.closed:
            return
        
        pos.closed = True
        pos.exit_time = exit_time
        pos.exit_price = exit_price
        pos.exit_reason = reason
        
        signal = pos.signal
        risk = signal.risk
        
        # Final PnL for remaining position
        if signal.direction == 'bullish':
            price_diff = exit_price - pos.fill_price
        else:
            price_diff = pos.fill_price - exit_price
        
        final_r = price_diff / risk if risk > 0 else 0
        final_pnl_remaining = final_r * pos.risk_usd * pos.remaining_pct
        
        # Total PnL = partials + final - commission
        pos.realized_pnl = pos.partial_pnl + final_pnl_remaining - pos.commission
        
        self.balance += final_pnl_remaining - pos.commission
        self.total_commissions += pos.commission
        
        self.closed_trades.append(pos)
        del self.open_positions[signal.symbol]
    
    def close_all_positions(self, current_time: datetime, reason: str):
        """Emergency close all."""
        for symbol in list(self.open_positions.keys()):
            pos = self.open_positions[symbol]
            bar = self.get_bar(symbol, current_time)
            if bar:
                self._close_position(pos, current_time, bar['close'], reason)
        
        self.pending_orders.clear()
        self.awaiting_entry.clear()
    
    def run(self) -> Dict[str, Any]:
        """Run the full backtest."""
        print(f"\n{'='*70}")
        print("M15 BACKTEST - Replicating main_live_bot.py")
        print(f"{'='*70}")
        print(f"  Initial balance: ${self.config.initial_balance:,.0f}")
        print(f"  Symbols: {len(self.symbols)}")
        print(f"  M15 bars: {len(self.timeline)}")
        print(f"  Risk: {self.config.risk_per_trade_pct}%")
        print(f"{'='*70}\n")
        
        equity_low = self.balance
        equity_high = self.balance
        max_tdd = 0.0
        max_ddd = 0.0
        
        last_scanned_date: Optional[date] = None
        
        pbar = tqdm(self.timeline, desc="Simulating", mininterval=1.0)
        
        for current_time in pbar:
            current_dt = current_time.to_pydatetime() if hasattr(current_time, 'to_pydatetime') else current_time
            today = current_dt.date()
            
            # New day handling
            if today != self.current_date:
                # Save previous day snapshot
                if self.current_date:
                    equity = self.calculate_equity(current_dt)
                    ddd_pct, _ = self.check_ddd(equity)
                    tdd_pct, _ = self.check_tdd(equity)
                    
                    self.daily_snapshots.append({
                        'date': str(self.current_date),
                        'day_start_equity': self.day_start_equity,
                        'day_end_balance': self.balance,
                        'daily_pnl': self.balance - self.day_start_equity,
                        'daily_dd_pct': ddd_pct,
                        'total_dd_pct': tdd_pct,
                        'safety_triggered': self.trading_halted_today,
                    })
                
                # New day setup
                self.current_date = today
                self.day_start_equity = self.calculate_equity(current_dt)
                self.trading_halted_today = False
                equity_low = self.day_start_equity
                equity_high = self.day_start_equity
            
            # Skip weekends
            if current_dt.weekday() >= 5:
                continue
            
            # Calculate equity
            equity = self.calculate_equity(current_dt)
            equity_low = min(equity_low, equity)
            equity_high = max(equity_high, equity)
            
            # Check TDD stop-out
            tdd_pct, tdd_breached = self.check_tdd(equity)
            max_tdd = max(max_tdd, tdd_pct)
            if tdd_breached:
                print(f"\n🚨 TDD STOP-OUT at {current_dt}: {tdd_pct:.1f}%")
                self.close_all_positions(current_dt, "TDD_STOP_OUT")
                break
            
            # Check DDD
            ddd_pct, ddd_action = self.check_ddd(equity)
            max_ddd = max(max_ddd, ddd_pct)
            
            if ddd_action == 'halt' and not self.trading_halted_today:
                print(f"\n🚨 DDD HALT at {current_dt}: {ddd_pct:.1f}%")
                self.close_all_positions(current_dt, f"DDD_{ddd_pct:.1f}%")
                self.trading_halted_today = True
                self.safety_events.append({
                    'time': str(current_dt),
                    'type': 'DDD_HALT',
                    'ddd_pct': ddd_pct,
                    'equity': equity,
                })
                continue
            
            if self.trading_halted_today:
                continue
            
            # === DAILY SCAN at 00:00-00:15 ===
            # Only scan once per day at first M15 bar
            if today != last_scanned_date and current_dt.hour == 0 and current_dt.minute < 30:
                self.run_daily_scan(current_dt)
                last_scanned_date = today
            
            # Check entry queue
            if self.awaiting_entry:
                self.check_entry_queue(current_dt)
            
            # Check pending order fills
            if self.pending_orders:
                self.check_pending_orders(current_dt)
            
            # Manage positions
            if self.open_positions:
                self.manage_positions(current_dt)
        
        # Close remaining positions at end
        if self.timeline:
            last_time = self.timeline[-1]
            last_dt = last_time.to_pydatetime() if hasattr(last_time, 'to_pydatetime') else last_time
            for symbol in list(self.open_positions.keys()):
                pos = self.open_positions[symbol]
                bar = self.get_bar(symbol, last_time)
                if bar:
                    self._close_position(pos, last_dt, bar['close'], "END")
        
        # Compile results
        total_trades = len(self.closed_trades)
        winners = sum(1 for t in self.closed_trades if t.realized_pnl > 0)
        win_rate = winners / total_trades * 100 if total_trades > 0 else 0
        
        total_r = sum(
            (t.realized_pnl + t.commission) / t.risk_usd if t.risk_usd > 0 else 0
            for t in self.closed_trades
        )
        
        net_pnl = self.balance - self.config.initial_balance
        return_pct = net_pnl / self.config.initial_balance * 100
        
        results = {
            'initial_balance': self.config.initial_balance,
            'final_balance': round(self.balance, 2),
            'net_pnl': round(net_pnl, 2),
            'return_pct': round(return_pct, 2),
            'total_trades': total_trades,
            'signals_generated': self.signals_generated,
            'winners': winners,
            'losers': total_trades - winners,
            'win_rate': round(win_rate, 1),
            'total_r': round(total_r, 2),
            'total_commissions': round(self.total_commissions, 2),
            'max_tdd_pct': round(max_tdd, 2),
            'max_ddd_pct': round(max_ddd, 2),
            'safety_events': len(self.safety_events),
        }
        
        # Print results
        print(f"\n{'='*70}")
        print("BACKTEST RESULTS")
        print(f"{'='*70}")
        print(f"\n📊 SIGNALS & TRADES:")
        print(f"   Signals generated: {self.signals_generated}")
        print(f"   Total trades: {total_trades}")
        print(f"   Winners: {winners} ({win_rate:.1f}%)")
        print(f"   Losers: {total_trades - winners}")
        
        print(f"\n💰 PROFIT/LOSS:")
        print(f"   Net PnL: ${net_pnl:,.2f}")
        print(f"   Commissions: ${self.total_commissions:,.2f}")
        
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
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='M15 Backtest - Replicates main_live_bot.py')
    parser.add_argument('--start', type=str, default='2023-01-01', help='Start date')
    parser.add_argument('--end', type=str, default='2025-12-31', help='End date')
    parser.add_argument('--balance', type=float, default=20000, help='Initial balance')
    parser.add_argument('--data-dir', type=str, default='data/ohlcv', help='Data directory')
    parser.add_argument('--output', type=str, default='ftmo_analysis_output/m15_backtest', help='Output directory')
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = datetime.strptime(args.start, '%Y-%m-%d')
    end_date = datetime.strptime(args.end, '%Y-%m-%d')
    
    # Load params
    params = load_strategy_params()
    print(f"✓ Loaded params: min_confluence={params.min_confluence}, trend_min_conf={params.trend_min_confluence}, range_min_conf={params.range_min_confluence}")
    print(f"  TP levels: {params.tp1_r_multiple}R / {params.tp2_r_multiple}R / {params.tp3_r_multiple}R")
    print(f"  Close pcts: {params.tp1_close_pct*100}% / {params.tp2_close_pct*100}% / {params.tp3_close_pct*100}%")
    
    # Get symbols that have M15 data
    data_dir = Path(args.data_dir)
    available_symbols = []
    for f in data_dir.glob("*_M15*.csv"):
        # Extract symbol name
        name = f.stem
        name = name.replace("_M15", "").replace("_2003_2025", "").replace("_2020_2025", "")
        available_symbols.append(name)
    
    print(f"✓ Found M15 data for {len(available_symbols)} symbols: {available_symbols[:5]}...")
    
    # Create config
    config = BacktestConfig(
        initial_balance=args.balance,
        min_quality_factors=FIVEERS_CONFIG.min_quality_factors,
    )
    
    # Run backtest
    bot = M15BacktestBot(
        symbols=available_symbols,
        params=params,
        config=config,
        data_dir=args.data_dir,
        start_date=start_date,
        end_date=end_date,
    )
    
    results = bot.run()
    
    # Save results
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save trades
    if bot.closed_trades:
        trades_data = []
        for pos in bot.closed_trades:
            trades_data.append({
                'symbol': pos.signal.symbol,
                'direction': pos.signal.direction,
                'confluence': pos.signal.confluence,
                'quality_factors': pos.signal.quality_factors,
                'regime': pos.signal.regime,
                'signal_time': str(pos.signal.signal_time),
                'fill_time': str(pos.fill_time),
                'fill_price': pos.fill_price,
                'exit_time': str(pos.exit_time),
                'exit_price': pos.exit_price,
                'exit_reason': pos.exit_reason,
                'lot_size': pos.lot_size,
                'risk_usd': pos.risk_usd,
                'commission': pos.commission,
                'realized_pnl': pos.realized_pnl,
            })
        pd.DataFrame(trades_data).to_csv(output_dir / 'trades.csv', index=False)
    
    # Save daily snapshots
    if bot.daily_snapshots:
        pd.DataFrame(bot.daily_snapshots).to_csv(output_dir / 'daily_snapshots.csv', index=False)
    
    print(f"\n✅ Results saved to: {output_dir}")


if __name__ == '__main__':
    main()
