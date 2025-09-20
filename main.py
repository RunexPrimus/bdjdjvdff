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
from datetime import datetime, timezone, date

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
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image  ")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)

# ---------------- Tarjimalar ----------------
TRANSLATIONS = {
    "uz_latin": {
        "choose_lang": "Iltimos, tilni tanlang:",
        "lang_uz_latin": "🇺🇿 O'zbek (Lotin)",
        "lang_uz_cyrillic": "🇺🇿 Ўзбек (Кирилл)",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",
        "start_text": "👋 Salom!\n\nMen siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\nPrivatda matn yuboring yoki guruhda /get bilan ishlating.",
        "gen_button": "🎨 Rasm yaratish",
        "donate_button": "💖 Donate",
        "prompt_request": "✍️ Endi tasvir yaratish uchun matn yuboring (privatda).",
        "group_prompt_missing": "❌ Guruhda /get dan keyin prompt yozing. Misol: /get futuristik shahar",
        "private_prompt_missing": "✍️ Iltimos, rasm uchun matn yozing (yoki oddiy matn yuboring).",
        "your_prompt": "🖌 Sizning matningiz:\n{}\n\n🔢 Nechta rasm yaratilsin?",
        "invalid_button": "❌ Noto'g'ri tugma.",
        "generating": "🔄 Rasm yaratilmoqda ({})... ⏳",
        "image_ready": "✅ Rasm tayyor! 📸",
        "error_occurred": "⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.",
        "api_error": "❌ API dan noma'lum javob keldi. Adminga murojaat qiling.",
        "no_image_id": "❌ Rasm ID olinmadi (API javobi).",
        "image_delayed": "⚠️ Rasmni tayyorlash biroz vaqt olmoqda. Keyinroq urinib ko'ring.",
        "change_language": "🌐 Tilni o'zgartirish",
        "daily_limit_exceeded": "🚫 Kunlik limit (5 ta) tugadi. 5 Stars to'lab, rasm yaratishingiz mumkin.",
        "pay_for_generation": "💳 5 Stars to'lash orqali rasm yaratish",
        "thank_you_donation": "✅ Rahmat, {}! Siz {} Stars yubordingiz.",
        "subscription_required": "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
        "subscribe_button": "🔗 Kanalga obuna bo‘lish",
        "check_subscription": "✅ Obunani tekshirish",
        "subscription_confirmed": "✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.",
        "subscription_not_confirmed": "⛔ Hali ham obuna bo‘lmagansiz. Obuna bo‘lib, qayta tekshiring.",
        "donate_prompt": "💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):",
        "donate_invalid_amount": "❌ Iltimos, 1–100000 oralig‘ida butun son kiriting.",
        "donate_title": "💖 Bot Donation",
        "donate_description": "Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        "lang_changed": "✅ Til o'zgartirildi!",
        "payment_processing": "✅ To'lov qabul qilindi! Rasm yaratilmoqda...",
    },
    "uz_cyrillic": {
        "choose_lang": "Илтимос, тилни танланг:",
        "lang_uz_latin": "🇺🇿 O'zbek (Lotin)",
        "lang_uz_cyrillic": "🇺🇿 Ўзбек (Кирилл)",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",
        "start_text": "👋 Салом!\n\nМен сиз учун сунъий интеллект ёрдамида расмлар яратиб бераман.\nПриватда матн юборинг ёки гуруҳда /get билан ишлаштиринг.",
        "gen_button": "🎨 Расм яратиш",
        "donate_button": "💖 Донат",
        "prompt_request": "✍️ Энди тасвир яратиш учун матн юборинг (приватда).",
        "group_prompt_missing": "❌ Гуруҳда /get дан кейин промпт ёзинг. Мисол: /get футуристик шаҳар",
        "private_prompt_missing": "✍️ Илтимос, расм учун матн ёзинг (ёки оддий матн юборинг).",
        "your_prompt": "🖌 Сизнинг матнингиз:\n{}\n\n🔢 Нечта расм яратилсин?",
        "invalid_button": "❌ Нотўғри тугма.",
        "generating": "🔄 Расм яратилмоқда ({})... ⏳",
        "image_ready": "✅ Расм тайёр! 📸",
        "error_occurred": "⚠️ Хатолик юз берди. Қайта уриниб кўринг.",
        "api_error": "❌ API дан номаълум жавоб келди. Админга мурожаат қилинг.",
        "no_image_id": "❌ Расм ID олинмади (API жавоби).",
        "image_delayed": "⚠️ Расмни тайёрлаш бироз вакт олмоқда. Кейинрок уриниб кўринг.",
        "change_language": "🌐 Тилни ўзгартириш",
        "daily_limit_exceeded": "🚫 Кунлик лимит (5 та) тугади. 5 Stars тўлаб, расм яратишингиз мумкин.",
        "pay_for_generation": "💳 5 Stars тўлаш орқали расм яратиш",
        "thank_you_donation": "✅ Раҳмат, {}! Сиз {} Stars юбордингиз.",
        "subscription_required": "⛔ Ботдан фойдаланиш учун каналга обуна бўлинг!",
        "subscribe_button": "🔗 Каналга обуна бўлиш",
        "check_subscription": "✅ Обунани текшириш",
        "subscription_confirmed": "✅ Раҳмат! Сиз обуна бўлгансиз. Энди ботдан фойдаланишингиз мумкин.",
        "subscription_not_confirmed": "⛔ Ҳали ҳам обуна бўлмагансиз. Обуна бўлиб, қайта текширинг.",
        "donate_prompt": "💰 Илтимос, юбормоқчи бўлган миқдорни киритинг (1–100000):",
        "donate_invalid_amount": "❌ Илтимос, 1–100000 оралиғида бутун сон киритинг.",
        "donate_title": "💖 Ботга донация",
        "donate_description": "Ботни қўллаб-қувватлаш учун иҳтиёрий сумма юборинг.",
        "lang_changed": "✅ Тил ўзгартирилди!",
        "payment_processing": "✅ Тўлов қабул қилинди! Расм яратилмоқда...",
    },
    "ru": {
        "choose_lang": "Пожалуйста, выберите язык:",
        "lang_uz_latin": "🇺🇿 O'zbek (Lotin)",
        "lang_uz_cyrillic": "🇺🇿 Ўзбек (Кирилл)",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",
        "start_text": "👋 Привет!\n\nЯ создаю для вас изображения с помощью ИИ.\nОтправьте текст в личку или используйте /get в группе.",
        "gen_button": "🎨 Создать изображение",
        "donate_button": "💖 Пожертвовать",
        "prompt_request": "✍️ Теперь отправьте текст для создания изображения (в личку).",
        "group_prompt_missing": "❌ В группе после /get укажите запрос. Пример: /get футуристический город",
        "private_prompt_missing": "✍️ Пожалуйста, введите текст для изображения (или просто отправьте текст).",
        "your_prompt": "🖌 Ваш текст:\n{}\n\n🔢 Сколько изображений создать?",
        "invalid_button": "❌ Неправильная кнопка.",
        "generating": "🔄 Создаю изображение ({})... ⏳",
        "image_ready": "✅ Изображение готово! 📸",
        "error_occurred": "⚠️ Произошла ошибка. Попробуйте снова.",
        "api_error": "❌ Неизвестный ответ от API. Обратитесь к администратору.",
        "no_image_id": "❌ Не удалось получить ID изображения (ответ API).",
        "image_delayed": "⚠️ Подготовка изображения занимает время. Попробуйте позже.",
        "change_language": "🌐 Сменить язык",
        "daily_limit_exceeded": "🚫 Дневной лимит (5 шт.) исчерпан. Оплатите 5 Stars, чтобы создать изображение.",
        "pay_for_generation": "💳 Создать изображение за 5 Stars",
        "thank_you_donation": "✅ Спасибо, {}! Вы отправили {} Stars.",
        "subscription_required": "⛔ Подпишитесь на наш канал, чтобы пользоваться ботом!",
        "subscribe_button": "🔗 Подписаться на канал",
        "check_subscription": "✅ Проверить подписку",
        "subscription_confirmed": "✅ Спасибо! Вы подписаны. Теперь можете пользоваться ботом.",
        "subscription_not_confirmed": "⛔ Вы еще не подписаны. Подпишитесь и проверьте снова.",
        "donate_prompt": "💰 Пожалуйста, введите сумму для отправки (1–100000):",
        "donate_invalid_amount": "❌ Пожалуйста, введите целое число от 1 до 100000.",
        "donate_title": "💖 Поддержка бота",
        "donate_description": "Поддержите бота, отправив любую сумму.",
        "lang_changed": "✅ Язык изменен!",
        "payment_processing": "✅ Оплата принята! Создаю изображение...",
    },
    "en": {
        "choose_lang": "Please choose your language:",
        "lang_uz_latin": "🇺🇿 O'zbek (Lotin)",
        "lang_uz_cyrillic": "🇺🇿 Ўзбек (Кирилл)",
        "lang_ru": "🇷🇺 Русский",
        "lang_en": "🇬🇧 English",
        "start_text": "👋 Hello!\n\nI create images for you using AI.\nSend text in private or use /get in groups.",
        "gen_button": "🎨 Generate Image",
        "donate_button": "💖 Donate",
        "prompt_request": "✍️ Now send the text to generate an image (in private).",
        "group_prompt_missing": "❌ In groups, write prompt after /get. Example: /get futuristic city",
        "private_prompt_missing": "✍️ Please enter text for the image (or just send text).",
        "your_prompt": "🖌 Your prompt:\n{}\n\n🔢 How many images to generate?",
        "invalid_button": "❌ Invalid button.",
        "generating": "🔄 Generating image ({})... ⏳",
        "image_ready": "✅ Image ready! 📸",
        "error_occurred": "⚠️ An error occurred. Please try again.",
        "api_error": "❌ Unknown response from API. Contact admin.",
        "no_image_id": "❌ Failed to get image ID (API response).",
        "image_delayed": "⚠️ Image preparation is taking time. Please try again later.",
        "change_language": "🌐 Change Language",
        "daily_limit_exceeded": "🚫 Daily limit (5) exceeded. Pay 5 Stars to generate image.",
        "pay_for_generation": "💳 Generate image for 5 Stars",
        "thank_you_donation": "✅ Thank you, {}! You sent {} Stars.",
        "subscription_required": "⛔ Subscribe to our channel to use the bot!",
        "subscribe_button": "🔗 Subscribe to channel",
        "check_subscription": "✅ Check subscription",
        "subscription_confirmed": "✅ Thank you! You are subscribed. You can now use the bot.",
        "subscription_not_confirmed": "⛔ You are not subscribed yet. Subscribe and check again.",
        "donate_prompt": "💰 Please enter the amount you wish to send (1–100000):",
        "donate_invalid_amount": "❌ Please enter a whole number between 1 and 100000.",
        "donate_title": "💖 Bot Donation",
        "donate_description": "Support the bot by sending any amount.",
        "lang_changed": "✅ Language changed!",
        "payment_processing": "✅ Payment received! Generating image...",
    }
}

