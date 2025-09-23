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

# Yangi import qo'shildi
from telegram.error import BadRequest, TelegramError

import asyncpg
import google.generativeai as genai
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
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image")
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if ADMIN_ID == 0:
    logger.error("ADMIN_ID muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY kiritilmagan. AI chat funksiyasi ishlamaydi.")

# ---------------- STATE ----------------
LANGUAGE_SELECT, WAITING_AMOUNT = range(2)

# ---------------- Til sozlamalari ----------------
# Yangilangan: Yangi matn kalitlari qo'shildi
LANGUAGES = {
    "uz": {
        "flag": "🇺🇿",
        "name": "O'zbekcha",
        "welcome": "👋 Salom!\n\nMen siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.",
        "gen_button": "🎨 Rasm yaratish",
        "ai_button": "💬 AI bilan suhbat",
        "donate_button": "💖 Donate",
        "lang_button": "🌐 Tilni o'zgartirish",
        "prompt_text": "✍️ Endi tasvir yaratish uchun matn yuboring.",
        "ai_prompt_text": "✍️ Suhbatni boshlash uchun savolingizni yozing.",
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
        "lang_changed": "✅ Til o'zgartirildi: {lang}",
        "select_lang": "🌐 Iltimos, tilni tanlang:",
        # Yangi: AI javob uchun oddiy matn
        "ai_response_header": "💬 AI javob:",
        # Yangi: Statistika matnlari
        "image_ready_header": "🎨 Rasm tayyor!",
        "image_prompt_label": "📝 Prompt:",
        "image_count_label": "🔢 Soni:",
        "image_time_label": "⏰ Vaqt (UTC+5):",
        "image_elapsed_label": "⏱ Yaratish uchun ketgan vaqt:",
        "choose_action": "Quyidagilardan birini tanlang:",
        "your_message": "💬 Sizning xabaringiz:",
        # Yangi: Admin xabari matnlari
        "admin_new_generation": "🎨 *Yangi generatsiya!*",
        "admin_user": "👤 *Foydalanuvchi:*",
        "admin_prompt": "📝 *Prompt:*",
        "admin_count": "🔢 *Soni:*",
        "admin_image_id": "🆔 *Image ID:*",
        "admin_time": "⏰ *Vaqt \\(UTC\\+5\\):*", # Markdown belgilari escape qilindi
    },
    "ru": {
        "flag": "🇷🇺",
        "name": "Русский",
        "welcome": "👋 Привет!\n\nЯ создаю для вас изображения с помощью ИИ.",
        "gen_button": "🎨 Создать изображение",
        "ai_button": "💬 AI bilan suhbat",
        "donate_button": "💖 Поддержать",
        "lang_button": "🌐 Изменить язык",
        "prompt_text": "✍️ Теперь отправьте текст для создания изображения.",
        "ai_prompt_text": "✍️ Suhbatni boshlash uchun savolingizni yozing.",
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
        "lang_changed": "✅ Язык изменен: {lang}",
        "select_lang": "🌐 Пожалуйста, выберите язык:",
        # Yangi: AI javob uchun oddiy matn
        "ai_response_header": "💬 Ответ AI:",
        # Yangi: Statistika matnlari
        "image_ready_header": "🎨 Rasm tayyor!",
        "image_prompt_label": "📝 Prompt:",
        "image_count_label": "🔢 Soni:",
        "image_time_label": "⏰ Vaqt (UTC+5):",
        "image_elapsed_label": "⏱ Yaratish uchun ketgan vaqt:",
        "choose_action": "Quyidagilardan birini tanlang:",
        "your_message": "💬 Sizning xabaringiz:",
        # Yangi: Admin xabari matnlari
        "admin_new_generation": "🎨 *Yangi generatsiya!*",
        "admin_user": "👤 *Foydalanuvchi:*",
        "admin_prompt": "📝 *Prompt:*",
        "admin_count": "🔢 *Soni:*",
        "admin_image_id": "🆔 *Image ID:*",
        "admin_time": "⏰ *Vaqt \\(UTC\\+5\\):*", # Markdown belgilari escape qilindi
    },
    "en": {
        "flag": "🇬🇧",
        "name": "English",
        "welcome": "👋 Hello!\n\nI create images for you using AI.",
        "gen_button": "🎨 Generate Image",
        "ai_button": "💬 AI bilan suhbat",
        "donate_button": "💖 Donate",
        "lang_button": "🌐 Change Language",
        "prompt_text": "✍️ Now send the text to generate an image.",
        "ai_prompt_text": "✍️ Suhbatni boshlash uchun savolingizni yozing.",
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
        "lang_changed": "✅ Language changed to: {lang}",
        "select_lang": "🌐 Please select language:",
        # Yangi: AI javob uchun oddiy matn
        "ai_response_header": "💬 AI Response:",
        # Yangi: Statistika matnlari
        "image_ready_header": "🎨 Rasm tayyor!",
        "image_prompt_label": "📝 Prompt:",
        "image_count_label": "🔢 Soni:",
        "image_time_label": "⏰ Vaqt (UTC+5):",
        "image_elapsed_label": "⏱ Yaratish uchun ketgan vaqt:",
        "choose_action": "Quyidagilardan birini tanlang:",
        "your_message": "💬 Sizning xabaringiz:",
        # Yangi: Admin xabari matnlari
        "admin_new_generation": "🎨 *Yangi generatsiya!*",
        "admin_user": "👤 *Foydalanuvchi:*",
        "admin_prompt": "📝 *Prompt:*",
        "admin_count": "🔢 *Soni:*",
        "admin_image_id": "🆔 *Image ID:*",
        "admin_time": "⏰ *Vaqt \\(UTC\\+5\\):*", # Markdown belgilari escape qilindi
    }
}

