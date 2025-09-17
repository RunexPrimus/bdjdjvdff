# bot_postgres_group.py
import logging
import aiohttp
import asyncio
import os
import json
import itertools
import random
import time
from datetime import datetime, timezone

import asyncpg
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

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
DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL

if not DATABASE_URL:
    logger.error("❌ Please set DATABASE_URL environment variable.")
    raise SystemExit(1)

_key_cycle = itertools.cycle(DIGEN_KEYS)

# ---------------- Helpers ----------------
def escape_md(text: str) -> str:
    if not text:
        return ""
    return text.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")

def utc_now():
    return datetime.now(timezone.utc)

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

# ---------------- Database ----------------
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS generations (
    id SERIAL PRIMARY KEY,
    chat_type TEXT,
    chat_id BIGINT,
    user_id BIGINT,
    username TEXT,
    prompt TEXT,
    image_id TEXT,
    image_count INT,
    created_at TIMESTAMPTZ
);
"""

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)

async def add_user_db(pool, tg_user):
    now = utc_now()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if user:
            await conn.execute(
                "UPDATE users SET username=$1, last_seen=$2 WHERE id=$3",
                tg_user.username, now, tg_user.id
            )
        else:
            await conn.execute(
                "INSERT INTO users(id, username, first_seen, last_seen) VALUES($1,$2,$3,$4)",
                tg_user.id, tg_user.username, now, now
            )

async def log_generation(pool, chat_type, chat_id, tg_user, prompt, image_id, count):
    now = utc_now()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO generations(chat_type, chat_id, user_id, username, prompt, image_id, image_count, created_at) "
            "VALUES($1,$2,$3,$4,$5,$6,$7,$8)",
            chat_type, chat_id, tg_user.id, tg_user.username, prompt, image_id, count, now
        )

# ---------------- Handlers ----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    await add_user_db(context.application.bot_data["db_pool"], tg_user)

    kb = [[InlineKeyboardButton("🎨 Rasm yaratishni boshlash", callback_data="start_gen")]]
    await update.message.reply_text(
        "👋 Salom!\n\n"
        "Men siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\n\n"
        "✍️ Xohlagan narsani yozing — men uni rasmga aylantiraman.\n\n"
        "_Misol:_ Futuristik cyberpunk shahar neon chiroqlar bilan",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    await add_user_db(context.application.bot_data["db_pool"], tg_user)
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "✍️ Endi tasvir yaratish uchun matn yuboring.\n\n_Misol:_ Futuristik cyberpunk shahar neon chiroqlar bilan",
        parse_mode="Markdown"
    )

# ---------------- Prompt qabul qilish ----------------
async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    chat_type = update.effective_chat.type
    text = update.message.text

    # DM: har qanday matn prompt
    if chat_type == "private":
        prompt = text
    # Group: faqat /get bilan boshlangan prompt
    elif chat_type in ["group", "supergroup"]:
        if not text.lower().startswith("/get"):
            return
        prompt = text.partition(" ")[2].strip()
        if not prompt:
            await update.message.reply_text("❌ /get dan keyin prompt yozing")
            return
    else:
        return

    await add_user_db(context.application.bot_data["db_pool"], tg_user)
    context.user_data["prompt"] = prompt
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

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    count = int(query.data.split("_")[1])
    prompt = context.user_data.get("prompt", "")

    waiting_msg = await query.edit_message_text(f"🔄 Rasm yaratilmoqda ({count} ta)...⏳")
    try:
        payload = {
            "prompt": prompt,
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
        # polling for first image
        while True:
            await asyncio.sleep(1)
            async with aiohttp.ClientSession() as check_session:
                try:
                    async with check_session.get(urls[0]) as check:
                        if check.status == 200:
                            break
                except Exception:
                    pass

        await waiting_msg.edit_text("✅ Rasm tayyor! 📸")
        media_group = [InputMediaPhoto(url) for url in urls]
        await query.message.reply_media_group(media_group)

        # log generation
        chat_type = query.message.chat.type
        chat_id = query.message.chat.id
        await log_generation(context.application.bot_data["db_pool"], chat_type, chat_id, user, prompt, image_id, count)

    except Exception as e:
        logger.exception(f"Xatolik generate(): {e}")
        await waiting_msg.edit_text("⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.")

# ---------------- Startup ----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.post_init = on_startup

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(generate, pattern="count_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
