# Binance Conservative Spot Scanner

A free, read-only research scanner for Binance Spot USDT pairs. It includes BTC, ETH, BNB, SOL, XRP and **NEAR** and runs every 15 minutes through GitHub Actions.

## What it does
- Pulls public Binance Spot candlesticks; no API key is required.
- Uses completed 4-hour and 1-day candles (not the still-forming candle).
- Calculates RSI(14), EMA20/50, MACD histogram and volume ratio.
- Applies strict conservative filters; otherwise reports `WAIT`.
- Writes `reports/latest.md` and `reports/latest.json` to the repository.
- Never places trades or needs trading permissions.

## Setup
1. Create a GitHub repository. For a free/private repo, GitHub Actions usage is subject to the account's included minutes; public repositories generally have free standard hosted-runner usage.
2. Upload this folder's contents to the repository's default branch (the `.github/workflows/scan.yml` path must be preserved).
3. In the repository, open **Settings → Actions → General → Workflow permissions** and allow read/write permissions if the workflow cannot push reports.
4. Open **Actions → Binance Spot Scanner → Run workflow** for the first scan. Scheduled scans then run at minutes 00, 15, 30 and 45 UTC (06:00, 06:15, 06:30, 06:45 Bangladesh time, etc.). GitHub may delay scheduled jobs; it is not a guaranteed exact-time service.
5. Open `reports/latest.md` for the latest report.

## Risk assumptions
Default capital is $300, risk budget is 1% ($3) per trade, maximum notional is 20% ($60) per trade, and at most three candidates are surfaced. These are sizing estimates, not a guarantee of execution price or loss cap; gaps, slippage and fees can increase losses.

## Important
- This is an alert/research tool, not financial advice.
- It does not submit orders, connect to an exchange account, or store API secrets.
- A BUY CANDIDATE is a technical screen result, not a recommendation to buy blindly. Confirm live price, spread, order-book liquidity, news and market regime yourself.
- GitHub Actions cron jobs can be delayed or disabled by GitHub after prolonged repository inactivity. Review workflow runs regularly.


## Telegram alerts (optional)
1. In Telegram, open **@BotFather**, send `/newbot`, follow the prompts, and copy the bot token. Do not paste the token into chat or commit it to the repository.
2. Open the new bot's chat and press **Start**. Send it a test message.
3. To obtain your chat ID, open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser after sending the bot a message. Read `message.chat.id` from the response. Keep the token private; do not share screenshots containing it.
4. In the GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:
   - `TELEGRAM_BOT_TOKEN` = the BotFather token
   - `TELEGRAM_CHAT_ID` = your chat ID
5. Run the workflow manually once to test. If credentials are configured, each scan sends the report to Telegram. Without them, scanning and report generation still work.
