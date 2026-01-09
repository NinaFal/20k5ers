#!/usr/bin/env python3
"""
H1-Based Trade Simulator

EXACT reproduction of strategy_core.py simulate_trades() logic,
but using H1 data for more accurate exit timing.

This matches the CURRENT code behavior, including:
- TP levels: 0.6R, 1.2R, 2.0R, 2.5R, 3.5R (atr_tp_multiplier, NOT tp_r_multiple)
- 5 TP levels with close percentages as weights
- partial_exit_at_1r is IGNORED (not implemented in code)
- Step-wise trailing stop updates

Author: [Generated for botcreativehub]
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# LOAD PARAMS FROM current_params.json (ALIGNED with strategy_core.py)
# ═══════════════════════════════════════════════════════════════════════════

def _load_tp_params():
    """Load TP parameters from current_params.json."""
    params_file = Path(__file__).parent.parent.parent / "params" / "current_params.json"
    
    if params_file.exists():
        with open(params_file) as f:
            data = json.load(f)
        
        # Handle nested structure
        if "parameters" in data:
            if isinstance(data["parameters"], dict) and "parameters" in data["parameters"]:
                params = data["parameters"]["parameters"]
            else:
                params = data["parameters"]
        else:
            params = data
        
        return params
    else:
        # Fallback defaults
        return {
            "tp1_r_multiple": 1.7,
            "tp2_r_multiple": 2.7,
            "tp3_r_multiple": 6.0,
            "tp1_close_pct": 0.34,
            "tp2_close_pct": 0.16,
            "tp3_close_pct": 0.35,
            "trail_activation_r": 0.65,
        }

_PARAMS = _load_tp_params()

# TP R-multiples (from current_params.json - ALIGNED with optimizer)
TP1_R = _PARAMS.get("tp1_r_multiple", 1.7)
TP2_R = _PARAMS.get("tp2_r_multiple", 2.7)
TP3_R = _PARAMS.get("tp3_r_multiple", 6.0)
TP4_R = TP3_R + 1.0  # TP3 + 1R (legacy support)
TP5_R = TP3_R + 2.0  # TP3 + 2R (legacy support)

# Close percentages (weights for RR calculation)
TP1_CLOSE_PCT = _PARAMS.get("tp1_close_pct", 0.34)
TP2_CLOSE_PCT = _PARAMS.get("tp2_close_pct", 0.16)
TP3_CLOSE_PCT = _PARAMS.get("tp3_close_pct", 0.35)
TP4_CLOSE_PCT = 0.15  # legacy (for trades that reach TP4)
TP5_CLOSE_PCT = 0.00  # legacy

# Trailing activation
TRAIL_ACTIVATION_R = _PARAMS.get("trail_activation_r", 0.65)


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TradeSetup:
    """Trade setup from signal generator."""
    
    symbol: str
    direction: str  # 'bullish' or 'bearish'
    entry_time: datetime
    entry_price: float
    stop_loss: float
    
    # Calculated from entry and SL
    risk: float = 0.0  # |entry - sl|
    
    # TP prices (calculated: entry ± risk * multiplier)
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    tp4: float = 0.0
    tp5: float = 0.0
    
    # For tracking
    trade_id: str = ""
    
    def __post_init__(self):
        """Calculate risk and TP levels."""
        self.risk = abs(self.entry_price - self.stop_loss)
        
        if self.direction == 'bullish':
            self.tp1 = self.entry_price + self.risk * TP1_R
            self.tp2 = self.entry_price + self.risk * TP2_R
            self.tp3 = self.entry_price + self.risk * TP3_R
            self.tp4 = self.entry_price + self.risk * TP4_R
            self.tp5 = self.entry_price + self.risk * TP5_R
        else:  # bearish
            self.tp1 = self.entry_price - self.risk * TP1_R
            self.tp2 = self.entry_price - self.risk * TP2_R
            self.tp3 = self.entry_price - self.risk * TP3_R
            self.tp4 = self.entry_price - self.risk * TP4_R
            self.tp5 = self.entry_price - self.risk * TP5_R


@dataclass
class TradeResult:
    """Result of simulated trade."""
    
    # Original trade info
    symbol: str
    direction: str
    entry_time: datetime
    entry_price: float
    stop_loss: float
    risk: float
    trade_id: str = ""
    
    # Exit info
    exit_time: Optional[datetime] = None
    exit_price: float = 0.0
    exit_reason: str = ""  # 'SL', 'TP1+Trail', 'TP2+Trail', etc., 'TP5'
    
    # Result
    rr: float = 0.0  # Risk/Reward ratio
    is_winner: bool = False
    
    # TP tracking
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    tp4_hit: bool = False
    tp5_hit: bool = False
    
    # Stats
    hours_in_trade: int = 0
    max_favorable_r: float = 0.0
    max_adverse_r: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'risk': self.risk,
            'trade_id': self.trade_id,
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
            'exit_price': self.exit_price,
            'exit_reason': self.exit_reason,
            'rr': round(self.rr, 4),
            'is_winner': self.is_winner,
            'tp1_hit': self.tp1_hit,
            'tp2_hit': self.tp2_hit,
            'tp3_hit': self.tp3_hit,
            'tp4_hit': self.tp4_hit,
            'tp5_hit': self.tp5_hit,
            'hours_in_trade': self.hours_in_trade,
            'max_favorable_r': round(self.max_favorable_r, 4),
            'max_adverse_r': round(self.max_adverse_r, 4),
        }


# ═══════════════════════════════════════════════════════════════════════════
# H1 TRADE SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

class H1TradeSimulator:
    """
    Simulates trades using H1 data.
    
    EXACTLY matches strategy_core.py simulate_trades() logic.
    """
    
    def __init__(self, h1_data_dir: str = 'data/ohlcv'):
        self.h1_data_dir = Path(h1_data_dir)
        self._h1_cache: Dict[str, pd.DataFrame] = {}
        
        logger.info("H1TradeSimulator initialized")
        logger.info(f"  TP levels: {TP1_R}R, {TP2_R}R, {TP3_R}R, {TP4_R}R, {TP5_R}R")
        logger.info(f"  Trail activation: {TRAIL_ACTIVATION_R}R")
    
    def load_h1_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load H1 data for a symbol."""
        if symbol in self._h1_cache:
            return self._h1_cache[symbol]
        
        # Normalize symbol (remove underscore for file search)
        symbol_clean = symbol.replace('_', '')
        
        # Special mappings for indices and crypto
        symbol_mappings = {
            'SPX500_USD': 'SPX500USD',
            'NAS100_USD': 'NAS100USD',
            'BTC_USD': 'BTCUSD',
            'ETH_USD': 'ETHUSD',
            'XAU_USD': 'XAUUSD',
            'XAG_USD': 'XAGUSD',
        }
        
        mapped_symbol = symbol_mappings.get(symbol, symbol_clean)
        
        # Try different filename patterns (most specific first)
        patterns = [
            f"{mapped_symbol}_H1_*.csv",
            f"{symbol_clean}_H1_*.csv",
            f"{symbol}_H1_*.csv",
            f"{mapped_symbol}_H1.csv",
            f"{symbol_clean}_H1.csv",
        ]
        
        for pattern in patterns:
            files = list(self.h1_data_dir.glob(pattern))
            if files:
                df = pd.read_csv(files[0])
                # Normalize column names to lowercase
                df.columns = df.columns.str.lower()
                # Handle both 'time' and 'timestamp' column names
                if 'time' in df.columns and 'timestamp' not in df.columns:
                    df['timestamp'] = pd.to_datetime(df['time'])
                else:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp').reset_index(drop=True)
                self._h1_cache[symbol] = df
                logger.info(f"Loaded {len(df)} H1 bars for {symbol}")
                return df
        
        logger.warning(f"No H1 data found for {symbol}")
        return None
    
    def get_h1_bars_for_trade(
        self,
        symbol: str,
        entry_time: datetime,
        max_days: int = 30,
    ) -> Optional[pd.DataFrame]:
        """Get H1 bars from entry time."""
        h1_data = self.load_h1_data(symbol)
        
        if h1_data is None:
            return None
        
        # Remove timezone info for comparison (H1 data is timezone-naive)
        if hasattr(entry_time, 'tzinfo') and entry_time.tzinfo is not None:
            entry_time = entry_time.replace(tzinfo=None)
        
        end_time = entry_time + timedelta(days=max_days)
        mask = (h1_data['timestamp'] >= entry_time) & (h1_data['timestamp'] <= end_time)
        
        return h1_data[mask].copy()
    
    def simulate_trade(self, setup: TradeSetup) -> TradeResult:
        """
        Simulate a trade hour-by-hour.
        
        EXACTLY matches strategy_core.py simulate_trades() logic.
        """
        # Get H1 data
        h1_bars = self.get_h1_bars_for_trade(setup.symbol, setup.entry_time)
        
        if h1_bars is None or len(h1_bars) == 0:
            # No data - assume SL loss
            return TradeResult(
                symbol=setup.symbol,
                direction=setup.direction,
                entry_time=setup.entry_time,
                entry_price=setup.entry_price,
                stop_loss=setup.stop_loss,
                risk=setup.risk,
                trade_id=setup.trade_id,
                exit_time=setup.entry_time + timedelta(days=1),
                exit_price=setup.stop_loss,
                exit_reason='SL_NO_DATA',
                rr=-1.0,
                is_winner=False,
            )
        
        # Initialize state
        trailing_sl = setup.stop_loss
        trailing_activated = False
        
        tp1_hit = False
        tp2_hit = False
        tp3_hit = False
        tp4_hit = False
        tp5_hit = False
        
        trade_closed = False
        exit_time = None
        exit_price = 0.0
        exit_reason = ""
        rr = 0.0
        is_winner = False
        
        max_favorable_r = 0.0
        max_adverse_r = 0.0
        hours_count = 0
        
        # R-multiples for each TP (for RR calculation)
        tp1_rr = TP1_R  # 0.6
        tp2_rr = TP2_R  # 1.2
        tp3_rr = TP3_R  # 2.0
        tp4_rr = TP4_R  # 2.5
        tp5_rr = TP5_R  # 3.5
        
        # ═══════════════════════════════════════════════════════════════════
        # SIMULATE HOUR BY HOUR
        # ═══════════════════════════════════════════════════════════════════
        
        for _, bar in h1_bars.iterrows():
            if trade_closed:
                break
            
            hours_count += 1
            bar_time = bar['timestamp']
            bar_high = bar['high']
            bar_low = bar['low']
            
            # Track max favorable/adverse
            if setup.direction == 'bullish':
                favorable = (bar_high - setup.entry_price) / setup.risk
                adverse = (bar_low - setup.entry_price) / setup.risk
            else:
                favorable = (setup.entry_price - bar_low) / setup.risk
                adverse = (setup.entry_price - bar_high) / setup.risk
            
            max_favorable_r = max(max_favorable_r, favorable)
            max_adverse_r = min(max_adverse_r, adverse)
            
            # ═══════════════════════════════════════════════════════════════
            # BULLISH TRADE
            # ═══════════════════════════════════════════════════════════════
            
            if setup.direction == 'bullish':
                
                # [CHECK 1] SL/Trailing Hit
                if bar_low <= trailing_sl:
                    trade_closed = True
                    exit_time = bar_time
                    exit_price = trailing_sl
                    
                    # Calculate RR based on TPs hit
                    trail_rr = (trailing_sl - setup.entry_price) / setup.risk
                    
                    if tp4_hit:
                        remaining_pct = TP5_CLOSE_PCT
                        rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                              TP3_CLOSE_PCT * tp3_rr + TP4_CLOSE_PCT * tp4_rr +
                              remaining_pct * trail_rr)
                        exit_reason = "TP4+Trail"
                        is_winner = True
                    
                    elif tp3_hit:
                        remaining_pct = TP4_CLOSE_PCT + TP5_CLOSE_PCT
                        rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                              TP3_CLOSE_PCT * tp3_rr + remaining_pct * trail_rr)
                        exit_reason = "TP3+Trail"
                        is_winner = True
                    
                    elif tp2_hit:
                        remaining_pct = TP3_CLOSE_PCT + TP4_CLOSE_PCT + TP5_CLOSE_PCT
                        rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                              remaining_pct * trail_rr)
                        exit_reason = "TP2+Trail"
                        is_winner = (rr >= 0)
                    
                    elif tp1_hit:
                        remaining_pct = (TP2_CLOSE_PCT + TP3_CLOSE_PCT + 
                                        TP4_CLOSE_PCT + TP5_CLOSE_PCT)
                        rr = TP1_CLOSE_PCT * tp1_rr + remaining_pct * trail_rr
                        exit_reason = "TP1+Trail"
                        is_winner = (rr >= 0)
                    
                    else:  # No TP hit - pure SL
                        rr = -1.0
                        exit_reason = "SL"
                        is_winner = False
                    
                    continue  # Trade closed
                
                # [CHECK 2] TP1
                if not tp1_hit and bar_high >= setup.tp1:
                    tp1_hit = True
                    if tp1_rr >= TRAIL_ACTIVATION_R:
                        trailing_sl = setup.entry_price  # Breakeven
                        trailing_activated = True
                
                # [CHECK 3] TP2
                if tp1_hit and not tp2_hit and bar_high >= setup.tp2:
                    tp2_hit = True
                    if tp2_rr >= TRAIL_ACTIVATION_R:
                        trailing_sl = setup.tp1 + 0.5 * setup.risk
                        trailing_activated = True
                
                # [CHECK 4] TP3
                if tp2_hit and not tp3_hit and bar_high >= setup.tp3:
                    tp3_hit = True
                    trailing_sl = setup.tp2 + 0.5 * setup.risk
                
                # [CHECK 5] TP4
                if tp3_hit and not tp4_hit and bar_high >= setup.tp4:
                    tp4_hit = True
                    trailing_sl = setup.tp3 + 0.5 * setup.risk
                
                # [CHECK 6] TP5 - Full exit
                if tp4_hit and not tp5_hit and bar_high >= setup.tp5:
                    tp5_hit = True
                    trade_closed = True
                    exit_time = bar_time
                    exit_price = setup.tp5
                    exit_reason = "TP5"
                    rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                          TP3_CLOSE_PCT * tp3_rr + TP4_CLOSE_PCT * tp4_rr +
                          TP5_CLOSE_PCT * tp5_rr)
                    is_winner = True
            
            # ═══════════════════════════════════════════════════════════════
            # BEARISH TRADE
            # ═══════════════════════════════════════════════════════════════
            
            else:  # bearish
                
                # [CHECK 1] SL/Trailing Hit
                if bar_high >= trailing_sl:
                    trade_closed = True
                    exit_time = bar_time
                    exit_price = trailing_sl
                    
                    # Calculate RR based on TPs hit
                    trail_rr = (setup.entry_price - trailing_sl) / setup.risk
                    
                    if tp4_hit:
                        remaining_pct = TP5_CLOSE_PCT
                        rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                              TP3_CLOSE_PCT * tp3_rr + TP4_CLOSE_PCT * tp4_rr +
                              remaining_pct * trail_rr)
                        exit_reason = "TP4+Trail"
                        is_winner = True
                    
                    elif tp3_hit:
                        remaining_pct = TP4_CLOSE_PCT + TP5_CLOSE_PCT
                        rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                              TP3_CLOSE_PCT * tp3_rr + remaining_pct * trail_rr)
                        exit_reason = "TP3+Trail"
                        is_winner = True
                    
                    elif tp2_hit:
                        remaining_pct = TP3_CLOSE_PCT + TP4_CLOSE_PCT + TP5_CLOSE_PCT
                        rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                              remaining_pct * trail_rr)
                        exit_reason = "TP2+Trail"
                        is_winner = (rr >= 0)
                    
                    elif tp1_hit:
                        remaining_pct = (TP2_CLOSE_PCT + TP3_CLOSE_PCT + 
                                        TP4_CLOSE_PCT + TP5_CLOSE_PCT)
                        rr = TP1_CLOSE_PCT * tp1_rr + remaining_pct * trail_rr
                        exit_reason = "TP1+Trail"
                        is_winner = (rr >= 0)
                    
                    else:  # No TP hit - pure SL
                        rr = -1.0
                        exit_reason = "SL"
                        is_winner = False
                    
                    continue
                
                # [CHECK 2] TP1
                if not tp1_hit and bar_low <= setup.tp1:
                    tp1_hit = True
                    if tp1_rr >= TRAIL_ACTIVATION_R:
                        trailing_sl = setup.entry_price
                        trailing_activated = True
                
                # [CHECK 3] TP2
                if tp1_hit and not tp2_hit and bar_low <= setup.tp2:
                    tp2_hit = True
                    if tp2_rr >= TRAIL_ACTIVATION_R:
                        trailing_sl = setup.tp1 - 0.5 * setup.risk
                        trailing_activated = True
                
                # [CHECK 4] TP3
                if tp2_hit and not tp3_hit and bar_low <= setup.tp3:
                    tp3_hit = True
                    trailing_sl = setup.tp2 - 0.5 * setup.risk
                
                # [CHECK 5] TP4
                if tp3_hit and not tp4_hit and bar_low <= setup.tp4:
                    tp4_hit = True
                    trailing_sl = setup.tp3 - 0.5 * setup.risk
                
                # [CHECK 6] TP5
                if tp4_hit and not tp5_hit and bar_low <= setup.tp5:
                    tp5_hit = True
                    trade_closed = True
                    exit_time = bar_time
                    exit_price = setup.tp5
                    exit_reason = "TP5"
                    rr = (TP1_CLOSE_PCT * tp1_rr + TP2_CLOSE_PCT * tp2_rr +
                          TP3_CLOSE_PCT * tp3_rr + TP4_CLOSE_PCT * tp4_rr +
                          TP5_CLOSE_PCT * tp5_rr)
                    is_winner = True
        
        # If trade never closed (ran out of H1 data), mark as still open
        if not trade_closed:
            exit_reason = "STILL_OPEN"
            rr = 0.0
            is_winner = False
        
        return TradeResult(
            symbol=setup.symbol,
            direction=setup.direction,
            entry_time=setup.entry_time,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            risk=setup.risk,
            trade_id=setup.trade_id,
            exit_time=exit_time,
            exit_price=exit_price,
            exit_reason=exit_reason,
            rr=rr,
            is_winner=is_winner,
            tp1_hit=tp1_hit,
            tp2_hit=tp2_hit,
            tp3_hit=tp3_hit,
            tp4_hit=tp4_hit,
            tp5_hit=tp5_hit,
            hours_in_trade=hours_count,
            max_favorable_r=max_favorable_r,
            max_adverse_r=max_adverse_r,
        )


