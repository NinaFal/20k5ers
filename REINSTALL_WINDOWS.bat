@echo off
REM Complete cleanup and fresh install for 5ers Trading Bot
REM Run this as Administrator

echo ========================================
echo STEP 1: Stopping all processes
echo ========================================
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul
taskkill /F /IM terminal64.exe 2>nul
timeout /t 2

echo.
echo ========================================
echo STEP 2: Deleting all scheduled tasks
echo ========================================
schtasks /delete /tn "\5ers Trading Bot" /f 2>nul
schtasks /delete /tn "\5ersTradeBot" /f 2>nul
schtasks /delete /tn "\ForexComDemoTradingBot" /f 2>nul
schtasks /delete /tn "\FTMOTradingBot" /f 2>nul
schtasks /delete /tn "\FTMO_Live_Bot" /f 2>nul
schtasks /delete /tn "\TradrLive" /f 2>nul
schtasks /delete /tn "\TradrLiveBot" /f 2>nul
timeout /t 2

echo.
echo ========================================
echo STEP 3: Removing old directory
echo ========================================
cd /d C:\
if exist "C:\botcreativehub" (
    echo Deleting C:\botcreativehub...
    rd /s /q C:\botcreativehub
    timeout /t 2
)

echo.
echo ========================================
echo STEP 4: Fresh clone from GitHub
echo ========================================
git clone https://github.com/TheTradrBot/botcreativehub.git
if %errorlevel% neq 0 (
    echo ERROR: Git clone failed!
    pause
    exit /b 1
)

cd botcreativehub

echo.
echo ========================================
echo STEP 5: Creating Python virtual environment
echo ========================================
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: venv creation failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo STEP 6: Installing Python packages
echo ========================================
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\pip install -r requirements.txt
venv\Scripts\pip install MetaTrader5

echo.
echo ========================================
echo STEP 7: Creating scheduled task
echo ========================================
schtasks /create /tn "5ers Trading Bot" /tr "C:\botcreativehub\start_bot_service.bat" /sc onstart /ru Administrator /rl highest /f
schtasks /change /tn "5ers Trading Bot" /enable

echo.
echo ========================================
echo STEP 8: Verification
echo ========================================
echo Checking files...
dir C:\botcreativehub\*.py
echo.
echo Checking venv...
venv\Scripts\python.exe --version
echo.
echo Checking task...
schtasks /query /tn "5ers Trading Bot" /fo list | findstr "TaskName Status"

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Test manually: cd /d C:\botcreativehub ^&^& venv\Scripts\python.exe main_live_bot.py
echo 2. Or run task: schtasks /run /tn "5ers Trading Bot"
echo.
pause
