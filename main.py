```python
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
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any

import asyncpg
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, LabeledPrice, User
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, PreCheckoutQueryHandler, JobQueue
)
from telegram.error import BadRequest, TelegramError
from telegram.constants import ParseMode

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
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image").strip()
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_USERNAME = os.getenv("BOT_USERNAME", "DigenAi_Bot") # Default to a known value if not set

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)

# ---------------- STATE MANAGEMENT ----------------
DONATE_AMOUNT = 1
ADMIN_BROADCAST_MESSAGE = 1
ADMIN_BAN_USER_ID = 1
ADMIN_UNBAN_USER_ID = 1
ADMIN_USER_INFO_ID = 1

USER_DATA_LANG = "lang"
USER_DATA_PROMPT = "prompt"
USER_DATA_TRANSLATED = "translated"
USER_DATA_PROGRESS_MSG_ID = "progress_msg_id"
USER_DATA_PROGRESS_JOB = "progress_job"
USER_DATA_INVOICE_PAYLOAD = "invoice_payload"

# ---------------- TRANSLATIONS ----------------
# Siz o'zgartirish kiritishingiz mumkin bo'lgan qisqacha tarjima lug'ati
TRANSLATIONS = {
    "en": {
        "choose_language": "🌐 Please choose your language:",
        "language_set": "✅ Language set to {lang_code}.",
        "main_panel_text": "👋 Main panel — manage images, balance, and settings here.",
        "btn_generate": "🎨 Generate Image",
        "btn_donate": "💖 Donate",
        "btn_account": "👤 My Account",
        "btn_change_lang": "🌐 Change Language",
        "btn_info": "ℹ️ Info / Stats",
        "btn_admin": "🛡️ Admin Panel",
        "enter_prompt": "✍️ Please send the text prompt for the image (in private chat).",
        "prompt_received": "🖌 Your prompt:\n<pre>{prompt}</pre>\n\n🔢 How many images to generate?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Generating image(s) ({count})... ⏳",
        "generating_progress": "🔄 Generating image(s) ({count})... {progress}%",
        "generating_8_limited": "🔄 Generating image(s) ({count})... ⏳ (Used {used}/{limit} free 8-batches today)",
        "insufficient_balance_8": "⚠️ You have already used 3 free 8-image generations today. Each subsequent 8-image generation costs 1 Star. Insufficient balance.",
        "stars_deducted": "💳 {price} Star(s) deducted. Generating image(s) ({count})... ⏳",
        "image_ready": "✅ Image(s) ready! 📸",
        "btn_generate_again": "🔄 Generate Again",
        "enter_donate_amount": "💰 Please enter the amount you want to donate (1–100000):",
        "invalid_donate_amount": "❌ Please enter an integer between 1 and 100000.",
        "donate_invoice_title": "💖 Bot Donation",
        "donate_invoice_description": "Send an optional amount to support the bot.",
        "donate_thanks": "✅ Thank you, {first_name}! You sent {amount_stars} Stars.",
        "account_title": "👤 My Account",
        "account_balance": "💳 Balance: {balance} Stars",
        "account_referrals": "👥 Referred Users: {count}",
        "account_referral_link": "🔗 Your Referral Link:\n{link}",
        "account_withdraw": "📤 Withdraw",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Withdrawal feature is not ready yet — Coming soon! ⏳",
        "api_soon": "🔑 API access: Coming soon!",
        "info_title": "ℹ️ Bot Info",
        "info_description": "This bot allows you to generate AI images. Invite friends to earn Stars!",
        "btn_contact_admin": "📩 Contact Admin",
        "btn_realtime_stats": "📈 Real-time Stats",
        "stats_title": "📊 Real-time Statistics",
        "stats_uptime": "⏱ Uptime: {uptime}",
        "stats_ping": "🌐 Ping: {ping} ms",
        "stats_users": "👥 Users: {count}",
        "stats_images": "🖼 Total Images Generated: {count}",
        "stats_donations": "💰 Total Donations: {amount} Stars",
        "sub_check_prompt": "⛔ You must be subscribed to our channel to use the bot!",
        "sub_check_link_text": "🔗 Subscribe to Channel",
        "sub_check_button_text": "✅ Check Subscription",
        "sub_check_success": "✅ Thank you! You are subscribed. You can now use the bot.",
        "sub_check_fail": "⛔ You are still not subscribed. Please subscribe and check again.",
        "btn_back": "⬅️ Back",
        "btn_back_to_main": "🏠 Main Menu",
        "invalid_button": "❌ Invalid button.",
        "error_try_again": "⚠️ An error occurred. Please try again.",
        "image_wait_timeout": "⚠️ It's taking a while to prepare the image. Please try again later.",
        "image_id_missing": "❌ Failed to get image ID (API response).",
        "api_unknown_response": "❌ Unknown response from API. Please contact the admin.",
        "admin_panel_title": "🛡️ Admin Panel",
        "btn_admin_broadcast": "📢 Broadcast Message",
        "btn_admin_ban": "🚫 Ban User",
        "btn_admin_unban": "✅ Unban User",
        "btn_admin_user_info": "👤 Get User Info",
        "btn_admin_toggle_maintenance": "🛠️ Toggle Maintenance",
        "btn_admin_get_referrals": "👥 Get User Referrals",
        "enter_broadcast_message": "📢 Please send the message to broadcast:",
        "enter_user_id_to_ban": "🚫 Please enter the User ID to ban:",
        "enter_user_id_to_unban": "✅ Please enter the User ID to unban:",
        "enter_user_id_for_info": "👤 Please enter the User ID to get info:",
        "user_banned": "✅ User {user_id} has been banned.",
        "user_unbanned": "✅ User {user_id} has been unbanned.",
        "user_already_banned": "⚠️ User {user_id} is already banned.",
        "user_not_banned": "⚠️ User {user_id} is not banned.",
        "user_info_title": "👤 User Info",
        "user_info_details": "ID: {id}\nUsername: @{username}\nFirst Seen: {first_seen}\nLast Seen: {last_seen}\nLanguage: {lang}\nBalance: {balance} Stars\nReferral Count: {referral_count}",
        "referrals_title": "👥 Referrals for User {user_id}",
        "no_referrals_found": "❌ No referrals found for this user.",
        "maintenance_enabled": "🛠️ Maintenance mode enabled.",
        "maintenance_disabled": "✅ Maintenance mode disabled.",
        "invalid_user_id": "❌ Invalid User ID.",
        "user_not_found": "❌ User not found.",
        "maintenance_message": "🛠️ The bot is currently under maintenance. Please try again later.",
        "referral_reward": "You received {reward} Stars for a successful referral!",
        "btn_cancel": "❌ Cancel",
        "operation_cancelled": "❌ Operation cancelled.",
        "prompt_missing_group": "❌ In a group, please provide a prompt after /get. Example: /get futuristic city",
        "prompt_missing_private": "✍️ Please send the text prompt for the image (or just send plain text).",
    },
    "ru": {
        "choose_language": "🌐 Пожалуйста, выберите язык:",
        "language_set": "✅ Язык установлен на {lang_code}.",
        "main_panel_text": "👋 Главная панель — управляйте изображениями, балансом и настройками здесь.",
        "btn_generate": "🎨 Создать изображение",
        "btn_donate": "💖 Пожертвовать",
        "btn_account": "👤 Мой аккаунт",
        "btn_change_lang": "🌐 Изменить язык",
        "btn_info": "ℹ️ Информация / Статистика",
        "btn_admin": "🛡️ Панель администратора",
        "enter_prompt": "✍️ Пожалуйста, отправьте текстовый запрос для изображения (в личном чате).",
        "prompt_received": "🖌 Ваш запрос:\n<pre>{prompt}</pre>\n\n🔢 Сколько изображений сгенерировать?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Генерация изображения(й) ({count})... ⏳",
        "generating_progress": "🔄 Генерация изображения(й) ({count})... {progress}%",
        "generating_8_limited": "🔄 Генерация изображения(й) ({count})... ⏳ (Использовано {used}/{limit} бесплатных пакетов по 8 сегодня)",
        "insufficient_balance_8": "⚠️ Вы уже использовали 3 бесплатные генерации по 8 изображений сегодня. Каждая последующая генерация из 8 изображений стоит 1 Star. Недостаточный баланс.",
        "stars_deducted": "💳 Списано {price} Star(s). Генерация изображения(й) ({count})... ⏳",
        "image_ready": "✅ Изображение(я) готово(ы)! 📸",
        "btn_generate_again": "🔄 Создать снова",
        "enter_donate_amount": "💰 Пожалуйста, введите сумму пожертвования (1–100000):",
        "invalid_donate_amount": "❌ Пожалуйста, введите целое число от 1 до 100000.",
        "donate_invoice_title": "💖 Пожертвование боту",
        "donate_invoice_description": "Отправьте произвольную сумму для поддержки бота.",
        "donate_thanks": "✅ Спасибо, {first_name}! Вы отправили {amount_stars} Stars.",
        "account_title": "👤 Мой аккаунт",
        "account_balance": "💳 Баланс: {balance} Stars",
        "account_referrals": "👥 Приглашенные пользователи: {count}",
        "account_referral_link": "🔗 Ваша реферальная ссылка:\n{link}",
        "account_withdraw": "📤 Вывести",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Функция вывода ещё не готова — Скоро будет! ⏳",
        "api_soon": "🔑 Доступ к API: Скоро!",
        "info_title": "ℹ️ Информация о боте",
        "info_description": "Этот бот позволяет генерировать изображения с помощью ИИ. Приглашайте друзей, чтобы заработать Звезды!",
        "btn_contact_admin": "📩 Связаться с админом",
        "btn_realtime_stats": "📈 Статистика в реальном времени",
        "stats_title": "📊 Статистика в реальном времени",
        "stats_uptime": "⏱ Время работы: {uptime}",
        "stats_ping": "🌐 Пинг: {ping} мс",
        "stats_users": "👥 Пользователи: {count}",
        "stats_images": "🖼 Всего сгенерировано изображений: {count}",
        "stats_donations": "💰 Всего пожертвований: {amount} Stars",
        "sub_check_prompt": "⛔ Вы должны быть подписаны на наш канал, чтобы использовать бота!",
        "sub_check_link_text": "🔗 Подписаться на канал",
        "sub_check_button_text": "✅ Проверить подписку",
        "sub_check_success": "✅ Спасибо! Вы подписаны. Теперь вы можете использовать бота.",
        "sub_check_fail": "⛔ Вы всё ещё не подписаны. Пожалуйста, подпишитесь и проверьте снова.",
        "btn_back": "⬅️ Назад",
        "btn_back_to_main": "🏠 Главное меню",
        "invalid_button": "❌ Неверная кнопка.",
        "error_try_again": "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.",
        "image_wait_timeout": "⚠️ Подготовка изображения занимает много времени. Пожалуйста, попробуйте позже.",
        "image_id_missing": "❌ Не удалось получить ID изображения (ответ API).",
        "api_unknown_response": "❌ Неизвестный ответ от API. Пожалуйста, свяжитесь с администратором.",
        "admin_panel_title": "🛡️ Панель администратора",
        "btn_admin_broadcast": "📢 Рассылка сообщения",
        "btn_admin_ban": "🚫 Забанить пользователя",
        "btn_admin_unban": "✅ Разбанить пользователя",
        "btn_admin_user_info": "👤 Получить информацию о пользователе",
        "btn_admin_toggle_maintenance": "🛠️ Переключить режим обслуживания",
        "btn_admin_get_referrals": "👥 Получить рефералов пользователя",
        "enter_broadcast_message": "📢 Пожалуйста, отправьте сообщение для рассылки:",
        "enter_user_id_to_ban": "🚫 Пожалуйста, введите ID пользователя для бана:",
        "enter_user_id_to_unban": "✅ Пожалуйста, введите ID пользователя для разбана:",
        "enter_user_id_for_info": "👤 Пожалуйста, введите ID пользователя для получения информации:",
        "user_banned": "✅ Пользователь {user_id} забанен.",
        "user_unbanned": "✅ Пользователь {user_id} разбанен.",
        "user_already_banned": "⚠️ Пользователь {user_id} уже забанен.",
        "user_not_banned": "⚠️ Пользователь {user_id} не забанен.",
        "user_info_title": "👤 Информация о пользователе",
        "user_info_details": "ID: {id}\nUsername: @{username}\nПервый вход: {first_seen}\nПоследний вход: {last_seen}\nЯзык: {lang}\nБаланс: {balance} Stars\nКоличество рефералов: {referral_count}",
        "referrals_title": "👥 Рефералы пользователя {user_id}",
        "no_referrals_found": "❌ Рефералы для этого пользователя не найдены.",
        "maintenance_enabled": "🛠️ Режим обслуживания включен.",
        "maintenance_disabled": "✅ Режим обслуживания выключен.",
        "invalid_user_id": "❌ Неверный ID пользователя.",
        "user_not_found": "❌ Пользователь не найден.",
        "maintenance_message": "🛠️ Бот находится на техническом обслуживании. Пожалуйста, попробуйте позже.",
        "referral_reward": "Вы получили {reward} Stars за успешное приглашение!",
        "btn_cancel": "❌ Отмена",
        "operation_cancelled": "❌ Операция отменена.",
        "prompt_missing_group": "❌ В группе, пожалуйста, укажите запрос после /get. Пример: /get футуристический город",
        "prompt_missing_private": "✍️ Пожалуйста, отправьте текстовый запрос для изображения (или просто отправьте текст).",
    },
    "uz": {
        "choose_language": "🌐 Iltimos, tilni tanlang:",
        "language_set": "✅ Til {lang_code} ga o'zgartirildi.",
        "main_panel_text": "👋 Bosh panel — bu yerdan rasmlar, balans va sozlamalarni boshqarishingiz mumkin.",
        "btn_generate": "🎨 Rasm yaratish",
        "btn_donate": "💖 Donate",
        "btn_account": "👤 Hisobim",
        "btn_change_lang": "🌐 Tilni o‘zgartirish",
        "btn_info": "ℹ️ Statistika / Info",
        "btn_admin": "🛡️ Admin Panel",
        "enter_prompt": "✍️ Endi tasvir yaratish uchun matn yuboring (privatda).",
        "prompt_received": "🖌 Sizning matningiz:\n<pre>{prompt}</pre>\n\n🔢 Nechta rasm yaratilsin?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Rasm yaratilmoqda ({count})... ⏳",
        "generating_progress": "🔄 Rasm yaratilmoqda ({count})... {progress}%",
        "generating_8_limited": "🔄 Rasm yaratilmoqda ({count})... ⏳ (bugun {used}/{limit} dan foydalanildi)",
        "insufficient_balance_8": "⚠️ Siz bugun allaqachon 3 marta 8 ta rasm yaratdingiz. Har keyingi 8 ta generatsiya — 1 Stars. Balans yetarli emas.",
        "stars_deducted": "💳 {price} Stars yechildi. Rasm yaratilmoqda ({count})... ⏳",
        "image_ready": "✅ Rasm tayyor! 📸",
        "btn_generate_again": "🔄 Yana yaratish",
        "enter_donate_amount": "💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):",
        "invalid_donate_amount": "❌ Iltimos, 1–100000 oralig‘ida butun son kiriting.",
        "donate_invoice_title": "💖 Bot Donation",
        "donate_invoice_description": "Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        "donate_thanks": "✅ Rahmat, {first_name}! Siz {amount_stars} Stars yubordingiz.",
        "account_title": "👤 Hisobim",
        "account_balance": "💳 Balans: {balance} Stars",
        "account_referrals": "👥 Taklif qilinganlar: {count}",
        "account_referral_link": "🔗 Sizning referral link:\n{link}",
        "account_withdraw": "📤 Yechib olish",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Yechib olish funksiyasi hozircha tayyor emas — Tez kunda! ⏳",
        "api_soon": "🔑 API: Tez kunda",
        "info_title": "ℹ️ Bot Haqida",
        "info_description": "Bu bot AI yordamida rasmlar yaratish imkonini beradi. Do'stlaringizni taklif qiling va Stars yig'ing!",
        "btn_contact_admin": "📩 Admin bilan bog‘lanish",
        "btn_realtime_stats": "📈 Real vaqt statistikasi",
        "stats_title": "📊 Real vaqt statistikasi",
        "stats_uptime": "⏱ Ish vaqti (uptime): {uptime}",
        "stats_ping": "🌐 Ping: {ping} ms",
        "stats_users": "👥 Foydalanuvchilar: {count}",
        "stats_images": "🖼 Umumiy yaratilgan rasmlar: {count}",
        "stats_donations": "💰 Umumiy donations: {amount} Stars",
        "sub_check_prompt": "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
        "sub_check_link_text": "🔗 Kanalga obuna bo‘lish",
        "sub_check_button_text": "✅ Obunani tekshirish",
        "sub_check_success": "✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.",
        "sub_check_fail": "⛔ Hali ham obuna bo‘lmagansiz. Obuna bo‘lib, qayta tekshiring.",
        "btn_back": "⬅️ Ortga",
        "btn_back_to_main": "🏠 Bosh menyu",
        "invalid_button": "❌ Noto'g'ri tugma.",
        "error_try_again": "⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.",
        "image_wait_timeout": "⚠️ Rasmni tayyorlash biroz vaqt olmoqda. Keyinroq urinib ko'ring.",
        "image_id_missing": "❌ Rasm ID olinmadi (API javobi).",
        "api_unknown_response": "❌ API dan noma'lum javob keldi. Adminga murojaat qiling.",
        "admin_panel_title": "🛡️ Admin Panel",
        "btn_admin_broadcast": "📢 Xabar yuborish",
        "btn_admin_ban": "🚫 Foydalanuvchini ban qilish",
        "btn_admin_unban": "✅ Foydalanuvchini bandan chiqarish",
        "btn_admin_user_info": "👤 Foydalanuvchi haqida ma'lumot",
        "btn_admin_toggle_maintenance": "🛠️ Xizmat ko'rsatish rejimini yoqish/o'chirish",
        "btn_admin_get_referrals": "👥 Foydalanuvchi referallarini olish",
        "enter_broadcast_message": "📢 Iltimos, tarqatish uchun xabar yuboring:",
        "enter_user_id_to_ban": "🚫 Iltimos, ban qilish uchun foydalanuvchi ID'sini kiriting:",
        "enter_user_id_to_unban": "✅ Iltimos, bandan chiqarish uchun foydalanuvchi ID'sini kiriting:",
        "enter_user_id_for_info": "👤 Iltimos, ma'lumot olish uchun foydalanuvchi ID'sini kiriting:",
        "user_banned": "✅ Foydalanuvchi {user_id} ban qilindi.",
        "user_unbanned": "✅ Foydalanuvchi {user_id} bandan chiqarildi.",
        "user_already_banned": "⚠️ Foydalanuvchi {user_id} allaqachon ban qilingan.",
        "user_not_banned": "⚠️ Foydalanuvchi {user_id} ban qilinmagan.",
        "user_info_title": "👤 Foydalanuvchi haqida ma'lumot",
        "user_info_details": "ID: {id}\nUsername: @{username}\nBirinchi kirish: {first_seen}\nOxirgi kirish: {last_seen}\nTil: {lang}\nBalans: {balance} Stars\nReferallar soni: {referral_count}",
        "referrals_title": "👥 Foydalanuvchi {user_id} referallari",
        "no_referrals_found": "❌ Bu foydalanuvchi uchun referallar topilmadi.",
        "maintenance_enabled": "🛠️ Xizmat ko'rsatish rejimi yoqildi.",
        "maintenance_disabled": "✅ Xizmat ko'rsatish rejimi o'chirildi.",
        "invalid_user_id": "❌ Noto'g'ri foydalanuvchi ID'si.",
        "user_not_found": "❌ Foydalanuvchi topilmadi.",
        "maintenance_message": "🛠️ Bot hozirda texnik xizmat ko'rsatish ostida. Iltimos, keyinroq qayta urinib ko'ring.",
        "referral_reward": "Muvaffaqiyatli taklif qilish uchun {reward} Stars oldingiz!",
        "btn_cancel": "❌ Bekor qilish",
        "operation_cancelled": "❌ Operatsiya bekor qilindi.",
        "prompt_missing_group": "❌ Guruhda /get dan keyin prompt yozing. Misol: /get futuristik shahar",
        "prompt_missing_private": "✍️ Iltimos, rasm uchun matn yozing (yoki oddiy matn yuboring).",
    },
    # Qolgan tillar uchun tarjimalarni shu yerda qo'shishingiz mumkin...
    # Masalan, "es", "id", "pt", "zh", "hi", "ar", "bn", "vi", "uk", "lt", "es-MX", "it", "uzk"
    # Hozircha ular uchun ingliz tilidan foydalanamiz
}

def t(lang_code: str, key: str, **kwargs) -> str:
    """Foydalanuvchi tiliga qarab kalit so'zni tarjima qiladi."""
    lang_dict = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])
    template = lang_dict.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            logger.warning(f"Translation key '{key}' format error with args {kwargs}")
    return template

# ---------------- MAINTENANCE MODE ----------------
MAINTENANCE_MODE = False

# ---------------- helpers ----------------
def escape_html(text: str) -> str:
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

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
    lang TEXT,
    balance NUMERIC DEFAULT 0,
    is_banned BOOLEAN DEFAULT FALSE
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

-- Add columns if they don't exist (PostgreSQL specific)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='lang') THEN
        ALTER TABLE users ADD COLUMN lang TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='balance') THEN
        ALTER TABLE users ADD COLUMN balance NUMERIC DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='is_banned') THEN
        ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT FALSE;
    END IF;
END
$$;
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
    if not CHANNEL_ID or not CHANNEL_USERNAME:
        logger.warning("CHANNEL_ID or CHANNEL_USERNAME not set, skipping subscription check.")
        return True
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logger.debug(f"[SUB CHECK ERROR] {e}")
        return False

async def force_sub_if_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type != "private":
        return True
    user_id = update.effective_user.id
    user_rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    if user_rec and user_rec.get("is_banned"):
        lang_code = user_rec.get("lang", "en")
        await update.message.reply_text(t(lang_code, "maintenance_message")) # Using same message for ban
        return False
    ok = await check_subscription(user_id, context)
    if not ok:
        lang_code = get_user_language(context, user_id)
        kb = [
            [InlineKeyboardButton(t(lang_code, "sub_check_link_text"), url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(t(lang_code, "sub_check_button_text"), callback_data="check_sub")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(t(lang_code, "sub_check_prompt"), reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(t(lang_code, "sub_check_prompt"), reply_markup=InlineKeyboardMarkup(kb))
        return False
    return True

async def check_sub_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if MAINTENANCE_MODE:
        lang_code = get_user_language(context, user_id)
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return
    user_rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    if user_rec and user_rec.get("is_banned"):
        lang_code = user_rec.get("lang", "en")
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return
    if await check_subscription(user_id, context):
        lang_code = get_user_language(context, user_id)
        text, kb = await send_main_panel(q.message.chat, lang_code, context.application.bot_data)
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        lang_code = get_user_language(context, user_id)
        kb = [
            [InlineKeyboardButton(t(lang_code, "sub_check_link_text"), url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(t(lang_code, "sub_check_button_text"), callback_data="check_sub")]
        ]
        await q.edit_message_text(t(lang_code, "sub_check_fail"), reply_markup=InlineKeyboardMarkup(kb))

# ---------------- DB user/session/logging ----------------
async def add_user_db(pool, tg_user: User) -> bool:
    now = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if row:
            await conn.execute(
                "UPDATE users SET username=$1, last_seen=$2 WHERE id=$3",
                tg_user.username if tg_user.username else None, now, tg_user.id
            )
            created = False
        else:
            await conn.execute(
                "INSERT INTO users(id, username, first_seen, last_seen, lang) VALUES($1,$2,$3,$4,$5)",
                tg_user.id, tg_user.username if tg_user.username else None, now, now, None
            )
            created = True
        await conn.execute("INSERT INTO sessions(user_id, started_at) VALUES($1,$2)", tg_user.id, now)
    return created

async def get_user_record(pool, user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)

async def set_user_lang(pool, user_id: int, lang_code: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET lang=$1 WHERE id=$2", lang_code, user_id)

async def adjust_user_balance(pool, user_id: int, delta: Decimal):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = (COALESCE(balance, 0) + $1) WHERE id=$2", str(delta), user_id)

async def log_generation(pool, tg_user: User, prompt: str, translated: str, image_id: str, count: int):
    now = utc_now()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO generations(user_id, username, prompt, translated_prompt, image_id, image_count, created_at) "
            "VALUES($1,$2,$3,$4,$5,$6,$7)",
            tg_user.id, tg_user.username if tg_user.username else None,
            prompt, translated, image_id, count, now
        )

async def ban_user(pool, user_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE users SET is_banned = TRUE WHERE id = $1", user_id)
        return result != "UPDATE 0"

async def unban_user(pool, user_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE users SET is_banned = FALSE WHERE id = $1", user_id)
        return result != "UPDATE 0"

async def is_user_banned(pool, user_id: int) -> bool:
    user_rec = await get_user_record(pool, user_id)
    return user_rec.get("is_banned") if user_rec else False

# ---------------- Limits / Referral helpers ----------------
FREE_8_PER_DAY = 3
PRICE_PER_8 = Decimal("1")
REFERRAL_REWARD = Decimal("0.25")

async def get_8_used_today(pool, user_id: int) -> int:
    now = utc_now()
    start_day = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    async with pool.acquire() as conn:
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM generations WHERE user_id=$1 AND image_count=8 AND created_at >= $2",
            user_id, start_day
        )
    return int(cnt or 0)

async def handle_referral(pool, inviter_id: int, invited_id: int):
    if inviter_id == invited_id:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM referrals WHERE invited_id=$1", invited_id)
        if row:
            return False
        try:
            await conn.execute("INSERT INTO referrals(inviter_id, invited_id) VALUES($1,$2)", inviter_id, invited_id)
            await conn.execute("UPDATE users SET balance = COALESCE(balance, 0) + $1 WHERE id=$2", str(REFERRAL_REWARD), inviter_id)
            return True
        except asyncpg.UniqueViolationError:
            return False
        except Exception as e:
            logger.exception(f"[REFERRAL ERR] {e}")
            return False

# ---------------- UI: languages ----------------
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

def build_lang_keyboard(lang_code: str):
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

# ---------------- Language Helper ----------------
def get_user_language(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    if context.user_data and USER_DATA_LANG in context.user_data:
        return context.user_data[USER_DATA_LANG]
    return "en"

# ---------------- Handlers ----------------
async def send_main_panel(chat, lang_code: str, bot_data: dict):
    kb = [
        [InlineKeyboardButton(t(lang_code, "btn_generate"), callback_data="start_gen")],
        [InlineKeyboardButton(t(lang_code, "btn_donate"), callback_data="donate_custom"), InlineKeyboardButton(t(lang_code, "btn_account"), callback_data="my_account")],
        [InlineKeyboardButton(t(lang_code, "btn_change_lang"), callback_data="change_lang"), InlineKeyboardButton(t(lang_code, "btn_info"), callback_data="show_info")],
    ]
    if chat.id == ADMIN_ID:
        kb.append([InlineKeyboardButton(t(lang_code, "btn_admin"), callback_data="admin_panel")])
    text = t(lang_code, "main_panel_text")
    return text, InlineKeyboardMarkup(kb)

# START
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        await update.message.reply_text("🛠️ The bot is currently under maintenance. Please try again later.")
        return

    if not await force_sub_if_private(update, context):
        return

    created = await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    user_rec = await get_user_record(context.application.bot_data["db_pool"], update.effective_user.id)
    
    args = context.args or []
    if created and args:
        for a in args:
            if a.startswith("ref_"):
                try:
                    inviter_id = int(a.split("_", 1)[1])
                    if inviter_id != update.effective_user.id:
                        await handle_referral(context.application.bot_data["db_pool"], inviter_id, update.effective_user.id)
                except Exception as e:
                    logger.warning(f"[REFERRAL PARSE ERROR] {e}")

    if not user_rec or not user_rec.get("lang"):
        context.user_data[USER_DATA_LANG] = "en"
        await update.message.reply_text(
            t("en", "choose_language"),
            reply_markup=build_lang_keyboard("en")
        )
        return

    lang_code = user_rec["lang"]
    context.user_data[USER_DATA_LANG] = lang_code
    text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def change_lang_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    if MAINTENANCE_MODE:
        user_id = q.from_user.id
        lang_code = get_user_language(context, user_id)
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return
    user_id = q.from_user.id
    lang_code = get_user_language(context, user_id)
    await q.edit_message_text(t(lang_code, "choose_language"), reply_markup=build_lang_keyboard(lang_code))

async def set_lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    if MAINTENANCE_MODE:
        user_id = q.from_user.id
        lang_code = get_user_language(context, user_id)
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return
    data = q.data
    code = data.split("_", 2)[2]
    await set_user_lang(context.application.bot_data["db_pool"], q.from_user.id, code)
    context.user_data[USER_DATA_LANG] = code
    text, kb = await send_main_panel(q.message.chat, code, context.application.bot_data)
    confirmation_text = t(code, "language_set", lang_code=code)
    full_text = f"{confirmation_text}\n\n{text}"
    try:
        await q.edit_message_text(full_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except BadRequest:
        try:
            await q.message.reply_text(full_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if update.callback_query:
        await update.callback_query.answer()
    if MAINTENANCE_MODE:
        user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
        lang_code = get_user_language(context, user_id)
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text(t(lang_code, "maintenance_message"))
        return
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    lang_code = get_user_language(context, user_id)
    await update.effective_message.reply_text(t(lang_code, "enter_prompt"))

# /get command
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "maintenance_message"))
        return

    if not await force_sub_if_private(update, context):
        return
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup"):
        if not context.args:
            lang_code = get_user_language(context, update.effective_user.id)
            await update.message.reply_text(t(lang_code, "prompt_missing_group"))
            return
        prompt = " ".join(context.args)
        message_text = t(get_user_language(context, update.effective_user.id), "prompt_received", prompt=escape_html(prompt))
    else:
        if not context.args:
            lang_code = get_user_language(context, update.effective_user.id)
            await update.message.reply_text(t(lang_code, "prompt_missing_private"))
            return
        prompt = " ".join(context.args)
        message_text = t(get_user_language(context, update.effective_user.id), "prompt_received", prompt=escape_html(prompt))

    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    context.user_data[USER_DATA_PROMPT] = prompt
    context.user_data[USER_DATA_TRANSLATED] = prompt
    lang_code = get_user_language(context, update.effective_user.id)
    kb = [[
        InlineKeyboardButton(t(lang_code, "btn_1"), callback_data="count_1"),
        InlineKeyboardButton(t(lang_code, "btn_2"), callback_data="count_2"),
        InlineKeyboardButton(t(lang_code, "btn_4"), callback_data="count_4"),
        InlineKeyboardButton(t(lang_code, "btn_8"), callback_data="count_8"),
    ]]
    await update.message.reply_text(message_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

# Private plain text -> prompt
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "maintenance_message"))
        return

    if update.effective_chat.type != "private":
        return
    if not await force_sub_if_private(update, context):
        return
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data[USER_DATA_PROMPT] = prompt
    context.user_data[USER_DATA_TRANSLATED] = prompt
    lang_code = get_user_language(context, update.effective_user.id)
    message_text = t(lang_code, "prompt_received", prompt=escape_html(prompt))
    kb = [[
        InlineKeyboardButton(t(lang_code, "btn_1"), callback_data="count_1"),
        InlineKeyboardButton(t(lang_code, "btn_2"), callback_data="count_2"),
        InlineKeyboardButton(t(lang_code, "btn_4"), callback_data="count_4"),
        InlineKeyboardButton(t(lang_code, "btn_8"), callback_data="count_8"),
    ]]
    await update.message.reply_text(message_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

# ---------------- Progress Simulation ----------------
async def simulate_progress(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job:
        return
    data = job.data
    chat_id = data.get('chat_id')
    message_id = data.get('message_id')
    count = data.get('count')
    used = data.get('used', None)
    limit = data.get('limit', None)
    price_deducted = data.get('price_deducted', None)
    lang_code = data.get('lang_code')
    progress = data.get('progress', 0)
    
    if not chat_id or not message_id or not lang_code:
        return

    progress = min(progress + random.randint(10, 20), 95)
    data['progress'] = progress
    
    try:
        if count == 8 and used is not None and limit is not None:
            if price_deducted:
                text = t(lang_code, "stars_deducted", price=price_deducted, count=count)
            else:
                text = t(lang_code, "generating_8_limited", count=count, used=used, limit=limit)
        else:
            if price_deducted:
                text = t(lang_code, "stars_deducted", price=price_deducted, count=count)
            else:
                text = t(lang_code, "generating", count=count)
                
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"{text}\n{progress}%")
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Progress update error: {e}")
    except Exception as e:
        logger.warning(f"Unexpected progress update error: {e}")

# GENERATE
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    if MAINTENANCE_MODE:
        user_id = q.from_user.id
        lang_code = get_user_language(context, user_id)
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return

    try:
        count = int(q.data.split("_")[1])
    except Exception:
        user_id = q.from_user.id
        lang_code = get_user_language(context, user_id)
        try:
            await q.edit_message_text(t(lang_code, "invalid_button"))
        except Exception:
            pass
        return

    user = q.from_user
    prompt = context.user_data.get(USER_DATA_PROMPT, "")
    translated = context.user_data.get(USER_DATA_TRANSLATED, prompt)

    user_rec = await get_user_record(context.application.bot_data["db_pool"], user.id)
    if user_rec and user_rec.get("is_banned"):
        lang_code = user_rec.get("lang", "en")
        try:
            await q.edit_message_text(t(lang_code, "maintenance_message"))
        except Exception:
            pass
        return

    if count == 8:
        pool = context.application.bot_data["db_pool"]
        used = await get_8_used_today(pool, user.id)
        if used >= FREE_8_PER_DAY:
            rec = await get_user_record(pool, user.id)
            balance = Decimal(rec.get("balance") or 0)
            if balance < PRICE_PER_8:
                kb = [
                    [InlineKeyboardButton(t(get_user_language(context, user.id), "btn_donate"), callback_data="donate_custom")],
                    [InlineKeyboardButton(t(get_user_language(context, user.id), "btn_account"), callback_data="my_account")]
                ]
                lang_code = get_user_language(context, user.id)
                try:
                    await q.edit_message_text(t(lang_code, "insufficient_balance_8"), reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    pass
                return
            else:
                await adjust_user_balance(pool, user.id, -PRICE_PER_8)
                lang_code = get_user_language(context, user.id)
                progress_text = t(lang_code, "stars_deducted", price=PRICE_PER_8, count=count)
                progress_msg = await q.edit_message_text(f"{progress_text}\n0%")
                context.user_data[USER_DATA_PROGRESS_MSG_ID] = progress_msg.message_id
                
                job_queue: JobQueue = context.job_queue
                if job_queue:
                    job_data = {
                        'chat_id': progress_msg.chat_id,
                        'message_id': progress_msg.message_id,
                        'count': count,
                        'price_deducted': str(PRICE_PER_8),
                        'lang_code': lang_code,
                        'progress': 0
                    }
                    job = job_queue.run_repeating(simulate_progress, interval=2, first=2, data=job_data)
                    context.user_data[USER_DATA_PROGRESS_JOB] = job
        else:
            lang_code = get_user_language(context, user.id)
            progress_text = t(lang_code, "generating_8_limited", count=count, used=used, limit=FREE_8_PER_DAY)
            progress_msg = await q.edit_message_text(f"{progress_text}\n0%")
            context.user_data[USER_DATA_PROGRESS_MSG_ID] = progress_msg.message_id
            
            job_queue: JobQueue = context.job_queue
            if job_queue:
                job_data = {
                    'chat_id': progress_msg.chat_id,
                    'message_id': progress_msg.message_id,
                    'count': count,
                    'used': used,
                    'limit': FREE_8_PER_DAY,
                    'lang_code': lang_code,
                    'progress': 0
                }
                job = job_queue.run_repeating(simulate_progress, interval=2, first=2, data=job_data)
                context.user_data[USER_DATA_PROGRESS_JOB] = job
    else:
        lang_code = get_user_language(context, user.id)
        progress_text = t(lang_code, "generating", count=count)
        progress_msg = await q.edit_message_text(f"{progress_text}\n0%")
        context.user_data[USER_DATA_PROGRESS_MSG_ID] = progress_msg.message_id
        
        job_queue: JobQueue = context.job_queue
        if job_queue:
            job_data = {
                'chat_id': progress_msg.chat_id,
                'message_id': progress_msg.message_id,
                'count': count,
                'lang_code': lang_code,
                'progress': 0
            }
            job = job_queue.run_repeating(simulate_progress, interval=2, first=2, data=job_data)
            context.user_data[USER_DATA_PROGRESS_JOB] = job

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
                    lang_code = get_user_language(context, user.id)
                    await q.message.reply_text(t(lang_code, "api_unknown_response"))
                    if USER_DATA_PROGRESS_JOB in context.user_data:
                        job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                        job.schedule_removal()
                    return

            logger.debug(f"[DIGEN DATA] {json.dumps(data)[:2000]}")

            image_id = None
            if isinstance(data, dict):
                image_id = (data.get("data") or {}).get("id") or data.get("id")
            if not image_id:
                logger.error("[DIGEN] image_id olinmadi")
                lang_code = get_user_language(context, user.id)
                await q.message.reply_text(t(lang_code, "image_id_missing"))
                if USER_DATA_PROGRESS_JOB in context.user_data:
                    job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                    job.schedule_removal()
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
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
                lang_code = get_user_language(context, user.id)
                try:
                    await q.edit_message_text(t(lang_code, "image_wait_timeout"))
                except Exception:
                    pass
                if USER_DATA_PROGRESS_JOB in context.user_data:
                    job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                    job.schedule_removal()
                return

            if USER_DATA_PROGRESS_JOB in context.user_data:
                job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                job.schedule_removal()
            
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

            lang_code = get_user_language(context, user.id)
            kb = [[InlineKeyboardButton(t(lang_code, "btn_generate_again"), callback_data="start_gen")]]
            last_progress_msg_id = context.user_data.pop(USER_DATA_PROGRESS_MSG_ID, None)
            if last_progress_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=q.message.chat_id,
                        message_id=last_progress_msg_id,
                        text=t(lang_code, "image_ready"),
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit progress message: {e}")
                    await q.message.reply_text(t(lang_code, "image_ready"), reply_markup=InlineKeyboardMarkup(kb))
            else:
                await q.message.reply_text(t(lang_code, "image_ready"), reply_markup=InlineKeyboardMarkup(kb))

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        lang_code = get_user_language(context, user.id)
        try:
            await q.edit_message_text(t(lang_code, "error_try_again"))
        except Exception:
            pass
        if USER_DATA_PROGRESS_JOB in context.user_data:
            job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
            job.schedule_removal()

# ---------------- Donate (Stars) flow ----------------
async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if update.callback_query:
        await update.callback_query.answer()
    if MAINTENANCE_MODE:
        user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
        lang_code = get_user_language(context, user_id)
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text(t(lang_code, "maintenance_message"))
        return ConversationHandler.END
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    lang_code = get_user_language(context, user_id)
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(t(lang_code, "enter_donate_amount"))
    return DONATE_AMOUNT

async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "maintenance_message"))
        return ConversationHandler.END

    if update.message.text.strip().lower() in ["/start", "/cancel", "cancel", "bekor qilish"]:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "operation_cancelled"))
        text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "invalid_donate_amount"))
        return DONATE_AMOUNT

    payload = f"donate_{update.effective_user.id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    context.user_data[USER_DATA_INVOICE_PAYLOAD] = payload
    prices = [LabeledPrice(f"{amount} Stars", amount * 100)]
    lang_code = get_user_language(context, update.effective_user.id)
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=t(lang_code, "donate_invoice_title"),
        description=t(lang_code, "donate_invoice_description"),
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    payload = query.invoice_payload
    user_id_from_payload = int(payload.split("_")[1])
    if user_id_from_payload == query.from_user.id:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Something went wrong...")

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount // 100
    user = update.effective_user
    lang_code = get_user_language(context, user.id)
    thanks_text = t(lang_code, "donate_thanks", first_name=user.first_name, amount_stars=amount_stars)
    await update.message.reply_text(thanks_text)
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload) VALUES($1,$2,$3,$4)",
            user.id, user.username if user.username else None, amount_stars, payment.invoice_payload
        )
    await adjust_user_balance(pool, user.id, Decimal(amount_stars))
    
    text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ---------------- Hisobim / Account panel ----------------
async def my_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        if MAINTENANCE_MODE:
            lang_code = get_user_language(context, q.from_user.id)
            await q.edit_message_text(t(lang_code, "maintenance_message"))
            return
        user_id = q.from_user.id
        chat = q.message.chat
    else:
        if MAINTENANCE_MODE:
            lang_code = get_user_language(context, update.effective_user.id)
            await update.message.reply_text(t(lang_code, "maintenance_message"))
            return
        user_id = update.effective_user.id
        chat = update.effective_chat

    rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    if not rec:
        lang_code = get_user_language(context, user_id)
        await chat.send_message(t(lang_code, "error_try_again"))
        return
        
    balance = Decimal(rec.get("balance") or 0)
    async with context.application.bot_data["db_pool"].acquire() as conn:
        refs = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id=$1", user_id)
    refs = int(refs or 0)
    
    bot_username = BOT_USERNAME or "DigenAi_Bot"
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    lang_code = rec.get("lang") or "en"
    account_title = t(lang_code, "account_title")
    account_balance = t(lang_code, "account_balance", balance=balance)
    account_referrals = t(lang_code, "account_referrals", count=refs)
    account_referral_link = t(lang_code, "account_referral_link", link=referral_link)
    account_withdraw = t(lang_code, "account_withdraw")
    account_api = t(lang_code, "account_api")
    withdraw_soon_text = t(lang_code, "withdraw_soon")
    api_soon_text = t(lang_code, "api_soon")
    
    text = (
        f"<b>{account_title}</b>\n\n"
        f"{account_balance}\n"
        f"{account_referrals}\n\n"
        f"{account_referral_link}\n\n"
        f"<b>{account_withdraw}:</b> {withdraw_soon_text}\n"
        f"<b>{account_api}:</b> {api_soon_text}"
    )
    kb = [
        [InlineKeyboardButton(t(lang_code, "btn_donate"), callback_data="donate_custom"), InlineKeyboardButton(account_withdraw, callback_data="withdraw")],
        [InlineKeyboardButton(t(lang_code, "btn_change_lang"), callback_data="change_lang"), InlineKeyboardButton(t(lang_code, "btn_back"), callback_data="back_main")]
    ]
    if update.callback_query:
        try:
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        except BadRequest:
            try:
                await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
            except Exception:
                pass
    else:
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# ---------------- Info / Stats ----------------
async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        if MAINTENANCE_MODE:
            lang_code = get_user_language(context, q.from_user.id)
            await q.edit_message_text(t(lang_code, "maintenance_message"))
            return
        chat = q.message.chat
        user_lang = get_user_language(context, q.from_user.id)
    else:
        if MAINTENANCE_MODE:
            lang_code = get_user_language(context, update.effective_user.id)
            await update.message.reply_text(t(lang_code, "maintenance_message"))
            return
        chat = update.effective_chat
        user_lang = get_user_language(context, update.effective_user.id)

    info_title = t(user_lang, "info_title")
    info_description = t(user_lang, "info_description")
    
    text = f"<b>{info_title}</b>\n\n{info_description}"
    
    kb = [
        [InlineKeyboardButton(t(user_lang, "btn_contact_admin"), url=f"tg://user?id={ADMIN_ID}")],
        [InlineKeyboardButton(t(user_lang, "btn_realtime_stats"), callback_data="realtime_stats")],
        [InlineKeyboardButton(t(user_lang, "btn_back"), callback_data="back_main")]
    ]
    
    if update.callback_query:
        try:
            await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
        except BadRequest:
            await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def realtime_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    stats_msg = await q.edit_message_text(t(user_lang, "stats_title") + "\n🔄 Yangilanmoqda...")
    
    job_queue: JobQueue = context.job_queue
    if job_queue:
        job_data = {
            'chat_id': stats_msg.chat_id,
            'message_id': stats_msg.message_id,
            'user_lang': user_lang,
            'db_pool': context.application.bot_data["db_pool"]
        }
        job = job_queue.run_repeating(update_stats_message, interval=5, first=0, data=job_data)
        context.chat_data['stats_job'] = job

async def update_stats_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job:
        return
    data = job.data
    chat_id = data.get('chat_id')
    message_id = data.get('message_id')
    user_lang = data.get('user_lang')
    pool = data.get('db_pool')
    
    if not chat_id or not message_id or not user_lang or not pool:
        return

    try:
        async with pool.acquire() as conn:
            start_time_row = await conn.fetchrow("SELECT value FROM meta WHERE key='start_time'")
            start_ts = int(start_time_row["value"]) if start_time_row else int(time.time())
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            gen_count = await conn.fetchval("SELECT COUNT(*) FROM generations")
            donation_sum_row = await conn.fetchval("SELECT COALESCE(SUM(stars),0) FROM donations")
            donation_sum = int(donation_sum_row) if donation_sum_row else 0
            
        uptime_seconds = int(time.time()) - start_ts
        uptime_str = str(timedelta(seconds=uptime_seconds))
        
        ping_ms = None
        try:
            t0 = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.google.com", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    await resp.text()
            ping_ms = int((time.time() - t0) * 1000)
        except Exception as e:
            logger.debug(f"[PING ERROR] {e}")
            ping_ms = None

        stats_title = t(user_lang, "stats_title")
        stats_uptime = t(user_lang, "stats_uptime", uptime=uptime_str)
        stats_ping = t(user_lang, "stats_ping", ping=f'{ping_ms} ms' if ping_ms is not None else 'Nomaʼlum')
        stats_users = t(user_lang, "stats_users", count=user_count)
        stats_images = t(user_lang, "stats_images", count=gen_count)
        stats_donations = t(user_lang, "stats_donations", amount=donation_sum)
        
        text = (
            f"<b>{stats_title}</b>\n\n"
            f"{stats_uptime}\n"
            f"{stats_ping}\n"
            f"{stats_users}\n"
            f"{stats_images}\n"
            f"{stats_donations}\n\n"
            "<i>🔄 Avtomatik yangilanadi...</i>"
        )
        
        kb = [[InlineKeyboardButton(t(user_lang, "btn_back"), callback_data="show_info")]]
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.HTML
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            logger.warning(f"Stats update error: {e}")
            job.schedule_removal()
    except Exception as e:
        logger.error(f"Unexpected stats update error: {e}")
        job.schedule_removal()

async def stop_stats_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'stats_job' in context.chat_data:
        job = context.chat_data['stats_job']
        job.schedule_removal()
        del context.chat_data['stats_job']

# ---------------- Simple navigation handlers ----------------
async def back_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    await stop_stats_updates(update, context)
    if MAINTENANCE_MODE:
        lang_code = get_user_language(context, q.from_user.id)
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return
    user_rec = await get_user_record(context.application.bot_data["db_pool"], q.from_user.id)
    lang_code = user_rec["lang"] if user_rec and user_rec["lang"] else "en"
    context.user_data[USER_DATA_LANG] = lang_code
    text, kb = await send_main_panel(q.message.chat, lang_code, context.application.bot_data)
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except BadRequest:
        try:
            await q.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    if MAINTENANCE_MODE:
        lang_code = get_user_language(context, q.from_user.id)
        await q.edit_message_text(t(lang_code, "maintenance_message"))
        return
    lang_code = get_user_language(context, q.from_user.id)
    try:
        await q.edit_message_text(t(lang_code, "withdraw_soon"))
    except Exception:
        pass

# ---------------- Admin Panel ----------------
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    user_id = update.effective_user.id if update.effective_user else (update.callback_query.from_user.id if update.callback_query else 0)
    if user_id != ADMIN_ID:
        user_rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
        lang_code = user_rec["lang"] if user_rec and user_rec["lang"] else "en"
        context.user_data[USER_DATA_LANG] = lang_code
        text, kb = await send_main_panel(update.effective_chat if update.effective_message else update.callback_query.message.chat, lang_code, context.application.bot_data)
        if update.callback_query:
            q = update.callback_query
            await q.answer()
            await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    if update.callback_query:
        q = update.callback_query
        await q.answer()
        chat = q.message.chat
    else:
        q = None
        chat = update.effective_chat

    lang_code = get_user_language(context, user_id)
    admin_title = t(lang_code, "admin_panel_title")
    btn_broadcast = t(lang_code, "btn_admin_broadcast")
    btn_ban = t(lang_code, "btn_admin_ban")
    btn_unban = t(lang_code, "btn_admin_unban")
    btn_user_info = t(lang_code, "btn_admin_user_info")
    btn_maintenance = t(lang_code, "btn_admin_toggle_maintenance")
    btn_referrals = t(lang_code, "btn_admin_get_referrals")
    btn_back = t(lang_code, "btn_back")
    
    text = f"<b>{admin_title}</b>"
    kb = [
        [InlineKeyboardButton(btn_broadcast, callback_data="admin_broadcast")],
        [InlineKeyboardButton(btn_ban, callback_data="admin_ban")],
        [InlineKeyboardButton(btn_unban, callback_data="admin_unban")],
        [InlineKeyboardButton(btn_user_info, callback_data="admin_user_info")],
        [InlineKeyboardButton(btn_referrals, callback_data="admin_referrals")],
        [InlineKeyboardButton(btn_maintenance, callback_data="admin_maintenance")],
        [InlineKeyboardButton(btn_back, callback_data="back_main")]
    ]
    
    if q:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else:
        await chat.send_message(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = get_user_language(context, q.from_user.id)
    cancel_btn = InlineKeyboardButton(t(lang_code, "btn_cancel"), callback_data="admin_panel")
    await q.message.reply_text(t(lang_code, "enter_broadcast_message"), reply_markup=InlineKeyboardMarkup([[cancel_btn]]))
    return ADMIN_BROADCAST_MESSAGE

async def admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.text and message.text.strip().lower() in ["/cancel", "cancel", "bekor qilish"]:
        lang_code = get_user_language(context, update.effective_user.id)
        await message.reply_text(t(lang_code, "operation_cancelled"))
        text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
        await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        user_ids = await conn.fetch("SELECT id FROM users WHERE is_banned = FALSE")
    
    lang_code = get_user_language(context, update.effective_user.id)
    success_count = 0
    fail_count = 0
    for record in user_ids:
        user_id = record['id']
        try:
            if message.text:
                await context.bot.send_message(user_id, message.text, parse_mode=ParseMode.HTML if message.parse_mode else None)
            elif message.photo:
                caption = message.caption or ""
                await context.bot.send_photo(user_id, message.photo[-1].file_id, caption=caption, parse_mode=ParseMode.HTML if message.parse_mode else None)
            elif message.document:
                caption = message.caption or ""
                await context.bot.send_document(user_id, message.document.file_id, caption=caption, parse_mode=ParseMode.HTML if message.parse_mode else None)
            elif message.video:
                caption = message.caption or ""
                await context.bot.send_video(user_id, message.video.file_id, caption=caption, parse_mode=ParseMode.HTML if message.parse_mode else None)
            elif message.audio:
                caption = message.caption or ""
                await context.bot.send_audio(user_id, message.audio.file_id, caption=caption, parse_mode=ParseMode.HTML if message.parse_mode else None)
            else:
                pass
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {e}")
            fail_count += 1
            
    await message.reply_text(f"📢 Xabar yuborildi!\n✅ Muvaffaqiyatli: {success_count}\n❌ Muvaffaqiyatsiz: {fail_count}")
    text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = get_user_language(context, q.from_user.id)
    cancel_btn = InlineKeyboardButton(t(lang_code, "btn_cancel"), callback_data="admin_panel")
    await q.message.reply_text(t(lang_code, "enter_user_id_to_ban"), reply_markup=InlineKeyboardMarkup([[cancel_btn]]))
    return ADMIN_BAN_USER_ID

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel", "bekor qilish"]:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "operation_cancelled"))
        text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    txt = update.message.text.strip()
    try:
        user_id = int(txt)
    except ValueError:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "invalid_user_id"))
        return ADMIN_BAN_USER_ID

    pool = context.application.bot_data["db_pool"]
    user_rec = await get_user_record(pool, user_id)
    if not user_rec:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "user_not_found"))
        return ConversationHandler.END

    is_already_banned = user_rec.get("is_banned")
    if is_already_banned:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "user_already_banned", user_id=user_id))
    else:
        success = await ban_user(pool, user_id)
        lang_code = get_user_language(context, update.effective_user.id)
        if success:
            await update.message.reply_text(t(lang_code, "user_banned", user_id=user_id))
        else:
            await update.message.reply_text(t(lang_code, "error_try_again"))
    
    text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = get_user_language(context, q.from_user.id)
    cancel_btn = InlineKeyboardButton(t(lang_code, "btn_cancel"), callback_data="admin_panel")
    await q.message.reply_text(t(lang_code, "enter_user_id_to_unban"), reply_markup=InlineKeyboardMarkup([[cancel_btn]]))
    return ADMIN_UNBAN_USER_ID

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel", "bekor qilish"]:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "operation_cancelled"))
        text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    txt = update.message.text.strip()
    try:
        user_id = int(txt)
    except ValueError:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "invalid_user_id"))
        return ADMIN_UNBAN_USER_ID

    pool = context.application.bot_data["db_pool"]
    user_rec = await get_user_record(pool, user_id)
    if not user_rec:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "user_not_found"))
        return ConversationHandler.END

    is_banned = user_rec.get("is_banned")
    if not is_banned:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "user_not_banned", user_id=user_id))
    else:
        success = await unban_user(pool, user_id)
        lang_code = get_user_language(context, update.effective_user.id)
        if success:
            await update.message.reply_text(t(lang_code, "user_unbanned", user_id=user_id))
        else:
            await update.message.reply_text(t(lang_code, "error_try_again"))
    
    text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_user_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = get_user_language(context, q.from_user.id)
    cancel_btn = InlineKeyboardButton(t(lang_code, "btn_cancel"), callback_data="admin_panel")
    await q.message.reply_text(t(lang_code, "enter_user_id_for_info"), reply_markup=InlineKeyboardMarkup([[cancel_btn]]))
    return ADMIN_USER_INFO_ID

async def admin_user_info_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.strip().lower() in ["/cancel", "cancel", "bekor qilish"]:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "operation_cancelled"))
        text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    txt = update.message.text.strip()
    try:
        user_id = int(txt)
    except ValueError:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "invalid_user_id"))
        return ADMIN_USER_INFO_ID

    pool = context.application.bot_data["db_pool"]
    user_rec = await get_user_record(pool, user_id)
    if not user_rec:
        lang_code = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(lang_code, "user_not_found"))
        return ConversationHandler.END

    async with pool.acquire() as conn:
        refs_count = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id=$1", user_id)
    refs_count = int(refs_count or 0)
    
    lang_code_admin = get_user_language(context, update.effective_user.id)
    lang_code_user = user_rec.get("lang") or "en"
    
    info_title = t(lang_code_admin, "user_info_title")
    info_details = t(
        lang_code_admin, "user_info_details",
        id=user_rec['id'],
        username=user_rec['username'] or "N/A",
        first_seen=user_rec['first_seen'].strftime('%Y-%m-%d %H:%M:%S') if user_rec['first_seen'] else "N/A",
        last_seen=user_rec['last_seen'].strftime('%Y-%m-%d %H:%M:%S') if user_rec['last_seen'] else "N/A",
        lang=user_rec['lang'] or "N/A",
        balance=user_rec['balance'] or 0,
        referral_count=refs_count
    )
    
    text = f"<b>{info_title}</b>\n\n{info_details}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    text, kb = await send_main_panel(update.effective_chat, lang_code_admin, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_get_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    # Foydalanuvchi ID'sini olish
    user_id = q.from_user.id 
    pool = context.application.bot_data["db_pool"]
    
    async with pool.acquire() as conn:
        # Avval foydalanuvchi haqida ma'lumot olish
        user_rec = await get_user_record(pool, user_id)
        if not user_rec:
             lang_code = get_user_language(context, user_id)
             await q.message.reply_text(t(lang_code, "user_not_found"))
             return
        # Keyin uning referallarini topish
        rows = await conn.fetch("SELECT invited_id FROM referrals WHERE inviter_id=$1", user_id)
        
    if not rows:
        lang_code = get_user_language(context, user_id)
        await q.message.reply_text(t(lang_code, "no_referrals_found"))
        return
        
    lang_code = get_user_language(context, user_id)
    referrals_title = t(lang_code, "referrals_title", user_id=user_id)
    text = f"<b>{referrals_title}</b>\n\n"
    
    for i, row in enumerate(rows, 1):
        invited_id = row['invited_id']
        invited_rec = await get_user_record(pool, invited_id)
        username = invited_rec['username'] if invited_rec and invited_rec['username'] else "N/A"
        text += f"{i}. ID: {invited_id}, Username: @{username}\n"
        
    await q.message.reply_text(text, parse_mode=ParseMode.HTML)

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    lang_code = get_user_language(context, q.from_user.id)
    if MAINTENANCE_MODE:
        await q.edit_message_text(t(lang_code, "maintenance_enabled"))
    else:
        await q.edit_message_text(t(lang_code, "maintenance_disabled"))

# ---------------- Error handler ----------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            lang_code = get_user_language(context, update.effective_user.id if update.effective_user else 0)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=t(lang_code, "error_try_again"))
    except Exception:
        pass

# ---------------- Startup ----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
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
    app.add_handler(CallbackQueryHandler(realtime_stats_handler, pattern=r"realtime_stats"))
    app.add_handler(CallbackQueryHandler(my_account_handler, pattern=r"my_account"))

    # Donate conversation
    donate_conv = ConversationHandler(
        entry_points=[CommandHandler("donate", donate_start), CallbackQueryHandler(donate_start, pattern="donate_custom")],
        states={
            DONATE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(donate_conv)

    # Payments handlers
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Generate callback
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"count_\d+"))

    # private plain text -> prompt handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))

    # Admin Panel Handlers
    app.add_handler(CallbackQueryHandler(admin_panel_handler, pattern=r"admin_panel"))
    
    # Admin Broadcast Conversation
    admin_broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern=r"admin_broadcast")],
        states={
            ADMIN_BROADCAST_MESSAGE: [MessageHandler(~filters.COMMAND, admin_broadcast_message)]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(admin_broadcast_conv)
    
    # Admin Ban Conversation
    admin_ban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_ban_start, pattern=r"admin_ban")],
        states={
            ADMIN_BAN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_user)]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(admin_ban_conv)
    
    # Admin Unban Conversation
    admin_unban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_unban_start, pattern=r"admin_unban")],
        states={
            ADMIN_UNBAN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_unban_user)]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(admin_unban_conv)
    
    # Admin User Info Conversation
    admin_user_info_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_user_info_start, pattern=r"admin_user_info")],
        states={
            ADMIN_USER_INFO_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_user_info_by_id)]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(admin_user_info_conv)
    
    # Admin Get Referrals (simple callback)
    app.add_handler(CallbackQueryHandler(admin_get_referrals, pattern=r"admin_referrals"))
    
    # Admin Toggle Maintenance
    app.add_handler(CallbackQueryHandler(admin_toggle_maintenance, pattern=r"admin_maintenance"))

    # errors
    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
``