# ═══════════════════════════════════════════════════════════════════════════
# BATCH SIMULATION
# ═══════════════════════════════════════════════════════════════════════════

def simulate_trades_with_h1(
    trades_df: pd.DataFrame,
    h1_data_dir: str = 'data/ohlcv',
    progress: bool = True,
) -> pd.DataFrame:
    """
    Re-simulate all trades using H1 data.
    
    Args:
        trades_df: DataFrame with columns:
            - symbol, direction, entry_time, entry_price, stop_loss
        h1_data_dir: Directory with H1 CSV files
        progress: Show progress
    
    Returns:
        DataFrame with H1-simulated results
    """
    simulator = H1TradeSimulator(h1_data_dir=h1_data_dir)
    
    results = []
    total = len(trades_df)
    
    for idx, row in trades_df.iterrows():
        if progress and idx % 100 == 0:
            print(f"  Simulating trade {idx+1}/{total}...")
        
        # Handle different column names for entry time
        entry_time_col = None
        for col in ['entry_time', 'entry_date', 'date', 'timestamp']:
            if col in row.index:
                entry_time_col = col
                break
        
        if entry_time_col is None:
            raise ValueError(f"No entry time column found in row: {row.index.tolist()}")
        
        # Create setup
        setup = TradeSetup(
            symbol=row['symbol'],
            direction=row.get('direction', row.get('signal_type', 'bullish')),
            entry_time=pd.to_datetime(row[entry_time_col]),
            entry_price=float(row['entry_price']),
            stop_loss=float(row['stop_loss']),
            trade_id=str(row.get('trade_id', idx)),
        )
        
        # Simulate
        result = simulator.simulate_trade(setup)
        results.append(result.to_dict())
    
    return pd.DataFrame(results)


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("H1 TRADE SIMULATOR - TEST")
    print("=" * 60)
    print(f"\nTP Levels: {TP1_R}R, {TP2_R}R, {TP3_R}R, {TP4_R}R, {TP5_R}R")
    print(f"Close %: {TP1_CLOSE_PCT}, {TP2_CLOSE_PCT}, {TP3_CLOSE_PCT}, {TP4_CLOSE_PCT}, {TP5_CLOSE_PCT}")
    print(f"Trail activation: {TRAIL_ACTIVATION_R}R")
    
    # Test setup
    setup = TradeSetup(
        symbol='EUR_USD',
        direction='bullish',
        entry_time=datetime(2024, 6, 15, 22, 0),
        entry_price=1.0800,
        stop_loss=1.0750,
        trade_id='TEST001',
    )
    
    print(f"\nTest Trade:")
    print(f"  Entry: {setup.entry_price}")
    print(f"  SL: {setup.stop_loss}")
    print(f"  Risk: {setup.risk}")
    print(f"  TP1: {setup.tp1} ({TP1_R}R)")
    print(f"  TP2: {setup.tp2} ({TP2_R}R)")
    print(f"  TP3: {setup.tp3} ({TP3_R}R)")
    print(f"  TP4: {setup.tp4} ({TP4_R}R)")
    print(f"  TP5: {setup.tp5} ({TP5_R}R)")
    
    # Would need H1 data to actually simulate
    print("\n(Actual simulation requires H1 data in data/ohlcv/)")
