#!/usr/bin/env python3
"""
Test script for weekend_gap_manager.py

Tests the correlation-aware Tier 1 weekend position selector
"""

from datetime import datetime, timezone
import weekend_gap_manager as wgm


class MockPosition:
    """Mock MT5 position for testing"""
    def __init__(self, symbol, price_open, price_current, sl, position_type, ticket=1000):
        self.symbol = symbol
        self.price_open = price_open
        self.price_current = price_current
        self.sl = sl
        self.type = position_type  # 0=BUY, 1=SELL
        self.ticket = ticket
        self.profit = 0.0
        self.volume = 1.0


def test_correlation_groups():
    """Test that symbols are correctly mapped to correlation groups"""
    print("=" * 70)
    print("TEST 1: Correlation Group Mapping")
    print("=" * 70)

    test_cases = [
        ("EURUSD", "USD_MAJORS"),
        ("GBPUSD", "USD_MAJORS"),
        ("XAUUSD", "METALS"),
        ("XAGUSD", "METALS"),
        ("BTCUSD", "CRYPTO_MAJOR"),
        ("ETHUSD", "CRYPTO_MAJOR"),
        ("US500.cash", "US_INDICES"),
        ("NAS100.cash", "US_INDICES"),
    ]

    for symbol, expected_group in test_cases:
        group = wgm.get_correlation_group(symbol)
        status = "✓" if group == expected_group else "✗"
        print(f"  {status} {symbol}: {group} (expected: {expected_group})")

    print()


def test_crypto_detection():
    """Test crypto pair detection"""
    print("=" * 70)
    print("TEST 2: Crypto Detection")
    print("=" * 70)

    test_cases = [
        ("BTCUSD", True),
        ("ETHUSD", True),
        ("EURUSD", False),
        ("XAUUSD", False),
    ]

    for symbol, is_crypto in test_cases:
        result = wgm.is_crypto_pair(symbol)
        status = "✓" if result == is_crypto else "✗"
        print(f"  {status} {symbol}: {result} (expected: {is_crypto})")

    print()


def test_r_calculation():
    """Test R-multiple calculation"""
    print("=" * 70)
    print("TEST 3: R-Multiple Calculation")
    print("=" * 70)

    # BUY position: entry=1.1000, current=1.1060, SL=1.0900
    # Risk = 1.1000 - 1.0900 = 0.0100
    # P&L = 1.1060 - 1.1000 = 0.0060
    # R = 0.0060 / 0.0100 = 0.6R
    pos1 = MockPosition("EURUSD", 1.1000, 1.1060, 1.0900, 0)
    r1 = wgm.get_current_r(pos1)
    print(f"  BUY position: {r1:.2f}R (expected: ~0.60R)")

    # SELL position: entry=1.1000, current=1.0940, SL=1.1100
    # Risk = 1.1100 - 1.1000 = 0.0100
    # P&L = 1.1000 - 1.0940 = 0.0060
    # R = 0.0060 / 0.0100 = 0.6R
    pos2 = MockPosition("EURUSD", 1.1000, 1.0940, 1.1100, 1)
    r2 = wgm.get_current_r(pos2)
    print(f"  SELL position: {r2:.2f}R (expected: ~0.60R)")

    print()


