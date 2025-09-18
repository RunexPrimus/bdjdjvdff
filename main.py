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
from decimal import Decimal

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
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))  # e.g. '[{"token":"...","session":"..."}]'
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
# Note: users.lang default is NULL so we can force language selection on first start
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    lang TEXT,
    balance NUMERIC DEFAULT 0
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
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS donations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    username TEXT,
    stars INT,
    payload TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    inviter_id BIGINT,
    invited_id BIGINT UNIQUE,
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

# ---------------- subscription check (optional) ----------------
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.debug(f"[SUB CHECK ERROR] {e}")
        # If can't check, return False to show prompt.
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
async def add_user_db(pool, tg_user) -> bool:
    """
    Ensure user exists. Returns True if user was newly created.
    """
    now = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if row:
            await conn.execute("UPDATE users SET username=$1, last_seen=$2 WHERE id=$3",
                               tg_user.username if tg_user.username else None, now, tg_user.id)
            created = False
        else:
            await conn.execute("INSERT INTO users(id, username, first_seen, last_seen) VALUES($1,$2,$3,$4)",
                               tg_user.id, tg_user.username if tg_user.username else None, now, now)
            created = True
        await conn.execute("INSERT INTO sessions(user_id, started_at) VALUES($1,$2)", tg_user.id, now)
    return created

async def get_user_record(pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)

async def set_user_lang(pool, user_id, lang_code):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET lang=$1 WHERE id=$2", lang_code, user_id)

async def adjust_user_balance(pool, user_id, delta: Decimal):
    async with pool.acquire() as conn:
        # Use numeric arithmetic
        await conn.execute("UPDATE users SET balance = (COALESCE(balance, 0) + $1) WHERE id=$2", str(delta), user_id)

async def log_generation(pool, tg_user, prompt, translated, image_id, count):
    now = utc_now()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO generations(user_id, username, prompt, translated_prompt, image_id, image_count, created_at) "
            "VALUES($1,$2,$3,$4,$5,$6,$7)",
            tg_user.id, tg_user.username if tg_user.username else None,
            prompt, translated, image_id, count, now
        )

# ---------------- Limits / Referral helpers ----------------
FREE_8_PER_DAY = 3
PRICE_PER_8 = Decimal("1")      # 1 Stars
REFERRAL_REWARD = Decimal("0.25")

async def get_8_used_today(pool, user_id) -> int:
    # Count generations where image_count == 8 and created_at >= start of UTC day
    now = utc_now()
    start_day = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM generations WHERE user_id=$1 AND image_count=8 AND created_at >= $2",
            user_id, start_day
        )
    return int(cnt or 0)

async def handle_referral(pool, inviter_id: int, invited_id: int):
    # Add referral only if not exists
    if inviter_id == invited_id:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM referrals WHERE invited_id=$1", invited_id)
        if row:
            return False
        try:
            await conn.execute("INSERT INTO referrals(inviter_id, invited_id) VALUES($1,$2)", inviter_id, invited_id)
            # Give inviter reward
            await conn.execute("UPDATE users SET balance = COALESCE(balance, 0) + $1 WHERE id=$2", str(REFERRAL_REWARD), inviter_id)
            return True
        except asyncpg.UniqueViolationError:
            return False
        except Exception as e:
            logger.exception(f"[REFERRAL ERR] {e}")
            return False

# ---------------- UI: languages ----------------
# 15 languages + Uzbek (Cyrillic)
LANGS = [
    ("🇺🇸 English", "en"),
    ("🇷🇺 Русский", "ru"),
    ("🇮🇩 Indonesia", "id"),
    ("🇱🇹 Lietuvių", "lt"),
    ("🇲🇽 Español (MX)", "es-MX"),
    ("🇪🇸 Español", "es"),
    ("🇮🇹 Italiano", "it"),
    ("🇨🇳 中文", "zh"),
    ("🇺🇿 O'zbek (Latin)", "uz"),
    ("🇺🇿 Кирилл (O'zbek)", "uzk"),
    ("🇧🇩 বাংলা", "bn"),
    ("🇮🇳 हिन्दी", "hi"),
    ("🇧🇷 Português", "pt"),
    ("🇸🇦 العربية", "ar"),
    ("🇺🇦 Українська", "uk"),
    ("🇻🇳 Tiếng Việt", "vi")
]

