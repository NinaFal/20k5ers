#!/usr/bin/env python3
"""
REALISTIC H1 VALIDATOR - EXACT MATCH MET MAIN_LIVE_BOT

Dit script simuleert EXACT wat de main_live_bot zou doen:
- Dynamic lot sizing met confluence/streak scaling
- Commissies ($4/lot forex, $0 indices)
- Safety mechanism (close all bij 4.3% daily DD)
- Realistische P&L berekening

Usage:
    python scripts/validate_h1_realistic.py --run run_002 --balance 60000
    python scripts/validate_h1_realistic.py --trades best_trades.csv --trials 100
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import argparse
import sys
import warnings

warnings.filterwarnings('ignore')

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════
# CONTRACT SPECS (from tradr/risk/position_sizing.py)
# ═══════════════════════════════════════════════════════════════════════════

CONTRACT_SPECS = {
    # Forex - $4 commission per lot round trip
    "EURUSD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "GBPUSD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "USDJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    "USDCHF": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "USDCAD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "AUDUSD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "NZDUSD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "EURJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    "GBPJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    "EURGBP": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "EURAUD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "EURCAD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "EURNZD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "GBPAUD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "GBPCAD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "GBPNZD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "AUDJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    "AUDCAD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "AUDNZD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "NZDJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    "NZDCAD": {"pip_value": 0.0001, "contract_size": 100000, "pip_location": 4, "commission_per_lot": 4.0, "type": "forex"},
    "CADJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    "CHFJPY": {"pip_value": 0.01, "contract_size": 100000, "pip_location": 2, "commission_per_lot": 4.0, "type": "forex"},
    
    # Metals - $4 commission per lot
    "XAUUSD": {"pip_value": 0.01, "contract_size": 100, "pip_location": 2, "commission_per_lot": 4.0, "type": "metal"},
    "XAGUSD": {"pip_value": 0.001, "contract_size": 5000, "pip_location": 3, "commission_per_lot": 4.0, "type": "metal"},
    
    # Indices - NO commission (spread-based)
    "US30": {"pip_value": 1.0, "contract_size": 1, "pip_location": 0, "commission_per_lot": 0.0, "type": "index"},
    "US100": {"pip_value": 1.0, "contract_size": 1, "pip_location": 0, "commission_per_lot": 0.0, "type": "index"},
    "US500": {"pip_value": 1.0, "contract_size": 1, "pip_location": 0, "commission_per_lot": 0.0, "type": "index"},
    "SPX500USD": {"pip_value": 0.1, "contract_size": 1, "pip_location": 1, "commission_per_lot": 0.0, "type": "index"},
    "NAS100USD": {"pip_value": 0.1, "contract_size": 1, "pip_location": 1, "commission_per_lot": 0.0, "type": "index"},
    
    # Crypto - NO commission (spread-based)
    "BTCUSD": {"pip_value": 1.0, "contract_size": 1, "pip_location": 0, "commission_per_lot": 0.0, "type": "crypto"},
    "ETHUSD": {"pip_value": 0.01, "contract_size": 1, "pip_location": 2, "commission_per_lot": 0.0, "type": "crypto"},
}

DEFAULT_SPEC = {
    "pip_value": 0.0001,
    "contract_size": 100000,
    "pip_location": 4,
    "commission_per_lot": 4.0,
    "type": "forex"
}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol format."""
    return symbol.replace("_", "").replace(".", "").replace("/", "").upper()


def get_contract_specs(symbol: str) -> dict:
    """Get contract specifications for a symbol."""
    normalized = normalize_symbol(symbol)
    return CONTRACT_SPECS.get(normalized, DEFAULT_SPEC)


# ═══════════════════════════════════════════════════════════════════════════
# DYNAMIC LOT SIZING (EXACT COPY from ftmo_config.py)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ScalingConfig:
    """Scaling configuration - matches ftmo_config.py EXACTLY."""
    # Base settings
    risk_per_trade_pct: float = 0.6  # 0.6% base risk
    use_dynamic_lot_sizing: bool = True
    
    # Confluence-based scaling
    confluence_base_score: int = 4
    confluence_scale_per_point: float = 0.15  # +15% per point above base
    max_confluence_multiplier: float = 1.5
    min_confluence_multiplier: float = 0.6
    
    # Streak-based scaling
    win_streak_bonus_per_win: float = 0.05  # +5% per consecutive win
    max_win_streak_bonus: float = 0.20  # Cap at +20%
    loss_streak_reduction_per_loss: float = 0.10  # -10% per consecutive loss
    max_loss_streak_reduction: float = 0.40  # Cap at -40%
    consecutive_loss_halt: int = 5  # Halt after 5 consecutive losses
    
    # Equity curve scaling
    equity_boost_threshold_pct: float = 3.0  # Boost size after 3% profit
    equity_boost_multiplier: float = 1.10  # +10% size when profitable
    equity_reduce_threshold_pct: float = 2.0  # Reduce size after 2% loss
    equity_reduce_multiplier: float = 0.80  # -20% size when in drawdown
    
    # DD safety
    daily_loss_warning_pct: float = 2.5
    daily_loss_reduce_pct: float = 3.5
    daily_loss_halt_pct: float = 4.2  # CLOSE ALL AT 4.2%!
    total_dd_warning_pct: float = 5.0
    total_dd_emergency_pct: float = 7.0
    
    # Risk modes
    max_risk_aggressive_pct: float = 1.5
    max_risk_normal_pct: float = 0.75
    max_risk_conservative_pct: float = 0.5
    ultra_safe_risk_pct: float = 0.25