def t(key: str, lang: str = "uz_latin") -> str:
    """Tarjima qilish funksiyasi"""
    return TRANSLATIONS.get(lang, TRANSLATIONS["uz_latin"]).get(key, f"[{key}]")

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
    language TEXT DEFAULT 'uz_latin'
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

CREATE TABLE IF NOT EXISTS daily_limits (
    user_id BIGINT PRIMARY KEY,
    date DATE,
    count INT DEFAULT 0
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
        "origin": "https://rm.digen.ai  ",
        "referer": "https://rm.digen.ai/  ",
    }

# ---------------- subscription check (optional) ----------------
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
        lang = context.user_data.get("lang", "uz_latin")
        kb = [
            [InlineKeyboardButton(t("subscribe_button", lang), url=f"https://t.me/  {CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(t("check_subscription", lang), callback_data="check_sub")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(t("subscription_required", lang), reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(t("subscription_required", lang), reply_markup=InlineKeyboardMarkup(kb))
        return False
    return True

async def check_sub_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    lang = context.user_data.get("lang", "uz_latin")
    if await check_subscription(user_id, context):
        await q.edit_message_text(t("subscription_confirmed", lang))
    else:
        kb = [
            [InlineKeyboardButton(t("subscribe_button", lang), url=f"https://t.me/  {CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(t("check_subscription", lang), callback_data="check_sub")]
        ]
        await q.edit_message_text(t("subscription_not_confirmed", lang), reply_markup=InlineKeyboardMarkup(kb))

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

# ---------------- Language handlers ----------------
async def change_language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    kb = [
        [InlineKeyboardButton(t("lang_uz_latin", "uz_latin"), callback_data="set_lang_uz_latin")],
        [InlineKeyboardButton(t("lang_uz_cyrillic", "uz_cyrillic"), callback_data="set_lang_uz_cyrillic")],
        [InlineKeyboardButton(t("lang_ru", "ru"), callback_data="set_lang_ru")],
        [InlineKeyboardButton(t("lang_en", "en"), callback_data="set_lang_en")],
    ]
    lang = context.user_data.get("lang", "uz_latin")
    text = t("choose_lang", lang)
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def set_language_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = q.data.split("_")[2]
    user_id = q.from_user.id

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET language = $1 WHERE id = $2", lang_code, user_id)

    context.user_data["lang"] = lang_code
    await q.edit_message_text(t("lang_changed", lang_code))
    kb = get_main_keyboard(lang_code)
    await q.message.reply_text(t("start_text", lang_code), parse_mode="Markdown", reply_markup=kb)

def get_main_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("gen_button", lang), callback_data="start_gen")],
        [InlineKeyboardButton(t("donate_button", lang), callback_data="donate_custom")],
        [InlineKeyboardButton(t("change_language", lang), callback_data="change_lang")]
    ])

# ---------------- Daily limit ----------------
async def check_daily_limit(user_id: int, pool) -> bool:
    today = date.today()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT count FROM daily_limits WHERE user_id = $1 AND date = $2",
            user_id, today
        )
        if not row:
            await conn.execute(
                "INSERT INTO daily_limits(user_id, date, count) VALUES($1, $2, $3)",
                user_id, today, 0
            )
            return True
        return row["count"] < 5