def build_lang_keyboard():
    kb = []
    row = []
    for label, code in LANGS:
        row.append(InlineKeyboardButton(label, callback_data=f"set_lang_{code}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(kb)

# ---------------- Handlers ----------------

# Small helper to send main panel
async def send_main_panel(chat, lang_code, bot_data):
    """Return InlineKeyboardMarkup for main panel and a text message. lang_code currently unused for translations."""
    kb = [
        [InlineKeyboardButton("🎨 Rasm yaratish", callback_data="start_gen")],
        [InlineKeyboardButton("💖 Donate", callback_data="donate_custom"), InlineKeyboardButton("👤 Hisobim", callback_data="my_account")],
        [InlineKeyboardButton("🌐 Tilni o‘zgartirish", callback_data="change_lang"), InlineKeyboardButton("ℹ️ Statistika / Info", callback_data="show_info")],
    ]
    text = "👋 Bosh panel — bu yerdan rasmlar yaratish, balans va sozlamalarni boshqarishingiz mumkin."
    return text, InlineKeyboardMarkup(kb)

# START
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return

    # Add user and detect if new
    created = await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    user_rec = await get_user_record(context.application.bot_data["db_pool"], update.effective_user.id)
    # Handle referral if present and user is new
    args = []
    if update.message and update.message.text:
        parts = update.message.text.strip().split()
        if len(parts) > 1:
            args = parts[1:]
    # Also use context.args if available (CommandHandler provides it)
    if context.args:
        args = context.args

    if created and args:
        # look for ref_<id>
        for a in args:
            if a.startswith("ref_"):
                try:
                    inviter_id = int(a.split("_", 1)[1])
                    # handle referral
                    await handle_referral(context.application.bot_data["db_pool"], inviter_id, update.effective_user.id)
                except Exception:
                    pass

    # If user has no lang set -> show language selection
    if not user_rec or not user_rec.get("lang"):
        await update.message.reply_text(
            "🌐 Iltimos, tilni tanlang (birinchi marta):",
            reply_markup=build_lang_keyboard()
        )
        return

    # Otherwise send main panel
    text, kb = await send_main_panel(update.effective_chat, user_rec.get("lang"), context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb)

async def change_lang_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🌐 Tilni tanlang:", reply_markup=build_lang_keyboard())

async def set_lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # set_lang_<code>
    code = data.split("_", 2)[2]
    await set_user_lang(context.application.bot_data["db_pool"], q.from_user.id, code)
    # send confirmation and main panel
    text, kb = await send_main_panel(q.message.chat, code, context.application.bot_data)
    try:
        await q.edit_message_text(f"✅ Til {code} ga o'zgartirildi.\n\n{text}", reply_markup=kb)
    except BadRequest:
        try:
            await q.message.reply_text(f"✅ Til {code} ga o'zgartirildi.\n\n{text}", reply_markup=kb)
        except Exception:
            pass

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # simple route to ask prompt
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("✍️ Endi tasvir yaratish uchun matn yuboring (privatda).")

# /get command (works in groups and private) - unchanged
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup"):
        if not context.args:
            await update.message.reply_text("❌ Guruhda /get dan keyin prompt yozing. Misol: /get futuristik shahar")
            return
        prompt = " ".join(context.args)
    else:
        if not context.args:
            await update.message.reply_text("✍️ Iltimos, rasm uchun matn yozing (yoki oddiy matn yuboring).")
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

# Private plain text -> prompt
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    # If conversation for donate is active, PTB will route to conversation handler first.
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

# GENERATE (robust) with limit checks for 8-image batches
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        count = int(q.data.split("_")[1])
    except Exception:
        try:
            await q.edit_message_text("❌ Noto'g'ri tugma.")
        except Exception:
            pass
        return

    user = q.from_user
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", prompt)

    # check 8-image limits
    if count == 8:
        pool = context.application.bot_data["db_pool"]
        used = await get_8_used_today(pool, user.id)
        if used >= FREE_8_PER_DAY:
            # need 1 Stars to proceed
            # check user's balance
            rec = await get_user_record(pool, user.id)
            balance = Decimal(rec.get("balance") or 0)
            if balance < PRICE_PER_8:
                # insufficient
                kb = [
                    [InlineKeyboardButton("💖 Donate", callback_data="donate_custom")],
                    [InlineKeyboardButton("👤 Hisobim", callback_data="my_account")]
                ]
                try:
                    await q.edit_message_text("⚠️ Siz bugun allaqachon 3 marta 8 ta rasm yaratdingiz. Har keyingi 8 ta generatsiya — 1 Stars. Balans yetarli emas.", reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    pass
                return
            else:
                # deduct price
                await adjust_user_balance(pool, user.id, -PRICE_PER_8)
                # notify user
                try:
                    await q.edit_message_text(f"💳 {PRICE_PER_8} Stars yechildi. Rasm yaratilmoqda ({count})... ⏳")
                except BadRequest:
                    pass
        else:
            # free - allowed
            try:
                await q.edit_message_text(f"🔄 Rasm yaratilmoqda ({count})... ⏳ (bugun {used}/{FREE_8_PER_DAY} dan foydalanildi)")
            except BadRequest:
                pass
    else:
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
                text_resp = await resp.text()
                logger.info(f"[DIGEN] status={resp.status}")
                try:
                    data = await resp.json()
                except Exception:
                    logger.error(f"[DIGEN PARSE ERROR] status={resp.status} text={text_resp}")
                    await q.message.reply_text("❌ API dan noma'lum javob keldi. Adminga murojaat qiling.")
                    return

            logger.debug(f"[DIGEN DATA] {json.dumps(data)[:2000]}")

            # try multiple possible locations for id
            image_id = None
            if isinstance(data, dict):
                image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                logger.error("[DIGEN] image_id olinmadi")
                await q.message.reply_text("❌ Rasm ID olinmadi (API javobi).")
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
            logger.info(f"[GENERATE] urls: {urls}")

            # wait loop for first image
            available = False
            max_wait = 60
            waited = 0
            interval = 1.5
            while waited < max_wait:
                try:
                    async with session.get(urls[0]) as chk:
                        if chk.status == 200:
                            available = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(interval)
                waited += interval

            if not available:
                logger.warning("[GENERATE] URL not ready after wait")
                try:
                    await q.edit_message_text("⚠️ Rasmni tayyorlash biroz vaqt olmoqda. Keyinroq urinib ko'ring.")
                except Exception:
                    pass
                return

            # send media group, fallback to single photos
            try:
                media = [InputMediaPhoto(u) for u in urls]
                await q.message.reply_media_group(media)
            except TelegramError as e:
                logger.exception(f"[MEDIA_GROUP ERROR] {e}; fallback to single photos")
                for u in urls:
                    try:
                        await q.message.reply_photo(u)
                    except Exception as ex:
                        logger.exception(f"[SINGLE SEND ERR] {ex}")

            await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)

            try:
                await q.edit_message_text("✅ Rasm tayyor! 📸")
            except BadRequest:
                pass

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        try:
            await q.edit_message_text("⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.")
        except Exception:
            pass

# ---------------- Donate (Stars) flow (unchanged) ----------------
WAITING_AMOUNT = 1

async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    prices = [LabeledPrice(f"{amount} Stars", amount)]
    # provider_token empty for Stars (XTR)
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="💖 Bot Donation",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        provider_token="",  # for XTR leave empty
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    # Keep same logic as before: amount_stars calculation may depend on your currency scaling
    amount_stars = payment.total_amount // 100
    user = update.effective_user
    await update.message.reply_text(f"✅ Rahmat, {user.first_name}! Siz {amount_stars} Stars yubordingiz.")
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload) VALUES($1,$2,$3,$4)",
            user.id, user.username if user.username else None, amount_stars, payment.invoice_payload
        )
    # update user's balance
    await adjust_user_balance(pool, user.id, Decimal(amount_stars))

