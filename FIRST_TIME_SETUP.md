# 🚀 EERSTE KEER SETUP - Clone Project

## Je bent hier: `C:\Users\Administrator>`

---

## STAP 1: Clone het project

```cmd
cd C:\Users\Administrator
git clone https://github.com/TheTradrBot/botcreativehub.git
cd botcreativehub
```

---

## STAP 2: Installeer dependencies

```cmd
pip install -r requirements.txt
pip install MetaTrader5 python-dotenv
```

---

## STAP 3: Configureer .env

```cmd
copy .env.forexcom_demo .env
notepad .env
```

**Vul in Notepad:**
```
MT5_PASSWORD=YOUR_ACTUAL_PASSWORD
```

Save & sluit Notepad.

---

## STAP 4: Setup Task Scheduler

```cmd
python scripts/setup_windows_task.py
```

**Dit print commands voor je. Kopieer de schtasks command.**

---

## STAP 5: Run als Administrator

**Rechtermuisknop op Start → Command Prompt (Admin)**

Paste:
```cmd
cd /d "C:\Users\Administrator\botcreativehub"
schtasks /Create /XML "trading_bot_task.xml" /TN "ForexComDemoTradingBot"
```

---

## STAP 6: Start bot

**Terug naar normale CMD:**

```cmd
schtasks /Run /TN "ForexComDemoTradingBot"
```

---

## STAP 7: Check logs

```cmd
type logs\trading_bot.log
```

---

## ✅ Klaar! Sluit RDP window.

Bot blijft draaien!

---

## 🔄 Later Updates (als je al hebt gecloned)

```cmd
cd C:\Users\Administrator\botcreativehub
git pull origin main
pip install -r requirements.txt
```

---

**LET OP:** Je project is in `C:\Users\Administrator\botcreativehub` (niet TheTradrBot folder)
