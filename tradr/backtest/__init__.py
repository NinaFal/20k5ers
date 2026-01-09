"""
Backtest module for tradr.

Provides H1-based trade simulation that matches strategy_core.py logic.
"""

from .h1_trade_simulator import (
    H1TradeSimulator,
    TradeSetup,
    TradeResult,
    simulate_trades_with_h1,
    TP1_R, TP2_R, TP3_R, TP4_R, TP5_R,
    TP1_CLOSE_PCT, TP2_CLOSE_PCT, TP3_CLOSE_PCT, TP4_CLOSE_PCT, TP5_CLOSE_PCT,
    TRAIL_ACTIVATION_R,
)

__all__ = [
    'H1TradeSimulator',
    'TradeSetup',
    'TradeResult',
    'simulate_trades_with_h1',
    'TP1_R', 'TP2_R', 'TP3_R', 'TP4_R', 'TP5_R',
    'TP1_CLOSE_PCT', 'TP2_CLOSE_PCT', 'TP3_CLOSE_PCT', 'TP4_CLOSE_PCT', 'TP5_CLOSE_PCT',
    'TRAIL_ACTIVATION_R',
]
