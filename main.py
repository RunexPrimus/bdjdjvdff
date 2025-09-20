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
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))  # e.g. '[{"token":"...","session":"..."}]'
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)

# ---------------- STATE ----------------
LANGUAGE_SELECT, WAITING_AMOUNT = range(2)

# ---------------- Til sozlamalari ----------------
LANGUAGES = {
    "uz": {
        "flag": "🇺🇿",
        "name": "O'zbekcha",
        "welcome": "👋 Salom!\n\nMen siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\nPrivatda matn yuboring yoki guruhda /get bilan ishlating.",
        "gen_button": "🎨 Rasm yaratish",
        "donate_button": "💖 Donate",
        "prompt_text": "✍️ Endi tasvir yaratish uchun matn yuboring (privatda).",
        "select_count": "🔢 Nechta rasm yaratilsin?",
        "generating": "🔄 Rasm yaratilmoqda ({count})... ⏳",
        "success": "✅ Rasm tayyor! 📸",
        "error": "⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.",
        "donate_prompt": "💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):",
        "donate_invalid": "❌ Iltimos, 1–100000 oralig‘ida butun son kiriting.",
        "donate_thanks": "✅ Rahmat, {name}! Siz {stars} Stars yubordingiz.",
        "refund_success": "✅ {stars} Stars muvaffaqiyatli qaytarildi foydalanuvchi {user_id} ga.",
        "refund_error": "❌ Xatolik: {error}",
        "no_permission": "⛔ Sizga ruxsat yo'q.",
        "usage_refund": "UsageId: /refund <user_id> <donation_id>",
        "not_found": "❌ Topilmadi yoki noto'g'ri ma'lumot.",
        "no_charge_id": "❌ Bu to'lovda charge_id yo'q (eski to'lov).",
        "sub_prompt": "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
        "sub_check": "✅ Obunani tekshirish",
        "sub_url_text": "🔗 Kanalga obuna bo‘lish",
        "sub_thanks": "✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.",
        "sub_still_not": "⛔ Hali ham obuna bo‘lmagansiz. Obuna bo‘lib, qayta tekshiring.",
    },
    "ru": {
        "flag": "🇷🇺",
        "name": "Русский",
        "welcome": "👋 Привет!\n\nЯ создаю для вас изображения с помощью ИИ.\nОтправляйте текст в личку или используйте /get в группе.",
        "gen_button": "🎨 Создать изображение",
        "donate_button": "💖 Поддержать",
        "prompt_text": "✍️ Теперь отправьте текст для создания изображения (в личку).",
        "select_count": "🔢 Сколько изображений создать?",
        "generating": "🔄 Создаю изображение ({count})... ⏳",
        "success": "✅ Изображение готово! 📸",
        "error": "⚠️ Произошла ошибка. Попробуйте еще раз.",
        "donate_prompt": "💰 Пожалуйста, введите сумму для отправки (1–100000):",
        "donate_invalid": "❌ Пожалуйста, введите целое число от 1 до 100000.",
        "donate_thanks": "✅ Спасибо, {name}! Вы отправили {stars} Stars.",
        "refund_success": "✅ {stars} Stars успешно возвращены пользователю {user_id}.",
        "refund_error": "❌ Ошибка: {error}",
        "no_permission": "⛔ У вас нет разрешения.",
        "usage_refund": "Использование: /refund <user_id> <donation_id>",
        "not_found": "❌ Не найдено или неверные данные.",
        "no_charge_id": "❌ В этом платеже нет charge_id (старый платеж).",
        "sub_prompt": "⛔ Чтобы пользоваться ботом, подпишитесь на наш канал!",
        "sub_check": "✅ Проверить подписку",
        "sub_url_text": "🔗 Подписаться на канал",
        "sub_thanks": "✅ Спасибо! Вы подписаны. Теперь вы можете пользоваться ботом.",
        "sub_still_not": "⛔ Вы все еще не подписаны. Подпишитесь и проверьте снова.",
    },
    "en": {
        "flag": "🇬🇧",
        "name": "English",
        "welcome": "👋 Hello!\n\nI create images for you using AI.\nSend text in private or use /get in group.",
        "gen_button": "🎨 Generate Image",
        "donate_button": "💖 Donate",
        "prompt_text": "✍️ Now send the text to generate an image (in private).",
        "select_count": "🔢 How many images to generate?",
        "generating": "🔄 Generating image ({count})... ⏳",
        "success": "✅ Image ready! 📸",
        "error": "⚠️ An error occurred. Please try again.",
        "donate_prompt": "💰 Please enter the amount you wish to send (1–100000):",
        "donate_invalid": "❌ Please enter a whole number between 1 and 100000.",
        "donate_thanks": "✅ Thank you, {name}! You sent {stars} Stars.",
        "refund_success": "✅ {stars} Stars successfully refunded to user {user_id}.",
        "refund_error": "❌ Error: {error}",
        "no_permission": "⛔ You don't have permission.",
        "usage_refund": "Usage: /refund <user_id> <donation_id>",
        "not_found": "❌ Not found or invalid data.",
        "no_charge_id": "❌ This payment has no charge_id (old payment).",
        "sub_prompt": "⛔ Subscribe to our channel to use the bot!",
        "sub_check": "✅ Check Subscription",
        "sub_url_text": "🔗 Subscribe to Channel",
        "sub_thanks": "✅ Thank you! You are subscribed. You can now use the bot.",
        "sub_still_not": "⛔ You are still not subscribed. Subscribe and check again.",
    }
}

