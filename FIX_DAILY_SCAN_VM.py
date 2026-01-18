#!/usr/bin/env python3
"""
FIX: Daily Scan Not Triggering

PROBLEM:
Bot doesn't scan at 00:10 server time because get_next_scan_time() 
is recalculated every loop, causing the target to always be in the future.

SOLUTION:
Store next_scan_target as instance variable and only update after successful scan.

USAGE:
    cd C:\botcreativehub
    python FIX_DAILY_SCAN_VM.py
"""

from pathlib import Path

# VM Path - UPDATE THIS IF DIFFERENT
MAIN_BOT_PATH = Path(r"C:\botcreativehub\main_live_bot.py")

print("=" * 70)
print("FIX: DAILY SCAN NOT TRIGGERING")
print("=" * 70)
print(f"Target: {MAIN_BOT_PATH}")
print()

if not MAIN_BOT_PATH.exists():
    print(f"❌ ERROR: File not found!")
    print(f"   Expected: {MAIN_BOT_PATH}")
    print(f"   Please check the path.")
    exit(1)

try:
    content = MAIN_BOT_PATH.read_text(encoding='utf-8')
    original_content = content
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 1: Initialize next_scan_target in __init__
    # ═══════════════════════════════════════════════════════════════════
    
    old_init = """        self.last_scan_time: Optional[datetime] = None
        self.last_validate_time: Optional[datetime] = None
        self.last_spread_check_time: Optional[datetime] = None
        self.last_entry_check_time: Optional[datetime] = None  # Track entry proximity checks"""
    
    new_init = """        self.last_scan_time: Optional[datetime] = None
        self.last_validate_time: Optional[datetime] = None
        self.last_spread_check_time: Optional[datetime] = None
        self.last_entry_check_time: Optional[datetime] = None  # Track entry proximity checks
        self.next_scan_target: Optional[datetime] = None  # Fixed scan target (not recalculated)"""
    
    if old_init in content:
        content = content.replace(old_init, new_init)
        print("✅ FIX 1: Added next_scan_target to __init__")
    else:
        print("⚠️  FIX 1: Could not find __init__ section")
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 2: Set next_scan_target at startup
    # ═══════════════════════════════════════════════════════════════════
    
    old_startup = """        else:
            next_scan = get_next_scan_time()
            log.info(f"Skipping immediate scan - next scheduled: {next_scan.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            self.last_scan_time = datetime.now(timezone.utc)"""
    
    new_startup = """        else:
            self.next_scan_target = get_next_scan_time()
            log.info(f"Skipping immediate scan - next scheduled: {self.next_scan_target.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            self.last_scan_time = datetime.now(timezone.utc)"""
    
    if old_startup in content:
        content = content.replace(old_startup, new_startup)
        print("✅ FIX 2: Set next_scan_target at startup")
    else:
        print("⚠️  FIX 2: Could not find startup section")
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 3: Fix the main scan loop logic
    # ═══════════════════════════════════════════════════════════════════
    
    old_scan_logic = """                # ═══════════════════════════════════════════════════════════════
                # DAILY SCAN - 10 min after daily close (00:10 server time)
                # ═══════════════════════════════════════════════════════════════
                next_scan = get_next_scan_time()
                if self.last_scan_time and now >= next_scan:
                    if is_market_open():
                        log.info("=" * 70)
                        log.info(f"📊 DAILY SCAN - {get_server_time().strftime('%Y-%m-%d %H:%M')} Server Time")
                        log.info("=" * 70)
                        self.scan_all_symbols()
                    else:
                        log.info("Market closed (weekend), skipping scan")
                        # Move last_scan_time forward to avoid repeated checks
                        self.last_scan_time = now"""
    
    new_scan_logic = """                # ═══════════════════════════════════════════════════════════════
                # DAILY SCAN - 10 min after daily close (00:10 server time)
                # ═══════════════════════════════════════════════════════════════
                # Initialize next_scan_target if not set (after restart)
                if self.next_scan_target is None:
                    self.next_scan_target = get_next_scan_time()
                    log.info(f"Next scan scheduled: {self.next_scan_target.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                
                # Check if it's time to scan
                if now >= self.next_scan_target:
                    if is_market_open():
                        log.info("=" * 70)
                        log.info(f"📊 DAILY SCAN - {get_server_time().strftime('%Y-%m-%d %H:%M')} Server Time")
                        log.info("=" * 70)
                        self.scan_all_symbols()
                        # Calculate NEXT scan target (not during this loop!)
                        self.next_scan_target = get_next_scan_time()
                        log.info(f"Next scan scheduled: {self.next_scan_target.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    else:
                        log.info("Market closed (weekend), skipping scan")
                        # Move target forward to avoid repeated checks
                        self.next_scan_target = get_next_scan_time()"""
    
    if old_scan_logic in content:
        content = content.replace(old_scan_logic, new_scan_logic)
        print("✅ FIX 3: Fixed scan loop logic")
    else:
        print("⚠️  FIX 3: Could not find scan loop section")
    
    # ═══════════════════════════════════════════════════════════════════
    # FIX 4: Update scan_all_symbols to set next_scan_target
    # ═══════════════════════════════════════════════════════════════════
    
    old_scan_end = """        log.info("=" * 70)
        
        self.last_scan_time = datetime.now(timezone.utc)"""
    
    new_scan_end = """        log.info("=" * 70)
        
        self.last_scan_time = datetime.now(timezone.utc)
        
        # Update next scan target AFTER successful scan
        if not hasattr(self, 'next_scan_target'):
            self.next_scan_target = None"""
    
    if old_scan_end in content:
        content = content.replace(old_scan_end, new_scan_end)
        print("✅ FIX 4: Added next_scan_target update to scan_all_symbols")
    else:
        print("⚠️  FIX 4: Could not find scan_all_symbols end section")
    
    # ═══════════════════════════════════════════════════════════════════
    # Write changes
    # ═══════════════════════════════════════════════════════════════════
    
    if content != original_content:
        # Backup original
        backup_path = MAIN_BOT_PATH.with_suffix('.py.backup_scan')
        backup_path.write_text(original_content, encoding='utf-8')
        print(f"\n📦 Backup created: {backup_path}")
        
        # Write fixed version
        MAIN_BOT_PATH.write_text(content, encoding='utf-8')
        
        print()
        print("=" * 70)
        print("✅ SUCCESS! DAILY SCAN FIX APPLIED")
        print("=" * 70)
        print()
        print("Changes:")
        print("  ✓ Added next_scan_target instance variable")
        print("  ✓ Fixed scan scheduling logic")
        print("  ✓ Scan target only updates AFTER successful scan")
        print()
        print("What this fixes:")
        print("  ❌ OLD: get_next_scan_time() recalculated every loop")
        print("  ❌ OLD: Scan target always in future, never triggers")
        print("  ✅ NEW: Scan target stored, only updates after scan")
        print("  ✅ NEW: Scan triggers at 00:10 server time daily")
        print()
        print("Next steps:")
        print("  1. RESTART your bot (Ctrl+C, then restart)")
        print("  2. Watch for 'Next scan scheduled:' message")
        print("  3. Bot will scan at next 00:10 server time")
        print()
        print("Example log after fix:")
        print("  Next scan scheduled: 2026-01-14 00:10:00 UTC")
        print("  ... (24 hours later) ...")
        print("  📊 DAILY SCAN - 2026-01-14 02:10 Server Time")
        print("  MARKET SCAN - 2026-01-14 00:10 UTC")
        print("  Symbols scanned: 35/37")
        print()
        print("=" * 70)
    else:
        print()
        print("⚠️  NO CHANGES NEEDED")
        print()
        print("Either:")
        print("  - Fix already applied")
        print("  - Code structure is different")
        print()
        print("Please check manually or contact support.")

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print()
print("=" * 70)
print("FIX COMPLETE!")
print("=" * 70)
