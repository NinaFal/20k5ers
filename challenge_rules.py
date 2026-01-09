"""
5ers 60K High Stakes Challenge Rules Definition
Defines the rules for the 5ers 60K High Stakes challenge
"""

from dataclasses import dataclass


@dataclass
class ChallengeRules:
    """5ers High Stakes Challenge rules and constraints"""
    account_currency: str = "USD"
    account_size: float = 60000.0  # $60K High Stakes
    max_daily_loss_pct: float = 5.0  # 5% daily loss limit ($3,000)
    max_total_drawdown_pct: float = 10.0  # 10% total drawdown limit ($6,000)
    risk_per_trade_pct: float = 0.6  # 0.6% risk per trade ($360 per R)
    max_open_risk_pct: float = 3.0  # Max 3% cumulative open risk
    
    # Profit targets (5ers specific)
    step1_profit_target_pct: float = 8.0   # Phase 1: 8% profit target ($4,800)
    step2_profit_target_pct: float = 5.0   # Phase 2: 5% profit target ($3,000)
    
    # Trading requirements (5ers requires 3 profitable days)
    min_profitable_days: int = 3  # 5ers requires 3 profitable days
    profitable_day_threshold_pct: float = 0.5  # Day counts as profitable if >0.5% profit
    
    # Position limits
    max_concurrent_trades: int = 7
    max_pending_orders: int = 20
    max_trades_per_day: int = 10
    
    # 5ers specific
    max_inactive_days: int = 30  # Account expires after 30 days inactivity
    first_payout_days: int = 14  # First payout after 14 days
    payout_frequency_days: int = 14  # Bi-weekly payouts
    profit_split_min: int = 80  # 80% profit split minimum
    profit_split_max: int = 100  # Up to 100% profit split


# Create the default 5ers 60K High Stakes rules
FIVEERS_60K_RULES = ChallengeRules(
    account_currency="USD",
    account_size=60000.0,
    max_daily_loss_pct=5.0,
    max_total_drawdown_pct=10.0,
    risk_per_trade_pct=0.6,
    max_open_risk_pct=3.0,
    step1_profit_target_pct=8.0,
    step2_profit_target_pct=5.0,
    min_profitable_days=3,
    profitable_day_threshold_pct=0.5,
    max_concurrent_trades=7,
    max_pending_orders=20,
    max_trades_per_day=10,
)

# Backward compatibility alias
FIVERS_10K_RULES = FIVEERS_60K_RULES