DEFAULT_LANGUAGE = "uz"

# ---------------- helpers ----------------
def escape_md(text: str) -> str:
    """
    Telegram MarkdownV2 uchun maxsus belgilarni escape qiladi.
    ! belgisini ham qo'shdik.
    """
    if not text:
        return ""
    # MarkdownV2 uchun escape qilinishi kerak bo'lgan belgilar, ! ham qo'shildi
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Har bir belgini oldidan \ qo'yamiz
    escaped = ''.join('\\' + char if char in escape_chars else char for char in text)
    return escaped

def utc_now():
    return datetime.now(timezone.utc)

def tashkent_time():
    return datetime.now(timezone.utc) + timedelta(hours=5)

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
        
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language_code TEXT DEFAULT 'uz'")
            logger.info("✅ Added column 'language_code' to table 'users'")
        except Exception as e:
            logger.info(f"ℹ️ Column 'language_code' already exists or error: {e}")
        
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
        "digen-language": "en-US",
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
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
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
            if lang_code:
                await conn.execute(
                    "UPDATE users SET username=$1, last_seen=$2, language_code=$3 WHERE id=$4",
                    tg_user.username if tg_user.username else None, now, lang_code, tg_user.id
                )
            else:
                await conn.execute(
                    "UPDATE users SET username=$1, last_seen=$2 WHERE id=$3",
                    tg_user.username if tg_user.username else None, now, tg_user.id
                )
        else:
            lang_code = lang_code or DEFAULT_LANGUAGE
            await conn.execute(
                "INSERT INTO users(id, username, first_seen, last_seen, language_code) VALUES($1,$2,$3,$4,$5)",
                tg_user.id, tg_user.username if tg_user.username else None, now, now, lang_code
            )
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

