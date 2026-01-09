# 🚀 Quick Start Commands - Direct Copy-Paste voor TheTradrBot

**Alle commands zijn klaar om direct te copy-pasten!**

---

## 📥 STAP 1: Pull Project

Open **Command Prompt** (normaal, niet admin):

```cmd
cd C:\Users\TheTradrBot\botcreativehub
git pull origin main
```

---

## 📦 STAP 2: Install Dependencies

```cmd
pip install -r requirements.txt
pip install MetaTrader5 python-dotenv
```

---

## ⚙️ STAP 3: Configureer .env

```cmd
copy .env.forexcom_demo .env
notepad .env
```

**Vul alleen MT5_PASSWORD in, de rest is al correct:**
```
MT5_PASSWORD=YOUR_PASSWORD_HERE
```

Save & sluit Notepad.

---

## 🤖 STAP 4: Setup Task Scheduler

### A. Genereer Task Config

```cmd
python scripts/setup_windows_task.py
```

**Kopieer de output command** (ziet er ongeveer zo uit):

---

### B. Run Als Administrator

**Rechtermuisknop op Start → Command Prompt (Admin)**

Paste de command van hierboven:

```cmd
cd /d "C:\Users\TheTradrBot\botcreativehub"
schtasks /Create /XML "trading_bot_task.xml" /TN "ForexComDemoTradingBot"
```

Moet zien: `SUCCESS: The scheduled task "ForexComDemoTradingBot" has successfully been created.`

---

## ▶️ STAP 5: Start Bot

**Terug naar normale Command Prompt (niet admin):**

```cmd
schtasks /Run /TN "ForexComDemoTradingBot"
```

---

## ✅ STAP 6: Verificatie

### Check logs:
```cmd
type logs\trading_bot.log
```

Moet zien:
```
[INFO] 5ERS 60K HIGH STAKES TRADING BOT
[INFO] Connecting to MT5...
[INFO] ✓ Connected to Forex.comGlobal-Demo
```

### Check Task Status:
```cmd
schtasks /Query /TN "ForexComDemoTradingBot" /V /FO LIST
```

Kijk naar `Status: Running`

---

## 🔌 STAP 7: RDP Disconnect

### ✅ JUISTE MANIER (Bot blijft draaien):
- Gewoon RDP window sluiten (X knop)
- OF: Start menu → User icon → **Disconnect**

### ❌ VERKEERDE MANIER (Bot stopt):
- **NIET** Sign out
- **NIET** Shut down

---

## 🛠️ Management Commands (Voor Later)

### Bot stoppen:
```cmd
schtasks /End /TN "ForexComDemoTradingBot"
```

### Bot herstarten:
```cmd
schtasks /End /TN "ForexComDemoTradingBot"
schtasks /Run /TN "ForexComDemoTradingBot"
```

### Status checken:
```cmd
schtasks /Query /TN "ForexComDemoTradingBot"
```

### Laatste 50 regels logs:
```cmd
powershell "Get-Content logs\trading_bot.log -Tail 50"
```

### Logs real-time volgen:
```cmd
powershell "Get-Content logs\trading_bot.log -Wait -Tail 20"
```

---

## 🔄 Task Verwijderen (Om Opnieuw Te Beginnen)

```cmd
schtasks /Delete /TN "ForexComDemoTradingBot" /F
```

Dan herhaal STAP 4.

---

## 📊 Monitoring Commands

### Check of Python bot draait:
```cmd
tasklist | findstr python
```

### Check MT5 terminal draait:
```cmd
tasklist | findstr terminal64
```

### Windows Task Scheduler GUI openen:
```cmd
taskschd.msc
```

Dan zoek naar: `ForexComDemoTradingBot`

---

## 🚨 Troubleshooting

### ❌ "git pull" faalt
```cmd
git reset --hard origin/main
git pull origin main
```

### ❌ "schtasks" commando niet gevonden
- Je zit in PowerShell → open **Command Prompt** (cmd.exe)

### ❌ "Access denied" bij schtasks
- Run **Command Prompt as Administrator**

### ❌ Bot start niet
1. Check MT5 terminal is **open**
2. Check `.env` heeft correct wachtwoord
3. Test handmatig:
```cmd
python main_live_bot.py --first-run
```

### ❌ Task blijft "Running" maar bot doet niets
```cmd
schtasks /End /TN "ForexComDemoTradingBot"
del trading_bot_task.xml
python scripts/setup_windows_task.py
REM Copy nieuwe schtasks command en run als Admin
schtasks /Run /TN "ForexComDemoTradingBot"
```

---

## 📍 File Locaties

```
C:\Users\TheTradrBot\botcreativehub\
├── .env                          # Je credentials (JIJ MAAKT AAN!)
├── trading_bot_task.xml          # Task Scheduler config (auto-generated)
├── logs\
│   └── trading_bot.log           # ⭐ HIER STAAN ALLE LOGS
├── main_live_bot.py              # Main bot
└── scripts\
    └── setup_windows_task.py     # Task setup script
```

---

## ⚡ ULTRA QUICK - Alles in 1 Keer

**Eerste keer setup (copy alles tegelijk):**

```cmd
cd C:\Users\TheTradrBot\botcreativehub
git pull origin main
pip install -r requirements.txt
copy .env.forexcom_demo .env
notepad .env
```

**Wacht tot je .env hebt opgeslagen, dan:**

```cmd
python scripts/setup_windows_task.py
```

**Kopieer de output command, open CMD as Admin, paste, dan terug naar normale CMD:**

```cmd
schtasks /Run /TN "ForexComDemoTradingBot"
type logs\trading_bot.log
```

**✅ KLAAR! Sluit RDP window.**

---

## 🎯 Dagelijkse Routine

### Ochtend (Optioneel):
```cmd
cd C:\Users\TheTradrBot\botcreativehub
type logs\trading_bot.log
```

### Avond (Optioneel):
```cmd
cd C:\Users\TheTradrBot\botcreativehub
powershell "Get-Content logs\trading_bot.log -Tail 100"
```

**Disconnect RDP → Bot blijft draaien 24/7!** 🚀

---

## 📞 Als Er Iets Misgaat

1. Check logs: `type logs\trading_bot.log`
2. Check MT5 terminal is open
3. Check `.env` wachtwoord klopt
4. Test handmatig: `python main_live_bot.py --first-run`
5. Check task status: `schtasks /Query /TN ForexComDemoTradingBot`

---

**LET OP**: Alle paths gebruiken `TheTradrBot` username - **direct copy-paste klaar!** ✅