# ---------------- Hisobim / Account panel ----------------
async def my_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Can be callback_query or message command
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        user_id = q.from_user.id
        chat = q.message.chat
    else:
        user_id = update.effective_user.id
        chat = update.effective_chat

    rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    balance = Decimal(rec.get("balance") or 0)
    # Count referrals
    async with context.application.bot_data["db_pool"].acquire() as conn:
        refs = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id=$1", user_id)
    refs = int(refs or 0)
    referral_link = f"https://t.me/{(os.getenv('BOT_USERNAME') or 'YourBot')}?start=ref_{user_id}"
    text = (
        f"👤 Hisobim\n\n"
        f"💳 Balans: {balance} Stars\n"
        f"👥 Taklif qilinganlar: {refs}\n\n"
        f"🔗 Sizning referral link:\n{referral_link}\n\n"
        f"📤 Yechib olish: Tez kunda\n"
        f"🔑 API: Tez kunda"
    )
    kb = [
        [InlineKeyboardButton("💖 Donate", callback_data="donate_custom"), InlineKeyboardButton("📤 Yechib olish (Tez kunda)", callback_data="withdraw")],
        [InlineKeyboardButton("🌐 Tilni o‘zgartirish", callback_data="change_lang"), InlineKeyboardButton("← Ortga", callback_data="back_main")]
    ]
    if update.callback_query:
        try:
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        except BadRequest:
            try:
                await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
            except Exception:
                pass
    else:
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(kb))

