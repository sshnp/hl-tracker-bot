# 🔍 Hyperliquid Wallet Tracker Bot

Telegram бот, який стежить за perp-позиціями гаманця на Hyperliquid
і сповіщає про відкриття / закриття позицій в реальному часі.

---

## 📦 Встановлення

```bash
cd hl_tracker_bot
pip install -r requirements.txt
```

---

## ⚙️ Налаштування

1. **Створити бота** → написати [@BotFather](https://t.me/BotFather) → `/newbot` → отримати `TELEGRAM_TOKEN`

2. **Дізнатись свій CHAT_ID** → написати [@userinfobot](https://t.me/userinfobot) → скопіювати id

3. **Скопіювати `.env.example` → `.env`** і заповнити:

```bash
cp .env.example .env
nano .env
```

```
TELEGRAM_TOKEN=1234567890:ABCdef...
CHAT_ID=123456789
WALLET=0x4909e918ed7acfab30d9569f2e570c7c8d222181
POLL_INTERVAL=15
```

---

## 🚀 Запуск

```bash
# Завантажити змінні середовища і запустити
export $(cat .env | xargs) && python bot.py
```

Або через systemd / screen / tmux для фонової роботи:

```bash
# screen
screen -S hlbot
export $(cat .env | xargs) && python bot.py
# Ctrl+A, D  →  відключитись, бот працює у фоні
```

---

## 📩 Що надсилає бот

| Подія | Повідомлення |
|-------|-------------|
| Нова позиція відкрита | 🚨 New position opened! + деталі |
| Позиція закрита | 🔒 Position closed + деталі |

### Команди бота
- `/start` — статус моніторингу
- `/positions` — поточні відкриті позиції

---

## 🔗 API

Бот використовує офіційний [Hyperliquid Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)  
Endpoint: `POST https://api.hyperliquid.xyz/info`  
Без API ключа, повністю публічний.
