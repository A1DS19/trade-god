# DCA Crypto Bot — Setup Guide

## What it does

- Watches BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, POL, TAO, SUI
- Buys $8 worth when a coin drops 3%+ from its 24h high
- Sells when you're up +5% (take profit) or down -15% (stop loss)
- Sends you Telegram notifications for every trade + daily summary at 8am UTC

---

## Step 1 — Get your Binance API Keys

1. Go to https://www.binance.com → Profile → API Management
2. Create a new API key (label it "DCA Bot")
3. Enable: **Spot & Margin Trading**
4. Disable: Withdrawals (for safety)
5. Copy the API Key and Secret into `config.json`

---

## Step 2 — Create your Telegram Bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot` → follow the steps → copy the **token**
3. Start a chat with your new bot
4. Get your Chat ID:
   - Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   - Send any message to your bot first
   - Copy the `"id"` number from `"chat"` in the response
5. Paste both into `config.json`

---

## Step 3 — Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python dca_bot.py
```

---

## Step 4 — Run 24/7 on a VPS (optional but recommended)

### Option A: Railway.app (free tier available)

1. Push this folder to a GitHub repo
2. Connect Railway → deploy → done

### Option B: Any VPS (DigitalOcean, Hetzner ~$4/mo)

```bash
# Keep bot running after you close terminal
nohup python dca_bot.py > /dev/null 2>&1 &

# Or use screen
screen -S bot
python dca_bot.py
# Ctrl+A then D to detach
```

---

## Files

| File               | Purpose                              |
| ------------------ | ------------------------------------ |
| `dca_bot.py`       | Main bot                             |
| `config.json`      | Your API keys (keep private!)        |
| `bot_state.json`   | Auto-created — tracks open positions |
| `bot.log`          | Auto-created — full trade log        |
| `requirements.txt` | Python dependencies                  |

---

## Adjusting the strategy (in dca_bot.py)

| Setting             | Default | What it does                   |
| ------------------- | ------- | ------------------------------ |
| `TRADE_AMOUNT_USDT` | $8      | Spent per buy                  |
| `DIP_THRESHOLD`     | 3%      | How big a dip triggers a buy   |
| `TAKE_PROFIT`       | 5%      | Sells when up this much        |
| `STOP_LOSS`         | 15%     | Sells to protect capital       |
| `BUY_COOLDOWN_HRS`  | 4h      | Min time between buys per coin |

---

## ⚠️ Risk Warning

This bot trades real money. Past performance doesn't guarantee future results.
Start with small amounts and monitor the first few days closely.
Never invest more than you can afford to lose.

---

## HYPE coin

HYPE is not yet listed on Binance Spot. Once it is, add `"HYPE"` to the `COINS` list in `dca_bot.py`.