def get_dynamic_lot_size_multiplier(
    config: ScalingConfig,
    confluence_score: int,
    win_streak: int = 0,
    loss_streak: int = 0,
    current_profit_pct: float = 0.0,
    daily_loss_pct: float = 0.0,
    total_dd_pct: float = 0.0,
) -> float:
    """
    Calculate dynamic lot size multiplier - EXACT COPY from ftmo_config.py.
    
    Returns multiplier to apply to base risk (e.g., 1.2 = 20% larger position)
    """
    if not config.use_dynamic_lot_sizing:
        return 1.0
    
    multiplier = 1.0
    
    # 1. Confluence-based scaling
    confluence_diff = confluence_score - config.confluence_base_score
    confluence_mult = 1.0 + (confluence_diff * config.confluence_scale_per_point)
    confluence_mult = max(config.min_confluence_multiplier, 
                         min(config.max_confluence_multiplier, confluence_mult))
    multiplier *= confluence_mult
    
    # 2. Win streak bonus
    if win_streak > 0:
        streak_bonus = min(win_streak * config.win_streak_bonus_per_win, 
                          config.max_win_streak_bonus)
        multiplier *= (1.0 + streak_bonus)
    
    # 3. Loss streak reduction
    if loss_streak > 0:
        streak_reduction = min(loss_streak * config.loss_streak_reduction_per_loss,
                              config.max_loss_streak_reduction)
        multiplier *= (1.0 - streak_reduction)
    
    # 4. Equity curve adjustment
    if current_profit_pct >= config.equity_boost_threshold_pct:
        multiplier *= config.equity_boost_multiplier
    elif current_profit_pct <= -config.equity_reduce_threshold_pct:
        multiplier *= config.equity_reduce_multiplier
    
    # 5. Safety caps based on drawdown
    if daily_loss_pct >= config.daily_loss_warning_pct:
        multiplier *= 0.7  # Force 30% reduction
    if total_dd_pct >= config.total_dd_warning_pct:
        multiplier *= 0.7  # Force 30% reduction
    
    # Final bounds (never exceed 2x or go below 0.3x)
    multiplier = max(0.3, min(2.0, multiplier))
    
    return round(multiplier, 3)


def get_dynamic_risk_pct(
    config: ScalingConfig,
    confluence_score: int,
    win_streak: int = 0,
    loss_streak: int = 0,
    current_profit_pct: float = 0.0,
    daily_loss_pct: float = 0.0,
    total_dd_pct: float = 0.0,
) -> float:
    """
    Get dynamic risk percentage - EXACT COPY from ftmo_config.py.
    """
    if loss_streak >= config.consecutive_loss_halt:
        return 0.0  # Halt trading
    
    # Determine base risk based on DD levels
    base_risk = config.risk_per_trade_pct
    
    if daily_loss_pct >= config.daily_loss_reduce_pct:
        base_risk = config.max_risk_conservative_pct
    elif daily_loss_pct >= config.daily_loss_warning_pct:
        base_risk = config.max_risk_normal_pct
    elif total_dd_pct >= config.total_dd_emergency_pct:
        base_risk = config.max_risk_conservative_pct
    elif total_dd_pct >= config.total_dd_warning_pct:
        base_risk = config.max_risk_normal_pct
    
    # Apply multiplier
    multiplier = get_dynamic_lot_size_multiplier(
        config=config,
        confluence_score=confluence_score,
        win_streak=win_streak,
        loss_streak=loss_streak,
        current_profit_pct=current_profit_pct,
        daily_loss_pct=daily_loss_pct,
        total_dd_pct=total_dd_pct,
    )
    
    dynamic_risk = base_risk * multiplier
    
    # Bounds
    dynamic_risk = min(dynamic_risk, config.max_risk_aggressive_pct * 1.5)
    dynamic_risk = max(dynamic_risk, 0.25)
    
    return round(dynamic_risk, 4)


# ═══════════════════════════════════════════════════════════════════════════
# LOT SIZE CALCULATION (from tradr/risk/position_sizing.py)
# ═══════════════════════════════════════════════════════════════════════════

def get_pip_value_per_lot(symbol: str, entry_price: float = None) -> float:
    """Get pip value per standard lot in USD."""
    specs = get_contract_specs(symbol)
    pip_size = specs["pip_value"]
    contract_size = specs["contract_size"]
    
    normalized = normalize_symbol(symbol)
    
    # For USD quote pairs: pip value = pip_size * contract_size
    if normalized.endswith("USD"):
        return pip_size * contract_size
    
    # For USD base pairs: convert using price
    elif normalized.startswith("USD") and entry_price and entry_price > 0:
        return (pip_size / entry_price) * contract_size
    
    # For cross pairs: approximate
    else:
        return pip_size * contract_size


