import asyncio
import logging
import os
import ssl
from datetime import datetime

import aiohttp
import certifi
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN")
CHAT_ID        = os.getenv("CHAT_ID", "YOUR_CHAT_ID")
POLL_INTERVAL  = int(os.getenv("POLL_INTERVAL", "15"))
HL_INFO_URL    = "https://api.hyperliquid.xyz/info"

# Список гаманців через змінну середовища WALLETS (через кому)
# або вписати вручну нижче
_wallets_env = os.getenv("WALLETS", "")
if _wallets_env:
    WALLETS: list[str] = [w.strip() for w in _wallets_env.split(",") if w.strip()]
else:
    WALLETS = [
        "0x4909e918ed7acfab30d9569f2e570c7c8d222181",
        "0xa5b0edf6b55128e0ddae8e51ac538c3188401d41",
        "0x393d0b87ed38fc779fd9611144ae649ba6082109",
        "0xeadc152ac1014ace57c6b353f89adf5faffe9d55",
    ]

# Мітки для гаманців (для зручності в повідомленнях)
WALLET_LABELS: dict[str, str] = {
    "0x4909e918ed7acfab30d9569f2e570c7c8d222181": "Whale #1",
    "0xa5b0edf6b55128e0ddae8e51ac538c3188401d41": "Whale #2",
    "0x393d0b87ed38fc779fd9611144ae649ba6082109": "Whale #3",
    "0xeadc152ac1014ace57c6b353f89adf5faffe9d55": "Whale #4",
}
# ─────────────────────────────────────────────────────────────────────────────

known_positions: dict[str, dict[str, dict]] = {w: {} for w in WALLETS}


def wallet_label(wallet: str) -> str:
    label = WALLET_LABELS.get(wallet)
    short = f"`{wallet[:6]}…{wallet[-4:]}`"
    return f"{label} {short}" if label else short


async def fetch_positions(session: aiohttp.ClientSession, wallet: str) -> list[dict]:
    payload = {"type": "clearinghouseState", "user": wallet}
    async with session.post(HL_INFO_URL, json=payload) as resp:
        data = await resp.json()
    positions = []
    for item in data.get("assetPositions", []):
        pos = item.get("position", {})
        size = float(pos.get("szi", 0))
        if size != 0:
            positions.append({
                "coin":      pos.get("coin", "?"),
                "size":      size,
                "entry":     float(pos.get("entryPx", 0)),
                "leverage":  pos.get("leverage", {}),
                "pnl":       float(pos.get("unrealizedPnl", 0)),
                "liq_price": float(pos.get("liquidationPx") or 0),
                "margin":    float(pos.get("marginUsed", 0)),
            })
    return positions


def fmt_position(pos: dict) -> str:
    side = "🟢 LONG" if pos["size"] > 0 else "🔴 SHORT"
    lev = pos["leverage"]
    lev_str = f"{lev.get('value', '?')}x {lev.get('type', '')}" if isinstance(lev, dict) else str(lev)
    liq = f"${pos['liq_price']:,.2f}" if pos['liq_price'] else "—"
    return (
        f"*{pos['coin']}* · {side}\n"
        f"  Size:      `{abs(pos['size']):,.2f}`\n"
        f"  Entry:     `${pos['entry']:,.4f}`\n"
        f"  Leverage:  `{lev_str}`\n"
        f"  Liq price: `{liq}`\n"
        f"  Margin:    `${pos['margin']:,.2f}`\n"
        f"  uPnL:      `${pos['pnl']:+.2f}`"
    )