DEFAULT_LANGUAGE = "uz"

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
    last_seen TIMESTAMPTZ,
    language_code TEXT DEFAULT 'uz'
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
    charge_id TEXT,
    refunded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
        row = await conn.fetchrow("SELECT value FROM meta WHERE key = 'start_time'")
        if not row:
            await conn.execute("INSERT INTO meta(key, value) VALUES($1, $2)", "start_time", str(int(time.time())))
        
        # Yangi ustunlarni qo'shish (agar mavjud bo'lmasa)
        try:
            # users jadvalida language_code borligini tekshirish
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language_code TEXT DEFAULT 'uz'")
            logger.info("✅ Added column 'language_code' to table 'users'")
        except Exception as e:
            logger.info(f"ℹ️ Column 'language_code' already exists or error: {e}")
        
        # donations jadvalida charge_id va refunded_at borligini tekshirish
        try:
            await conn.execute("ALTER TABLE donations ADD COLUMN IF NOT EXISTS charge_id TEXT")
            await conn.execute("ALTER TABLE donations ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ")
            logger.info("✅ Added columns 'charge_id', 'refunded_at' to table 'donations'")
        except Exception as e:
            logger.info(f"ℹ️ Columns already exist or error: {e}")
# ---------------- Digen headers ----------------
def get_digen_headers():
    if not DIGEN_KEYS:
        return {}
    key = random.choice(DIGEN_KEYS)
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "digen-language": "en-US",  # API uchun doim ingliz
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
        return False

