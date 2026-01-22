#!/usr/bin/env python3
"""
Tradr Bot - Standalone MT5 Live Trading Bot

This bot runs 24/7 on your Windows VM and trades using the EXACT SAME
strategy logic that produced the great backtest results. Discord is NOT
required for trading - the bot operates independently.

IMPORTANT: Uses strategy_core.py directly - the same code as backtests!

Supported Brokers:
- Forex.com Demo (for testing)
- 5ers Live (production)

Usage:
    python main_live_bot.py                    # Uses BROKER_TYPE from .env
    python main_live_bot.py --demo             # Force demo mode
    python main_live_bot.py --validate-symbols # Validate symbol mapping only
    python main_live_bot.py --dry-run          # Run without executing trades

Configuration:
    Set environment variables in .env file:
    - BROKER_TYPE: "forexcom_demo" or "fiveers_live"
    - MT5_SERVER: Broker server name
    - MT5_LOGIN: Account login number
    - MT5_PASSWORD: Account password
    - SCAN_INTERVAL_HOURS: How often to scan (default: 4)
"""

import os
import sys
import time
import json
import argparse
import signal as sig_module
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from zoneinfo import ZoneInfo  # Python 3.9+

# ═══════════════════════════════════════════════════════════════════════════════
# MT5/5ERS SERVER TIMEZONE - UTC+2/+3 (EET/EEST)
# ═══════════════════════════════════════════════════════════════════════════════
SERVER_TZ = ZoneInfo("Europe/Helsinki")  # UTC+2/+3 (EET/EEST)


# ═══════════════════════════════════════════════════════════════════════════════
# CRYPTO DETECTION - For weekend 24/7 scanning
# ═══════════════════════════════════════════════════════════════════════════════
def is_crypto_pair(symbol: str) -> bool:
    """
    Check if symbol is a cryptocurrency that trades 24/7.
    
    Crypto markets (BTC, ETH, etc.) trade continuously through weekends,
    unlike forex/indices which close Friday evening and reopen Sunday evening.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSD", "ETHUSD", "EURUSD")
        
    Returns:
        True if crypto pair (trades 24/7 including weekends)
        False if traditional pair (closed on weekends)
    """
    crypto_keywords = [
        "BTC",     # Bitcoin
        "ETH",     # Ethereum
        "XBT",     # Bitcoin (alternative ticker)
        "CRYPTO",  # Generic crypto prefix
        "LTC",     # Litecoin
        "XRP",     # Ripple
        "BCH",     # Bitcoin Cash
        "ADA",     # Cardano
        "DOT",     # Polkadot
        "LINK",    # Chainlink
        "UNI",     # Uniswap
        "MATIC",   # Polygon
        "SOL",     # Solana
        "AVAX",    # Avalanche
    ]
    
    # Normalize symbol - remove separators, convert to uppercase
    symbol_normalized = symbol.upper().replace("_", "").replace("/", "").replace(".", "")
    
    # Check if any crypto keyword is in the symbol
    return any(keyword in symbol_normalized for keyword in crypto_keywords)


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from strategy_core import (
    StrategyParams,
    compute_confluence,
    compute_trade_levels,
    _infer_trend,
    _pick_direction_from_bias,
)

try:
    from historical_sr import get_all_htf_sr_levels
    HISTORICAL_SR_AVAILABLE = True
except ImportError:
    HISTORICAL_SR_AVAILABLE = False
    def get_all_htf_sr_levels(symbol):
        return {'monthly': [], 'weekly': []}

from tradr.mt5.client import MT5Client, PendingOrder
from tradr.risk.manager import RiskManager
from tradr.utils.logger import setup_logger
from challenge_risk_manager import ChallengeRiskManager, ChallengeConfig, RiskMode, ActionType, ProtectionAction, create_challenge_manager

# Import broker config for multi-broker support
from broker_config import get_broker_config, BrokerType, BrokerConfig
from symbol_mapping import get_broker_symbol, get_internal_symbol

# Import weekend gap risk management
import weekend_gap_manager as wgm

CHALLENGE_MODE = True


@dataclass
class PendingSetup:
    """Tracks a pending trade setup waiting for entry."""
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: Optional[float]
    tp3: Optional[float]
    tp4: Optional[float] = None  # Added for 5-TP system
    tp5: Optional[float] = None  # Added for 5-TP system
    confluence: int = 0
    confluence_score: int = 0
    quality_factors: int = 0
    entry_distance_r: float = 0.0
    created_at: str = ""
    order_ticket: Optional[int] = None
    status: str = "pending"
    lot_size: float = 0.0
    partial_closes: int = 0  # 0=none, 1=TP1, 2=TP2, 3=TP3, 4=TP4, 5=TP5
    trailing_sl: Optional[float] = None
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    tp4_hit: bool = False  # Added for 5-TP system
    tp5_hit: bool = False  # Added for 5-TP system
    progressive_trail_applied: bool = False  # Progressive trailing: SL moved to TP1 at 0.9R
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PendingSetup":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

from config import SIGNAL_MODE, MIN_CONFLUENCE_STANDARD, MIN_CONFLUENCE_AGGRESSIVE
from config import FOREX_PAIRS, METALS, INDICES, CRYPTO_ASSETS
from symbol_mapping import ALL_TRADABLE_OANDA, ftmo_to_oanda, oanda_to_ftmo
from ftmo_config import FIVEERS_CONFIG

# Load broker configuration (auto-detects from BROKER_TYPE env var)
BROKER_CONFIG: BrokerConfig = get_broker_config()

# MT5 connection details from broker config
MT5_SERVER = BROKER_CONFIG.mt5_server
MT5_LOGIN = BROKER_CONFIG.mt5_login
MT5_PASSWORD = BROKER_CONFIG.mt5_password
SCAN_INTERVAL_HOURS = BROKER_CONFIG.scan_interval_hours

# Broker-specific settings
ACCOUNT_SIZE = BROKER_CONFIG.account_size
IS_DEMO = BROKER_CONFIG.is_demo
BROKER_NAME = BROKER_CONFIG.broker_name
BROKER_NAME = BROKER_CONFIG.broker_name

# Load MIN_CONFLUENCE from params loader (single source of truth)
try:
    from params.params_loader import get_min_confluence
    MIN_CONFLUENCE = get_min_confluence()
except Exception:
    MIN_CONFLUENCE = 5  # Fallback if params not available

# Get tradable symbols from broker config (respects excluded_symbols)
TRADABLE_SYMBOLS = BROKER_CONFIG.get_tradable_symbols()

log = setup_logger("tradr", log_file="logs/tradr_live.log")
running = True


# ═══════════════════════════════════════════════════════════════════════════════
# TIMEZONE HELPERS - MT5/5ERS SERVER TIME
# ═══════════════════════════════════════════════════════════════════════════════

def get_server_time() -> datetime:
    """Get current time in MT5 server timezone (UTC+2/+3)."""
    return datetime.now(SERVER_TZ)


def get_server_date() -> datetime.date:
    """Get current date in MT5 server timezone."""
    return get_server_time().date()


def get_next_daily_close() -> datetime:
    """
    Get next daily close time (00:00 server time).
    Daily candle closes at midnight server time.
    """
    server_now = get_server_time()
    
    # Daily close is at 00:00 server time
    today_close = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if server_now >= today_close:
        # Today's close has passed, next one is tomorrow
        next_close = today_close + timedelta(days=1)
    else:
        next_close = today_close
    
    return next_close


def get_next_scan_time(include_today: bool = False) -> datetime:
    """
    Get next scheduled scan time (10 min after daily close).
    Returns datetime in UTC for comparison.

    Args:
        include_today: If True, returns today's scan time even if it's in the past.
                      Useful for initial setup to catch missed scans.
    """
    server_now = get_server_time()

    # Daily close is at 00:00 server time, scan at 00:10 server time
    today_scan = server_now.replace(hour=0, minute=10, second=0, microsecond=0)

    # If include_today is True and we haven't passed today's scan yet, return it
    if include_today and server_now < today_scan:
        # Skip weekends
        if today_scan.weekday() < 5:  # Monday-Friday
            return today_scan.astimezone(timezone.utc)

    # If we're past today's scan (or it's weekend), get tomorrow's
    if server_now >= today_scan or today_scan.weekday() >= 5:
        tomorrow_scan = today_scan + timedelta(days=1)
        # Skip weekends
        while tomorrow_scan.weekday() >= 5:
            tomorrow_scan += timedelta(days=1)
        return tomorrow_scan.astimezone(timezone.utc)

    # Return today's scan (handles case where include_today=False but it's before scan time)
    return today_scan.astimezone(timezone.utc)


def is_market_open() -> bool:
    """
    Check if forex market is open (not weekend).
    Forex: Opens Sunday 22:00 UTC, closes Friday 22:00 UTC.
    """
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour
    
    # Weekend = Saturday whole day + Sunday before 22:00 UTC
    if weekday == 5:  # Saturday
        return False
    if weekday == 6 and hour < 22:  # Sunday before 22:00 UTC
        return False
    # Friday after 22:00 UTC
    if weekday == 4 and hour >= 22:
        return False
    
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# 5ERS DRAWDOWN MONITOR - CRITICAL: Different from FTMO!
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class DrawdownMonitor:
    """
    5ers-compliant drawdown monitoring.
    
    CRITICAL 5ERS DIFFERENCES:
    - Total DD = 10% van STARTBALANS (constant, niet trailing!)
    - GEEN daily DD limiet bij 5ers (unlike FTMO's 5%)
    - Stop-out level = $54,000 (voor 60K account) - CONSTANT
    
    Dit is NIET hetzelfde als FTMO waar daily DD wel geldt!
    """
    
    initial_balance: float = 20000.0
    
    def __post_init__(self):
        self.stop_out_level = self.initial_balance * 0.90  # $54,000
        self.warning_level = self.initial_balance * 0.93   # $55,800 (7% DD)
        self.caution_level = self.initial_balance * 0.95   # $57,000 (5% DD)
        
        # Tracking
        self.high_water_mark = self.initial_balance
        self.current_equity = self.initial_balance
        self.total_dd_pct = 0.0
    
    def update(self, current_equity: float) -> Dict:
        """Update equity and calculate drawdown."""
        self.current_equity = current_equity
        
        # Update HWM (for profit tracking, not DD calculation)
        if current_equity > self.high_water_mark:
            self.high_water_mark = current_equity
        
        # 5ERS: Calculate total DD from INITIAL balance (not HWM!)
        if current_equity < self.initial_balance:
            self.total_dd_pct = ((self.initial_balance - current_equity) / self.initial_balance) * 100
        else:
            self.total_dd_pct = 0.0
        
        return self.get_status()
    
    def get_status(self) -> Dict:
        """Get current drawdown status."""
        return {
            "initial_balance": self.initial_balance,
            "current_equity": self.current_equity,
            "high_water_mark": self.high_water_mark,
            "stop_out_level": self.stop_out_level,
            "total_dd_pct": self.total_dd_pct,
            "distance_to_stopout": self.current_equity - self.stop_out_level,
            "distance_to_stopout_pct": ((self.current_equity - self.stop_out_level) / self.initial_balance) * 100,
            "is_warning": self.current_equity <= self.warning_level,
            "is_caution": self.current_equity <= self.caution_level,
            "is_stopped_out": self.current_equity <= self.stop_out_level,
        }
    
    def should_halt_trading(self) -> bool:
        """Check if trading should be halted (stop-out reached)."""
        return self.current_equity <= self.stop_out_level
    
    def should_reduce_risk(self) -> bool:
        """Check if risk should be reduced (warning level reached)."""
        return self.current_equity <= self.warning_level
    
    def get_risk_multiplier(self) -> float:
        """Get risk multiplier based on drawdown level."""
        if self.current_equity <= self.caution_level:
            return 0.5  # 50% of normal risk
        if self.current_equity <= self.warning_level:
            return 0.7  # 70% of normal risk
        return 1.0  # Normal risk

# Print broker config on startup
log.info("=" * 70)
log.info(f"BROKER: {BROKER_NAME}")
log.info(f"Demo Mode: {'YES ⚠️' if IS_DEMO else 'NO (LIVE)'}")
log.info(f"Account Size: ${ACCOUNT_SIZE:,.0f}")
log.info(f"Risk per Trade: {BROKER_CONFIG.risk_per_trade_pct}% = ${BROKER_CONFIG.risk_amount:.0f}")
log.info(f"Tradable Symbols: {len(TRADABLE_SYMBOLS)}")
log.info("=" * 70)


def load_best_params_from_file():
    """
    Load best parameters from params/current_params.json (single source of truth).
    - No fallback to StrategyParams defaults.
    - Merges with PARAMETER_DEFAULTS (same as optimizer) to guarantee 77 params.
    - Warns if the file is missing params (so you know to re-save from a run).
    """
    from pathlib import Path
    from params.params_loader import load_strategy_params, load_params_dict
    from params.defaults import PARAMETER_DEFAULTS
    
    params_file = Path(__file__).parent / "params" / "current_params.json"
    if not params_file.exists():
        raise FileNotFoundError(
            "CRITICAL: params/current_params.json does not exist!\n"
            "Select a run first: python scripts/select_run.py <run_name>"
        )
    
    # Load raw for diagnostics
    raw = load_params_dict()
    if "parameters" in raw:
        raw_params = raw["parameters"]
    else:
        raw_params = {k: v for k, v in raw.items() if not k.startswith("_")}
    
    missing = set(PARAMETER_DEFAULTS.keys()) - set(raw_params.keys())
    if missing:
        log.warning(
            "params/current_params.json is missing %d parameters; filling from defaults: %s",
            len(missing), sorted(missing)
        )
    
    # Use the same merge logic as optimizer
    params_obj = load_strategy_params()
    log.info("✓ Loaded %d parameters (post-merge) from params/current_params.json", len(vars(params_obj)))
    return params_obj


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global running
    log.info("Shutdown signal received, stopping bot...")
    running = False


sig_module.signal(sig_module.SIGINT, signal_handler)
sig_module.signal(sig_module.SIGTERM, signal_handler)


