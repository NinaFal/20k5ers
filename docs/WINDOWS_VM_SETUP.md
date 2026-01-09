# Windows VM Setup - Complete Guide

## 🎯 Doel
Bot laten draaien 24/7 op Windows VM, ook als je RDP sessie sluit.

---

## 📥 Stap 1: Pull Project

```cmd
cd C:\Users\TheTradrBot\botcreativehub
git pull origin main
```

---

## 🔧 Stap 2: Installeer Dependencies

```cmd
pip install -r requirements.txt
pip install MetaTrader5 python-dotenv
```

---

## ⚙️ Stap 3: Configureer .env

```cmd
copy .env.forexcom_demo .env
notepad .env
```

Vul in:
```env
MT5_LOGIN=531
MT5_PASSWORD=YOUR_PASSWORD_HERE
MT5_SERVER=Forex.comGlobal-Demo
```

---

## 🤖 Stap 4: Setup Auto-Start (Task Scheduler)

### Optie A: Automatisch via Python Script

```cmd
python scripts/setup_windows_task.py
```

Dit script:
1. Maakt een Task Scheduler XML bestand
2. Geeft je de exacte commands om te copy-pasten
3. Instructies voor GUI methode

**Dan kopieer je de commands naar Command Prompt (als Administrator):**

```cmd
cd /d "C:\Users\TheTradrBot\botcreativehub"
schtasks /Create /XML "trading_bot_task.xml" /TN "ForexComDemoTradingBot"
```

### Optie B: Handmatig via GUI

1. Run `python scripts/setup_windows_task.py` (maakt XML)
2. Druk `Windows + R`
3. Type: `taskschd.msc` + Enter
4. Klik: **Action → Import Task...**
5. Selecteer: `trading_bot_task.xml`
6. Klik: **OK**

---

## ✅ Stap 5: Start de Bot

### Eenmalig testen:
```cmd
python main_live_bot.py --first-run
```

### Via Task Scheduler:
```cmd
schtasks /Run /TN "ForexComDemoTradingBot"
```

---

## 📊 Task Management Commands

### Status checken:
```cmd
schtasks /Query /TN "ForexComDemoTradingBot" /V /FO LIST
```

### Bot stoppen:
```cmd
schtasks /End /TN "ForexComDemoTradingBot"
```

### Task verwijderen:
```cmd
schtasks /Delete /TN "ForexComDemoTradingBot" /F
```

### Task handmatig starten:
```cmd
schtasks /Run /TN "ForexComDemoTradingBot"
```

---

## 🖥️ RDP Disconnect (BELANGRIJK!)

### ✅ CORRECT - Bot blijft draaien:
1. Klik **Start menu**
2. Klik je **user icon**
3. Selecteer **"Disconnect"**

OF: Gewoon RDP window sluiten (X knop)

### ❌ VERKEERD - Bot stopt:
- **NIET** Sign out
- **NIET** Shut down
- **NIET** Restart

---

## 📁 File Locaties

```
C:\Users\TheTradrBot\botcreativehub\
├── .env                          # Je credentials (MAAK AAN!)
├── main_live_bot.py              # Main bot script
├── start_bot.bat                 # ✅ NIEUW - Quick start script
├── trading_bot_task.xml          # ✅ NIEUW - Task Scheduler config
├── logs/
│   └── trading_bot.log           # Bot logs (check hier!)
└── scripts/
    └── setup_windows_task.py     # ✅ NIEUW - Auto-setup script
```

---

## 🔍 Logs Monitoren

### Real-time logs bekijken:
```cmd
Get-Content logs\trading_bot.log -Wait -Tail 50
```

Of gebruik **Notepad++** / **VS Code** om logs te volgen.

---

## 🚨 Troubleshooting

### ❌ "Task creation failed"
- Run Command Prompt **as Administrator**
- Check `trading_bot_task.xml` exists
- Verify path to Python is correct

### ❌ "Bot not starting"
1. Check Task Scheduler (taskschd.msc)
2. Right-click task → Properties
3. Check "Last Run Result" (0x0 = success)
4. Check `logs/trading_bot.log`

### ❌ "MT5 connection failed"
1. Open MT5 Terminal handmatig
2. Login met credentials
3. Laat MT5 Terminal **OPEN** (minimized is ok)
4. Restart bot task

### ❌ Bot stopt na RDP disconnect
- Controleer dat je **Disconnect** gebruikt (niet Sign out)
- Check Task Scheduler: "Run whether user is logged on or not"
- Verify task is still running: `tasklist | findstr python`

---

## ⚡ Quick Start Commands (Copy-Paste)

```cmd
cd C:\Users\TheTradrBot\botcreativehub
git pull origin main
pip install -r requirements.txt
copy .env.forexcom_demo .env
notepad .env
python scripts/setup_windows_task.py
REM Then copy the schtasks command from output and run as Admin
```

---

## 🎯 What Happens After Setup

1. ✅ Bot auto-starts 1 minute after Windows login
2. ✅ Bot restarts automatically if it crashes (3 attempts)
3. ✅ You can disconnect RDP - bot keeps running
4. ✅ Logs are written to `logs/trading_bot.log`
5. ✅ Check status anytime with task scheduler

---

## 📋 Daily Routine

**Morning:**
- RDP into VM
- Check `logs/trading_bot.log`
- Verify bot is running: Task Scheduler

**Evening:**
- Check performance in MT5
- Review logs for any issues
- Disconnect RDP (bot keeps running)

**No need to manually start/stop bot!**

---

## 🔐 Security Notes

- ⚠️ `.env` contains your MT5 password - keep it secret!
- ✅ Don't commit `.env` to git (already in .gitignore)
- ✅ Use strong password for VM RDP access
- ✅ Only allow necessary ports in firewall

---

## ☁️ VM Provider Specific

### Azure VM:
- Set "Auto-shutdown" to **Disabled** in Azure Portal
- Or set auto-shutdown time to 23:59 if you want safety net

### AWS EC2:
- Use "Stop Protection" to prevent accidental shutdown
- Set instance to NOT stop on idle

### Google Cloud:
- Remove "Automatic restart" schedule if enabled
- Keep instance running 24/7

---

## 📞 Support Checklist

If bot isn't working, provide:
1. Last 100 lines from `logs/trading_bot.log`
2. Task Scheduler status (schtasks /Query)
3. MT5 connection status
4. Windows Event Viewer → Application logs

---

**Ready to deploy! 🚀**
