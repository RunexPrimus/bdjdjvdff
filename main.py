# bot_postgres_group.py
import logging
import aiohttp
import asyncio
import os
import json
import itertools
import random
import time
from datetime import datetime, timezone, timedelta

import asyncpg
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
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
_key_cycle = itertools.cycle(DIGEN_KEYS)
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"
DATABASE_URL = os.getenv("DATABASE_URL")

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

# ---------------- Database ----------------
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

# ---------------- Digen ----------------
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

# ---------------- Subscription ----------------
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.debug(f"[SUB CHECK ERROR] {e}")
        return False

async def force_sub_required(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    subscribed = await check_subscription(user_id, context)
    logger.info(f"[FORCE SUB] user_id={user_id}, subscribed={subscribed}")
    if not subscribed:
        kb = [[
            InlineKeyboardButton("🔗 Obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"),
        ], [
            InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")
        ]]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(
                "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await update.message.reply_text(
                "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        return False
    return True

async def check_sub_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    subscribed = await check_subscription(user_id, context)
    logger.info(f"[CHECK BUTTON] user_id={user_id}, subscribed={subscribed}")
    if subscribed:
        await query.edit_message_text("✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.")
    else:
        kb = [[
            InlineKeyboardButton("🔗 Obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}"),
        ], [
            InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")
        ]]
        await query.edit_message_text(
            "⛔ Hali ham obuna bo‘lmadiz. Obuna bo‘lib, qayta tekshiring.",
            reply_markup=InlineKeyboardMarkup(kb)
        )

# ---------------- DB utils ----------------
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
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "✍️ Endi tasvir yaratish uchun matn yuboring.\n\n_Misol:_ Futuristik cyberpunk shahar neon chiroqlar bilan",
        parse_mode="Markdown"
    )

# --- /get handler for groups ---
async def get_prompt_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        return
    text = update.message.text
    if not text.lower().startswith("/get"):
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("✍️ /get so‘zidan keyin prompt yozing.")
        return
    prompt = parts[1]
    if not await force_sub_required(update, context):
        return
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt
    await ask_image_count_group(update, context)

async def ask_image_count_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# --- generate handler ---
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    count = int(query.data.split("_")[1])
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", "")

    waiting_msg = await query.edit_message_text(f"🔄 Rasm yaratilmoqda ({count} ta)...⏳", parse_mode="Markdown")
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
        await asyncio.sleep(2)  # simple wait
        media_group = [InputMediaPhoto(url) for url in urls]
        await query.message.reply_media_group(media_group)
        await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)
    except Exception as e:
        logger.exception(f"Generate error: {e}")
        await waiting_msg.edit_text("⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.")

# ---------------- Startup ----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized and pool created.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.post_init = on_startup

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(generate, pattern="count_"))
    app.add_handler(CallbackQueryHandler(check_sub_button, pattern="check_sub"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, get_prompt_group))

    app.run_polling()

if __name__ == "__main__":
    main()