class LiveTradingBot:
    """
    Main live trading bot for 5ers 60K High Stakes Challenge.

    Uses the EXACT SAME strategy logic as backtest.py for perfect parity.
    Now uses pending orders to match backtest entry behavior exactly.

    KEY FEATURES (5ers Compliant):
    - 5-TP Exit System: 5 take profit levels (0.6R to 3.5R)
    - Immediate scan on first run after restart/weekend
    - Daily scan 10 min after daily close (00:10 server time)
    - Spread & volume checks before entry
    - Weekend gap protection
    - Total DD monitoring (no daily DD for 5ers!)
    """
    def start_ddd_protection_loop(self):
        """
        Start a background thread that checks DDD every 5 seconds and closes all trades if DDD >= halt%.
        
        CRITICAL FIX JAN 20, 2026:
        1. Also cancels ALL pending/limit orders (not just positions)
        2. Syncs day_start_equity on new day to prevent stale baseline
        3. Logs every check for debugging
        
        Strictly compares current equity to fixed day_start_equity from challenge_risk_state.json.
        """
        import threading
        from datetime import date
        
        def ddd_protection_worker():
            from time import sleep
            last_log_time = 0
            
            while running:
                try:
                    # Get current account info
                    account = self.mt5.get_account_info()
                    if not account:
                        log.warning("[DDD Protection] Could not get MT5 account info - connection lost?")
                        sleep(5)
                        continue
                    current_equity = account.get("equity", 0)
                    current_balance = account.get("balance", 0)
                    
                    # Get fixed day_start_equity from challenge_manager (never updated during day)
                    if not self.challenge_manager:
                        log.error("[DDD Protection] CRITICAL: challenge_manager is None! Protection NOT active!")
                        sleep(5)
                        continue
                    
                    # AUTOMATIC RESET: Check if DDD halt is from a PREVIOUS day and auto-reset
                    today = date.today()
                    today_str = today.strftime("%Y-%m-%d")
                    if self.ddd_halted and self.ddd_halt_date and self.ddd_halt_date != today_str:
                        log.warning("=" * 70)
                        log.warning(f"[DDD Protection] 🌅 AUTO-RESET: DDD halt was from {self.ddd_halt_date}, today is {today_str}")
                        log.warning(f"[DDD Protection] Resetting day_start_equity from ${self.challenge_manager.day_start_equity:,.2f} to ${current_equity:,.2f}")
                        log.warning("=" * 70)
                        # Update challenge manager state
                        self.challenge_manager.day_start_equity = current_equity
                        self.challenge_manager.day_start_balance = current_balance
                        self.challenge_manager.current_date = today
                        self.challenge_manager.daily_pnl = 0.0
                        self.challenge_manager.daily_loss_pct = 0.0
                        self.challenge_manager._save_state()
                        # Clear halt
                        self.ddd_halted = False
                        self.ddd_halt_reason = ""
                        self.ddd_halt_date = None
                        self._save_ddd_halt_state()
                        log.info(f"[DDD Protection] ✅ Trading re-enabled for new day with fresh DDD baseline: ${current_equity:,.2f}")
                        sleep(5)
                        continue
                    
                    # CRITICAL FIX: Check if new day and sync
                    if today != self.challenge_manager.current_date:
                        log.warning(f"[DDD Protection] New day detected! {self.challenge_manager.current_date} -> {today}")
                        log.warning(f"[DDD Protection] Syncing with MT5 to update day_start_equity...")
                        
                        # CRITICAL: If DDD halt was active from yesterday, reset day_start_equity to CURRENT equity
                        # This is essential because DDD from yesterday should NOT carry over to new day
                        if self.ddd_halted:
                            log.info(f"[DDD Protection] ✅ NEW DAY - Resetting DDD halt from yesterday")
                            log.info(f"[DDD Protection] Updating day_start_equity from ${self.challenge_manager.day_start_equity:,.2f} to ${current_equity:,.2f}")
                            self.challenge_manager.day_start_equity = current_equity
                            self.challenge_manager.day_start_balance = current_balance
                            self.challenge_manager.current_date = today
                            self.challenge_manager._save_state()
                            self.ddd_halted = False
                            self.ddd_halt_reason = ""
                            self.ddd_halt_date = None
                            self._save_ddd_halt_state()
                            log.info(f"[DDD Protection] ✅ Trading re-enabled for new day with fresh DDD baseline")
                        else:
                            # Normal new day transition - sync with MT5
                            self.challenge_manager.sync_with_mt5(current_balance, current_equity)
                    
                    day_start_equity = self.challenge_manager.day_start_equity
                    if day_start_equity <= 0:
                        log.error(f"[DDD Protection] day_start_equity is {day_start_equity}! Using current equity as fallback.")
                        day_start_equity = current_equity
                        self.challenge_manager.day_start_equity = current_equity
                        self.challenge_manager._save_state()
                    
                    daily_pnl = current_equity - day_start_equity
                    daily_loss_pct = abs(min(0, daily_pnl)) / day_start_equity * 100
                    
                    # Get all DDD thresholds from config
                    warning_pct = getattr(FIVEERS_CONFIG, "daily_loss_warning_pct", 2.0)
                    reduce_pct = getattr(FIVEERS_CONFIG, "daily_loss_reduce_pct", 3.0)
                    halt_pct = getattr(FIVEERS_CONFIG, "daily_loss_halt_pct", 3.5)
                    
                    # === ALSO CHECK TDD (Total DrawDown) ===
                    # TDD is calculated from INITIAL balance (not day start)
                    starting_balance = self.challenge_manager.starting_balance
                    if starting_balance > 0:
                        total_dd_pct = max(0, (starting_balance - current_equity) / starting_balance * 100)
                    else:
                        total_dd_pct = 0.0
                    tdd_halt_pct = 10.0  # 5ers: 10% max total drawdown
                    
                    # Log status only every 5 min OR when DDD/TDD changes significantly
                    import time as time_module
                    now = time_module.time()
                    last_ddd = getattr(self, '_last_logged_ddd', -1)
                    last_tdd = getattr(self, '_last_logged_tdd', -1)
                    ddd_changed = abs(daily_loss_pct - last_ddd) >= 0.5  # Log if DDD changed by 0.5%+
                    tdd_changed = abs(total_dd_pct - last_tdd) >= 0.25   # Log if TDD changed by 0.25%+
                    time_elapsed = now - last_log_time >= 300  # Or every 5 minutes
                    
                    if ddd_changed or tdd_changed or time_elapsed:
                        log.info(f"[DDD/TDD Protection] Equity: ${current_equity:,.2f} | Day Start: ${day_start_equity:,.2f} | Starting: ${starting_balance:,.2f}")
                        log.info(f"[DDD/TDD Protection] DDD: {daily_loss_pct:.2f}% (warn: {warning_pct}%, reduce: {reduce_pct}%, halt: {halt_pct}%) | TDD: {total_dd_pct:.2f}% (halt at {tdd_halt_pct:.2f}%)")
                        last_log_time = now
                        self._last_logged_ddd = daily_loss_pct
                        self._last_logged_tdd = total_dd_pct
                    
                    # === CHECK TDD FIRST (most critical - 10% = account breached) ===
                    if total_dd_pct >= tdd_halt_pct:
                        log.error("=" * 70)
                        log.error(f"🚨 TDD HALT: Equity ${current_equity:,.2f} is {total_dd_pct:.2f}% below starting balance (${starting_balance:,.2f})")
                        log.error(f"  TDD {total_dd_pct:.2f}% >= {tdd_halt_pct:.2f}%! ACCOUNT BREACHED - CLOSING ALL!")
                        log.error("=" * 70)
                        
                        # Cancel ALL pending/limit orders
                        self._emergency_close_all()
                        
                        self.ddd_halted = True
                        self.ddd_halt_reason = f"TDD {total_dd_pct:.2f}% >= {tdd_halt_pct:.2f}% - ACCOUNT BREACHED"
                        self.ddd_halt_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        self._save_ddd_halt_state()  # Persist halt state
                        log.error(f"  🛑 TRADING PERMANENTLY HALTED. {self.ddd_halt_reason}")
                        sleep(60)  # Sleep longer - this is permanent
                        continue
                    
                    # === TIER 3: DDD >= 3.5% → CLOSE ALL ===
                    if daily_loss_pct >= halt_pct:
                        log.error("=" * 70)
                        log.error(f"🚨 DDD TIER 3 HALT: Equity ${current_equity:,.2f} is {daily_loss_pct:.2f}% below day start (${day_start_equity:,.2f})")
                        log.error(f"  DDD {daily_loss_pct:.2f}% >= {halt_pct:.2f}%! CLOSING ALL TRADES AND ORDERS!")
                        log.error("=" * 70)
                        
                        # Cancel ALL pending/limit orders and close all positions
                        self._emergency_close_all()
                        
                        # Set a flag to halt trading until next day
                        self.ddd_halted = True
                        self.ddd_halt_reason = f"DDD {daily_loss_pct:.2f}% >= {halt_pct:.2f}%"
                        self.ddd_halt_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        self._save_ddd_halt_state()  # Persist halt state for restart survival
                        log.error(f"  🛑 Trading halted until next day. Reason: {self.ddd_halt_reason}")
                        # Sleep longer to avoid repeated closes
                        sleep(30)
                    
                    # === TIER 2: DDD >= 3.0% → REDUCE RISK (cancel pending orders only) ===
                    elif daily_loss_pct >= reduce_pct:
                        if not getattr(self, '_ddd_reduce_logged', False):
                            log.warning("=" * 70)
                            log.warning(f"⚠️ DDD TIER 2 REDUCE: Equity ${current_equity:,.2f} is {daily_loss_pct:.2f}% below day start")
                            log.warning(f"  DDD {daily_loss_pct:.2f}% >= {reduce_pct:.2f}%! Reducing risk, cancelling pending orders...")
                            log.warning("=" * 70)
                            
                            # Cancel pending orders to reduce exposure
                            try:
                                pending_orders = self.mt5.get_pending_orders()
                                if pending_orders:
                                    log.warning(f"  Cancelling {len(pending_orders)} pending orders...")
                                    for order in pending_orders:
                                        try:
                                            self.mt5.cancel_pending_order(order.ticket)
                                            log.info(f"  ✓ Cancelled pending order {order.symbol}")
                                        except Exception as e:
                                            log.error(f"  ✗ Failed to cancel {order.symbol}: {e}")
                            except Exception as e:
                                log.error(f"  ✗ Failed to get pending orders: {e}")
                            
                            self._ddd_reduce_logged = True
                        self.ddd_halted = False  # Don't halt, just reduce
                        self.ddd_halt_reason = ""
                    
                    # === TIER 1: DDD >= 2.0% → WARNING ===
                    elif daily_loss_pct >= warning_pct:
                        if not getattr(self, '_ddd_warning_logged', False):
                            log.warning("=" * 70)
                            log.warning(f"⚠️ DDD TIER 1 WARNING: Equity ${current_equity:,.2f} is {daily_loss_pct:.2f}% below day start")
                            log.warning(f"  DDD {daily_loss_pct:.2f}% >= {warning_pct:.2f}%! Monitoring closely...")
                            log.warning("=" * 70)
                            self._ddd_warning_logged = True
                        self.ddd_halted = False
                        self.ddd_halt_reason = ""
                    
                    # === NORMAL: Reset flags ===
                    else:
                        self.ddd_halted = False
                        self.ddd_halt_reason = ""
                        self._ddd_warning_logged = False
                        self._ddd_reduce_logged = False
                    
                    sleep(5)
                except Exception as e:
                    log.error(f"[DDD Protection] Exception: {e}")
                    import traceback
                    log.error(traceback.format_exc())
                    sleep(5)
        t = threading.Thread(target=ddd_protection_worker, daemon=True)
        t.start()
    
    def _emergency_close_all(self):
        """
        Emergency close all positions and cancel all pending orders.
        Called when DDD or TDD limits are breached.
        
        CRITICAL FIX JAN 20, 2026: Also cancels pending/limit orders.
        CRITICAL FIX JAN 20, 2026 #2: Also clears all queues to prevent re-entry.
        """
        # Cancel ALL pending/limit orders FIRST
        try:
            pending_orders = self.mt5.get_pending_orders()
            if pending_orders:
                log.error(f"  Cancelling {len(pending_orders)} pending orders...")
                for order in pending_orders:
                    try:
                        result = self.mt5.cancel_pending_order(order.ticket)
                        if result:
                            log.info(f"  ✓ Cancelled pending order {order.symbol} (ticket: {order.ticket})")
                        else:
                            log.error(f"  ✗ Failed to cancel pending order {order.symbol}: {order.ticket}")
                    except Exception as e:
                        log.error(f"  ✗ Exception cancelling order {order.ticket}: {e}")
            else:
                log.info(f"  No pending orders to cancel")
        except Exception as e:
            log.error(f"  ✗ Failed to get/cancel pending orders: {e}")
        
        # Close all positions
        try:
            positions = self.mt5.get_my_positions()
            if positions:
                log.error(f"  Closing {len(positions)} open positions...")
                for pos in positions:
                    result = self.mt5.close_position(pos.ticket)
                    if hasattr(result, 'success') and result.success:
                        log.info(f"  ✓ Closed {pos.symbol}")
                    else:
                        log.error(f"  ✗ Failed to close {pos.symbol}: {getattr(result, 'error', 'unknown')}")
            else:
                log.info(f"  No open positions to close")
        except Exception as e:
            log.error(f"  ✗ Failed to get/close positions: {e}")
        
        # CRITICAL: Only clear ACTIVE setups (pending orders, filled positions)
        # KEEP awaiting_entry and awaiting_spread - these are untriggered signals that should persist!
        # Signals in queues are still valid and can trigger after halt resets (within 120h expiry)
        try:
            # Mark pending_setups with active orders/positions as "halted"
            # This prevents them from re-triggering but doesn't affect untriggered signals in queues
            if hasattr(self, 'pending_setups') and self.pending_setups:
                halted_count = 0
                for symbol, setup in self.pending_setups.items():
                    if setup.status in ("pending", "filled"):
                        setup.status = "halted"
                        halted_count += 1
                        log.info(f"  ✓ Marked {symbol} setup as halted (was {setup.status})")
                if halted_count > 0:
                    self._save_pending_setups()
                    log.info(f"  ✓ Halted {halted_count} active setups")
            
            # Log what we're KEEPING (not clearing)
            if hasattr(self, 'awaiting_entry') and self.awaiting_entry:
                log.info(f"  ℹ️ Keeping {len(self.awaiting_entry)} signals in awaiting_entry (untriggered, still valid)")
            if hasattr(self, 'awaiting_spread') and self.awaiting_spread:
                log.info(f"  ℹ️ Keeping {len(self.awaiting_spread)} signals in awaiting_spread (untriggered, still valid)")
            
        except Exception as e:
            log.error(f"  ✗ Failed to update setups: {e}")

    PENDING_SETUPS_FILE = "pending_setups.json"
    TRADING_DAYS_FILE = "trading_days.json"
    FIRST_RUN_FLAG_FILE = "first_run_complete.flag"
    AWAITING_SPREAD_FILE = "awaiting_spread.json"
    AWAITING_ENTRY_FILE = "awaiting_entry.json"  # Signals waiting for price proximity
    VALIDATE_INTERVAL_MINUTES = 10
    MAIN_LOOP_INTERVAL_SECONDS = 10
    SPREAD_CHECK_INTERVAL_MINUTES = 5
    ENTRY_CHECK_INTERVAL_MINUTES = 5  # Check entry proximity every 5 min
    MAX_SPREAD_WAIT_HOURS = 120  # 5 days - matches backtest max_wait_bars=5
    MAX_ENTRY_WAIT_HOURS = 120  # 5 days - matches backtest max_wait_bars=5
    WEEKEND_GAP_THRESHOLD_PCT = 1.0  # 1% gap threshold
    
    def __init__(self, immediate_scan: bool = False):
        self.ddd_halted = False
        self.ddd_halt_reason = ""
        self.ddd_halt_date: Optional[str] = None  # Track which day the halt occurred
        self.mt5 = MT5Client(
            server=MT5_SERVER,
            login=MT5_LOGIN,
            password=MT5_PASSWORD,
        )
        self.risk_manager = RiskManager(state_file="challenge_state.json")
        # STRICT: Load params (merged with defaults) - no fallback to dataclass defaults
        # load_best_params_from_file() returns StrategyParams with defaults merged
        self.params = load_best_params_from_file()
        self.last_scan_time: Optional[datetime] = None
        self.next_scan_time: Optional[datetime] = None  # Store next scheduled scan time
        self.last_validate_time: Optional[datetime] = None
        self.last_spread_check_time: Optional[datetime] = None
        self.last_entry_check_time: Optional[datetime] = None  # Track entry proximity checks
        self.scan_count = 0
        self.pending_setups: Dict[str, PendingSetup] = {}
        self.symbol_map: Dict[str, str] = {}  # our_symbol -> broker_symbol
        self.challenge_manager: Optional[ChallengeRiskManager] = None
        # First run detection
        self.immediate_scan_requested = immediate_scan
        self.first_run_complete = self._check_first_run_complete()
        # 5ers DD Monitor (no daily DD, only total DD from start balance!)
        self.dd_monitor = DrawdownMonitor(initial_balance=ACCOUNT_SIZE)
        
        # Trading days tracking for 5ers minimum trading days requirement
        self.trading_days: set = set()
        self.challenge_start_date: Optional[datetime] = None
        self.challenge_end_date: Optional[datetime] = None

        # Weekend gap risk management
        self.friday_closing_done: bool = False  # Track if we've done Friday closing this week
        self.friday_close_prices: dict = {}  # Store Friday close prices for gap detection
        self.last_friday_close_check: Optional[datetime] = None  # When we last did Friday check

        self._load_pending_setups()
        self._load_trading_days()
        self._load_awaiting_spread()
        self._load_awaiting_entry()  # Signals waiting for price proximity
        self._load_ddd_halt_state()  # Load DDD halt state (survives restarts)
        self._auto_start_challenge()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DDD HALT STATE PERSISTENCE - Survives bot restarts within same day
    # ═══════════════════════════════════════════════════════════════════════════
    
    DDD_HALT_STATE_FILE = "ddd_halt_state.json"
    
    def _load_ddd_halt_state(self):
        """Load DDD halt state from file. Halt persists for same day only."""
        try:
            if Path(self.DDD_HALT_STATE_FILE).exists():
                with open(self.DDD_HALT_STATE_FILE, 'r') as f:
                    state = json.load(f)
                
                halt_date = state.get("halt_date", "")
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
                if halt_date == today:
                    # Same day - restore halt state
                    self.ddd_halted = state.get("halted", False)
                    self.ddd_halt_reason = state.get("reason", "")
                    self.ddd_halt_date = halt_date
                    if self.ddd_halted:
                        log.warning(f"🚨 RESTORED DDD HALT STATE from earlier today: {self.ddd_halt_reason}")
                else:
                    # New day - clear old halt
                    log.info(f"DDD halt from {halt_date} expired (new day: {today})")
                    self.ddd_halted = False
                    self.ddd_halt_reason = ""
                    self.ddd_halt_date = None
                    self._save_ddd_halt_state()  # Clear the file
        except Exception as e:
            log.error(f"Error loading DDD halt state: {e}")
            self.ddd_halted = False
            self.ddd_halt_reason = ""
    
    def _save_ddd_halt_state(self):
        """Save DDD halt state to file."""
        try:
            state = {
                "halted": self.ddd_halted,
                "reason": self.ddd_halt_reason,
                "halt_date": self.ddd_halt_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.DDD_HALT_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log.error(f"Error saving DDD halt state: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIRST RUN DETECTION - Scan immediately after restart/weekend
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _check_first_run_complete(self) -> bool:
        """Check of eerste scan al gedaan is sinds laatste restart."""
        flag_file = Path(self.FIRST_RUN_FLAG_FILE)
        if flag_file.exists():
            # Check of flag file recent is (binnen 24 uur)
            mtime = flag_file.stat().st_mtime
            age_hours = (time.time() - mtime) / 3600
            return age_hours < 24
        return False
    
    def _mark_first_run_complete(self):
        """Markeer dat eerste scan voltooid is."""
        Path(self.FIRST_RUN_FLAG_FILE).touch()
    
    def should_do_immediate_scan(self) -> bool:
        """Bepaal of we direct moeten scannen (na restart of weekend)."""
        # 1. Expliciet gevraagd via --first-run
        if self.immediate_scan_requested:
            return True
        
        # 2. Eerste run na restart en markt is open
        if not self.first_run_complete and is_market_open():
            return True
        
        return False
    
    def is_news_blackout(self) -> bool:
        """Check if currently in news event blackout period."""
        if not FIVEERS_CONFIG.block_trading_around_news:
            return False
        now = datetime.now(timezone.utc)
        
        # Check each major news event
        for day_of_week, hour, minute in FIVEERS_CONFIG.major_news_events:
            if now.weekday() != day_of_week:
                continue
            
            # Create news event time for today
            news_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Calculate blackout window
            blackout_start = news_time - timedelta(minutes=FIVEERS_CONFIG.news_blackout_minutes_before)
            blackout_end = news_time + timedelta(minutes=FIVEERS_CONFIG.news_blackout_minutes_after)
            
            if blackout_start <= now <= blackout_end:
                log.warning(f"📰 NEWS BLACKOUT: {now.strftime('%H:%M UTC')} - Event at {news_time.strftime('%H:%M UTC')}")
                return True
        
        return False
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SPREAD QUEUE - Track signals waiting for better spread
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _load_awaiting_spread(self):
        """Load signals waiting for better spread."""
        self.awaiting_spread: Dict = {}
        try:
            if Path(self.AWAITING_SPREAD_FILE).exists():
                with open(self.AWAITING_SPREAD_FILE, 'r') as f:
                    self.awaiting_spread = json.load(f)
                if self.awaiting_spread:
                    log.info(f"Loaded {len(self.awaiting_spread)} signals awaiting spread improvement")
        except Exception as e:
            log.error(f"Error loading awaiting_spread: {e}")
            self.awaiting_spread = {}
    
    def _save_awaiting_spread(self):
        """Save signals waiting for better spread."""
        try:
            with open(self.AWAITING_SPREAD_FILE, 'w') as f:
                json.dump(self.awaiting_spread, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Error saving awaiting_spread: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # AWAITING ENTRY - Queue for signals waiting for price proximity
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _load_awaiting_entry(self):
        """Load signals waiting for price to approach entry level."""
        self.awaiting_entry: Dict = {}
        try:
            if Path(self.AWAITING_ENTRY_FILE).exists():
                with open(self.AWAITING_ENTRY_FILE, 'r') as f:
                    self.awaiting_entry = json.load(f)
                if self.awaiting_entry:
                    log.info(f"Loaded {len(self.awaiting_entry)} signals awaiting entry proximity")
        except Exception as e:
            log.error(f"Error loading awaiting_entry: {e}")
            self.awaiting_entry = {}
    
    def _save_awaiting_entry(self):
        """Save signals waiting for price proximity."""
        try:
            with open(self.AWAITING_ENTRY_FILE, 'w') as f:
                json.dump(self.awaiting_entry, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Error saving awaiting_entry: {e}")
    
    def add_to_awaiting_entry(self, setup: Dict):
        """
        Add setup to entry queue - wait for price to approach entry level.
        
        When price is far from entry (>0.3R), we don't place limit order yet.
        This avoids wasted limit orders that never fill.
        """
        symbol = setup["symbol"]
        entry = setup.get("entry", 0)
        sl = setup.get("stop_loss", 0)
        
        # BUGFIX: Don't add if we already have a pending/filled setup
        if symbol in self.pending_setups:
            existing = self.pending_setups[symbol]
            if existing.status in ("pending", "filled"):
                log.info(f"[{symbol}] Not adding to entry queue - already have {existing.status} setup")
                return
        
        # BUGFIX: Don't add if we have an open position
        broker_symbol = self.symbol_map.get(symbol, symbol)
        if self.check_existing_position(broker_symbol):
            log.info(f"[{symbol}] Not adding to entry queue - already have open position")
            return
        
        self.awaiting_entry[symbol] = {
            **setup,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_check": datetime.now(timezone.utc).isoformat(),
            "check_count": 0,
        }
        self._save_awaiting_entry()
        
        # Calculate current distance for logging
        broker_symbol = self.symbol_map.get(symbol, symbol)
        tick = self.mt5.get_tick(broker_symbol)
        if tick:
            risk = abs(entry - sl) if entry and sl else 0
            if risk > 0:
                current_price = tick.bid if setup.get("direction") == "bullish" else tick.ask
                entry_distance_r = abs(current_price - entry) / risk
                log.info(f"[{symbol}] Added to entry queue - price is {entry_distance_r:.2f}R from entry, waiting for proximity")
            else:
                log.info(f"[{symbol}] Added to entry queue - waiting for price proximity")
        else:
            log.info(f"[{symbol}] Added to entry queue - waiting for price proximity")
    
    def check_awaiting_entry_signals(self):
        """
        Check signals waiting for price to approach entry level.
        Called every ENTRY_CHECK_INTERVAL_MINUTES (default: 30 min).
        
        Logic:
        - If DDD halt active: skip (don't place new orders)
        - If price is within limit_order_proximity_r (0.3R) of entry: place limit order
        - If signal too old (MAX_ENTRY_WAIT_HOURS): remove
        - If entry is beyond max_entry_distance_r: remove
        """
        # CRITICAL: Don't place orders during DDD halt
        if getattr(self, 'ddd_halted', False):
            log.debug("Skipping entry queue check - DDD halt active")
            return
        
        if not self.awaiting_entry:
            return
        
        now = datetime.now(timezone.utc)
        signals_to_remove = []
        proximity_r = FIVEERS_CONFIG.limit_order_proximity_r  # 0.3R
        
        log.info(f"Checking {len(self.awaiting_entry)} signals awaiting price proximity...")
        
        for symbol, setup in list(self.awaiting_entry.items()):
            # BUGFIX: Check if we already have a pending order or position for this symbol
            if symbol in self.pending_setups:
                existing = self.pending_setups[symbol]
                if existing.status in ("pending", "filled"):
                    log.debug(f"[{symbol}] Already have {existing.status} setup - removing from entry queue")
                    signals_to_remove.append(symbol)
                    continue
            
            broker_symbol = self.symbol_map.get(symbol, symbol)
            if self.check_existing_position(broker_symbol):
                log.debug(f"[{symbol}] Already have open position - removing from entry queue")
                signals_to_remove.append(symbol)
                continue
            
            # Check age - expire after MAX_ENTRY_WAIT_HOURS
            created_at_str = setup.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    age_hours = (now - created_at).total_seconds() / 3600
                    
                    if age_hours > self.MAX_ENTRY_WAIT_HOURS:
                        log.info(f"[{symbol}] Entry signal expired after {age_hours:.1f} hours")
                        signals_to_remove.append(symbol)
                        continue
                except ValueError:
                    pass
            
            # Get current price
            # broker_symbol already defined above
            tick = self.mt5.get_tick(broker_symbol)
            if not tick:
                log.debug(f"[{symbol}] Cannot get tick, will retry later")
                continue
            
            entry = setup.get("entry", 0)
            sl = setup.get("stop_loss", 0)
            risk = abs(entry - sl) if entry and sl else 0
            
            if risk <= 0:
                log.warning(f"[{symbol}] Invalid risk={risk}, removing from queue")
                signals_to_remove.append(symbol)
                continue
            
            current_price = tick.bid if setup.get("direction") == "bullish" else tick.ask
            entry_distance_r = abs(current_price - entry) / risk
            
            # NOTE: Don't cancel based on distance - setup was valid at placement
            # Price can temporarily move away and come back
            # Only cancel via: time expiry (7d), SL breach, or direction change
            # if entry_distance_r > FIVEERS_CONFIG.max_entry_distance_r:
            #     log.info(f"[{symbol}] Entry too far ({entry_distance_r:.2f}R > {FIVEERS_CONFIG.max_entry_distance_r}R), removing")
            #     signals_to_remove.append(symbol)
            #     continue
            
            # Log distance for monitoring
            if entry_distance_r > FIVEERS_CONFIG.max_entry_distance_r:
                log.debug(f"[{symbol}] Entry {entry_distance_r:.2f}R away (beyond {FIVEERS_CONFIG.max_entry_distance_r}R) - keeping order, price may return")
            
            # Check if price is close enough to place limit order
            if entry_distance_r <= proximity_r:
                log.info(f"[{symbol}] ✅ Price within {proximity_r}R of entry ({entry_distance_r:.2f}R)")
                
                # Check spread before placing order
                conditions = self.check_market_conditions(symbol)
                
                if conditions["spread_ok"]:
                    log.info(f"[{symbol}] Placing limit order!")
                    if self.place_setup_order(setup, check_spread=False, skip_proximity_check=True):
                        signals_to_remove.append(symbol)
                else:
                    # Price close but spread bad - move to spread queue
                    log.info(f"[{symbol}] Price OK but spread bad ({conditions['spread_pips']:.1f} pips)")
                    log.info(f"[{symbol}] Moving to spread queue...")
                    signals_to_remove.append(symbol)
                    self.add_to_awaiting_spread(setup)
            else:
                # Still too far
                setup["check_count"] = setup.get("check_count", 0) + 1
                setup["last_check"] = now.isoformat()
                log.debug(f"[{symbol}] Price at {entry_distance_r:.2f}R from entry, waiting for {proximity_r}R")
        
        # Remove processed signals
        for symbol in signals_to_remove:
            if symbol in self.awaiting_entry:
                del self.awaiting_entry[symbol]
        
        self._save_awaiting_entry()
    
    def add_to_awaiting_spread(self, setup: Dict):
        """Add setup to awaiting spread queue."""
        symbol = setup["symbol"]
        
        # BUGFIX: Don't add if we already have a pending/filled setup
        if symbol in self.pending_setups:
            existing = self.pending_setups[symbol]
            if existing.status in ("pending", "filled"):
                log.info(f"[{symbol}] Not adding to spread queue - already have {existing.status} setup")
                return
        
        # BUGFIX: Don't add if we have an open position
        broker_symbol = self.symbol_map.get(symbol, symbol)
        if self.check_existing_position(broker_symbol):
            log.info(f"[{symbol}] Not adding to spread queue - already have open position")
            return
        
        self.awaiting_spread[symbol] = {
            **setup,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_check": datetime.now(timezone.utc).isoformat(),
            "check_count": 0,
        }
        self._save_awaiting_spread()
        log.info(f"[{symbol}] Added to spread queue - waiting for better conditions")
    
    def check_awaiting_spread_signals(self):
        """
        Check signals waiting for better spread.
        Called every SPREAD_CHECK_INTERVAL_MINUTES.
        """
        # CRITICAL: Don't place orders during DDD halt
        if getattr(self, 'ddd_halted', False):
            log.debug("Skipping spread queue check - DDD halt active")
            return
        
        if not self.awaiting_spread:
            return
        
        now = datetime.now(timezone.utc)
        signals_to_remove = []
        
        log.info(f"Checking {len(self.awaiting_spread)} signals waiting for spread improvement...")
        
        for symbol, setup in list(self.awaiting_spread.items()):
            # Check age - expire after MAX_SPREAD_WAIT_HOURS
            created_at_str = setup.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    age_hours = (now - created_at).total_seconds() / 3600
                    
                    if age_hours > self.MAX_SPREAD_WAIT_HOURS:
                        log.info(f"[{symbol}] Signal expired after {age_hours:.1f} hours")
                        signals_to_remove.append(symbol)
                        continue
                except ValueError:
                    pass
            
            # Check if entry price is still reachable
            broker_symbol = self.symbol_map.get(symbol, symbol)
            tick = self.mt5.get_tick(broker_symbol)
            if not tick:
                continue
            
            entry = setup.get("entry", 0)
            sl = setup.get("stop_loss", 0)
            risk = abs(entry - sl) if entry and sl else 0
            
            if risk > 0:
                current_price = tick.bid if setup.get("direction") == "bullish" else tick.ask
                entry_distance_r = abs(current_price - entry) / risk
                
                if entry_distance_r > FIVEERS_CONFIG.max_entry_distance_r:
                    log.info(f"[{symbol}] Entry too far now ({entry_distance_r:.2f}R), removing")
                    signals_to_remove.append(symbol)
                    continue
            
            # Check if we already have a pending order or position for this symbol
            if symbol in self.pending_setups:
                existing = self.pending_setups[symbol]
                if existing.status in ("pending", "filled"):
                    log.debug(f"[{symbol}] Already have {existing.status} setup - removing from spread queue")
                    signals_to_remove.append(symbol)
                    continue
            
            broker_symbol = self.symbol_map.get(symbol, symbol)
            if self.check_existing_position(broker_symbol):
                log.debug(f"[{symbol}] Already have open position - removing from spread queue")
                signals_to_remove.append(symbol)
                continue
            
            # Check market conditions
            conditions = self.check_market_conditions(symbol)
            
            if conditions["spread_ok"] and conditions["volume_ok"]:
                log.info(f"[{symbol}] ✅ Spread now OK ({conditions['spread_pips']:.1f} pips)")
                log.info(f"[{symbol}] Executing trade!")
                
                # Execute trade
                if self.place_setup_order(setup, check_spread=False):
                    signals_to_remove.append(symbol)
            else:
                log.debug(f"[{symbol}] Still waiting - {conditions['reason']}")
                setup["check_count"] = setup.get("check_count", 0) + 1
                setup["last_check"] = now.isoformat()
        
        # Remove processed signals
        for symbol in signals_to_remove:
            if symbol in self.awaiting_spread:
                del self.awaiting_spread[symbol]
        
        self._save_awaiting_spread()
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MARKET CONDITIONS CHECK - Spread & Volume
    # ═══════════════════════════════════════════════════════════════════════════
    
    def check_market_conditions(self, symbol: str) -> Dict:
        """
        Check volume en spread voor een symbol.
        
        Returns:
            Dict met: spread_ok, volume_ok, spread_pips, reason
        """
        broker_symbol = self.symbol_map.get(symbol, symbol)
        
        tick = self.mt5.get_tick(broker_symbol)
        if not tick:
            return {
                "spread_ok": False,
                "volume_ok": False,
                "spread_pips": 999,
                "reason": "Cannot get tick data"
            }
        
        # Calculate spread in pips
        from ftmo_config import get_pip_size
        pip_size = get_pip_size(symbol)
        spread_pips = tick.spread / pip_size if pip_size > 0 else tick.spread
        
        # Get max allowed spread
        max_spread = FIVEERS_CONFIG.get_max_spread_pips(symbol)
        spread_ok = spread_pips <= max_spread
        
        # Volume check - basic tick volume check
        candles = self.mt5.get_ohlcv(broker_symbol, "M1", 5)
        if candles:
            recent_volume = sum(c.get("volume", 0) for c in candles[-3:]) / 3
            volume_ok = recent_volume > 0
        else:
            volume_ok = True  # Default to OK if we can't check
        
        reason = ""
        if not spread_ok:
            reason = f"Spread too wide: {spread_pips:.1f} > {max_spread:.1f} pips"
        if not volume_ok:
            reason = f"Low volume detected"
        
        return {
            "spread_ok": spread_ok,
            "volume_ok": volume_ok,
            "spread_pips": spread_pips,
            "max_spread": max_spread,
            "reason": reason
        }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # WEEKEND GAP PROTECTION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def check_weekend_gap(self, symbol: str) -> Optional[Dict]:
        """
        Check voor weekend gap en return gap info.
        
        Returns:
            Dict met gap_pct, direction, is_significant OF None als geen gap
        """
        broker_symbol = self.symbol_map.get(symbol, symbol)
        
        # Get recent D1 candles
        candles = self.mt5.get_ohlcv(broker_symbol, "D1", 5)
        if not candles or len(candles) < 2:
            return None
        
        friday_close = candles[-2]["close"]  # Voorlaatste candle = vrijdag
        current_candle = candles[-1]
        monday_open = current_candle["open"]
        
        gap_pct = ((monday_open - friday_close) / friday_close) * 100
        
        return {
            "friday_close": friday_close,
            "monday_open": monday_open,
            "gap_pct": gap_pct,
            "gap_direction": "up" if gap_pct > 0 else "down",
            "is_significant": abs(gap_pct) >= self.WEEKEND_GAP_THRESHOLD_PCT,
        }
    
    def handle_weekend_gap_positions(self):
        """
        Handle bestaande posities na weekend gap.
        
        Actions:
        - Als SL door gap heen is gesprongen: sluit direct
        - Log significant gaps voor monitoring
        """
        positions = self.mt5.get_my_positions()
        if not positions:
            return
        
        server_now = get_server_time()
        
        # Alleen uitvoeren op maandagochtend
        if server_now.weekday() != 0:  # Niet maandag
            return
        if server_now.hour > 2:  # Na eerste 2 uur van maandag
            return
        
        log.info("=" * 70)
        log.info("🔍 WEEKEND GAP CHECK - Analyzing positions after weekend")
        log.info("=" * 70)
        
        for pos in positions:
            internal_symbol = get_internal_symbol(pos.symbol)
            gap_info = self.check_weekend_gap(internal_symbol)
            
            if not gap_info:
                continue
            
            tick = self.mt5.get_tick(pos.symbol)
            if not tick:
                continue
            
            current_price = tick.bid if pos.type == 0 else tick.ask  # 0=BUY
            
            # Check of SL is gapped
            if pos.type == 0:  # Long position
                if current_price <= pos.sl:
                    log.warning(f"[{pos.symbol}] ⚠️ SL GAPPED! Price {current_price:.5f} <= SL {pos.sl:.5f}")
                    log.warning(f"  Weekend gap: {gap_info['gap_pct']:.2f}%")
                    log.warning(f"  Closing position immediately!")
                    self.mt5.close_position(pos.ticket)
            else:  # Short position
                if current_price >= pos.sl:
                    log.warning(f"[{pos.symbol}] ⚠️ SL GAPPED! Price {current_price:.5f} >= SL {pos.sl:.5f}")
                    log.warning(f"  Weekend gap: {gap_info['gap_pct']:.2f}%")
                    log.warning(f"  Closing position immediately!")
                    self.mt5.close_position(pos.ticket)
            
            if gap_info["is_significant"]:
                log.info(f"[{pos.symbol}] Significant gap detected: {gap_info['gap_pct']:.2f}%")
                log.info(f"  Friday close: {gap_info['friday_close']:.5f}")
                log.info(f"  Monday open: {gap_info['monday_open']:.5f}")
                log.info(f"  Position P/L: ${pos.profit:.2f}")

    # ═══════════════════════════════════════════════════════════════════════════
    # WEEKEND GAP RISK MANAGEMENT - Tier 1 Conservative Strategy
    # ═══════════════════════════════════════════════════════════════════════════

    def handle_friday_position_closing(self):
        """
        TIER 1: Correlation-aware Friday position closing
        Runs Friday 16:00+ UTC to reduce weekend gap exposure

        Actions:
        - Close losing positions (< 0R)
        - Close positions > 1.6R (take profit)
        - Reduce 50% of positions 0-0.5R (new positions)
        - Hold positions 0.5R-1.6R in sweet spot (max 2 per correlation group, max 5 total)
        - Hold ALL crypto (BTC/ETH - no weekend gap risk)
        """
        now = datetime.now(timezone.utc)

        # Only run Friday 16:00+ UTC
        if now.weekday() != 4 or now.hour < 16:
            # Reset flag on non-Friday or before 16:00
            if now.weekday() != 4:
                self.friday_closing_done = False
            return

        # Only run once per Friday
        if self.friday_closing_done:
            return

        log.info("=" * 70)
        log.info("🔒 FRIDAY POSITION CLOSING - Weekend Gap Risk Management (Tier 1)")
        log.info("=" * 70)

        positions = self.mt5.get_my_positions()
        if not positions:
            log.info("No positions to manage for weekend")
            self.friday_closing_done = True
            return

        # Use weekend_gap_manager to select positions
        result = wgm.select_positions_for_weekend_tier1(
            positions=positions,
            current_time=now,
            max_per_group=2,  # Max 2 positions per correlation group
            max_total_non_crypto=5,  # Max 5 non-crypto positions total
        )

        # Execute closures
        for pos in result['CLOSE']:
            symbol = get_internal_symbol(pos.symbol)
            log.info(f"🔒 Closing {symbol} for weekend (ticket {pos.ticket})")
            close_result = self.mt5.close_position(pos.ticket)
            if hasattr(close_result, 'success') and close_result.success:
                log.info(f"  ✓ Closed successfully")
            else:
                log.error(f"  ✗ Failed to close: {getattr(close_result, 'error', 'unknown')}")

        # Execute 50% reductions
        for pos in result['REDUCE_50']:
            symbol = get_internal_symbol(pos.symbol)
            current_volume = pos.volume
            reduce_volume = current_volume / 2

            log.info(f"⚠️ Reducing {symbol} by 50% (ticket {pos.ticket})")
            log.info(f"  Current volume: {current_volume:.2f} → New volume: {reduce_volume:.2f}")

            # Close 50% by volume
            close_result = self.mt5.close_position(pos.ticket, volume=reduce_volume)
            if hasattr(close_result, 'success') and close_result.success:
                log.info(f"  ✓ Reduced successfully")
            else:
                log.error(f"  ✗ Failed to reduce: {getattr(close_result, 'error', 'unknown')}")

        # Store Friday close prices for gap detection
        remaining_positions = self.mt5.get_my_positions()
        if remaining_positions:
            self.friday_close_prices = wgm.store_friday_close_prices(
                remaining_positions,
                self.mt5
            )

        # Mark Friday closing as done
        self.friday_closing_done = True
        self.last_friday_close_check = now

        log.info("=" * 70)
        log.info(f"✅ Friday closing complete - {len(result['HOLD'])} positions held for weekend")
        log.info(f"   Max gap risk: {result['stats']['max_gap_risk_pct']:.1f}% of account")
        log.info("=" * 70)

    def handle_sunday_gap_detection(self):
        """
        SUNDAY EVENING GAP DETECTION
        Runs Sunday 22:00-23:59 UTC when forex markets reopen

        Actions:
        - Detect significant gaps (> 1%)
        - Close positions where SL was gapped through
        - Close positions with catastrophic gaps (> 2% adverse)
        """
        now = datetime.now(timezone.utc)

        day_of_week = now.weekday()
        hour = now.hour

        # Sunday = 6, Monday = 0
        is_sunday_open = (day_of_week == 6 and hour >= 22)
        is_monday_morning = (day_of_week == 0 and hour < 2)

        if not (is_sunday_open or is_monday_morning):
            return

        if not self.friday_close_prices:
            log.warning("⚠️ No Friday close prices stored, skipping Sunday gap detection")
            return

        positions = self.mt5.get_my_positions()
        if not positions:
            return

        log.info("=" * 70)
        log.info("🚨 SUNDAY GAP DETECTION - Forex Markets Reopening")
        log.info("=" * 70)

        # Detect gaps using weekend_gap_manager
        gap_result = wgm.detect_sunday_gaps(
            positions=positions,
            friday_prices=self.friday_close_prices,
            current_time=now,
            gap_threshold_pct=1.0,  # Log warning if gap > 1%
            catastrophic_gap_pct=2.0,  # Close if adverse gap > 2%
        )

        # Execute immediate closures for gapped positions
        for pos in gap_result['CLOSE_IMMEDIATELY']:
            symbol = get_internal_symbol(pos.symbol)
            log.critical(f"🚨 EMERGENCY CLOSE: {symbol} (ticket {pos.ticket})")
            close_result = self.mt5.close_position(pos.ticket)
            if hasattr(close_result, 'success') and close_result.success:
                log.info(f"  ✓ Closed successfully at market")
            else:
                log.error(f"  ✗ Failed to close: {getattr(close_result, 'error', 'unknown')}")

        # Log warnings
        for pos, gap_pct in gap_result['WARNINGS']:
            symbol = get_internal_symbol(pos.symbol)
            log.warning(f"⚠️ {symbol}: {gap_pct:.2f}% gap detected")

        log.info("=" * 70)
        log.info(f"✅ Sunday gap detection complete - {len(gap_result['CLOSE_IMMEDIATELY'])} positions closed")
        log.info("=" * 70)

    # ═══════════════════════════════════════════════════════════════════════════
    # 5ERS DRAWDOWN MONITORING (No daily DD limit!)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def monitor_5ers_drawdown(self) -> bool:
        """
        Monitor drawdown levels (5ers compliant - NO daily DD limit!).
        
        CRITICAL: 5ers only tracks total DD from START BALANCE.
        Stop-out = $54,000 for 60K account (constant, not trailing).
        
        Returns:
            True if stop-out triggered (halt trading), False otherwise
        """
        account = self.mt5.get_account_info()
        if not account:
            return False
        
        equity = account.get("equity", 0)
        status = self.dd_monitor.update(equity)
        
        # Log warning levels
        if status["is_warning"]:
            log.warning("=" * 70)
            log.warning("⚠️ 5ERS DRAWDOWN WARNING")
            log.warning(f"  Equity: ${equity:,.2f}")
            log.warning(f"  Total DD: {status['total_dd_pct']:.2f}% (from ${status['initial_balance']:,.0f})")
            log.warning(f"  Distance to stop-out: ${status['distance_to_stopout']:,.2f}")
            log.warning(f"  Stop-out level: ${status['stop_out_level']:,.2f}")
            log.warning("=" * 70)
        
        if status["is_stopped_out"]:
            log.error("=" * 70)
            log.error("🛑 5ERS STOP-OUT TRIGGERED!")
            log.error(f"  Equity: ${equity:,.2f}")
            log.error(f"  Stop-out level: ${status['stop_out_level']:,.2f}")
            log.error("  Total DD = 10% from start balance - ACCOUNT BREACHED")
            log.error("  CLOSING ALL POSITIONS!")
            log.error("=" * 70)
            
            # Close all positions
            positions = self.mt5.get_my_positions()
            for pos in positions:
                result = self.mt5.close_position(pos.ticket)
                if result.success:
                    log.info(f"  ✓ Closed {pos.symbol}")
                else:
                    log.error(f"  ✗ Failed to close {pos.symbol}: {result.error}")
            
            return True  # Stop-out triggered
        
        return False

    def _load_pending_setups(self):
        """Load pending setups from file."""
        try:
            if Path(self.PENDING_SETUPS_FILE).exists():
                with open(self.PENDING_SETUPS_FILE, 'r') as f:
                    data = json.load(f)
                for symbol, setup_dict in data.items():
                    self.pending_setups[symbol] = PendingSetup.from_dict(setup_dict)
                log.info(f"Loaded {len(self.pending_setups)} pending setups from file")
        except Exception as e:
            log.error(f"Error loading pending setups: {e}")
            self.pending_setups = {}
    
    def _save_pending_setups(self):
        """Save pending setups to file."""
        try:
            data = {symbol: setup.to_dict() for symbol, setup in self.pending_setups.items()}
            with open(self.PENDING_SETUPS_FILE, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Error saving pending setups: {e}")
    
    def _load_trading_days(self):
        """Load trading days from file for FTMO minimum trading days tracking."""
        try:
            if Path(self.TRADING_DAYS_FILE).exists():
                with open(self.TRADING_DAYS_FILE, 'r') as f:
                    data = json.load(f)
                self.trading_days = set(data.get("trading_days", []))
                start_date_str = data.get("challenge_start_date")
                end_date_str = data.get("challenge_end_date")
                if start_date_str:
                    normalized = start_date_str.replace("Z", "+00:00")
                    self.challenge_start_date = datetime.fromisoformat(normalized)
                if end_date_str:
                    normalized = end_date_str.replace("Z", "+00:00")
                    self.challenge_end_date = datetime.fromisoformat(normalized)
                log.info(f"Loaded {len(self.trading_days)} trading days from file")
        except Exception as e:
            log.error(f"Error loading trading days: {e}")
            self.trading_days = set()
    
    def start_new_challenge(self, duration_days: int = 30):
        """
        Start a new challenge period with fresh trading days tracking.
        Call this when starting Phase 1, Phase 2, or resetting the challenge.
        """
        self.trading_days = set()
        self.challenge_start_date = datetime.now(timezone.utc)
        self.challenge_end_date = self.challenge_start_date + timedelta(days=duration_days)
        self._save_trading_days()
        log.info(f"New challenge started: {self.challenge_start_date.date()} to {self.challenge_end_date.date()} ({duration_days} days)")
    
    def _save_trading_days(self):
        """Save trading days to file."""
        try:
            data = {
                "trading_days": list(self.trading_days),
                "challenge_start_date": self.challenge_start_date.isoformat() if self.challenge_start_date else None,
                "challenge_end_date": self.challenge_end_date.isoformat() if self.challenge_end_date else None,
            }
            with open(self.TRADING_DAYS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Error saving trading days: {e}")
    
    def record_trading_day(self):
        """
        Record today as a trading day when a trade is executed.
        Called after successful order placement/fill.
        """
        from ftmo_config import FIVEERS_CONFIG
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today not in self.trading_days:
            self.trading_days.add(today)
            self._save_trading_days()
            log.info(f"Recorded trading day: {today} (Total: {len(self.trading_days)}/{FIVEERS_CONFIG.min_profitable_days} required)")
    
    def check_trading_days_warning(self) -> bool:
        """
        Check if we're at risk of not meeting minimum trading days requirement.
        Returns True if warning should be shown (not enough days traded relative to time remaining).
        """
        from ftmo_config import FIVEERS_CONFIG
        
        if self.challenge_end_date is None:
            return False
        
        now = datetime.now(timezone.utc)
        days_remaining = (self.challenge_end_date - now).days
        trading_days_count = len(self.trading_days)
        days_needed = FIVEERS_CONFIG.min_profitable_days - trading_days_count
        
        if days_needed <= 0:
            return False
        
        if days_remaining <= days_needed + 2:
            log.warning(f"TRADING DAYS WARNING: {trading_days_count}/{FIVEERS_CONFIG.min_profitable_days} days traded, "
                       f"{days_remaining} days remaining in challenge. Need {days_needed} more trading days!")
            return True
        
        return False
    
    def get_trading_days_status(self) -> Dict:
        """Get current trading days status for reporting."""
        from ftmo_config import FIVEERS_CONFIG
        
        trading_days_count = len(self.trading_days)
        days_needed = max(0, FIVEERS_CONFIG.min_profitable_days - trading_days_count)
        
        status = {
            "trading_days_count": trading_days_count,
            "min_required": FIVEERS_CONFIG.min_profitable_days,
            "days_needed": days_needed,
            "trading_days": sorted(list(self.trading_days)),
            "requirement_met": trading_days_count >= FIVEERS_CONFIG.min_profitable_days,
        }
        
        if self.challenge_end_date:
            now = datetime.now(timezone.utc)
            status["days_remaining"] = max(0, (self.challenge_end_date - now).days)
        
        return status
    
    def _auto_start_challenge(self):
        """Auto-start challenge if not already active."""
        if not self.risk_manager.state.live_flag:
            log.info("Challenge not active - auto-starting Phase 1...")
            self.risk_manager.start_challenge(phase=1)
            if self.challenge_start_date is None:
                self.start_new_challenge(duration_days=30)
            log.info("Challenge auto-started! Trading is now enabled.")
        else:
            phase = self.risk_manager.state.phase
            log.info(f"Challenge already active (Phase {phase}) - continuing...")
    
    def connect(self) -> bool:
        """Connect to MT5."""
        log.info("=" * 70)
        log.info("CONNECTING TO MT5")
        log.info("=" * 70)
        
        if not self.mt5.connect():
            log.error("Failed to connect to MT5")
            return False
        
        account = self.mt5.get_account_info()
        log.info(f"Connected: {account.get('login')} @ {account.get('server')}")
        log.info(f"Balance: ${account.get('balance', 0):,.2f}")
        log.info(f"Equity: ${account.get('equity', 0):,.2f}")
        log.info(f"Leverage: 1:{account.get('leverage', 0)}")
        
        # Discover available symbols
        log.info("\n" + "=" * 70)
        log.info(f"DISCOVERING BROKER SYMBOLS ({BROKER_NAME})")
        log.info("=" * 70)
        
        available_symbols = self.mt5.get_available_symbols()
        log.info(f"Broker has {len(available_symbols)} total symbols")
        
        # Get broker type for symbol mapping
        broker_type = BROKER_CONFIG.broker_type.value
        
        # Map our symbols to broker symbols
        # TRADABLE_SYMBOLS uses OANDA format (EUR_USD), broker uses specific format
        mapped_count = 0
        self.symbol_map = {}
        
        for our_symbol in TRADABLE_SYMBOLS:
            # Use broker-aware symbol mapping
            broker_symbol = get_broker_symbol(our_symbol, broker_type)
            
            # First try the mapped symbol
            if self.mt5.get_symbol_info(broker_symbol):
                self.symbol_map[our_symbol] = broker_symbol
                mapped_count += 1
                log.info(f"✓ {our_symbol:15s} -> {broker_symbol}")
            else:
                # Try to find a match in available symbols
                found_symbol = self.mt5.find_symbol_match(our_symbol)
                if found_symbol:
                    self.symbol_map[our_symbol] = found_symbol
                    mapped_count += 1
                    log.info(f"✓ {our_symbol:15s} -> {found_symbol} (auto-detected)")
                else:
                    log.warning(f"✗ {our_symbol:15s} -> NOT FOUND (expected: {broker_symbol})")
        
        log.info("=" * 70)
        log.info(f"Mapped {mapped_count}/{len(TRADABLE_SYMBOLS)} symbols")
        log.info("=" * 70)
        
        if mapped_count == 0:
            log.error("No symbols could be mapped! Check broker symbol naming.")
            return False
        
        # Validate symbol mapping integrity
        log.info("\n" + "=" * 70)
        log.info("VALIDATING SYMBOL MAPPING")
        log.info("=" * 70)
        sample_symbols = list(self.symbol_map.items())[:5]
        for oanda_sym, broker_sym in sample_symbols:
            # Test that we can get symbol info
            info = self.mt5.get_symbol_info(broker_sym)
            if info:
                log.info(f"✓ {oanda_sym} -> {broker_sym} (digits: {info.get('digits')}, spread: {info.get('spread')})")
            else:
                log.error(f"✗ {oanda_sym} -> {broker_sym} FAILED to get symbol info")
        log.info("=" * 70)
        
        balance = account.get('balance', 0)
        equity = account.get('equity', 0)
        if balance > 0:
            log.info("Syncing risk manager with MT5 account...")
            self.risk_manager.sync_from_mt5(balance, equity)
            log.info(f"Risk manager synced: Balance=${balance:,.2f}, Equity=${equity:,.2f}")
            
            if CHALLENGE_MODE:
                from ftmo_config import FIVEERS_CONFIG
                log.info("Initializing Challenge Risk Manager (5ers 60K COMPLIANT)...")
                config = ChallengeConfig(
                    enabled=True,
                    phase=self.risk_manager.state.phase,
                    account_size=balance,
                    max_risk_per_trade_pct=FIVEERS_CONFIG.risk_per_trade_pct,
                    max_cumulative_risk_pct=FIVEERS_CONFIG.max_cumulative_risk_pct,
                    max_concurrent_trades=FIVEERS_CONFIG.max_concurrent_trades,
                    max_pending_orders=FIVEERS_CONFIG.max_pending_orders,
                    # ALIGNED: Use tp_close_pct from current_params.json (self.params)
                    tp1_close_pct=self.params.tp1_close_pct,
                    tp2_close_pct=self.params.tp2_close_pct,
                    tp3_close_pct=self.params.tp3_close_pct,
                    daily_loss_warning_pct=FIVEERS_CONFIG.daily_loss_warning_pct,
                    daily_loss_reduce_pct=FIVEERS_CONFIG.daily_loss_reduce_pct,
                    daily_loss_halt_pct=FIVEERS_CONFIG.daily_loss_halt_pct,
                    total_dd_warning_pct=FIVEERS_CONFIG.total_dd_warning_pct,
                    total_dd_emergency_pct=FIVEERS_CONFIG.total_dd_emergency_pct,
                    protection_loop_interval_sec=FIVEERS_CONFIG.protection_loop_interval_sec,
                    pending_order_max_age_hours=FIVEERS_CONFIG.pending_order_expiry_hours,
                    profit_ultra_safe_threshold_pct=FIVEERS_CONFIG.profit_ultra_safe_threshold_pct,
                    ultra_safe_risk_pct=FIVEERS_CONFIG.ultra_safe_risk_pct,
                )
                self.challenge_manager = ChallengeRiskManager(
                    config=config,
                    mt5_client=self.mt5,
                    state_file="challenge_risk_state.json",
                    trading_days_file=self.TRADING_DAYS_FILE,
                )
                self.challenge_manager.sync_with_mt5(balance, equity)
                log.info("Challenge Risk Manager initialized with ELITE PROTECTION")
        
        # CRITICAL: Sync pending_setups and queues with actual MT5 state
        self._startup_sync_with_mt5()
        
        return True
    
    def _startup_sync_with_mt5(self):
        """
        CRITICAL STARTUP SYNC: Validate all pending_setups and queues against MT5 reality.
        
        This prevents:
        1. Orphaned pending_setups blocking new signals
        2. Stale queue entries after bot restart
        3. Mismatch between JSON state and actual MT5 positions/orders
        
        Called immediately after connect() to ensure clean state.
        """
        log.info("=" * 70)
        log.info("🔄 STARTUP SYNC - Validating state against MT5")
        log.info("=" * 70)
        
        # Get actual MT5 state
        my_positions = self.mt5.get_my_positions()
        my_pending_orders = self.mt5.get_my_pending_orders()
        
        position_symbols = {p.symbol for p in my_positions}
        pending_order_tickets = {o.ticket for o in my_pending_orders}
        
        log.info(f"MT5 Reality: {len(my_positions)} positions, {len(my_pending_orders)} pending orders")
        log.info(f"Loaded State: {len(self.pending_setups)} pending_setups, {len(self.awaiting_entry)} awaiting_entry, {len(self.awaiting_spread)} awaiting_spread")
        
        # 1. Clean up pending_setups that no longer exist in MT5
        orphaned_setups = []
        for symbol, setup in list(self.pending_setups.items()):
            broker_symbol = self.symbol_map.get(symbol, symbol)
            
            if setup.status == "pending":
                # Check if pending order still exists
                if setup.order_ticket and setup.order_ticket not in pending_order_tickets:
                    log.warning(f"[{symbol}] Orphaned pending setup (order {setup.order_ticket} not in MT5) - removing")
                    orphaned_setups.append(symbol)
            
            elif setup.status == "filled":
                # Check if position still exists
                if broker_symbol not in position_symbols:
                    log.warning(f"[{symbol}] Orphaned filled setup (position not in MT5) - removing")
                    orphaned_setups.append(symbol)
            
            elif setup.status == "halted":
                # Halted setups from DDD halt - check if new day
                # If same day as halt, keep blocking. If new day, remove.
                if setup.created_at:
                    try:
                        created_date = datetime.fromisoformat(setup.created_at.replace("Z", "+00:00")).date()
                        today = datetime.now(timezone.utc).date()
                        if created_date < today:
                            log.info(f"[{symbol}] Halted setup from {created_date} - new day, removing block")
                            orphaned_setups.append(symbol)
                        else:
                            log.info(f"[{symbol}] Halted setup from today - keeping block")
                    except Exception:
                        orphaned_setups.append(symbol)
        
        for symbol in orphaned_setups:
            del self.pending_setups[symbol]
        
        if orphaned_setups:
            self._save_pending_setups()
            log.info(f"Cleaned up {len(orphaned_setups)} orphaned setups")
        
        # 2. Clean up expired signals in awaiting_entry
        now = datetime.now(timezone.utc)
        expired_entry = []
        for symbol, setup in list(self.awaiting_entry.items()):
            created_at_str = setup.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    age_hours = (now - created_at).total_seconds() / 3600
                    if age_hours > self.MAX_ENTRY_WAIT_HOURS:
                        log.warning(f"[{symbol}] Entry signal expired ({age_hours:.1f}h old) - removing")
                        expired_entry.append(symbol)
                except Exception:
                    pass
        
        for symbol in expired_entry:
            del self.awaiting_entry[symbol]
        
        if expired_entry:
            self._save_awaiting_entry()
            log.info(f"Cleaned up {len(expired_entry)} expired entry signals")
        
        # 3. Clean up expired signals in awaiting_spread
        expired_spread = []
        for symbol, setup in list(self.awaiting_spread.items()):
            created_at_str = setup.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    age_hours = (now - created_at).total_seconds() / 3600
                    if age_hours > self.MAX_SPREAD_WAIT_HOURS:
                        log.warning(f"[{symbol}] Spread signal expired ({age_hours:.1f}h old) - removing")
                        expired_spread.append(symbol)
                except Exception:
                    pass
        
        for symbol in expired_spread:
            del self.awaiting_spread[symbol]
        
        if expired_spread:
            self._save_awaiting_spread()
            log.info(f"Cleaned up {len(expired_spread)} expired spread signals")
        
        # 4. Log final state
        log.info("=" * 70)
        log.info(f"✅ STARTUP SYNC COMPLETE")
        log.info(f"  Active pending_setups: {len(self.pending_setups)}")
        log.info(f"  Active awaiting_entry: {len(self.awaiting_entry)}")
        log.info(f"  Active awaiting_spread: {len(self.awaiting_spread)}")
        log.info("=" * 70)
    
    def disconnect(self):
        """Disconnect from MT5."""
        self.mt5.disconnect()
        log.info("Disconnected from MT5")
    
    def get_candle_data(self, symbol: str) -> Dict[str, List[Dict]]:
        """
        Get multi-timeframe candle data for a symbol.
        Same timeframes used in backtests for parity.
        """
        # Use broker symbol format
        broker_symbol = self.symbol_map.get(symbol, symbol)
        
        data = {
            "monthly": self.mt5.get_ohlcv(broker_symbol, "MN1", 24),
            "weekly": self.mt5.get_ohlcv(broker_symbol, "W1", 104),
            "daily": self.mt5.get_ohlcv(broker_symbol, "D1", 500),
            "h4": self.mt5.get_ohlcv(broker_symbol, "H4", 500),
        }
        return data
    
    def check_existing_position(self, symbol: str) -> bool:
        """Check if we already have a position on this symbol."""
        # symbol is in OANDA format, convert to broker format for checking
        broker_symbol = self.symbol_map.get(symbol, symbol)
        positions = self.mt5.get_my_positions()
        for pos in positions:
            if pos.symbol == broker_symbol:
                return True
        return False
    
    def _get_dynamic_pip_value(self, symbol: str, broker_symbol: str) -> float:
        """
        Get pip value using MT5's tick_value (most accurate source).
        
        MT5's trade_tick_value gives the profit/loss per tick movement per lot
        in account currency (USD). This is the ONLY 100% reliable source.
        
        Fallback: Calculate based on exchange rates if MT5 doesn't provide it.
        
        Returns:
            Pip value per standard lot in USD (always > 0)
        """
        from tradr.brokers.fiveers_specs import get_fiveers_contract_specs
        
        # Get fallback specs first (always needed)
        try:
            specs = get_fiveers_contract_specs(symbol)
        except Exception:
            specs = {"pip_size": 0.0001, "pip_value_per_lot": 10.0}
        
        base_pip_value = specs.get("pip_value_per_lot", 10.0)
        pip_size = specs.get("pip_size", 0.0001)
        
        # Ensure we always return a valid positive value
        if base_pip_value <= 0:
            base_pip_value = 10.0
        if pip_size <= 0:
            pip_size = 0.0001
        
        # FIRST: Try to get tick_value directly from MT5 (most reliable!)
        try:
            symbol_info = self.mt5.get_symbol_info(broker_symbol)
            if symbol_info:
                tick_value = symbol_info.get("tick_value", 0)
                tick_size = symbol_info.get("tick_size", 0)
                
                # Only use MT5 values if they are valid positive numbers
                if tick_value and tick_value > 0 and tick_size and tick_size > 0:
                    # Calculate pip value from tick value
                    # pip_value = tick_value * (pip_size / tick_size)
                    pip_value = tick_value * (pip_size / tick_size)
                    
                    # Sanity check - pip value should be reasonable
                    if pip_value > 0 and pip_value < 10000:
                        log.info(f"[{symbol}] MT5 tick_value=${tick_value:.4f}/tick, tick_size={tick_size}, pip_size={pip_size} -> pip_value=${pip_value:.4f}/pip")
                        return pip_value
                    else:
                        log.warning(f"[{symbol}] MT5 pip_value ${pip_value:.4f} seems invalid, using fallback")
        except Exception as e:
            log.warning(f"[{symbol}] Error getting MT5 tick_value: {e}")
        
        # FALLBACK: Calculate based on exchange rates
        log.debug(f"[{symbol}] Using exchange rate calculation for pip value")
        
        # Normalize symbol
        sym_upper = symbol.upper().replace("_", "")
        
        # UK100 is GBP-denominated
        if "UK100" in sym_upper or "FTSE" in sym_upper:
            try:
                gbpusd_tick = self.mt5.get_tick("GBPUSD")
                if gbpusd_tick and gbpusd_tick.bid > 0:
                    gbpusd_rate = (gbpusd_tick.bid + gbpusd_tick.ask) / 2
                    pip_value = 1.0 * gbpusd_rate
                    log.debug(f"[{symbol}] Fallback pip value: £1 × GBPUSD({gbpusd_rate:.4f}) = ${pip_value:.4f}/point")
                    return pip_value
            except Exception:
                pass
            return 1.40  # Safe estimate
        
        # US indices - already in USD
        if any(x in sym_upper for x in ["NAS100", "SPX500", "SP500", "US100", "US500", "US30"]):
            return base_pip_value
        
        # Metals and Crypto - already in USD
        if any(x in sym_upper for x in ["XAU", "XAG", "BTC", "ETH"]):
            return base_pip_value
        
        # FOREX - check quote currency
        if len(sym_upper) >= 6:
            quote_currency = sym_upper[-3:]
            
            if quote_currency == "USD":
                return 10.0
            
            try:
                if quote_currency == "JPY":
                    usdjpy_tick = self.mt5.get_tick("USDJPY")
                    if usdjpy_tick and usdjpy_tick.bid > 0:
                        usdjpy_rate = (usdjpy_tick.bid + usdjpy_tick.ask) / 2
                        if usdjpy_rate > 0:
                            return 1000.0 / usdjpy_rate
                    return 6.67
                
                if quote_currency == "CHF":
                    usdchf_tick = self.mt5.get_tick("USDCHF")
                    if usdchf_tick and usdchf_tick.bid > 0:
                        usdchf_rate = (usdchf_tick.bid + usdchf_tick.ask) / 2
                        if usdchf_rate > 0:
                            return 10.0 / usdchf_rate
                    return 11.0
                
                if quote_currency == "CAD":
                    usdcad_tick = self.mt5.get_tick("USDCAD")
                    if usdcad_tick and usdcad_tick.bid > 0:
                        usdcad_rate = (usdcad_tick.bid + usdcad_tick.ask) / 2
                        if usdcad_rate > 0:
                            return 10.0 / usdcad_rate
                    return 7.5
                
                if quote_currency == "GBP":
                    gbpusd_tick = self.mt5.get_tick("GBPUSD")
                    if gbpusd_tick and gbpusd_tick.bid > 0:
                        gbpusd_rate = (gbpusd_tick.bid + gbpusd_tick.ask) / 2
                        return 10.0 * gbpusd_rate
                    return 12.5
                
                if quote_currency == "AUD":
                    audusd_tick = self.mt5.get_tick("AUDUSD")
                    if audusd_tick and audusd_tick.bid > 0:
                        audusd_rate = (audusd_tick.bid + audusd_tick.ask) / 2
                        return 10.0 * audusd_rate
                    return 6.5
                
                if quote_currency == "NZD":
                    nzdusd_tick = self.mt5.get_tick("NZDUSD")
                    if nzdusd_tick and nzdusd_tick.bid > 0:
                        nzdusd_rate = (nzdusd_tick.bid + nzdusd_tick.ask) / 2
                        return 10.0 * nzdusd_rate
                    return 6.0
            except Exception as e:
                log.warning(f"[{symbol}] Error calculating pip value for {quote_currency}: {e}")
        
        # Final fallback - always return a valid positive value
        log.debug(f"[{symbol}] Using base pip value: ${base_pip_value:.2f}")
        return base_pip_value
    
    def _calculate_lot_size_at_fill(
        self,
        symbol: str,
        broker_symbol: str,
        entry: float,
        sl: float,
        confluence: int,
    ) -> float:
        """
        BUGFIX P0: Calculate lot size at FILL MOMENT (not signal moment).

        This ensures:
        1. Lot size uses CURRENT balance (proper compounding)
        2. DDD/TDD checks use current equity
        3. Risk percentage reflects current account state

        IMPORTANT: NO position count reduction - must match simulate_main_live_bot.py
        The simulator uses fixed 0.6% risk per trade regardless of position count.

        Args:
            symbol: OANDA format symbol
            broker_symbol: Broker format symbol
            entry: Entry price
            sl: Stop loss price
            confluence: Confluence score

        Returns:
            Lot size (float), or 0.0 if cannot calculate
        """
        from tradr.risk.position_sizing import calculate_lot_size
        from ftmo_config import FIVEERS_CONFIG
        
        if not CHALLENGE_MODE or not self.challenge_manager:
            log.error(f"[{symbol}] Cannot calculate lot size - challenge manager not available")
            return 0.0

        # Get CURRENT account snapshot (not stale snapshot from signal moment)
        snapshot = self.challenge_manager.get_account_snapshot()
        if snapshot is None:
            log.error(f"[{symbol}] Cannot get account snapshot")
            return 0.0

        # Always use fixed day_start_equity and starting_balance from JSON (not updated during the day)
        day_start_equity = self.challenge_manager.day_start_equity
        starting_balance = self.challenge_manager.initial_balance
        current_equity = snapshot.equity
        current_balance = snapshot.balance

        # Calculate DDD and TDD using fixed values
        daily_pnl = current_equity - day_start_equity
        daily_loss_pct = abs(min(0, daily_pnl)) / day_start_equity * 100 if day_start_equity > 0 else 0
        total_dd_pct = (starting_balance - current_equity) / starting_balance * 100 if starting_balance > 0 and current_equity < starting_balance else 0
        profit_pct = (current_equity - starting_balance) / starting_balance * 100 if starting_balance > 0 else 0

        log.info(f"[{symbol}] DDD/TDD check at fill: day_start_equity=${day_start_equity:.2f}, starting_balance=${starting_balance:.2f}, current_equity=${current_equity:.2f}, daily_loss_pct={daily_loss_pct:.2f}%, total_dd_pct={total_dd_pct:.2f}%")

        # Check if trading is halted
        if daily_loss_pct >= FIVEERS_CONFIG.daily_loss_halt_pct:
            log.warning(f"[{symbol}] Trading halted: daily loss {daily_loss_pct:.1f}% >= {FIVEERS_CONFIG.daily_loss_halt_pct}% (NO TRADE)")
            return 0.0

        if total_dd_pct >= FIVEERS_CONFIG.total_dd_emergency_pct:
            log.warning(f"[{symbol}] Trading halted: total DD {total_dd_pct:.1f}% >= {FIVEERS_CONFIG.total_dd_emergency_pct}% (NO TRADE)")
            return 0.0

        # Get win/loss streaks
        win_streak = getattr(self.risk_manager.state, 'win_streak', 0) if hasattr(self.risk_manager, 'state') else 0
        loss_streak = getattr(self.risk_manager.state, 'loss_streak', 0) if hasattr(self.risk_manager, 'state') else 0

        # Calculate risk percentage (dynamic or static)
        if FIVEERS_CONFIG.use_dynamic_lot_sizing:
            risk_pct = FIVEERS_CONFIG.get_dynamic_risk_pct(
                confluence_score=confluence,
                win_streak=win_streak,
                loss_streak=loss_streak,
                current_profit_pct=profit_pct,
                daily_loss_pct=daily_loss_pct,
                total_dd_pct=total_dd_pct,
            )
            log.info(f"[{symbol}] Dynamic risk: {risk_pct:.3f}% (confluence: {confluence}, streaks: +{win_streak}/-{loss_streak})")
        else:
            risk_pct = FIVEERS_CONFIG.get_risk_pct(daily_loss_pct, total_dd_pct)

        if risk_pct <= 0:
            log.warning(f"[{symbol}] Risk percentage is 0 - trading halted (NO TRADE)")
            return 0.0

        # Get symbol info
        symbol_info = self.mt5.get_symbol_info(broker_symbol)
        max_lot = symbol_info.get('max_lot', 100.0) if symbol_info else 100.0
        min_lot = symbol_info.get('min_lot', 0.01) if symbol_info else 0.01

        # Ensure min_lot and max_lot are valid
        if min_lot <= 0:
            min_lot = 0.01
        if max_lot <= 0:
            max_lot = 100.0

        # Get DYNAMIC pip value based on current exchange rates
        try:
            dynamic_pip_value = self._get_dynamic_pip_value(symbol, broker_symbol)
        except Exception as e:
            log.error(f"[{symbol}] Error getting dynamic pip value: {e}, using fallback $10/pip")
            dynamic_pip_value = 10.0
        
        # Sanity check pip value
        if dynamic_pip_value <= 0:
            log.warning(f"[{symbol}] Invalid pip value {dynamic_pip_value}, using $10/pip")
            dynamic_pip_value = 10.0
        
        log.info(f"[{symbol}] Dynamic pip value: ${dynamic_pip_value:.4f}/pip")

        # Calculate lot size using CURRENT balance
        # IMPORTANT: NO position count reduction - must match simulate_main_live_bot.py
        try:
            lot_result = calculate_lot_size(
                symbol=broker_symbol,
                account_balance=current_balance,  # CURRENT balance!
                risk_percent=risk_pct / 100,
                entry_price=entry,
                stop_loss_price=sl,
                max_lot=max_lot,
                min_lot=min_lot,
                broker="5ers",  # CRITICAL: Use 5ers contract specs
                pip_value_override=dynamic_pip_value,  # Use dynamic pip value!
            )
        except Exception as e:
            log.error(f"[{symbol}] Error calculating lot size: {e}")
            return 0.0

        if lot_result.get("error"):
            log.warning(f"[{symbol}] Cannot calculate lot size: {lot_result.get('error')} (NO TRADE)")
            return 0.0

        lot_size = lot_result.get("lot_size", 0.0)
        risk_usd = lot_result.get("risk_usd", 0.0)
        risk_pips = lot_result.get("stop_pips", 0.0)

        # Validate lot size
        if lot_size <= 0 or lot_size < min_lot:
            log.warning(f"[{symbol}] Lot size {lot_size} too small (min: {min_lot}) (NO TRADE)")
            return 0.0

        # Round to lot step
        if symbol_info:
            lot_step = symbol_info.get('lot_step', 0.01)
            if lot_step > 0:
                lot_size = max(min_lot, round(lot_size / lot_step) * lot_step)
            lot_size = min(lot_size, max_lot)

        log.info(f"[{symbol}] Lot size calculated at FILL MOMENT:")
        log.info(f"  Balance: ${current_balance:.2f}")
        log.info(f"  Risk %: {risk_pct:.2f}% (daily loss: {daily_loss_pct:.1f}%, DD: {total_dd_pct:.1f}%)")
        log.info(f"  Risk $: ${risk_usd:.2f}")
        log.info(f"  Stop pips: {risk_pips:.1f}")
        log.info(f"  Lot size: {lot_size}")

        return lot_size
    
    def _calculate_atr(self, candles: List[Dict], period: int = 14) -> float:
        """
        Calculate Average True Range from candles.
        
        Args:
            candles: List of candle dicts with 'high', 'low', 'close' keys
            period: ATR period (default 14)
            
        Returns:
            ATR value, or 0.0 if insufficient data
        """
        if len(candles) < period + 1:
            return 0.0
        
        true_ranges = []
        for i in range(1, len(candles)):
            high = candles[i].get("high", 0)
            low = candles[i].get("low", 0)
            prev_close = candles[i-1].get("close", 0)
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        if len(true_ranges) < period:
            return 0.0
        
        return sum(true_ranges[-period:]) / period
    
    def scan_symbol(self, symbol: str) -> Optional[Dict]:
        """
        Scan a single symbol for trade setup.
        
        SYMBOL FORMAT:
        - Input symbol: OANDA format (e.g., EUR_USD, XAU_USD, SPX500_USD)
        - Broker symbol: FTMO MT5 format (e.g., EURUSD, XAUUSD, US500.cash)
        - Data fetching: Uses broker symbol for MT5 candles
        - Trading: Uses broker symbol for orders
        
        MATCHES BACKTEST LOGIC EXACTLY:
        1. Get HTF trends (M/W/D)
        2. Pick direction from bias
        3. Compute confluence flags
        4. Check for active setup
        5. Validate entry is reachable from current price
        6. Validate SL is appropriate
        
        Returns trade setup dict if signal is active AND tradeable, None otherwise.
        """
        from ftmo_config import FIVEERS_CONFIG, get_pip_size, get_sl_limits
        
        if symbol not in self.symbol_map:
            log.debug(f"[{symbol}] Not available on this broker, skipping")
            return None
        
        broker_symbol = self.symbol_map[symbol]
        log.info(f"[{symbol}] Scanning (OANDA: {symbol}, FTMO: {broker_symbol})...")
        
        if self.check_existing_position(broker_symbol):
            log.info(f"[{symbol}] Already in position, skipping")
            return None
        
        # BUGFIX: Block ALL existing setups, not just "pending" status
        # Also block "halted" setups to prevent re-entry after DDD halt
        if symbol in self.pending_setups:
            existing = self.pending_setups[symbol]
            if existing.status in ("pending", "filled", "halted"):
                log.info(f"[{symbol}] Already have {existing.status} setup, skipping")
                return None
        
        data = self.get_candle_data(symbol)
        
        if not data["daily"] or len(data["daily"]) < 50:
            log.warning(f"[{symbol}] Insufficient daily data ({len(data.get('daily', []))} candles)")
            return None
        
        if not data["weekly"] or len(data["weekly"]) < 10:
            log.warning(f"[{symbol}] Insufficient weekly data")
            return None
        
        monthly_candles = data["monthly"] if data["monthly"] else []
        weekly_candles = data["weekly"]
        daily_candles = data["daily"]
        h4_candles = data["h4"] if data["h4"] else daily_candles[-20:]
        
        mn_trend = _infer_trend(monthly_candles) if monthly_candles else "mixed"
        wk_trend = _infer_trend(weekly_candles) if weekly_candles else "mixed"
        d_trend = _infer_trend(daily_candles) if daily_candles else "mixed"
        
        direction, _, _ = _pick_direction_from_bias(mn_trend, wk_trend, d_trend)
        
        historical_sr = get_all_htf_sr_levels(symbol) if HISTORICAL_SR_AVAILABLE else None
        
        flags, notes, trade_levels = compute_confluence(
            monthly_candles,
            weekly_candles,
            daily_candles,
            h4_candles,
            direction,
            self.params,
            historical_sr,
        )
        
        # compute_confluence returns 5 TP levels; unpack all to avoid tuple mismatch errors
        entry, sl, tp1, tp2, tp3, tp4, tp5 = trade_levels
        
        confluence_score = sum(1 for v in flags.values() if v)
        
        has_confirmation = flags.get("confirmation", False)
        has_rr = flags.get("rr", False)
        has_location = flags.get("location", False)
        has_fib = flags.get("fib", False)
        has_liquidity = flags.get("liquidity", False)
        has_structure = flags.get("structure", False)
        has_htf_bias = flags.get("htf_bias", False)
        
        # EXACT same quality factor calculation as backtest_live_bot.py
        quality_factors = sum([has_location, has_fib, has_liquidity, has_structure, has_htf_bias])
        
        # BUGFIX: Removed has_rr gate - it was preventing all trades from being active
        # If confluence and quality are sufficient, R:R is implicitly validated
        if confluence_score >= MIN_CONFLUENCE and quality_factors >= FIVEERS_CONFIG.min_quality_factors:
            status = "active"
        elif confluence_score >= MIN_CONFLUENCE:
            status = "watching"
        else:
            status = "scan_only"
        
        log.info(f"[{symbol}] {direction.upper()} | Conf: {confluence_score}/7 | Quality: {quality_factors} | Status: {status}")
        
        for pillar, is_met in flags.items():
            marker = "✓" if is_met else "✗"
            note = notes.get(pillar, "")[:50]
            log.debug(f"  [{marker}] {pillar}: {note}")
        
        if status != "active":
            return None
        
        if entry is None or sl is None or tp1 is None:
            log.warning(f"[{symbol}] Missing entry/SL/TP levels")
            return None
        
        risk = abs(entry - sl)
        if risk <= 0:
            log.warning(f"[{symbol}] Invalid risk: entry={entry:.5f}, sl={sl:.5f}")
            return None
        
        tick = self.mt5.get_tick(broker_symbol)
        if tick is None:
            log.warning(f"[{symbol}] Cannot get current tick price")
            return None
        
        current_price = tick.bid if direction == "bullish" else tick.ask
        
        entry_distance = abs(current_price - entry)
        entry_distance_r = entry_distance / risk
        
        if entry_distance_r > FIVEERS_CONFIG.max_entry_distance_r:
            log.info(f"[{symbol}] Entry too far: {entry:.5f} is {entry_distance_r:.2f}R from current {current_price:.5f} (max: {FIVEERS_CONFIG.max_entry_distance_r}R)")
            return None
        
        log.info(f"[{symbol}] Entry proximity OK: {entry_distance_r:.2f}R from current price")
        
        # SL validation with asset-specific limits
        pip_size = get_pip_size(symbol)
        sl_pips = abs(entry - sl) / pip_size
        min_sl_pips, max_sl_pips = get_sl_limits(symbol)
        
        # Min SL check - adjust if needed
        if sl_pips < min_sl_pips:
            log.info(f"[{symbol}] SL too tight: {sl_pips:.1f} pips (min: {min_sl_pips})")
            if direction == "bullish":
                sl = entry - (min_sl_pips * pip_size)
            else:
                sl = entry + (min_sl_pips * pip_size)
            risk = abs(entry - sl)
            sl_pips = min_sl_pips
            log.info(f"[{symbol}] SL adjusted to minimum: {sl:.5f} ({sl_pips:.1f} pips)")
        
        # ATR-based SL validation (same as backtest)
        atr = self._calculate_atr(daily_candles, period=14)
        if atr > 0:
            sl_atr_ratio = abs(entry - sl) / atr
            
            if sl_atr_ratio < FIVEERS_CONFIG.min_sl_atr_ratio:
                log.info(f"[{symbol}] SL too tight in ATR terms: {sl_atr_ratio:.2f} ATR (min: {FIVEERS_CONFIG.min_sl_atr_ratio})")
                if direction == "bullish":
                    sl = entry - (atr * FIVEERS_CONFIG.min_sl_atr_ratio)
                else:
                    sl = entry + (atr * FIVEERS_CONFIG.min_sl_atr_ratio)
                risk = abs(entry - sl)
                log.info(f"[{symbol}] SL adjusted to {FIVEERS_CONFIG.min_sl_atr_ratio} ATR: {sl:.5f}")
            
        # ════════════════════════════════════════════════════════════════════════
        # 3-TP SYSTEM: Use tp*_r_multiple from current_params.json
        # ALIGNED WITH SIMULATOR - uses tp1_r_multiple, tp2_r_multiple, tp3_r_multiple
        # TP3 closes ALL remaining position (same as simulator)
        # ════════════════════════════════════════════════════════════════════════
        risk = abs(entry - sl)
        if direction == "bullish":
            tp1 = entry + (risk * self.params.tp1_r_multiple)
            tp2 = entry + (risk * self.params.tp2_r_multiple)
            tp3 = entry + (risk * self.params.tp3_r_multiple)
        else:
            tp1 = entry - (risk * self.params.tp1_r_multiple)
            tp2 = entry - (risk * self.params.tp2_r_multiple)
            tp3 = entry - (risk * self.params.tp3_r_multiple)
        
        if direction == "bullish":
            if current_price <= sl:
                log.warning(f"[{symbol}] Current price {current_price:.5f} already below SL {sl:.5f} - skipping")
                return None
        else:
            if current_price >= sl:
                log.warning(f"[{symbol}] Current price {current_price:.5f} already above SL {sl:.5f} - skipping")
                return None
        
        log.info(f"[{symbol}] ✓ ACTIVE SIGNAL VALIDATED!")
        log.info(f"  Direction: {direction.upper()}")
        log.info(f"  Confluence: {confluence_score}/7")
        log.info(f"  Current Price: {current_price:.5f}")
        log.info(f"  Entry: {entry:.5f} ({entry_distance_r:.2f}R away)")
        log.info(f"  SL: {sl:.5f} ({sl_pips:.1f} pips)")
        log.info(f"  TP1: {tp1:.5f} ({self.params.tp1_r_multiple}R) -> {self.params.tp1_close_pct*100:.0f}%")
        log.info(f"  TP2: {tp2:.5f} ({self.params.tp2_r_multiple}R) -> {self.params.tp2_close_pct*100:.0f}%")
        log.info(f"  TP3: {tp3:.5f} ({self.params.tp3_r_multiple}R) -> CLOSE ALL remaining")
        
        return {
            "symbol": symbol,
            "broker_symbol": broker_symbol,
            "direction": direction,
            "confluence": confluence_score,
            "quality_factors": quality_factors,
            "current_price": current_price,
            "entry": entry,
            "stop_loss": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "entry_distance_r": entry_distance_r,
            "sl_pips": sl_pips,
            "flags": flags,
            "notes": notes,
        }
    
    def _calculate_pending_orders_risk(self) -> float:
        """Calculate total risk from all pending setups."""
        pending_list = []
        for symbol, setup in self.pending_setups.items():
            if setup.status == "pending" and setup.lot_size > 0:
                pending_list.append({
                    'symbol': symbol,
                    'lot_size': setup.lot_size,
                    'entry_price': setup.entry_price,
                    'stop_loss': setup.stop_loss,
                })
        return self.risk_manager.calculate_pending_orders_risk(pending_list)
    
    def _try_replace_worst_pending(
        self,
        new_symbol: str,
        new_confluence: int,
        new_entry_distance_r: float,
    ) -> bool:
        """
        Try to replace the worst pending order with a better one.
        
        Compares new setup quality vs existing pending orders.
        Replaces if new setup is significantly better (closer entry OR higher confluence).
        
        Returns True if replacement was made, False otherwise.
        """
        pending_orders = [
            (sym, setup) for sym, setup in self.pending_setups.items()
            if setup.status == "pending"
        ]
        
        if not pending_orders:
            return False
        
        worst_symbol = None
        worst_score = float('inf')
        worst_setup = None
        
        for sym, setup in pending_orders:
            entry_dist_r = getattr(setup, 'entry_distance_r', 1.0)
            confluence = getattr(setup, 'confluence_score', 4)
            score = confluence - entry_dist_r
            
            if score < worst_score:
                worst_score = score
                worst_symbol = sym
                worst_setup = setup
        
        if worst_symbol is None:
            return False
        
        new_score = new_confluence - new_entry_distance_r
        
        if new_score > worst_score + 0.5:
            log.info(f"[{new_symbol}] Better setup found (score: {new_score:.2f}) - replacing {worst_symbol} (score: {worst_score:.2f})")
            
            if worst_setup and worst_setup.order_ticket:
                try:
                    self.mt5.cancel_pending_order(worst_setup.order_ticket)
                    log.info(f"[{worst_symbol}] Cancelled pending order (ticket: {worst_setup.order_ticket})")
                except Exception as e:
                    log.warning(f"[{worst_symbol}] Failed to cancel order: {e}")
            
            del self.pending_setups[worst_symbol]
            self._save_pending_setups()
            return True
        
        log.info(f"[{new_symbol}] New setup (score: {new_score:.2f}) not better than worst pending (score: {worst_score:.2f})")
        return False
    
    def place_setup_order(self, setup: Dict, check_spread: bool = True, skip_proximity_check: bool = False) -> bool:
        """
        Place order for a validated setup.
        
        5ERS 60K OPTIMIZED:
        - Uses market order when price is at entry (like backtest instant fill)
        - Uses pending order when price is near but not at entry
        - Validates all risk limits before placing
        - Calculates proper lot size for 60K account
        - Spread check: If spread too wide, adds to awaiting_spread queue
        - Proximity check: If price too far, adds to awaiting_entry queue
        
        Args:
            setup: Trade setup dict
            check_spread: If True, check spread and add to queue if too wide
            skip_proximity_check: If True, skip proximity check (used when called from awaiting_entry)
        """
        from ftmo_config import FTMO_CONFIG, get_pip_size, get_sl_limits
        
        symbol = setup["symbol"]
        broker_symbol = setup.get("broker_symbol", self.symbol_map.get(symbol, symbol))
        direction = setup["direction"]
        current_price = setup.get("current_price", 0)
        entry = setup["entry"]
        sl = setup["stop_loss"]
        tp1 = setup["tp1"]
        tp2 = setup.get("tp2")
        tp3 = setup.get("tp3")
        tp4 = setup.get("tp4")  # 5-TP system
        tp5 = setup.get("tp5")  # 5-TP system
        confluence = setup["confluence"]
        quality_factors = setup["quality_factors"]
        entry_distance_r = setup.get("entry_distance_r", 0)
        
        # ═══════════════════════════════════════════════════════════════
        # ENTRY PROXIMITY CHECK - Wait for price to approach entry
        # If price is > 0.3R from entry, add to awaiting_entry queue
        # ═══════════════════════════════════════════════════════════════
        if not skip_proximity_check and entry_distance_r > FIVEERS_CONFIG.limit_order_proximity_r:
            log.info(f"[{symbol}] Price too far from entry ({entry_distance_r:.2f}R > {FIVEERS_CONFIG.limit_order_proximity_r}R)")
            log.info(f"[{symbol}] Adding to entry queue - will check every {self.ENTRY_CHECK_INTERVAL_MINUTES} min")
            self.add_to_awaiting_entry(setup)
            return False
        
        # ═══════════════════════════════════════════════════════════════
        # SPREAD & VOLUME CHECK - Only for MARKET orders (immediate entry)
        # For LIMIT orders, spread at placement doesn't matter - we wait for our price
        # ═══════════════════════════════════════════════════════════════
        is_market_order = entry_distance_r <= FIVEERS_CONFIG.immediate_entry_r
        
        if check_spread and is_market_order:
            conditions = self.check_market_conditions(symbol)
            
            if not conditions["spread_ok"] or not conditions["volume_ok"]:
                log.warning(f"[{symbol}] Market order blocked - bad conditions: {conditions['reason']}")
                log.warning(f"[{symbol}] Adding to spread queue for retry every {self.SPREAD_CHECK_INTERVAL_MINUTES} min")
                self.add_to_awaiting_spread(setup)
                return False
            
            log.info(f"[{symbol}] Market conditions OK for market order - Spread: {conditions['spread_pips']:.1f} pips")
        elif is_market_order:
            log.debug(f"[{symbol}] Spread check skipped for market order (check_spread=False)")
        else:
            log.debug(f"[{symbol}] Limit order - spread at placement doesn't matter")
        
        # Additional spread sanity check for market orders only
        if FIVEERS_CONFIG.min_spread_check and is_market_order:
            tick = self.mt5.get_tick(broker_symbol)
            if tick is not None:
                pip_size = get_pip_size(symbol)
                if pip_size <= 0:
                    log.warning(f"[{symbol}] Cannot determine pip size for spread check - using default 5 pip max")
                    pip_size = 0.0001
                
                current_spread_pips = tick.spread / pip_size
                
                if not FIVEERS_CONFIG.is_spread_acceptable(symbol, current_spread_pips):
                    max_spread = FIVEERS_CONFIG.get_max_spread_pips(symbol)
                    log.warning(f"[{symbol}] Spread too wide: {current_spread_pips:.1f} pips > {max_spread:.1f} pips max - skipping trade")
                    return False
                
                log.info(f"[{symbol}] Spread check passed: {current_spread_pips:.1f} pips")
        
        # BUGFIX: Block ALL existing setups, not just "pending" status
        # This prevents re-entry when position is still open (filled) or recently closed
        if symbol in self.pending_setups:
            existing = self.pending_setups[symbol]
            if existing.status in ("pending", "filled"):
                log.info(f"[{symbol}] Already have {existing.status} setup at {existing.entry_price:.5f}, skipping")
                return False
        
        # Also check if we have an open position for this symbol
        broker_symbol = self.symbol_map.get(symbol, symbol)
        if self.check_existing_position(broker_symbol):
            log.info(f"[{symbol}] Already have open position, skipping")
            return False
        
        if CHALLENGE_MODE and self.challenge_manager:
            snapshot = self.challenge_manager.get_account_snapshot()
            if snapshot is None:
                log.error(f"[{symbol}] Cannot get account snapshot")
                return False
            
            # Challenge snapshot uses daily_loss_pct; fall back gracefully if fields are missing
            daily_loss_pct = getattr(snapshot, "daily_loss_pct", 0)
            total_dd_pct = getattr(snapshot, "total_dd_pct", 0)
            profit_pct = (snapshot.equity - self.challenge_manager.initial_balance) / self.challenge_manager.initial_balance * 100
            
            if daily_loss_pct >= FIVEERS_CONFIG.daily_loss_halt_pct:
                log.warning(f"[{symbol}] Trading halted: daily loss {daily_loss_pct:.1f}% >= {FIVEERS_CONFIG.daily_loss_halt_pct}%")
                return False
            
            if total_dd_pct >= FIVEERS_CONFIG.total_dd_emergency_pct:
                log.warning(f"[{symbol}] Trading halted: total DD {total_dd_pct:.1f}% >= {FIVEERS_CONFIG.total_dd_emergency_pct}%")
                return False
            
            # STATIC POSITION LIMIT - Match simulator behavior
            # Simple hard cap at 100 positions (unlimited trades)
            max_trades = 100
            pending_count = len([s for s in self.pending_setups.values() if s.status == "pending"])
            open_positions = getattr(snapshot, "open_positions", len(self.mt5.get_my_positions()) if self.mt5 else 0)
            total_exposure = open_positions + pending_count

            # Check against static max trades limit
            if total_exposure >= max_trades:
                log.info(f"[{symbol}] Max trades reached: {total_exposure}/{max_trades} (positions: {open_positions}, pending: {pending_count})")
                return False
            
            # NOTE: NO cumulative risk check - removed to match simulator
            # Simulator has no cumulative risk limits, only position count limit
            
            # BUGFIX P0: LOT SIZE WILL BE CALCULATED AT FILL MOMENT
            # Do NOT calculate lot size here - it will be calculated when order fills
            # This ensures proper compounding with current balance, not stale balance
            log.info(f"[{symbol}] Risk check passed - lot size will be calculated at fill moment")
            
            # NOTE: We do NOT simulate daily loss from potential SL hit.
            # The simulator (simulate_main_live_bot.py) only checks DDD at fill moment,
            # not hypothetical losses. This matches backtest behavior.
            
        else:
            risk_check = self.risk_manager.check_trade(
                symbol=broker_symbol,
                direction=direction,
                entry_price=entry,
                stop_loss_price=sl,
            )
            
            if not risk_check.allowed:
                log.warning(f"[{symbol}] Trade blocked by risk manager: {risk_check.reason}")
                return False
            
            lot_size = risk_check.adjusted_lot
        
        if entry_distance_r <= FIVEERS_CONFIG.immediate_entry_r:
            order_type = "MARKET"
            log.info(f"[{symbol}] Price at entry ({entry_distance_r:.2f}R) - using MARKET ORDER")
            
            # BUGFIX P0: Calculate lot size at FILL MOMENT (not signal moment)
            lot_size = self._calculate_lot_size_at_fill(
                symbol=symbol,
                broker_symbol=broker_symbol,
                entry=entry,
                sl=sl,
                confluence=confluence,
            )
            
            if lot_size <= 0:
                log.error(f"[{symbol}] Invalid lot size calculation: {lot_size}")
                return False
            
            result = self.mt5.place_market_order(
                symbol=broker_symbol,
                direction=direction,
                volume=lot_size,
                sl=sl,
                tp=0,  # No auto-TP - bot manages partial closes at TP1/TP2/TP3 manually
            )
            
            if not result.success:
                log.error(f"[{symbol}] Market order FAILED: {result.error}")
                return False
            
            log.info(f"[{symbol}] MARKET ORDER FILLED!")
            log.info(f"  Order Ticket: {result.order_id}")
            log.info(f"  Fill Price: {result.price:.5f}")
            log.info(f"  Volume: {result.volume}")
            
            self.risk_manager.record_trade_open(
                symbol=broker_symbol,
                direction=direction,
                entry_price=result.price,
                stop_loss=sl,
                lot_size=result.volume,
                order_id=result.order_id,
            )
            
            pending_setup = PendingSetup(
                symbol=symbol,
                direction=direction,
                entry_price=result.price,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                confluence=confluence,
                confluence_score=confluence,
                quality_factors=quality_factors,
                entry_distance_r=entry_distance_r,
                created_at=datetime.now(timezone.utc).isoformat(),
                order_ticket=result.order_id,
                status="filled",
                lot_size=lot_size,  # Actual lot size used for market order
            )
            
        else:
            order_type = "PENDING"
            log.info(f"[{symbol}] Price {entry_distance_r:.2f}R from entry - using PENDING ORDER")
            log.info(f"[{symbol}] Placing PENDING ORDER:")
            log.info(f"  Direction: {direction.upper()}")
            log.info(f"  Entry Level: {entry:.5f}")
            log.info(f"  SL: {sl:.5f}")
            log.info(f"  TP1: {tp1:.5f}")
            log.info(f"  TP3: {tp3:.5f} (closes ALL remaining)" if tp3 else "  TP3: N/A")
            log.info(f"  Lot Size: Will be calculated when order fills")
            log.info(f"  Expiration: {FIVEERS_CONFIG.pending_order_expiry_hours} hours")
            
            # BUGFIX P0: Use minimal lot size for pending order placement
            # Real lot size will be calculated when order actually fills
            symbol_info = self.mt5.get_symbol_info(broker_symbol)
            min_lot = symbol_info.get('min_lot', 0.01) if symbol_info else 0.01
            
            result = self.mt5.place_pending_order(
                symbol=broker_symbol,
                direction=direction,
                volume=min_lot,  # Placeholder - will be adjusted on fill
                entry_price=entry,
                sl=sl,
                tp=0,  # No auto-TP - bot manages partial closes at TP1/TP2/TP3 manually
                expiration_hours=int(FIVEERS_CONFIG.pending_order_expiry_hours),
            )
            
            if not result.success:
                log.error(f"[{symbol}] Pending order FAILED: {result.error}")
                return False
            
            log.info(f"[{symbol}] PENDING ORDER PLACED SUCCESSFULLY!")
            log.info(f"  Order Ticket: {result.order_id}")
            log.info(f"  Entry Level: {result.price:.5f}")
            log.info(f"  Volume: {result.volume}")
            
            pending_setup = PendingSetup(
                symbol=symbol,
                direction=direction,
                entry_price=entry,
                stop_loss=sl,
                tp1=tp1,
                tp2=tp2,
                tp3=tp3,
                confluence=confluence,
                confluence_score=confluence,
                quality_factors=quality_factors,
                entry_distance_r=entry_distance_r,
                created_at=datetime.now(timezone.utc).isoformat(),
                order_ticket=result.order_id,
                status="pending",
                lot_size=0.0,  # Will be calculated when order fills
            )
        
        self.pending_setups[symbol] = pending_setup
        self._save_pending_setups()
        
        if pending_setup.status == "filled":
            self.record_trading_day()
        
        return True
    
    def check_position_updates(self):
        """
        Check for position closures (TP/SL hits) and update state.
        
        This syncs our internal state with actual MT5 positions.
        """
        my_positions = self.mt5.get_my_positions()
        open_tickets = {p.ticket for p in my_positions}
        
        state_positions = self.risk_manager.state.open_positions.copy()
        
        for pos_dict in state_positions:
            order_id = pos_dict.get("order_id")
            if order_id is None:
                continue
            
            if order_id not in open_tickets:
                log.info(f"Position {order_id} closed (detected from MT5)")
                
                self.risk_manager.record_trade_close(
                    order_id=order_id,
                    exit_price=0.0,
                    pnl_usd=0.0,
                )
                
                # BUGFIX: Remove closed position from pending_setups AND queues
                # This prevents re-entry of the same setup after position closes
                symbol_to_remove = None
                for symbol, setup in list(self.pending_setups.items()):
                    if setup.order_ticket == order_id and setup.status == "filled":
                        log.info(f"[{symbol}] Removing closed position from pending_setups (ticket {order_id})")
                        symbol_to_remove = symbol
                        del self.pending_setups[symbol]
                        self._save_pending_setups()
                        break
                
                # Also remove from entry/spread queues to prevent re-execution
                if symbol_to_remove:
                    if symbol_to_remove in self.awaiting_entry:
                        log.info(f"[{symbol_to_remove}] Removing from entry queue after position close")
                        del self.awaiting_entry[symbol_to_remove]
                        self._save_awaiting_entry()
                    
                    if symbol_to_remove in self.awaiting_spread:
                        log.info(f"[{symbol_to_remove}] Removing from spread queue after position close")
                        del self.awaiting_spread[symbol_to_remove]
                        self._save_awaiting_spread()
    
    def check_pending_orders(self):
        """
        Check status of pending orders every minute (like backtest simulation).
        
        - Detect if pending orders were filled (position exists)
        - Detect if orders expired or were cancelled
        - Cancel orders if price moved past SL (setup invalidated)
        - Delete pending orders older than 24 hours (time-based expiry)
        """
        if not self.pending_setups:
            return
        
        my_positions = self.mt5.get_my_positions()
        position_symbols = {p.symbol for p in my_positions}
        
        my_pending_orders = self.mt5.get_my_pending_orders()
        pending_order_tickets = {o.ticket for o in my_pending_orders}
        
        setups_to_remove = []
        now = datetime.now(timezone.utc)
        expiry_hours = FIVEERS_CONFIG.pending_order_expiry_hours
        
        for symbol, setup in self.pending_setups.items():
            if setup.status != "pending":
                continue
            
            if setup.created_at:
                try:
                    created_time = datetime.fromisoformat(setup.created_at.replace("Z", "+00:00"))
                    age_hours = (now - created_time).total_seconds() / 3600
                    
                    if age_hours >= expiry_hours:
                        log.info(f"[{symbol}] Pending order EXPIRED after {age_hours:.1f} hours (max {expiry_hours}h) - deleting")
                        if setup.order_ticket:
                            self.mt5.cancel_pending_order(setup.order_ticket)
                        setup.status = "expired"
                        setups_to_remove.append(symbol)
                        continue
                except (ValueError, TypeError) as e:
                    log.warning(f"[{symbol}] Could not parse created_at: {setup.created_at} - {e}")
            
            broker_symbol = self.symbol_map.get(symbol, symbol)
            if broker_symbol in position_symbols:
                log.info(f"[{symbol}] Pending order FILLED! Position now open (broker: {broker_symbol})")

                # BUGFIX P0: Calculate lot size at FILL MOMENT (not signal moment)
                # Find the actual position to get filled volume
                filled_position = next((p for p in my_positions if p.symbol == broker_symbol), None)

                if filled_position:
                    # CRITICAL: Recalculate lot size with CURRENT balance
                    # The pending order was placed with min_lot as placeholder
                    # Now we need to modify the position to correct lot size

                    correct_lot_size = self._calculate_lot_size_at_fill(
                        symbol=symbol,
                        broker_symbol=broker_symbol,
                        entry=setup.entry_price,
                        sl=setup.stop_loss,
                        confluence=setup.confluence,
                    )
                    
                    if correct_lot_size > 0 and abs(filled_position.volume - correct_lot_size) > 0.01:
                        # Position filled with placeholder lot size - need to adjust
                        log.warning(f"[{symbol}] Position filled with {filled_position.volume} lots, should be {correct_lot_size} lots")
                        log.warning(f"[{symbol}] Closing and re-opening with correct lot size...")
                        
                        # Close the position with wrong lot size
                        close_result = self.mt5.close_position(filled_position.ticket)
                        
                        if close_result.success:
                            # Re-open with correct lot size
                            reopen_result = self.mt5.place_market_order(
                                symbol=broker_symbol,
                                direction=setup.direction,
                                volume=correct_lot_size,
                                sl=setup.stop_loss,
                                tp=0,
                            )
                            
                            if reopen_result.success:
                                log.info(f"[{symbol}] ✅ Position re-opened with correct lot size: {correct_lot_size}")
                                setup.lot_size = correct_lot_size
                                setup.order_ticket = reopen_result.order_id
                            else:
                                log.error(f"[{symbol}] ❌ Failed to re-open position: {reopen_result.error}")
                                setup.status = "cancelled"
                                setups_to_remove.append(symbol)
                                continue
                        else:
                            log.error(f"[{symbol}] ❌ Failed to close position for re-sizing: {close_result.error}")
                            # Keep the position but with wrong lot size
                            setup.lot_size = filled_position.volume
                    else:
                        # Lot size is close enough or correct
                        setup.lot_size = filled_position.volume
                    
                    setup.status = "filled"
                    
                    self.risk_manager.record_trade_open(
                        symbol=broker_symbol,
                        direction=setup.direction,
                        entry_price=setup.entry_price,
                        stop_loss=setup.stop_loss,
                        lot_size=setup.lot_size,
                        order_id=setup.order_ticket or 0,
                    )
                else:
                    log.error(f"[{symbol}] Position marked as filled but not found in MT5!")
                    setup.status = "filled"
                
                self._save_pending_setups()
                self.record_trading_day()
                continue
            
            if setup.order_ticket and setup.order_ticket not in pending_order_tickets:
                log.info(f"[{symbol}] Pending order EXPIRED or CANCELLED (ticket {setup.order_ticket})")
                setup.status = "expired"
                setups_to_remove.append(symbol)
                continue
            
            tick = self.mt5.get_tick(broker_symbol)
            if tick:
                if setup.direction == "bullish" and tick.bid <= setup.stop_loss:
                    log.warning(f"[{symbol}] Price ({tick.bid:.5f}) breached SL ({setup.stop_loss:.5f}) - cancelling pending order")
                    if setup.order_ticket:
                        self.mt5.cancel_pending_order(setup.order_ticket)
                    setup.status = "cancelled"
                    setups_to_remove.append(symbol)
                elif setup.direction == "bearish" and tick.ask >= setup.stop_loss:
                    log.warning(f"[{symbol}] Price ({tick.ask:.5f}) breached SL ({setup.stop_loss:.5f}) - cancelling pending order")
                    if setup.order_ticket:
                        self.mt5.cancel_pending_order(setup.order_ticket)
                    setup.status = "cancelled"
                    setups_to_remove.append(symbol)
        
        for symbol in setups_to_remove:
            del self.pending_setups[symbol]
        
        if setups_to_remove:
            self._save_pending_setups()
    
    # DISABLED: validate_setup() - align with simulator
    # def validate_setup(self, symbol: str) -> bool:
    # """
    # Re-validate a pending setup to check if it's still valid.
        
    # Like the backtest, cancels if:
    # - Structure has shifted
    # - SL has been breached
    # - Confluence is no longer met
    # """
    # if symbol not in self.pending_setups:
    # return True
        
    # setup = self.pending_setups[symbol]
    # if setup.status != "pending":
    # return True
        
    # data = self.get_candle_data(symbol)
        
    # if not data["daily"] or len(data["daily"]) < 30:
    # return True
        
    # monthly_candles = data["monthly"] if data["monthly"] else []
    # weekly_candles = data["weekly"]
    # daily_candles = data["daily"]
    # h4_candles = data["h4"] if data["h4"] else daily_candles[-20:]
        
    # mn_trend = _infer_trend(monthly_candles) if monthly_candles else "mixed"
    # wk_trend = _infer_trend(weekly_candles) if weekly_candles else "mixed"
    # d_trend = _infer_trend(daily_candles) if daily_candles else "mixed"
        
    # direction, _, _ = _pick_direction_from_bias(mn_trend, wk_trend, d_trend)
        
    # if direction != setup.direction:
    # log.warning(f"[{symbol}] Direction changed from {setup.direction} to {direction} - cancelling setup")
    # if setup.order_ticket:
    # self.mt5.cancel_pending_order(setup.order_ticket)
    # del self.pending_setups[symbol]
    # self._save_pending_setups()
    # return False
        
    # historical_sr = get_all_htf_sr_levels(symbol) if HISTORICAL_SR_AVAILABLE else None
        
    # flags, notes, trade_levels = compute_confluence(
    # monthly_candles,
    # weekly_candles,
    # daily_candles,
    # h4_candles,
    # direction,
    # self.params,
    # historical_sr,
    # )
        
    # confluence_score = sum(1 for v in flags.values() if v)
    # has_rr = flags.get("rr", False)
    # quality_factors = sum([
    # flags.get("location", False),
    # flags.get("fib", False),
    # flags.get("liquidity", False),
    # flags.get("structure", False),
    # flags.get("htf_bias", False)
    # ])
        
    # # BUGFIX: Removed has_rr gate for consistency with new active signal criteria
    # if not (confluence_score >= MIN_CONFLUENCE and quality_factors >= 1):
    # log.warning(f"[{symbol}] Setup no longer valid (conf: {confluence_score}/7, quality: {quality_factors}) - cancelling")
    # if setup.order_ticket:
    # self.mt5.cancel_pending_order(setup.order_ticket)
    # del self.pending_setups[symbol]
    # self._save_pending_setups()
    # return False
        
    # return True
    
    # DISABLED: validate_all_setups()
    # def validate_all_setups(self):
    # """Validate all pending setups periodically."""
    # if not self.pending_setups:
    # return
        
    # log.info(f"Validating {len(self.pending_setups)} pending setups...")
        
    # symbols_to_validate = list(self.pending_setups.keys())
        
    # for symbol in symbols_to_validate:
    # try:
    # self.validate_setup(symbol)
    # time.sleep(0.2)
    # except Exception as e:
    # log.error(f"[{symbol}] Error validating setup: {e}")
        
    # self.last_validate_time = datetime.now(timezone.utc)
    
    def monitor_live_pnl(self) -> bool:
        """
        Monitor live P/L and trigger emergency close if needed.
        
        Strategy:
        1. Check current daily loss and total drawdown
        2. If approaching limits, close highest-risk positions first
        3. Re-check after each close to avoid overshooting
        4. Cancel pending orders if getting close to limits
        
        Returns:
            True if emergency close was triggered, False otherwise
        """
        account = self.mt5.get_account_info()
        if not account:
            log.warning("Could not get account info for P/L monitoring")
            return False
        
        current_equity = account.get('equity', 0)
        current_balance = account.get('balance', 0)
        
        if current_equity <= 0:
            return False
        
        # Calculate current exposure
        day_start = self.risk_manager.state.day_start_balance
        initial = self.risk_manager.state.initial_balance
        
        daily_loss_pct = 0.0
        if current_equity < day_start:
            daily_loss_pct = ((day_start - current_equity) / day_start) * 100
        
        total_dd_pct = 0.0
        if current_equity < initial:
            total_dd_pct = ((initial - current_equity) / initial) * 100
        
        # Cancel pending orders if approaching limits (above 3.0% daily or 6% total)
        # IMPROVED: Cancel earlier to prevent slippage issues
        if daily_loss_pct >= 3.0 or total_dd_pct >= 6.0:
            pending_orders = self.mt5.get_my_pending_orders()
            if pending_orders:
                log.warning(f"Approaching limits (Daily: {daily_loss_pct:.1f}%, DD: {total_dd_pct:.1f}%) - cancelling {len(pending_orders)} pending orders")
                for order in pending_orders:
                    self.mt5.cancel_pending_order(order.ticket)
                self.pending_setups.clear()
                self._save_pending_setups()
        
        # Start closing positions if above 3.5% daily or 7.0% total
        # IMPROVED: Close earlier to account for slippage (0.3-0.5% buffer to 5% limit)
        if daily_loss_pct >= 3.5 or total_dd_pct >= 7.0:
            positions = self.mt5.get_my_positions()
            if not positions:
                return False
            
            log.warning("=" * 70)
            log.warning(f"PROTECTIVE CLOSE TRIGGERED!")
            log.warning(f"Daily Loss: {daily_loss_pct:.2f}% | Total DD: {total_dd_pct:.2f}%")
            log.warning(f"Closing positions gradually to stay under limits")
            log.warning("=" * 70)
            
            # Sort positions by unrealized loss (worst first)
            positions_sorted = sorted(positions, key=lambda p: p.profit)
            
            for pos in positions_sorted:
                log.warning(f"Closing {pos.symbol} (P/L: ${pos.profit:.2f}, Volume: {pos.volume})")
                result = self.mt5.close_position(pos.ticket)
                
                if result.success:
                    log.info(f"  ✓ Closed at {result.price}, P/L: ${pos.profit:.2f}")
                    self.risk_manager.record_trade_close(
                        order_id=pos.ticket,
                        exit_price=result.price,
                        pnl_usd=pos.profit,
                    )
                    
                    # Re-check after closing
                    account = self.mt5.get_account_info()
                    if account:
                        new_equity = account.get('equity', 0)
                        new_daily_loss = 0.0
                        new_total_dd = 0.0
                        
                        if new_equity < day_start:
                            new_daily_loss = ((day_start - new_equity) / day_start) * 100
                        if new_equity < initial:
                            new_total_dd = ((initial - new_equity) / initial) * 100
                        
                        log.info(f"  After close: Daily Loss: {new_daily_loss:.2f}%, Total DD: {new_total_dd:.2f}%")
                        
                        # Stop if we're back under 3.5% daily and 7% total
                        if new_daily_loss < 3.5 and new_total_dd < 7.0:
                            log.info("  Back under safe thresholds - stopping protective close")
                            return False
                        
                        # Emergency if we've breached hard limits
                        if new_daily_loss >= 5.0 or new_total_dd >= 10.0:
                            log.error("  BREACH DETECTED - closing all remaining positions immediately!")
                            break
                else:
                    log.error(f"  ✗ Failed to close: {result.error}")
            
            # Check final state
            account = self.mt5.get_account_info()
            if account:
                final_equity = account.get('equity', 0)
                final_daily = 0.0
                final_dd = 0.0
                
                if final_equity < day_start:
                    final_daily = ((day_start - final_equity) / day_start) * 100
                if final_equity < initial:
                    final_dd = ((initial - final_equity) / initial) * 100
                
                if final_daily >= 5.0 or final_dd >= 10.0:
                    log.error(f"LIMIT BREACH AFTER CLOSE: Daily {final_daily:.2f}%, DD {final_dd:.2f}%")
                    self.risk_manager.state.failed = True
                    self.risk_manager.state.fail_reason = f"Limit breached: Daily {final_daily:.1f}%, DD {final_dd:.1f}%"
                    self.risk_manager.save_state()
                    return True
            
            return False
        
        return False
    
    def manage_partial_takes(self):
        """
        Manage partial take profits for active positions.
        
        3-TP SYSTEM (ALIGNED WITH SIMULATOR):
        - TP1: Close tp1_close_pct at tp1_r_multiple
        - TP2: Close tp2_close_pct at tp2_r_multiple  
        - TP3: Close ALL REMAINING at tp3_r_multiple
        
        All closes via MARKET ORDERS with position=ticket!
        
        TRAILING STOP LOGIC (matches simulator):
        - TP1 hit: SL → Breakeven
        - TP2 hit: SL → TP1 + 0.5R
        - TP3 hit: Close ALL remaining position
        
        Tracks partial close state in pending_setups.partial_closes (0-3).
        """
        positions = self.mt5.get_my_positions()
        if not positions:
            return
        
        for pos in positions:
            # Find matching setup - try broker symbol first, then internal symbol
            setup = None
            broker_symbol = pos.symbol
            
            # Try to find by broker symbol or internal symbol
            for sym, s in self.pending_setups.items():
                if s.order_ticket == pos.ticket:
                    setup = s
                    break
                mapped_broker = self.symbol_map.get(sym, sym)
                if mapped_broker == broker_symbol:
                    setup = s
                    break
            
            if not setup or setup.status != "filled":
                continue
            
            tick = self.mt5.get_tick(broker_symbol)
            if not tick:
                continue
            
            current_price = tick.bid if setup.direction == "bullish" else tick.ask
            entry = setup.entry_price
            risk = abs(entry - setup.stop_loss)
            
            if risk <= 0:
                continue
            
            # Calculate current R
            if setup.direction == "bullish":
                current_r = (current_price - entry) / risk
            else:
                current_r = (entry - current_price) / risk
            
            # Get TP levels from params (3-TP system - ALIGNED WITH SIMULATOR)
            tp1_r = self.params.tp1_r_multiple
            tp2_r = self.params.tp2_r_multiple
            tp3_r = self.params.tp3_r_multiple
            
            original_volume = setup.lot_size
            current_volume = pos.volume
            partial_state = setup.partial_closes if hasattr(setup, 'partial_closes') else 0
            
            # ═══════════════════════════════════════════════════════════════
            # TP1 HIT - Close tp1_close_pct, move SL to breakeven
            # ═══════════════════════════════════════════════════════════════
            if current_r >= tp1_r and partial_state == 0:
                close_pct = self.params.tp1_close_pct
                close_volume = max(0.01, round(original_volume * close_pct, 2))
                close_volume = min(close_volume, current_volume)
                
                log.info(f"[{broker_symbol}] TP1 HIT at {current_r:.2f}R! Closing {close_pct*100:.0f}%")
                
                # Retry logic for partial close (up to 3 attempts)
                result = None
                for attempt in range(3):
                    result = self.mt5.partial_close(pos.ticket, close_volume)
                    if result.success:
                        break
                    if attempt < 2:
                        log.warning(f"[{broker_symbol}] Partial close attempt {attempt+1} failed, retrying...")
                        time.sleep(0.5 * (attempt + 1))
                
                if result and result.success:
                    log.info(f"[{broker_symbol}] ✅ Partial close at {result.price}")
                    setup.partial_closes = 1
                    setup.tp1_hit = True
                    
                    # Move SL to breakeven (matches simulator)
                    new_sl = entry
                    self.mt5.modify_sl_tp(pos.ticket, sl=new_sl)
                    log.info(f"[{broker_symbol}] SL moved to breakeven: {new_sl:.5f}")
                    
                    self._save_pending_setups()
                else:
                    log.error(f"[{broker_symbol}] Partial close failed: {result.error}")
            
            # ═══════════════════════════════════════════════════════════════
            # PROGRESSIVE TRAILING: Between TP1 and TP2, at 0.9R move SL to TP1
            # This locks in more profit earlier, improving risk-adjusted returns
            # Backtested: +$66K improvement (+16%) over standard trailing
            # ═══════════════════════════════════════════════════════════════
            progressive_trigger_r = 0.9  # Trigger progressive trail at 0.9R
            
            if (partial_state == 1 and 
                current_r >= progressive_trigger_r and 
                current_r < tp2_r and
                not getattr(setup, 'progressive_trail_applied', False)):
                
                # Calculate TP1 level for trailing SL
                if setup.direction == "bullish":
                    new_sl = entry + (risk * tp1_r)
                else:
                    new_sl = entry - (risk * tp1_r)
                
                log.info(f"[{broker_symbol}] Progressive trail at {current_r:.2f}R! Moving SL to TP1 ({tp1_r}R)")
                
                modify_result = self.mt5.modify_sl_tp(pos.ticket, sl=new_sl)
                if modify_result:
                    log.info(f"[{broker_symbol}] ✅ SL trailed to TP1: {new_sl:.5f}")
                    setup.progressive_trail_applied = True
                    self._save_pending_setups()
                else:
                    log.warning(f"[{broker_symbol}] Failed to apply progressive trail")
            
            # ═══════════════════════════════════════════════════════════════
            # TP2 HIT - Close tp2_close_pct, trail SL to TP1 + 0.5R
            # ═══════════════════════════════════════════════════════════════
            if current_r >= tp2_r and partial_state == 1:
                close_pct = self.params.tp2_close_pct
                close_volume = max(0.01, round(original_volume * close_pct, 2))
                close_volume = min(close_volume, current_volume)
                
                log.info(f"[{broker_symbol}] TP2 HIT at {current_r:.2f}R! Closing {close_pct*100:.0f}%")
                
                # Retry logic for partial close (up to 3 attempts)
                result = None
                for attempt in range(3):
                    result = self.mt5.partial_close(pos.ticket, close_volume)
                    if result.success:
                        break
                    if attempt < 2:
                        log.warning(f"[{broker_symbol}] Partial close attempt {attempt+1} failed, retrying...")
                        time.sleep(0.5 * (attempt + 1))
                
                if result and result.success:
                    log.info(f"[{broker_symbol}] ✅ Partial close at {result.price}")
                    setup.partial_closes = 2
                    setup.tp2_hit = True
                    
                    # Trail SL to TP1 + 0.5R (matches simulator)
                    if setup.direction == "bullish":
                        new_sl = entry + (risk * tp1_r) + (0.5 * risk)
                    else:
                        new_sl = entry - (risk * tp1_r) - (0.5 * risk)
                    
                    self.mt5.modify_sl_tp(pos.ticket, sl=new_sl)
                    log.info(f"[{broker_symbol}] SL trailed to TP1+0.5R: {new_sl:.5f}")
                    
                    self._save_pending_setups()
                else:
                    log.error(f"[{broker_symbol}] Partial close failed: {result.error}")
            
            # ═══════════════════════════════════════════════════════════════
            # TP3 HIT - Close ALL REMAINING (matches simulator exactly)
            # ═══════════════════════════════════════════════════════════════
            if current_r >= tp3_r and partial_state == 2:
                log.info(f"[{broker_symbol}] TP3 HIT at {current_r:.2f}R! Closing ALL remaining")
                
                # Retry logic for position close (up to 3 attempts)
                result = None
                for attempt in range(3):
                    result = self.mt5.close_position(pos.ticket)
                    if result.success:
                        break
                    if attempt < 2:
                        log.warning(f"[{broker_symbol}] Close position attempt {attempt+1} failed, retrying...")
                        time.sleep(0.5 * (attempt + 1))
                
                if result and result.success:
                    log.info(f"[{broker_symbol}] ✅ Position FULLY CLOSED at {result.price}")
                    setup.partial_closes = 3
                    setup.tp3_hit = True
                    setup.status = "closed"
                    
                    # Calculate total R for this trade (matches simulator)
                    total_r = (tp1_r * self.params.tp1_close_pct +
                              tp2_r * self.params.tp2_close_pct +
                              tp3_r * (1.0 - self.params.tp1_close_pct - self.params.tp2_close_pct))
                    log.info(f"[{broker_symbol}] Total R: ~{total_r:.2f}R (perfect 3-TP exit)")
                    
                    self._save_pending_setups()
                else:
                    log.error(f"[{broker_symbol}] Failed to close position: {result.error}")
    
    def execute_protection_actions(self) -> bool:
        """
        Execute protection actions from Challenge Risk Manager.
        
        Called every 30 seconds when CHALLENGE_MODE is enabled.
        Executes actions returned by challenge_manager.run_protection_check():
        - CLOSE_ALL: Close all positions and cancel pending orders
        - CANCEL_PENDING: Cancel specific pending orders
        - MOVE_SL_BREAKEVEN: Move SL to entry price for specific positions
        - CLOSE_WORST: Close the worst performing position
        
        Returns:
            True if an emergency action was triggered (halt trading), False otherwise
        """
        if not CHALLENGE_MODE or not self.challenge_manager:
            return False
        
        actions = self.challenge_manager.run_protection_check()
        
        if not actions:
            return False
        
        actions_sorted = sorted(actions, key=lambda a: a.priority, reverse=True)
        emergency_triggered = False
        
        for action in actions_sorted:
            log.warning(f"[RISK] Executing protection action: {action.action.value} - {action.reason}")
            
            try:
                if action.action == ActionType.CLOSE_ALL:
                    log.error("=" * 70)
                    log.error("EMERGENCY: CLOSE ALL TRIGGERED")
                    log.error(f"Reason: {action.reason}")
                    log.error("=" * 70)
                    
                    positions = self.mt5.get_my_positions()
                    for pos in positions:
                        result = self.mt5.close_position(pos.ticket)
                        if result.success:
                            log.info(f"  ✓ Closed {pos.symbol} at {result.price}")
                            self.risk_manager.record_trade_close(
                                order_id=pos.ticket,
                                exit_price=result.price,
                                pnl_usd=pos.profit,
                            )
                        else:
                            log.error(f"  ✗ Failed to close {pos.symbol}: {result.error}")
                    
                    pending_orders = self.mt5.get_my_pending_orders()
                    for order in pending_orders:
                        self.mt5.cancel_pending_order(order.ticket)
                        log.info(f"  ✓ Cancelled pending order {order.ticket}")
                    
                    self.pending_setups.clear()
                    self._save_pending_setups()
                    
                    action.executed = True
                    emergency_triggered = True
                    
                elif action.action == ActionType.CLOSE_PENDING:
                    # Cancel all pending orders
                    pending_orders = self.mt5.get_my_pending_orders()
                    for order in pending_orders:
                        result = self.mt5.cancel_pending_order(order.ticket)
                        if result:
                            log.info(f"  ✓ Cancelled pending order {order.ticket}")
                        else:
                            log.error(f"  ✗ Failed to cancel pending order {order.ticket}")
                    action.executed = True
                    
                elif action.action == ActionType.MOVE_SL_BREAKEVEN:
                    for ticket in action.positions_affected:
                        positions = self.mt5.get_my_positions()
                        pos = next((p for p in positions if p.ticket == ticket), None)
                        if pos:
                            result = self.mt5.modify_sl_tp(ticket, sl=pos.price_open)
                            if result:
                                log.info(f"  ✓ Moved SL to breakeven for {pos.symbol} ({pos.price_open:.5f})")
                            else:
                                log.error(f"  ✗ Failed to move SL to breakeven for {pos.symbol}")
                        else:
                            log.warning(f"  Position {ticket} not found for SL modification")
                    action.executed = True
                    
                elif action.action == ActionType.CLOSE_WORST:
                    for ticket in action.positions_affected:
                        result = self.mt5.close_position(ticket)
                        if result.success:
                            log.info(f"  ✓ Closed worst position {ticket} at {result.price}")
                            self.risk_manager.record_trade_close(
                                order_id=ticket,
                                exit_price=result.price,
                                pnl_usd=0.0,
                            )
                        else:
                            log.error(f"  ✗ Failed to close position {ticket}: {result.error}")
                    action.executed = True
                    
                elif action.action == ActionType.HALT_TRADING:
                    log.error(f"[RISK] Trading HALTED: {action.reason}")
                    action.executed = True
                    emergency_triggered = True
                
                elif action.action == ActionType.HALT_NEW_TRADES:
                    # Just log - don't open new trades, but don't close existing ones
                    log.warning(f"[RISK] New trades HALTED (existing positions remain): {action.reason}")
                    action.executed = True
                
                elif action.action == ActionType.REDUCE_RISK:
                    # Risk is already reduced in challenge_risk_manager via risk_mode
                    # Just log and cancel pending orders to reduce exposure
                    log.warning(f"[RISK] Risk REDUCED (risk mode: conservative): {action.reason}")
                    
                    # Cancel pending orders to reduce exposure
                    pending_orders = self.mt5.get_my_pending_orders()
                    if pending_orders:
                        log.warning(f"  Cancelling {len(pending_orders)} pending orders to reduce exposure...")
                        for order in pending_orders:
                            try:
                                self.mt5.cancel_pending_order(order.ticket)
                                log.info(f"  ✓ Cancelled pending order {order.ticket} ({order.symbol})")
                            except Exception as e:
                                log.error(f"  ✗ Failed to cancel {order.ticket}: {e}")
                    action.executed = True
                    
            except Exception as e:
                log.error(f"[RISK] Error executing action {action.action.value}: {e}")
        
        return emergency_triggered
    
    def scan_all_symbols(self):
        """
        Scan all tradable symbols and place pending orders.
        
        Uses the same logic as the backtest walk-forward loop.
        Now places pending limit orders instead of market orders
        to match backtest entry behavior exactly.
        """
        # NEWS BLACKOUT CHECK
        if self.is_news_blackout():
            log.warning("Skipping scan - major news event blackout period")
            return
        
        # WEEKEND GAP PROTECTION CHECK
        if CHALLENGE_MODE and self.challenge_manager:
            if self.challenge_manager.should_close_for_weekend():
                log.warning("🌅 WEEKEND GAP PROTECTION TRIGGERED - closing all positions")
                positions = self.mt5.get_my_positions()
                for pos in positions:
                    result = self.mt5.close_position(pos.ticket)
                    if result.success:
                        log.info(f"  ✓ Closed {pos.symbol} for weekend protection")
                        self.risk_manager.record_trade_close(
                            order_id=pos.ticket,
                            exit_price=result.price,
                            pnl_usd=pos.profit,
                        )
                return
        
        # DDD/TDD CHECK BEFORE SCAN - Block new orders if in danger zone
        if CHALLENGE_MODE and self.challenge_manager:
            # Sync with MT5 to get current equity
            try:
                current_equity = self.mt5.get_account_equity()
                current_balance = self.mt5.get_account_balance()
                self.challenge_manager.sync_with_mt5(current_balance, current_equity)
            except Exception as e:
                log.error(f"Failed to sync risk manager: {e}")
            
            # Get current DDD/TDD percentages
            day_start = self.challenge_manager.day_start_equity
            starting = self.challenge_manager.starting_balance
            equity = self.challenge_manager.current_equity
            
            daily_loss_pct = abs(min(0, equity - day_start)) / day_start * 100 if day_start > 0 else 0
            total_dd_pct = max(0, (starting - equity) / starting * 100) if starting > 0 else 0
            
            log.info("=" * 70)
            log.info(f"📊 PRE-SCAN RISK CHECK")
            log.info(f"  Day Start Equity: ${day_start:,.2f}")
            log.info(f"  Current Equity: ${equity:,.2f}")
            log.info(f"  DDD: {daily_loss_pct:.2f}% (halt at 3.5%, reduce at 3.0%)")
            log.info(f"  TDD: {total_dd_pct:.2f}% (halt at 10%)")
            log.info("=" * 70)
            
            # Block scan entirely if DDD >= 3.5% (HALT tier)
            if daily_loss_pct >= 3.5:
                log.error("=" * 70)
                log.error(f"🚫 SCAN BLOCKED: DDD {daily_loss_pct:.2f}% >= 3.5%")
                log.error("  No new orders will be placed until next trading day")
                log.error("=" * 70)
                return
            
            # Block scan if TDD >= 7% (emergency zone)
            if total_dd_pct >= 7.0:
                log.error("=" * 70)
                log.error(f"🚫 SCAN BLOCKED: TDD {total_dd_pct:.2f}% >= 7%")
                log.error("  No new orders will be placed - approaching 10% limit!")
                log.error("=" * 70)
                return
        
        log.info("=" * 70)
        log.info(f"MARKET SCAN - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        log.info(f"Strategy Mode: {SIGNAL_MODE} (Min Confluence: {MIN_CONFLUENCE}/7)")
        log.info(f"Using PENDING ORDERS (like backtest)")
        log.info("=" * 70)
        
        self.scan_count += 1
        signals_found = 0
        orders_placed = 0
        
        # Only scan symbols that are available on broker
        available_symbols = [s for s in TRADABLE_SYMBOLS if s in self.symbol_map]
        
        # ═══════════════════════════════════════════════════════════════════════════════
        # WEEKEND CRYPTO SCANNING - Detect if it's weekend and filter accordingly
        # ═══════════════════════════════════════════════════════════════════════════════
        current_day = datetime.now(timezone.utc).weekday()  # 0=Monday, 6=Sunday
        is_weekend = current_day in [5, 6]  # Saturday=5, Sunday=6
        
        for symbol in available_symbols:
            try:
                # ═══════════════════════════════════════════════════════════
                # WEEKEND LOGIC - Skip forex on weekends, ALWAYS scan crypto
                # ═══════════════════════════════════════════════════════════
                if is_weekend and not is_crypto_pair(symbol):
                    log.debug(f"[{symbol}] Skipping weekend scan - forex market closed")
                    continue
                
                setup = self.scan_symbol(symbol)
                
                if setup:
                    signals_found += 1
                    
                    if self.place_setup_order(setup):
                        orders_placed += 1
                
                time.sleep(0.5)
                
            except Exception as e:
                log.error(f"[{symbol}] Error during scan: {e}")
                continue
            time.sleep(0.1)
        
        log.info("=" * 70)
        log.info("SCAN COMPLETE")
        log.info(f"  Symbols scanned: {len(available_symbols)}/{len(TRADABLE_SYMBOLS)}")
        log.info(f"  Active signals: {signals_found}")
        log.info(f"  Pending orders placed: {orders_placed}")
        
        positions = self.mt5.get_my_positions()
        pending_orders = self.mt5.get_my_pending_orders()
        log.info(f"  Open positions: {len(positions)}")
        log.info(f"  Pending orders: {len(pending_orders)}")
        log.info(f"  Tracked setups: {len(self.pending_setups)}")
        
        # Get status from CHALLENGE manager (not risk_manager) for accurate DDD/TDD
        if CHALLENGE_MODE and self.challenge_manager:
            day_start = self.challenge_manager.day_start_equity
            starting = self.challenge_manager.starting_balance
            equity = self.challenge_manager.current_equity
            balance = self.challenge_manager.current_balance
            
            daily_loss_pct = abs(min(0, equity - day_start)) / day_start * 100 if day_start > 0 else 0
            total_dd_pct = max(0, (starting - equity) / starting * 100) if starting > 0 else 0
            profit_pct = (balance - starting) / starting * 100 if starting > 0 else 0
            
            phase = 1 if profit_pct < 8.0 else 2
            target_pct = 8.0 if phase == 1 else 5.0
            
            log.info(f"  Challenge Phase: {phase}")
            log.info(f"  Balance: ${balance:,.2f}")
            log.info(f"  Profit: {profit_pct:+.2f}% (Target: {target_pct}%)")
            log.info(f"  📊 DDD: {daily_loss_pct:.2f}%/5% (Day Start: ${day_start:,.2f})")
            log.info(f"  📊 TDD: {total_dd_pct:.2f}%/10% (Starting: ${starting:,.2f})")
            log.info(f"  Profitable Days: {len(self.challenge_manager.trading_days)}/3")
        else:
            status = self.risk_manager.get_status()
            log.info(f"  Challenge Phase: {status['phase']}")
            log.info(f"  Balance: ${status['balance']:,.2f}")
            log.info(f"  Profit: {status['profit_pct']:+.2f}% (Target: {status['target_pct']}%)")
            log.info(f"  Daily DD: {status['daily_loss_pct']:.2f}%/5%")
            log.info(f"  Max DD: {status['drawdown_pct']:.2f}%/10%")
            log.info(f"  Profitable Days: {status['profitable_days']}/{status['min_profitable_days']}")
        log.info("=" * 70)
        
        self.last_scan_time = datetime.now(timezone.utc)
    
    def run(self):
        """
        Main trading loop - runs 24/7 for 5ers 60K High Stakes Challenge.
        
        5ERS-SPECIFIC FEATURES:
        - First run: Immediate scan after restart/weekend (if --first-run or flag missing)
        - Scheduled scan: 10 min after daily close (00:10 server time)
        - Weekend gap protection: Check positions on Monday morning
        - Spread queue: Retry trades when spread improves
        - 5-TP partial close system: 10/10/15/20/45% at 0.6R/1.2R/2.0R/2.5R/3.5R
        - DD monitoring: Total DD only (5ers has NO daily DD limit!)
        
        SCHEDULE:
        - Every 10 seconds: Protection checks, 5-TP management
        - Every 10 minutes: Spread queue check, validate setups
        - 00:10 server time: Daily market scan
        - Monday 00:00-02:00: Weekend gap protection
        """
        log.info("=" * 70)
        log.info("TRADR BOT - 5ERS 60K HIGH STAKES CHALLENGE")
        log.info("=" * 70)
        log.info(f"KRITIEKE 5ERS REGELS:")
        log.info(f"  - Account: ${ACCOUNT_SIZE:,.0f}")
        log.info(f"  - Total DD: 10% = ${ACCOUNT_SIZE * 0.10:,.0f} (stop-out: ${ACCOUNT_SIZE * 0.90:,.0f}) - STATIC!")
        log.info(f"  - Daily DD: 5% = ${ACCOUNT_SIZE * 0.05:,.0f} (from day start)")
        log.info(f"  - DDD Safety: Halt at 3.5%, Reduce at 3.0%, Warn at 2.0%")
        log.info(f"  - Step 1: 8% profit = ${ACCOUNT_SIZE * 0.08:,.0f}")
        log.info(f"  - Step 2: 5% profit = ${ACCOUNT_SIZE * 0.05:,.0f}")
        log.info(f"  - Min Trading Days: 3")
        log.info("=" * 70)
        log.info(f"3-TP EXIT SYSTEM (ALIGNED WITH SIMULATOR):")
        log.info(f"  - TP1: {self.params.tp1_r_multiple}R -> {self.params.tp1_close_pct*100:.0f}%")
        log.info(f"  - TP2: {self.params.tp2_r_multiple}R -> {self.params.tp2_close_pct*100:.0f}%")
        log.info(f"  - TP3: {self.params.tp3_r_multiple}R -> CLOSE ALL remaining")
        log.info("=" * 70)
        log.info(f"Server: {MT5_SERVER}")
        log.info(f"Login: {MT5_LOGIN}")
        log.info(f"Demo: {'YES ⚠️' if IS_DEMO else 'NO (LIVE)'}")
        log.info(f"Min Confluence: {MIN_CONFLUENCE}/7")
        log.info(f"Symbols: {len(TRADABLE_SYMBOLS)}")
        log.info("=" * 70)
        
        if not self.connect():
            log.error("Failed to connect to MT5. Exiting.")
            return
        
        # CRITICAL FIX JAN 20, 2026: Start DDD protection loop AFTER connect()
        # Otherwise challenge_manager is None and the protection never works!
        self.start_ddd_protection_loop()
        log.info("🛡️ DDD/TDD Protection loop started")
        
        log.info("Starting trading loop...")
        log.info("Press Ctrl+C to stop")
        
        global running
        
        # ═══════════════════════════════════════════════════════════════════
        # FIRST RUN CHECK - Immediate scan if needed
        # ═══════════════════════════════════════════════════════════════════
        if self.should_do_immediate_scan():
            log.info("=" * 70)
            log.info("🚀 IMMEDIATE SCAN - First run after restart/weekend")
            log.info("=" * 70)
            self.scan_all_symbols()
            self._mark_first_run_complete()
            # Calculate next scan time after immediate scan
            self.next_scan_time = get_next_scan_time()
        else:
            # Get today's scan time (00:10 server time)
            server_now = get_server_time()
            today_scan = server_now.replace(hour=0, minute=10, second=0, microsecond=0)
            today_scan_utc = today_scan.astimezone(timezone.utc)

            # If today's scan time has passed and it's a weekday, use today (will trigger immediately)
            # Otherwise use next future scan time
            if server_now >= today_scan and today_scan.weekday() < 5:
                self.next_scan_time = today_scan_utc
                log.info(f"Missed today's scan - will scan immediately")
                log.info(f"Scheduled scan time was: {self.next_scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                self.next_scan_time = get_next_scan_time()
                log.info(f"Skipping immediate scan - next scheduled: {self.next_scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        # Weekend gap check (only on Monday morning)
        self.handle_weekend_gap_positions()
        
        self.last_validate_time = datetime.now(timezone.utc)
        self.last_spread_check_time = datetime.now(timezone.utc)
        last_protection_check = datetime.now(timezone.utc)
        emergency_triggered = False
        
        while running:
            # If DDD halt is active, skip trading actions
            if getattr(self, 'ddd_halted', False):
                log.warning(f"🚨 DDD HALT ACTIVE: {getattr(self, 'ddd_halt_reason', '')} - Trading paused until next day.")
                time.sleep(10)
                continue
            try:
                now = datetime.now(timezone.utc)
                
                # ═══════════════════════════════════════════════════════════════
                # 5ERS DD MONITORING (no daily DD limit!)
                # ═══════════════════════════════════════════════════════════════
                if self.monitor_5ers_drawdown():
                    emergency_triggered = True
                    log.error("5ERS STOP-OUT TRIGGERED - halting all trading")
                    continue
                
                # Emergency halt check
                if CHALLENGE_MODE and self.challenge_manager and self.challenge_manager.halted:
                    if not emergency_triggered:
                        emergency_triggered = True
                        log.error(f"Challenge Manager halted trading: {self.challenge_manager.halt_reason}")
                
                if not emergency_triggered:
                    time_since_protection_check = (now - last_protection_check).total_seconds()
                    if time_since_protection_check >= self.MAIN_LOOP_INTERVAL_SECONDS:
                        # Protection checks
                        if CHALLENGE_MODE and self.challenge_manager:
                            if self.execute_protection_actions():
                                emergency_triggered = True
                                log.error("Challenge protection triggered emergency - halting all trading")
                                continue
                        else:
                            if self.monitor_live_pnl():
                                emergency_triggered = True
                                log.error("Emergency close triggered - halting all trading")
                                continue
                        
                        # 5-TP partial close management
                        self.manage_partial_takes()

                        # Weekend gap risk management
                        self.handle_friday_position_closing()  # Friday 16:00+ UTC
                        self.handle_sunday_gap_detection()  # Sunday 22:00+ UTC

                        last_protection_check = now

                if emergency_triggered:
                    time.sleep(60)
                    continue
                
                # ═══════════════════════════════════════════════════════════════
                # SPREAD QUEUE CHECK - Every SPREAD_CHECK_INTERVAL_MINUTES
                # ═══════════════════════════════════════════════════════════════
                if self.last_spread_check_time:
                    time_since_spread = (now - self.last_spread_check_time).total_seconds() / 60
                    if time_since_spread >= self.SPREAD_CHECK_INTERVAL_MINUTES:
                        self.check_awaiting_spread_signals()
                        self.last_spread_check_time = now
                
                # ═══════════════════════════════════════════════════════════════
                # ENTRY QUEUE CHECK - Every ENTRY_CHECK_INTERVAL_MINUTES
                # Check signals waiting for price to approach entry level
                # ═══════════════════════════════════════════════════════════════
                if self.last_entry_check_time is None:
                    self.last_entry_check_time = now
                else:
                    time_since_entry = (now - self.last_entry_check_time).total_seconds() / 60
                    if time_since_entry >= self.ENTRY_CHECK_INTERVAL_MINUTES:
                        self.check_awaiting_entry_signals()
                        self.last_entry_check_time = now
                
                # Pending orders and position updates
                self.check_pending_orders()
                self.check_position_updates()
                
                # Validate setups - DISABLED to align with simulator
                # Simulator trusts signal at scan time, only expires via time/SL breach
                # if self.last_validate_time:
                #     next_validate = self.last_validate_time + timedelta(minutes=self.VALIDATE_INTERVAL_MINUTES)
                #     if now >= next_validate:
                #         self.validate_all_setups()
                
                # ═══════════════════════════════════════════════════════════════
                # DAILY SCAN - 10 min after daily close (00:10 server time)
                # ═══════════════════════════════════════════════════════════════
                if self.next_scan_time and now >= self.next_scan_time:
                    if is_market_open():
                        log.info("=" * 70)
                        log.info(f"📊 DAILY SCAN - {get_server_time().strftime('%Y-%m-%d %H:%M')} Server Time")
                        log.info("=" * 70)
                        
                        # CRITICAL: Reset DDD halt at daily scan time (new trading day)
                        if self.ddd_halted:
                            log.info("✅ NEW TRADING DAY - Resetting DDD halt from previous day")
                            self.ddd_halted = False
                            self.ddd_halt_reason = ""
                            self.ddd_halt_date = None
                            self._save_ddd_halt_state()
                            log.info("✅ Trading re-enabled!")

                        # Update daily tracking and reset for new day
                        self.risk_manager._check_new_day()
                        
                        # Update day_start_equity BEFORE scan (use current equity as new day start)
                        # This is the equity at daily close which becomes the new day's starting point
                        account = self.mt5.get_account_info()
                        if account and self.challenge_manager:
                            current_equity = account.get("equity", 0)
                            old_day_start = self.challenge_manager.day_start_equity
                            self.challenge_manager.update_day_start_equity(current_equity)
                            log.info(f"Day start equity updated: ${old_day_start:,.2f} → ${current_equity:,.2f}")

                        self.scan_all_symbols()

                        # Calculate next scan time after successful scan
                        self.next_scan_time = get_next_scan_time()
                        log.info(f"Next scan scheduled: {self.next_scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    else:
                        log.info("Market closed (weekend), skipping scan")
                        # Calculate next scan time (will skip to Monday)
                        self.next_scan_time = get_next_scan_time()
                        log.info(f"Next scan scheduled: {self.next_scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
                # Reconnection handling
                if not self.mt5.connected:
                    log.warning("MT5 connection lost, attempting reconnect...")
                    if self.connect():
                        log.info("Reconnected successfully")
                    else:
                        log.error("Reconnect failed, waiting 60s...")
                        time.sleep(60)
                        continue
                
                time.sleep(self.MAIN_LOOP_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                log.error(f"Error in main loop: {e}")
                import traceback
                log.error(traceback.format_exc())
                time.sleep(60)
        
        log.info("Shutting down...")
        
        self._save_pending_setups()
        self._save_awaiting_spread()
        self.disconnect()
        log.info("Bot stopped")


def main():
    """Entry point with command line arguments."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Tradr Bot - 5ers 60K High Stakes Challenge')
    parser.add_argument('--demo', action='store_true', help='Force demo mode')
    parser.add_argument('--dry-run', action='store_true', help='Run without executing trades')
    parser.add_argument('--validate-symbols', action='store_true', help='Validate symbol mapping only')
    parser.add_argument('--first-run', action='store_true', 
                        help='Force immediate market scan (use after weekend/restart)')
    parser.add_argument('--reset-state', action='store_true',
                        help='Reset challenge state files (challenge_risk_state.json, trading_days.json)')
    parser.add_argument('--reset-day-start', action='store_true',
                        help='Reset day_start_equity to current MT5 equity (use if bot missed trading days or MT5 traded without bot)')
    parser.add_argument('--set-day-start-equity', type=float,
                        help='Manually set day_start_equity to a specific value (e.g. from 5ers dashboard)')
    
    args = parser.parse_args()
    
    Path("logs").mkdir(exist_ok=True)
    
    if not MT5_LOGIN or not MT5_PASSWORD:
        print("=" * 70)
        print("TRADR BOT - CONFIGURATION REQUIRED")
        print("=" * 70)
        print("")
        print("ERROR: MT5 credentials not configured!")
        print("")
        print("Create a .env file with:")
        print("  BROKER_TYPE=forexcom_demo or fiveers_live")
        print("  MT5_SERVER=YourBrokerServer")
        print("  MT5_LOGIN=12345678")
        print("  MT5_PASSWORD=YourPassword")
        print("")
        sys.exit(1)
    
    # Handle reset-state before initializing bot
    if args.reset_state:
        print("=" * 70)
        print("🔄 RESETTING CHALLENGE STATE")
        print("=" * 70)
        
        state_files = ["challenge_risk_state.json", "trading_days.json"]
        for file in state_files:
            if os.path.exists(file):
                os.remove(file)
                print(f"✓ Removed {file}")
            else:
                print(f"⚠ {file} not found")
        
        print("State files reset. Bot will start with fresh state.")
        print("=" * 70)
    
    bot = LiveTradingBot(immediate_scan=args.first_run)
    
    # Handle reset-day-start after bot initialization but before run
    if args.reset_day_start:
        print("=" * 70)
        print("🔄 RESETTING DAY START EQUITY")
        print("=" * 70)
        
        if not bot.connect():
            print("ERROR: Could not connect to MT5 for day start reset")
            sys.exit(1)
        
        # Get current account info
        account = bot.mt5.get_account_info()
        if account:
            current_equity = account.get("equity", 0)
            print(f"Current MT5 equity: ${current_equity:,.2f}")
            
            if bot.challenge_manager:
                print(f"Old day_start_equity: ${bot.challenge_manager.day_start_equity:,.2f}")
                # Use the new method to properly update day_start_equity
                bot.challenge_manager.update_day_start_equity(current_equity)
                print(f"New day_start_equity: ${bot.challenge_manager.day_start_equity:,.2f}")
                print("✓ Day start equity updated to current equity (end of previous day)")
            else:
                print("ERROR: Challenge manager not initialized")
                sys.exit(1)
        else:
            print("ERROR: Could not get MT5 account info")
            sys.exit(1)
        
        print("Day start equity reset complete.")
        print("=" * 70)
        bot.disconnect()
        sys.exit(0)
    
    # Handle set-day-start-equity
    if args.set_day_start_equity is not None:
        print("=" * 70)
        print("🔧 MANUALLY SETTING DAY START EQUITY")
        print("=" * 70)
        
        manual_value = args.set_day_start_equity
        print(f"Requested value: ${manual_value:,.2f}")
        
        if manual_value <= 0:
            print("ERROR: Day start equity must be greater than 0")
            sys.exit(1)
        
        if not bot.connect():
            print("ERROR: Could not connect to MT5")
            sys.exit(1)
        
        # Get current account info for validation
        account = bot.mt5.get_account_info()
        if account:
            current_equity = account.get("equity", 0)
            print(f"Current MT5 equity: ${current_equity:,.2f}")
            
            if bot.challenge_manager:
                print(f"Old day_start_equity: ${bot.challenge_manager.day_start_equity:,.2f}")
                
                # Validate the manual value is reasonable
                if manual_value > current_equity * 1.5:
                    print(f"WARNING: Manual value (${manual_value:,.2f}) is much higher than current equity (${current_equity:,.2f})")
                    response = input("Continue anyway? (y/N): ")
                    if response.lower() != 'y':
                        print("Aborted.")
                        bot.disconnect()
                        sys.exit(0)
                elif manual_value < current_equity * 0.5:
                    print(f"WARNING: Manual value (${manual_value:,.2f}) is much lower than current equity (${current_equity:,.2f})")
                    response = input("Continue anyway? (y/N): ")
                    if response.lower() != 'y':
                        print("Aborted.")
                        bot.disconnect()
                        sys.exit(0)
                
                # Set the manual value
                bot.challenge_manager.day_start_equity = manual_value
                bot.challenge_manager._save_state()
                print(f"New day_start_equity: ${bot.challenge_manager.day_start_equity:,.2f}")
                print("✓ Day start equity manually set")
                
                # Calculate current DDD with new value
                daily_loss = manual_value - current_equity
                daily_loss_pct = (daily_loss / manual_value) * 100 if manual_value > 0 else 0
                
                print("")
                print(f"📊 DDD STATUS WITH NEW VALUE:")
                print(f"  Day Start (previous close): ${manual_value:,.2f}")
                print(f"  Current Equity: ${current_equity:,.2f}")
                print(f"  Daily P&L: ${current_equity - manual_value:+,.2f}")
                print(f"  DDD: {daily_loss_pct:.2f}%")
                
                # Check if halt should be active
                halt_threshold = 3.5
                if daily_loss_pct >= halt_threshold:
                    print("")
                    print(f"🚨 DDD {daily_loss_pct:.2f}% >= {halt_threshold}% - HALT WILL BE ACTIVE!")
                    print(f"   Bot will NOT trade until next daily close (00:00 server time)")
                    print(f"   At 00:10 server time the scan will execute for new day")
                    # Set halt state
                    bot.ddd_halted = True
                    bot.ddd_halt_reason = f"DDD {daily_loss_pct:.2f}% (manual equity set)"
                    bot.ddd_halt_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    bot._save_ddd_halt_state()
                    print("   ✓ DDD halt state saved")
                else:
                    print("")
                    print(f"✅ DDD {daily_loss_pct:.2f}% < {halt_threshold}% - Trading allowed")
                    # Clear any previous halt
                    if bot.ddd_halted:
                        bot.ddd_halted = False
                        bot.ddd_halt_reason = ""
                        bot._save_ddd_halt_state()
                        print("   ✓ Previous DDD halt cleared")
            else:
                print("ERROR: Challenge manager not initialized")
                sys.exit(1)
        else:
            print("ERROR: Could not get MT5 account info")
            sys.exit(1)
        
        print("")
        print("Manual day start equity setting complete.")
        print("=" * 70)
        bot.disconnect()
        sys.exit(0)
    
    bot.run()


if __name__ == "__main__":
    main()