async def increment_daily_limit(user_id: int, pool):
    today = date.today()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE daily_limits SET count = count + 1 WHERE user_id = $1 AND date = $2",
            user_id, today
        )

# ---------------- Handlers ----------------

# START
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return

    user = update.effective_user
    pool = context.application.bot_data["db_pool"]
    await add_user_db(pool, user)

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT language FROM users WHERE id = $1", user.id)
        lang = row["language"] if row and row["language"] else None

    if not lang:
        await change_language_handler(update, context)
        return

    context.user_data["lang"] = lang
    kb = get_main_keyboard(lang)
    await update.message.reply_text(t("start_text", lang), parse_mode="Markdown", reply_markup=kb)

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    lang = context.user_data.get("lang", "uz_latin")
    await update.callback_query.message.reply_text(t("prompt_request", lang))

# /get command
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_sub_if_private(update, context):
        return
    chat_type = update.effective_chat.type
    lang = context.user_data.get("lang", "uz_latin")
    if chat_type in ("group", "supergroup"):
        if not context.args:
            await update.message.reply_text(t("group_prompt_missing", lang))
            return
        prompt = " ".join(context.args)
    else:
        if not context.args:
            await update.message.reply_text(t("private_prompt_missing", lang))
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
        t("your_prompt", lang).format(escape_md(prompt)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# Private plain text -> prompt
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if not await force_sub_if_private(update, context):
        return
    lang = context.user_data.get("lang", "uz_latin")
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
        t("your_prompt", lang).format(escape_md(prompt)),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# GENERATE (robust)
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        count = int(q.data.split("_")[1])
    except Exception:
        lang = context.user_data.get("lang", "uz_latin")
        try:
            await q.edit_message_text(t("invalid_button", lang))
        except Exception:
            pass
        return

    user = q.from_user
    pool = context.application.bot_data["db_pool"]
    lang = context.user_data.get("lang", "uz_latin")

    # Kunlik limitni tekshirish
    within_limit = await check_daily_limit(user.id, pool)
    if not within_limit:
        kb = [[InlineKeyboardButton(t("pay_for_generation", lang), callback_data="pay_gen")]]
        await q.edit_message_text(t("daily_limit_exceeded", lang), reply_markup=InlineKeyboardMarkup(kb))
        return

    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", prompt)

    try:
        await q.edit_message_text(t("generating", lang).format(count))
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
                    await q.message.reply_text(t("api_error", lang))
                    return

            logger.debug(f"[DIGEN DATA] {json.dumps(data)[:2000]}")

            image_id = None
            if isinstance(data, dict):
                image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                logger.error("[DIGEN] image_id olinmadi")
                await q.message.reply_text(t("no_image_id", lang))
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/  {image_id}-{i}.jpeg" for i in range(count)]
            logger.info(f"[GENERATE] urls: {urls}")

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
                    await q.edit_message_text(t("image_delayed", lang))
                except Exception:
                    pass
                return

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

            await log_generation(pool, user, prompt, translated, image_id, count)
            await increment_daily_limit(user.id, pool)

            try:
                await q.edit_message_text(t("image_ready", lang))
            except BadRequest:
                pass

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        try:
            await q.edit_message_text(t("error_occurred", lang))
        except Exception:
            pass

# ---------------- Donate (Stars) flow ----------------
WAITING_AMOUNT = 1

async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz_latin")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(t("donate_prompt", lang))
    else:
        await update.message.reply_text(t("donate_prompt", lang))
    return WAITING_AMOUNT

async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", "uz_latin")
    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text(t("donate_invalid_amount", lang))
        return WAITING_AMOUNT

    payload = f"donate_{update.effective_user.id}_{int(time.time())}"
    prices = [LabeledPrice(f"{amount} Stars", amount)]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=t("donate_title", lang),
        description=t("donate_description", lang),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END

# ---------------- Payment for generation ----------------
async def pay_gen_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = context.user_data.get("lang", "uz_latin")

    payload = f"gen_{q.from_user.id}_{int(time.time())}"
    prices = [LabeledPrice("5 Stars", 5)]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=t("donate_title", lang),
        description=t("daily_limit_exceeded", lang),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        is_flexible=False
    )

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user = update.effective_user
    lang = context.user_data.get("lang", "uz_latin")

    if payment.invoice_payload.startswith("gen_"):
        # To'lov generatsiya uchun — rasm yaratishni davom ettiramiz
        await update.message.reply_text(t("payment_processing", lang))

        # user_data dan prompt va count ni olish
        prompt = context.user_data.get("prompt", "")
        translated = context.user_data.get("translated", prompt)
        # count ni saqlamaganmiz — shuning uchun default 1 qilamiz
        # Yaxshisi: count ni ham user_data ga saqlash kerak edi.
        count = 8  # Yoki xohlasangiz, 4 qilish ham mumkin

        # Xuddi generate_cb dagi kabi API so'rovini qilamiz
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
                    logger.info(f"[DIGEN PAID] status={resp.status}")
                    try:
                        data = await resp.json()
                    except Exception:
                        await update.message.reply_text(t("api_error", lang))
                        return

                image_id = None
                if isinstance(data, dict):
                    image_id = (data.get("data") or {}).get("id") or data.get("id")
                if not image_id:
                    await update.message.reply_text(t("no_image_id", lang))
                    return

                urls = [f"https://liveme-image.s3.amazonaws.com/  {image_id}-{i}.jpeg" for i in range(count)]

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
                    await update.message.reply_text(t("image_delayed", lang))
                    return

                media = [InputMediaPhoto(u) for u in urls]
                await update.message.reply_media_group(media)

                await log_generation(context.application.bot_data["db_pool"], user, prompt, translated, image_id, count)

                await update.message.reply_text(t("image_ready", lang))

        except Exception as e:
            logger.exception(f"[PAID GENERATE ERROR] {e}")
            await update.message.reply_text(t("error_occurred", lang))

    else:
        # Oddiy donate
        amount_stars = payment.total_amount // 100
        await update.message.reply_text(t("thank_you_donation", lang).format(user.first_name, amount_stars))
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
            lang = context.user_data.get("lang", "uz_latin")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=t("error_occurred", lang))
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

    # Language
    app.add_handler(CallbackQueryHandler(change_language_handler, pattern="change_lang"))
    app.add_handler(CallbackQueryHandler(set_language_cb, pattern=r"set_lang_"))

    # Donate
    donate_conv = ConversationHandler(
        entry_points=[CommandHandler("donate", donate_start), CallbackQueryHandler(donate_start, pattern="donate_custom")],
        states={WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[]
    )
    app.add_handler(donate_conv)

    # Payments
    app.add_handler(CallbackQueryHandler(pay_gen_handler, pattern="pay_gen"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Generate
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))

    # private plain text
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
