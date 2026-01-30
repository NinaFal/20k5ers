"""
Weekend Gap Risk Management

Implements correlation-aware Tier 1 weekend position management:
- Automatically holds crypto (BTC, ETH) - no gap risk
- Closes losing positions before weekend
- Takes profit on positions > 1.6R
- Limits positions per correlation group to avoid clustered exposure
- Enforces overall position limits based on gap risk tolerance

Author: Claude Code
Created: 2026-01-19
"""

from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CORRELATION GROUPS
# ═══════════════════════════════════════════════════════════════════════════

CORRELATION_GROUPS = {
    # Group 1: USD Majors (HIGH correlation ~0.7-0.9)
    # All move together when USD strengthens/weakens
    'USD_MAJORS': ['EUR_USD', 'GBP_USD', 'AUD_USD', 'NZD_USD'],

    # Group 2: USD Inverse (USD as quote currency)
    # Inverse correlation to USD_MAJORS
    'USD_INVERSE': ['USD_JPY', 'USD_CHF', 'USD_CAD'],

    # Group 3: EUR Crosses (MEDIUM correlation ~0.5-0.7)
    'EUR_CROSSES': ['EUR_GBP', 'EUR_JPY', 'EUR_CHF', 'EUR_AUD', 'EUR_CAD', 'EUR_NZD'],

    # Group 4: GBP Crosses (MEDIUM correlation ~0.5-0.7)
    'GBP_CROSSES': ['GBP_JPY', 'GBP_CHF', 'GBP_AUD', 'GBP_CAD', 'GBP_NZD'],

    # Group 5: JPY Crosses (MEDIUM correlation ~0.4-0.6)
    'JPY_CROSSES': ['AUD_JPY', 'NZD_JPY', 'CAD_JPY', 'CHF_JPY', 'EUR_JPY', 'GBP_JPY'],

    # Group 6: Commodity Pairs (MEDIUM correlation ~0.6)
    'COMMODITY_FX': ['AUD_NZD', 'AUD_CHF', 'AUD_CAD', 'NZD_CHF', 'NZD_CAD', 'CAD_CHF'],

    # Group 7: Precious Metals (HIGH correlation ~0.8)
    # Gold and silver move together, both USD-correlated
    'METALS': ['XAU_USD', 'XAG_USD'],

    # Group 8: US Indices (VERY HIGH correlation ~0.95)
    # S&P 500 and Nasdaq almost always move together
    'US_INDICES': ['SPX500_USD', 'NAS100_USD'],

    # Group 9: Other Indices
    'OTHER_INDICES': ['UK100_USD'],

    # Group 10: Major Crypto (HIGH correlation ~0.75)
    # BTC and ETH highly correlated but NO WEEKEND GAP RISK
    'CRYPTO_MAJOR': ['BTC_USD', 'ETH_USD'],

    # Group 11: Alt Crypto (MEDIUM correlation ~0.5)
    'CRYPTO_ALT': ['XRP_USD', 'ADA_USD'],
}

# All crypto symbols (no weekend gap risk)
CRYPTO_SYMBOLS = ['BTC_USD', 'ETH_USD', 'XRP_USD', 'ADA_USD']


# ═══════════════════════════════════════════════════════════════════════════
# SYMBOL MAPPING (Broker format <-> OANDA format)
# ═══════════════════════════════════════════════════════════════════════════

