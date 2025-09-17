# bot_postgres_digen_donate.py
import logging
import aiohttp
import asyncio
import re
import os
import json
import itertools
import random
import time
from datetime import datetime, timezone

import asyncpg
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
    PreCheckoutQueryHandler
)

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@SizningKanal")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"
DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL connection string
_key_cycle = itertools.cycle(DIGEN_KEYS)

if not DATABASE_URL:
    logger.error("❌ Please set DATABASE_URL environment variable (Postgres).")
    raise SystemExit(1)

# ---------------- Helpers ----------------
def escape_md(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~>#+\-=|{}.!])', r'\\\1', text)

def utc_now():
    return datetime.now(timezone.utc)

# ---------------- Database utilities ----------------
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS generations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    prompt TEXT,
    translated_prompt TEXT,
    image_id TEXT,
    image_count INT,
    created_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS donations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    stars INT,
    payload TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        row = await conn.fetchrow("SELECT value FROM meta WHERE key = 'start_time'")
        if not row:
            await conn.execute(
                "INSERT INTO meta(key, value) VALUES($1, $2)",
                "start_time", str(int(time.time()))
            )

# ---------------- Digen header ----------------
def get_digen_headers():
    if not DIGEN_KEYS:
        return {}
    key = random.choice(DIGEN_KEYS)
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "digen-language": "uz-US",
        "digen-platform": "web",
        "digen-token": key["token"],
        "digen-sessionid": key["session"],
        "origin": "https://rm.digen.ai",
        "referer": "https://rm.digen.ai/",
    }

# ---------------- User/session functions (DB) ----------------
async def add_user_db(pool, tg_user):
    now = utc_now()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if user:
            await conn.execute(
                "UPDATE users SET username = $1, last_seen = $2 WHERE id = $3",
                tg_user.username if tg_user.username else None,
                now, tg_user.id
            )
        else:
            await conn.execute(
                "INSERT INTO users(id, username, first_seen, last_seen) VALUES($1,$2,$3,$4)",
                tg_user.id,
                tg_user.username if tg_user.username else None,
                now,
                now
            )
        await conn.execute(
            "INSERT INTO sessions(user_id, started_at) VALUES($1, $2)",
            tg_user.id, now
        )

async def log_generation(pool, tg_user, prompt, translated, image_id, count):
    now = utc_now()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO generations(user_id, username, prompt, translated_prompt, image_id, image_count, created_at) "
            "VALUES($1,$2,$3,$4,$5,$6,$7)",
            tg_user.id, tg_user.username if tg_user.username else None,
            prompt, translated, image_id, count, now
        )

# ---------------- Start ----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    await add_user_db(context.application.bot_data["db_pool"], tg_user)
    kb = [[InlineKeyboardButton("🎨 Rasm yaratishni boshlash", callback_data="start_gen")],
          [InlineKeyboardButton("💖 Donate qilish", callback_data="donate_custom")]]
    await update.message.reply_text(
        "👋 Salom!\n\nMen siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\n\n"
        "✍️ Xohlagan narsani yozing — men uni rasmga aylantiraman.\n\n"
        "_Misol:_ Futuristik cyberpunk shahar neon chiroqlar bilan",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "✍️ Endi tasvir yaratish uchun matn yuboring.\n\n_Misol:_ Futuristik cyberpunk shahar neon chiroqlar bilan",
        parse_mode="Markdown"
    )

# ---------------- Prompt handler ----------------
async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    text = update.message.text if update.message else None
    if not text:
        return
    await add_user_db(context.application.bot_data["db_pool"], tg_user)
    context.user_data["prompt"] = text
    context.user_data["translated"] = text
    await ask_image_count(update, context)

async def ask_image_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = context.user_data.get("prompt", "")
    kb = [[
        InlineKeyboardButton("1️⃣", callback_data="count_1"),
        InlineKeyboardButton("2️⃣", callback_data="count_2"),
        InlineKeyboardButton("4️⃣", callback_data="count_4"),
        InlineKeyboardButton("8️⃣", callback_data="count_8"),
    ]]
    await update.message.reply_text(
        f"🖌 Sizning matningiz:\n{escape_md(prompt)}\n\n🔢 Nechta rasm yaratilsin?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ---------------- Generate ----------------
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    count = int(query.data.split("_")[1])
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", "")

    waiting_msg = await query.edit_message_text(f"🔄 Rasm yaratilmoqda ({count} ta)...⏳")
    try:
        payload = {
            "prompt": translated,
            "image_size": "512x512",
            "width": 512,
            "height": 512,
            "lora_id": "",
            "batch_size": count,
            "reference_images": [],
            "strength": ""
        }
        headers = get_digen_headers()
        async with aiohttp.ClientSession() as session:
            async with session.post(DIGEN_URL, headers=headers, json=payload) as r:
                if r.status != 200:
                    await waiting_msg.edit_text(f"❌ API xatosi: {r.status}")
                    return
                data = await r.json()

        image_id = data.get("data", {}).get("id")
        if not image_id:
            await waiting_msg.edit_text("❌ Rasm ID olinmadi.")
            return

        urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
        await query.edit_message_text(f"✅ Rasm tayyor! 📸")
        media_group = [InputMediaPhoto(url) for url in urls]
        await query.message.reply_media_group(media_group)
        await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)
    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        await waiting_msg.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko‘ring.")

# ---------------- Donate flow ----------------
async def donate_custom_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000 Stars):")
    return "WAITING_AMOUNT"

async def donate_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        amount = int(text)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Iltimos, 1–100000 oralig‘ida raqam kiriting.")
        return "WAITING_AMOUNT"

    user = update.effective_user
    chat_id = update.effective_chat.id
    payload = f"donate_{user.id}_{int(time.time())}"

    prices = [LabeledPrice(f"{amount} Stars", amount * 100)]
    await context.bot.send_invoice(
        chat_id=chat_id,
        title="💖 Bot Donation",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        provider_token="",  # digital goods
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return -1

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user = update.effective_user
    chat_id = update.effective_chat.id
    amount_stars = payment.total_amount // 100
    payload = payment.invoice_payload

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Rahmat {user.first_name}! Siz {amount_stars} Stars yubordingiz."
    )
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload, created_at) VALUES($1,$2,$3,$4,now())",
            user.id, user.username if user.username else None, amount_stars, payload
        )

# ---------------- Main ----------------
async def main():
    pool = await asyncpg.create_pool(DATABASE_URL)
    await init_db(pool)

    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["db_pool"] = pool

    # Command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt))

    # Image count selection
    app.add_handler(CallbackQueryHandler(generate, pattern=r"count_\d+"))

    # Donate
    app.add_handler(CommandHandler("donate", donate_custom_prompt))
    app.add_handler(CallbackQueryHandler(donate_custom_prompt, pattern="donate_custom"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, donate_custom_amount))

    # Payments
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    await app.start()
    await app.updater.start_polling()
    await app.idle()

if __name__ == "__main__":
    asyncio.run(main())
