# FTMO Compliance Implementation Guide

## Critical Issue: Daily Loss Not Tracked in Backtest

The current backtest (`ftmo_challenge_analyzer.py`) does NOT track daily loss limits. This means:
- Trades that would be blocked in live trading are simulated
- Backtest shows 25.9% max DD which would FAIL FTMO (10% limit)
- In reality, the challenge would fail at 5% daily loss

## Implementation Plan

### Step 1: Add Compliance State Tracking

Add this class to `ftmo_challenge_analyzer.py` (before `run_full_period_backtest`):

```python
@dataclass
class FTMOComplianceTracker:
    """Track FTMO compliance during backtest simulation."""
    
    account_size: float = 200000.0
    current_balance: float = 200000.0
    highest_balance: float = 200000.0
    day_start_balance: float = 200000.0
    current_day: Optional[date] = None
    
    # Tracking stats
    trades_skipped_daily: int = 0
    trades_skipped_dd: int = 0
    trades_skipped_streak: int = 0
    consecutive_losses: int = 0
    halted_reason: Optional[str] = None
    
    # FTMO Limits
    DAILY_LOSS_HALT_PCT: float = 4.2  # Halt before 5%
    TOTAL_DD_HALT_PCT: float = 8.0    # Halt before 10%
    CONSECUTIVE_LOSS_HALT: int = 5    # Halt after N losses
    
    @property
    def daily_loss_pct(self) -> float:
        """Current daily loss as percentage."""
        if self.current_balance >= self.day_start_balance:
            return 0.0
        return ((self.day_start_balance - self.current_balance) / self.day_start_balance) * 100
    
    @property
    def total_dd_pct(self) -> float:
        """Current total drawdown as percentage."""
        if self.current_balance >= self.account_size:
            return 0.0
        return ((self.account_size - self.current_balance) / self.account_size) * 100
    
    def check_new_day(self, trade_date: date) -> None:
        """Check if it's a new trading day and reset daily tracking."""
        if trade_date != self.current_day:
            self.current_day = trade_date
            self.day_start_balance = self.current_balance
    
    def can_take_trade(self, potential_loss: float) -> Tuple[bool, str]:
        """
        Check if a trade can be taken given current compliance state.
        
        Args:
            potential_loss: Maximum potential loss in USD (if SL hit)
        
        Returns:
            (can_trade, reason)
        """
        # Check consecutive losses
        if self.consecutive_losses >= self.CONSECUTIVE_LOSS_HALT:
            self.trades_skipped_streak += 1
            return False, f"Streak halt: {self.consecutive_losses} consecutive losses"
        
        # Check daily loss before trade
        if self.daily_loss_pct >= self.DAILY_LOSS_HALT_PCT:
            self.trades_skipped_daily += 1
            return False, f"Daily loss halt: {self.daily_loss_pct:.1f}% >= {self.DAILY_LOSS_HALT_PCT}%"
        
        # Check total DD before trade
        if self.total_dd_pct >= self.TOTAL_DD_HALT_PCT:
            self.trades_skipped_dd += 1
            return False, f"Total DD halt: {self.total_dd_pct:.1f}% >= {self.TOTAL_DD_HALT_PCT}%"
        
        # Check if trade would breach daily limit
        simulated_balance = self.current_balance - abs(potential_loss)
        simulated_daily_loss = ((self.day_start_balance - simulated_balance) / self.day_start_balance) * 100
        
        if simulated_daily_loss >= 5.0:  # Hard FTMO limit
            self.trades_skipped_daily += 1
            return False, f"Would breach daily: {simulated_daily_loss:.1f}%"
        
        # Check if trade would breach total DD limit
        simulated_total_dd = ((self.account_size - simulated_balance) / self.account_size) * 100
        
        if simulated_total_dd >= 10.0:  # Hard FTMO limit
            self.trades_skipped_dd += 1
            return False, f"Would breach total DD: {simulated_total_dd:.1f}%"
        
        return True, "OK"
    
    def update_after_trade(self, pnl: float) -> bool:
        """
        Update tracker after a trade completes.
        
        Args:
            pnl: Trade P&L in USD (positive = profit, negative = loss)
        
        Returns:
            True if challenge is still valid, False if failed
        """
        self.current_balance += pnl
        
        # Update consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Update highest balance
        if self.current_balance > self.highest_balance:
            self.highest_balance = self.current_balance
        
        # Check for hard limit breach
        if self.daily_loss_pct >= 5.0:
            self.halted_reason = f"FAILED: Daily loss {self.daily_loss_pct:.1f}% >= 5%"
            return False
        
        if self.total_dd_pct >= 10.0:
            self.halted_reason = f"FAILED: Total DD {self.total_dd_pct:.1f}% >= 10%"
            return False
        
        return True
    
    def get_report(self) -> Dict:
        """Get compliance tracking report."""
        return {
            'final_balance': self.current_balance,
            'total_return_pct': ((self.current_balance - self.account_size) / self.account_size) * 100,
            'max_dd_pct': self.total_dd_pct,
            'trades_skipped_daily': self.trades_skipped_daily,
            'trades_skipped_dd': self.trades_skipped_dd,
            'trades_skipped_streak': self.trades_skipped_streak,
            'total_skipped': self.trades_skipped_daily + self.trades_skipped_dd + self.trades_skipped_streak,
            'halted_reason': self.halted_reason,
            'challenge_passed': self.halted_reason is None,
        }
```

