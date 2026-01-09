#!/usr/bin/env python3
"""
Setup Windows Task Scheduler for Trading Bot

This script creates a Windows Task Scheduler entry to:
1. Auto-start bot on Windows login
2. Keep bot running in background
3. Restart bot if it crashes

Run this ONCE on your Windows VM:
    python scripts/setup_windows_task.py
"""

import os
import sys
from pathlib import Path


def create_task_xml(project_dir: Path, python_exe: str) -> str:
    """Create Task Scheduler XML configuration."""
    
    # Get absolute paths
    bot_script = project_dir / "main_live_bot.py"
    log_dir = project_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>2026-01-04T00:00:00</Date>
    <Author>{os.environ.get('USERNAME', 'TradingBot')}</Author>
    <Description>Forex.com Demo Trading Bot - Auto-restart on failure</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT1M</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
    <RestartOnFailure>
      <Interval>PT5M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{bot_script}"</Arguments>
      <WorkingDirectory>{project_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
    
    return xml


def setup_task_scheduler():
    """Setup Windows Task Scheduler task."""
    
    print("=" * 70)
    print("WINDOWS TASK SCHEDULER SETUP")
    print("=" * 70)
    
    # Get project directory
    project_dir = Path(__file__).parent.parent.absolute()
    print(f"\nProject directory: {project_dir}")
    
    # Find Python executable
    python_exe = sys.executable
    print(f"Python executable: {python_exe}")
    
    # Create XML file
    xml_content = create_task_xml(project_dir, python_exe)
    xml_file = project_dir / "trading_bot_task.xml"
    
    with open(xml_file, "w", encoding="utf-16") as f:
        f.write(xml_content)
    
    print(f"\n✅ Created task XML: {xml_file}")
    
    # Generate schtasks command
    task_name = "ForexComDemoTradingBot"
    
    print("\n" + "=" * 70)
    print("INSTALLATION COMMANDS")
    print("=" * 70)
    print("\n📋 Copy and paste these commands into Command Prompt (as Administrator):\n")
    
    print(f'cd /d "{project_dir}"')
    print(f'schtasks /Create /XML "{xml_file}" /TN "{task_name}"')
    
    print("\n" + "=" * 70)
    print("TASK MANAGEMENT COMMANDS")
    print("=" * 70)
    
    print(f"\n✅ Start task manually:")
    print(f'   schtasks /Run /TN "{task_name}"')
    
    print(f"\n⏹️  Stop task:")
    print(f'   schtasks /End /TN "{task_name}"')
    
    print(f"\n🔍 Check task status:")
    print(f'   schtasks /Query /TN "{task_name}" /V /FO LIST')
    
    print(f"\n🗑️  Delete task:")
    print(f'   schtasks /Delete /TN "{task_name}" /F')
    
    print("\n" + "=" * 70)
    print("ALTERNATIVE: GUI METHOD")
    print("=" * 70)
    print("\n1. Press Windows+R")
    print("2. Type: taskschd.msc")
    print("3. Click 'Import Task...'")
    print(f"4. Select: {xml_file}")
    print("5. Click OK")
    
    print("\n" + "=" * 70)
    print("WHAT THIS DOES")
    print("=" * 70)
    print("\n✅ Auto-starts bot 1 minute after Windows login")
    print("✅ Restarts bot if it crashes (3 attempts, 5 min apart)")
    print("✅ Runs in background (no window)")
    print("✅ Logs to logs/trading_bot.log")
    print("✅ You can disconnect RDP - bot keeps running!")
    
    print("\n" + "=" * 70)
    print("IMPORTANT: RDP DISCONNECT (NOT CLOSE)")
    print("=" * 70)
    print("\n⚠️  To keep VM running after you leave:")
    print("   1. Click Start menu")
    print("   2. Click your user icon")
    print("   3. Select 'Disconnect' (NOT 'Sign out' or 'Shut down')")
    print("   OR: Just close RDP window (X button)")
    print("\n✅ VM stays running, bot keeps trading!")
    print("❌ DO NOT shut down or sign out!")
    
    return xml_file


if __name__ == "__main__":
    xml_file = setup_task_scheduler()
    
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("\n1. Open Command Prompt as Administrator")
    print("2. Copy the commands above")
    print("3. Paste and run them")
    print("4. Check task is created: taskschd.msc")
    print("5. Test: schtasks /Run /TN ForexComDemoTradingBot")
    print("6. Check logs/trading_bot.log")
    print("\n✅ Done! Bot will auto-start on next login.")
