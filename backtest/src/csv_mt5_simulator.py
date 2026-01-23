"""
CSV MT5 Simulator - Drop-in replacement for MT5Client using CSV data

This class provides the EXACT same interface as tradr/mt5/client.py MT5Client,
but reads from CSV files instead of connecting to MT5.

Usage in main_live_bot_backtest.py:
    # Replace:
    #   from tradr.mt5.client import MT5Client
    # With:
    #   from backtest.csv_mt5_simulator import CSVMT5Simulator as MT5Client

The simulator steps through M15 bars to simulate real-time price movement.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES - EXACT SAME AS tradr/mt5/client.py
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TickData:
    """Represents a price tick."""
    symbol: str
    bid: float
    ask: float
    time: datetime
    spread: float


@dataclass
class Position:
    """Represents an open position."""
    ticket: int
    symbol: str
    type: int  # 0 = buy, 1 = sell
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    time: datetime
    magic: int
    comment: str


@dataclass
class PendingOrder:
    """Represents a pending order."""
    ticket: int
    symbol: str
    type: int  # 2=buy_limit, 3=sell_limit, 4=buy_stop, 5=sell_stop
    volume: float
    price: float
    sl: float
    tp: float
    time_setup: datetime
    expiration: datetime
    magic: int
    comment: str


@dataclass
class TradeResult:
    """Result of a trade operation."""
    success: bool
    order_id: int = 0
    deal_id: int = 0
    price: float = 0.0
    volume: float = 0.0
    error: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# SYMBOL INFO / SPECS
# ═══════════════════════════════════════════════════════════════════════════

SYMBOL_SPECS = {
    # Forex majors
    "EURUSD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPUSD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "USDJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "USDCHF": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "USDCAD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "AUDUSD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "NZDUSD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    # Forex crosses
    "EURJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "AUDJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "NZDJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "CADJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "CHFJPY": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "EURGBP": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "EURAUD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "EURCAD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "EURNZD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "EURCHF": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPAUD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPCAD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPNZD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "GBPCHF": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "AUDCAD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "AUDNZD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "AUDCHF": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "NZDCAD": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "NZDCHF": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "CADCHF": {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    # Metals
    "XAUUSD": {"point": 0.01, "digits": 2, "pip_size": 0.1, "contract_size": 100, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "XAGUSD": {"point": 0.001, "digits": 3, "pip_size": 0.01, "contract_size": 5000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    # Indices (5ers format)
    "US500": {"point": 0.01, "digits": 2, "pip_size": 1.0, "contract_size": 1, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "NAS100": {"point": 0.01, "digits": 2, "pip_size": 1.0, "contract_size": 1, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "US30": {"point": 0.01, "digits": 2, "pip_size": 1.0, "contract_size": 1, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "UK100": {"point": 0.01, "digits": 2, "pip_size": 1.0, "contract_size": 1, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    # Crypto
    "BTCUSD": {"point": 0.01, "digits": 2, "pip_size": 1.0, "contract_size": 1, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
    "ETHUSD": {"point": 0.01, "digits": 2, "pip_size": 0.1, "contract_size": 1, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01},
}

DEFAULT_SPEC = {"point": 0.00001, "digits": 5, "pip_size": 0.0001, "contract_size": 100000, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}


def _normalize_symbol(symbol: str) -> str:
    """Normalize symbol (remove underscores, uppercase)."""
    return symbol.replace("_", "").replace(".", "").upper()


def _get_spec(symbol: str) -> dict:
    """Get symbol specification."""
    norm = _normalize_symbol(symbol)
    return SYMBOL_SPECS.get(norm, DEFAULT_SPEC)


# ═══════════════════════════════════════════════════════════════════════════
# CSV MT5 SIMULATOR
# ═══════════════════════════════════════════════════════════════════════════

class CSVMT5Simulator:
    """
    CSV-based MT5 simulator - EXACT same interface as MT5Client.
    
    This class:
    1. Loads historical data from CSV files
    2. Maintains simulated current time
    3. Provides all MT5Client methods using CSV data
    4. Manages simulated positions/orders in memory
    """
    
    MAGIC_NUMBER = 123456
    COMMENT = "TradrBot"
    
    def __init__(
        self,
        server: str = "",
        login: int = 0,
        password: str = "",
        data_dir: str = "data/ohlcv",
        initial_balance: float = 20000.0,
        spread_pips: float = 1.0,
    ):
        """
        Initialize the CSV MT5 simulator.
        
        Args:
            server, login, password: Ignored (for API compatibility)
            data_dir: Directory containing CSV data files
            initial_balance: Starting account balance
            spread_pips: Default spread in pips
        """
        self.server = server
        self.login = login
        self.password = password
        self.data_dir = Path(data_dir)
        self.spread_pips = spread_pips
        
        self.connected = False
        
        # Account state
        self._balance = initial_balance
        self._initial_balance = initial_balance
        
        # Simulated time (call set_current_time to advance)
        self._current_time: datetime = datetime(2023, 1, 1, tzinfo=timezone.utc)
        
        # Data caches
        self._data_cache: Dict[str, Dict[str, pd.DataFrame]] = {}  # {symbol: {timeframe: df}}
        self._m15_indexed: Dict[str, Dict[datetime, dict]] = {}  # {symbol: {time: bar}}
        
        # Simulated positions and orders
        self._positions: Dict[int, Position] = {}
        self._pending_orders: Dict[int, PendingOrder] = {}
        self._next_ticket: int = 1000000
        
        # Available symbols (discovered from M15 files)
        self._available_symbols: List[str] = []
        
        # Closed trades log
        self._closed_trades: List[dict] = []
    
    # ═══════════════════════════════════════════════════════════════════════
    # SIMULATION CONTROL (not in MT5Client, but needed for backtest)
    # ═══════════════════════════════════════════════════════════════════════
    
    def set_current_time(self, time: datetime):
        """Set simulated current time."""
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        self._current_time = time
    
    def get_current_time(self) -> datetime:
        """Get current simulated time."""
        return self._current_time
    
    def set_balance(self, balance: float):
        """Set account balance."""
        self._balance = balance
    
    def get_closed_trades(self) -> List[dict]:
        """Get list of closed trades (for results)."""
        return self._closed_trades
    
    def load_m15_data(self, symbols: List[str]):
        """Pre-load M15 data for fast access during simulation (OPTIMIZED)."""
        log.info(f"Loading M15 data for {len(symbols)} symbols...")
        for symbol in symbols:
            df = self._load_data(symbol, "M15")
            if df is not None and not df.empty:
                self._available_symbols.append(symbol)
                
                # OPTIMIZED: Vectorized indexing instead of iterrows
                # Convert time column to proper datetime with UTC
                if df['time'].dt.tz is None:
                    df['time'] = df['time'].dt.tz_localize('UTC')
                
                # Create dict with timestamp as key using vectorized operations
                df_indexed = df.set_index('time')[['open', 'high', 'low', 'close', 'volume']].to_dict('index')
                self._m15_indexed[symbol] = df_indexed
                
        log.info(f"Loaded M15 data for {len(self._available_symbols)} symbols")
    
    def get_m15_bar(self, symbol: str, time: datetime) -> Optional[dict]:
        """Get M15 bar at specific time."""
        if symbol not in self._m15_indexed:
            return None
        # Convert to pandas Timestamp for lookup (matches the df.set_index format)
        ts = pd.Timestamp(time)
        if ts.tzinfo is None:
            ts = ts.tz_localize('UTC')
        return self._m15_indexed[symbol].get(ts)
    
    def get_m15_timeline(self, start: datetime, end: datetime) -> List[datetime]:
        """Get all M15 timestamps in range."""
        # Convert to pandas Timestamp
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize('UTC')
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize('UTC')
        
        all_times = set()
        for symbol in list(self._m15_indexed.keys())[:5]:  # Sample from first 5
            for t in self._m15_indexed[symbol].keys():
                if start_ts <= t <= end_ts:
                    all_times.add(t)
        return sorted(all_times)
    
    # ═══════════════════════════════════════════════════════════════════════
    # MT5Client INTERFACE - CONNECTION
    # ═══════════════════════════════════════════════════════════════════════
    
    def connect(self) -> bool:
        """Simulate connection (always succeeds)."""
        self.connected = True
        log.info("CSVMT5Simulator: Connected (simulated)")
        return True
    
    def connect_with_retry(self, max_attempts: int = None) -> bool:
        """Connect with retry (simulated)."""
        return self.connect()
    
    def disconnect(self):
        """Simulate disconnection."""
        self.connected = False
        log.info("CSVMT5Simulator: Disconnected (simulated)")
    
    def ensure_connected(self) -> bool:
        """Ensure connected."""
        if not self.connected:
            return self.connect()
        return True
    
    # ═══════════════════════════════════════════════════════════════════════
    # MT5Client INTERFACE - ACCOUNT INFO
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_account_info(self) -> Dict:
        """Get account info (simulated)."""
        floating_pnl = self._calculate_floating_pnl()
        equity = self._balance + floating_pnl
        
        return {
            "balance": self._balance,
            "equity": equity,
            "margin": 0.0,
            "margin_free": equity,
            "margin_level": 100.0 if equity > 0 else 0.0,
            "profit": floating_pnl,
            "currency": "USD",
            "leverage": 100,
            "server": self.server,
            "login": self.login,
        }
    
    def get_account_equity(self) -> float:
        """Get current account equity."""
        floating_pnl = self._calculate_floating_pnl()
        return self._balance + floating_pnl
    
    def get_account_balance(self) -> float:
        """Get current account balance."""
        return self._balance
    
    def _calculate_floating_pnl(self) -> float:
        """Calculate floating P&L for all positions."""
        total_pnl = 0.0
        for pos in self._positions.values():
            pnl = self._calculate_position_pnl(pos)
            total_pnl += pnl
        return total_pnl
    
    def _calculate_position_pnl(self, pos: Position) -> float:
        """Calculate P&L for a single position.
        
        CRITICAL: Use CONSISTENT source for pip_size and pip_value!
        Both must come from get_fiveers_contract_specs() to match.
        """
        bar = self.get_m15_bar(pos.symbol, self._current_time)
        if bar is None:
            return pos.profit  # Return last known profit
        
        current_price = bar['close']
        
        # CRITICAL: Use SAME source for pip_size and pip_value
        from tradr.brokers.fiveers_specs import get_fiveers_contract_specs
        fiveers_specs = get_fiveers_contract_specs(pos.symbol)
        pip_size = fiveers_specs.get('pip_size', 0.0001)
        pip_value_per_lot = fiveers_specs.get('pip_value_per_lot', 10.0)
        
        if pos.type == 0:  # Buy
            price_diff = current_price - pos.price_open
        else:  # Sell
            price_diff = pos.price_open - current_price
        
        pips = price_diff / pip_size
        
        # P&L = pips × pip_value × volume
        pnl = pips * pip_value_per_lot * pos.volume
        
        return pnl
    
    def _get_pip_value(self, symbol: str) -> float:
        """
        Get pip value per lot using 5ers contract specs.
        
        CRITICAL: 5ers uses MINI contracts for indices ($1/point, not $10-20/point).
        """
        from tradr.brokers.fiveers_specs import get_fiveers_contract_specs
        
        specs = get_fiveers_contract_specs(symbol)
        return specs.get("pip_value_per_lot", 10.0)
    
    # ═══════════════════════════════════════════════════════════════════════
    # MT5Client INTERFACE - MARKET DATA
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_tick(self, symbol: str) -> Optional[TickData]:
        """Get current tick (from M15 bar close)."""
        # Normalize symbol for lookup
        norm = _normalize_symbol(symbol)
        
        # Try to find the symbol in indexed data
        lookup_symbol = None
        for s in self._m15_indexed.keys():
            if _normalize_symbol(s) == norm:
                lookup_symbol = s
                break
        
        if lookup_symbol is None:
            return None
        
        bar = self.get_m15_bar(lookup_symbol, self._current_time)
        if bar is None:
            # Try to find the most recent bar before current time
            if lookup_symbol in self._m15_indexed:
                times = [t for t in self._m15_indexed[lookup_symbol].keys() if t <= self._current_time]
                if times:
                    latest = max(times)
                    bar = self._m15_indexed[lookup_symbol][latest]
        
        if bar is None:
            return None
        
        price = bar['close']
        spec = _get_spec(symbol)
        pip_size = spec.get('pip_size', 0.0001)
        spread = self.spread_pips * pip_size
        
        return TickData(
            symbol=symbol,
            bid=price,
            ask=price + spread,
            time=self._current_time,
            spread=spread,
        )
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
        end_time: datetime = None,
    ) -> Optional[List[Dict]]:
        """Get OHLCV data (bars BEFORE current time). Returns list of dicts like MT5Client."""
        if end_time is None:
            end_time = self._current_time
        
        # Map MT5 timeframe names
        tf_map = {"MN1": "MN", "MN": "MN", "W1": "W1", "D1": "D1", "H4": "H4", "H1": "H1", "M15": "M15", "M1": "M15"}
        tf = tf_map.get(timeframe, timeframe)
        
        df = self._load_data(symbol, tf)
        if df is None or df.empty:
            return None
        
        # Ensure time column is timezone-aware UTC
        if df['time'].dt.tz is None:
            df = df.copy()
            df['time'] = df['time'].dt.tz_localize('UTC')
        
        # Convert end_time to pandas Timestamp with UTC
        end_ts = pd.Timestamp(end_time)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize('UTC')
        
        # Filter to BEFORE end_time (no look-ahead!)
        df = df[df['time'] < end_ts]
        
        if df.empty:
            return None
        
        # Return last N bars as list of dicts (MT5Client format)
        result = df.tail(count).copy()
        return result.to_dict('records')
    
    def get_ohlcv_df(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
        end_time: datetime = None,
    ) -> Optional[pd.DataFrame]:
        """Get OHLCV data as DataFrame (for internal use)."""
        if end_time is None:
            end_time = self._current_time
        
        # Map MT5 timeframe names
        tf_map = {"MN1": "MN", "MN": "MN", "W1": "W1", "D1": "D1", "H4": "H4", "H1": "H1", "M15": "M15", "M1": "M15"}
        tf = tf_map.get(timeframe, timeframe)
        
        df = self._load_data(symbol, tf)
        if df is None or df.empty:
            return None
        
        # Ensure time column is timezone-aware UTC
        if df['time'].dt.tz is None:
            df = df.copy()
            df['time'] = df['time'].dt.tz_localize('UTC')
        
        # Convert end_time to pandas Timestamp with UTC
        end_ts = pd.Timestamp(end_time)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize('UTC')
        
        # Filter to BEFORE end_time (no look-ahead!)
        df = df[df['time'] < end_ts]
        
        if df.empty:
            return None
        
        return df.tail(count).copy()
    
    def _load_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load data from CSV file."""
        # Check cache
        if symbol in self._data_cache and timeframe in self._data_cache[symbol]:
            return self._data_cache[symbol][timeframe]
        
        # Symbol formats: OANDA (AUD_USD) vs simple (AUDUSD)
        symbol_no_underscore = symbol.replace("_", "")
        
        # Try various file patterns
        patterns = [
            f"{symbol}_{timeframe}.csv",
            f"{symbol}_{timeframe}_2020_2025.csv",
            f"{symbol}_{timeframe}_2003_2025.csv",
            f"{symbol}_{timeframe}_2014_2025.csv",
            f"{symbol_no_underscore}_{timeframe}.csv",
            f"{symbol_no_underscore}_{timeframe}_2020_2025.csv",
            f"{symbol_no_underscore}_{timeframe}_2003_2025.csv",
            f"{symbol_no_underscore}_{timeframe}_2014_2025.csv",
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
            if symbol not in self._data_cache:
                self._data_cache[symbol] = {}
            self._data_cache[symbol][timeframe] = df
            
            return df
        except Exception as e:
            log.error(f"Error loading {filepath}: {e}")
            return None
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols."""
        if self._available_symbols:
            return self._available_symbols
        
        # Discover from M15 files
        symbols = set()
        for f in self.data_dir.glob("*_M15*.csv"):
            name = f.stem
            name = name.replace("_M15", "").replace("_2020_2025", "").replace("_2003_2025", "")
            symbols.add(name)
        
        self._available_symbols = sorted(symbols)
        return self._available_symbols
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get symbol info."""
        spec = _get_spec(symbol)
        return {
            "name": symbol,
            "point": spec["point"],
            "digits": spec["digits"],
            "trade_contract_size": spec["contract_size"],
            "volume_min": spec["volume_min"],
            "volume_max": spec["volume_max"],
            "volume_step": spec["volume_step"],
            "pip_size": spec["pip_size"],
        }
    
    def find_symbol_match(self, symbol: str) -> Optional[str]:
        """Find matching symbol in available symbols."""
        norm = _normalize_symbol(symbol)
        for s in self._available_symbols:
            if _normalize_symbol(s) == norm:
                return s
        return None
    
    # ═══════════════════════════════════════════════════════════════════════
    # MT5Client INTERFACE - POSITIONS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_positions(self, symbol: str = None) -> List[Position]:
        """Get all positions or for specific symbol."""
        positions = list(self._positions.values())
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        
        # Update profit for each position
        for pos in positions:
            pos.profit = self._calculate_position_pnl(pos)
        
        return positions
    
    def get_my_positions(self) -> List[Position]:
        """Get positions for this bot (by magic number)."""
        return [p for p in self._positions.values() if p.magic == self.MAGIC_NUMBER]
    
    def close_position(self, ticket: int, volume: float = None, close_price: float = None) -> TradeResult:
        """Close a position (partial or full).
        
        Args:
            ticket: Position ticket to close
            volume: Volume to close (None = full close)
            close_price: Exact close price (e.g. SL/TP hit price). If None, uses current bar close.
        """
        if ticket not in self._positions:
            return TradeResult(success=False, error="Position not found")
        
        pos = self._positions[ticket]
        
        # Use provided close_price (for SL/TP hits) or get current bar close
        if close_price is None:
            bar = self.get_m15_bar(pos.symbol, self._current_time)
            if bar is None:
                # Try to get tick instead
                tick = self.get_tick(pos.symbol)
                if tick:
                    close_price = tick.bid if pos.type == 0 else tick.ask
                else:
                    return TradeResult(success=False, error="No price data")
            else:
                close_price = bar['close']
        
        close_volume = volume if volume else pos.volume
        
        # Calculate P&L using the ACTUAL close price (not current bar price)
        pnl = self._calculate_pnl_at_price(pos, close_price, close_volume)
        
        if close_volume >= pos.volume:
            # Full close
            del self._positions[ticket]
            self._balance += pnl
            
            # Log closed trade
            self._closed_trades.append({
                'ticket': ticket,
                'symbol': pos.symbol,
                'type': 'buy' if pos.type == 0 else 'sell',
                'volume': pos.volume,
                'open_price': pos.price_open,
                'close_price': close_price,
                'open_time': pos.time,
                'close_time': self._current_time,
                'pnl': pnl,
                'sl': pos.sl,
                'tp': pos.tp,
            })
        else:
            # Partial close
            pos.volume -= close_volume
            self._balance += pnl
        
        return TradeResult(
            success=True,
            order_id=ticket,
            deal_id=ticket,
            price=close_price,
            volume=close_volume,
        )
    
    def _calculate_pnl_at_price(self, pos: Position, close_price: float, volume: float = None) -> float:
        """Calculate P&L for closing a position at a specific price.
        
        This is used for SL/TP hits where we know the exact exit price.
        """
        from tradr.brokers.fiveers_specs import get_fiveers_contract_specs
        fiveers_specs = get_fiveers_contract_specs(pos.symbol)
        pip_size = fiveers_specs.get('pip_size', 0.0001)
        pip_value_per_lot = fiveers_specs.get('pip_value_per_lot', 10.0)
        
        if pos.type == 0:  # Buy
            price_diff = close_price - pos.price_open
        else:  # Sell
            price_diff = pos.price_open - close_price
        
        pips = price_diff / pip_size
        vol = volume if volume else pos.volume
        
        # P&L = pips × pip_value × volume
        pnl = pips * pip_value_per_lot * vol
        
        return pnl
    
    def modify_sl_tp(
        self,
        ticket: int,
        sl: float = None,
        tp: float = None,
    ) -> TradeResult:
        """Modify SL/TP for a position."""
        if ticket not in self._positions:
            return TradeResult(success=False, error="Position not found")
        
        pos = self._positions[ticket]
        if sl is not None:
            pos.sl = sl
        if tp is not None:
            pos.tp = tp
        
        return TradeResult(success=True, order_id=ticket)
    
    def partial_close(self, ticket: int, volume: float, close_price: float = None) -> TradeResult:
        """Partially close a position (alias for close_position with volume)."""
        return self.close_position(ticket, volume, close_price)
    
    # ═══════════════════════════════════════════════════════════════════════
    # MT5Client INTERFACE - ORDERS
    # ═══════════════════════════════════════════════════════════════════════
    
    def place_market_order(
        self,
        symbol: str,
        direction: str = None,  # "bullish" or "bearish" (for compatibility)
        order_type: str = None,  # "buy" or "sell"
        volume: float = 0.01,
        sl: float = 0.0,
        tp: float = 0.0,
        magic: int = None,
        comment: str = None,
    ) -> TradeResult:
        """Place a market order (compatible with MT5Client interface)."""
        # Determine order type from direction if not specified
        if order_type is None and direction is not None:
            order_type = "buy" if direction.lower() == "bullish" else "sell"
        if order_type is None:
            return TradeResult(success=False, error="No order_type or direction specified")
        
        tick = self.get_tick(symbol)
        if tick is None:
            return TradeResult(success=False, error="No tick data")
        
        fill_price = tick.ask if order_type == "buy" else tick.bid
        pos_type = 0 if order_type == "buy" else 1
        
        ticket = self._next_ticket
        self._next_ticket += 1
        
        pos = Position(
            ticket=ticket,
            symbol=symbol,
            type=pos_type,
            volume=volume,
            price_open=fill_price,
            sl=sl,
            tp=tp,
            profit=0.0,
            time=self._current_time,
            magic=magic if magic else self.MAGIC_NUMBER,
            comment=comment if comment else self.COMMENT,
        )
        
        self._positions[ticket] = pos
        
        return TradeResult(
            success=True,
            order_id=ticket,
            deal_id=ticket,
            price=fill_price,
            volume=volume,
        )
    
    def place_pending_order(
        self,
        symbol: str,
        direction: str = None,  # "bullish" or "bearish" (for compatibility)
        order_type: str = None,  # "buy_limit", "sell_limit", "buy_stop", "sell_stop"
        volume: float = 0.01,
        entry_price: float = None,  # Alias for price
        price: float = None,
        sl: float = 0.0,
        tp: float = 0.0,
        expiration: datetime = None,
        expiration_hours: int = None,  # Alternative to expiration datetime
        magic: int = None,
        comment: str = None,
    ) -> TradeResult:
        """Place a pending order (compatible with MT5Client interface)."""
        # Handle entry_price alias
        if entry_price is not None and price is None:
            price = entry_price
        if price is None:
            return TradeResult(success=False, error="No price specified")
        
        # Determine order type from direction if not specified
        if order_type is None and direction is not None:
            # Get current price to determine limit vs stop
            tick = self.get_tick(symbol)
            current_price = tick.bid if tick else price
            
            if direction.lower() == "bullish":
                # If entry below current = buy limit, above = buy stop
                order_type = "buy_limit" if price < current_price else "buy_stop"
            else:
                # If entry above current = sell limit, below = sell stop
                order_type = "sell_limit" if price > current_price else "sell_stop"
        
        type_map = {"buy_limit": 2, "sell_limit": 3, "buy_stop": 4, "sell_stop": 5}
        order_type_int = type_map.get(order_type, 2)
        
        ticket = self._next_ticket
        self._next_ticket += 1
        
        # Handle expiration
        if expiration is None:
            if expiration_hours is not None:
                expiration = self._current_time + timedelta(hours=expiration_hours)
            else:
                expiration = self._current_time + timedelta(days=30)
        
        order = PendingOrder(
            ticket=ticket,
            symbol=symbol,
            type=order_type_int,
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            time_setup=self._current_time,
            expiration=expiration,
            magic=magic if magic else self.MAGIC_NUMBER,
            comment=comment if comment else self.COMMENT,
        )
        
        self._pending_orders[ticket] = order
        
        return TradeResult(
            success=True,
            order_id=ticket,
            price=price,
            volume=volume,
        )
    
    def cancel_pending_order(self, ticket: int) -> bool:
        """Cancel a pending order."""
        if ticket in self._pending_orders:
            del self._pending_orders[ticket]
            return True
        return False
    
    def get_pending_orders(self, symbol: str = None) -> List[PendingOrder]:
        """Get pending orders."""
        orders = list(self._pending_orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders
    
    def get_my_pending_orders(self) -> List[PendingOrder]:
        """Get pending orders for this bot."""
        return [o for o in self._pending_orders.values() if o.magic == self.MAGIC_NUMBER]
    
    # ═══════════════════════════════════════════════════════════════════════
    # SIMULATION HELPERS - Check SL/TP/Order fills on M15 bar
    # ═══════════════════════════════════════════════════════════════════════
    
    def check_pending_order_fills(self) -> List[int]:
        """Check if any pending orders should fill on current M15 bar."""
        filled_tickets = []
        
        for ticket, order in list(self._pending_orders.items()):
            bar = self.get_m15_bar(order.symbol, self._current_time)
            if bar is None:
                continue
            
            high, low = bar['high'], bar['low']
            
            filled = False
            fill_price = order.price
            
            if order.type == 2:  # buy_limit
                if low <= order.price:
                    filled = True
            elif order.type == 3:  # sell_limit
                if high >= order.price:
                    filled = True
            elif order.type == 4:  # buy_stop
                if high >= order.price:
                    filled = True
            elif order.type == 5:  # sell_stop
                if low <= order.price:
                    filled = True
            
            if filled:
                # Convert to position
                pos_type = 0 if order.type in (2, 4) else 1
                pos = Position(
                    ticket=ticket,
                    symbol=order.symbol,
                    type=pos_type,
                    volume=order.volume,
                    price_open=fill_price,
                    sl=order.sl,
                    tp=order.tp,
                    profit=0.0,
                    time=self._current_time,
                    magic=order.magic,
                    comment=order.comment,
                )
                self._positions[ticket] = pos
                del self._pending_orders[ticket]
                filled_tickets.append(ticket)
        
        return filled_tickets
    
    def check_sl_tp_hits(self) -> List[dict]:
        """Check if any positions hit SL or TP on current M15 bar."""
        hits = []
        
        for ticket, pos in list(self._positions.items()):
            bar = self.get_m15_bar(pos.symbol, self._current_time)
            if bar is None:
                continue
            
            high, low = bar['high'], bar['low']
            
            if pos.type == 0:  # Buy position
                # SL hit (price drops to SL)
                if pos.sl > 0 and low <= pos.sl:
                    hits.append({'ticket': ticket, 'type': 'sl', 'price': pos.sl})
                # TP hit (price rises to TP)
                elif pos.tp > 0 and high >= pos.tp:
                    hits.append({'ticket': ticket, 'type': 'tp', 'price': pos.tp})
            else:  # Sell position
                # SL hit (price rises to SL)
                if pos.sl > 0 and high >= pos.sl:
                    hits.append({'ticket': ticket, 'type': 'sl', 'price': pos.sl})
                # TP hit (price drops to TP)
                elif pos.tp > 0 and low <= pos.tp:
                    hits.append({'ticket': ticket, 'type': 'tp', 'price': pos.tp})
        
        return hits
    
    def update_all_position_profits(self):
        """Update profit for all positions."""
        for pos in self._positions.values():
            pos.profit = self._calculate_position_pnl(pos)