def test_friday_position_selection():
    """Test Friday position selection logic"""
    print("=" * 70)
    print("TEST 4: Friday Position Selection (Tier 1)")
    print("=" * 70)

    # Create mock positions with various R-multiples and correlation groups
    positions = [
        # Crypto - should ALWAYS hold
        MockPosition("BTCUSD", 50000, 50400, 49500, 0, 1001),  # BTC +0.8R
        MockPosition("ETHUSD", 3000, 3033, 2970, 0, 1002),     # ETH +1.1R

        # USD_MAJORS - max 2 from this group
        MockPosition("EURUSD", 1.1000, 1.1130, 1.0900, 0, 1003),  # EUR +1.3R (should hold)
        MockPosition("GBPUSD", 1.2000, 1.2090, 1.1900, 0, 1004),  # GBP +0.9R (should hold)
        MockPosition("AUDUSD", 0.7000, 0.7070, 0.6900, 0, 1005),  # AUD +0.7R (excess - close)

        # METALS - 2 positions
        MockPosition("XAUUSD", 2000, 2024, 1980, 0, 1006),     # XAU +1.2R (should hold)
        MockPosition("XAGUSD", 25.00, 25.15, 24.85, 0, 1007),  # XAG +0.6R (correlated - close)

        # US_INDICES - 2 positions
        MockPosition("US500.cash", 4500, 4563, 4455, 0, 1008),    # SPX +1.4R (should hold)
        MockPosition("NAS100.cash", 15000, 15165, 14850, 0, 1009), # NAS +1.1R (correlated - close)

        # Losing position - should close
        MockPosition("USDJPY", 145.00, 144.70, 144.50, 0, 1010),  # JPY -0.3R (losing - close)

        # New position - should reduce 50%
        MockPosition("EURJPY", 160.00, 160.40, 159.00, 0, 1011),  # EURJPY +0.4R (reduce)

        # Position > 1.6R - should close (take profit)
        MockPosition("GBPJPY", 180.00, 180.99, 179.00, 0, 1012),  # GBPJPY +1.7R (close)
    ]

    # Simulate Friday 18:00 UTC
    friday_afternoon = datetime(2026, 1, 16, 18, 0, tzinfo=timezone.utc)  # Friday

    result = wgm.select_positions_for_weekend_tier1(
        positions=positions,
        current_time=friday_afternoon,
        max_per_group=2,
        max_total_non_crypto=5,
    )

    print(f"\n📊 RESULTS:")
    print(f"  HOLD: {len(result['HOLD'])} positions")
    for pos in result['HOLD']:
        symbol = wgm.convert_broker_to_oanda(pos.symbol)
        r = wgm.get_current_r(pos)
        group = wgm.get_correlation_group(pos.symbol)
        print(f"    ✅ {symbol}: {r:+.2f}R ({group})")

    print(f"\n  CLOSE: {len(result['CLOSE'])} positions")
    for pos in result['CLOSE']:
        symbol = wgm.convert_broker_to_oanda(pos.symbol)
        r = wgm.get_current_r(pos)
        print(f"    ❌ {symbol}: {r:+.2f}R")

    print(f"\n  REDUCE 50%: {len(result['REDUCE_50'])} positions")
    for pos in result['REDUCE_50']:
        symbol = wgm.convert_broker_to_oanda(pos.symbol)
        r = wgm.get_current_r(pos)
        print(f"    ⚠️ {symbol}: {r:+.2f}R")

    print(f"\n  Max Gap Risk: {result['stats']['max_gap_risk_pct']:.1f}%")

    print()


def test_sunday_gap_detection():
    """Test Sunday gap detection logic"""
    print("=" * 70)
    print("TEST 5: Sunday Gap Detection")
    print("=" * 70)

    # Create mock positions
    positions = [
        # Position where SL was gapped (should close immediately)
        MockPosition("EURUSD", 1.1000, 1.0850, 1.0900, 0, 2001),  # Friday: 1.1000, Now: 1.0850, SL: 1.0900

        # Position with significant but not catastrophic gap
        MockPosition("GBPUSD", 1.2000, 1.1970, 1.1900, 0, 2002),  # Small gap

        # Crypto (no gap risk)
        MockPosition("BTCUSD", 50000, 49500, 49000, 0, 2003),  # BTC (should skip)
    ]

    friday_prices = {
        "EURUSD": 1.1000,
        "GBPUSD": 1.2000,
        "BTCUSD": 50000,
    }

    # Simulate Sunday 22:00 UTC
    sunday_evening = datetime(2026, 1, 18, 22, 0, tzinfo=timezone.utc)  # Sunday

    result = wgm.detect_sunday_gaps(
        positions=positions,
        friday_prices=friday_prices,
        current_time=sunday_evening,
        gap_threshold_pct=1.0,
        catastrophic_gap_pct=2.0,
    )

    print(f"\n📊 RESULTS:")
    print(f"  CLOSE IMMEDIATELY: {len(result['CLOSE_IMMEDIATELY'])} positions")
    for pos in result['CLOSE_IMMEDIATELY']:
        symbol = wgm.convert_broker_to_oanda(pos.symbol)
        print(f"    🚨 {symbol} (ticket {pos.ticket})")

    print(f"\n  WARNINGS: {len(result['WARNINGS'])} gaps detected")
    for pos, gap_pct in result['WARNINGS']:
        symbol = wgm.convert_broker_to_oanda(pos.symbol)
        print(f"    ⚠️ {symbol}: {gap_pct:.2f}% gap")

    print()


if __name__ == "__main__":
    print("\n🧪 WEEKEND GAP MANAGER TESTS\n")

    test_correlation_groups()
    test_crypto_detection()
    test_r_calculation()
    test_friday_position_selection()
    test_sunday_gap_detection()

    print("=" * 70)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 70)
