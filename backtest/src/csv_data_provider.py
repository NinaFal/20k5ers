"""
CSV Data Provider - Simulates MT5 API using historical CSV data

This class provides the EXACT same interface as MT5Wrapper, but reads from CSV files.
It allows main_backtest_bot.py to run with minimal code changes.

Usage:
    provider = CSVDataProvider(data_dir="data/ohlcv", timeframe="M15")
    provider.set_current_time(datetime(2023, 6, 15, 14, 30))
    
    # These methods work exactly like MT5Wrapper
    tick = provider.get_tick("EURUSD")
    candles = provider.get_ohlcv("EURUSD", "D1", 100)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)


@dataclass
class SimulatedTick:
    """Simulated tick data matching MT5 tick structure."""
    bid: float
    ask: float
    last: float
    time: datetime
    spread: float = 0.0


@dataclass
class SimulatedPosition:
    """Simulated position matching MT5 position structure."""
    ticket: int
    symbol: str
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    swap: float
    commission: float
    magic: int
    comment: str
    time: datetime
    type: int  # 0=buy, 1=sell


@dataclass
class SimulatedOrder:
    """Simulated pending order matching MT5 order structure."""
    ticket: int
    symbol: str
    volume: float
    price_open: float
    sl: float
    tp: float
    magic: int
    comment: str
    time: datetime
    type: int  # 2=buy_limit, 3=sell_limit, etc.


class CSVDataProvider:
    """
    CSV-based data provider that mimics MT5Wrapper interface.
    
    Key differences from live MT5:
    - Time is simulated via set_current_time()
    - Prices come from historical CSV data
    - Orders/positions are simulated in memory
    """
    
    def __init__(
        self,
        data_dir: str = "data/ohlcv",
        intraday_timeframe: str = "M15",  # M15 or H1
        spread_pips: float = 1.0,  # Default spread in pips
    ):
        """
        Initialize CSV data provider.
        
        Args:
            data_dir: Directory containing OHLCV CSV files
            intraday_timeframe: Timeframe for execution (M15 or H1)
            spread_pips: Default spread to simulate
        """
        self.data_dir = Path(data_dir)
        self.intraday_tf = intraday_timeframe
        self.spread_pips = spread_pips
        
        # Caches
        self._data_cache: Dict[str, Dict[str, pd.DataFrame]] = {}  # {symbol: {tf: df}}
        self._intraday_index: Dict[str, Dict[datetime, Dict]] = {}  # {symbol: {time: bar}}
        
        # Simulation state
        self._current_time: datetime = datetime(2023, 1, 1, tzinfo=timezone.utc)
        self._positions: Dict[int, SimulatedPosition] = {}
        self._pending_orders: Dict[int, SimulatedOrder] = {}
        self._next_ticket: int = 1000000
        
        # Account state
        self._balance: float = 20000.0
        self._equity: float = 20000.0
        
        # Load available symbols
        self._symbols = self._discover_symbols()
        log.info(f"CSVDataProvider initialized with {len(self._symbols)} symbols, timeframe: {intraday_tf}")
    
    def _discover_symbols(self) -> List[str]:
        """Discover available symbols from CSV files."""
        symbols = set()
        
        # Look for M15 or H1 files
        patterns = [f"*_{self.intraday_tf}.csv", f"*_{self.intraday_tf}_*.csv"]
        for pattern in patterns:
            for f in self.data_dir.glob(pattern):
                # Extract symbol name
                symbol = f.stem
                symbol = symbol.replace(f"_{self.intraday_tf}", "")
                symbol = symbol.replace("_2003_2025", "").replace("_2020_2025", "")
                symbols.add(symbol)
        
        return sorted(symbols)
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        return self._symbols
    
    def set_current_time(self, time: datetime):
        """Set the simulated current time."""
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        self._current_time = time
    
    def get_current_time(self) -> datetime:
        """Get current simulated time."""
        return self._current_time
    
    def set_balance(self, balance: float):
        """Set account balance."""
        self._balance = balance
        self._equity = balance + sum(p.profit for p in self._positions.values())
    
    # ═══════════════════════════════════════════════════════════════════════
    # MT5-COMPATIBLE INTERFACE
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account info (MT5-compatible)."""
        floating_pnl = sum(p.profit for p in self._positions.values())
        return {
            "balance": self._balance,
            "equity": self._balance + floating_pnl,
            "margin": 0.0,
            "margin_free": self._balance + floating_pnl,
            "margin_level": 100.0,
            "profit": floating_pnl,
        }
    
    def get_tick(self, symbol: str) -> Optional[SimulatedTick]:
        """
        Get current tick for symbol (MT5-compatible).
        
        Returns simulated tick based on current intraday bar.
        """
        bar = self._get_current_bar(symbol)
        if bar is None:
            return None
        
        # Use close price as current price
        price = bar['close']
        
        # Calculate spread
        pip_size = self._get_pip_size(symbol)
        spread = self.spread_pips * pip_size
        
        return SimulatedTick(
            bid=price,
            ask=price + spread,
            last=price,
            time=self._current_time,
            spread=spread,
        )
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
        end_time: datetime = None,
    ) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data (MT5-compatible).
        
        Args:
            symbol: Symbol name
            timeframe: Timeframe (MN, W1, D1, H4, H1, M15)
            count: Number of bars to return
            end_time: End time (defaults to current simulated time)
        
        Returns:
            DataFrame with open, high, low, close, volume columns
        """
        if end_time is None:
            end_time = self._current_time
        
        # Load data for timeframe
        df = self._load_timeframe_data(symbol, timeframe)
        if df is None or df.empty:
            return None
        
        # Filter to BEFORE end_time (no look-ahead bias!)
        df = df[df.index < end_time]
        
        if df.empty:
            return None
        
        # Return last N bars
        return df.tail(count).copy()
    
    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """Get symbol info (MT5-compatible)."""
        pip_size = self._get_pip_size(symbol)
        return {
            "pip_size": pip_size,
            "point": pip_size / 10,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "trade_contract_size": 100000,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
        }
    
    def get_my_positions(self) -> List[SimulatedPosition]:
        """Get open positions (MT5-compatible)."""
        return list(self._positions.values())
    
    def get_pending_orders(self) -> List[SimulatedOrder]:
        """Get pending orders (MT5-compatible)."""
        return list(self._pending_orders.values())
    
    def place_market_order(
        self,
        symbol: str,
        order_type: str,  # "buy" or "sell"
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        magic: int = 0,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Place market order (MT5-compatible)."""
        tick = self.get_tick(symbol)
        if tick is None:
            return {"success": False, "error": "No tick data"}
        
        # Fill price
        fill_price = tick.ask if order_type == "buy" else tick.bid
        
        # Create position
        ticket = self._next_ticket
        self._next_ticket += 1
        
        pos = SimulatedPosition(
            ticket=ticket,
            symbol=symbol,
            volume=volume,
            price_open=fill_price,
            sl=sl,
            tp=tp,
            profit=0.0,
            swap=0.0,
            commission=volume * 4.0,  # $4 per lot
            magic=magic,
            comment=comment,
            time=self._current_time,
            type=0 if order_type == "buy" else 1,
        )
        
        self._positions[ticket] = pos
        
        return {
            "success": True,
            "ticket": ticket,
            "price": fill_price,
            "volume": volume,
        }
    
    def place_limit_order(
        self,
        symbol: str,
        order_type: str,  # "buy_limit" or "sell_limit"
        volume: float,
        price: float,
        sl: float = 0.0,
        tp: float = 0.0,
        magic: int = 0,
        comment: str = "",
    ) -> Dict[str, Any]:
        """Place limit order (MT5-compatible)."""
        ticket = self._next_ticket
        self._next_ticket += 1
        
        order = SimulatedOrder(
            ticket=ticket,
            symbol=symbol,
            volume=volume,
            price_open=price,
            sl=sl,
            tp=tp,
            magic=magic,
            comment=comment,
            time=self._current_time,
            type=2 if order_type == "buy_limit" else 3,
        )
        
        self._pending_orders[ticket] = order
        
        return {
            "success": True,
            "ticket": ticket,
            "price": price,
            "volume": volume,
        }
    
    def close_position(self, ticket: int, volume: float = None) -> Dict[str, Any]:
        """Close position (MT5-compatible)."""
        if ticket not in self._positions:
            return {"success": False, "error": "Position not found"}
        
        pos = self._positions[ticket]
        tick = self.get_tick(pos.symbol)
        
        if tick is None:
            return {"success": False, "error": "No tick data"}
        
        # Close price
        close_price = tick.bid if pos.type == 0 else tick.ask  # Opposite of open
        
        # Calculate P&L
        if pos.type == 0:  # Buy
            pnl = (close_price - pos.price_open) * pos.volume * 100000
        else:  # Sell
            pnl = (pos.price_open - close_price) * pos.volume * 100000
        
        close_volume = volume if volume else pos.volume
        
        if close_volume >= pos.volume:
            # Full close
            del self._positions[ticket]
            self._balance += pnl - pos.commission
        else:
            # Partial close
            partial_pnl = pnl * (close_volume / pos.volume)
            pos.volume -= close_volume
            self._balance += partial_pnl
        
        return {
            "success": True,
            "ticket": ticket,
            "price": close_price,
            "profit": pnl,
        }
    
    def cancel_pending_order(self, ticket: int) -> Dict[str, Any]:
        """Cancel pending order (MT5-compatible)."""
        if ticket in self._pending_orders:
            del self._pending_orders[ticket]
            return {"success": True, "ticket": ticket}
        return {"success": False, "error": "Order not found"}
    
    def modify_position(
        self,
        ticket: int,
        sl: float = None,
        tp: float = None,
    ) -> Dict[str, Any]:
        """Modify position SL/TP (MT5-compatible)."""
        if ticket not in self._positions:
            return {"success": False, "error": "Position not found"}
        
        pos = self._positions[ticket]
        if sl is not None:
            pos.sl = sl
        if tp is not None:
            pos.tp = tp
        
        return {"success": True, "ticket": ticket}
    
    # ═══════════════════════════════════════════════════════════════════════
    # DATA LOADING
    # ═══════════════════════════════════════════════════════════════════════
    
    def _load_timeframe_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load data for specific timeframe."""
        # Check cache
        if symbol in self._data_cache and timeframe in self._data_cache[symbol]:
            return self._data_cache[symbol][timeframe]
        
        # Find file
        file_patterns = [
            f"{symbol}_{timeframe}.csv",
            f"{symbol}_{timeframe}_2003_2025.csv",
            f"{symbol}_{timeframe}_2020_2025.csv",
        ]
        
        file_path = None
        for pattern in file_patterns:
            path = self.data_dir / pattern
            if path.exists():
                file_path = path
                break
        
        if file_path is None:
            return None
        
        # Load CSV
        try:
            df = pd.read_csv(file_path, parse_dates=['time'])
            
            # Normalize column names
            df.columns = [c.lower() for c in df.columns]
            
            # Set time as index
            if 'time' in df.columns:
                df.set_index('time', inplace=True)
            
            # Ensure timezone
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize('UTC')
            
            # Cache
            if symbol not in self._data_cache:
                self._data_cache[symbol] = {}
            self._data_cache[symbol][timeframe] = df
            
            return df
            
        except Exception as e:
            log.error(f"Error loading {file_path}: {e}")
            return None
    
    def _get_current_bar(self, symbol: str) -> Optional[Dict]:
        """Get current intraday bar."""
        df = self._load_timeframe_data(symbol, self.intraday_tf)
        if df is None or df.empty:
            return None
        
        # Find bar at or before current time
        mask = df.index <= self._current_time
        if not mask.any():
            return None
        
        bar = df.loc[mask].iloc[-1]
        return {
            'time': bar.name,
            'open': bar['open'],
            'high': bar['high'],
            'low': bar['low'],
            'close': bar['close'],
        }
    
    def _get_pip_size(self, symbol: str) -> float:
        """Get pip size for symbol."""
        symbol_upper = symbol.upper()
        
        if "JPY" in symbol_upper:
            return 0.01
        elif "XAU" in symbol_upper or "GOLD" in symbol_upper:
            return 0.01
        elif "XAG" in symbol_upper or "SILVER" in symbol_upper:
            return 0.001
        elif "BTC" in symbol_upper:
            return 1.0
        elif "ETH" in symbol_upper:
            return 0.01
        elif any(x in symbol_upper for x in ["NAS", "SPX", "NDX", "US30", "UK100"]):
            return 1.0
        else:
            return 0.0001  # Standard forex
    
    # ═══════════════════════════════════════════════════════════════════════
    # SIMULATION HELPERS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_intraday_timeline(self, start: datetime, end: datetime) -> List[datetime]:
        """Get all intraday timestamps in range."""
        all_times = set()
        
        for symbol in self._symbols[:5]:  # Sample from first 5 symbols
            df = self._load_timeframe_data(symbol, self.intraday_tf)
            if df is not None:
                mask = (df.index >= start) & (df.index <= end)
                all_times.update(df.index[mask].tolist())
        
        return sorted(all_times)
    
    def update_position_profits(self):
        """Update floating P&L for all positions."""
        for pos in self._positions.values():
            tick = self.get_tick(pos.symbol)
            if tick is None:
                continue
            
            if pos.type == 0:  # Buy
                pos.profit = (tick.bid - pos.price_open) * pos.volume * 100000
            else:  # Sell
                pos.profit = (pos.price_open - tick.ask) * pos.volume * 100000
    
    def check_sl_tp_hits(self, symbol: str) -> List[Dict]:
        """Check if current bar hits any SL/TP for symbol's positions."""
        hits = []
        bar = self._get_current_bar(symbol)
        if bar is None:
            return hits
        
        high = bar['high']
        low = bar['low']
        
        for ticket, pos in list(self._positions.items()):
            if pos.symbol != symbol:
                continue
            
            if pos.type == 0:  # Buy position
                # SL hit (price goes down to SL)
                if pos.sl > 0 and low <= pos.sl:
                    hits.append({"ticket": ticket, "type": "sl", "price": pos.sl})
                # TP hit (price goes up to TP)
                elif pos.tp > 0 and high >= pos.tp:
                    hits.append({"ticket": ticket, "type": "tp", "price": pos.tp})
            else:  # Sell position
                # SL hit (price goes up to SL)
                if pos.sl > 0 and high >= pos.sl:
                    hits.append({"ticket": ticket, "type": "sl", "price": pos.sl})
                # TP hit (price goes down to TP)
                elif pos.tp > 0 and low <= pos.tp:
                    hits.append({"ticket": ticket, "type": "tp", "price": pos.tp})
        
        return hits
    
    def check_limit_order_fills(self, symbol: str) -> List[int]:
        """Check if current bar fills any pending limit orders."""
        fills = []
        bar = self._get_current_bar(symbol)
        if bar is None:
            return fills
        
        high = bar['high']
        low = bar['low']
        
        for ticket, order in list(self._pending_orders.items()):
            if order.symbol != symbol:
                continue
            
            # Buy limit fills when price drops to order price
            if order.type == 2 and low <= order.price_open:
                fills.append(ticket)
            # Sell limit fills when price rises to order price
            elif order.type == 3 and high >= order.price_open:
                fills.append(ticket)
        
        return fills
    
    def fill_pending_order(self, ticket: int) -> Dict[str, Any]:
        """Convert pending order to position."""
        if ticket not in self._pending_orders:
            return {"success": False, "error": "Order not found"}
        
        order = self._pending_orders[ticket]
        
        # Create position
        pos = SimulatedPosition(
            ticket=ticket,
            symbol=order.symbol,
            volume=order.volume,
            price_open=order.price_open,
            sl=order.sl,
            tp=order.tp,
            profit=0.0,
            swap=0.0,
            commission=order.volume * 4.0,
            magic=order.magic,
            comment=order.comment,
            time=self._current_time,
            type=0 if order.type == 2 else 1,  # buy_limit -> buy, sell_limit -> sell
        )
        
        self._positions[ticket] = pos
        del self._pending_orders[ticket]
        
        return {
            "success": True,
            "ticket": ticket,
            "price": order.price_open,
            "volume": order.volume,
        }
