"""
Parameters package for FTMO Trading Bot.

Provides centralized parameter loading from optimized JSON config.
"""

from params.params_loader import (
    load_strategy_params,
    load_params_dict,
    get_min_confluence,
    get_max_concurrent_trades,
    get_risk_per_trade_pct,
    get_transaction_costs,
    save_optimized_params,
    ParamsNotFoundError,
)

__all__ = [
    "load_strategy_params",
    "load_params_dict",
    "get_min_confluence",
    "get_max_concurrent_trades",
    "get_risk_per_trade_pct",
    "get_transaction_costs",
    "save_optimized_params",
    "ParamsNotFoundError",
]