BROKER_TO_OANDA = {
    # Forex Majors
    'EURUSD': 'EUR_USD',
    'GBPUSD': 'GBP_USD',
    'USDJPY': 'USD_JPY',
    'USDCHF': 'USD_CHF',
    'USDCAD': 'USD_CAD',
    'AUDUSD': 'AUD_USD',
    'NZDUSD': 'NZD_USD',

    # EUR Crosses
    'EURGBP': 'EUR_GBP',
    'EURJPY': 'EUR_JPY',
    'EURCHF': 'EUR_CHF',
    'EURAUD': 'EUR_AUD',
    'EURCAD': 'EUR_CAD',
    'EURNZD': 'EUR_NZD',

    # GBP Crosses
    'GBPJPY': 'GBP_JPY',
    'GBPCHF': 'GBP_CHF',
    'GBPAUD': 'GBP_AUD',
    'GBPCAD': 'GBP_CAD',
    'GBPNZD': 'GBP_NZD',

    # Other Crosses
    'AUDJPY': 'AUD_JPY',
    'AUDCHF': 'AUD_CHF',
    'AUDCAD': 'AUD_CAD',
    'AUDNZD': 'AUD_NZD',
    'NZDJPY': 'NZD_JPY',
    'NZDCHF': 'NZD_CHF',
    'NZDCAD': 'NZD_CAD',
    'CADJPY': 'CAD_JPY',
    'CADCHF': 'CAD_CHF',
    'CHFJPY': 'CHF_JPY',

    # Metals
    'XAUUSD': 'XAU_USD',
    'XAGUSD': 'XAG_USD',

    # Indices (broker format varies)
    'US500.cash': 'SPX500_USD',
    'US500': 'SPX500_USD',
    'SPX500': 'SPX500_USD',
    'NAS100.cash': 'NAS100_USD',
    'NAS100': 'NAS100_USD',
    'UK100.cash': 'UK100_USD',
    'UK100': 'UK100_USD',

    # Crypto
    'BTCUSD': 'BTC_USD',
    'ETHUSD': 'ETH_USD',
    'XRPUSD': 'XRP_USD',
    'ADAUSD': 'ADA_USD',
}


def convert_broker_to_oanda(broker_symbol: str) -> str:
    """Convert broker format to OANDA format"""
    return BROKER_TO_OANDA.get(broker_symbol, broker_symbol)


def is_crypto_pair(symbol: str) -> bool:
    """
    Check if symbol is crypto (works with both broker and OANDA formats)
    Crypto trades 24/7, no weekend gap risk
    """
    oanda_symbol = convert_broker_to_oanda(symbol)
    return oanda_symbol in CRYPTO_SYMBOLS


def get_correlation_group(symbol: str) -> str:
    """Return the correlation group for a symbol (OANDA format)"""
    oanda_symbol = convert_broker_to_oanda(symbol)

    for group_name, symbols in CORRELATION_GROUPS.items():
        if oanda_symbol in symbols:
            return group_name

    return 'UNCORRELATED'


# ═══════════════════════════════════════════════════════════════════════════
# POSITION HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_current_r(pos, mt5_client=None) -> float:
    """
    Calculate current R-multiple for a position
    R-multiple = (Current P&L) / (Initial Risk)
    
    NOTE: MT5 Position objects don't have price_current attribute.
    We calculate R from the profit and volume instead, or use mt5_client to get current price.
    """
    entry = pos.price_open
    sl = pos.sl
    
    # Calculate risk in price terms
    if pos.type == 0:  # BUY
        risk = abs(entry - sl)
    else:  # SELL
        risk = abs(sl - entry)
    
    if risk == 0:
        return 0.0
    
    # Method 1: If we have price_current (backtest/simulator)
    if hasattr(pos, 'price_current') and pos.price_current is not None:
        current = pos.price_current
        if pos.type == 0:  # BUY
            current_r = (current - entry) / risk
        else:  # SELL
            current_r = (entry - current) / risk
        return current_r
    
    # Method 2: Calculate from profit and volume (live MT5)
    # profit = (current - entry) * volume * contract_size for BUY
    # We can calculate: profit / (risk * volume * contract_size) ≈ R
    # But we need contract_size... use approximation from profit ratio
    if hasattr(pos, 'profit') and pos.profit is not None:
        # Get initial risk in USD (approximate)
        # If we don't have contract specs, estimate R from profit direction
        # positive profit = positive R for correctly sized trades
        # This is an approximation but works for weekend selection
        
        # Try to get current price via mt5_client
        if mt5_client is not None:
            try:
                tick = mt5_client.get_tick(pos.symbol)
                if tick:
                    current = tick.bid if pos.type == 0 else tick.ask
                    if pos.type == 0:  # BUY
                        current_r = (current - entry) / risk
                    else:  # SELL
                        current_r = (entry - current) / risk
                    return current_r
            except Exception:
                pass
        
        # Fallback: estimate R from profit sign
        # Assume risk_per_trade is ~0.7% of $20K = $140
        # This gives rough R estimate
        estimated_risk_usd = 140.0  # Conservative estimate
        estimated_r = pos.profit / estimated_risk_usd
        return estimated_r
    
    return 0.0


