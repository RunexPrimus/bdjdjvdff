#!/usr/bin/env python3
# main.py
import os
import re
import time
import json
import random
import logging
import asyncio
from datetime import datetime, timezone

import aiohttp
import asyncpg
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, PreCheckoutQueryHandler, filters
)
from telegram.error import BadRequest, TelegramError

# ----------------- CONFIG & LOG -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@YourChannel")
# Digen endpoint (o'zingizniki bilan almashtiring)
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN kerak. ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL kerak. ENV ga qo'ying.")
    raise SystemExit(1)

# ----------------- DB SCHEMA -----------------
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

# ----------------- HELPERS -----------------
def utc_now():
    return datetime.now(timezone.utc)

def escape_md(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~>#+\-=|{}.!])', r'\\\1', text)

def get_digen_headers():
    # agar sizda token/session list bo'lsa, shu yerni kengaytiring
    return {"accept": "application/json", "content-type": "application/json"}

# ----------------- DB UTIL -----------------
async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        row = await conn.fetchrow("SELECT value FROM meta WHERE key='start_time'")
        if not row:
            await conn.execute("INSERT INTO meta(key, value) VALUES($1,$2)", "start_time", str(int(time.time())))

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

async def log_donation(pool, tg_user, stars, payload):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload) VALUES($1,$2,$3,$4)",
            tg_user.id, tg_user.username if tg_user.username else None, stars, payload
        )

# ----------------- SUBSCRIPTION CHECK -----------------
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

# ----------------- HANDLERS -----------------
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
        "💖 Donat uchun tugmani bosing yoki /donate buyrug'ini yozing.",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def start_gen_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("✍️ Endi tasvir yaratish uchun matn yuboring.")

# PROMPT HANDLERS
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Iltimos, /get <prompt> tarzida yozing.")
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
    # Agar donate rejimida bo'lsa prompt qabul qilinmaydi
    if context.user_data.get("donate_mode"):
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

# GENERATE WITH PROGRESS
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
        status_msg = await q.edit_message_text(f"🔄 Rasm yaratilmoqda ({count})... 0%")
    except BadRequest:
        status_msg = q.message  # fallback

    payload = {
        "prompt": translated,
        "image_size": "512x512",
        "width": 512,
        "height": 512,
        "batch_size": count,
        "reference_images": []
    }
    headers = get_digen_headers()
    sess_timeout = aiohttp.ClientTimeout(total=240)

    try:
        async with aiohttp.ClientSession(timeout=sess_timeout) as session:
            async with session.post(DIGEN_URL, headers=headers, json=payload) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    await status_msg.edit_text("❌ API javobini o‘qib bo‘lmadi.")
                    return

            image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                await status_msg.edit_text("❌ Rasm ID olinmadi.")
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]

            # Poll for image availability with progress
            available = False
            waited = 0.0
            progress = 0
            timeout_seconds = 90.0
            step = 1.5
            while waited < timeout_seconds:
                new_progress = int((waited / timeout_seconds) * 100)
                if new_progress - progress >= 5:
                    progress = new_progress
                    try:
                        await status_msg.edit_text(f"🔄 Rasm yaratilmoqda ({count})... {progress}%")
                    except Exception:
                        pass
                try:
                    async with session.get(urls[0]) as chk:
                        if chk.status == 200:
                            available = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(step)
                waited += step

            if not available:
                await status_msg.edit_text("⚠️ Rasm tayyor bo‘lmadi yoki yuklanmadi.")
                return

            # Send images
            media = [InputMediaPhoto(u) for u in urls]
            try:
                for i in range(0, len(media), 10):
                    await q.message.reply_media_group(media[i:i+10])
            except TelegramError:
                for u in urls:
                    try:
                        await q.message.reply_photo(u)
                    except Exception:
                        pass

            await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)

            # notify admin
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

            try:
                await status_msg.edit_text("✅ Rasm tayyor! 📸")
            except Exception:
                pass

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        try:
            await status_msg.edit_text("⚠️ Xatolik yuz berdi.")
        except Exception:
            pass

# ----------------- DONATE FLOW (Telegram Stars XTR) -----------------
WAITING_AMOUNT = 1