### Step 2: Integrate into run_full_period_backtest

Modify `run_full_period_backtest()` to use the compliance tracker:

```python
def run_full_period_backtest(
    start_date: datetime,
    end_date: datetime,
    min_confluence: int = 3,
    min_quality_factors: int = 1,
    risk_per_trade_pct: float = 0.5,
    # ... existing params ...
    # NEW: Compliance parameters
    daily_loss_halt_pct: float = 4.2,
    total_dd_halt_pct: float = 8.0,
    consecutive_loss_halt: int = 5,
    enable_compliance_tracking: bool = True,  # Can disable for comparison
) -> Tuple[List[Trade], Dict]:
    """
    Run backtest with FTMO-compliant circuit breakers.
    
    Returns:
        Tuple of (trades_list, compliance_report)
    """
    # Initialize compliance tracker
    tracker = FTMOComplianceTracker(
        account_size=ACCOUNT_SIZE,
        DAILY_LOSS_HALT_PCT=daily_loss_halt_pct,
        TOTAL_DD_HALT_PCT=total_dd_halt_pct,
        CONSECUTIVE_LOSS_HALT=consecutive_loss_halt,
    )
    
    # ... existing asset loop to generate all potential trades ...
    
    # Sort all trades by entry date for sequential processing
    all_potential_trades.sort(key=lambda t: t.entry_date)
    
    accepted_trades = []
    
    for trade in all_potential_trades:
        if not enable_compliance_tracking:
            accepted_trades.append(trade)
            continue
        
        # Get trade date
        trade_date = trade.entry_date.date() if hasattr(trade.entry_date, 'date') else trade.entry_date
        
        # Check for new day
        tracker.check_new_day(trade_date)
        
        # Calculate potential loss
        risk_usd = ACCOUNT_SIZE * (risk_per_trade_pct / 100.0)
        
        # Check if trade can be taken
        can_trade, reason = tracker.can_take_trade(risk_usd)
        
        if not can_trade:
            continue  # Skip this trade
        
        # Simulate trade outcome
        trade_pnl = trade.rr * risk_usd
        
        # Update tracker
        challenge_valid = tracker.update_after_trade(trade_pnl)
        
        if not challenge_valid:
            break  # Challenge failed, stop processing
        
        accepted_trades.append(trade)
    
    return accepted_trades, tracker.get_report()
```

### Step 3: Update Objective Function

Update the objective function to handle compliance reports:

```python
def objective_ftmo_v3(trial: optuna.Trial) -> float:
    # ... parameter setup ...
    
    training_trades, compliance_report = run_full_period_backtest(
        start_date=TRAINING_START,
        end_date=TRAINING_END,
        # ... existing params ...
        daily_loss_halt_pct=params.get('daily_loss_halt_pct', 4.2),
        total_dd_halt_pct=8.0,
        consecutive_loss_halt=params.get('consecutive_loss_halt', 5),
        enable_compliance_tracking=True,
    )
    
    # Store compliance stats
    trial.set_user_attr('compliance', compliance_report)
    
    # Penalize failed challenges
    if not compliance_report['challenge_passed']:
        return -100000.0  # Severe penalty for FTMO breach
    
    # Penalize high skip rates
    skip_rate = compliance_report['total_skipped'] / max(len(training_trades) + compliance_report['total_skipped'], 1)
    if skip_rate > 0.5:
        # More than 50% of trades skipped - too conservative
        return -50000.0
    
    # ... rest of objective calculation ...
```

### Step 4: Position Sizing with Streak Reduction

Add this to the trade simulation:

```python
def calculate_dynamic_risk(
    base_risk_pct: float,
    consecutive_losses: int,
    daily_loss_pct: float,
    total_dd_pct: float,
) -> float:
    """
    Calculate dynamic risk based on current state.
    
    Returns reduced risk % when in drawdown.
    """
    risk = base_risk_pct
    
    # Reduce for consecutive losses (10% per loss, max 40%)
    if consecutive_losses > 0:
        reduction = min(consecutive_losses * 0.10, 0.40)
        risk *= (1 - reduction)
    
    # Reduce for daily loss warning
    if daily_loss_pct >= 2.5:
        risk *= 0.7  # 30% reduction
    elif daily_loss_pct >= 1.5:
        risk *= 0.85  # 15% reduction
    
    # Reduce for total DD warning
    if total_dd_pct >= 5.0:
        risk *= 0.7  # 30% reduction
    elif total_dd_pct >= 3.0:
        risk *= 0.85  # 15% reduction
    
    # Never go below 0.2% or above base
    return max(0.2, min(base_risk_pct, risk))
```

---

## Expected Impact

| Metric | Before | After Compliance |
|--------|--------|------------------|
| Max DD | 25.9% | **<10%** |
| Trades Taken | 1536 | ~800-1000 |
| Win Rate | 48% | 48-52% |
| Challenge Pass | ❌ | ✅ |

The trade count will be lower because:
1. Trades are skipped when approaching daily limit
2. Trades are skipped when approaching total DD limit
3. Trades are skipped after 5 consecutive losses

But the challenge will PASS because we never breach FTMO limits.

---

## Testing the Implementation

Add this test function:

```python
def test_compliance_tracking():
    """Test that compliance tracking works correctly."""
    from datetime import datetime
    
    # Run backtest WITHOUT compliance
    trades_no_compliance, _ = run_full_period_backtest(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 6, 30),
        enable_compliance_tracking=False,
    )
    
    # Run backtest WITH compliance
    trades_with_compliance, report = run_full_period_backtest(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 6, 30),
        enable_compliance_tracking=True,
    )
    
    print(f"Trades without compliance: {len(trades_no_compliance)}")
    print(f"Trades with compliance: {len(trades_with_compliance)}")
    print(f"Trades skipped: {report['total_skipped']}")
    print(f"Challenge passed: {report['challenge_passed']}")
    print(f"Max DD: {report['max_dd_pct']:.1f}%")
    
    # Verify compliance version has lower DD
    assert report['max_dd_pct'] < 10.0, "Compliance tracking should prevent >10% DD"
    assert len(trades_with_compliance) <= len(trades_no_compliance), "Compliance should skip some trades"
```

---

## Files to Modify

1. **ftmo_challenge_analyzer.py**
   - Add `FTMOComplianceTracker` class (~line 350)
   - Modify `run_full_period_backtest()` (~line 596)
   - Modify `objective_ftmo_v2()` (~line 1035)

2. **params/current_params.json**
   - Add new compliance parameters

3. **ftmo_config.py**
   - No changes needed (already has limits defined)

---

## Rollback Plan

If compliance tracking causes issues:

```python
# Quick disable: Add parameter to run_full_period_backtest
enable_compliance_tracking=False  # Skip all compliance checks
```

This allows testing with and without compliance for comparison.
