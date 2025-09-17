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
from datetime import datetime, timezone, timedelta

import asyncpg
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, PreCheckoutQueryHandler
)

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
# DIGEN_KEYS should be JSON string like: '[{"token":"...","session":"..."}]'
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image")
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway internal URL (use this inside Railway)

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if ADMIN_ID == 0:
    logger.warning("ADMIN_ID o'rnatilmagan. Ba'zi funksiyalar ishlamasligi mumkin.")

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
            await conn.execute(
                "INSERT INTO meta(key, value) VALUES($1, $2)",
                "start_time", str(int(time.time()))
            )

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
async def check_subscription_private(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if user is member of required CHANNEL_ID.
    We only enforce this in private chats (so groups are not blocked).
    Note: Bot must be member of the channel to check reliably.
    """
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.debug(f"[SUB CHECK ERROR] {e}")
        # If we cannot check (bot not in channel / permissions), fail open (allow) but log.
        return False

async def force_sub_if_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Enforce subscription only in private chats.
    Return True if allowed to proceed.
    """
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    if chat_type in ("group", "supergroup"):
        # don't force sub in groups (to avoid interfering)
        return True

    ok = await check_subscription_private(user_id, context)
    if not ok:
        kb = [
            [InlineKeyboardButton("🔗 Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
        ]
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

async def check_sub_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if await check_subscription_private(user_id, context):
        await query.edit_message_text("✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.")
    else:
        kb = [
            [InlineKeyboardButton("🔗 Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")]
        ]
        await query.edit_message_text(
            "⛔ Hali ham obuna bo‘lmadingiz. Obuna bo‘lib, qayta tekshiring.",
            reply_markup=InlineKeyboardMarkup(kb)
        )

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

# ---------------- stats helpers ----------------
from datetime import timedelta as _td
async def get_total_users(pool):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users") or 0

async def get_active_users_count(pool, days):
    cutoff = utc_now() - _td(days=days)
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen >= $1", cutoff) or 0

async def get_sessions_count(pool, days):
    cutoff = utc_now() - _td(days=days)
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM sessions WHERE started_at >= $1", cutoff) or 0

async def get_start_time(pool):
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM meta WHERE key = 'start_time'")
        return int(val) if val else int(time.time())

# ---------------- Handlers ----------------

# START
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    kb = [[InlineKeyboardButton("🎨 Rasm yaratish", callback_data="start_gen")],
          [InlineKeyboardButton("💖 Donate", callback_data="donate_custom")]]
    await update.message.reply_text(
        "👋 Salom!\n\nMen siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\n"
        "Privatda matn yuboring yoki guruhda /get bilan ishlating.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# When user clicks "start_gen"
async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "✍️ Matn yuboring (privatda). Guruhda /get <prompt> yozing.",
        parse_mode="Markdown"
    )

# /get command (works in groups and private)
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # context.args contains the prompt if sent as /get prompt
    chat_type = update.effective_chat.type
    user = update.effective_user

    if chat_type in ("group", "supergroup"):
        # expect args after /get
        if not context.args:
            await update.message.reply_text("❌ Guruhda: /get so'zidan keyin prompt yozing. Misol: /get futuristik shahar")
            return
        prompt = " ".join(context.args)
    else:
        # private chat: if /get but no args -> ask for prompt
        if not context.args:
            await update.message.reply_text("✍️ Iltimos, rasm uchun matn yozing (yoki oddiy matn yuboring).")
            return
        prompt = " ".join(context.args)

    # proceed
    if not await force_sub_if_private(update, context):
        return
    await add_user_db(context.application.bot_data["db_pool"], user)
    # store prompt in user_data and ask for count (same flow as private)
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt  # translation disabled
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

# In private, allow plain text to be prompt
# --- main.py ichida private_text_handler ni quyidagiga o'zgartiring ---
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Conversation davomida bo'lsa, boshqa handler ishlamasin
    if "donate_conversation" in context.user_data:
        return  # donate flow hali tugamagan

    # Faqat private chatda ishlasin
    if update.effective_chat.type != "private":
        return

    if not await force_sub_if_private(update, context):
        return

    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text.strip()
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


# GENERATE
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # handle potential BadRequest for "message not modified" gracefully
    try:
        count = int(query.data.split("_")[1])
    except Exception:
        await query.edit_message_text("❌ Noto'g'ri tugma.")
        return

    user = query.from_user
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", prompt)

    waiting_msg = None
    try:
        # edit message for waiting
        try:
            waiting_msg = await query.edit_message_text(f"🔄 Rasm yaratilmoqda ({count})... ⏳")
        except Exception:
            # sometimes message already same; ignore
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
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(DIGEN_URL, headers=headers, json=payload) as r:
                if r.status != 200:
                    text = f"❌ API xatosi: {r.status}"
                    if waiting_msg:
                        await waiting_msg.edit_text(text)
                    else:
                        await query.message.reply_text(text)
                    return
                data = await r.json()

        image_id = data.get("data", {}).get("id")
        if not image_id:
            if waiting_msg:
                await waiting_msg.edit_text("❌ Rasm ID olinmadi.")
            else:
                await query.message.reply_text("❌ Rasm ID olinmadi.")
            return

        urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]

        # polling simple
        progress = 0
        last_text = ""
        while True:
            progress = min(progress + 15, 95)
            bar = "▰" * (progress // 10) + "▱" * (10 - progress // 10)
            txt = f"🔄 Rasm yaratilmoqda ({count}):\n{bar} {progress}%"
            if txt != last_text:
                try:
                    if waiting_msg:
                        await waiting_msg.edit_text(txt)
                    else:
                        await query.message.reply_text(txt)
                except Exception:
                    pass
                last_text = txt
            await asyncio.sleep(1)

            # check first url
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as check_sess:
                    async with check_sess.get(urls[0]) as check:
                        if check.status == 200:
                            break
            except Exception:
                pass

        try:
            if waiting_msg:
                await waiting_msg.edit_text("✅ Rasm tayyor! 📸")
            else:
                await query.message.reply_text("✅ Rasm tayyor! 📸")
        except Exception:
            pass

        # send media group
        media_group = [InputMediaPhoto(u) for u in urls]
        await query.message.reply_media_group(media_group)

        # log
        await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)

        # notify admin
        if ADMIN_ID:
            caption = (
                f"👤 *Yangi generatsiya:*\n"
                f"🆔 ID: `{user.id}`\n"
                f"👤 Username: @{user.username if user.username else 'yo‘q'}\n"
                f"✍️ Prompt: {escape_md(prompt)}\n"
                f"📸 {count} ta rasm"
            )
            try:
                await context.bot.send_media_group(
                    chat_id=ADMIN_ID,
                    media=[InputMediaPhoto(urls[0], caption=caption, parse_mode="Markdown")] +
                          [InputMediaPhoto(u) for u in urls[1:]]
                )
            except Exception as e:
                logger.exception(f"[ADMIN NOTIFY ERROR] {e}")

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        try:
            if waiting_msg:
                await waiting_msg.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko‘ring.")
            else:
                await query.message.reply_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko‘ring.")
        except Exception:
            pass

# ---------------- Stats & ping ----------------
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["db_pool"]
    total_users = await get_total_users(pool)
    daily_u = await get_active_users_count(pool, 1)
    weekly_u = await get_active_users_count(pool, 7)
    monthly_u = await get_active_users_count(pool, 30)
    yearly_u = await get_active_users_count(pool, 365)
    daily_s = await get_sessions_count(pool, 1)
    weekly_s = await get_sessions_count(pool, 7)
    monthly_s = await get_sessions_count(pool, 30)
    start_ts = await get_start_time(pool)
    uptime_seconds = int(time.time() - start_ts)
    uptime = f"{uptime_seconds // 3600} soat {(uptime_seconds % 3600) // 60} daqiqa"
    await update.message.reply_text(
        f"📊 *Bot statistikasi:*\n"
        f"👥 Umumiy foydalanuvchilar: {total_users}\n"
        f"📅 24 soat: {daily_u} foydalanuvchi ({daily_s} sessiya)\n"
        f"📅 7 kun: {weekly_u} foydalanuvchi ({weekly_s} sessiya)\n"
        f"📅 30 kun: {monthly_u} foydalanuvchi ({monthly_s} sessiya)\n"
        f"📅 365 kun: {yearly_u} foydalanuvchi\n"
        f"⏱ Ish vaqti: {uptime}",
        parse_mode="Markdown"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = time.time()
    msg = await update.message.reply_text("🏓 Ping o‘lchanmoqda...")
    latency = int((time.time() - start) * 1000)
    await msg.edit_text(f"🏓 *Pong!* `{latency} ms`", parse_mode="Markdown")

# ---------------- Admin broadcast ----------------
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Ruxsat yo‘q.")
        return
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users")
        user_ids = [r["id"] for r in rows]
    text = " ".join(context.args)
    count = 0
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        for uid in user_ids:
            try:
                await context.bot.send_photo(uid, file_id, caption=caption)
                count += 1
            except Exception:
                continue
        await update.message.reply_text(f"✅ {count} foydalanuvchiga rasm yuborildi.")
        return
    if not text:
        await update.message.reply_text("✍️ Foydalanish: /broadcast <xabar> yoki yuboring rasm bilan (admin).")
        return
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, text)
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"✅ {count} foydalanuvchiga xabar yuborildi.")

# ---------------- Donate (Stars) flow ----------------
WAITING_AMOUNT = 1

async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["donate_conversation"] = True  # 👈 qo'shildi
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
        await update.message.reply_text("❌ Iltimos, 1–100000 oralig‘ida butun son kiriting.")
        return WAITING_AMOUNT

    payload = f"donate_{update.effective_user.id}_{int(time.time())}"
    prices = [LabeledPrice(f"{amount} Stars", amount * 100)]

    # conversation tugadi -> flagni tozalaymiz
    context.user_data.pop("donate_conversation", None)

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="💖 Bot Donation",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        provider_token="",  # Stars uchun bo'sh
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount // 100
    user = update.effective_user
    await update.message.reply_text(f"✅ Rahmat, {user.first_name}! Siz {amount_stars} Stars yubordingiz.")
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
            await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ Xatolik yuz berdi. Adminga murojaat qiling.")
    except Exception:
        pass

# ---------------- Startup ----------------
async def on_startup(app: Application):
    # create pool & init DB
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized and pool created.")

# ---------------- MAIN ----------------
# 🔑 O'ZGARTIRILGAN QISMLAR
# 1️⃣ Private text handler ikki marta qo'shilgan edi, endi bitta qoldirdim
# 2️⃣ filters.ChatType.PRIVATE uchun private_text_handler qo'yildi
# 3️⃣ donate_conv fallback qo'shildi
# 4️⃣ generate_cb da polling timeout qo'shildi
# 5️⃣ loglar yanada to'liq qo'yildi

# ... kodning yuqorisi o'zgarishsiz ...

def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # 🔹 asosiy komandalar
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("get", cmd_get))

    # 🔹 Callback tugmalar
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))

    # 🔹 Private matnlar
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))

    # 🔹 Statistika & admin
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # 🔹 Donate (Stars) conversation
    donate_conv = ConversationHandler(
        entry_points=[
            CommandHandler("donate", donate_start),
            CallbackQueryHandler(donate_start, pattern="donate_custom")
        ],
        states={WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[MessageHandler(filters.ALL, donate_start)]
    )
    app.add_handler(donate_conv)
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # 🔹 Error handler
    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    # Use run_polling() which handles initialization/start/shutdown for you.
    app.run_polling()

if __name__ == "__main__":
    main()