async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # mark user in donate mode (so prompt handler ignores their next message)
    context.user_data["donate_mode"] = True
    text = "💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)
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

    # For Telegram Stars (XTR) provider_token usually not required; omit provider_token to avoid empty string issues
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="💖 Donat",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        currency="XTR",
        prices=prices
    )

    # clear donate flag
    context.user_data["donate_mode"] = False
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount
    user = update.effective_user
    await update.message.reply_text(f"✅ Rahmat, {user.first_name}! Siz {amount_stars} ⭐ yubordingiz.")
    # Save donation to DB
    try:
        await log_donation(context.application.bot_data["db_pool"], user, amount_stars, payment.invoice_payload)
    except Exception as e:
        logger.warning(f"[DONATION LOG ERROR] {e}")

# ----------------- PING & STATS & BROADCAST -----------------
async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = utc_now()
    # message date is in UTC
    try:
        msg_time = update.message.date.replace(tzinfo=timezone.utc)
        latency = (now - msg_time).total_seconds() * 1000
        await update.message.reply_text(f"Pong! ⏱ {int(latency)} ms")
    except Exception:
        await update.message.reply_text("Pong!")

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        gens_count = await conn.fetchval("SELECT COUNT(*) FROM generations")
        dons_count = await conn.fetchval("SELECT COUNT(*) FROM donations")
    await update.message.reply_text(f"📊 Statistika:\n👥 Foydalanuvchilar: {users_count}\n🖼 Generatsiyalar: {gens_count}\n💖 Donatlar: {dons_count}")

# Broadcast (admin only)
BROADCAST_WAITING = 1
BROADCAST_CONFIRM = 2

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END
    await update.message.reply_text("✉️ Yubormoqchi bo‘lgan matnni yuboring (media yo'q — faqat matn).")
    return BROADCAST_WAITING

async def broadcast_message_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["broadcast_text"] = text
    kb = [
        [InlineKeyboardButton("✅ Ha, yubor", callback_data="broadcast_send")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="broadcast_cancel")]
    ]
    await update.message.reply_text(f"Xabar tayyor:\n\n{text}\n\nYuborishni tasdiqlaysizmi?", reply_markup=InlineKeyboardMarkup(kb))
    return BROADCAST_CONFIRM

async def broadcast_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "broadcast_cancel":
        await q.edit_message_text("📴 Broadcast bekor qilindi.")
        return ConversationHandler.END
    elif data == "broadcast_send":
        # Fetch users
        pool = context.application.bot_data["db_pool"]
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM users")
        total = len(rows)
        sent = 0
        failed = 0
        status = await q.edit_message_text(f"🚀 Broadcast boshlanmoqda... 0/{total}")
        for i, r in enumerate(rows, start=1):
            uid = r["id"]
            try:
                await context.bot.send_message(uid, context.user_data.get("broadcast_text", ""))
                sent += 1
            except BadRequest as e:
                # user blocked bot or chat not found
                failed += 1
            except Exception as e:
                failed += 1
            # update every 10 messages
            if i % 10 == 0 or i == total:
                try:
                    await status.edit_text(f"🚀 Broadcast: {i}/{total} — yuborildi: {sent}, xato: {failed}")
                except Exception:
                    pass
            await asyncio.sleep(0.07)  # to avoid hitting rate limits
        try:
            await status.edit_text(f"✅ Broadcast tugadi. yuborildi: {sent}, xato: {failed}")
        except Exception:
            pass
        return ConversationHandler.END

# ----------------- ERROR HANDLER -----------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ Xatolik yuz berdi.")
    except Exception:
        pass

# ----------------- STARTUP -----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized and pool created.")

# ----------------- MAIN -----------------
def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # Basic handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(start_gen_cb, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="check_sub"))

    # Prompt handlers
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))

    # Donate Conversation
    donate_conv = ConversationHandler(
        entry_points=[CommandHandler("donate", donate_start), CallbackQueryHandler(donate_start, pattern="donate_custom")],
        states={WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[],
    )
    app.add_handler(donate_conv)
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Ping / stats
    app.add_handler(CommandHandler("ping", ping_handler))
    app.add_handler(CommandHandler("stats", stats_handler))

    # Broadcast conv (admin)
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_received)],
            BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_cb, pattern="^broadcast_")]
        },
        fallbacks=[]
    )
    app.add_handler(broadcast_conv)

    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