# ---------------- Admin ga xabar yuborish (YANGILANGAN) ----------------
# Endi barcha rasmlarni yuboradi va tarjima qiladi
async def notify_admin_generation(context: ContextTypes.DEFAULT_TYPE, user, prompt, image_urls, count, image_id):
    """
    Foydalanuvchi rasm generatsiya qilganda, barcha rasmlarni admin foydalanuvchisiga yuboradi.
    """
    if not ADMIN_ID:
        return # Agar ADMIN_ID o'rnatilmagan bo'lsa, hech narsa yuborilmaydi

    try:
        # Foydalanuvchi tilini olish (agar kerak bo'lsa)
        lang_code = DEFAULT_LANGUAGE
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", ADMIN_ID)
            if row:
                lang_code = row["language_code"]
        lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

        tashkent_dt = tashkent_time()
        # Admin xabari uchun matn (statistika) - Tarjima qilingan matnlardan foydalanilmoqda
        caption_text = (
            f"{lang['admin_new_generation']}\n\n"
            f"{lang['admin_user']} @{user.username if user.username else 'N/A'} (ID: {user.id})\n"
            f"{lang['admin_prompt']} {escape_md(prompt)}\n"
            f"{lang['admin_count']} {count}\n"
            f"{lang['admin_image_id']} `{image_id}`\n" # Image ID ni ham qo'shamiz
            f"{lang['admin_time']} {tashkent_dt.strftime('%Y-%m-%d %H:%M:%S')}" # Markdown belgilari escape qilindi
        )
        
        # 1. Avval statistikani yuboramiz (1-rasmga biriktiriladi)
        if image_urls:
            first_image_url = image_urls[0]
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=first_image_url,
                caption=caption_text,
                parse_mode="MarkdownV2"
            )
            logger.info(f"[ADMIN NOTIFY] Foydalanuvchi {user.id} uchun generatsiya admin ga yuborildi (1-rasm va statistika).")

            # 2. Qolgan rasmlarni alohida yuboramiz
            for i, url in enumerate(image_urls[1:], start=2): # 2-rasmdan boshlab
                 try:
                     await context.bot.send_photo(chat_id=ADMIN_ID, photo=url)
                     logger.info(f"[ADMIN NOTIFY] Foydalanuvchi {user.id} uchun {i}-rasm admin ga yuborildi.")
                 except Exception as e:
                     logger.error(f"[ADMIN NOTIFY ERROR] Foydalanuvchi {user.id} uchun {i}-rasm yuborishda xato: {e}")

        else:
            # Agar rasm URL lari bo'lmasa, faqat matnni yuboramiz
            await context.bot.send_message(chat_id=ADMIN_ID, text=caption_text, parse_mode="MarkdownV2")
            logger.info(f"[ADMIN NOTIFY] Foydalanuvchi {user.id} uchun generatsiya admin ga yuborildi (faqat matn).")

    except Exception as e:
        logger.exception(f"[ADMIN NOTIFY ERROR] Umumiy xato: {e}")