async def force_sub_if_private(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_code=None) -> bool:
    if update.effective_chat.type != "private":
        return True
    ok = await check_subscription(update.effective_user.id, context)
    if not ok:
        lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE]) if lang_code else LANGUAGES[DEFAULT_LANGUAGE]
        kb = [
            [InlineKeyboardButton(lang["sub_url_text"], url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(lang["sub_check"], callback_data="check_sub")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(lang["sub_prompt"], reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(lang["sub_prompt"], reply_markup=InlineKeyboardMarkup(kb))
        return False
    return True

async def check_sub_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    # Foydalanuvchi tilini olish
    lang_code = None
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE]) if lang_code else LANGUAGES[DEFAULT_LANGUAGE]
    
    if await check_subscription(user_id, context):
        await q.edit_message_text(lang["sub_thanks"])
    else:
        kb = [
            [InlineKeyboardButton(lang["sub_url_text"], url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(lang["sub_check"], callback_data="check_sub")]
        ]
        await q.edit_message_text(lang["sub_still_not"], reply_markup=InlineKeyboardMarkup(kb))

# ---------------- DB user/session/logging ----------------
async def add_user_db(pool, tg_user, lang_code=None):
    now = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if row:
            update_fields = "username=$1, last_seen=$2"
            params = [tg_user.username if tg_user.username else None, now, tg_user.id]
            if lang_code:
                update_fields += ", language_code=$3"
                params = [tg_user.username if tg_user.username else None, now, lang_code, tg_user.id]
            await conn.execute(f"UPDATE users SET {update_fields} WHERE id=$4", *params)
        else:
            lang_code = lang_code or DEFAULT_LANGUAGE
            await conn.execute("INSERT INTO users(id, username, first_seen, last_seen, language_code) VALUES($1,$2,$3,$4,$5)",
                               tg_user.id, tg_user.username if tg_user.username else None, now, now, lang_code)
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

# START - Tilni tanlash
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton(f"{LANGUAGES['uz']['flag']} {LANGUAGES['uz']['name']}", callback_data="lang_uz")],
        [InlineKeyboardButton(f"{LANGUAGES['ru']['flag']} {LANGUAGES['ru']['name']}", callback_data="lang_ru")],
        [InlineKeyboardButton(f"{LANGUAGES['en']['flag']} {LANGUAGES['en']['name']}", callback_data="lang_en")],
    ]
    await update.message.reply_text("🌐 Iltimos, tilni tanlang / Пожалуйста, выберите язык / Please select language:", reply_markup=InlineKeyboardMarkup(kb))
    return LANGUAGE_SELECT

async def language_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = q.data.split("_")[1]
    context.user_data["language"] = lang_code

    # DBga saqlash
    await add_user_db(context.application.bot_data["db_pool"], q.from_user, lang_code)

    lang = LANGUAGES[lang_code]
    kb = [
        [InlineKeyboardButton(lang["gen_button"], callback_data="start_gen")],
        [InlineKeyboardButton(lang["donate_button"], callback_data="donate_custom")]
    ]
    await q.edit_message_text(lang["welcome"], reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    # Tilni olish
    lang_code = context.user_data.get("language", DEFAULT_LANGUAGE)
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    await q.message.reply_text(lang["prompt_text"])

# /get command (works in groups and private)
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_code = DEFAULT_LANGUAGE
    if update.effective_chat.type == "private":
        # Foydalanuvchi tilini olish
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
            if row:
                lang_code = row["language_code"]
    
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    if not await force_sub_if_private(update, context, lang_code):
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
    context.user_data["translated"] = prompt  # Keyinchalik tarjima qilish mumkin
    kb = [
        [InlineKeyboardButton("1️⃣", callback_data="count_1")],
        [InlineKeyboardButton("2️⃣", callback_data="count_2")],
        [InlineKeyboardButton("4️⃣", callback_data="count_4")],
        [InlineKeyboardButton("8️⃣", callback_data="count_8")]
    ]
    await update.message.reply_text(
        f"{lang['select_count']}\n🖌 Sizning matningiz:\n{escape_md(prompt)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# Private plain text -> prompt
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
        
    # Foydalanuvchi tilini olish
    lang_code = context.user_data.get("language", DEFAULT_LANGUAGE)
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    if not await force_sub_if_private(update, context, lang_code):
        return
        
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt  # Keyinchalik tarjima qilish mumkin
    kb = [
        [InlineKeyboardButton("1️⃣", callback_data="count_1")],
        [InlineKeyboardButton("2️⃣", callback_data="count_2")],
        [InlineKeyboardButton("4️⃣", callback_data="count_4")],
        [InlineKeyboardButton("8️⃣", callback_data="count_8")]
    ]
    await update.message.reply_text(
        f"{lang['select_count']}\n🖌 Sizning matningiz:\n{escape_md(prompt)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# GENERATE (robust)
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    # Tilni olish
    lang_code = context.user_data.get("language", DEFAULT_LANGUAGE)
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    try:
        count = int(q.data.split("_")[1])
    except Exception:
        try:
            await q.edit_message_text(lang["error"])
        except Exception:
            pass
        return

    user = q.from_user
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", prompt)

    # try edit message (ignore MessageNotModified)
    try:
        await q.edit_message_text(lang["generating"].format(count=count))
    except BadRequest:
        pass
    except Exception as e:
        logger.debug(f"[EDIT WARN] {e}")

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
                    await q.message.reply_text(lang["error"])
                    return

            logger.debug(f"[DIGEN DATA] {json.dumps(data)[:2000]}")

            # try multiple possible locations for id
            image_id = None
            if isinstance(data, dict):
                image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                logger.error("[DIGEN] image_id olinmadi")
                await q.message.reply_text(lang["error"])
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
                await q.edit_message_text(lang["success"])
            except BadRequest:
                pass

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        try:
            await q.edit_message_text(lang["error"])
        except Exception:
            pass

# ---------------- Donate (Stars) flow ----------------
async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Tilni olish
    lang_code = None
    if update.callback_query:
        lang_code = context.user_data.get("language", DEFAULT_LANGUAGE)
        await update.callback_query.answer()
    else:
        if update.effective_chat.type == "private":
            async with context.application.bot_data["db_pool"].acquire() as conn:
                row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
                if row:
                    lang_code = row["language_code"]
    
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE]) if lang_code else LANGUAGES[DEFAULT_LANGUAGE]
    
    if update.callback_query:
        await update.callback_query.message.reply_text(lang["donate_prompt"])
    else:
        await update.message.reply_text(lang["donate_prompt"])
    return WAITING_AMOUNT

async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Tilni olish
    lang_code = context.user_data.get("language", DEFAULT_LANGUAGE)
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text(lang["donate_invalid"])
        return WAITING_AMOUNT

    payload = f"donate_{update.effective_user.id}_{int(time.time())}"
    prices = [LabeledPrice(f"{amount} Stars", amount)]  # XTR da 1 Star = 1
    
    # provider_token empty for Stars (XTR)
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="💖 Bot Donation",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        provider_token="",  # for XTR leave empty
        currency="XTR",  # Stars uchun
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount  # XTR da 1 Star = 1
    user = update.effective_user
    
    # charge_id ni olish
    charge_id = payment.provider_payment_charge_id
    
    # Tilni olish
    lang_code = None
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE]) if lang_code else LANGUAGES[DEFAULT_LANGUAGE]
    
    await update.message.reply_text(lang["donate_thanks"].format(name=user.first_name, stars=amount_stars))

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload, charge_id) VALUES($1,$2,$3,$4,$5)",
            user.id, user.username if user.username else None, amount_stars, payment.invoice_payload, charge_id
        )