def calculate_lot_size(
    symbol: str,
    account_balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss_price: float,
    max_lot: float = 100.0,
    min_lot: float = 0.01,
) -> dict:
    """
    Calculate position size - EXACT COPY from tradr/risk/position_sizing.py.
    """
    specs = get_contract_specs(symbol)
    pip_value_unit = specs["pip_value"]
    pip_location = specs["pip_location"]
    
    # Calculate stop distance in pips
    stop_distance = abs(entry_price - stop_loss_price)
    
    if pip_location == 0:
        stop_pips = stop_distance
    else:
        stop_pips = stop_distance / pip_value_unit
    
    if stop_pips <= 0:
        return {"lot_size": 0.0, "risk_usd": 0.0, "stop_pips": 0.0, "error": "Invalid SL"}
    
    # Risk in USD
    risk_usd = account_balance * (risk_percent / 100)
    
    # Pip value per lot
    pip_value_per_lot = get_pip_value_per_lot(symbol, entry_price)
    
    if pip_value_per_lot <= 0:
        return {"lot_size": min_lot, "risk_usd": risk_usd, "stop_pips": stop_pips}
    
    # Lot size = risk / (pips * pip_value)
    lot_size = risk_usd / (stop_pips * pip_value_per_lot)
    
    # Round and clamp
    lot_size = round(lot_size, 2)
    lot_size = max(min_lot, min(max_lot, lot_size))
    
    # Actual risk
    actual_risk_usd = lot_size * stop_pips * pip_value_per_lot
    
    return {
        "lot_size": lot_size,
        "risk_usd": round(actual_risk_usd, 2),
        "stop_pips": round(stop_pips, 1),
        "pip_value_per_lot": pip_value_per_lot,
    }


# ═══════════════════════════════════════════════════════════════════════════
# COMMISSION CALCULATION
# ═══════════════════════════════════════════════════════════════════════════

def calculate_commission(symbol: str, lot_size: float) -> float:
    """Calculate round-trip commission for a trade."""
    specs = get_contract_specs(symbol)
    commission_per_lot = specs.get("commission_per_lot", 4.0)
    return lot_size * commission_per_lot


# ═══════════════════════════════════════════════════════════════════════════
# REALISTIC H1 SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TradeState:
    """State of an open trade."""
    trade_id: str
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    stop_loss: float
    risk: float  # Price distance to SL
    
    # Lot size and costs
    lot_size: float = 0.0
    risk_usd: float = 0.0
    commission: float = 0.0
    
    # TP levels
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    
    # State
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    trailing_sl: float = 0.0
    realized_r: float = 0.0
    remaining_pct: float = 1.0
    
    # Scaling info
    confluence_score: int = 4
    risk_pct_used: float = 0.6
    lot_multiplier: float = 1.0


@dataclass
class SimulationState:
    """Full simulation state."""
    # Account
    initial_balance: float = 60_000
    balance: float = 60_000
    equity: float = 60_000
    
    # DD tracking (5ers rules)
    total_dd_stop_out: float = 54_000  # CONSTANT 10% of initial
    daily_hwm: float = 60_000
    current_day: str = ""
    
    # Streaks
    win_streak: int = 0
    loss_streak: int = 0
    
    # Stats
    total_trades: int = 0
    winners: int = 0
    losers: int = 0
    total_r: float = 0.0
    total_pnl: float = 0.0
    total_commissions: float = 0.0
    
    # Safety
    daily_dd_breaches: int = 0
    total_dd_breached: bool = False
    safety_close_count: int = 0
    safety_close_pnl: float = 0.0
    trading_halted_today: bool = False  # NEW: No new trades after safety close
    
    # Open trades
    open_trades: Dict[str, TradeState] = field(default_factory=dict)