# ---------------- Tilni o'zgartirish handleri ----------------
async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton(f"{LANGUAGES['uz']['flag']} {LANGUAGES['uz']['name']}", callback_data="lang_uz")],
        [InlineKeyboardButton(f"{LANGUAGES['ru']['flag']} {LANGUAGES['ru']['name']}", callback_data="lang_ru")],
        [InlineKeyboardButton(f"{LANGUAGES['en']['flag']} {LANGUAGES['en']['name']}", callback_data="lang_en")],
    ]
    lang_code = DEFAULT_LANGUAGE
    if update.effective_chat.type == "private":
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
            if row:
                lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(lang["select_lang"], reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(lang["select_lang"], reply_markup=InlineKeyboardMarkup(kb))
    return LANGUAGE_SELECT

async def language_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = q.data.split("_")[1]
    user = q.from_user
    
    await add_user_db(context.application.bot_data["db_pool"], user, lang_code)
    
    lang = LANGUAGES[lang_code]
    kb = [
        [InlineKeyboardButton(lang["gen_button"], callback_data="start_gen")],
        [InlineKeyboardButton(lang["ai_button"], callback_data="start_ai_flow")], # Yangi tugma, tarjima qilingan
        [InlineKeyboardButton(lang["donate_button"], callback_data="donate_custom")],
        [InlineKeyboardButton(lang["lang_button"], callback_data="change_language")]
    ]
    await q.edit_message_text(lang["lang_changed"].format(lang=lang["name"]), reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ---------------- START handleri ----------------
# Yangilangan: Yangi AI chat tugmasi qo'shildi
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang_code = None
    
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

    # Mavjud barcha tugmalar + yangi AI chat tugmasi
    kb = [
        [InlineKeyboardButton(lang["gen_button"], callback_data="start_gen")],
        [InlineKeyboardButton(lang["ai_button"], callback_data="start_ai_flow")], # Yangi tugma, tarjima qilingan
        [InlineKeyboardButton(lang["donate_button"], callback_data="donate_custom")],
        [InlineKeyboardButton(lang["lang_button"], callback_data="change_language")]
    ]
    await update.message.reply_text(lang["welcome"], reply_markup=InlineKeyboardMarkup(kb))

# ---------------- Bosh menyudan AI chat ----------------
async def start_ai_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    # await q.message.reply_text("✍️ Suhbatni boshlash uchun savolingizni yozing.")
    await q.message.reply_text(lang["ai_prompt_text"]) # Yangilangan, tarjima qilingan
    # AI chat flow boshlanadi
    context.user_data["flow"] = "ai"
    # Oxirgi faollik vaqtini saqlaymiz
    context.user_data["last_active"] = datetime.now(timezone.utc)

# ---------------- Bosh menyudan rasm generatsiya ----------------
async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    await q.message.reply_text(lang["prompt_text"])
    # flow o'zgaruvchisini o'rnatamiz
    context.user_data["flow"] = "image_pending_prompt"

# ---------------- Bosh menyuga qaytish tugmasi ----------------
async def handle_change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_language(update, context)

# /get command
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_code = DEFAULT_LANGUAGE
    if update.effective_chat.type == "private":
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
    context.user_data["translated"] = prompt
    kb = [
        [InlineKeyboardButton("1️⃣", callback_data="count_1")],
        [InlineKeyboardButton("2️⃣", callback_data="count_2")],
        [InlineKeyboardButton("4️⃣", callback_data="count_4")],
        [InlineKeyboardButton("8️⃣", callback_data="count_8")]
    ]
    await update.message.reply_text(
        f"{lang['select_count']}\n🖌 Sizning matningiz:\n{escape_md(prompt)}",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# Private plain text -> prompt + inline buttons yoki AI chat
# Yangilangan: Tanlov tugmachasi bosilganda flow o'rnatiladi

    except Exception as gemini_err:
        logger.error(f"[GEMINI PROMPT ERROR] Gemini API dan foydalanganda xato: {gemini_err}")
        # Xatolik yuz bersa ham, original promptni Digen ga yuboramiz
        context.user_data["translated"] = original_prompt
    # --- Yangi tugadi ---

    # Agar hech qanday flow boshlanmagan bo'lsa (faqat oddiy matn)
    if flow is None: 
        kb = [
            [
                InlineKeyboardButton("🖼 Rasm yaratish", callback_data="gen_image_from_prompt"),
                InlineKeyboardButton("💬 AI bilan suhbat", callback_data="ai_chat_from_prompt")
            ]
        ]
        # await update.message.reply_text(
        #     f"Quyidagilardan birini tanlang:\n\n💬 *Sizning xabaringiz:* {escape_md(prompt)}",
        #     parse_mode="MarkdownV2",
        #     reply_markup=InlineKeyboardMarkup(kb)
        # )
        # Yangilangan qatorlar, tarjima qilingan
        

# ---------------- Tanlov tugmachasi orqali rasm generatsiya ----------------
# Yangilangan: context.user_data["flow"] o'rnatiladi
async def gen_image_from_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    # flow o'zgaruvchisini o'rnatamiz
    context.user_data["flow"] = "image_pending_prompt"
    
    # To'g'ridan-to'g'ri 1 ta rasm generatsiya qilamiz
    fake_update = Update(0, message=q.message)
    fake_update.callback_query = q
    fake_update.callback_query.data = "count_1"
    await generate_cb(fake_update, context)

# ---------------- Tanlov tugmachasi orqali AI chat -
---------------
# ---------------- Private plain text -> prompt + inline buttons yoki AI chat ----------------
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
        
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    # Flow tekshirish
    flow = context.user_data.get("flow")
    now = datetime.now(timezone.utc)

    if flow == "ai":
        last_active = context.user_data.get("last_active")
        if last_active and (now - last_active).total_seconds() <= 900:
            prompt = update.message.text
            await update.message.reply_text("🧠 AI javob berayotganicha kuting...")

            try:
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = await model.generate_content_async(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=1000,
                        temperature=0.7
                    )
                )
                answer = response.text.strip()
                if not answer:
                    answer = "⚠️ Javob topilmadi."
            except Exception as e:
                logger.exception("[GEMINI ERROR]")
                answer = lang["error"]

            # Barcha * belgilarni olib tashlash
            import re
            clean_answer = re.sub(r"[*_~`]", "", answer)

            await update.message.reply_text(f"{lang['ai_response_header']}\n\n{clean_answer}")

            # Oxirgi faollik vaqtini yangilash
            context.user_data["last_active"] = now
            return
        else:
            # Flowni bekor qilamiz
            context.user_data["flow"] = None
            context.user_data["last_active"] = None

    # Agar hech qanday flow bo‘lmasa, oddiy rasm generatsiya jarayoni
    if not await force_sub_if_private(update, context, lang_code):
        return
        
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt

    # --- Gemini orqali Digen uchun tayyorlash ---
    original_prompt = prompt
    gemini_instruction = "Auto detect this language and translate this text to English for image generation. No other text, just the translated prompt:"
    gemini_full_prompt = f"{gemini_instruction}\n{original_prompt}"

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        gemini_response = await model.generate_content_async(
            gemini_full_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=100,
                temperature=0.5
            )
        )
        digen_ready_prompt = gemini_response.text.strip()
        if not digen_ready_prompt:
            digen_ready_prompt = original_prompt
        context.user_data["translated"] = digen_ready_prompt
    except Exception as gemini_err:
        logger.error(f"[GEMINI PROMPT ERROR] {gemini_err}")
        context.user_data["translated"] = original_prompt

    # Inline tugmalar
    kb = [
        [
            InlineKeyboardButton("🖼 Rasm yaratish", callback_data="gen_image_from_prompt"),
            InlineKeyboardButton("💬 AI bilan suhbat", callback_data="ai_chat_from_prompt")
        ]
    ]
    await update.message.reply_text(
        f"{lang['choose_action']}\n\n*{lang['your_message']}* {escape_md(prompt)}",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
        )
# Yangilangan: context.user_data["flow"] o'rnatiladi
async def ai_chat_from_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    # AI chat flow boshlanadi
    context.user_data["flow"] = "ai"
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    # await q.message.reply_text("✍️ Suhbatni boshlash uchun savolingizni yozing.")
    await q.message.reply_text(lang["ai_prompt_text"]) # Yangilangan, tarjima qilingan

# GENERATE (robust) - Yangilangan versiya (Prompt - Gemini - Digen)
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
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
    # --- Yangi: Tarjima qilingan promptni olish ---
    # Agar private_text_handler da tarjima qilinmagan bo'lsa, bu yerda ham tarjima qilish mumkin edi,
    # lekin endi u private_text_handler da qilingani uchun bu yerda faqat olinadi.
    translated = context.user_data.get("translated", prompt) # Digen uchun tayyor prompt
    # --- Yangi tugadi ---

    start_time = time.time() # Vaqtni boshlash

    # Yangi: Oddiy progress bar (soxta)
    async def update_progress(percent):
        bar_length = 10
        filled_length = int(bar_length * percent // 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        try:
            # Eski xabarni yangilash uchun Markdown ishlatmaymiz
            await q.edit_message_text(f"🔄 Rasm yaratilmoqda... {bar} {percent}%")
        except Exception:
            pass # Xatolikni e'tiborsiz qoldirish mumkin

    # Dastlabki progress
    await update_progress(10)

    # --- Yangi: payload da tarjima qilingan promptdan foydalanamiz ---
    payload = {
        "prompt": translated, # Yangilangan qator
        "image_size": "512x512",
        "width": 512,
        "height": 512,
        "lora_id": "",
        "batch_size": count,
        "reference_images": [],
        "strength": ""
    }
    # --- Yangi tugadi ---

    headers = get_digen_headers()
    sess_timeout = aiohttp.ClientTimeout(total=180)
    try:
        # Progressni yangilash (soxta)
        await asyncio.sleep(0.5)
        await update_progress(30)
        
        async with aiohttp.ClientSession(timeout=sess_timeout) as session:
            # Progressni yangilash (soxta)
            await asyncio.sleep(0.5)
            await update_progress(50)
            
            async with session.post(DIGEN_URL, headers=headers, json=payload) as resp:
                # Progressni yangilash (soxta)
                await asyncio.sleep(0.5)
                await update_progress(70)
                
                text_resp = await resp.text()
                logger.info(f"[DIGEN] status={resp.status}")
                try:
                    data = await resp.json()
                except Exception:
                    logger.error(f"[DIGEN PARSE ERROR] status={resp.status} text={text_resp}")
                    await q.message.reply_text(lang["error"])
                    return

            logger.debug(f"[DIGEN DATA] {json.dumps(data)[:2000]}")

            image_id = None
            if isinstance(data, dict):
                image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                logger.error("[DIGEN] image_id olinmadi")
                await q.message.reply_text(lang["error"])
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
            logger.info(f"[GENERATE] urls: {urls}")

            available = False
            max_wait = 60
            waited = 0
            interval = 1.5
            while waited < max_wait:
                # Progressni yangilash (soxta)
                progress_percent = min(90, 70 + int((waited / max_wait) * 20))
                await update_progress(progress_percent)
                
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

            # 100% progress
            await update_progress(100)
            
            end_time = time.time()
            elapsed_time = end_time - start_time

            # Yangi: Statistika bilan rasm(lar)ni yuborish (Oddiy matn sifatida)
            # escape_md dan foydalanib, maxsus belgilarni to'g'ri qo'yamiz
            escaped_prompt = escape_md(prompt) # Original promptni log qilamiz
            
            # Statistikani oddiy matn sifatida yaratamiz, hech qanday parse_mode ishlatmaymiz
            # Tarjimalar to'g'rilangan
            # stats_text = (
            #     f"🎨 Rasm tayyor!\n\n" 
            #     f"📝 Prompt: {escaped_prompt}\n" # escape_md qilingan prompt
            #     f"🔢 Soni: {count}\n"
            #     f"⏰ Vaqt (UTC+5): {tashkent_time().strftime('%Y-%m-%d %H:%M:%S')}\n"
            #     f"⏱ Yaratish uchun ketgan vaqt: {elapsed_time:.1f}s"
            # )
            # Yangilangan qatorlar, tarjima qilingan
            stats_text = (
                f"{lang['image_ready_header']}\n\n"
                f"{lang['image_prompt_label']} {escaped_prompt}\n"
                f"{lang['image_count_label']} {count}\n"
                f"{lang['image_time_label']} {tashkent_time().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{lang['image_elapsed_label']} {elapsed_time:.1f}s"
            )

            try:
                # Birinchi rasmga statistika, qolganlariga yo'q. parse_mode ishlatmaymiz.
                media = [InputMediaPhoto(u, caption=stats_text if i == 0 else None) for i, u in enumerate(urls)]
                await q.message.reply_media_group(media)
            except TelegramError as e:
                logger.exception(f"[MEDIA_GROUP ERROR] {e}; fallback to single photos")
                # Agar MediaGroup ishlamasa, birinchi rasmga statistika bilan, qolganlariga yo'q holda yuboramiz
                try:
                    await q.message.reply_photo(urls[0], caption=stats_text) # parse_mode ishlatmaymiz
                    for u in urls[1:]:
                        try:
                            await q.message.reply_photo(u)
                        except Exception as ex:
                            logger.exception(f"[SINGLE SEND ERR] {ex}")
                except Exception as e2:
                    logger.exception(f"[FALLBACK PHOTO ERROR] {e2}")
                    # Agar bu ham ishlamasa, oddiy matn sifatida xabar beramiz
                    await q.message.reply_text(lang["success"])

            # --- Yangi: Admin xabarnomasi (barcha rasmlar bilan) ---
            # log_generation uchun ham kerakli o'zgaruvchilarni saqlaymiz
            digen_prompt_for_logging = translated # Log uchun saqlaymiz
            if ADMIN_ID and urls:
                 # notify_admin_generation ga urls (barcha rasmlar ro'yxati) uzatiladi
                 await notify_admin_generation(context, user, prompt, urls, count, image_id)
            # --- Yangi tugadi ---

            # --- Yangi: log_generation ga to'g'ri translated_prompt uzatiladi ---
            await log_generation(context.application.bot_data["db_pool"], user, prompt, digen_prompt_for_logging, image_id, count)
            # --- Yangi tugadi ---

            # Oxirgi progress xabarini muvaffaqiyatli natija bilan almashtirish
            try:
                await q.edit_message_text("✅ Tayyor!")
            except BadRequest:
                pass

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        try:
            await q.edit_message_text(lang["error"])
        except Exception:
            pass


# ---------------- Donate (Stars) flow ----------------
# Yangilangan: ConversationHandler bilan boshqariladi
async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_code = DEFAULT_LANGUAGE
    if update.callback_query:
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.callback_query.from_user.id)
            if row:
                lang_code = row["language_code"]
        await update.callback_query.answer()
    else:
        if update.effective_chat.type == "private":
            async with context.application.bot_data["db_pool"].acquire() as conn:
                row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
                if row:
                    lang_code = row["language_code"]
    
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    if update.callback_query:
        await update.callback_query.message.reply_text(lang["donate_prompt"])
    else:
        await update.message.reply_text(lang["donate_prompt"])
    return WAITING_AMOUNT

# Yangilangan: ConversationHandler bilan boshqariladi
async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text(lang["donate_invalid"])
        return WAITING_AMOUNT # ConversationHandler WAITING_AMOUNT holatida qoladi

    payload = f"donate_{update.effective_user.id}_{int(time.time())}"
    prices = [LabeledPrice(f"{amount} Stars", amount)]
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title="💖 Bot Donation",
        description="Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END # ConversationHandler tugaydi

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount
    user = update.effective_user
    
    charge_id = payment.provider_payment_charge_id
    
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user.id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    
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
            await context.bot.refund_star_payment(
                user_id=target_user_id,
                telegram_payment_charge_id=charge_id
            )
            await update.message.reply_text(f"✅ {stars} Stars muvaffaqiyatli qaytarildi foydalanuvchi {target_user_id} ga.")

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

    # ConversationHandler larda per_message=False qilish
    # Bu ogohlantirishlarni oldini oladi
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)], # CommandHandler
        states={
            LANGUAGE_SELECT: [CallbackQueryHandler(language_select_handler, pattern=r"lang_(uz|ru|en)")],
        },
        fallbacks=[CommandHandler("start", start_handler)], # CommandHandler
        per_message=False # O'zgardi
    )
    app.add_handler(start_conv)

    lang_conv = ConversationHandler(
        entry_points=[
            CommandHandler("language", cmd_language), # CommandHandler
            CallbackQueryHandler(cmd_language, pattern="change_language")
        ],
        states={
            LANGUAGE_SELECT: [CallbackQueryHandler(language_select_handler, pattern=r"lang_(uz|ru|en)")],
        },
        fallbacks=[CommandHandler("language", cmd_language)], # CommandHandler
        per_message=False # O'zgardi
    )
    app.add_handler(lang_conv)

    donate_conv = ConversationHandler(
        entry_points=[CommandHandler("donate", donate_start), CallbackQueryHandler(donate_start, pattern="donate_custom")],
        states={WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[],
        per_message=False # O'zgardi
    )
    app.add_handler(donate_conv)

    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="check_sub"))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("refund", cmd_refund))

    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))
    # Yangi handlerlar
    app.add_handler(CallbackQueryHandler(start_ai_flow_handler, pattern="start_ai_flow"))
    app.add_handler(CallbackQueryHandler(gen_image_from_prompt_handler, pattern="gen_image_from_prompt"))
    app.add_handler(CallbackQueryHandler(ai_chat_from_prompt_handler, pattern="ai_chat_from_prompt"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))

    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