# ---------------- Refund handler (faqat admin uchun) ----------------
async def cmd_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Sizga ruxsat yo'q.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("UsageId: /refund <user_id> <donation_id>")
        return

    try:
        target_user_id = int(context.args[0])
        donation_id = int(context.args[1])
    except (ValueError, IndexError):
        await update.message.reply_text("UsageId: /refund <user_id> <donation_id>")
        return

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT charge_id, stars FROM donations WHERE id = $1 AND user_id = $2",
            donation_id, target_user_id
        )
        if not row:
            await update.message.reply_text("❌ Topilmadi yoki noto'g'ri ma'lumot.")
            return

        charge_id = row["charge_id"]
        stars = row["stars"]

        if not charge_id:
            await update.message.reply_text("❌ Bu to'lovda charge_id yo'q (eski to'lov).")
            return

        try:
            # Refund qilish (Stars uchun)
            await context.bot.refund_star_payment(
                user_id=target_user_id,
                telegram_payment_charge_id=charge_id
            )
            await update.message.reply_text(f"✅ {stars} Stars muvaffaqiyatli qaytarildi foydalanuvchi {target_user_id} ga.")

            # DBda refund qilinganini belgilash
            await conn.execute(
                "UPDATE donations SET refunded_at = NOW() WHERE id = $1",
                donation_id
            )

        except Exception as e:
            logger.exception(f"[REFUND ERROR] {e}")
            await update.message.reply_text(f"❌ Xatolik: {str(e)}")

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

    # START conversation handler
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)],
        states={
            LANGUAGE_SELECT: [CallbackQueryHandler(language_select_handler, pattern=r"lang_(uz|ru|en)")],
        },
        fallbacks=[CommandHandler("start", start_handler)]
    )
    app.add_handler(start_conv)

    # Basic handlers
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="check_sub"))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("refund", cmd_refund))  # Yangi refund handler

    # Donate conversation
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
