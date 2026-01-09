@echo off
REM ========================================
REM COPY FILES TO C:\botcreativehub
REM ========================================

echo Copying project files to C:\botcreativehub...
echo.

REM Create directory if it doesn't exist
if not exist "C:\botcreativehub\" mkdir "C:\botcreativehub\"

REM Copy all files
xcopy /E /I /Y "%~dp0*" "C:\botcreativehub\"

if %errorlevel% == 0 (
    echo.
    echo ✓ Files copied successfully to C:\botcreativehub
    echo.
    echo Next steps:
    echo 1. Copy .env file:
    echo    copy C:\botcreativehub\.env.forexcom_demo C:\botcreativehub\.env
    echo.
    echo 2. Run setup_task_scheduler.bat as Administrator
    echo.
) else (
    echo.
    echo ✗ Failed to copy files
    echo.
)

pause
