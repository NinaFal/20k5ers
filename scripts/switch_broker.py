#!/usr/bin/env python3
"""
Broker Switching Utility

Easily switch between Forex.com Demo and 5ers Live accounts.

Usage:
    python scripts/switch_broker.py demo      # Switch to Forex.com Demo
    python scripts/switch_broker.py live      # Switch to 5ers Live
    python scripts/switch_broker.py status    # Show current config
"""

import sys
import shutil
from pathlib import Path


def get_project_root():
    """Get project root directory."""
    return Path(__file__).parent.parent


def switch_to_demo():
    """Switch to Forex.com Demo configuration."""
    root = get_project_root()
    demo_env = root / ".env.forexcom_demo"
    active_env = root / ".env"
    
    if not demo_env.exists():
        print(f"❌ Demo config not found: {demo_env}")
        return False
    
    # Backup current .env if exists
    if active_env.exists():
        backup = root / ".env.backup"
        shutil.copy(active_env, backup)
        print(f"📦 Backed up current .env to .env.backup")
    
    # Copy demo config
    shutil.copy(demo_env, active_env)
    print(f"✅ Switched to Forex.com Demo (account 531, $50,000)")
    print(f"📝 Updated: {active_env}")
    print()
    print("⚠️  IMPORTANT:")
    print("   1. Edit .env and add your MT5_PASSWORD")
    print("   2. Verify MT5_SERVER=Forex.comGlobal-Demo")
    print("   3. Test with: python main_live_bot.py --first-run")
    
    return True


def switch_to_live():
    """Switch to 5ers Live configuration."""
    root = get_project_root()
    live_env = root / ".env.fiveers_live"
    active_env = root / ".env"
    
    if not live_env.exists():
        print(f"❌ Live config not found: {live_env}")
        return False
    
    # Backup current .env if exists
    if active_env.exists():
        backup = root / ".env.backup"
        shutil.copy(active_env, backup)
        print(f"📦 Backed up current .env to .env.backup")
    
    # Copy live config
    shutil.copy(live_env, active_env)
    print(f"✅ Switched to 5ers 60K High Stakes Live ($60,000)")
    print(f"📝 Updated: {active_env}")
    print()
    print("⚠️  LIVE TRADING - CRITICAL CHECKLIST:")
    print("   1. Edit .env and add your 5ers MT5_LOGIN")
    print("   2. Edit .env and add your 5ers MT5_PASSWORD")
    print("   3. Verify MT5_SERVER=5ersLtd-Server")
    print("   4. Test connection: python -c 'from broker_config import get_broker_config; get_broker_config().print_summary()'")
    print("   5. Run with: python main_live_bot.py --first-run")
    
    return True


def show_status():
    """Show current broker configuration."""
    root = get_project_root()
    active_env = root / ".env"
    
    if not active_env.exists():
        print("❌ No active .env file found!")
        print("   Run: python scripts/switch_broker.py demo")
        return
    
    # Read current config
    with open(active_env, "r") as f:
        content = f.read()
    
    # Extract key values
    broker_type = None
    mt5_login = None
    account_size = None
    mt5_server = None
    
    for line in content.split("\n"):
        if line.startswith("BROKER_TYPE="):
            broker_type = line.split("=")[1].strip()
        elif line.startswith("MT5_LOGIN="):
            mt5_login = line.split("=")[1].strip()
        elif line.startswith("ACCOUNT_SIZE="):
            account_size = line.split("=")[1].strip()
        elif line.startswith("MT5_SERVER="):
            mt5_server = line.split("=")[1].strip()
    
    print("=" * 70)
    print("CURRENT BROKER CONFIGURATION")
    print("=" * 70)
    print(f"  Broker Type:    {broker_type or 'Unknown'}")
    print(f"  MT5 Server:     {mt5_server or 'Unknown'}")
    print(f"  MT5 Login:      {mt5_login or 'Unknown'}")
    print(f"  Account Size:   ${account_size or 'Unknown'}")
    print("=" * 70)
    
    if broker_type == "forexcom_demo":
        print("📊 Running in DEMO mode (Forex.com)")
    elif broker_type == "fiveers_live":
        print("⚠️  Running in LIVE mode (5ers)")
    
    print()
    print("Available commands:")
    print("  python scripts/switch_broker.py demo   # Switch to demo")
    print("  python scripts/switch_broker.py live   # Switch to live")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/switch_broker.py [demo|live|status]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command in ("demo", "forexcom", "test"):
        success = switch_to_demo()
        sys.exit(0 if success else 1)
    
    elif command in ("live", "5ers", "fiveers", "production"):
        # Extra confirmation for live
        print("⚠️  WARNING: You are about to switch to LIVE TRADING mode!")
        print("   This will trade real money on your 5ers account.")
        print()
        confirm = input("Type 'YES' to confirm: ")
        if confirm != "YES":
            print("❌ Cancelled")
            sys.exit(1)
        
        success = switch_to_live()
        sys.exit(0 if success else 1)
    
    elif command in ("status", "show", "current"):
        show_status()
        sys.exit(0)
    
    else:
        print(f"❌ Unknown command: {command}")
        print("   Valid commands: demo, live, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