class RealisticH1Simulator:
    """
    Realistic H1 simulator that matches main_live_bot behavior EXACTLY.
    
    Features:
    - Dynamic lot sizing with scaling
    - Commissions ($4/lot forex, $0 indices)
    - Safety mechanism (close all bij 4.3% daily DD)
    - Proper lot size calculation
    """
    
    UTC_PLUS_3 = timezone(timedelta(hours=3))  # 5ers server time
    
    def __init__(
        self,
        initial_balance: float = 60_000,
        h1_data_dir: str = 'data/ohlcv',
        tp_levels: dict = None,
        close_pcts: dict = None,
        scaling_config: ScalingConfig = None,
    ):
        self.initial_balance = initial_balance
        self.h1_data_dir = Path(h1_data_dir)
        
        # TP levels from params
        self.tp_levels = tp_levels or {'tp1': 0.6, 'tp2': 1.2, 'tp3': 2.0}
        self.close_pcts = close_pcts or {'tp1': 0.35, 'tp2': 0.30, 'tp3': 0.35}
        
        # Scaling config
        self.scaling = scaling_config or ScalingConfig()
        
        # H1 data cache
        self._h1_cache: Dict[str, pd.DataFrame] = {}
        self._h1_timeline: Dict[datetime, Dict[str, dict]] = {}
        
        # State
        self.state = SimulationState(
            initial_balance=initial_balance,
            balance=initial_balance,
            equity=initial_balance,
            total_dd_stop_out=initial_balance * 0.90,  # CONSTANT!
            daily_hwm=initial_balance,
        )
        
        # Results
        self.closed_trades: List[dict] = []
        self.daily_stats: List[dict] = []
        self.safety_events: List[dict] = []
    
    def load_h1_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load H1 data for symbol (cached)."""
        if symbol in self._h1_cache:
            return self._h1_cache[symbol]
        
        # Try different file patterns
        normalized = normalize_symbol(symbol)
        patterns = [
            f"{symbol}_H1_*.csv",
            f"{symbol}_H1.csv",
            f"{normalized}_H1_*.csv",
            f"*{normalized}*H1*.csv",
        ]
        
        for pattern in patterns:
            files = list(self.h1_data_dir.glob(pattern))
            if files:
                df = pd.read_csv(files[0])
                # Find timestamp column
                for col in ['timestamp', 'time', 'datetime', 'date', 'Time']:
                    if col in df.columns:
                        df['timestamp'] = pd.to_datetime(df[col])
                        break
                df = df.sort_values('timestamp').reset_index(drop=True)
                df.columns = df.columns.str.lower()
                self._h1_cache[symbol] = df
                return df
        
        return None
    
    def build_timeline(self, symbols: set, start_date: datetime, end_date: datetime):
        """Build unified H1 timeline for all symbols."""
        self._h1_timeline = defaultdict(dict)
        
        # Ensure start/end are timezone-naive for comparison
        if hasattr(start_date, 'tzinfo') and start_date.tzinfo is not None:
            start_date = start_date.replace(tzinfo=None)
        if hasattr(end_date, 'tzinfo') and end_date.tzinfo is not None:
            end_date = end_date.replace(tzinfo=None)
        
        loaded_count = 0
        for symbol in symbols:
            df = self.load_h1_data(symbol)
            if df is None:
                continue
            
            loaded_count += 1
            # Ensure df timestamp is timezone-naive
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            
            mask = (df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)
            df_filtered = df[mask]
            
            for _, row in df_filtered.iterrows():
                ts = row['timestamp']
                self._h1_timeline[ts][symbol] = {
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'close': row['close'],
                }
        
        print(f"  Loaded H1 data for {loaded_count}/{len(symbols)} symbols")
        print(f"  Timeline: {len(self._h1_timeline)} unique hours")
    
    def _start_new_day(self, date_str: str):
        """Reset daily tracking at start of new day."""
        # Record previous day stats
        if self.state.current_day:
            self.daily_stats.append({
                'date': self.state.current_day,
                'balance': self.state.balance,
                'equity': self.state.equity,
                'daily_hwm': self.state.daily_hwm,
                'open_trades': len(self.state.open_trades),
                'trading_halted': self.state.trading_halted_today,
            })
        
        # Reset for new day
        self.state.current_day = date_str
        self.state.daily_hwm = max(self.state.balance, self.state.equity)
        self.state.trading_halted_today = False  # Reset halt flag for new day
        
        # Reset loss streak at new day (like taking a break after losses)
        # This prevents permanent halt after consecutive_loss_halt is reached
        self.state.loss_streak = 0
    
    def _calculate_floating_pnl(self, bar_data: dict) -> float:
        """Calculate total floating P&L for all open trades."""
        floating_pnl = 0.0
        
        for trade in self.state.open_trades.values():
            if trade.symbol not in bar_data:
                continue
            
            bar = bar_data[trade.symbol]
            current_price = bar['close']
            
            # Calculate unrealized P&L
            if trade.direction == 'bullish':
                price_diff = current_price - trade.entry_price
            else:
                price_diff = trade.entry_price - current_price
            
            # P&L = (price_diff / risk) * risk_usd * remaining_pct
            if trade.risk > 0:
                current_r = price_diff / trade.risk
                floating_pnl += current_r * trade.risk_usd * trade.remaining_pct
        
        return floating_pnl
    
    def _check_safety(self, timestamp: datetime) -> Tuple[bool, str]:
        """
        Check safety limits - CLOSE ALL if 4.3% daily DD reached.
        
        Returns (should_close_all, reason)
        """
        # Daily DD check
        daily_dd_amount = self.state.daily_hwm - self.state.equity
        daily_dd_pct = (daily_dd_amount / self.state.daily_hwm * 100) if self.state.daily_hwm > 0 else 0
        
        if daily_dd_pct >= self.scaling.daily_loss_halt_pct:
            return True, f"DAILY_DD_{daily_dd_pct:.1f}%"
        
        # Total DD check (8.5% safety, before 10% hard limit)
        if self.state.equity < self.state.total_dd_stop_out * 1.015:  # 1.5% buffer
            total_dd_pct = (self.initial_balance - self.state.equity) / self.initial_balance * 100
            return True, f"TOTAL_DD_{total_dd_pct:.1f}%"
        
        return False, ""
    
    def _close_all_trades(self, bar_data: dict, timestamp: datetime, reason: str):
        """SAFETY: Close all open trades immediately and halt trading for the day."""
        self.safety_events.append({
            'timestamp': timestamp,
            'reason': reason,
            'equity': self.state.equity,
            'open_trades': len(self.state.open_trades),
        })
        
        for trade_id, trade in list(self.state.open_trades.items()):
            if trade.symbol in bar_data:
                exit_price = bar_data[trade.symbol]['close']
            else:
                exit_price = trade.entry_price  # Fallback
            
            # Calculate P&L
            pnl = self._close_trade(trade, exit_price, f'SAFETY_{reason}', timestamp)
            
            self.state.safety_close_count += 1
            self.state.safety_close_pnl += pnl
        
        self.state.open_trades.clear()
        self.state.trading_halted_today = True  # NO NEW TRADES until next day
        # Reset daily HWM to current balance to prevent repeated triggers
        self.state.daily_hwm = self.state.balance
    
    def _open_trade(
        self,
        trade_data: dict,
        timestamp: datetime,
    ) -> Optional[TradeState]:
        """Open a new trade with proper lot sizing and scaling."""
        # Check if trading halted for today (after safety close)
        if self.state.trading_halted_today:
            return None
        
        symbol = trade_data['symbol']
        entry_price = trade_data['entry_price']
        stop_loss = trade_data['stop_loss']
        direction = trade_data['direction']
        confluence_score = trade_data.get('confluence_score', 4)
        
        # Calculate current profit %
        current_profit_pct = (self.state.balance - self.initial_balance) / self.initial_balance * 100
        
        # Calculate daily loss %
        daily_loss_pct = 0.0
        if self.state.equity < self.state.daily_hwm:
            daily_loss_pct = (self.state.daily_hwm - self.state.equity) / self.state.daily_hwm * 100
        
        # Calculate total DD %
        total_dd_pct = 0.0
        if self.state.equity < self.initial_balance:
            total_dd_pct = (self.initial_balance - self.state.equity) / self.initial_balance * 100
        
        # Get dynamic risk %
        risk_pct = get_dynamic_risk_pct(
            config=self.scaling,
            confluence_score=confluence_score,
            win_streak=self.state.win_streak,
            loss_streak=self.state.loss_streak,
            current_profit_pct=current_profit_pct,
            daily_loss_pct=daily_loss_pct,
            total_dd_pct=total_dd_pct,
        )
        
        if risk_pct <= 0:
            return None  # Trading halted
        
        # Calculate lot size
        lot_result = calculate_lot_size(
            symbol=symbol,
            account_balance=self.state.balance,
            risk_percent=risk_pct,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )
        
        lot_size = lot_result['lot_size']
        risk_usd = lot_result['risk_usd']
        
        # Calculate commission
        commission = calculate_commission(symbol, lot_size)
        
        # Calculate TP levels
        risk = abs(entry_price - stop_loss)
        if direction == 'bullish':
            tp1 = entry_price + risk * self.tp_levels['tp1']
            tp2 = entry_price + risk * self.tp_levels['tp2']
            tp3 = entry_price + risk * self.tp_levels['tp3']
        else:
            tp1 = entry_price - risk * self.tp_levels['tp1']
            tp2 = entry_price - risk * self.tp_levels['tp2']
            tp3 = entry_price - risk * self.tp_levels['tp3']
        
        # Calculate multiplier for logging
        base_risk = self.scaling.risk_per_trade_pct
        multiplier = risk_pct / base_risk if base_risk > 0 else 1.0
        
        trade = TradeState(
            trade_id=trade_data.get('trade_id', f"{symbol}_{timestamp}"),
            symbol=symbol,
            direction=direction,
            entry_time=timestamp,
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk=risk,
            lot_size=lot_size,
            risk_usd=risk_usd,
            commission=commission,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            trailing_sl=stop_loss,
            confluence_score=confluence_score,
            risk_pct_used=risk_pct,
            lot_multiplier=multiplier,
        )
        
        return trade
    
    def _close_trade(
        self,
        trade: TradeState,
        exit_price: float,
        exit_reason: str,
        timestamp: datetime,
    ) -> float:
        """Close trade and return net P&L."""
        # Calculate gross P&L
        if trade.direction == 'bullish':
            price_diff = exit_price - trade.entry_price
        else:
            price_diff = trade.entry_price - exit_price
        
        # P&L from remaining position
        if trade.risk > 0:
            exit_r = price_diff / trade.risk
            final_r = trade.realized_r + (exit_r * trade.remaining_pct)
        else:
            final_r = trade.realized_r
        
        gross_pnl = final_r * trade.risk_usd
        net_pnl = gross_pnl - trade.commission
        
        # Update state
        self.state.balance += net_pnl
        self.state.total_trades += 1
        self.state.total_r += final_r
        self.state.total_pnl += net_pnl
        self.state.total_commissions += trade.commission
        
        # Update streaks
        if net_pnl > 0:
            self.state.winners += 1
            self.state.win_streak += 1
            self.state.loss_streak = 0
        else:
            self.state.losers += 1
            self.state.loss_streak += 1
            self.state.win_streak = 0
        
        # Record closed trade
        self.closed_trades.append({
            'trade_id': trade.trade_id,
            'symbol': trade.symbol,
            'direction': trade.direction,
            'entry_time': trade.entry_time,
            'exit_time': timestamp,
            'entry_price': trade.entry_price,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'lot_size': trade.lot_size,
            'risk_usd': trade.risk_usd,
            'commission': trade.commission,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'final_r': final_r,
            'risk_pct_used': trade.risk_pct_used,
            'lot_multiplier': trade.lot_multiplier,
            'tp1_hit': trade.tp1_hit,
            'tp2_hit': trade.tp2_hit,
            'tp3_hit': trade.tp3_hit,
        })
        
        return net_pnl
    
    def _process_open_trade(
        self,
        trade: TradeState,
        bar: dict,
        timestamp: datetime,
    ) -> bool:
        """
        Process an open trade for current H1 bar.
        Returns True if trade should be closed.
        """
        high = bar['high']
        low = bar['low']
        close_trade = False
        
        if trade.direction == 'bullish':
            # Check SL/Trailing SL
            if low <= trade.trailing_sl:
                trail_r = (trade.trailing_sl - trade.entry_price) / trade.risk
                trade.realized_r += trade.remaining_pct * trail_r
                trade.remaining_pct = 0
                close_trade = True
            else:
                # Check TPs
                if not trade.tp1_hit and high >= trade.tp1:
                    trade.tp1_hit = True
                    trade.realized_r += trade.remaining_pct * self.close_pcts['tp1'] * self.tp_levels['tp1']
                    trade.remaining_pct *= (1 - self.close_pcts['tp1'])
                    trade.trailing_sl = trade.entry_price  # Move to BE
                
                if trade.tp1_hit and not trade.tp2_hit and high >= trade.tp2:
                    trade.tp2_hit = True
                    trade.realized_r += trade.remaining_pct * self.close_pcts['tp2'] * self.tp_levels['tp2']
                    trade.remaining_pct *= (1 - self.close_pcts['tp2'])
                    trade.trailing_sl = trade.tp1
                
                if trade.tp2_hit and not trade.tp3_hit and high >= trade.tp3:
                    trade.tp3_hit = True
                    trade.realized_r += trade.remaining_pct * self.tp_levels['tp3']
                    trade.remaining_pct = 0
                    close_trade = True
        
        else:  # Bearish
            if high >= trade.trailing_sl:
                trail_r = (trade.entry_price - trade.trailing_sl) / trade.risk
                trade.realized_r += trade.remaining_pct * trail_r
                trade.remaining_pct = 0
                close_trade = True
            else:
                if not trade.tp1_hit and low <= trade.tp1:
                    trade.tp1_hit = True
                    trade.realized_r += trade.remaining_pct * self.close_pcts['tp1'] * self.tp_levels['tp1']
                    trade.remaining_pct *= (1 - self.close_pcts['tp1'])
                    trade.trailing_sl = trade.entry_price
                
                if trade.tp1_hit and not trade.tp2_hit and low <= trade.tp2:
                    trade.tp2_hit = True
                    trade.realized_r += trade.remaining_pct * self.close_pcts['tp2'] * self.tp_levels['tp2']
                    trade.remaining_pct *= (1 - self.close_pcts['tp2'])
                    trade.trailing_sl = trade.tp1
                
                if trade.tp2_hit and not trade.tp3_hit and low <= trade.tp3:
                    trade.tp3_hit = True
                    trade.realized_r += trade.remaining_pct * self.tp_levels['tp3']
                    trade.remaining_pct = 0
                    close_trade = True
        
        return close_trade or trade.remaining_pct <= 0.001
    
    def simulate(self, trades_df: pd.DataFrame) -> dict:
        """
        Run full H1 simulation with scaling, commissions, and safety.
        """
        print("\n" + "=" * 70)
        print("REALISTIC H1 SIMULATION WITH SCALING")
        print("=" * 70)
        
        # Prepare trades
        trades = self._prepare_trades(trades_df)
        if not trades:
            return self._get_results()
        
        print(f"  Trades to simulate: {len(trades)}")
        print(f"  Initial balance: ${self.initial_balance:,.0f}")
        print(f"  Total DD stop-out: ${self.state.total_dd_stop_out:,.0f} (CONSTANT)")
        print(f"  Base risk: {self.scaling.risk_per_trade_pct}%")
        print(f"  Dynamic scaling: {'ON' if self.scaling.use_dynamic_lot_sizing else 'OFF'}")
        
        # Get date range
        min_date = min(t['entry_time'] for t in trades)
        max_date = max(t['entry_time'] for t in trades) + timedelta(days=30)
        symbols = set(t['symbol'] for t in trades)
        
        # Build timeline
        print(f"\n  Building H1 timeline for {len(symbols)} symbols...")
        self.build_timeline(symbols, min_date, max_date)
        
        if not self._h1_timeline:
            print("  ERROR: No H1 data loaded!")
            return self._get_results()
        
        # Sort timestamps
        all_timestamps = sorted(self._h1_timeline.keys())
        print(f"\n  Simulating {len(all_timestamps)} H1 bars...")
        
        # Simulation loop
        pending_idx = 0
        halted = False
        max_concurrent = 0
        
        for i, timestamp in enumerate(all_timestamps):
            if halted:
                break
            
            bar_data = self._h1_timeline[timestamp]
            
            # Check new day (UTC+3)
            server_time = timestamp.replace(tzinfo=timezone.utc)
            server_date = server_time.strftime('%Y-%m-%d')
            
            if server_date != self.state.current_day:
                self._start_new_day(server_date)
            
            # Open new trades
            while pending_idx < len(trades) and trades[pending_idx]['entry_time'] <= timestamp:
                trade_data = trades[pending_idx]
                trade = self._open_trade(trade_data, timestamp)
                if trade:
                    self.state.open_trades[trade.trade_id] = trade
                pending_idx += 1
            
            max_concurrent = max(max_concurrent, len(self.state.open_trades))
            
            # Process open trades
            closed_this_bar = []
            for trade_id, trade in self.state.open_trades.items():
                if trade.symbol not in bar_data:
                    continue
                
                bar = bar_data[trade.symbol]
                should_close = self._process_open_trade(trade, bar, timestamp)
                
                if should_close:
                    exit_price = bar['close']
                    if trade.tp3_hit:
                        exit_reason = 'TP3'
                    elif trade.tp2_hit:
                        exit_reason = 'TP2+Trail'
                    elif trade.tp1_hit:
                        exit_reason = 'TP1+Trail'
                    else:
                        exit_reason = 'SL'
                    
                    self._close_trade(trade, exit_price, exit_reason, timestamp)
                    closed_this_bar.append(trade_id)
            
            # Remove closed trades
            for tid in closed_this_bar:
                del self.state.open_trades[tid]
            
            # Update equity
            floating_pnl = self._calculate_floating_pnl(bar_data)
            self.state.equity = self.state.balance + floating_pnl
            
            # Check safety
            should_close_all, reason = self._check_safety(timestamp)
            if should_close_all:
                print(f"\n  🚨 SAFETY TRIGGERED at {timestamp}: {reason}")
                self._close_all_trades(bar_data, timestamp, reason)
                self.state.daily_dd_breaches += 1
            
            # Check total DD breach
            if self.state.equity < self.state.total_dd_stop_out:
                print(f"\n  ❌ TOTAL DD BREACHED at {timestamp}!")
                self.state.total_dd_breached = True
                halted = True
            
            # Progress
            if i % 2000 == 0:
                print(f"    Bar {i}/{len(all_timestamps)}, Open: {len(self.state.open_trades)}, "
                      f"Closed: {len(self.closed_trades)}, Balance: ${self.state.balance:,.0f}")
        
        # Close remaining trades at timeout
        if self.state.open_trades:
            last_bar = self._h1_timeline.get(all_timestamps[-1], {})
            for trade_id, trade in list(self.state.open_trades.items()):
                if trade.symbol in last_bar:
                    exit_price = last_bar[trade.symbol]['close']
                else:
                    exit_price = trade.entry_price
                self._close_trade(trade, exit_price, 'TIMEOUT', all_timestamps[-1])
            self.state.open_trades.clear()
        
        # Final daily stat
        if self.state.current_day:
            self.daily_stats.append({
                'date': self.state.current_day,
                'balance': self.state.balance,
                'equity': self.state.equity,
                'daily_hwm': self.state.daily_hwm,
                'open_trades': 0,
            })
        
        self._print_summary(max_concurrent)
        return self._get_results()
    
    def _prepare_trades(self, df: pd.DataFrame) -> List[dict]:
        """Convert DataFrame to list of trade dicts."""
        trades = []
        
        for idx, row in df.iterrows():
            # Get symbol
            symbol = row.get('symbol', row.get('pair', ''))
            
            # Get direction
            direction = str(row.get('direction', row.get('signal_type', 'bullish'))).lower()
            
            # Get entry time - ensure timezone-naive
            entry_time = pd.to_datetime(row.get('entry_time', row.get('entry_date')))
            if hasattr(entry_time, 'tzinfo') and entry_time.tzinfo is not None:
                entry_time = entry_time.replace(tzinfo=None)
            
            # Get prices
            entry_price = float(row.get('entry_price', row.get('entry', 0)))
            stop_loss = float(row.get('stop_loss', row.get('sl', 0)))
            
            # Get confluence
            confluence = int(row.get('confluence_score', row.get('confluence', 4)))
            
            trade = {
                'trade_id': f"{symbol}_{idx}",
                'symbol': symbol,
                'direction': direction,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'confluence_score': confluence,
            }
            trades.append(trade)
        
        trades.sort(key=lambda x: x['entry_time'])
        return trades
    
    def _print_summary(self, max_concurrent: int):
        """Print simulation summary."""
        print("\n" + "=" * 70)
        print("SIMULATION COMPLETE")
        print("=" * 70)
        
        win_rate = (self.state.winners / self.state.total_trades * 100) if self.state.total_trades > 0 else 0
        
        print(f"\n📊 TRADE STATISTICS:")
        print(f"   Total trades: {self.state.total_trades}")
        print(f"   Winners: {self.state.winners} ({win_rate:.1f}%)")
        print(f"   Losers: {self.state.losers}")
        print(f"   Max concurrent: {max_concurrent}")
        
        gross_pnl = self.state.total_pnl + self.state.total_commissions
        print(f"\n📊 PROFIT BREAKDOWN:")
        print(f"   Gross P&L: ${gross_pnl:,.2f}")
        print(f"   Total Commissions: -${self.state.total_commissions:,.2f}")
        print(f"   ─────────────────────────────")
        print(f"   NET P&L: ${self.state.total_pnl:,.2f}")
        print(f"   Total R: {self.state.total_r:+.2f}R")
        
        print(f"\n📊 SCALING IMPACT:")
        if self.closed_trades:
            avg_mult = np.mean([t['lot_multiplier'] for t in self.closed_trades])
            avg_risk = np.mean([t['risk_pct_used'] for t in self.closed_trades])
            print(f"   Avg lot multiplier: {avg_mult:.2f}x")
            print(f"   Avg risk % used: {avg_risk:.3f}%")
        
        print(f"\n📊 SAFETY MECHANISM:")
        print(f"   Daily DD close-all triggers: {self.state.daily_dd_breaches}")
        print(f"   Trades closed by safety: {self.state.safety_close_count}")
        print(f"   Safety close P&L: ${self.state.safety_close_pnl:,.2f}")
        
        print(f"\n📊 DRAWDOWN ANALYSIS:")
        print(f"   Total DD Breached: {'YES ❌' if self.state.total_dd_breached else 'NO ✅'}")
        
        final_dd = (self.initial_balance - self.state.balance) / self.initial_balance * 100
        print(f"   Final DD: {final_dd:.2f}%")
        
        print(f"\n📊 FINAL RESULTS:")
        print(f"   Starting: ${self.initial_balance:,.0f}")
        print(f"   Final: ${self.state.balance:,.0f}")
        print(f"   Return: {(self.state.balance / self.initial_balance - 1) * 100:+.1f}%")
        
        if self.state.daily_dd_breaches == 0 and not self.state.total_dd_breached:
            print(f"\n{'='*70}")
            print("✅ RESULT: PASSED ALL DRAWDOWN CHECKS!")
            print(f"{'='*70}")
        else:
            print(f"\n{'='*70}")
            print(f"⚠️ RESULT: {self.state.daily_dd_breaches} SAFETY CLOSES, {'TOTAL DD BREACHED' if self.state.total_dd_breached else 'TOTAL DD OK'}")
            print(f"{'='*70}")
    
    def _get_results(self) -> dict:
        """Get results dict."""
        win_rate = (self.state.winners / self.state.total_trades * 100) if self.state.total_trades > 0 else 0
        
        return {
            'total_trades': self.state.total_trades,
            'winners': self.state.winners,
            'losers': self.state.losers,
            'win_rate': win_rate,
            'total_r': self.state.total_r,
            'gross_pnl': self.state.total_pnl + self.state.total_commissions,
            'total_commissions': self.state.total_commissions,
            'net_pnl': self.state.total_pnl,
            'daily_dd_breaches': self.state.daily_dd_breaches,
            'total_dd_breached': self.state.total_dd_breached,
            'safety_close_count': self.state.safety_close_count,
            'safety_close_pnl': self.state.safety_close_pnl,
            'final_balance': self.state.balance,
            'return_pct': (self.state.balance / self.initial_balance - 1) * 100,
            'closed_trades': self.closed_trades,
            'daily_stats': self.daily_stats,
            'safety_events': self.safety_events,
        }
    
    def save_results(self, output_dir: str, run_name: str):
        """Save results to files."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save trades
        if self.closed_trades:
            trades_df = pd.DataFrame(self.closed_trades)
            trades_df.to_csv(output_path / f"{run_name}_trades.csv", index=False)
        
        # Save daily stats
        if self.daily_stats:
            daily_df = pd.DataFrame(self.daily_stats)
            daily_df.to_csv(output_path / f"{run_name}_daily.csv", index=False)
        
        # Save safety events
        if self.safety_events:
            safety_df = pd.DataFrame(self.safety_events)
            safety_df.to_csv(output_path / f"{run_name}_safety.csv", index=False)
        
        # Save summary
        results = self._get_results()
        summary = {k: v for k, v in results.items() if not isinstance(v, list)}
        with open(output_path / f"{run_name}_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n✅ Results saved to {output_path}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def find_run_directory(run_spec: str) -> Path:
    """Find run directory."""
    if Path(run_spec).exists():
        return Path(run_spec)
    
    for pattern in [
        f"ftmo_analysis_output/TPE/history/{run_spec}",
        f"ftmo_analysis_output/VALIDATE/history/{run_spec}",
        f"ftmo_analysis_output/**/history/{run_spec}",
    ]:
        matches = list(Path('.').glob(pattern))
        if matches:
            return matches[0]
    
    raise FileNotFoundError(f"Run not found: {run_spec}")


def load_trades(source: str) -> pd.DataFrame:
    """Load trades from file or run directory."""
    path = Path(source)
    
    if path.is_file():
        return pd.read_csv(path)
    
    run_dir = find_run_directory(source)
    
    for pattern in ['best_trades_final.csv', '*trades*.csv']:
        files = list(run_dir.glob(pattern))
        if files:
            df = pd.read_csv(files[0])
            print(f"📄 Loaded {len(df)} trades from {files[0]}")
            return df
    
    raise FileNotFoundError(f"No trades file in {run_dir}")


def load_params() -> dict:
    """Load params from current_params.json (single source of truth)."""
    if Path('params/current_params.json').exists():
        with open('params/current_params.json') as f:
            data = json.load(f)
            if 'parameters' in data:
                print("✓ Using params/current_params.json")
                return data['parameters']
            return data
    
    print("⚠️ params/current_params.json not found, using defaults")
    return {}


def main():
    parser = argparse.ArgumentParser(description='Realistic H1 validator with scaling')
    parser.add_argument('--run', type=str, help='Run directory (e.g., run_002)')
    parser.add_argument('--trades', type=str, help='Direct path to trades CSV')
    parser.add_argument('--balance', type=float, default=60000)
    parser.add_argument('--h1-dir', type=str, default='data/ohlcv')
    parser.add_argument('--output', type=str, default='ftmo_analysis_output/hourly_validator')
    parser.add_argument('--no-scaling', action='store_true', help='Disable dynamic scaling')
    
    args = parser.parse_args()
    
    if not args.run and not args.trades:
        print("❌ Must provide --run or --trades")
        sys.exit(1)
    
    # Load trades
    source = args.trades if args.trades else args.run
    trades_df = load_trades(source)
    
    # Load params from current_params.json (single source of truth)
    params = load_params()
    
    # Extract TP levels from params
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
    
    # Setup scaling config
    scaling_config = ScalingConfig(
        risk_per_trade_pct=params.get('risk_per_trade_pct', 0.6),
        use_dynamic_lot_sizing=not args.no_scaling,
        # When scaling disabled, also disable consecutive loss halt
        consecutive_loss_halt=999 if args.no_scaling else 5,
    )
    
    print(f"\n📋 Configuration:")
    print(f"   TP Levels: {tp_levels}")
    print(f"   Close %s: {close_pcts}")
    print(f"   Base Risk: {scaling_config.risk_per_trade_pct}%")
    print(f"   Scaling: {'ON' if scaling_config.use_dynamic_lot_sizing else 'OFF'}")
    
    # Run simulation
    simulator = RealisticH1Simulator(
        initial_balance=args.balance,
        h1_data_dir=args.h1_dir,
        tp_levels=tp_levels,
        close_pcts=close_pcts,
        scaling_config=scaling_config,
    )
    
    results = simulator.simulate(trades_df)
    
    # Save results
    run_name = args.run or Path(args.trades).stem if args.trades else 'manual'
    simulator.save_results(args.output, f"{run_name}_realistic")
    
    print("\n✅ Done!")


if __name__ == '__main__':
    main()