# ---------------- Info / Stats ----------------
async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Send uptime, ping, totals, and admin contact
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        chat = q.message.chat
    else:
        chat = update.effective_chat

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        start_time_row = await conn.fetchrow("SELECT value FROM meta WHERE key='start_time'")
        start_ts = int(start_time_row["value"]) if start_time_row else int(time.time())
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        gen_count = await conn.fetchval("SELECT COUNT(*) FROM generations")
        donation_sum = await conn.fetchval("SELECT COALESCE(SUM(stars),0) FROM donations")
    # uptime
    uptime_seconds = int(time.time()) - start_ts
    uptime_str = str(timedelta(seconds=uptime_seconds))
    # ping measurement (simple HTTP GET to google with timeout)
    ping_ms = None
    try:
        t0 = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.google.com", timeout=2) as resp:
                await resp.text()
        ping_ms = int((time.time() - t0) * 1000)
    except Exception:
        ping_ms = None

    text = (
        f"📊 Statistika\n\n"
        f"⏱ Ish vaqti (uptime): {uptime_str}\n"
        f"🌐 Ping: {f'{ping_ms} ms' if ping_ms is not None else 'Nomaʼlum'}\n"
        f"👥 Foydalanuvchilar: {user_count}\n"
        f"🖼 Umumiy yaratilgan rasmlar: {gen_count}\n"
        f"💰 Umumiy donations: {donation_sum}\n"
    )
    kb = [
        [InlineKeyboardButton("📩 Admin bilan bog‘lanish", url=f"tg://user?id={ADMIN_ID}")],
        [InlineKeyboardButton("← Ortga", callback_data="back_main")]
    ]
    if update.callback_query:
        try:
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        except BadRequest:
            await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(kb))

# ---------------- Simple navigation handlers ----------------
async def back_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rec = await get_user_record(context.application.bot_data["db_pool"], q.from_user.id)
    text, kb = await send_main_panel(q.message.chat, rec.get("lang") if rec else None, context.application.bot_data)
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except BadRequest:
        try:
            await q.message.reply_text(text, reply_markup=kb)
        except Exception:
            pass

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # placeholder
    try:
        await q.edit_message_text("📤 Yechib olish funksiyasi hozircha tayyor emas — Tez kunda! ⏳")
    except Exception:
        pass

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
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized and pool created.")

# ---------------- MAIN ----------------
def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # Basic handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="check_sub"))
    app.add_handler(CommandHandler("get", cmd_get))

    # Language handlers
    app.add_handler(CallbackQueryHandler(set_lang_handler, pattern=r"set_lang_"))
    app.add_handler(CallbackQueryHandler(change_lang_entry, pattern=r"change_lang"))
    app.add_handler(CallbackQueryHandler(back_main_handler, pattern=r"back_main"))
    app.add_handler(CallbackQueryHandler(withdraw_handler, pattern=r"withdraw"))

    # Info / account
    app.add_handler(CommandHandler("info", info_handler))
    app.add_handler(CallbackQueryHandler(info_handler, pattern=r"show_info"))
    app.add_handler(CallbackQueryHandler(my_account_handler, pattern=r"my_account"))

    # Donate conversation MUST be added BEFORE generic text handler
    donate_conv = ConversationHandler(
        entry_points=[CommandHandler("donate", donate_start), CallbackQueryHandler(donate_start, pattern="donate_custom")],
        states={WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[]
    )
    app.add_handler(donate_conv)

    # Payments handlers
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Generate callback
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))

    # private plain text -> prompt handler (after donate_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))

    # errors
    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
