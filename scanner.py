#!/usr/bin/env python3
"""Read-only Binance Spot scanner. It never places orders."""
from __future__ import annotations
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

BASE_URL = "https://data-api.binance.vision"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "NEARUSDT"]
CAPITAL_USDT = float(os.getenv("CAPITAL_USDT", "300"))
RISK_FRACTION = float(os.getenv("RISK_FRACTION", "0.01"))
MAX_POSITION_FRACTION = float(os.getenv("MAX_POSITION_FRACTION", "0.20"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ConservativeSpotScanner/1.0"})

def get_klines(symbol: str, interval: str, limit: int = 120) -> list[list[Any]]:
    response = SESSION.get(
        f"{BASE_URL}/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or len(data) < 60:
        raise ValueError(f"Insufficient {interval} candles for {symbol}")
    return data

def ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(alpha * value + (1 - alpha) * out[-1])
    return out

def rsi(values: list[float], period: int = 14) -> float:
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

def macd_hist(values: list[float]) -> float:
    e12, e26 = ema(values, 12), ema(values, 26)
    line = [a-b for a, b in zip(e12, e26)]
    signal = ema(line, 9)
    return line[-1] - signal[-1]

def analyze(symbol: str) -> dict[str, Any]:
    h4 = get_klines(symbol, "4h")
    d1 = get_klines(symbol, "1d")
    # Ignore the currently forming candle to avoid intrabar false signals.
    h4, d1 = h4[:-1], d1[:-1]
    closes4 = [float(x[4]) for x in h4]
    highs4 = [float(x[2]) for x in h4]
    lows4 = [float(x[3]) for x in h4]
    volumes4 = [float(x[5]) for x in h4]
    closes1 = [float(x[4]) for x in d1]
    price = closes4[-1]
    e20_4, e50_4 = ema(closes4, 20)[-1], ema(closes4, 50)[-1]
    e20_1 = ema(closes1, 20)[-1]
    r = rsi(closes4)
    mh = macd_hist(closes4)
    avg_vol = sum(volumes4[-21:-1]) / 20
    vol_ratio = volumes4[-1] / avg_vol if avg_vol else 0
    # Recent 20-candle support/resistance, excluding current completed candle.
    support = min(lows4[-21:-1])
    resistance = max(highs4[-21:-1])
    stop = min(support * 0.995, price * 0.97)
    risk_pct = (price - stop) / price if price > stop else 1
    target1, target2 = price + 2*(price-stop), price + 3*(price-stop)
    position_cap = CAPITAL_USDT * MAX_POSITION_FRACTION
    risk_budget = CAPITAL_USDT * RISK_FRACTION
    risk_sized_qty = risk_budget / (price-stop) if price > stop else 0
    qty = min(risk_sized_qty, position_cap / price) if price > 0 else 0
    conditions = {
        "daily_above_ema20": closes1[-1] > e20_1,
        "4h_ema20_above_ema50": e20_4 > e50_4,
        "rsi_45_to_65": 45 <= r <= 65,
        "macd_hist_positive": mh > 0,
        "volume_1_2x": vol_ratio >= 1.2,
        "price_near_or_above_resistance": price >= resistance * 0.985,
    }
    passed = sum(conditions.values())
    # Conservative: require every filter. No signal when reward/risk is not valid.
    signal = "BUY CANDIDATE" if all(conditions.values()) and risk_pct <= 0.05 else "WAIT"
    return {
        "symbol": symbol, "price": price, "signal": signal, "score": f"{passed}/6",
        "rsi14_4h": round(r, 2), "ema20_4h": e20_4, "ema50_4h": e50_4,
        "ema20_1d": e20_1, "macd_hist_4h": mh, "volume_ratio": round(vol_ratio, 2),
        "support_4h": support, "resistance_4h": resistance, "stop_loss": stop,
        "target1_2R": target1, "target2_3R": target2, "risk_pct": round(risk_pct*100, 2),
        "suggested_qty": qty, "suggested_notional": qty*price,
        "checks": conditions,
    }

def fmt(x: Any) -> str:
    if isinstance(x, (int, float)):
        return f"{x:,.6g}"
    return str(x)

def send_telegram(text: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        return "Telegram not configured."

    message = text[:3900]

    try:
        response = SESSION.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )

        if not response.ok:
            print("Telegram API error:", response.status_code, response.text)
            return "Telegram notification failed; see API error above."

        print("Telegram notification sent.")
        return "Telegram notification sent."

    except Exception as exc:
        print("Telegram error:", str(exc))
        return "Telegram notification failed."

def main() -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results, errors = [], []
    for symbol in SYMBOLS:
        try:
            results.append(analyze(symbol))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
        time.sleep(0.15)
    candidates = sorted(
        [x for x in results if x["signal"] == "BUY CANDIDATE"],
        key=lambda x: (float(x["score"].split("/")[0]), x["volume_ratio"]),
        reverse=True,
    )[:MAX_POSITIONS]
    # A candidate is a research alert, not an instruction or order.
    overall = "BUY CANDIDATES FOUND" if candidates else "WAIT / NO TRADE"
    payload = {
        "timestamp_utc": timestamp, "capital_usdt": CAPITAL_USDT,
        "risk_budget_per_trade_usdt": CAPITAL_USDT*RISK_FRACTION,
        "max_positions": MAX_POSITIONS, "overall": overall,
        "candidates": candidates, "results": results, "errors": errors,
        "disclaimer": "Read-only research; not financial advice; no orders are placed. Confirm liquidity, spread, fees, news and market conditions before any trade."
    }
    (REPORT_DIR / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        "# Binance Conservative Spot Scanner",
        f"- Scan time (UTC): {timestamp}",
        f"- Capital: ${CAPITAL_USDT:.2f} | Max risk/trade: ${CAPITAL_USDT*RISK_FRACTION:.2f}",
        f"- Overall: **{overall}**",
        "- Symbols: " + ", ".join(SYMBOLS),
        "",
        "| Pair | Signal | Score | Price | RSI 4h | Vol x | Stop | Target 1 | Target 2 | Suggested USDT |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in results:
        lines.append(
            f"| {x['symbol']} | {x['signal']} | {x['score']} | {fmt(x['price'])} | "
            f"{x['rsi14_4h']} | {x['volume_ratio']} | {fmt(x['stop_loss'])} | "
            f"{fmt(x['target1_2R'])} | {fmt(x['target2_3R'])} | {fmt(x['suggested_notional'])} |"
        )
    if errors:
        lines += ["", "## Data errors"] + [f"- {e['symbol']}: {e['error']}" for e in errors]
    lines += ["", "## BUY candidate checks"]
    for x in candidates:
        lines.append(f"- **{x['symbol']}**: " + ", ".join(k for k,v in x["checks"].items() if v))
    lines += ["", "> Read-only research alert, not financial advice. No orders are placed. Verify current price, spread, liquidity, fees and news before trading."]
    (REPORT_DIR / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report_text = "\n".join(lines)
    print(report_text)
    print(send_telegram(report_text))

if __name__ == "__main__":
    main()
