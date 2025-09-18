#!/usr/bin/env python3
# main.py
import logging
import aiohttp
import asyncio
import re
import os
import json
import random
import time
from datetime import datetime, timezone

import asyncpg
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, PreCheckoutQueryHandler
)
from telegram.error import BadRequest, TelegramError

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@SizningKanal")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)

# ---------------- helpers ----------------
def escape_md(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~>#+\-=|{}.!])', r'\\\1', text)

def utc_now():
    return datetime.now(timezone.utc)

# ---------------- DB schema ----------------
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
            await conn.execute("INSERT INTO meta(key, value) VALUES($1, $2)", "start_time", str(int(time.time())))

# ---------------- Digen headers ----------------
def get_digen_headers():
    if not DIGEN_KEYS:
        return {}
    key = random.choice(DIGEN_KEYS)
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "digen-language": "uz-US",
        "digen-platform": "web",
        "digen-token": key.get("token", ""),
        "digen-sessionid": key.get("session", ""),
        "origin": "https://rm.digen.ai",
        "referer": "https://rm.digen.ai/",
    }

# ---------------- subscription check ----------------
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.debug(f"[SUB CHECK ERROR] {e}")
        return False

async def force_sub_if_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type != "private":
        return True
    ok = await check_subscription(update.effective_user.id, context)
    if not ok:
        kb = [
            [InlineKeyboardButton("🔗 Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text("⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!", reply_markup=InlineKeyboardMarkup(kb))
        return False
    return True

async def check_sub_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if await check_subscription(user_id, context):
        await q.edit_message_text("✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.")
    else:
        kb = [
            [InlineKeyboardButton("🔗 Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
        ]
        await q.edit_message_text("⛔ Hali ham obuna bo‘lmagansiz. Obuna bo‘lib, qayta tekshiring.", reply_markup=InlineKeyboardMarkup(kb))

# ---------------- DB user/session/logging ----------------
async def add_user_db(pool, tg_user):
    now = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if row:
            await conn.execute("UPDATE users SET username=$1, last_seen=$2 WHERE id=$3",
                               tg_user.username if tg_user.username else None, now, tg_user.id)
        else:
            await conn.execute("INSERT INTO users(id, username, first_seen, last_seen) VALUES($1,$2,$3,$4)",
                               tg_user.id, tg_user.username if tg_user.username else None, now, now)
        await conn.execute("INSERT INTO sessions(user_id, started_at) VALUES($1,$2)", tg_user.id, now)

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
    if not await force_sub_if_private(update, context):
        return
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    kb = [
        [InlineKeyboardButton("🎨 Rasm yaratish", callback_data="start_gen")],
        [InlineKeyboardButton("💖 Donat qilish", callback_data="donate_custom")]
    ]
    await update.message.reply_text(
        "👋 Salom!\n\nMen siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\n"
        "✍️ Xohlagan narsani yozing — men uni rasmga aylantiraman.\n\n"
        "💖 Botni qo‘llab-quvvatlash uchun pastdagi tugmani bosing.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("✍️ Endi tasvir yaratish uchun matn yuboring.")

async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return
    if context.application.user_data.get(update.effective_user.id, {}).get("donate_mode"):
        return  # donate rejimida prompt qabul qilmaymiz
    if not context.args:
        await update.message.reply_text("✍️ Iltimos, rasm uchun matn yozing.")
        return
    prompt = " ".join(context.args)
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt
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

async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ❌ Agar donate state-da bo'lsa prompt sifatida ishlamaydi
    if context.application.user_data.get(update.effective_user.id, {}).get("donate_mode"):
        return
    if update.effective_chat.type != "private":
        return
    if not await force_sub_if_private(update, context):
        return
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt
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

async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        count = int(q.data.split("_")[1])
    except Exception:
        await q.edit_message_text("❌ Noto‘g‘ri tugma.")
        return

    user = q.from_user
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", prompt)

    try:
        await q.edit_message_text(f"🔄 Rasm yaratilmoqda ({count})... ⏳")
    except BadRequest:
        pass

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
    sess_timeout = aiohttp.ClientTimeout(total=180)

    try:
        async with aiohttp.ClientSession(timeout=sess_timeout) as session:
            async with session.post(DIGEN_URL, headers=headers, json=payload) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    await q.message.reply_text("❌ API javobini o‘qib bo‘lmadi.")
                    return

            image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                await q.message.reply_text("❌ Rasm ID olinmadi.")
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]

            available = False
            waited = 0
            while waited < 60:
                try:
                    async with session.get(urls[0]) as chk:
                        if chk.status == 200:
                            available = True
                            break
                except:
                    pass
                await asyncio.sleep(1.5)
                waited += 1.5

            if not available:
                await q.edit_message_text("⚠️ Rasm tayyor bo‘lmadi.")
                return

            try:
                media = [InputMediaPhoto(u) for u in urls]
                for i in range(0, len(media), 10):
                    await q.message.reply_media_group(media[i:i+10])
            except TelegramError:
                for u in urls:
                    await q.message.reply_photo(u)

            await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)

            try:
                admin_text = (
                    f"👤 <b>Yangi Generatsiya</b>\n"
                    f"🆔 <code>{user.id}</code>\n"
                    f"👥 @{user.username or 'no_username'}\n"
                    f"🖊 Prompt: <code>{escape_md(prompt)}</code>\n"
                    f"📸 Rasmlar soni: {count}\n"
                    f"🕒 {utc_now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"[ADMIN NOTIFY ERROR] {e}")

            await q.edit_message_text("✅ Rasm tayyor! 📸")

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        await q.edit_message_text("⚠️ Xatolik yuz berdi.")

# ---------------- Donate ----------------
WAITING_AMOUNT = 1

async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("[DONATE] donate_start chaqirildi!")
    context.application.user_data.setdefault(update.effective_user.id, {})["donate_mode"] = True
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):")
    else:
        await update.message.reply_text("💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):")
    return WAITING_AMOUNT

async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ 1–100000 oralig‘ida butun son kiriting.")
        return WAITING_AMOUNT

    payload = f"donate_{update.effective_user.id}_{int(time.time())}"
    prices = [LabeledPrice(f"{amount} ⭐", amount)]
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="💖 Donat",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        currency="XTR",
        prices=prices
    )
    context.application.user_data[update.effective_user.id]["donate_mode"] = False
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount
    user = update.effective_user
    await update.message.reply_text(f"✅ Rahmat, {user.first_name}! Siz {amount_stars} ⭐ yubordingiz.")
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload) VALUES($1,$2,$3,$4)",
            user.id, user.username if user.username else None, amount_stars, payment.invoice_payload
        )

# ---------------- Error handler ----------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ Xatolik yuz berdi.")
    except Exception:
        pass

# ---------------- Startup ----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized and pool created.")

# ---------------- MAIN ----------------
def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="check_sub"))
    app.add_handler(CommandHandler("get", cmd_get))

    donate_conv = ConversationHandler(
        entry_points=[
            CommandHandler("donate", donate_start),
            CallbackQueryHandler(donate_start, pattern="donate_custom")
        ],
        states={WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[]
    )
    app.add_handler(donate_conv)

    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))

    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
