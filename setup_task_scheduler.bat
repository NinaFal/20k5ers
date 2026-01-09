@echo off
REM ========================================
REM Windows Task Scheduler Setup for 5ers Bot
REM Run this as Administrator
REM ========================================

echo Creating Windows Task Scheduler task for 5ers Bot...
echo.

REM Set variables
set TASK_NAME=5ersbot
set SCRIPT_PATH=C:\botcreativehub\start_bot_service.bat
set WORKING_DIR=C:\botcreativehub

REM Delete existing task if it exists
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %errorlevel% == 0 (
    echo Deleting existing task...
    schtasks /Delete /TN "%TASK_NAME%" /F
)

echo.
echo Creating new scheduled task...
echo Task Name: %TASK_NAME%
echo Script: %SCRIPT_PATH%
echo.

REM Create the task
REM - Runs at system startup
REM - Runs whether user is logged on or not
REM - Runs with highest privileges
REM - Restarts on failure every 5 minutes
REM - Never stops running

schtasks /Create /TN "%TASK_NAME%" ^
    /TR "%SCRIPT_PATH%" ^
    /SC ONSTART ^
    /RU SYSTEM ^
    /RL HIGHEST ^
    /F

if %errorlevel% == 0 (
    echo.
    echo ✓ Task created successfully!
    echo.
    echo To start the bot now, run:
    echo   schtasks /run /tn "%TASK_NAME%"
    echo.
    echo To stop the bot:
    echo   schtasks /end /tn "%TASK_NAME%"
    echo.
    echo To view task details:
    echo   schtasks /query /tn "%TASK_NAME%" /v
    echo.
) else (
    echo.
    echo ✗ Failed to create task. Make sure you run this as Administrator.
    echo.
)

pause