def is_sl_protected(pos) -> bool:
    """
    Check if SL is at breakeven or better (can't lose on gap)
    """
    entry = pos.price_open
    sl = pos.sl

    # BUY position: SL should be >= entry for protection
    if pos.type == 0:  # mt5.ORDER_TYPE_BUY
        return sl >= entry

    # SELL position: SL should be <= entry for protection
    else:  # mt5.ORDER_TYPE_SELL
        return sl <= entry


# ═══════════════════════════════════════════════════════════════════════════
# TIER 1: CORRELATION-AWARE WEEKEND POSITION SELECTOR
# ═══════════════════════════════════════════════════════════════════════════

def select_positions_for_weekend_tier1(
    positions,
    mt5_client=None,
    current_time: Optional[datetime] = None,
    max_per_group: int = 2,
    max_total_non_crypto: int = 5,
) -> dict:
    """
    TIER 1: Conservative correlation-aware weekend position selector

    Rules:
    1. Crypto: Always hold (BTC, ETH - no gap risk, trade 24/7)
    2. Close ALL losing positions (< 0R)
    3. Close ALL positions > 1.6R (take profit, avoid reversal risk)
    4. Reduce 50% of positions 0-0.5R (new positions with little profit buffer)
    5. Hold positions 0.5R-1.6R (sweet spot: has profit + upside)
    6. MAX 1-2 positions per correlation group (avoid correlation clusters)
    7. Overall max: 3-5 non-crypto positions

    Args:
        positions: List of MT5 position objects
        mt5_client: MT5 client for getting current prices (live mode)
        current_time: Current time (defaults to now UTC)
        max_per_group: Max positions per correlation group (default: 2)
        max_total_non_crypto: Max total non-crypto positions (default: 5)

    Returns:
        dict with keys:
            'HOLD': List of positions to hold
            'CLOSE': List of positions to close
            'REDUCE_50': List of positions to reduce by 50%
            'stats': Dictionary of risk statistics
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Only run Friday 16:00+ UTC (4 hours before forex close)
    if current_time.weekday() != 4 or current_time.hour < 16:
        return {
            'HOLD': list(positions),
            'CLOSE': [],
            'REDUCE_50': [],
            'stats': {
                'reason': 'Not Friday afternoon',
                'crypto': 0,
                'non_crypto': 0,
                'at_risk_positions': 0,
                'max_gap_risk_pct': 0,
            }
        }

    logger.info("═" * 70)
    logger.info("🔍 WEEKEND POSITION EVALUATION (Tier 1 Conservative)")
    logger.info("═" * 70)

    hold = []
    close = []
    reduce = []

    crypto_hold = []
    non_crypto_candidates = []

    # ═══════════════════════════════════════════════════
    # STEP 1: Apply basic rules to ALL positions
    # ═══════════════════════════════════════════════════
    for pos in positions:
        current_r = get_current_r(pos, mt5_client)
        symbol = pos.symbol
        oanda_symbol = convert_broker_to_oanda(symbol)

        # CRYPTO: Always hold (no gap risk, trades 24/7)
        if is_crypto_pair(symbol):
            hold.append(pos)
            crypto_hold.append(pos)
            logger.info(f"🪙 HOLD {oanda_symbol}: CRYPTO ({current_r:+.2f}R) - No weekend gap risk")
            continue

        # RULE 1: Close ALL losing positions (protect capital)
        if current_r < 0:
            close.append(pos)
            logger.info(f"❌ CLOSE {oanda_symbol}: LOSING ({current_r:+.2f}R)")
            continue

        # RULE 2: Close positions > 1.6R (take profit, avoid reversal)
        # At 1.6R, you've captured most of the move; risk/reward not favorable
        if current_r > 1.6:
            close.append(pos)
            logger.info(f"💰 CLOSE {oanda_symbol}: TAKE PROFIT ({current_r:+.2f}R)")
            continue

        # RULE 3: Reduce 50% if very new (0-0.5R)
        # New positions have little profit buffer; reduce exposure
        if 0 <= current_r < 0.5:
            reduce.append(pos)
            logger.info(f"⚠️ REDUCE 50% {oanda_symbol}: NEW POSITION ({current_r:+.2f}R)")
            continue

        # RULE 4: Candidates for holding (0.5R-1.6R sweet spot)
        # Has profit buffer + room to run to TP levels
        if 0.5 <= current_r <= 1.6:
            non_crypto_candidates.append(pos)
            logger.info(f"✅ CANDIDATE {oanda_symbol}: SWEET SPOT ({current_r:+.2f}R)")
            continue

    # ═══════════════════════════════════════════════════
    # STEP 2: Correlation-aware selection of non-crypto positions
    # ═══════════════════════════════════════════════════
    logger.info("")
    logger.info("─" * 70)
    logger.info("📊 CORRELATION ANALYSIS")
    logger.info("─" * 70)

    # Group candidates by correlation group
    groups_dict = {}
    for pos in non_crypto_candidates:
        symbol = pos.symbol
        oanda_symbol = convert_broker_to_oanda(symbol)
        group = get_correlation_group(symbol)

        if group not in groups_dict:
            groups_dict[group] = []
        groups_dict[group].append(pos)

    # Display groups
    for group_name, group_positions in groups_dict.items():
        symbols = [convert_broker_to_oanda(p.symbol) for p in group_positions]
        r_values = [f"{get_current_r(p, mt5_client):+.2f}R" for p in group_positions]
        logger.info(f"  {group_name}: {len(group_positions)} positions")
        for sym, r_val in zip(symbols, r_values):
            logger.info(f"    - {sym}: {r_val}")

    # ═══════════════════════════════════════════════════
    # STEP 3: Select max N positions per correlation group
    # ═══════════════════════════════════════════════════
    selected_non_crypto = []

    for group_name, group_positions in groups_dict.items():
        # Sort by current R (prefer higher R = more profit locked in, closer to BE)
        group_sorted = sorted(group_positions,
                             key=lambda p: get_current_r(p, mt5_client),
                             reverse=True)

        # Take top max_per_group from this correlation group
        keep = group_sorted[:max_per_group]
        excess = group_sorted[max_per_group:]

        selected_non_crypto.extend(keep)

        # Close excess positions from same correlation group
        for pos in excess:
            symbol = pos.symbol
            oanda_symbol = convert_broker_to_oanda(symbol)
            current_r = get_current_r(pos, mt5_client)
            close.append(pos)
            logger.info(f"⚠️ CLOSE {oanda_symbol}: EXCESS in {group_name} ({current_r:+.2f}R)")

    # ═══════════════════════════════════════════════════
    # STEP 4: Apply overall non-crypto limit
    # ═══════════════════════════════════════════════════
    if len(selected_non_crypto) > max_total_non_crypto:
        logger.warning(f"⚠️ {len(selected_non_crypto)} non-crypto positions exceeds limit of {max_total_non_crypto}")

        # Sort by current R (prefer higher R positions)
        ranked = sorted(selected_non_crypto,
                       key=lambda p: get_current_r(p, mt5_client),
                       reverse=True)

        final_keep = ranked[:max_total_non_crypto]
        final_close = ranked[max_total_non_crypto:]

        for pos in final_close:
            symbol = pos.symbol
            oanda_symbol = convert_broker_to_oanda(symbol)
            current_r = get_current_r(pos, mt5_client)
            close.append(pos)
            logger.info(f"⚠️ CLOSE {oanda_symbol}: OVERALL LIMIT EXCEEDED ({current_r:+.2f}R)")

        selected_non_crypto = final_keep

    # Final hold list = crypto + selected non-crypto
    hold.extend(selected_non_crypto)

    # ═══════════════════════════════════════════════════
    # STEP 5: Calculate gap risk exposure
    # ═══════════════════════════════════════════════════

    # Count positions with SL still in loss territory (at risk of gap)
    at_risk_positions = [p for p in selected_non_crypto if not is_sl_protected(p)]
    protected_positions = [p for p in selected_non_crypto if is_sl_protected(p)]

    num_at_risk = len(at_risk_positions)
    num_protected = len(protected_positions)

    # Assume 0.6% risk per position (configurable in ftmo_config.py)
    # Worst case: all at-risk positions gap through SL
    max_gap_loss_pct = num_at_risk * 0.6

    # ═══════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════
    logger.info("")
    logger.info("═" * 70)
    logger.info("📊 WEEKEND POSITION SUMMARY")
    logger.info("═" * 70)
    logger.info(f"  🪙 Crypto (BTC/ETH):      {len(crypto_hold)} (unlimited - no gap risk)")
    logger.info(f"  📈 Non-Crypto (Forex/etc): {len(selected_non_crypto)} (max {max_total_non_crypto})")
    logger.info(f"     - Protected (SL @ BE+): {num_protected}")
    logger.info(f"     - At Risk (SL in loss): {num_at_risk}")
    logger.info(f"  ❌ Closing:                {len(close)}")
    logger.info(f"  ⚠️ Reducing 50%:           {len(reduce)}")
    logger.info(f"  ✅ TOTAL HELD:             {len(hold)}")
    logger.info("")
    logger.info(f"  🎲 MAX WEEKEND GAP RISK:")
    logger.info(f"     - At-risk positions:   {num_at_risk}")
    logger.info(f"     - Max loss (worst):    {max_gap_loss_pct:.1f}% of account")
    logger.info(f"     - DDD limit:           5.0%")
    logger.info(f"     - Safety margin:       {5.0 - max_gap_loss_pct:.1f}%")
    logger.info("═" * 70)

    return {
        'HOLD': hold,
        'CLOSE': close,
        'REDUCE_50': reduce,
        'stats': {
            'crypto': len(crypto_hold),
            'non_crypto': len(selected_non_crypto),
            'protected': num_protected,
            'at_risk_positions': num_at_risk,
            'max_gap_risk_pct': max_gap_loss_pct,
            'total_positions_held': len(hold),
            'total_positions_closed': len(close),
            'total_positions_reduced': len(reduce),
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# FRIDAY CLOSE PRICE STORAGE (for Sunday gap detection)
# ═══════════════════════════════════════════════════════════════════════════

def store_friday_close_prices(positions, mt5_wrapper) -> dict:
    """
    Store Friday close prices for all open positions
    Used for Sunday gap detection

    Returns:
        dict: {symbol: close_price}
    """
    friday_prices = {}

    for pos in positions:
        symbol = pos.symbol
        # Try to get price_current attribute (backtest)
        if hasattr(pos, 'price_current') and pos.price_current is not None:
            current_price = pos.price_current
        else:
            # Get current price from MT5 (live)
            try:
                tick = mt5_wrapper.get_tick(symbol)
                if tick:
                    current_price = tick.bid if pos.type == 0 else tick.ask
                else:
                    logger.warning(f"Could not get price for {symbol}")
                    continue
            except Exception as e:
                logger.warning(f"Error getting price for {symbol}: {e}")
                continue
        friday_prices[symbol] = current_price

    logger.info(f"📝 Stored Friday close prices for {len(friday_prices)} symbols")

    return friday_prices


# ═══════════════════════════════════════════════════════════════════════════
# SUNDAY EVENING GAP DETECTION (22:00 UTC when forex opens)
# ═══════════════════════════════════════════════════════════════════════════

def detect_sunday_gaps(
    positions,
    friday_prices: dict,
    mt5_client=None,
    current_time: Optional[datetime] = None,
    gap_threshold_pct: float = 1.0,
    catastrophic_gap_pct: float = 2.0,
) -> dict:
    """
    Detect weekend gaps when forex markets reopen Sunday 22:00 UTC

    CRITICAL: This runs Sunday evening (22:00-23:59 UTC) when forex opens
    OR Monday morning (00:00-02:00 UTC) as backup

    Args:
        positions: Current MT5 positions
        friday_prices: Dict of {symbol: friday_close_price}
        mt5_client: MT5 client for getting current prices (live mode)
        current_time: Current time (defaults to now UTC)
        gap_threshold_pct: Log warning if gap > this % (default: 1.0%)
        catastrophic_gap_pct: Close position if adverse gap > this % (default: 2.0%)

    Returns:
        dict with keys:
            'CLOSE_IMMEDIATELY': List of positions to close (SL gapped or catastrophic gap)
            'WARNINGS': List of (position, gap_pct) for gaps > threshold
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    day_of_week = current_time.weekday()
    hour = current_time.hour

    # Sunday = 6, Monday = 0
    is_sunday_open = (day_of_week == 6 and hour >= 22)
    is_monday_morning = (day_of_week == 0 and hour < 2)

    if not (is_sunday_open or is_monday_morning):
        return {'CLOSE_IMMEDIATELY': [], 'WARNINGS': []}

    logger.info("═" * 70)
    logger.info("🚨 SUNDAY EVENING GAP DETECTION")
    logger.info("═" * 70)

    close_immediately = []
    warnings = []

    for pos in positions:
        symbol = pos.symbol
        oanda_symbol = convert_broker_to_oanda(symbol)

        # Skip crypto (no weekend gaps)
        if is_crypto_pair(symbol):
            continue

        # Get Friday close price
        friday_close = friday_prices.get(symbol)
        if friday_close is None:
            logger.warning(f"⚠️ {oanda_symbol}: No Friday close price stored, skipping gap check")
            continue

        # Get current price - try attribute first, then mt5_client
        if hasattr(pos, 'price_current') and pos.price_current is not None:
            current_price = pos.price_current
        elif mt5_client is not None:
            try:
                tick = mt5_client.get_tick(symbol)
                if tick:
                    current_price = tick.bid if pos.type == 0 else tick.ask
                else:
                    logger.warning(f"Could not get current price for {symbol}")
                    continue
            except Exception:
                logger.warning(f"Error getting price for {symbol}")
                continue
        else:
            logger.warning(f"No price available for {symbol}")
            continue

        # Calculate gap percentage
        gap_pct = abs(current_price - friday_close) / friday_close * 100

        # THRESHOLD 1: Gap > threshold - Log warning
        if gap_pct > gap_threshold_pct:
            gap_direction = "UP" if current_price > friday_close else "DOWN"
            logger.warning(
                f"⚠️ SIGNIFICANT GAP: {oanda_symbol} gapped {gap_direction} {gap_pct:.2f}% "
                f"(Friday: {friday_close:.5f}, Now: {current_price:.5f})"
            )
            warnings.append((pos, gap_pct))

        # THRESHOLD 2: SL gapped through - CLOSE IMMEDIATELY
        pos_type = "BUY" if pos.type == 0 else "SELL"
        sl_breached = False

        # Use current_price for SL breach check
        if pos_type == "BUY" and current_price < pos.sl:
            sl_breached = True
        elif pos_type == "SELL" and current_price > pos.sl:
            sl_breached = True

        if sl_breached:
            logger.critical(
                f"🚨 GAP THROUGH SL: {oanda_symbol} ticket {pos.ticket} "
                f"SL={pos.sl:.5f}, Current={current_price:.5f}, Gap={gap_pct:.2f}%"
            )
            close_immediately.append(pos)
            continue

        # THRESHOLD 3: Catastrophic adverse gap - Close even if SL not hit
        # Prevents massive losses from extreme gaps (Brexit, Swiss Franc, etc.)
        current_r = get_current_r(pos, mt5_client)
        adverse_gap_pct = 0

        if pos_type == "BUY" and current_price < friday_close:
            adverse_gap_pct = (friday_close - current_price) / friday_close * 100
        elif pos_type == "SELL" and current_price > friday_close:
            adverse_gap_pct = (current_price - friday_close) / friday_close * 100

        if adverse_gap_pct > catastrophic_gap_pct:
            logger.critical(
                f"🚨 CATASTROPHIC GAP: {oanda_symbol} ticket {pos.ticket} "
                f"gapped {adverse_gap_pct:.2f}% AGAINST position (Current R: {current_r:+.2f}R)"
            )
            close_immediately.append(pos)
            continue

    # Summary
    logger.info("")
    logger.info("─" * 70)
    logger.info(f"  Significant gaps detected: {len(warnings)}")
    logger.info(f"  Positions to close immediately: {len(close_immediately)}")
    logger.info("═" * 70)

    return {
        'CLOSE_IMMEDIATELY': close_immediately,
        'WARNINGS': warnings,
    }