async def check_wallet(bot: Bot, session: aiohttp.ClientSession, wallet: str):
    global known_positions
    try:
        positions = await fetch_positions(session, wallet)
    except Exception as e:
        logger.error("[%s] Failed to fetch: %s", wallet[:8], e)
        return

    current: dict[str, dict] = {p["coin"]: p for p in positions}
    prev: dict[str, dict] = known_positions[wallet]
    ts = datetime.utcnow().strftime("%H:%M:%S UTC")
    wlabel = wallet_label(wallet)
    url = f"https://hypurrscan.io/address/{wallet}#perps"

    for coin, pos in current.items():
        if coin not in prev:
            logger.info("[%s] New position: %s", wallet[:8], coin)
            text = (
                f"🚨 *New position opened!*\n"
                f"🕐 {ts} · 👛 {wlabel}\n\n"
                f"{fmt_position(pos)}\n\n"
                f"[HypurrScan]({url})"
            )
            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown",
                                   disable_web_page_preview=True)
        else:
            old_size = abs(prev[coin]["size"])
            new_size = abs(pos["size"])
            if new_size > old_size * 1.01:
                pct = (new_size - old_size) / old_size * 100
                logger.info("[%s] Position increased: %s +%.1f%%", wallet[:8], coin, pct)
                side = "LONG" if pos["size"] > 0 else "SHORT"
                text = (
                    f"📈 *Position increased* (+{pct:.1f}%)\n"
                    f"🕐 {ts} · 👛 {wlabel}\n\n"
                    f"*{coin}* · {side}\n"
                    f"  Size: `{old_size:,.2f}` → `{new_size:,.2f}`\n"
                    f"  Entry: `${pos['entry']:,.4f}`\n"
                    f"  Margin: `${pos['margin']:,.2f}`\n"
                    f"  uPnL: `${pos['pnl']:+.2f}`\n\n"
                    f"[HypurrScan]({url})"
                )
                await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown",
                                       disable_web_page_preview=True)
            elif new_size < old_size * 0.99:
                pct = (old_size - new_size) / old_size * 100
                logger.info("[%s] Position decreased: %s -%.1f%%", wallet[:8], coin, pct)
                side = "LONG" if pos["size"] > 0 else "SHORT"
                text = (
                    f"📉 *Position partially closed* (-{pct:.1f}%)\n"
                    f"🕐 {ts} · 👛 {wlabel}\n\n"
                    f"*{coin}* · {side}\n"
                    f"  Size: `{old_size:,.2f}` → `{new_size:,.2f}`\n"
                    f"  Entry: `${pos['entry']:,.4f}`\n"
                    f"  uPnL: `${pos['pnl']:+.2f}`\n\n"
                    f"[HypurrScan]({url})"
                )
                await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown",
                                       disable_web_page_preview=True)

    for coin, pos in prev.items():
        if coin not in current:
            logger.info("[%s] Position closed: %s", wallet[:8], coin)
            side = "LONG" if pos["size"] > 0 else "SHORT"
            text = (
                f"🔒 *Position closed*\n"
                f"🕐 {ts} · 👛 {wlabel}\n\n"
                f"*{coin}* · {side}\n"
                f"  Entry was: `${pos['entry']:,.4f}`\n\n"
                f"[HypurrScan]({url})"
            )
            await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown",
                                   disable_web_page_preview=True)

    known_positions[wallet] = current


async def poll_loop(bot: Bot):
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    async with aiohttp.ClientSession(connector=connector) as session:
        logger.info("Polling %d wallets every %ds", len(WALLETS), POLL_INTERVAL)
        for w in WALLETS:
            logger.info("  → %s  (%s)", w, WALLET_LABELS.get(w, ""))
        while True:
            for wallet in WALLETS:
                await check_wallet(bot, session, wallet)
                await asyncio.sleep(1)
            await asyncio.sleep(POLL_INTERVAL)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["👁 *Monitoring wallets:*\n"]
    for w in WALLETS:
        label = WALLET_LABELS.get(w, "")
        lines.append(f"• {label} `{w[:6]}…{w[-4:]}`")
    lines.append(f"\n⏱ Polling every *{POLL_INTERVAL}s*")
    lines.append("Use /positions to see all open positions.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_positions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    total = sum(len(v) for v in known_positions.values())
    if total == 0:
        await update.message.reply_text("No open positions currently tracked.")
        return
    lines = [f"📊 *Open positions ({total} total)*\n"]
    for wallet, positions in known_positions.items():
        if not positions:
            continue
        lines.append(f"👛 {wallet_label(wallet)}")
        for pos in positions.values():
            lines.append(fmt_position(pos))
            lines.append("")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("positions", cmd_positions))
    async with app:
        await app.start()
        await app.updater.start_polling()
        await poll_loop(app.bot)
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())