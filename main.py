import logging
import aiohttp
import asyncio
import telegram
import httpx
import re
import os
import json
import random
import uuid
import time
import threading
from datetime import datetime, timezone, timedelta
from collections import ChainMap

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

logging.getLogger("httpx").setLevel(logging.WARNING)
# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# ---------------- STATES ----------------
BAN_STATE = 1
UNBAN_STATE = 2
BROADCAST_STATE = 3
DONATE_WAITING_AMOUNT = 4
# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))
MANDATORY_CHANNELS = json.loads(os.getenv("MANDATORY_CHANNELS", "[]"))
if not MANDATORY_CHANNELS:
    MANDATORY_CHANNELS = [{"username": "@Digen_AI_News", "id": -1003170509666}]
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
LANGUAGE_SELECT, DONATE_WAITING_AMOUNT = range(2)

# ---------------- Til sozlamalari ----------------
# Yangilangan: Yangi matn kalitlari qo'shildi
LANGUAGES = {
    # --- O'zbekcha (Mavjud, lekin to'liq qayta tekshirildi) ---
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
        "get_no_args_group": "❌ Guruhda /get dan keyin prompt yozing. Misol: /get futuristik shahar",
"get_no_args_private": "✍️ Iltimos, rasm uchun matn yozing.",
"generating_progress": "🔄 Rasm yaratilmoqda... {bar} {percent}%",
"image_delayed": "⚠️ Rasm tayyorlanish biroz kechikmoqda. Keyinroq qayta urinib ko'ring.",
"donate_title": "💖 Botga Yordam",
"donate_description": "Botni qo'llab-quvvatlash uchun Stars yuboring.",
"done": "✅ Tayyor!",
"error_occurred": "⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.",
"choose_action_prompt": "Quyidagilardan birini tanlang:",
"your_message_label": "💬 Sizning xabaringiz:",
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
        "your_prompt_label": "🖌 Sizning matningiz:",
        "sub_prompt": "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
        "sub_check": "✅ Obunani tekshirish",
        "sub_url_text": "🔗 Kanalga obuna bo‘lish",
        "sub_thanks": "✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.",
        "sub_still_not": "⛔ Hali ham obuna bo‘lmagansiz. Obuna bo‘lib, qayta tekshiring.",
        "lang_changed": "✅ Til o'zgartirildi: {lang}",
            "gen_button_short": "Rasm Yaratish",
    "ai_button_short": "AI bilan Suhbat",
        "settings_menu_title": "⚙️ Sozlamalar",
"select_image_model_button": "🖼 Rasm modelini tanlash",
"back_to_main_button": "🔙 Asosiy menyuga qaytish",

"fake_lab_generating": "🔄 Soxta shaxs yaratilmoqda...\n\n👤 Bu shaxs **haqiqiy emas** — AI tomonidan yaratilgan!\n\n⏳ Iltimos, kuting...",
"fake_lab_ready_caption": "👤 **Bu shaxs HAQIQIY EMAS!**\n🤖 Sun’iy intellekt tomonidan yaratilgan.\n\n🔄 **Yangilash** orqali yangi rasm oling.",
"fake_lab_refreshing": "🔄 **Yangi rasm yuklanmoqda...**\n⏳ Iltimos, kuting...",
"fake_lab_error": "⚠️ **Xatolik yuz berdi.**\nIltimos, qayta urinib ko‘ring.",

"progress_step_10": "🧠 Prompt tahlil qilinmoqda...",
"progress_step_25": "🎨 Model tanlanmoqda...",
"progress_step_40": "🌈 Ranglar va kompozitsiya tuzilmoqda...",
"progress_step_60": "💡 Yorug‘lik va soyalar muvozanatlashmoqda...",
"progress_step_80": "🧩 Tafsilotlar yakunlanmoqda...",
"progress_step_100": "✅ Natija tayyorlanmoqda...",

"stats_title": "🤖 Digen AI Statistikasi",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Jami rasmlar",
"stats_today": "📆 Bugun",
"stats_users": "👥 Foydalanuvchilar",
"stats_new_30d": "🆕 So‘nggi 30 kun",
"stats_your_images": "👤 Siz yaratganlar",
"stats_refresh_button": "🔄 Yangilash",
        "select_lang": "🌐 Iltimos, tilni tanlang:",
        "ai_response_header": "💬 AI javob:",
        "image_ready_header": "🎨 Rasm tayyor!",
        "image_prompt_label": "📝 Prompt:",
        "image_count_label": "🔢 Soni:",
        "image_model_label": "🖼 Model:",
        "image_time_label": "⏰ Vaqt (UTC+5):",
        "image_elapsed_label": "⏱ Yaratish uchun ketgan vaqt:",
        "choose_action": "Quyidagilardan birini tanlang:",
        "your_message": "💬 Sizning xabaringiz:",
        "admin_new_generation": "🎨 *Yangi generatsiya!*",
        "admin_user": "👤 *Foydalanuvchi:*",
        "admin_prompt": "📝 *Prompt:*",
        "admin_count": "🔢 *Soni:*",
        "admin_image_id": "🆔 *Image ID:*",
        "admin_time": "⏰ *Vaqt \\(UTC\\+5\\):*",
        "back_to_main_button": "⬅️ Orqaga",
    },
    # --- Inglizcha (🇺🇸) ---
    "en": {
        "flag": "🇺🇸",
        "name": "English",
        "welcome": "👋 Hello!\n\nI create images for you using AI.",
        "gen_button": "🎨 Generate Image",
        "ai_button": "💬 Chat with AI",
        "donate_button": "💖 Donate",
        "lang_button": "🌐 Change Language",
        "prompt_text": "✍️ Now send the text to generate an image.",
        "ai_prompt_text": "✍️ Write your question to start a conversation.",
        "select_count": "🔢 How many images to generate?",
        "generating": "🔄 Generating image ({count})... ⏳",
        "success": "✅ Image ready! 📸",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ In groups, write a prompt after /get. Example: /get futuristic city",
"get_no_args_private": "✍️ Please enter a text prompt for the image.",
"generating_progress": "🔄 Generating image... {bar} {percent}%",
"image_delayed": "⚠️ The image is taking a while to prepare. Please try again later.",
"donate_title": "💖 Support the Bot",
"donate_description": "Send Stars to support the bot.",
"done": "✅ Done!",
        "settings_menu_title": "⚙️ Settings",
"select_image_model_button": "🖼 Select Image Model",
"back_to_main_button": "🔙 Back",

"fake_lab_generating": "🔄 Generating a fake person...\n\n👤 This person is **not real** — created by AI!\n\n⏳ Please wait...",
"fake_lab_ready_caption": "👤 **This person is NOT REAL!**\n🤖 Generated by artificial intelligence.\n\n🔄 Use **Refresh** to get a new image.",
"fake_lab_refreshing": "🔄 **Loading a new image...**\n⏳ Please wait...",
"fake_lab_error": "⚠️ **An error occurred.**\nPlease try again.",

"progress_step_10": "🧠 Analyzing prompt...",
"progress_step_25": "🎨 Selecting model...",
"progress_step_40": "🌈 Building colors and composition...",
"progress_step_60": "💡 Balancing lighting and shadows...",
"progress_step_80": "🧩 Finalizing details...",
"progress_step_100": "✅ Preparing for delivery...",
"back_to_main_button": "⬅️ Back",
"stats_title": "🤖 Digen AI Statistics",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Total images",
"stats_today": "📆 Today",
"stats_users": "👥 Users",
"stats_new_30d": "🆕 Last 30 days",
"stats_your_images": "👤 You generated",
"stats_refresh_button": "🔄 Refresh",
"error_occurred": "⚠️ An error occurred. Please try again.",
"choose_action_prompt": "Choose one of the following:",
"your_message_label": "💬 Your message:",
         "gen_button_short": "Generate Image",
    "ai_button_short": "Chat with AI",
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
        "your_prompt_label": "🖌 Your text:",
        "sub_prompt": "⛔ Subscribe to our channel to use the bot!",
        "sub_check": "✅ Check Subscription",
        "sub_url_text": "🔗 Subscribe to Channel",
        "sub_thanks": "✅ Thank you! You are subscribed. You can now use the bot.",
        "sub_still_not": "⛔ You are still not subscribed. Subscribe and check again.",
        "lang_changed": "✅ Language changed to: {lang}",
        "select_lang": "🌐 Please select language:",
        "ai_response_header": "💬 AI Response:",
        "image_ready_header": "🎨 Image is ready!",
        "image_prompt_label": "📝 Prompt:",
        "image_count_label": "🔢 Count:",
        "image_time_label": "⏰ Time (UTC+5):",
        "image_elapsed_label": "⏱ Time taken to create:",
        "choose_action": "Choose one of the following:",
        "your_message": "💬 Your message:",
        "admin_new_generation": "🎨 *New Generation!*",
        "admin_user": "👤 *User:*",
        "admin_prompt": "📝 *Prompt:*",
        "admin_count": "🔢 *Count:*",
        "admin_image_id": "🆔 *Image ID:*",
        "admin_time": "⏰ *Time \\(UTC\\+5\\):*",
    },
    # --- Ruscha (🇷🇺) ---
    "ru": {
        "flag": "🇷🇺",
        "name": "Русский",
        "welcome": "👋 Привет!\n\nЯ создаю для вас изображения с помощью ИИ.",
        "gen_button": "🎨 Создать изображение",
        "ai_button": "💬 Чат с ИИ",
        "donate_button": "💖 Поддержать",
        "lang_button": "🌐 Изменить язык",
        "prompt_text": "✍️ Теперь отправьте текст для создания изображения.",
        "ai_prompt_text": "✍️ Напишите свой вопрос, чтобы начать разговор.",
        "select_count": "🔢 Сколько изображений создать?",
        "generating": "🔄 Создаю изображение ({count})... ⏳",
        "success": "✅ Изображение готово! 📸",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ В группах напишите промпт после /get. Пример: /get футуристический город",
"get_no_args_private": "✍️ Пожалуйста, введите текст для генерации изображения.",
"generating_progress": "🔄 Создаю изображение... {bar} {percent}%",
"image_delayed": "⚠️ Подготовка изображения занимает больше времени. Попробуйте позже.",
"donate_title": "💖 Поддержать бота",
        "back_to_main_button": "⬅️ Back",
"donate_description": "Отправьте Stars, чтобы поддержать бота.",
"done": "✅ Готово!",
"error_occurred": "⚠️ Произошла ошибка. Попробуйте снова.",
"choose_action_prompt": "Выберите один из вариантов:",
"your_message_label": "💬 Ваше сообщение:",
          "gen_button_short": "Создать изображение",
    "ai_button_short": "Чат с ИИ",
        "settings_menu_title": "⚙️ Настройки",
"select_image_model_button": "🖼 Выбрать модель изображения",
"back_to_main_button": "🔙 Назад в главное меню",

"fake_lab_generating": "🔄 Создание фейкового человека...\n\n👤 Этот человек **нереален** — создан искусственным интеллектом!\n\n⏳ Пожалуйста, подождите...",
"fake_lab_ready_caption": "👤 **Этот человек НЕ НАСТОЯЩИЙ!**\n🤖 Сгенерирован искусственным интеллектом.\n\n🔄 Используйте **Обновить**, чтобы получить новое изображение.",
"fake_lab_refreshing": "🔄 **Загружается новое изображение...**\n⏳ Пожалуйста, подождите...",
"fake_lab_error": "⚠️ **Произошла ошибка.**\nПожалуйста, попробуйте снова.",

"progress_step_10": "🧠 Анализ промпта...",
"progress_step_25": "🎨 Выбор модели...",
"progress_step_40": "🌈 Создание цветов и композиции...",
"progress_step_60": "💡 Балансировка света и теней...",
"progress_step_80": "🧩 Завершение деталей...",
"progress_step_100": "✅ Подготовка к выдаче...",

"stats_title": "🤖 Статистика Digen AI",
"stats_ping": "⚡ Пинг",
"stats_total_images": "🖼 Всего изображений",
"stats_today": "📆 Сегодня",
"stats_users": "👥 Пользователи",
"stats_new_30d": "🆕 Последние 30 дней",
"stats_your_images": "👤 Вы создали",
"stats_refresh_button": "🔄 Обновить",
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
        "your_prompt_label": "🖌 Ваш текст:",
        "sub_prompt": "⛔ Чтобы пользоваться ботом, подпишитесь на наш канал!",
        "sub_check": "✅ Проверить подписку",
        "sub_url_text": "🔗 Подписаться на канал",
        "sub_thanks": "✅ Спасибо! Вы подписаны. Теперь вы можете пользоваться ботом.",
        "sub_still_not": "⛔ Вы все еще не подписаны. Подпишитесь и проверьте снова.",
        "lang_changed": "✅ Язык изменен: {lang}",
        "select_lang": "🌐 Пожалуйста, выберите язык:",
        "ai_response_header": "💬 Ответ ИИ:",
        "image_ready_header": "🎨 Изображение готово!",
        "image_prompt_label": "📝 Текст:",
        "image_count_label": "🔢 Количество:",
        "image_time_label": "⏰ Время (UTC+5):",
        "image_elapsed_label": "⏱ Время создания:",
        "choose_action": "Выберите один из вариантов:",
        "your_message": "💬 Ваше сообщение:",
        "admin_new_generation": "🎨 *Новая генерация!*",
        "admin_user": "👤 *Пользователь:*",
        "admin_prompt": "📝 *Текст:*",
        "admin_count": "🔢 *Количество:*",
        "admin_image_id": "🆔 *ID изображения:*",
        "admin_time": "⏰ *Время \\(UTC\\+5\\):*",
    },
    # --- Indonezcha (🇮🇩) ---
    "id": {
        "flag": "🇮🇩",
        "name": "Bahasa Indonesia",
        "welcome": "👋 Halo!\n\nSaya membuat gambar untuk Anda menggunakan AI.",
        "gen_button": "🎨 Buat Gambar",
        "ai_button": "💬 Ngobrol dengan AI",
        "donate_button": "💖 Donasi",
        "lang_button": "🌐 Ganti Bahasa",
        "image_model_label": "🖼 Model:",
        "settings_menu_title": "⚙️ Pengaturan",
"select_image_model_button": "🖼 Pilih Model Gambar",
"back_to_main_button": "🔙 Kembali",
"fake_lab_generating": "🔄 Membuat wajah AI...\n\n👤 Orang ini **bukan nyata** — dibuat oleh AI!\n\n⏳ Silakan tunggu...",
"fake_lab_ready_caption": "👤 **Orang ini BUKAN NYATA!**\n🤖 Dihasilkan oleh kecerdasan buatan.\n\n🔄 Tekan **Segarkan** untuk gambar baru.",
"fake_lab_refreshing": "🔄 **Memuat gambar baru...**\n⏳ Mohon tunggu...",
"fake_lab_error": "⚠️ **Terjadi kesalahan.**\nSilakan coba lagi.",
"progress_step_10": "🧠 Menganalisis prompt...",
"progress_step_25": "🎨 Memilih model...",
        "back_to_main_button": "⬅️ Back",
"progress_step_40": "🌈 Membangun warna & komposisi...",
"progress_step_60": "💡 Menyeimbangkan cahaya & bayangan...",
"progress_step_80": "🧩 Menyelesaikan detail...",
"progress_step_100": "✅ Menyiapkan pengiriman...",
"stats_title": "🤖 Statistik Digen AI",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Total gambar",
"stats_today": "📆 Hari ini",
"stats_users": "👥 Pengguna",
"stats_new_30d": "🆕 30 hari terakhir",
"stats_your_images": "👤 Gambar yang Anda buat",
"stats_refresh_button": "🔄 Segarkan",
        "prompt_text": "✍️ Sekarang kirim teks untuk membuat gambar.",
        "ai_prompt_text": "✍️ Tulis pertanyaan Anda untuk memulai percakapan.",
        "select_count": "🔢 Berapa banyak gambar yang akan dibuat?",
        "generating": "🔄 Membuat gambar ({count})... ⏳",
        "success": "✅ Gambar siap! 📸",
        "get_no_args_group": "❌ Di grup, tulis prompt setelah /get. Contoh: /get kota futuristik",
"get_no_args_private": "✍️ Harap masukkan teks untuk membuat gambar.",
"generating_progress": "🔄 Membuat gambar... {bar} {percent}%",
"image_delayed": "⚠️ Pembuatan gambar sedang tertunda. Coba lagi nanti.",
"donate_title": "💖 Dukung Bot",
"donate_description": "Kirim Stars untuk mendukung bot.",
"done": "✅ Selesai!",
"error_occurred": "⚠️ Terjadi kesalahan. Silakan coba lagi.",
"choose_action_prompt": "Pilih salah satu opsi berikut:",
"your_message_label": "💬 Pesan Anda:",
        "error": "⚠️ Terjadi kesalahan. Silakan coba lagi.",
        "donate_prompt": "💰 Silakan masukkan jumlah yang ingin Anda kirim (1–100000):",
        "donate_invalid": "❌ Harap masukkan angka bulat antara 1 dan 100000.",
        "donate_thanks": "✅ Terima kasih, {name}! Anda mengirim {stars} Stars.",
        "refund_success": "✅ {stars} Stars berhasil dikembalikan ke pengguna {user_id}.",
        "refund_error": "❌ Kesalahan: {error}",
        "no_permission": "⛔ Anda tidak memiliki izin.",
        "usage_refund": "Penggunaan: /refund <user_id> <donation_id>",
        "not_found": "❌ Tidak ditemukan atau data tidak valid.",
        "no_charge_id": "❌ Pembayaran ini tidak memiliki charge_id (pembayaran lama).",
        "your_prompt_label": "🖌 Teks Anda:",
        "sub_prompt": "⛔ Berlangganan saluran kami untuk menggunakan bot!",
        "sub_check": "✅ Periksa Langganan",
        "sub_url_text": "🔗 Berlangganan Saluran",
        "sub_thanks": "✅ Terima kasih! Anda telah berlangganan. Sekarang Anda dapat menggunakan bot.",
        "sub_still_not": "⛔ Anda masih belum berlangganan. Berlangganan dan periksa lagi.",
        "lang_changed": "✅ Bahasa diubah ke: {lang}",
        "select_lang": "🌐 Silakan pilih bahasa:",
        "ai_response_header": "💬 Jawaban AI:",
        "image_ready_header": "🎨 Gambar siap!",
        "image_prompt_label": "📝 Teks:",
        "image_count_label": "🔢 Jumlah:",
        "image_time_label": "⏰ Waktu (UTC+5):",
        "image_elapsed_label": "⏱ Waktu yang dibutuhkan untuk membuat:",
        "choose_action": "Pilih salah satu dari berikut ini:",
        "your_message": "💬 Pesan Anda:",
        "admin_new_generation": "🎨 *Generasi Baru!*",
        "admin_user": "👤 *Pengguna:*",
        "admin_prompt": "📝 *Teks:*",
        "admin_count": "🔢 *Jumlah:*",
        "admin_image_id": "🆔 *ID Gambar:*",
        "admin_time": "⏰ *Waktu \\(UTC\\+5\\):*",
    },
    # --- Litvacha (🇱🇹) ---
    "lt": {
        "flag": "🇱🇹",
        "name": "Lietuvių",
        "welcome": "👋 Sveiki!\n\nAš kuriu jums paveikslėlius naudodamas dirbtinį intelektą.",
        "gen_button": "🎨 Generuoti paveikslėlį",
        "settings_menu_title": "⚙️ Nustatymai",
"select_image_model_button": "🖼 Pasirinkti vaizdo modelį",
"back_to_main_button": "🔙 Atgal",
"back_to_main_button": "⬅️ Back",
"fake_lab_generating": "🔄 Generuojamas netikras asmuo...\n\n👤 Šis asmuo **nėra tikras** — sukurtas dirbtinio intelekto!\n\n⏳ Prašome palaukti...",
"fake_lab_ready_caption": "👤 **Šis asmuo NĖRA TIKRAS!**\n🤖 Sukurtas dirbtinio intelekto.\n\n🔄 Naudokite **Atnaujinti**, kad gautumėte naują vaizdą.",
"fake_lab_refreshing": "🔄 **Įkeliamas naujas vaizdas...**\n⏳ Prašome palaukti...",
"fake_lab_error": "⚠️ **Įvyko klaida.**\nPabandykite dar kartą.",

"progress_step_10": "🧠 Analizuojamas raginimas...",
"progress_step_25": "🎨 Pasirenkamas modelis...",
"progress_step_40": "🌈 Kuriamos spalvos ir kompozicija...",
"progress_step_60": "💡 Derinamas apšvietimas ir šešėliai...",
"progress_step_80": "🧩 Užbaigiamos detalės...",
"progress_step_100": "✅ Ruošiama pristatymui...",

"stats_title": "🤖 Digen AI statistika",
"stats_ping": "⚡ Vėlinimas",
"stats_total_images": "🖼 Iš viso vaizdų",
"stats_today": "📆 Šiandien",
"stats_users": "👥 Naudotojai",
"stats_new_30d": "🆕 Paskutinės 30 dienų",
"stats_your_images": "👤 Jūsų sukurta",
"stats_refresh_button": "🔄 Atnaujinti",
        "ai_button": "💬 Kalbėtis su AI",
        "donate_button": "💖 Paaukoti",
        "image_model_label": "🖼 Model:",
        "lang_button": "🌐 Pakeisti kalbą",
        "prompt_text": "✍️ Dabar išsiųskite tekstą, kad sugeneruotumėte paveikslėlį.",
        "ai_prompt_text": "✍️ Parašykite savo klausimą, kad pradėtumėte pokalbį.",
        "select_count": "🔢 Kiek paveikslėlių generuoti?",
        "generating": "🔄 Generuojamas paveikslėlis ({count})... ⏳",
        "success": "✅ Paveikslėlis paruoštas! 📸",
        "get_no_args_group": "❌ Grupėse po /get įveskite užduotį. Pavyzdys: /get futuristinis miestas",
"get_no_args_private": "✍️ Įveskite tekstą paveikslėlio kūrimui.",
"generating_progress": "🔄 Kuriamas paveikslėlis... {bar} {percent}%",
"image_delayed": "⚠️ Paveikslėlio paruošimas užtrunka. Bandykite vėliau.",
"donate_title": "💖 Paremkite botą",
"donate_description": "Siųskite Stars, kad paremtumėte botą.",
"done": "✅ Atlikta!",
"error_occurred": "⚠️ Įvyko klaida. Bandykite dar kartą.",
"choose_action_prompt": "Pasirinkite vieną iš šių parinkčių:",
"your_message_label": "💬 Jūsų žinutė:",
        "donate_prompt": "💰 Įveskite sumą, kurią norite išsiųsti (1–100000):",
        "donate_invalid": "❌ Įveskite sveikąjį skaičių nuo 1 iki 100000.",
        "donate_thanks": "✅ Ačiū, {name}! Jūs išsiuntėte {stars} Stars.",
        "refund_success": "✅ {stars} Stars sėkmingai grąžinti vartotojui {user_id}.",
        "refund_error": "❌ Klaida: {error}",
        "no_permission": "⛔ Jūs neturite leidimo.",
        "usage_refund": "Naudojimas: /refund <user_id> <donation_id>",
        "not_found": "❌ Nerasta arba neteisingi duomenys.",
        "no_charge_id": "❌ Šis mokėjimas neturi charge_id (senas mokėjimas).",
        "your_prompt_label": "🖌 Jūsų tekstas:",
        "sub_prompt": "⛔ Prenumeruokite mūsų kanalą, kad galėtumėte naudotis botu!",
        "sub_check": "✅ Patikrinti prenumeratą",
        "sub_url_text": "🔗 Prenumeruoti kanalą",
        "sub_thanks": "✅ Ačiū! Jūs prenumeruojate. Dabar galite naudotis botu.",
        "sub_still_not": "⛔ Jūs vis dar nesate prenumeruojantis. Prenumeruokite ir patikrinkite dar kartą.",
        "lang_changed": "✅ Kalba pakeista į: {lang}",
        "select_lang": "🌐 Pasirinkite kalbą:",
        "ai_response_header": "💬 AI atsakymas:",
        "image_ready_header": "🎨 Paveikslėlis paruoštas!",
        "image_prompt_label": "📝 Užduotis:",
        "image_count_label": "🔢 Kiekis:",
        "image_time_label": "⏰ Laikas (UTC+5):",
        "image_elapsed_label": "⏱ Laikas, praleistas kūrimui:",
        "choose_action": "Pasirinkite vieną iš šių parinkčių:",
        "your_message": "💬 Jūsų žinutė:",
        "admin_new_generation": "🎨 *Nauja generacija!*",
        "admin_user": "👤 *Vartotojas:*",
        "admin_prompt": "📝 *Užduotis:*",
        "admin_count": "🔢 *Kiekis:*",
        "admin_image_id": "🆔 *Paveikslėlio ID:*",
        "admin_time": "⏰ *Laikas \\(UTC\\+5\\):*",
    },
    # --- Ispancha (Meksika) (🇲🇽) ---
    "esmx": {
        "flag": "🇲🇽",
        "name": "Español (México)",
        "welcome": "👋 ¡Hola!\n\nCreo imágenes para ti usando IA.",
        "gen_button": "🎨 Generar Imagen",
        "ai_button": "💬 Chatear con IA",
        "donate_button": "💖 Donar",
        "lang_button": "🌐 Cambiar Idioma",
        "image_model_label": "🖼 Model:",
        "settings_menu_title": "⚙️ Configuración",
"select_image_model_button": "🖼 Seleccionar modelo de imagen",
"back_to_main_button": "🔙 Volver",
        "back_to_main_button": "⬅️ Back",
"fake_lab_generating": "🔄 Generando persona falsa...\n\n👤 Esta persona **NO ES real** — creada por IA!\n\n⏳ Por favor, espera...",
"fake_lab_ready_caption": "👤 **¡Esta persona NO ES REAL!**\n🤖 Generada por inteligencia artificial.\n\n🔄 Usa **Actualizar** para obtener una nueva imagen.",
"fake_lab_refreshing": "🔄 **Cargando nueva imagen...**\n⏳ Por favor espera...",
"fake_lab_error": "⚠️ **Ocurrió un error.**\nPor favor, inténtalo de nuevo.",
"progress_step_10": "🧠 Analizando prompt...",
"progress_step_25": "🎨 Seleccionando modelo...",
"progress_step_40": "🌈 Construyendo colores y composición...",
"progress_step_60": "💡 Equilibrando luz y sombras...",
"progress_step_80": "🧩 Finalizando detalles...",
"progress_step_100": "✅ Preparando entrega...",
"stats_title": "🤖 Estadísticas de Digen AI",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Total de imágenes",
"stats_today": "📆 Hoy",
"stats_users": "👥 Usuarios",
"stats_new_30d": "🆕 Últimos 30 días",
"stats_your_images": "👤 Tú generaste",
"stats_refresh_button": "🔄 Actualizar",
        "prompt_text": "✍️ Ahora envía el texto para generar una imagen.",
        "ai_prompt_text": "✍️ Escribe tu pregunta para comenzar una conversación.",
        "select_count": "🔢 ¿Cuántas imágenes generar?",
        "generating": "🔄 Generando imagen ({count})... ⏳",
        "success": "✅ ¡Imagen lista! 📸",
        "get_no_args_group": "❌ En grupos, escribe un prompt después de /get. Ejemplo: /get ciudad futurista",
"get_no_args_private": "✍️ Por favor, escribe un texto para generar la imagen.",
"generating_progress": "🔄 Generando imagen... {bar} {percent}%",
"image_delayed": "⚠️ La imagen tarda en prepararse. Intenta más tarde.",
"donate_title": "💖 Apoya al Bot",
"donate_description": "Envía Stars para apoyar al bot.",
"done": "✅ ¡Listo!",
"error_occurred": "⚠️ Ocurrió un error. Por favor, inténtalo de nuevo.",
"choose_action_prompt": "Elige una de las siguientes opciones:",
"your_message_label": "💬 Tu mensaje:",
        "error": "⚠️ Ocurrió un error. Por favor, inténtalo de nuevo.",
        "donate_prompt": "💰 Por favor, ingresa la cantidad que deseas enviar (1–100000):",
        "donate_invalid": "❌ Por favor, ingresa un número entero entre 1 y 100000.",
        "donate_thanks": "✅ ¡Gracias, {name}! Enviaste {stars} Stars.",
        "refund_success": "✅ {stars} Stars devueltos exitosamente al usuario {user_id}.",
        "refund_error": "❌ Error: {error}",
        "no_permission": "⛔ No tienes permiso.",
        "usage_refund": "Uso: /refund <user_id> <donation_id>",
        "not_found": "❌ No encontrado o datos inválidos.",
        "no_charge_id": "❌ Este pago no tiene charge_id (pago antiguo).",
        "your_prompt_label": "🖌 Tu texto:",
        "sub_prompt": "⛔ ¡Suscríbete a nuestro canal para usar el bot!",
        "sub_check": "✅ Verificar Suscripción",
        "sub_url_text": "🔗 Suscribirse al Canal",
        "sub_thanks": "✅ ¡Gracias! Estás suscrito. Ahora puedes usar el bot.",
        "sub_still_not": "⛔ Aún no estás suscrito. Suscríbete y verifica de nuevo.",
        "lang_changed": "✅ Idioma cambiado a: {lang}",
        "select_lang": "🌐 Por favor, selecciona un idioma:",
        "ai_response_header": "💬 Respuesta de IA:",
        "image_ready_header": "🎨 ¡La imagen está lista!",
        "image_prompt_label": "📝 Texto:",
        "image_count_label": "🔢 Cantidad:",
        "image_time_label": "⏰ Hora (UTC+5):",
        "image_elapsed_label": "⏱ Tiempo empleado en crear:",
        "choose_action": "Elige una de las siguientes opciones:",
        "your_message": "💬 Tu mensaje:",
        "admin_new_generation": "🎨 *¡Nueva Generación!*",
        "admin_user": "👤 *Usuario:*",
        "admin_prompt": "📝 *Texto:*",
        "admin_count": "🔢 *Cantidad:*",
        "admin_image_id": "🆔 *ID de Imagen:*",
        "admin_time": "⏰ *Hora \\(UTC\\+5\\):*",
    },
    # --- Ispancha (Ispaniya) (🇪🇸) ---
    "eses": {
        "flag": "🇪🇸",
        "name": "Español (España)",
        "welcome": "👋 ¡Hola!\n\nCreo imágenes para ti usando IA.",
        "gen_button": "🎨 Generar Imagen",
        "ai_button": "💬 Chatear con IA",
        "donate_button": "💖 Donar",
        "lang_button": "🌐 Cambiar Idioma",
        "prompt_text": "✍️ Ahora envía el texto para generar una imagen.",
        "ai_prompt_text": "✍️ Escribe tu pregunta para comenzar una conversación.",
        "select_count": "🔢 ¿Cuántas imágenes generar?",
        "generating": "🔄 Generando imagen ({count})... ⏳",
        "success": "✅ ¡Imagen lista! 📸",
        "settings_menu_title": "⚙️ Configuración",
"select_image_model_button": "🖼 Seleccionar modelo de imagen",
"back_to_main_button": "🔙 Volver",
"fake_lab_generating": "🔄 Generando persona falsa...\n\n👤 Esta persona **NO ES real** — creada por IA!\n\n⏳ Por favor, espera...",
"fake_lab_ready_caption": "👤 **¡Esta persona NO ES REAL!**\n🤖 Generada por inteligencia artificial.\n\n🔄 Usa **Actualizar** para obtener una nueva imagen.",
"fake_lab_refreshing": "🔄 **Cargando nueva imagen...**\n⏳ Por favor espera...",
"fake_lab_error": "⚠️ **Ocurrió un error.**\nPor favor, inténtalo de nuevo.",
"progress_step_10": "🧠 Analizando prompt...",
"progress_step_25": "🎨 Seleccionando modelo...",
"progress_step_40": "🌈 Construyendo colores y composición...",
"progress_step_60": "💡 Equilibrando luz y sombras...",
"progress_step_80": "🧩 Finalizando detalles...",
"progress_step_100": "✅ Preparando entrega...",
"stats_title": "🤖 Estadísticas de Digen AI",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Total de imágenes",
"stats_today": "📆 Hoy",
"stats_users": "👥 Usuarios",
        "back_to_main_button": "⬅️ Back",
"stats_new_30d": "🆕 Últimos 30 días",
"stats_your_images": "👤 Tú generaste",
"stats_refresh_button": "🔄 Actualizar",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ En grupos, escribe un texto después de /get. Ejemplo: /get ciudad futurista",
"get_no_args_private": "✍️ Por favor, introduce un texto para generar la imagen.",
"generating_progress": "🔄 Generando imagen... {bar} {percent}%",
"image_delayed": "⚠️ La imagen tarda en prepararse. Inténtalo más tarde.",
"donate_title": "💖 Apoya al Bot",
"donate_description": "Envía Stars para apoyar al bot.",
"done": "✅ ¡Listo!",
"error_occurred": "⚠️ Ha ocurrido un error. Por favor, inténtalo de nuevo.",
"choose_action_prompt": "Elige una de las siguientes opciones:",
"your_message_label": "💬 Tu mensaje:",
        "error": "⚠️ Ha ocurrido un error. Por favor, inténtalo de nuevo.",
        "donate_prompt": "💰 Por favor, introduce la cantidad que deseas enviar (1–100000):",
        "donate_invalid": "❌ Por favor, introduce un número entero entre 1 y 100000.",
        "donate_thanks": "✅ ¡Gracias, {name}! Has enviado {stars} Stars.",
        "refund_success": "✅ {stars} Stars devueltos correctamente al usuario {user_id}.",
        "refund_error": "❌ Error: {error}",
        "no_permission": "⛔ No tienes permiso.",
        "usage_refund": "Uso: /refund <user_id> <donation_id>",
        "not_found": "❌ No encontrado o datos no válidos.",
        "no_charge_id": "❌ Este pago no tiene charge_id (pago antiguo).",
        "your_prompt_label": "🖌 Tu texto:",
        "sub_prompt": "⛔ ¡Suscríbete a nuestro canal para usar el bot!",
        "sub_check": "✅ Comprobar Suscripción",
        "sub_url_text": "🔗 Suscribirse al Canal",
        "sub_thanks": "✅ ¡Gracias! Estás suscrito. Ahora puedes usar el bot.",
        "sub_still_not": "⛔ Todavía no estás suscrito. Suscríbete y comprueba de nuevo.",
        "lang_changed": "✅ Idioma cambiado a: {lang}",
        "select_lang": "🌐 Por favor, selecciona un idioma:",
        "ai_response_header": "💬 Respuesta de IA:",
        "image_ready_header": "🎨 ¡La imagen está lista!",
        "image_prompt_label": "📝 Texto:",
        "image_count_label": "🔢 Cantidad:",
        "image_time_label": "⏰ Hora (UTC+5):",
        "image_elapsed_label": "⏱ Tiempo empleado en crear:",
        "choose_action": "Elige una de las siguientes opciones:",
        "your_message": "💬 Tu mensaje:",
        "admin_new_generation": "🎨 *¡Nueva Generación!*",
        "admin_user": "👤 *Usuario:*",
        "admin_prompt": "📝 *Texto:*",
        "admin_count": "🔢 *Cantidad:*",
        "admin_image_id": "🆔 *ID de Imagen:*",
        "admin_time": "⏰ *Hora \\(UTC\\+5\\):*",
    },
    # --- Italyancha (🇮🇹) ---
    "it": {
        "flag": "🇮🇹",
        "name": "Italiano",
        "welcome": "👋 Ciao!\n\nCreo immagini per te usando l'IA.",
        "gen_button": "🎨 Genera Immagine",
        "ai_button": "💬 Chatta con l'IA",
        "donate_button": "💖 Dona",
        "lang_button": "🌐 Cambia Lingua",
        "image_model_label": "🖼 Model:",
        "prompt_text": "✍️ Ora invia il testo per generare un'immagine.",
        "ai_prompt_text": "✍️ Scrivi la tua domanda per iniziare una conversazione.",
        "select_count": "🔢 Quante immagini generare?",
        "generating": "🔄 Generazione immagine ({count})... ⏳",
        "success": "✅ Immagine pronta! 📸",
        "settings_menu_title": "⚙️ Impostazioni",
"select_image_model_button": "🖼 Seleziona modello immagine",
"back_to_main_button": "🔙 Indietro",
"fake_lab_generating": "🔄 Generazione di una persona falsa...\n\n👤 Questa persona **non è reale** — creata dall'intelligenza artificiale!\n\n⏳ Attendere prego...",
"fake_lab_ready_caption": "👤 **Questa persona NON È REALE!**\n🤖 Generata dall'intelligenza artificiale.\n\n🔄 Usa **Aggiorna** per ottenere una nuova immagine.",
"fake_lab_refreshing": "🔄 **Caricamento di una nuova immagine...**\n⏳ Attendere prego...",
"fake_lab_error": "⚠️ **Si è verificato un errore.**\nPer favore, riprova.",

"progress_step_10": "🧠 Analisi del prompt...",
"progress_step_25": "🎨 Selezione del modello...",
"progress_step_40": "🌈 Costruzione dei colori e della composizione...",
"progress_step_60": "💡 Bilanciamento di luci e ombre...",
"progress_step_80": "🧩 Rifinitura dei dettagli...",
"progress_step_100": "✅ Preparazione alla consegna...",

"stats_title": "🤖 Statistiche Digen AI",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Immagini totali",
"stats_today": "📆 Oggi",
"stats_users": "👥 Utenti",
"stats_new_30d": "🆕 Ultimi 30 giorni",
"stats_your_images": "👤 Immagini generate da te",
"stats_refresh_button": "🔄 Aggiorna",
        "get_no_args_group": "❌ Nei gruppi, scrivi un prompt dopo /get. Esempio: /get città futuristica",
"get_no_args_private": "✍️ Inserisci un testo per generare l'immagine.",
"generating_progress": "🔄 Generazione in corso... {bar} {percent}%",
"image_delayed": "⚠️ L'immagine sta impiegando più tempo del previsto. Riprova più tardi.",
"donate_title": "💖 Supporta il Bot",
"donate_description": "Invia Stars per supportare il bot.",
"done": "✅ Fatto!",
"error_occurred": "⚠️ Si è verificato un errore. Riprova.",
"choose_action_prompt": "Scegli una delle seguenti opzioni:",
"your_message_label": "💬 Il tuo messaggio:",
        "error": "⚠️ Si è verificato un errore. Riprova.",
        "donate_prompt": "💰 Inserisci l'importo che desideri inviare (1–100000):",
        "donate_invalid": "❌ Inserisci un numero intero compreso tra 1 e 100000.",
        "donate_thanks": "✅ Grazie, {name}! Hai inviato {stars} Stars.",
        "refund_success": "✅ {stars} Stars rimborsati con successo all'utente {user_id}.",
        "refund_error": "❌ Errore: {error}",
        "no_permission": "⛔ Non hai il permesso.",
        "usage_refund": "Utilizzo: /refund <user_id> <donation_id>",
        "not_found": "❌ Non trovato o dati non validi.",
        "no_charge_id": "❌ Questo pagamento non ha un charge_id (pagamento vecchio).",
        "your_prompt_label": "🖌 Il tuo testo:",
        "sub_prompt": "⛔ Iscriviti al nostro canale per usare il bot!",
        "sub_check": "✅ Controlla l'iscrizione",
        "sub_url_text": "🔗 Iscriviti al Canale",
        "sub_thanks": "✅ Grazie! Sei iscritto. Ora puoi usare il bot.",
        "sub_still_not": "⛔ Non sei ancora iscritto. Iscriviti e controlla di nuovo.",
        "lang_changed": "✅ Lingua cambiata in: {lang}",
        "select_lang": "🌐 Seleziona una lingua:",
        "ai_response_header": "💬 Risposta IA:",
        "image_ready_header": "🎨 Immagine pronta!",
        "image_prompt_label": "📝 Testo:",
        "image_count_label": "🔢 Quantità:",
        "image_time_label": "⏰ Ora (UTC+5):",
        "image_elapsed_label": "⏱ Tempo impiegato per creare:",
        "choose_action": "Scegli una delle seguenti opzioni:",
        "your_message": "💬 Il tuo messaggio:",
        "admin_new_generation": "🎨 *Nuova Generazione!*",
        "admin_user": "👤 *Utente:*",
        "admin_prompt": "📝 *Testo:*",
        "admin_count": "🔢 *Quantità:*",
        "admin_image_id": "🆔 *ID Immagine:*",
        "admin_time": "⏰ *Ora \\(UTC\\+5\\):*",
        "back_to_main_button": "⬅️ Back",
    },
    # --- Xitoycha (Soddalashtirilgan) (🇨🇳) ---
    "zhcn": {
        "flag": "🇨🇳",
        "name": "简体中文",
        "welcome": "👋 你好！\n\n我使用人工智能为你生成图像。",
        "gen_button": "🎨 生成图像",
        "ai_button": "💬 与AI聊天",
        "donate_button": "💖 捐赠",
        "lang_button": "🌐 更改语言",
        "prompt_text": "✍️ 现在发送文本来生成图像。",
        "ai_prompt_text": "✍️ 写下你的问题以开始对话。",
        "select_count": "🔢 生成多少张图像？",
        "generating": "🔄 正在生成图像 ({count})... ⏳",
        "success": "✅ 图像已准备好！ 📸",
        "settings_menu_title": "⚙️ 设置",
"select_image_model_button": "🖼 选择图像模型",
"back_to_main_button": "🔙 返回",
"fake_lab_generating": "🔄 正在生成AI人像...\n\n👤 此人 **不是真实的** — 由 AI 创造！\n\n⏳ 请稍候...",
"fake_lab_ready_caption": "👤 **此人并不真实！**\n🤖 由人工智能生成。\n\n🔄 使用 **刷新** 获取新图像。",
"fake_lab_refreshing": "🔄 **正在加载新图像...**\n⏳ 请稍候...",
"fake_lab_error": "⚠️ **发生错误。**\n请重试。",
"progress_step_10": "🧠 正在分析提示...",
"progress_step_25": "🎨 选择模型...",
"progress_step_40": "🌈 构建颜色与构图...",
"progress_step_60": "💡 平衡光影...",
"progress_step_80": "🧩 完善细节...",
"progress_step_100": "✅ 准备交付...",
"stats_title": "🤖 Digen AI 统计",
"stats_ping": "⚡ 延迟",
"stats_total_images": "🖼 总图像数",
"stats_today": "📆 今日",
"stats_users": "👥 用户",
"stats_new_30d": "🆕 最近 30 天",
"stats_your_images": "👤 你生成的",
"stats_refresh_button": "🔄 刷新",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ 在群组中，请在 /get 后输入提示词。例如：/get 未来城市",
"get_no_args_private": "✍️ 请输入用于生成图像的文本。",
"generating_progress": "🔄 正在生成图像... {bar} {percent}%",
"image_delayed": "⚠️ 图像生成需要更长时间。请稍后再试。",
"donate_title": "💖 支持机器人",
"donate_description": "发送 Stars 以支持机器人。",
"done": "✅ 完成！",
"error_occurred": "⚠️ 发生错误。请重试。",
"choose_action_prompt": "请选择以下选项之一：",
"your_message_label": "💬 您的消息：",
        "error": "⚠️ 发生错误。请重试。",
        "donate_prompt": "💰 请输入您要发送的金额 (1–100000)：",
        "donate_invalid": "❌ 请输入1到100000之间的整数。",
        "donate_thanks": "✅ 谢谢，{name}！您发送了 {stars} Stars。",
        "refund_success": "✅ {stars} Stars 已成功退还给用户 {user_id}。",
        "refund_error": "❌ 错误：{error}",
        "no_permission": "⛔ 您没有权限。",
        "usage_refund": "用法：/refund <user_id> <donation_id>",
        "not_found": "❌ 未找到或数据无效。",
        "no_charge_id": "❌ 此付款没有 charge_id（旧付款）。",
        "your_prompt_label": "🖌 您的文本：",
        "sub_prompt": "⛔ 订阅我们的频道以使用机器人！",
        "sub_check": "✅ 检查订阅",
        "sub_url_text": "🔗 订阅频道",
        "sub_thanks": "✅ 谢谢！您已订阅。现在您可以使用机器人了。",
        "sub_still_not": "⛔ 您仍未订阅。请订阅并再次检查。",
        "lang_changed": "✅ 语言已更改为：{lang}",
        "select_lang": "🌐 请选择语言：",
        "ai_response_header": "💬 AI 回答：",
        "image_ready_header": "🎨 图像已准备好！",
        "image_prompt_label": "📝 文本：",
        "image_count_label": "🔢 数量：",
        "image_time_label": "⏰ 时间 (UTC+5)：",
        "image_elapsed_label": "⏱ 创建所用时间：",
        "choose_action": "请选择以下选项之一：",
        "your_message": "💬 您的消息：",
        "admin_new_generation": "🎨 *新生成！*",
        "admin_user": "👤 *用户：*",
        "admin_prompt": "📝 *文本：*",
        "admin_count": "🔢 *数量：*",
        "admin_image_id": "🆔 *图像ID：*",
        "admin_time": "⏰ *时间 \\(UTC\\+5\\)：*",
        "back_to_main_button": "⬅️ Back",
    },
    # --- Bengalcha (🇧🇩) ---
    "bn": {
        "flag": "🇧🇩",
        "name": "বাংলা",
        "welcome": "👋 হ্যালো!\n\nআমি আপনার জন্য AI ব্যবহার করে ছবি তৈরি করি।",
        "gen_button": "🎨 ছবি তৈরি করুন",
        "ai_button": "💬 AI এর সাথে চ্যাট করুন",
        "donate_button": "💖 অনুদান করুন",
        "lang_button": "🌐 ভাষা পরিবর্তন করুন",
        "prompt_text": "✍️ এখন একটি ছবি তৈরি করতে টেক্সট পাঠান।",
        "ai_prompt_text": "✍️ একটি কথোপকথন শুরু করতে আপনার প্রশ্ন লিখুন।",
        "select_count": "🔢 কতগুলি ছবি তৈরি করবেন?",
        "generating": "🔄 ছবি তৈরি করা হচ্ছে ({count})... ⏳",
        "success": "✅ ছবি প্রস্তুত! 📸",
        "settings_menu_title": "⚙️ সেটিংস",
"select_image_model_button": "🖼 ইমেজ মডেল নির্বাচন করুন",
"back_to_main_button": "🔙 ফিরে যান",

"fake_lab_generating": "🔄 কৃত্রিম ব্যক্তির ছবি তৈরি হচ্ছে...\n\n👤 এই ব্যক্তি **বাস্তব নয়** — AI দ্বারা তৈরি!\n\n⏳ অনুগ্রহ করে অপেক্ষা করুন...",
"fake_lab_ready_caption": "👤 **এই ব্যক্তি বাস্তব নয়!**\n🤖 কৃত্রিম বুদ্ধিমত্তা দ্বারা তৈরি।\n\n🔄 নতুন ছবি পেতে **রিফ্রেশ** করুন।",
"fake_lab_refreshing": "🔄 **নতুন ছবি লোড হচ্ছে...**\n⏳ অনুগ্রহ করে অপেক্ষা করুন...",
"fake_lab_error": "⚠️ **একটি ত্রুটি ঘটেছে।**\nঅনুগ্রহ করে আবার চেষ্টা করুন।",
"back_to_main_button": "⬅️ Back",
"progress_step_10": "🧠 প্রম্পট বিশ্লেষণ করা হচ্ছে...",
"progress_step_25": "🎨 মডেল নির্বাচন করা হচ্ছে...",
"progress_step_40": "🌈 রং এবং কম্পোজিশন তৈরি করা হচ্ছে...",
"progress_step_60": "💡 আলো এবং ছায়া সামঞ্জস্য করা হচ্ছে...",
"progress_step_80": "🧩 বিস্তারিত সম্পন্ন করা হচ্ছে...",
"progress_step_100": "✅ বিতরণের জন্য প্রস্তুত করা হচ্ছে...",

"stats_title": "🤖 Digen AI পরিসংখ্যান",
"stats_ping": "⚡ পিং",
"stats_total_images": "🖼 মোট ছবি",
"stats_today": "📆 আজ",
"stats_users": "👥 ব্যবহারকারী",
"stats_new_30d": "🆕 গত ৩০ দিন",
"stats_your_images": "👤 আপনি তৈরি করেছেন",
"stats_refresh_button": "🔄 রিফ্রেশ",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ গ্রুপে, /get এর পরে একটি প্রম্পট লিখুন। উদাহরণ: /get ফিউচারিস্টিক সিটি",
"get_no_args_private": "✍️ দয়া করে ছবির জন্য একটি টেক্সট লিখুন।",
"generating_progress": "🔄 ছবি তৈরি হচ্ছে... {bar} {percent}%",
"image_delayed": "⚠️ ছবি তৈরি করতে আরও সময় লাগছে। পরে আবার চেষ্টা করুন।",
"donate_title": "💖 বটকে সমর্থন করুন",
"donate_description": "বটকে সমর্থন করতে Stars পাঠান।",
"done": "✅ সম্পন্ন!",
"error_occurred": "⚠️ একটি ত্রুটি ঘটেছে। অনুগ্রহ করে আবার চেষ্টা করুন।",
"choose_action_prompt": "নিচের যেকোনো একটি নির্বাচন করুন:",
"your_message_label": "💬 আপনার বার্তা:",
        "error": "⚠️ একটি ত্রুটি ঘটেছে। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "donate_prompt": "💰 অনুগ্রহ করে আপনি যে পরিমাণ পাঠাতে চান তা লিখুন (1–100000):",
        "donate_invalid": "❌ অনুগ্রহ করে 1 থেকে 100000 এর মধ্যে একটি পূর্ণসংখ্যা লিখুন।",
        "donate_thanks": "✅ ধন্যবাদ, {name}! আপনি {stars} Stars পাঠিয়েছেন।",
        "refund_success": "✅ {stars} Stars সফলভাবে ব্যবহারকারী {user_id} কে ফেরত দেওয়া হয়েছে।",
        "refund_error": "❌ ত্রুটি: {error}",
        "no_permission": "⛔ আপনার অনুমতি নেই।",
        "usage_refund": "ব্যবহার: /refund <user_id> <donation_id>",
        "not_found": "❌ পাওয়া যায়নি বা অবৈধ তথ্য।",
        "no_charge_id": "❌ এই পেমেন্টের কোন charge_id নেই (পুরানো পেমেন্ট)।",
        "your_prompt_label": "🖌 আপনার টেক্সট:",
        "sub_prompt": "⛔ বট ব্যবহার করতে আমাদের চ্যানেলে সাবস্ক্রাইব করুন!",
        "sub_check": "✅ সাবস্ক্রিপশন পরীক্ষা করুন",
        "sub_url_text": "🔗 চ্যানেলে সাবস্ক্রাইব করুন",
        "sub_thanks": "✅ ধন্যবাদ! আপনি সাবস্ক্রাইব করেছেন। এখন আপনি বট ব্যবহার করতে পারেন।",
        "sub_still_not": "⛔ আপনি এখনও সাবস্ক্রাইব করেননি। সাবস্ক্রাইব করুন এবং আবার পরীক্ষা করুন।",
        "lang_changed": "✅ ভাষা পরিবর্তন করা হয়েছে: {lang}",
        "select_lang": "🌐 অনুগ্রহ করে একটি ভাষা নির্বাচন করুন:",
        "ai_response_header": "💬 AI উত্তর:",
        "image_ready_header": "🎨 ছবি প্রস্তুত!",
        "image_prompt_label": "📝 টেক্সট:",
        "image_count_label": "🔢 সংখ্যা:",
        "image_time_label": "⏰ সময় (UTC+5):",
        "image_elapsed_label": "⏱ তৈরি করতে সময় লেগেছে:",
        "choose_action": "নিচের যেকোনো একটি নির্বাচন করুন:",
        "your_message": "💬 আপনার বার্তা:",
        "admin_new_generation": "🎨 *নতুন জেনারেশন!*",
        "admin_user": "👤 *ব্যবহারকারী:*",
        "admin_prompt": "📝 *টেক্সট:*",
        "admin_count": "🔢 *সংখ্যা:*",
        "admin_image_id": "🆔 *ছবির ID:*",
        "admin_time": "⏰ *সময় \\(UTC\\+5\\):*",
    },
    # --- Hindcha (🇮🇳) ---
    "hi": {
        "flag": "🇮🇳",
        "name": "हिन्दी",
        "welcome": "👋 नमस्ते!\n\nमैं आपके लिए AI का उपयोग करके छवियाँ बनाता हूँ।",
        "gen_button": "🎨 छवि उत्पन्न करें",
        "ai_button": "💬 AI से चैट करें",
        "donate_button": "💖 दान करें",
        "lang_button": "🌐 भाषा बदलें",
        "prompt_text": "✍️ अब एक छवि उत्पन्न करने के लिए पाठ भेजें।",
        "ai_prompt_text": "✍️ एक वार्तालाप शुरू करने के लिए अपना प्रश्न लिखें।",
        "select_count": "🔢 कितनी छवियाँ उत्पन्न करें?",
        "generating": "🔄 छवि उत्पन्न हो रही है ({count})... ⏳",
        "success": "✅ छवि तैयार है! 📸",
        "back_to_main_button": "⬅️ Back",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ समूह में, /get के बाद एक प्रॉम्प्ट लिखें। उदाहरण: /get भविष्य का शहर",
"get_no_args_private": "✍️ कृपया छवि के लिए एक पाठ दर्ज करें।",
"generating_progress": "🔄 छवि बन रही है... {bar} {percent}%",
"image_delayed": "⚠️ छवि तैयार होने में थोड़ा समय लग रहा है। बाद में पुनः प्रयास करें।",
"donate_title": "💖 बॉट का समर्थन करें",
"donate_description": "बॉट का समर्थन करने के लिए Stars भेजें।",
"done": "✅ हो गया!",
"error_occurred": "⚠️ एक त्रुटि हुई। कृपया पुनः प्रयास करें।",
"choose_action_prompt": "निम्नलिखित में से एक चुनें:",
"your_message_label": "💬 आपका संदेश:",
        "error": "⚠️ एक त्रुटि हुई। कृपया पुनः प्रयास करें।",
        "donate_prompt": "💰 कृपया वह राशि दर्ज करें जो आप भेजना चाहते हैं (1–100000):",
        "donate_invalid": "❌ कृपया 1 से 100000 के बीच एक पूर्णांक दर्ज करें।",
        "donate_thanks": "✅ धन्यवाद, {name}! आपने {stars} Stars भेजे।",
        "refund_success": "✅ {stars} Stars उपयोगकर्ता {user_id} को सफलतापूर्वक वापस कर दिए गए।",
        "refund_error": "❌ त्रुटि: {error}",
        "no_permission": "⛔ आपके पास अनुमति नहीं है।",
        "usage_refund": "उपयोग: /refund <user_id> <donation_id>",
        "not_found": "❌ नहीं मिला या अमान्य डेटा।",
        "no_charge_id": "❌ इस भुगतान में charge_id नहीं है (पुराना भुगतान)।",
        "your_prompt_label": "🖌 आपका पाठ:",
        "sub_prompt": "⛔ बॉट का उपयोग करने के लिए हमारे चैनल की सदस्यता लें!",
        "sub_check": "✅ सदस्यता की जाँच करें",
        "sub_url_text": "🔗 चैनल की सदस्यता लें",
        "sub_thanks": "✅ धन्यवाद! आप सदस्यता ले चुके हैं। अब आप बॉट का उपयोग कर सकते हैं।",
        "sub_still_not": "⛔ आप अभी भी सदस्यता नहीं ली है। सदस्यता लें और फिर से जाँचें।",
        "lang_changed": "✅ भाषा बदल दी गई है: {lang}",
        "select_lang": "🌐 कृपया एक भाषा चुनें:",
        "ai_response_header": "💬 AI प्रतिक्रिया:",
        "image_ready_header": "🎨 छवि तैयार है!",
        "image_prompt_label": "📝 प्रॉम्प्ट:",
        "image_count_label": "🔢 गिनती:",
        "image_time_label": "⏰ समय (UTC+5):",
        "image_elapsed_label": "⏱ बनाने में लगा समय:",
        "choose_action": "निम्नलिखित में से एक चुनें:",
        "your_message": "💬 आपका संदेश:",
        "admin_new_generation": "🎨 *नई पीढ़ी!*",
        "admin_user": "👤 *उपयोगकर्ता:*",
        "admin_prompt": "📝 *प्रॉम्प्ट:*",
        "admin_count": "🔢 *गिनती:*",
        "admin_image_id": "🆔 *छवि आईडी:*",
        "admin_time": "⏰ *समय \\(UTC\\+5\\):*",
    },
    # --- Portugalccha (Braziliya) (🇧🇷) ---
    "ptbr": {
        "flag": "🇧🇷",
        "name": "Português (Brasil)",
        "welcome": "👋 Olá!\n\nEu crio imagens para você usando IA.",
        "gen_button": "🎨 Gerar Imagem",
        "ai_button": "💬 Conversar com IA",
        "donate_button": "💖 Doar",
        "lang_button": "🌐 Mudar Idioma",
        "image_model_label": "🖼 Model:",
        "prompt_text": "✍️ Agora envie o texto para gerar uma imagem.",
        "ai_prompt_text": "✍️ Escreva sua pergunta para iniciar uma conversa.",
        "select_count": "🔢 Quantas imagens gerar?",
        "generating": "🔄 Gerando imagem ({count})... ⏳",
        "success": "✅ Imagem pronta! 📸",
        "settings_menu_title": "⚙️ Configurações",
"select_image_model_button": "🖼 Selecionar modelo de imagem",
"back_to_main_button": "🔙 Voltar",

"fake_lab_generating": "🔄 Gerando uma pessoa falsa...\n\n👤 Esta pessoa **NÃO É real** — criada por IA!\n\n⏳ Por favor, aguarde...",
"fake_lab_ready_caption": "👤 **Esta pessoa NÃO É REAL!**\n🤖 Gerada por inteligência artificial.\n\n🔄 Use **Atualizar** para obter uma nova imagem.",
"fake_lab_refreshing": "🔄 **Carregando nova imagem...**\n⏳ Por favor, aguarde...",
"fake_lab_error": "⚠️ **Ocorreu um erro.**\nPor favor, tente novamente.",

"progress_step_10": "🧠 Analisando o prompt...",
"progress_step_25": "🎨 Selecionando modelo...",
"progress_step_40": "🌈 Construindo cores e composição...",
"progress_step_60": "💡 Balanceando luz e sombras...",
"progress_step_80": "🧩 Finalizando detalhes...",
"progress_step_100": "✅ Preparando para entrega...",

"stats_title": "🤖 Estatísticas do Digen AI",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Total de imagens",
"stats_today": "📆 Hoje",
"stats_users": "👥 Usuários",
"stats_new_30d": "🆕 Últimos 30 dias",
"stats_your_images": "👤 Imagens geradas por você",
"stats_refresh_button": "🔄 Atualizar",
        "get_no_args_group": "❌ Em grupos, escreva um prompt após /get. Exemplo: /get cidade futurista",
"get_no_args_private": "✍️ Por favor, digite um texto para gerar a imagem.",
"generating_progress": "🔄 Gerando imagem... {bar} {percent}%",
"image_delayed": "⚠️ A imagem está demorando para ser preparada. Tente novamente mais tarde.",
"donate_title": "💖 Apoie o Bot",
"donate_description": "Envie Stars para apoiar o bot.",
"done": "✅ Pronto!",
"error_occurred": "⚠️ Ocorreu um erro. Por favor, tente novamente.",
"choose_action_prompt": "Escolha uma das opções a seguir:",
"your_message_label": "💬 Sua mensagem:",
        "error": "⚠️ Ocorreu um erro. Por favor, tente novamente.",
        "donate_prompt": "💰 Por favor, insira o valor que deseja enviar (1–100000):",
        "donate_invalid": "❌ Por favor, insira um número inteiro entre 1 e 100000.",
        "donate_thanks": "✅ Obrigado, {name}! Você enviou {stars} Stars.",
        "refund_success": "✅ {stars} Stars reembolsados com sucesso para o usuário {user_id}.",
        "refund_error": "❌ Erro: {error}",
        "no_permission": "⛔ Você não tem permissão.",
        "usage_refund": "Uso: /refund <user_id> <donation_id>",
        "not_found": "❌ Não encontrado ou dados inválidos.",
        "no_charge_id": "❌ Este pagamento não possui charge_id (pagamento antigo).",
        "your_prompt_label": "🖌 Seu texto:",
        "sub_prompt": "⛔ Inscreva-se no nosso canal para usar o bot!",
        "sub_check": "✅ Verificar Inscrição",
        "sub_url_text": "🔗 Inscrever-se no Canal",
        "sub_thanks": "✅ Obrigado! Você está inscrito. Agora você pode usar o bot.",
        "sub_still_not": "⛔ Você ainda não está inscrito. Inscreva-se e verifique novamente.",
        "lang_changed": "✅ Idioma alterado para: {lang}",
        "select_lang": "🌐 Por favor, selecione um idioma:",
        "ai_response_header": "💬 Resposta da IA:",
        "image_ready_header": "🎨 Imagem pronta!",
        "image_prompt_label": "📝 Texto:",
        "image_count_label": "🔢 Quantidade:",
        "image_time_label": "⏰ Hora (UTC+5):",
        "image_elapsed_label": "⏱ Tempo gasto para criar:",
        "choose_action": "Escolha uma das opções a seguir:",
        "your_message": "💬 Sua mensagem:",
        "admin_new_generation": "🎨 *Nova Geração!*",
        "admin_user": "👤 *Usuário:*",
        "admin_prompt": "📝 *Texto:*",
        "admin_count": "🔢 *Quantidade:*",
        "admin_image_id": "🆔 *ID da Imagem:*",
        "admin_time": "⏰ *Hora \\(UTC\\+5\\):*",
        "back_to_main_button": "⬅️ Back",
    },
    # --- Arabcha (🇸🇦) ---
    "ar": {
        "flag": "🇸🇦",
        "name": "العربية",
        "welcome": "👋 مرحباً!\n\nأقوم بإنشاء صور لك باستخدام الذكاء الاصطناعي.",
        "gen_button": "🎨 إنشاء صورة",
        "ai_button": "💬 الدردشة مع الذكاء الاصطناعي",
        "donate_button": "💖 تبرع",
        "lang_button": "🌐 تغيير اللغة",
        "prompt_text": "✍️ الآن أرسل النص لإنشاء صورة.",
        "ai_prompt_text": "✍️ اكتب سؤالك لبدء محادثة.",
        "select_count": "🔢 كم عدد الصور التي سيتم إنشاؤها؟",
        "generating": "🔄 يتم إنشاء الصورة ({count})... ⏳",
        "success": "✅ الصورة جاهزة! 📸",
        "settings_menu_title": "⚙️ الإعدادات",
"select_image_model_button": "🖼 اختر نموذج الصورة",
"back_to_main_button": "🔙 رجوع",
"fake_lab_generating": "🔄 جاري إنشاء شخص زائف...\n\n👤 هذا الشخص **ليس حقيقياً** — تم إنشاؤه بواسطة AI!\n\n⏳ الرجاء الانتظار...",
"fake_lab_ready_caption": "👤 **هذا الشخص ليس حقيقياً!**\n🤖 تم إنشاؤه بواسطة الذكاء الاصطناعي.\n\n🔄 استخدم **تحديث** للحصول على صورة جديدة.",
"fake_lab_refreshing": "🔄 **جاري تحميل صورة جديدة…**\n⏳ الرجاء الانتظار...",
"fake_lab_error": "⚠️ **حدث خطأ.**\nالرجاء المحاولة مرة أخرى.",
"progress_step_10": "🧠 تحليل المُدخل...",
"progress_step_25": "🎨 اختيار النموذج...",
"progress_step_40": "🌈 بناء الألوان والتكوين...",
"progress_step_60": "💡 موازنة الضوء والظلال...",
"progress_step_80": "🧩 إنهاء التفاصيل...",
"progress_step_100": "✅ التجهيز للتسليم...",
"stats_title": "🤖 إحصائيات Digen AI",
"stats_ping": "⚡ استجابة",
"stats_total_images": "🖼 إجمالي الصور",
"stats_today": "📆 اليوم",
"stats_users": "👥 المستخدمين",
"stats_new_30d": "🆕 آخر 30 يومًا",
"stats_your_images": "👤 الصور التي أنشأتها",
"stats_refresh_button": "🔄 تحديث",
        "image_model_label": "🖼 Model:",
        "get_no_args_group": "❌ في المجموعات، اكتب موجهًا بعد /get. مثال: /get مدينة مستقبلية",
"get_no_args_private": "✍️ يرجى إدخال نص لإنشاء الصورة.",
"generating_progress": "🔄 يتم إنشاء الصورة... {bar} {percent}%",
"image_delayed": "⚠️ تستغرق الصورة وقتًا أطول من المعتاد. حاول مرة أخرى لاحقًا.",
"donate_title": "💖 دعم البوت",
"donate_description": "أرسل Stars لدعم البوت.",
"done": "✅ تم!",
"error_occurred": "⚠️ حدث خطأ. يرجى المحاولة مرة أخرى.",
"choose_action_prompt": "اختر واحدة من الخيارات التالية:",
"your_message_label": "💬 رسالتك:",
        "error": "⚠️ حدث خطأ. يرجى المحاولة مرة أخرى.",
        "donate_prompt": "💰 يرجى إدخال المبلغ الذي ترغب في إرساله (1–100000):",
        "donate_invalid": "❌ يرجى إدخال رقم صحيح بين 1 و 100000.",
        "donate_thanks": "✅ شكراً لك، {name}! لقد أرسلت {stars} نجوم.",
        "refund_success": "✅ تم إرجاع {stars} نجوم بنجاح إلى المستخدم {user_id}.",
        "refund_error": "❌ خطأ: {error}",
        "no_permission": "⛔ ليس لديك إذن.",
        "usage_refund": "الاستخدام: /refund <user_id> <donation_id>",
        "not_found": "❌ غير موجود أو بيانات غير صالحة.",
        "no_charge_id": "❌ هذا الدفع لا يحتوي على charge_id (دفع قديم).",
        "your_prompt_label": "🖌 نصك:",
        "sub_prompt": "⛔ اشترك في قناتنا لاستخدام البوت!",
        "sub_check": "✅ التحقق من الاشتراك",
        "sub_url_text": "🔗 الاشتراك في القناة",
        "sub_thanks": "✅ شكراً لك! أنت مشترك الآن. يمكنك استخدام البوت.",
        "sub_still_not": "⛔ أنت لست مشتركاً بعد. اشترك وتحقق مرة أخرى.",
        "lang_changed": "✅ تم تغيير اللغة إلى: {lang}",
        "select_lang": "🌐 الرجاء اختيار اللغة:",
        "ai_response_header": "💬 رد الذكاء الاصطناعي:",
        "image_ready_header": "🎨 الصورة جاهزة!",
        "image_prompt_label": "📝 النص:",
        "image_count_label": "🔢 العدد:",
        "image_time_label": "⏰ الوقت (UTC+5):",
        "image_elapsed_label": "⏱ الوقت المستغرق للإنشاء:",
        "choose_action": "اختر واحدة من الخيارات التالية:",
        "your_message": "💬 رسالتك:",
        "admin_new_generation": "🎨 *توليد جديد!*",
        "admin_user": "👤 *المستخدم:*",
        "admin_prompt": "📝 *النص:*",
        "admin_count": "🔢 *العدد:*",
        "admin_image_id": "🆔 *معرف الصورة:*",
        "admin_time": "⏰ *الوقت \\(UTC\\+5\\):*",
    },
    # --- Ukraincha (🇺🇦) ---
    "uk": {
        "flag": "🇺🇦",
        "name": "Українська",
        "welcome": "👋 Привіт!\n\nЯ створюю для вас зображення за допомогою ШІ.",
        "gen_button": "🎨 Створити зображення",
        "ai_button": "💬 Чат з ШІ",
        "donate_button": "💖 Пожертвувати",
        "lang_button": "🌐 Змінити мову",
        "image_model_label": "🖼 Model:",
        "settings_menu_title": "⚙️ Налаштування",
"select_image_model_button": "🖼 Обрати модель зображення",
"back_to_main_button": "🔙 Назад",
"fake_lab_generating": "🔄 Генерую AI-людину...\n\n👤 Ця особа **не є реальною** — створена штучним інтелектом!\n\n⏳ Будь ласка, зачекайте...",
"fake_lab_ready_caption": "👤 **Ця особа НЕ РЕАЛЬНА!**\n🤖 Згенеровано штучним інтелектом.\n\n🔄 Використайте **Оновити** щоб отримати нове зображення.",
"fake_lab_refreshing": "🔄 **Завантаження нового зображення...**\n⏳ Будь ласка, зачекайте...",
"fake_lab_error": "⚠️ **Сталася помилка.**\nБудь ласка, спробуйте ще раз.",
"progress_step_10": "🧠 Аналіз промпта...",
"progress_step_25": "🎨 Вибір моделі...",
"progress_step_40": "🌈 Побудова кольорів і композиції...",
"progress_step_60": "💡 Балансування світла та тіней...",
"progress_step_80": "🧩 Завершення деталей...",
"progress_step_100": "✅ Підготовка до відправки...",
"stats_title": "🤖 Статистика Digen AI",
"stats_ping": "⚡ Пінг",
"stats_total_images": "🖼 Усього зображень",
"stats_today": "📆 Сьогодні",
"stats_users": "👥 Користувачі",
"stats_new_30d": "🆕 Останні 30 днів",
"stats_your_images": "👤 Ви створили",
"stats_refresh_button": "🔄 Оновити",
        "prompt_text": "✍️ Тепер надішліть текст для створення зображення.",
        "ai_prompt_text": "✍️ Напишіть своє запитання, щоб розпочати розмову.",
        "select_count": "🔢 Скільки зображень створити?",
        "generating": "🔄 Створюю зображення ({count})... ⏳",
        "success": "✅ Зображення готове! 📸",
        "get_no_args_group": "❌ У групах напишіть промпт після /get. Приклад: /get футуристичне місто",
"get_no_args_private": "✍️ Будь ласка, введіть текст для створення зображення.",
"generating_progress": "🔄 Створення зображення... {bar} {percent}%",
"image_delayed": "⚠️ Підготовка зображення займає більше часу. Спробуйте пізніше.",
"donate_title": "💖 Підтримати бота",
"donate_description": "Надішліть Stars, щоб підтримати бота.",
"done": "✅ Готово!",
"error_occurred": "⚠️ Сталася помилка. Спробуйте ще раз.",
"choose_action_prompt": "Виберіть один із варіантів:",
"your_message_label": "💬 Ваше повідомлення:",
        "error": "⚠️ Сталася помилка. Будь ласка, спробуйте ще раз.",
        "donate_prompt": "💰 Будь ласка, введіть суму, яку ви хочете надіслати (1–100000):",
        "donate_invalid": "❌ Будь ласка, введіть ціле число від 1 до 100000.",
        "donate_thanks": "✅ Дякую, {name}! Ви надіслали {stars} Stars.",
        "refund_success": "✅ {stars} Stars успішно повернуто користувачу {user_id}.",
        "refund_error": "❌ Помилка: {error}",
        "no_permission": "⛔ У вас немає дозволу.",
        "usage_refund": "Використання: /refund <user_id> <donation_id>",
        "not_found": "❌ Не знайдено або недійсні дані.",
        "no_charge_id": "❌ Цей платіж не має charge_id (старий платіж).",
        "your_prompt_label": "🖌 Ваш текст:",
        "sub_prompt": "⛔ Підпишіться на наш канал, щоб користуватися ботом!",
        "sub_check": "✅ Перевірити підписку",
        "sub_url_text": "🔗 Підписатися на канал",
        "sub_thanks": "✅ Дякую! Ви підписані. Тепер ви можете користуватися ботом.",
        "sub_still_not": "⛔ Ви все ще не підписані. Підпишіться та перевірте ще раз.",
        "lang_changed": "✅ Мову змінено на: {lang}",
        "select_lang": "🌐 Будь ласка, виберіть мову:",
        "ai_response_header": "💬 Відповідь ШІ:",
        "image_ready_header": "🎨 Зображення готове!",
        "image_prompt_label": "📝 Текст:",
        "image_count_label": "🔢 Кількість:",
        "image_time_label": "⏰ Час (UTC+5):",
        "image_elapsed_label": "⏱ Час, витрачений на створення:",
        "choose_action": "Виберіть один із варіантів:",
        "your_message": "💬 Ваше повідомлення:",
        "admin_new_generation": "🎨 *Нове покоління!*",
        "admin_user": "👤 *Користувач:*",
        "admin_prompt": "📝 *Текст:*",
        "admin_count": "🔢 *Кількість:*",
        "admin_image_id": "🆔 *ID зображення:*",
        "admin_time": "⏰ *Час \\(UTC\\+5\\):*",
    },
    # --- Vyetnamcha (🇻🇳) ---
    "vi": {
        "flag": "🇻🇳",
        "name": "Tiếng Việt",
        "welcome": "👋 Xin chào!\n\nTôi tạo hình ảnh cho bạn bằng AI.",
        "gen_button": "🎨 Tạo Hình Ảnh",
        "ai_button": "💬 Trò chuyện với AI",
        "donate_button": "💖 Quyên góp",
        "lang_button": "🌐 Đổi Ngôn ngữ",
        "image_model_label": "🖼 Model:",
        "prompt_text": "✍️ Bây giờ hãy gửi văn bản để tạo hình ảnh.",
        "ai_prompt_text": "✍️ Viết câu hỏi của bạn để bắt đầu cuộc trò chuyện.",
        "select_count": "🔢 Tạo bao nhiêu hình ảnh?",
        "generating": "🔄 Đang tạo hình ảnh ({count})... ⏳",
        "success": "✅ Hình ảnh đã sẵn sàng! 📸",
        "settings_menu_title": "⚙️ Cài đặt",
"select_image_model_button": "🖼 Chọn mô hình hình ảnh",
"back_to_main_button": "🔙 Quay lại",
"fake_lab_generating": "🔄 Đang tạo người giả...\n\n👤 Người này **không có thật** — do AI tạo ra!\n\n⏳ Vui lòng chờ...",
"fake_lab_ready_caption": "👤 **Người này KHÔNG CÓ THẬT!**\n🤖 Được tạo bởi trí tuệ nhân tạo.\n\n🔄 Nhấn **Làm mới** để lấy hình ảnh mới.",
"fake_lab_refreshing": "🔄 **Đang tải hình ảnh mới...**\n⏳ Vui lòng chờ...",
"fake_lab_error": "⚠️ **Đã xảy ra lỗi.**\nVui lòng thử lại.",
"progress_step_10": "🧠 Phân tích prompt...",
"progress_step_25": "🎨 Lựa chọn mô hình...",
"progress_step_40": "🌈 Xây dựng màu sắc và bố cục...",
"progress_step_60": "💡 Cân bằng ánh sáng và bóng...",
"progress_step_80": "🧩 Hoàn thiện chi tiết...",
"progress_step_100": "✅ Chuẩn bị giao hình ảnh...",
"stats_title": "🤖 Thống kê Digen AI",
"stats_ping": "⚡ Ping",
"stats_total_images": "🖼 Tổng số hình ảnh",
"stats_today": "📆 Hôm nay",
"stats_users": "👥 Người dùng",
"stats_new_30d": "🆕 30 ngày qua",
"stats_your_images": "👤 Bạn đã tạo",
"stats_refresh_button": "🔄 Làm mới",
        "get_no_args_group": "❌ Trong nhóm, hãy viết prompt sau /get. Ví dụ: /get thành phố tương lai",
"get_no_args_private": "✍️ Vui lòng nhập văn bản để tạo hình ảnh.",
"generating_progress": "🔄 Đang tạo hình ảnh... {bar} {percent}%",
"image_delayed": "⚠️ Hình ảnh đang mất nhiều thời gian để chuẩn bị. Vui lòng thử lại sau.",
"donate_title": "💖 Ủng hộ Bot",
"donate_description": "Gửi Stars để ủng hộ bot.",
"done": "✅ Xong!",
"error_occurred": "⚠️ Đã xảy ra lỗi. Vui lòng thử lại.",
"choose_action_prompt": "Chọn một trong các tùy chọn sau:",
"your_message_label": "💬 Tin nhắn của bạn:",
        "error": "⚠️ Đã xảy ra lỗi. Vui lòng thử lại.",
        "donate_prompt": "💰 Vui lòng nhập số tiền bạn muốn gửi (1–100000):",
        "donate_invalid": "❌ Vui lòng nhập một số nguyên từ 1 đến 100000.",
        "donate_thanks": "✅ Cảm ơn bạn, {name}! Bạn đã gửi {stars} Stars.",
        "refund_success": "✅ {stars} Stars đã được hoàn lại thành công cho người dùng {user_id}.",
        "refund_error": "❌ Lỗi: {error}",
        "no_permission": "⛔ Bạn không có quyền.",
        "usage_refund": "Cách dùng: /refund <user_id> <donation_id>",
        "not_found": "❌ Không tìm thấy hoặc dữ liệu không hợp lệ.",
        "no_charge_id": "❌ Thanh toán này không có charge_id (thanh toán cũ).",
        "your_prompt_label": "🖌 Văn bản của bạn:",
        "sub_prompt": "⛔ Đăng ký kênh của chúng tôi để sử dụng bot!",
        "sub_check": "✅ Kiểm tra Đăng ký",
        "sub_url_text": "🔗 Đăng ký Kênh",
        "sub_thanks": "✅ Cảm ơn bạn! Bạn đã đăng ký. Bây giờ bạn có thể sử dụng bot.",
        "sub_still_not": "⛔ Bạn vẫn chưa đăng ký. Hãy đăng ký và kiểm tra lại.",
        "lang_changed": "✅ Đã đổi ngôn ngữ sang: {lang}",
        "select_lang": "🌐 Vui lòng chọn ngôn ngữ:",
        "ai_response_header": "💬 Phản hồi của AI:",
        "image_ready_header": "🎨 Hình ảnh đã sẵn sàng!",
        "image_prompt_label": "📝 Văn bản:",
        "image_count_label": "🔢 Số lượng:",
        "image_time_label": "⏰ Thời gian (UTC+5):",
        "image_elapsed_label": "⏱ Thời gian tạo:",
        "choose_action": "Chọn một trong những tùy chọn sau:",
        "your_message": "💬 Tin nhắn của bạn:",
        "admin_new_generation": "🎨 *Thế hệ mới!*",
        "admin_user": "👤 *Người dùng:*",
        "admin_prompt": "📝 *Văn bản:*",
        "admin_count": "🔢 *Số lượng:*",
        "admin_image_id": "🆔 *ID Hình ảnh:*",
        "admin_time": "⏰ *Thời gian \\(UTC\\+5\\):*",
    },
}
DEFAULT_LANGUAGE = "uz"

# ---------------- i18n helper: missing kalitlar default tilga fallback qiladi ----------------
def get_lang(lang_code=None):
    base = LANGUAGES.get(DEFAULT_LANGUAGE, {})
    cur = LANGUAGES.get(lang_code or DEFAULT_LANGUAGE, {})
    return ChainMap(cur, base)

# Hamma tillarda kamchilik bo'lsa ham bot ishlashi uchun default kalitlarni to'ldirib chiqamiz
try:
    _base = LANGUAGES.get(DEFAULT_LANGUAGE, {})
    for _code, _d in LANGUAGES.items():
        if _d is _base:
            continue
        for _k, _v in _base.items():
            _d.setdefault(_k, _v)
except Exception as _e:
    logger.warning(f"[LANG FILL WARNING] {_e}")

# Quota matnlari (kamida uz/en/ru)
try:
    LANGUAGES.setdefault("uz", {}).setdefault("generating_content", "✨ Generating...")
    LANGUAGES.setdefault("uz", {}).setdefault("quota_reached",
        "⚠️ *Kunlik limit tugadi!*\n\n"
        "• Limit: *{limit}*\n"
        "• Bugun ishlatildi: *{used}*\n"
        "• Qo'shimcha rasm kerak: *{need}*\n"
        "• Sizdagi kredit: *{credits}*"
    )
    LANGUAGES.setdefault("uz", {}).setdefault("quota_reset", "🕛 Kunlik limit har kuni 00:00 (UTC+5) da yangilanadi.")
    LANGUAGES.setdefault("uz", {}).setdefault("quota_pack_thanks", "✅ To'lov qabul qilindi! +{credits} ta qo'shimcha rasm limiti qo'shildi.")

    LANGUAGES.setdefault("en", {}).setdefault("generating_content", "✨ Generating...")
    LANGUAGES.setdefault("en", {}).setdefault("quota_reached",
        "⚠️ *Daily limit reached!*\n\n"
        "• Limit: *{limit}*\n"
        "• Used today: *{used}*\n"
        "• Extra needed: *{need}*\n"
        "• Your credits: *{credits}*"
    )
    LANGUAGES.setdefault("en", {}).setdefault("quota_reset", "🕛 Daily limit resets at 00:00 (UTC+5).")
    LANGUAGES.setdefault("en", {}).setdefault("quota_pack_thanks", "✅ Payment received! +{credits} extra images added.")

    LANGUAGES.setdefault("ru", {}).setdefault("generating_content", "✨ Генерирую...")
    LANGUAGES.setdefault("ru", {}).setdefault("quota_reached",
        "⚠️ *Дневной лимит исчерпан!*\n\n"
        "• Лимит: *{limit}*\n"
        "• Сегодня использовано: *{used}*\n"
        "• Нужно дополнительно: *{need}*\n"
        "• Ваши кредиты: *{credits}*"
    )
    LANGUAGES.setdefault("ru", {}).setdefault("quota_reset", "🕛 Лимит обновляется каждый день в 00:00 (UTC+5).")
    LANGUAGES.setdefault("ru", {}).setdefault("quota_pack_thanks", "✅ Оплата получена! Добавлено +{credits} изображений.")
except Exception as _e:
    logger.warning(f"[QUOTA LANG WARNING] {_e}")


# ---------------- Daily quota ----------------
DAILY_FREE_IMAGES = int(os.getenv("DAILY_FREE_IMAGES", "50"))
EXTRA_PACK_SIZE = int(os.getenv("EXTRA_PACK_SIZE", "50"))
# 50 ta rasm = 50 Stars (1 rasm = 1 Star)
EXTRA_PACK_PRICE_STARS = int(os.getenv("EXTRA_PACK_PRICE_STARS", "50"))

def tashkent_day_start_utc(now=None):
    now = now or utc_now()
    local = now + timedelta(hours=5)
    local_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start - timedelta(hours=5)

async def get_user_daily_images(pool, user_id):
    start_utc = tashkent_day_start_utc()
    async with pool.acquire() as conn:
        return int(await conn.fetchval(
            "SELECT COALESCE(SUM(image_count), 0) FROM generations WHERE user_id=$1 AND created_at >= $2",
            user_id, start_utc
        ) or 0)

async def get_user_extra_credits(pool, user_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT extra_credits FROM users WHERE id=$1", user_id)
        return int(row["extra_credits"] or 0) if row else 0

async def reserve_quota_or_explain(pool, user_id, requested):
    """Agar kerak bo'lsa extra_credits dan yechadi. Yetmasa: False + info qaytaradi."""
    start_utc = tashkent_day_start_utc()
    async with pool.acquire() as conn:
        u = await conn.fetchrow("SELECT is_banned, extra_credits FROM users WHERE id=$1", user_id)
        if u and u["is_banned"]:
            return False, {"reason": "banned"}
        used = int(await conn.fetchval(
            "SELECT COALESCE(SUM(image_count), 0) FROM generations WHERE user_id=$1 AND created_at >= $2",
            user_id, start_utc
        ) or 0)
        credits = int((u["extra_credits"] if u else 0) or 0)
        need_paid = max(used + requested - DAILY_FREE_IMAGES, 0)
        if need_paid <= 0:
            return True, {"used": used, "credits": credits, "need_paid": 0}
        if credits >= need_paid:
            await conn.execute("UPDATE users SET extra_credits = extra_credits - $1 WHERE id = $2", need_paid, user_id)
            return True, {"used": used, "credits": credits - need_paid, "need_paid": need_paid}
        return False, {"reason": "quota", "used": used, "credits": credits, "need_paid": need_paid}

DIGEN_MODELS = [
    {
        "id": "",
        "title": "🖼 Oddiy uslub",
        "description": "Hech qanday maxsus effektlarsiz, tabiiy va sof tasvir yaratadi.",
        "background_prompts": [
            "high quality, 8k, sharp focus, natural lighting",
            "photorealistic, detailed, vibrant colors, professional photography",
            "clean background, studio lighting, ultra-detailed"
        ]
    },
    {
        "id": "86",
        "title": "🧸 Kawaii Figuralar",
        "description": "Juda yoqimli va o‘yinchoq uslubidagi shirin rasm turlari.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/kawaii.webp",
        "background_prompts": [
            "kawaii style, soft pastel colors, chibi character, cute toy aesthetic",
            "adorable expressions, bright background, playful composition",
            "round shapes, big eyes, cozy and cheerful mood"
        ]
    },
    {
        "id": "89",
        "title": "🎨 Fluxlisimo Chizmasi",
        "description": "Yaponcha manga uslubida yaratilgan detalli, badiiy portretlar va illyustratsiyalar.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/fluxlisimo.webp",
        "background_prompts": [
            "manga illustration, detailed lines, artistic shading, elegant composition",
            "Japanese art style, high contrast, expressive pose, brush texture",
            "sketch aesthetic, delicate ink work, moody atmosphere"
        ]
    },
    {
        "id": "88",
        "title": "🏛 Klassik San’at (Gustave)",
        "description": "Klassik va nafis san’at uslubida yaratilgan rasmlar.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/gustave.webp",
        "background_prompts": [
            "classical painting, oil texture, Renaissance style, realistic anatomy",
            "fine art portrait, baroque lighting, golden tones, museum quality",
            "dramatic composition, chiaroscuro, detailed brushwork"
        ]
    },
    {
        "id": "87",
        "title": "🧱 LEGO Dunyo",
        "description": "LEGO bloklari uslubidagi qiziqarli va rangli tasvirlar.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/lego.webp",
        "background_prompts": [
            "LEGO bricks, toy aesthetic, colorful blocks, plastic texture",
            "miniature city, bright lighting, 3D render style",
            "creative lego build, playful environment, high detail"
        ]
    },
    {
        "id": "82",
        "title": "🌌 Galaktik Qo‘riqchi",
        "description": "Koinot va mexanika uyg‘unligidagi kuchli, sirli uslub.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/40k.webp",
        "background_prompts": [
            "sci-fi, galactic armor, cosmic background, glowing effects",
            "space battle, futuristic lighting, metallic reflections",
            "astral energy, nebula sky, cinematic atmosphere"
        ]
    },
    {
        "id": "81",
        "title": "🌑 Qorong‘u Sehr (Dark Allure)",
        "description": "Sirli, jozibali va qorong‘u estetika bilan bezatilgan tasvirlar.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/evil.webp",
        "background_prompts": [
            "dark fantasy, gothic atmosphere, shadow play, mystical lighting",
            "eerie mood, glowing eyes, moody color palette",
            "smoky environment, dramatic shadows, ethereal presence"
        ]
    },
    {
        "id": "83",
        "title": "👁 Lahzani His Et (In the Moment)",
        "description": "Haqiqiy his-tuyg‘ularni jonli tasvirlar orqali ifodalaydi.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/fp.webp",
        "background_prompts": [
            "emotional realism, cinematic lighting, soft focus",
            "authentic expressions, natural pose, human warmth",
            "intimate moment, detailed eyes, storytelling portrait"
        ]
    },
    {
        "id": "84",
        "title": "🎭 Anime Fantom",
        "description": "Rang-barang, jonli va ifodali anime uslubidagi tasvirlar.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/niji.webp",
        "background_prompts": [
            "anime style, vibrant colors, cel shading, detailed eyes, fantasy background",
            "Japanese anime, dynamic pose, soft lighting, dreamy atmosphere",
            "manga illustration, expressive character, pastel colors, whimsical"
        ]
    },
    {
        "id": "85",
        "title": "✨ Ghibli Sehrli Olami",
        "description": "Ghibli filmlariga xos mo‘jizaviy, iliq va sehrli muhit yaratadi.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/ghibli.webp",
        "background_prompts": [
            "Studio Ghibli style, soft watercolor, magical forest, warm sunlight",
            "whimsical landscape, floating islands, gentle breeze, hand-painted",
            "enchanted meadow, golden hour, fluffy clouds, nostalgic mood"
        ]
    },
    {
        "id": "79",
        "title": "🧙 Sehrgarlar Olami (Sorcerers)",
        "description": "Sehrgarlar va afsonaviy mavjudotlar bilan to‘la fantaziya dunyosi.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/w1.webp",
        "background_prompts": [
            "fantasy world, magic spells, glowing runes, epic wizard",
            "enchanted castle, ancient symbols, mysterious energy",
            "arcane magic, mystical forest, cinematic fantasy lighting"
        ]
    },
    {
        "id": "80",
        "title": "🧚 Afsonaviy Dunyolar (Mythos)",
        "description": "Afsonalar va fantaziya uyg‘unligidagi go‘zal, nafis tasvirlar.",
        "preview_image": "https://rm2-asset.s3.us-west-1.amazonaws.com/flux-lora/images/mythic.webp",
        "background_prompts": [
            "mythical creatures, ethereal light, elegant composition",
            "ancient legend, divine aura, soft colors, fantasy setting",
            "dreamlike world, shimmering atmosphere, celestial tones"
        ]
    }
]

#---------------------------------------------
# Admin qidiruv uchun maxsus handler
async def admin_user_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.user_data.get("admin_search_mode"):
        return
    context.user_data["admin_search_mode"] = False

    query = (update.message.text or "").strip()
    user_id = None
    username = None
    try:
        user_id = int(query)
    except ValueError:
        username = query[1:] if query.startswith("@") else query

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        if user_id is not None:
            user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        elif username:
            user = await conn.fetchrow("SELECT id FROM users WHERE username = $1", username)
        else:
            user = None

    if not user:
        await update.message.reply_text("❌ Foydalanuvchi topilmadi.")
        return

    await admin_show_user_card(context, int(user["id"]), message=update.message)

#-------------------------------------------
async def random_anime_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
        chat_id = q.message.chat_id
        user_id = q.from_user.id
    else:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

    # Tilni olish
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    # Progress xabar
    progress_msg = await context.bot.send_message(chat_id, "🔄AI anime rasmi yuklanmoqda...")

    temp_files = []
    image_urls = []
    try:
        seeds = [random.randint(1, 100000) for _ in range(10)]
        base_url = "https://www.thiswaifudoesnotexist.net/example-{}.jpg"

        async with aiohttp.ClientSession() as session:
            for seed in seeds:
                url = base_url.format(seed)
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
                            temp_path = f"/tmp/anime_{uuid.uuid4().hex}.jpg"
                            with open(temp_path, "wb") as f:
                                f.write(image_data)
                            temp_files.append(temp_path)
                            image_urls.append(url)
                except Exception as e:
                    logger.warning(f"[ANIME] Rasm yuklanmadi (seed={seed}): {e}")
                    continue

        if not image_urls:
            await progress_msg.edit_text("⚠️ Hech qanday rasm topilmadi. Qayta urinib ko'ring.")
            return

        # Media group tayyorlash — caption faqat birinchi rasmga
        media = []
        caption = "👤 **Bu rasmlar HAQIQIY EMAS!**\n🤖 Hammasi sun'iy intellekt (AI) tomonidan yaratilgan."
        for i, path in enumerate(temp_files):
            with open(path, "rb") as f:
                if i == 0:
                    media.append(InputMediaPhoto(media=f, caption=caption, parse_mode="Markdown"))
                else:
                    media.append(InputMediaPhoto(media=f))

        # Rasm(lar)ni yuborish
        await context.bot.send_media_group(chat_id=chat_id, media=media)
        await progress_msg.delete()

        # ✅ Bitta xabar: "✅ Tayyor!" + tugmalar
        final_text = "✅ Tayyor!"
        kb = [
            [InlineKeyboardButton("🔄 Yangilash", callback_data="random_anime_refresh")],
            [InlineKeyboardButton(lang["back_to_main_button"], callback_data="back_to_main")]
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=final_text,
            reply_markup=InlineKeyboardMarkup(kb)
        )

    except Exception as e:
        logger.exception(f"[RANDOM ANIME ERROR] {e}")
        await progress_msg.edit_text(lang["error"])
    finally:
        # Keshni tozalash
        for f in temp_files:
            try:
                os.remove(f)
            except Exception as e:
                logger.warning(f"[CLEANUP] Faylni o'chirib bo'lmadi: {f} — {e}")

async def random_anime_refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # Eski xabarni o'chiramiz (ixtiyoriy)
    try:
        await q.message.delete()
    except:
        pass
    # Yangi rasmlarni yuborish
    await random_anime_handler(update, context)
#--------------------------------------------
async def fake_lab_new_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    await q.message.reply_text(lang["fake_lab_generating"], parse_mode="Markdown")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://thispersondoesnotexist.com/",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Status {resp.status}")
                image_data = await resp.read()

        temp_path = f"/tmp/fake_lab_{uuid.uuid4().hex}.jpg"
        with open(temp_path, "wb") as f:
            f.write(image_data)

        # Chiroyli caption
        caption = (
            "👤 **Bu odam HAQIQIY EMAS!**\n"
            "🤖 U sun'iy intellekt (AI) tomonidan yaratilgan.\n\n"
            "🔄 **Yangilash** tugmasi orqali yangi rasm olishingiz mumkin."
        )

        kb = [
            [InlineKeyboardButton("Yangilash", callback_data="fake_lab_refresh")],
            [InlineKeyboardButton("Orqaga", callback_data="back_to_main")]
        ]

        with open(temp_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=photo,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )

        context.user_data["fake_lab_last_photo"] = temp_path

    except Exception as e:
        logger.exception(f"[FAKE LAB ERROR] {e}")
        await q.message.reply_text(lang["error"])

async def fake_lab_refresh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # Til sozlamasini olish
    lang = context.user_data.get("lang", {
        "fake_lab_refreshing": "🔄 Qayta ishlanmoqda... Iltimos kuting."
    })

    # Progress
    await q.edit_message_caption(caption=lang["fake_lab_refreshing"], parse_mode="Markdown")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://thispersondoesnotexist.com/",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"Status {resp.status}")
                image_data = await resp.read()

        temp_path = f"/tmp/fake_lab_{uuid.uuid4().hex}.jpg"
        with open(temp_path, "wb") as f:
            f.write(image_data)

        # ✅ To‘g‘ri indentation — bu kod try ichida
        caption = (
            "👤 **Bu odam HAQIQIY EMAS!**\n"
            "🤖 U sun'iy intellekt (AI) tomonidan yaratilgan.\n\n"
            "🔄 **Yangilash** tugmasi orqali yangi rasm olishingiz mumkin."
        )

        kb = [
            [InlineKeyboardButton("🔄 Yangilash", callback_data="fake_lab_refresh")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_main")]
        ]

        with open(temp_path, "rb") as photo:
            await q.edit_message_media(
                media=InputMediaPhoto(media=photo, caption=caption, parse_mode="Markdown"),
                reply_markup=InlineKeyboardMarkup(kb)
            )

        context.user_data["fake_lab_last_photo"] = temp_path

    except Exception as e:
        logger.exception(f"[FAKE LAB REFRESH ERROR] {e}")
        await q.edit_message_caption(
            caption="⚠️ **Xatolik yuz berdi.**\nQayta urinib ko'ring.",
            parse_mode="Markdown"
        )

# ---------------- helpers ----------------
def escape_md(text: str) -> str:
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
    is_banned BOOLEAN DEFAULT FALSE,
    language_code TEXT DEFAULT 'uz',
    image_model_id TEXT DEFAULT '',
    extra_credits INT DEFAULT 0
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
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE")
            logger.info("✅ Added column 'is_banned' to table 'users'")
        except Exception as e:
            logger.info(f"ℹ️ Column 'is_banned' already exists or error: {e}")

        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS image_model_id TEXT DEFAULT ''")
            logger.info("✅ Added column 'image_model_id' to table 'users'")
        except Exception as e:
            logger.info(f"ℹ️ Column 'image_model_id' already exists or error: {e}")

        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_credits INT DEFAULT 0")
            logger.info("✅ Added column 'extra_credits' to table 'users'")
        except Exception as e:
            logger.info(f"ℹ️ Column 'extra_credits' already exists or error: {e}")
        try:
            await conn.execute("ALTER TABLE donations ADD COLUMN IF NOT EXISTS charge_id TEXT")
            await conn.execute("ALTER TABLE donations ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ")
            logger.info("✅ Added columns 'charge_id', 'refunded_at' to table 'donations'")
        except Exception as e:
            logger.info(f"ℹ️ Columns already exist or error: {e}")

# ---------------- Digen headers ----------------
import threading

# Global indeks va lock
_digen_key_index = 0
_digen_lock = threading.Lock()

def get_digen_headers():
    global _digen_key_index
    if not DIGEN_KEYS:
        return {}
    with _digen_lock:
        key = DIGEN_KEYS[_digen_key_index % len(DIGEN_KEYS)]
        _digen_key_index += 1
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "digen-language": "en-US",
        "digen-platform": "web",
        "digen-token": key.get("token", ""),
        "digen-sessionid": key.get("session", ""),
        "origin": "https://digen.ai",
        "referer": "https://digen.ai/image",
    }


#--------------------------
async def check_ban(user_id: int, pool) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_banned FROM users WHERE id = $1", user_id)
        if row and row["is_banned"]:
            return True
    return False
# ---------------- subscription check ----------------
async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Foydalanuvchi barcha majburiy kanallarga obuna bo'lganligini tekshiradi.
    """
    for channel in MANDATORY_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel["id"], user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception as e:
            logger.debug(f"[SUB CHECK ERROR] Kanal {channel['id']}: {e}")
            return False
    return True
    
async def force_sub_if_private(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_code=None) -> bool:
    if update.effective_chat.type != "private":
        return True
    ok = await check_subscription(update.effective_user.id, context)
    if not ok:
        lang = get_lang(lang_code) if lang_code else LANGUAGES[DEFAULT_LANGUAGE]
        kb = []
        # Barcha kanallar uchun tugmalar
        for channel in MANDATORY_CHANNELS:
            kb.append([InlineKeyboardButton(
                f"{lang['sub_url_text']} {channel['username']}",
                url=f"https://t.me/{channel['username'].strip('@')}"
            )])
        kb.append([InlineKeyboardButton(lang["sub_check"], callback_data="check_sub")])
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
    lang = get_lang(lang_code)
    if await check_subscription(user_id, context):
        await q.edit_message_text(lang["sub_thanks"])
    else:
        kb = []
        for channel in MANDATORY_CHANNELS:
            kb.append([InlineKeyboardButton(
                f"{lang['sub_url_text']} {channel['username']}",
                url=f"https://t.me/{channel['username'].strip('@')}"
            )])
        kb.append([InlineKeyboardButton(lang["sub_check"], callback_data="check_sub")])
        await q.edit_message_text(lang["sub_still_not"], reply_markup=InlineKeyboardMarkup(kb))

# ---------------- DB user/session/logging ----------------
async def add_user_db(pool, tg_user, lang_code=None, image_model_id=None):
    now = utc_now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", tg_user.id)
        if row:
            updates = []
            params = []
            idx = 1
            if lang_code is not None:
                updates.append(f"language_code=${idx}")
                params.append(lang_code)
                idx += 1
            if image_model_id is not None:
                updates.append(f"image_model_id=${idx}")
                params.append(image_model_id)
                idx += 1
            updates.append(f"username=${idx}")
            updates.append(f"last_seen=${idx+1}")
            params.extend([tg_user.username if tg_user.username else None, now, tg_user.id])
            if updates:
                query = f"UPDATE users SET {', '.join(updates)} WHERE id=${len(params)}"
                await conn.execute(query, *params)
        else:
            lang_code = lang_code or DEFAULT_LANGUAGE
            image_model_id = image_model_id or ""
            await conn.execute(
                "INSERT INTO users(id, username, first_seen, last_seen, language_code, image_model_id) "
                "VALUES($1,$2,$3,$4,$5,$6)",
                tg_user.id, tg_user.username if tg_user.username else None,
                now, now, lang_code, image_model_id
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

#-------------Sozlamalar--------------------
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    lang_code = DEFAULT_LANGUAGE
    image_model_id = ""
    
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow(
            "SELECT language_code, image_model_id FROM users WHERE id = $1", user_id
        )
        if row:
            lang_code = row["language_code"] or DEFAULT_LANGUAGE
            image_model_id = row["image_model_id"] or ""

    lang = get_lang(lang_code)
    current_model_title = "Default Mode"
    for m in DIGEN_MODELS:
        if m["id"] == image_model_id:
            current_model_title = m["title"]
            break

    text = "⚙️ **Sozlamalar**"  # caption
    kb = [
        [InlineKeyboardButton(f"🖼 Image Model: {current_model_title}", callback_data="select_image_model")],
        [InlineKeyboardButton(lang["back_to_main_button"], callback_data="back_to_main")]
    ]

    # Xabarni tahrirlashda xatolikka chidamli bo'lish
    try:
        await q.edit_message_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except BadRequest as e:
        if "message is not modified" in str(e):
            pass
        elif "There is no text in the message to edit" in str(e):
            await q.message.reply_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            try:
                await q.message.delete()
            except:
                pass
        else:
            raise
#--------------------------------------------------
async def confirm_model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    model_id = q.data.split("_", 2)[2]
    model = next((m for m in DIGEN_MODELS if m["id"] == model_id), None)
    if not model:
        return

    kb = [
        [InlineKeyboardButton("✅ Tanlash", callback_data=f"set_model_{model_id}")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="select_image_model")]
    ]
    caption = (
        f"🖼 **{model['title']}**\n"
        f"{model['description']}\n"
        "Tanlaysizmi?"
    )
    photo_url = model.get("preview_image", "https://via.placeholder.com/600x600.png?text=Preview")

    try:
        await q.message.edit_media(
            media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode="Markdown"),
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except BadRequest as e:
        if "message is not modified" in str(e):
            pass
        elif "message to edit is not a media message" in str(e):
            # Eski xabar media emas — oddiy matn sifatida tahrirlash
            await q.edit_message_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            logger.error(f"[CONFIRM_MODEL] Unknown error: {e}")
            await q.edit_message_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.exception(f"[CONFIRM_MODEL] Unexpected error: {e}")
        await q.edit_message_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
async def set_image_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    model_id = q.data.split("_", 2)[2]
    user = q.from_user
    # DB ga saqlash
    await add_user_db(context.application.bot_data["db_pool"], user, image_model_id=model_id)

    # Eski xabarni tahrirlash o'rniga, yangi xabar yuborish
    user_id = user.id
    lang_code = DEFAULT_LANGUAGE
    image_model_id = ""
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow(
            "SELECT language_code, image_model_id FROM users WHERE id = $1", user_id
        )
        if row:
            lang_code = row["language_code"] or DEFAULT_LANGUAGE
            image_model_id = row["image_model_id"] or ""

    lang = get_lang(lang_code)
    current_model_title = "Default Mode"
    for m in DIGEN_MODELS:
        if m["id"] == image_model_id:
            current_model_title = m["title"]
            break

    text = "⚙️ **Sozlamalar**"
    kb = [
        [InlineKeyboardButton(f"🖼 Image Model: {current_model_title}", callback_data="select_image_model")],
        [InlineKeyboardButton(lang["back_to_main_button"], callback_data="back_to_main")]
    ]

    # Yangi xabar yuborish (eski xabarni tahrirlamaymiz)
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    
    # Eski xabarni o'chirish (ixtiyoriy)
    try:
        await q.message.delete()
    except:
        pass
#------------------------------------------------
async def select_image_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = []
    models = DIGEN_MODELS
    for i in range(0, len(models), 2):
        row = [
            InlineKeyboardButton(models[i]["title"], callback_data=f"confirm_model_{models[i]['id']}")
        ]
        if i + 1 < len(models):
            row.append(
                InlineKeyboardButton(models[i+1]["title"], callback_data=f"confirm_model_{models[i+1]['id']}")
            )
        kb.append(row)
    kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_settings")])
    caption = (
        "🖼 **Image Modelni tanlang**\n"
        "Har bir model o‘ziga xos uslubda rasm yaratadi. "
        "O‘zingizga yoqqanini tanlang 👇"
    )
    # Har doim ishlaydigan placeholder rasm
    photo_url = "https://via.placeholder.com/600x600.png?text=Model+Preview"
    
    # Xavfsiz edit_media + fallback
    try:
        await q.message.edit_media(
            media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode="Markdown"),
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except BadRequest as e:
        error_msg = str(e).lower()
        if "wrong type" in error_msg or "message to edit is not a media message" in error_msg:
            # Yangi xabar yuborish
            await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            try:
                await q.message.delete()
            except:
                pass
        else:
            logger.error(f"[SELECT_MODEL] Boshqa xato: {e}")
            await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.exception(f"[SELECT_MODEL] Kutilmagan xato: {e}")
        await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def confirm_model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    model_id = q.data.split("_", 2)[2]
    model = next((m for m in DIGEN_MODELS if m["id"] == model_id), None)
    if not model:
        return

    kb = [
        [InlineKeyboardButton("✅ Tanlash", callback_data=f"set_model_{model_id}")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="select_image_model")]
    ]
    caption = (
        f"🖼 **{model['title']}**\n"
        f"{model['description']}\n"
        "Tanlaysizmi?"
    )
    photo_url = model.get("preview_image") or "https://via.placeholder.com/600x600.png?text=Preview"

    try:
        await q.message.edit_media(
            media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode="Markdown"),
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except BadRequest as e:
        error_msg = str(e).lower()
        if "wrong type" in error_msg or "message to edit is not a media message" in error_msg:
            await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            try:
                await q.message.delete()
            except:
                pass
        else:
            logger.error(f"[CONFIRM_MODEL] Boshqa xato: {e}")
            await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.exception(f"[CONFIRM_MODEL] Kutilmagan xato: {e}")
        await q.message.reply_text(caption, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
# ---------------- Tilni o'zgartirish handleri ----------------
async def notify_admin_generation(context: ContextTypes.DEFAULT_TYPE, user, prompt, image_urls, count, image_id):
    if not ADMIN_ID:
        return  # Agar ADMIN_ID o'rnatilmagan bo'lsa, hech narsa yuborilmaydi

    try:
        # Foydalanuvchi tilini olish
        lang_code = DEFAULT_LANGUAGE
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", ADMIN_ID)
            if row:
                lang_code = row["language_code"]
        lang = get_lang(lang_code)

        tashkent_dt = tashkent_time()

        # Admin uchun xabar matni
        caption_text = (
            f"🎨 <b>Yangi generatsiya!</b>\n\n"
            f"👤 <b>Foydalanuvchi:</b> @{user.username if user.username else 'N/A'} "
            f"(ID: <code>{user.id}</code>)\n"
            f"📝 <b>Prompt:</b> <code>{prompt}</code>\n"
            f"🔢 <b>Soni:</b> {count}\n"
            f"🆔 <b>Image ID:</b> <code>{image_id}</code>\n"
            f"⏰ <b>Vaqt (UTC+5):</b> {tashkent_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Agar rasm mavjud bo‘lsa — bitta media group sifatida yuboramiz
        if image_urls:
            media = []
            for i, url in enumerate(image_urls):
                if i == 0:
                    # Faqat birinchi rasm caption bilan bo‘ladi
                    media.append(InputMediaPhoto(media=url, caption=caption_text, parse_mode="HTML"))
                else:
                    media.append(InputMediaPhoto(media=url))

            await context.bot.send_media_group(chat_id=ADMIN_ID, media=media)
            logger.info(f"[ADMIN NOTIFY] Foydalanuvchi {user.id} uchun {len(image_urls)} ta rasm media group sifatida yuborildi.")

        else:
            # Rasm yo'q — faqat matn yuboriladi
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=caption_text,
                parse_mode="HTML"
            )
            logger.info(f"[ADMIN NOTIFY] Foydalanuvchi {user.id} uchun faqat matn yuborildi (rasm yo‘q).")

    except Exception as e:
        logger.exception(f"[ADMIN NOTIFY ERROR] Umumiy xato: {e}")

#---------------------------------------------------------------

async def notify_admin_on_error(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    prompt: str,
    digen_headers: dict,
    error: Exception,
    image_count: int = 1
):
    if not ADMIN_ID:
        return

    try:
        lang_code = DEFAULT_LANGUAGE
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", ADMIN_ID)
            if row:
                lang_code = row["language_code"]
        lang = get_lang(lang_code)

        tashkent_dt = tashkent_time()
        token = digen_headers.get("digen-token", "N/A")
        session_id = digen_headers.get("digen-sessionid", "N/A")

        error_text = (
            f"🚨 **Xatolik: Rasm generatsiyasi muvaffaqiyatsiz tugadi!**\n\n"
            f"👤 **Foydalanuvchi:** @{user.username or 'N/A'} (ID: `{user.id}`)\n"
            f"📝 **Prompt:** `{prompt}`\n"
            f"🔢 **Soni:** {image_count}\n"
            f"🔑 **Token:** `{token}`\n"
            f"🆔 **Session ID:** `{session_id}`\n"
            f"⏰ **Vaqt (UTC+5):** {tashkent_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"❌ **Xatolik:** `{str(error)}`"
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=error_text,
            parse_mode="Markdown"
        )
        logger.info(f"[ADMIN ERROR NOTIFY] Foydalanuvchi {user.id} uchun xatolik haqida xabar yuborildi.")
    except Exception as e:
        logger.exception(f"[ADMIN ERROR NOTIFY FAILED] {e}")
# ---------------- Tilni o'zgartirish handleri ----------------
async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Tugmalarni 2 ustunda, oxirgi tugma alohida qatorga joylashtiramiz
    kb = [
        [InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
         InlineKeyboardButton("🇮🇩 Bahasa Indonesia", callback_data="lang_id")],
        [InlineKeyboardButton("🇱🇹 Lietuvių", callback_data="lang_lt"),
         InlineKeyboardButton("🇲🇽 Español (LatAm)", callback_data="lang_esmx")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_eses"),
         InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it")],
        [InlineKeyboardButton("🇨🇳 简体中文", callback_data="lang_zhcn"),
         InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")],
        [InlineKeyboardButton("🇮🇳 हिंदी", callback_data="lang_hi"),
         InlineKeyboardButton("🇧🇷 Português", callback_data="lang_ptbr")],
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
         InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk")],
        [InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang_vi")]  # ✅ Faqat bitta qavslar [...]
    ]
    lang_code = DEFAULT_LANGUAGE
    if update.effective_chat.type == "private":
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
            if row:
                lang_code = row["language_code"]
    lang = get_lang(lang_code)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(lang["select_lang"], reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(lang["select_lang"], reply_markup=InlineKeyboardMarkup(kb))
    return LANGUAGE_SELECT
async def language_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = q.data.split("_", 1)[1]
    user = q.from_user

    # Foydalanuvchini bazaga yozamiz
    await add_user_db(context.application.bot_data["db_pool"], user, lang_code)

    # Tilni olish
    lang = get_lang(lang_code)

    # Keyboard yaratish
    kb = [
        [
            InlineKeyboardButton(lang["gen_button"], callback_data="start_gen"),
            InlineKeyboardButton(lang["ai_button"], callback_data="start_ai_flow")
        ],
        [
            InlineKeyboardButton(lang["donate_button"], callback_data="donate_custom"),
            InlineKeyboardButton(lang["lang_button"], callback_data="change_language")
        ],
        [
            InlineKeyboardButton("📈 Statistika", callback_data="show_stats"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="open_settings")
        ],
        [
            InlineKeyboardButton("🧪 FakeLab", callback_data="fake_lab_new"),
            InlineKeyboardButton("🎨 Random AI Anime", callback_data="random_anime")
        ],
    ]

    # Faqat admin uchun tugma qo‘shamiz
    if user.id == ADMIN_ID:
        kb.insert(-1, [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")])

    # Til o‘zgarganligini xabar qilish
    await q.edit_message_text(
        text=lang["lang_changed"].format(lang=lang["name"]),
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang_code = None
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)
    kb = [
        [
            InlineKeyboardButton(lang["gen_button"], callback_data="start_gen"),
            InlineKeyboardButton(lang["ai_button"], callback_data="start_ai_flow")
        ],
        [
            InlineKeyboardButton(lang["donate_button"], callback_data="donate_custom"),
            InlineKeyboardButton(lang["lang_button"], callback_data="change_language")
        ],
        [
            InlineKeyboardButton("📈 Statistika", callback_data="show_stats"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="open_settings")
        ],
        [
            InlineKeyboardButton("🧪 FakeLab", callback_data="fake_lab_new"),
            InlineKeyboardButton("🎨 Random AI Anime", callback_data="random_anime")
        ],
    ]
    if user_id == ADMIN_ID:
        kb.insert(-1, [InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")])

    text = lang["welcome"]
    reply_markup = InlineKeyboardMarkup(kb)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
        except BadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)
# ---------------- Bosh menyudan AI chat ----------------
async def start_ai_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)
    # Faqat bitta marta, tarjima qilingan xabarni yuborish
    await q.message.reply_text(lang["ai_prompt_text"])
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
    lang = get_lang(lang_code)
    await q.message.reply_text(lang["prompt_text"])
    # flow o'zgaruvchisini o'rnatamiz
    context.user_data["flow"] = "image_pending_prompt"
# ---------------- Bosh menyuga qaytish tugmasi ----------------
async def handle_change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_language(update, context)

# /get command
# /get command
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang_code = DEFAULT_LANGUAGE
    if update.effective_chat.type == "private":
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
            if row:
                lang_code = row["language_code"]
    lang = get_lang(lang_code)
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
            await update.message.reply_text("✍️ Iltimos, rasm uchun matn yozing.")
            return
        prompt = " ".join(context.args)
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = prompt

    # Tugmalarni yonma-yon qilish uchun bitta qatorga joylashtiramiz
    kb = [
        [
            InlineKeyboardButton("1️⃣", callback_data="count_1"),
            InlineKeyboardButton("2️⃣", callback_data="count_2")
        ]
    ]

    await update.message.reply_text(
        f"{lang['select_count']}\n🖌 Sizning matningiz:\n{escape_md(prompt)}",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# Private plain text -> prompt + inline buttons yoki AI chat
# Yangilangan: Tanlov tugmachasi bosilganda flow o'rnatiladi
# Private plain text -> prompt + inline buttons yoki AI chat
# Yangilangan: Tanlov tugmachasi bosilganda flow o'rnatiladi
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    # Agar foydalanuvchi oldin "AI chat" tugmasini bosgan bo'lsa
    flow = context.user_data.get("flow")
    if flow == "ai":
        last_active = context.user_data.get("last_active")
        now = datetime.now(timezone.utc)
        if last_active:
            if (now - last_active).total_seconds() > 900:
                context.user_data["flow"] = None
                context.user_data["last_active"] = None
            else:
                prompt = update.message.text
                await update.message.reply_text("🧠 AI javob bermoqda...")
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
                except Exception:
                    logger.exception("[GEMINI ERROR]")
                    answer = lang["error"]
                await update.message.reply_text(f"{lang['ai_response_header']}\n{answer}")
                context.user_data["last_active"] = datetime.now(timezone.utc)
                return
        else:
            prompt = update.message.text
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
            except Exception:
                logger.exception("[GEMINI ERROR]")
                answer = lang["error"]
            await update.message.reply_text(f"{lang['ai_response_header']}\n{answer}")
            context.user_data["last_active"] = datetime.now(timezone.utc)
            return

    # Agar hech qanday maxsus flow bo'lmasa, oddiy rasm generatsiya jarayoni ketaveradi
    if not await force_sub_if_private(update, context, lang_code):
        return

    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data["prompt"] = prompt

    # --- Promptni Gemini orqali tarjima qilish ---
    original_prompt = prompt
    gemini_instruction = "Automatically detect the user’s language and translate it into English. Convert the text into a professional, detailed image-generation prompt with realistic, cinematic, and descriptive style. Focus on atmosphere, lighting, color, and composition. Return only the final English prompt. Do not include any explanations or extra text :"
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

        # ✅ Mantiqiy rad etishlarni tekshirish
        if digen_ready_prompt and not any(phrase in digen_ready_prompt.lower() for phrase in [
            "i cannot",
            "sorry",
            "i'm sorry",
            "i am sorry",
            "i am programmed",
            "harmless ai",
            "not allowed",
            "unable to",
            "can't assist",
            "not appropriate",
            "refuse to",
            "against my guidelines",
            "i don't",
            "i won't",
            "i do not"
        ]):
            context.user_data["translated"] = digen_ready_prompt
        else:
            logger.warning(f"[GEMINI FILTERED] Prompt rad etildi: '{original_prompt}' → '{digen_ready_prompt}'. Asl matn saqlanadi.")
            context.user_data["translated"] = original_prompt

    except Exception as gemini_err:
        logger.error(f"[GEMINI PROMPT ERROR] {gemini_err}")
        context.user_data["translated"] = original_prompt
    # --- Yangi tugadi ---

    # ❗ Mana shu qism funksiya ichida bo‘lishi shart
    if flow is None:
        context.user_data["flow"] = "image_pending_prompt"
        kb = [
            [
                InlineKeyboardButton("🖼 Rasm yaratish", callback_data="gen_image_from_prompt"),
                InlineKeyboardButton("💬 AI bilan suhbat", callback_data="ai_chat_from_prompt")
            ]
        ]
        await update.message.reply_text(
            f"{lang['choose_action']}\n*{lang['your_message']}* {escape_md(prompt)}",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return
    else:
        kb = [
            [
                InlineKeyboardButton("1️⃣", callback_data="count_1"),
                InlineKeyboardButton("2️⃣", callback_data="count_2"),
                InlineKeyboardButton("3️⃣", callback_data="count_3"),
                InlineKeyboardButton("4️⃣", callback_data="count_4")
            ]
        ]
        await update.message.reply_text(
            f"{lang['select_count']}\n🖌 Sizning matningiz:\n{escape_md(prompt)}",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
async def gen_image_from_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # flow: image
    context.user_data["flow"] = "image_pending_prompt"

    # Til
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    prompt = context.user_data.get("prompt", "")
    kb = [[
        InlineKeyboardButton("1️⃣", callback_data="count_1"),
        InlineKeyboardButton("2️⃣", callback_data="count_2")
    ]]

    await q.message.reply_text(
        f"{lang['select_count']}\n{lang.get('your_prompt_label', '🖌 Sizning matningiz:')}\n{escape_md(prompt)}",
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
    lang = get_lang(lang_code)
    # Faqat bitta marta, tarjima qilingan xabarni yuborish
    await q.message.reply_text(lang["ai_prompt_text"])
# ---------------- Digen headers (thread-safe) ----------------
_digen_key_index = 0
_digen_lock = threading.Lock()

def get_digen_headers():
    global _digen_key_index
    if not DIGEN_KEYS:
        return {}
    with _digen_lock:
        key = DIGEN_KEYS[_digen_key_index % len(DIGEN_KEYS)]
        _digen_key_index += 1
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "digen-language": "en-US",
        "digen-platform": "web",
        "digen-token": key.get("token", ""),
        "digen-sessionid": key.get("session", ""),
        "origin": "https://digen.ai/image",
        "referer": "https://digen.ai/image",
    }
# ---------------- Asosiy handler: generate_cb ----------------
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    pool = context.application.bot_data["db_pool"]

    # Til
    lang_code = DEFAULT_LANGUAGE
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", q.from_user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    try:
        count = int(q.data.split("_")[1])
    except Exception:
        await q.edit_message_text(lang["error"])
        return

    user = q.from_user
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", prompt)

    # --- Daily quota check ---
    ok, info = await reserve_quota_or_explain(pool, user.id, count)
    if not ok:
        reason = info.get("reason")
        if reason == "banned":
            await q.edit_message_text("⛔ Sizning akkauntingiz ban qilingan.")
            return

        if reason == "quota":
            used = int(info.get("used", 0))
            credits = int(info.get("credits", 0))
            need_paid = int(info.get("need_paid", 0))

            # pending generatsiya (to'lovdan keyin avtomatik davom ettirish uchun)
            context.user_data["pending_generation"] = {
                "prompt": prompt,
                "translated": translated,
                "count": count
            }

            reset_line = lang.get("quota_reset", "🕛 Kunlik limit har kuni 00:00 (UTC+5) da yangilanadi.")
            msg = lang.get(
                "quota_reached",
                """⚠️ *Kunlik limit tugadi!*

• Limit: *{limit}*
• Bugun ishlatildi: *{used}*
• Qo'shimcha rasm kerak: *{need}*
• Sizdagi kredit: *{credits}*

Qo'shimcha limit olish uchun Stars orqali pack xarid qiling."""
            ).format(limit=DAILY_FREE_IMAGES, used=used, need=need_paid, credits=credits)

            kb = [
                [InlineKeyboardButton(f"💫 +{EXTRA_PACK_SIZE} ta — {EXTRA_PACK_PRICE_STARS} ⭐", callback_data=f"buy_pack_{EXTRA_PACK_SIZE}")],
                [InlineKeyboardButton(f"💫 +{EXTRA_PACK_SIZE*2} ta — {EXTRA_PACK_PRICE_STARS*2} ⭐", callback_data=f"buy_pack_{EXTRA_PACK_SIZE*2}")],
                [InlineKeyboardButton(lang.get("back_to_main_button", "⬅️ Orqaga"), callback_data="back_to_main")]
            ]
            await q.edit_message_text(
                msg + "\n\n" + reset_line,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return

        await q.edit_message_text(lang["error"])
        return

    # 🔹 Foydalanuvchiga bitta xabar
    await q.edit_message_text(lang.get("generating_content", "✨ Generating your content... Please hold on a moment."))

    # 🔹 Orqa fonda generatsiya — progress yo‘q
    asyncio.create_task(
        _background_generate(
            context=context,
            user=user,
            prompt=prompt,
            translated=translated,
            count=count,
            chat_id=q.message.chat_id,
            lang=lang,
            paid_credits_used=int(info.get("need_paid", 0) or 0)
        )
    )

# ---------------- Orqa fonda generatsiya ----------------

async def _background_generate(context, user, prompt, translated, count, chat_id, lang, paid_credits_used=0):
    start_time = time.time()
    lora_id = ""
    background_prompt = ""

    # --- Modelni olish va background prompt tanlash ---
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT image_model_id FROM users WHERE id = $1", user.id)
        if row and row["image_model_id"]:
            lora_id = row["image_model_id"]
            selected_model = next((m for m in DIGEN_MODELS if m["id"] == lora_id), None)
            if selected_model and "background_prompts" in selected_model:
                background_prompt = random.choice(selected_model["background_prompts"])
        if not background_prompt:
            background_prompt = random.choice([
                "high quality, 8k, sharp focus",
                "ultra-detailed, professional photography",
                "cinematic lighting, vibrant colors"
            ])

    final_prompt = f"{translated}, {background_prompt}".strip()
    payload = {
        "prompt": final_prompt,
        "image_size": "768x1368",
        "width": 768,
        "height": 1368,
        "lora_id": lora_id,
        "batch_size": count,
        "model": "zimage",
        "resolution_model": "9:16",
        "reference_images": [],
        "strength": "0.9"
    }

    headers = get_digen_headers()

    async def _refund_if_needed():
        if paid_credits_used and int(paid_credits_used) > 0:
            try:
                async with context.application.bot_data["db_pool"].acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET extra_credits = COALESCE(extra_credits, 0) + $1 WHERE id = $2",
                        int(paid_credits_used), user.id
                    )
            except Exception as e:
                logger.warning(f"[CREDIT REFUND FAILED] {e}")

    try:
        # --- Digen API chaqiruvi ---
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=500)) as session:
            async with session.post(DIGEN_URL, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"[DIGEN ERROR] Status {resp.status}, Body: {await resp.text()}")
                    await context.bot.send_message(chat_id, lang["error"])
                    await _refund_if_needed()
                    return
                data = await resp.json()

        image_id = (data.get("data") or {}).get("id") or data.get("id")
        if not image_id:
            logger.error(f"[DIGEN] Image ID topilmadi. Javob: {data}")
            await context.bot.send_message(chat_id, lang["error"])
            await _refund_if_needed()
            return

       # ✅ To'g'ri versiya:
        image_id_clean = str(image_id).strip()
        urls = [f"https://liveme-image.s3.amazonaws.com/{image_id_clean}-{i}.jpeg".strip() for i in range(count)]
        logger.info(f"[GENERATE] Cleaned urls: {urls}")

        # --- Rasm tayyor bo‘lganligini sinab ko‘rish (30 soniya maks, 5 sek interval) ---
        image_ready = False
        for attempt in range(350):
            try:
                # Birinchi rasmni tekshiramiz
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=50)) as check_session:
                    async with check_session.head(urls[0], allow_redirects=True) as head_resp:
                        if head_resp.status == 200:
                            image_ready = True
                            break
            except Exception as e:
                logger.debug(f"[CHECK] Attempt {attempt+1}/30 failed for {urls[0]}: {e}")
            await asyncio.sleep(2)

        if not image_ready:
            # HEAD ishlamasa, GET sinab ko'rish (bir marta)
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=350)) as check_session:
                    async with check_session.get(urls[0], timeout=350) as get_resp:
                        if get_resp.status == 200:
                            image_ready = True
                        else:
                            logger.warning(f"[CHECK] GET status: {get_resp.status}")
            except Exception as e:
                logger.exception(f"[CHECK FINAL GET FAILED] {e}")

        if not image_ready:
            await context.bot.send_message(chat_id, lang["image_delayed"])
            await _refund_if_needed()
            await notify_admin_on_error(context, user, prompt, headers, Exception("Image delay timeout"), count)
            return

        # --- Caption tayyorlash ---
        escaped_prompt = escape_md(prompt)
        model_title = "Default Mode"
        if lora_id:
            m = next((m for m in DIGEN_MODELS if m["id"] == lora_id), None)
            if m:
                model_title = m["title"]

        stats = (
            f"{lang['image_ready_header']}\n"
            f"{lang['image_prompt_label']} {escaped_prompt}\n"
            f"{lang['image_model_label']} {model_title}\n"
            f"{lang['image_count_label']} {count}\n"
            f"{lang['image_time_label']} {tashkent_time().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # --- Media tayyorlash ---
        media = []
        for i, url in enumerate(urls):
            try:
                # 🔹 `url`ni tozalab foydalanamiz
                clean_url = url.strip()
                caption = stats if i == 0 else ""
                media.append(InputMediaPhoto(media=clean_url, caption=caption))
            except Exception as e:
                logger.error(f"[MEDIA BUILD ERROR] index={i}, url={url}: {e}")
                await context.bot.send_message(chat_id, lang["error"])
                await _refund_if_needed()
                return

        # --- Media group yuborishda timeoutni oshirish (va retry) ---
        success = False
        for attempt in range(3):
            try:
                await context.bot.send_media_group(
                    chat_id=chat_id,
                    media=media,
                    write_timeout=250,  # Telegram API uchun yetarli
                    read_timeout=250,
                    connect_timeout=250
                )
                success = True
                break
            except (telegram.error.TimedOut, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                logger.warning(f"[SEND MEDIA TIMEOUT] {attempt+1}/3: {e}")
                if attempt < 2:
                    await asyncio.sleep(3)
                else:
                    raise
            except telegram.error.BadRequest as e:
                if "MEDIA_CAPTION_TOO_LONG" in str(e):
                    # captionni qisqartiramiz
                    stats = f"✅ {count} ta rasm"
                    media = [InputMediaPhoto(media=url.strip(), caption=(stats if i == 0 else "")) for i, url in enumerate(urls)]
                    continue  # qayta urinish
                else:
                    raise

        if not success:
            raise telegram.error.TimedOut("All retries failed")

        # --- Loglash va admin xabari ---
        await log_generation(context.application.bot_data["db_pool"], user, prompt, final_prompt, image_id, count)
        if ADMIN_ID and urls:
            await notify_admin_generation(context, user, prompt, urls, count, image_id)

    except Exception as e:
        await _refund_if_needed()
        logger.exception(f"[BACKGROUND GENERATE ERROR] {e}")
        try:
            await context.bot.send_message(chat_id, lang["error"])
        except:
            pass
        try:
            await notify_admin_on_error(context, user, prompt, headers, e, count)
        except Exception as ne:
            logger.exception(f"[ADMIN NOTIFY FAILED] {ne}")

# ---------------- Buy extra images (Stars) ----------------
async def buy_pack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    try:
        credits = int(q.data.split("_")[2])
    except Exception:
        credits = EXTRA_PACK_SIZE

    # Narx: 1 rasm = 1 Star (default: 50 rasm = 50 Stars)
    stars = int((credits / max(EXTRA_PACK_SIZE, 1)) * EXTRA_PACK_PRICE_STARS)

    payload = f"quota_{q.from_user.id}_{credits}_{int(time.time())}"
    prices = [LabeledPrice(f"+{credits} images", stars)]

    await context.bot.send_invoice(
        chat_id=q.message.chat_id,
        title="🎨 Image Pack",
        description=f"+{credits} ta qo'shimcha rasm limiti",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        is_flexible=False
    )

# ---------------- Donate (Stars) flow ----------------
# Yangilangan: context.user_data["current_operation"] o'rnatiladi
async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Yangi: donate jarayonini belgilash
    context.user_data["current_operation"] = "donate"

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

    lang = get_lang(lang_code)

    if update.callback_query:
        await update.callback_query.message.reply_text(lang["donate_prompt"])
    else:
        await update.message.reply_text(lang["donate_prompt"])
    return DONATE_WAITING_AMOUNT

# Yangilangan: context.user_data["current_operation"] tekshiriladi
async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Yangi: faqat donate jarayonida bo'lsa ishlashi
    if context.user_data.get("current_operation") != "donate":
        # Agar foydalanuvchi donate jarayonida bo'lmasa, bu handler ishlamasin
        # Boshqa handlerlar bu xabarni qo'lga kiritadi
        return ConversationHandler.END # Yoki hech nishga qaytmasa ham bo'ladi

    # Yangi: donate jarayoni tugadi, belgini o'chiramiz
    context.user_data.pop("current_operation", None)

    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", update.effective_user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text(lang["donate_invalid"])
        return DONATE_WAITING_AMOUNT
        # Yangi: donate jarayoni davom etayotgani uchun, DONATE_WAITING_AMOUNT qaytaramiz
        # Agar ConversationHandler ishlamayotgan bo'lsa, bu hech narsa o'zgartirmaydi
        return DONATE_WAITING_AMOUNT 

    # ... (qolgan kodlar - invoice yuborish) ...
    payload = f"donate_{update.effective_user.id}_{int(time.time())}"
    prices = [LabeledPrice(f"{amount} Stars", amount)]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=lang["donate_title"],
        description=lang["donate_description"],
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    # Oxirida ConversationHandler tugashi kerak
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount
    user = update.effective_user

    # ✅ TO'G'RI: telegram_payment_charge_id
    charge_id = payment.telegram_payment_charge_id

    pool = context.application.bot_data["db_pool"]

    # til
    lang_code = DEFAULT_LANGUAGE
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    payload = payment.invoice_payload or ""

    # Har qanday Stars to'lovi DB ga yozib boriladi
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload, charge_id) VALUES($1,$2,$3,$4,$5)",
            user.id, user.username if user.username else None, amount_stars, payload, charge_id
        )

    # Quota pack to'lovi bo'lsa — kredit qo'shamiz
    if payload.startswith("quota_"):
        try:
            # quota_{user_id}_{credits}_{ts}
            parts = payload.split("_")
            credits = int(parts[2])
        except Exception:
            credits = EXTRA_PACK_SIZE

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET extra_credits = COALESCE(extra_credits, 0) + $1 WHERE id = $2",
                credits, user.id
            )

        await update.message.reply_text(
            lang.get("quota_pack_thanks", "✅ To'lov qabul qilindi! +{credits} ta qo'shimcha rasm limiti qo'shildi.").format(credits=credits)
        )

        # Agar foydalanuvchi limitdan o'tib pending generatsiya qilgan bo'lsa — avtomatik boshlaymiz
        pending = context.user_data.get("pending_generation")
        if pending and isinstance(pending, dict):
            try:
                ok, info = await reserve_quota_or_explain(pool, user.id, int(pending.get("count", 1)))
                if ok:
                    await context.bot.send_message(user.id, lang.get("generating_content", "✨ Generating..."))
                    asyncio.create_task(
                        _background_generate(
                            context=context,
                            user=user,
                            prompt=pending.get("prompt", ""),
                            translated=pending.get("translated", pending.get("prompt", "")),
                            count=int(pending.get("count", 1)),
                            chat_id=user.id,
                            lang=lang,
                            paid_credits_used=int(info.get("need_paid", 0) or 0)
                        )
                    )
                    context.user_data.pop("pending_generation", None)
            except Exception as e:
                logger.exception(f"[PENDING GENERATION AFTER PAYMENT ERROR] {e}")
        return

    # Aks holda — donate deb qabul qilamiz
    await update.message.reply_text(
        lang["donate_thanks"].format(name=user.first_name, stars=amount_stars)
    )

# ---------------- Refund handler (faqat admin uchun) ----------------

async def cmd_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Error.")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("UsageId: /refund <user_id> <telegram_payment_charge_id>")
        return
    try:
        target_user_id = int(context.args[0])
        telegram_payment_charge_id = context.args[1].strip()
    except (ValueError, IndexError):
        await update.message.reply_text("UsageId: /refund <user_id> <telegram_payment_charge_id>")
        return

    # DB dan stars miqdorini olish (ixtiyoriy, faqat log uchun)
    stars = 0
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT stars FROM donations WHERE charge_id = $1 AND user_id = $2",
            telegram_payment_charge_id, target_user_id
        )
        if row:
            stars = row["stars"]
        else:
            # Agar topilmasa ham, refund qilishga ruxsat beramiz (masalan, eski to'lov bo'lsa)
            logger.info(f"[REFUND] To'lov DB da topilmadi, lekin refund urinishi davom ettirilmoqda: {telegram_payment_charge_id}")

    try:
        await context.bot.refund_star_payment(
            user_id=target_user_id,
            telegram_payment_charge_id=telegram_payment_charge_id
        )
        # Muvaffaqiyatli bo'lsa, DB ga refund qilinganligini belgilaymiz
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE donations SET refunded_at = NOW() WHERE charge_id = $1 AND user_id = $2",
                telegram_payment_charge_id, target_user_id
            )
        await update.message.reply_text(
            f"✅ {stars} Stars muvaffaqiyatli qaytarildi foydalanuvchi {target_user_id} ga."
        )
    except Exception as e:
        logger.exception(f"[REFUND ERROR] {e}")
        await update.message.reply_text(f"❌ Xatolik: {str(e)}")
# ---------------- Error handler ----------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ An error occurred. Please contact the admin or try again.")
    except Exception:
        pass

#--------------------------------------------------

# ---------------- Public Statistika (Hamma uchun) ----------------
async def cmd_public_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_mode=False):
    # Foydalanuvchini to'g'ri aniqlash
    if update.callback_query:
        user = update.callback_query.from_user
    else:
        user = update.effective_user

    # Tilni olish
    lang_code = DEFAULT_LANGUAGE
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user.id)
        if row:
            lang_code = row["language_code"]
    lang = get_lang(lang_code)

    pool = context.application.bot_data["db_pool"]
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        new_users_30d = await conn.fetchval("SELECT COUNT(*) FROM users WHERE first_seen >= $1", thirty_days_ago)
        total_images = await conn.fetchval("SELECT COALESCE(SUM(image_count), 0) FROM generations")
        today_images = await conn.fetchval("SELECT COALESCE(SUM(image_count), 0) FROM generations WHERE created_at >= $1", today_start)
        user_images = await conn.fetchval("SELECT COALESCE(SUM(image_count), 0) FROM generations WHERE user_id = $1", user.id)

    fake_ping = random.randint(30, 80)

    # ✅ Bu qatorlar async with dan TASHQARIDA bo'lishi kerak
    stats_text = (
        f"{lang['stats_title']}\n"
        f"{lang['stats_ping']}: `{fake_ping}ms`\n"
        f"{lang['stats_total_images']}: `{total_images}`\n"
        f"{lang['stats_today']}: `{today_images}`\n"
        f"{lang['stats_users']}: `{total_users}`\n"
        f"{lang['stats_new_30d']}: `{new_users_30d}`\n"
        f"{lang['stats_your_images']}: `{user_images}`"
    )

    kb = [
        [InlineKeyboardButton(lang["stats_refresh_button"], callback_data="stats_refresh")],
        [InlineKeyboardButton(lang["back_to_main_button"], callback_data="back_to_main")]
    ]

    if edit_mode and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=stats_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception:
            pass
    else:
        await update.message.reply_text(
            stats_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
#-------------------------------------------------------------------------------
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list_0")],
        [InlineKeyboardButton("🚫 Ban / 🔓 Unban", callback_data="admin_ban_unban_menu")],
        [InlineKeyboardButton("📣 Broadcast", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")],
        [InlineKeyboardButton("💎 Refund", callback_data="admin_refund_menu")],
        [InlineKeyboardButton("📤 DB Eksport", callback_data="admin_export_db")],
        [InlineKeyboardButton("⬅️ Asosiy", callback_data="back_to_main")]
    ]
    await q.edit_message_text("🔐 **Admin Panel**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
#------------------------------------------------------------------------------------------
async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    pool = context.application.bot_data["db_pool"]
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        new_24h = await conn.fetchval("SELECT COUNT(*) FROM users WHERE first_seen >= $1", now - timedelta(hours=24))
        total_gens = await conn.fetchval("SELECT COALESCE(SUM(image_count), 0) FROM generations")
        today_gens = await conn.fetchval("SELECT COALESCE(SUM(image_count), 0) FROM generations WHERE created_at >= $1", today_start)
        stars_earned = await conn.fetchval("SELECT COALESCE(SUM(stars), 0) FROM donations WHERE refunded_at IS NULL")
        errors_48h = await conn.fetchval(
            "SELECT COUNT(*) FROM donations d JOIN generations g ON d.user_id = g.user_id "
            "WHERE d.refunded_at IS NOT NULL AND d.created_at >= $1",
            now - timedelta(hours=48)
        )
        active_7d = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM generations WHERE created_at >= $1", week_ago)

    text = (
        "📊 *Admin Statistika*\n\n"
        f"👥 *Jami foydalanuvchilar:* {total_users}\n"
        f"🆕 *24h yangi:* +{new_24h}\n"
        f"📆 *Bugun generatsiya:* {today_gens}\n"
        f"🖼 *Jami rasmlar:* {total_gens}\n"
        f"💬 *7 kunlik faol:* {active_7d}\n"
        f"💎 *Stars daromad:* {stars_earned} XTR\n"
        f"📉 *48h refund:* {errors_48h}"
    )
    kb = [
        [InlineKeyboardButton("🔄 Yangilash", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list_0")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")]
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

#------------------------------------------------------------------------------------------
async def admin_users_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    page = int(q.data.split("_")[-1])
    offset = page * 5
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT id, username, language_code, image_model_id,
                   (SELECT COUNT(*) FROM generations WHERE user_id = u.id) AS gen_count,
                   last_seen
            FROM users u
            ORDER BY last_seen DESC
            LIMIT 5 OFFSET $1
        """, offset)
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
    pages = (total + 4) // 5  # 5 ta/ sahifa

    lines = ["👥 *Foydalanuvchilar roʻyxati:*"]
    for u in users:
        uname = f"@{u['username']}" if u["username"] else "—"
        lang = u["language_code"] or "uz"
        flag = LANGUAGES.get(lang, {}).get("flag", "🌐")
        model_title = "Default"
        for m in DIGEN_MODELS:
            if m["id"] == u["image_model_id"]:
                model_title = m["title"][:15]
                break
        last_seen = (utc_now() - u["last_seen"]).total_seconds() / 3600 if u["last_seen"] else 999
        last_str = f"{int(last_seen)}h" if last_seen < 48 else f"{int(last_seen/24)}d"
        lines.append(
            f"\n▫️ `{u['id']}` {flag} {uname}\n"
            f"   📸 {u['gen_count']} | 🎨 {model_title} | 🕒 {last_str}"
        )
    text = "\n".join(lines) if lines else "❌ Hech kim yo‘q."

    kb = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"admin_users_list_{page-1}"))
    if (page + 1) * 5 < total:
        row.append(InlineKeyboardButton("➡️", callback_data=f"admin_users_list_{page+1}"))
    if row:
        kb.append(row)
    
    kb.append([
        InlineKeyboardButton("🔍 Qidiruv (ID/username)", callback_data="admin_user_search_prompt")
    ])
    kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")])

    await q.edit_message_text(text[:4096], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

#---------------------------------------------------------------------------------------
async def admin_user_search_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🔍 ID yoki @username yuboring:")
    context.user_data["admin_search_mode"] = True
#------------------------------------------------------------------------------------------
async def admin_channels_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    # Hozircha statik kanal ko'rsatiladi
    channels_list = "\n".join([f"• {ch['username']}" for ch in MANDATORY_CHANNELS]) if MANDATORY_CHANNELS else "❌ Hech narsa yo'q"
    text = f"🔗 **Majburiy obuna kanallari:**\n\n{channels_list}\n\nℹ️ Kanallarni o'zgartirish uchun `.env` faylini tahrirlang."
    await q.message.reply_text(text, parse_mode="Markdown")
#------------------------------------------------------------------------------------------------
async def admin_ban_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split("_")[2])
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = TRUE WHERE id = $1", user_id)
    await q.answer(f"Foydalanuvchi {user_id} ban qilindi ✅", show_alert=True)
    await admin_show_user_card(context, user_id, q=q)

async def admin_unban_inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split("_")[2])
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = FALSE WHERE id = $1", user_id)
    await q.answer(f"Foydalanuvchi {user_id} bandan chiqarildi ✅", show_alert=True)
    await admin_show_user_card(context, user_id, q=q)

#-----------------------------------------------------------------------------------
async def admin_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("🔑 Digen Tokenlar", callback_data="admin_manage_tokens")],
        [InlineKeyboardButton("🌐 Til sozlamalari", callback_data="admin_lang_editor")],
        [InlineKeyboardButton("📥 DB yuklab olish", callback_data="admin_export_db")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")]
    ]
    await q.edit_message_text("⚙️ *Sozlamalar*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
#-------------------------------------------------------------------------------------
BROADCAST_STATE = 101

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("📣 Broadcast xabarini yuboring (matn, rasm, video, fayl...):")
    return BROADCAST_STATE

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # Barcha foydalanuvchilarni olish
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT id FROM users")
    
    sent = 0
    for row in users:
        try:
            if update.message.text:
                await context.bot.send_message(chat_id=row["id"], text=update.message.text)
            elif update.message.photo:
                await context.bot.send_photo(chat_id=row["id"], photo=update.message.photo[-1].file_id, caption=update.message.caption)
            elif update.message.video:
                await context.bot.send_video(chat_id=row["id"], video=update.message.video.file_id, caption=update.message.caption)
            elif update.message.document:
                await context.bot.send_document(chat_id=row["id"], document=update.message.document.file_id, caption=update.message.caption)
            else:
                await context.bot.copy_message(chat_id=row["id"], from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
            sent += 1
        except Exception as e:
            logger.warning(f"[BROADCAST] {row['id']} ga yuborishda xatolik: {e}")
    
    await update.message.reply_text(f"✅ {sent} ta foydalanuvchiga xabar yuborildi.")
    return ConversationHandler.END

#-----------------------------------------------------------------------------------
async def admin_unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🔓 Bandan chiqarish uchun foydalanuvchi ID sini yuboring:")
    return UNBAN_STATE

async def admin_unban_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        user_id = int(update.message.text.strip())
        pool = context.application.bot_data["db_pool"]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
            if not row:
                await update.message.reply_text(f"❌ Foydalanuvchi `{user_id}` topilmadi.", parse_mode="Markdown")
                return
            await conn.execute("UPDATE users SET is_banned = FALSE WHERE id = $1", user_id)
        await update.message.reply_text(f"✅ Foydalanuvchi `{user_id}` muvaffaqiyatli **bandan chiqarildi**.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID. Faqat raqam yuboring.")
    return ConversationHandler.END

# ---------------- Admin: Ban / Unban menu + Qo'shimcha funksiyalar ----------------

ADMIN_SENDMSG_STATE = 120

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin komandasi (faqat admin)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Sizga ruxsat yo'q.")
        return
    kb = [
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list_0")],
        [InlineKeyboardButton("🚫 Ban / 🔓 Unban", callback_data="admin_ban_unban_menu")],
        [InlineKeyboardButton("📣 Broadcast", callback_data="admin_broadcast_menu")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")],
        [InlineKeyboardButton("💎 Refund", callback_data="admin_refund_menu")],
        [InlineKeyboardButton("📤 DB Eksport", callback_data="admin_export_db")],
    ]
    await update.message.reply_text("🔐 **Admin Panel**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def admin_ban_unban_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("🚫 Ban (ID orqali)", callback_data="admin_ban_start")],
        [InlineKeyboardButton("🔓 Unban (ID orqali)", callback_data="admin_unban_start")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")]
    ]
    await q.edit_message_text("🚫 / 🔓 *Ban & Unban*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def admin_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🚫 Ban qilish uchun foydalanuvchi ID sini yuboring:")
    return BAN_STATE

async def admin_ban_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        user_id = int(update.message.text.strip())
        pool = context.application.bot_data["db_pool"]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
            if not row:
                await update.message.reply_text(f"❌ Foydalanuvchi `{user_id}` topilmadi.", parse_mode="Markdown")
                return ConversationHandler.END
            await conn.execute("UPDATE users SET is_banned = TRUE WHERE id = $1", user_id)
        await update.message.reply_text(f"✅ Foydalanuvchi `{user_id}` **ban qilindi**.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID. Faqat raqam yuboring.")
    return ConversationHandler.END

async def admin_show_user_card(context: ContextTypes.DEFAULT_TYPE, user_id: int, *, q=None, message=None):
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        u = await conn.fetchrow(
            "SELECT id, username, language_code, is_banned, image_model_id, extra_credits, last_seen, first_seen "
            "FROM users WHERE id=$1",
            user_id
        )
        if not u:
            if q:
                await q.answer("User topilmadi", show_alert=True)
            if message:
                await message.reply_text("❌ Foydalanuvchi topilmadi.")
            return

        total_images = int(await conn.fetchval(
            "SELECT COALESCE(SUM(image_count),0) FROM generations WHERE user_id=$1", user_id
        ) or 0)
        today_images = int(await conn.fetchval(
            "SELECT COALESCE(SUM(image_count),0) FROM generations WHERE user_id=$1 AND created_at >= $2",
            user_id, tashkent_day_start_utc()
        ) or 0)

    lang = get_lang(u["language_code"] or DEFAULT_LANGUAGE)

    model_title = "Default"
    for m in DIGEN_MODELS:
        if m["id"] == (u["image_model_id"] or ""):
            model_title = m["title"]
            break

    uname = f"@{u['username']}" if u["username"] else "—"
    text = (
        f"👤 *User Card*\n\n"
        f"🆔 *ID:* `{u['id']}`\n"
        f"👤 *Username:* {uname}\n"
        f"🌐 *Til:* {lang['flag']} {lang['name']}\n"
        f"🎨 *Model:* {model_title}\n"
        f"🖼 *Bugun:* `{today_images}` / `{DAILY_FREE_IMAGES}`\n"
        f"🖼 *Jami:* `{total_images}`\n"
        f"💳 *Extra kredit:* `{int(u['extra_credits'] or 0)}`\n"
        f"⛔ *Ban:* {'✅ Ha' if u['is_banned'] else '❌ Yo‘q'}"
    )

    kb = [
        [
            InlineKeyboardButton("🚫 Ban", callback_data=f"admin_ban_{u['id']}"),
            InlineKeyboardButton("🔓 Unban", callback_data=f"admin_unban_{u['id']}")
        ],
        [InlineKeyboardButton("📨 Xabar yuborish", callback_data=f"admin_sendmsg_{u['id']}")],
        [InlineKeyboardButton("📈 Statistika", callback_data=f"admin_user_stats_{u['id']}")],
        [InlineKeyboardButton("⬅️ Roʻyxatga qaytish", callback_data="admin_users_list_0")]
    ]

    if q:
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    elif message:
        await message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def admin_user_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split("_")[-1])

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        total_images = int(await conn.fetchval(
            "SELECT COALESCE(SUM(image_count),0) FROM generations WHERE user_id=$1", user_id
        ) or 0)
        last10 = await conn.fetch(
            "SELECT prompt, image_count, created_at FROM generations WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10",
            user_id
        )

    lines = [f"📈 *User stats* — `{user_id}`", f"🖼 *Jami rasmlar:* `{total_images}`", ""]
    for r in last10:
        p = (r["prompt"] or "")[:35].replace("\n", " ")
        lines.append(f"• `{r['image_count']}` — {escape_md(p)}")
    text = "\n".join(lines)[:4096]

    kb = [
        [InlineKeyboardButton("⬅️ User Card", callback_data=f"admin_usercard_{user_id}")],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_panel")]
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def admin_usercard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split("_")[-1])
    await admin_show_user_card(context, user_id, q=q)

async def admin_sendmsg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    user_id = int(q.data.split("_")[-1])
    context.user_data["admin_sendmsg_target"] = user_id
    await q.message.reply_text(f"📨 `{user_id}` ga yuboriladigan xabarni yozing:", parse_mode="Markdown")
    return ADMIN_SENDMSG_STATE

async def admin_sendmsg_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    user_id = context.user_data.get("admin_sendmsg_target")
    context.user_data.pop("admin_sendmsg_target", None)
    if not user_id:
        await update.message.reply_text("❌ Target topilmadi.")
        return ConversationHandler.END
    try:
        await context.bot.copy_message(chat_id=user_id, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
        await update.message.reply_text("✅ Yuborildi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")
    return ConversationHandler.END

async def admin_refund_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, user_id, stars, charge_id, created_at FROM donations "
            "WHERE refunded_at IS NULL AND charge_id IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 10"
        )
    if not rows:
        kb = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")]]
        await q.edit_message_text("💎 Refund uchun to'lovlar topilmadi.", reply_markup=InlineKeyboardMarkup(kb))
        return

    lines = ["💎 *Refund menu* (oxirgi 10 ta):", ""]
    kb = []
    for r in rows:
        lines.append(f"• `#{r['id']}` user `{r['user_id']}` — `{r['stars']}` ⭐")
        kb.append([InlineKeyboardButton(f"Refund #{r['id']} — {r['stars']}⭐", callback_data=f"admin_refund_{r['id']}")])
    kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_panel")])

    await q.edit_message_text("\n".join(lines)[:4096], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def admin_refund_do_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    donation_id = int(q.data.split("_")[-1])

    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT user_id, charge_id, stars FROM donations WHERE id=$1", donation_id)

    if not r or not r["charge_id"]:
        await q.answer("❌ Topilmadi yoki charge_id yo'q", show_alert=True)
        return

    try:
        await context.bot.refund_star_payment(
            user_id=int(r["user_id"]),
            telegram_payment_charge_id=str(r["charge_id"])
        )
        async with pool.acquire() as conn:
            await conn.execute("UPDATE donations SET refunded_at = NOW() WHERE id = $1", donation_id)
        await q.answer("✅ Refund bajarildi", show_alert=True)
    except Exception as e:
        await q.answer(f"❌ Refund xatosi: {e}", show_alert=True)

    await admin_refund_menu_handler(update, context)

async def admin_export_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    pool = context.application.bot_data["db_pool"]

    import csv, tempfile, zipfile
    from pathlib import Path

    tmpdir = Path(tempfile.mkdtemp(prefix="bot_export_"))
    files = []

    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT * FROM users ORDER BY last_seen DESC")
        gens = await conn.fetch("SELECT * FROM generations ORDER BY created_at DESC LIMIT 20000")
        dons = await conn.fetch("SELECT * FROM donations ORDER BY created_at DESC LIMIT 20000")
        sess = await conn.fetch("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 20000")

    def dump_csv(rows, filename):
        if not rows:
            return
        p = tmpdir / filename
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(rows[0].keys())
            for r in rows:
                w.writerow([r.get(k) for k in rows[0].keys()])
        files.append(p)

    dump_csv(users, "users.csv")
    dump_csv(gens, "generations.csv")
    dump_csv(dons, "donations.csv")
    dump_csv(sess, "sessions.csv")

    zpath = tmpdir / "export.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, arcname=p.name)

    await q.message.reply_document(document=zpath.open("rb"), filename="export.zip", caption="📤 DB export (CSV)")


async def admin_manage_tokens_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    total = len(DIGEN_KEYS) if isinstance(DIGEN_KEYS, list) else 0
    await q.edit_message_text(
        f"🔑 *Digen tokenlar*\n\nJami tokenlar: `{total}`\n\nTokenlarni o'zgartirish uchun serverdagi `.env` (DIGEN_KEYS) ni yangilang.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_settings")]])
    )

async def admin_lang_editor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    q = update.callback_query
    await q.answer()
    base = LANGUAGES.get(DEFAULT_LANGUAGE, {})
    report = []
    for code, d in LANGUAGES.items():
        missing = [k for k in base.keys() if k not in d]
        if missing:
            report.append((code, len(missing)))
    report.sort(key=lambda x: x[1], reverse=True)
    lines = ["🌐 *Til audit* (missing keys):", ""]
    for code, n in report[:15]:
        lines.append(f"• `{code}` — `{n}`")
    if not report:
        lines.append("✅ Hammasi joyida (default kalitlar mavjud).")
    await q.edit_message_text(
        "\n".join(lines)[:4096],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_settings")]])
    )


#-------------------------------------------------------------------------
async def show_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_public_stats(update, context, edit_mode=True)
#-------------------------------------------------------
# ---------------- Startup ----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=4)
    app.bot_data["db_pool"] = pool
    await init_db(pool)
    logger.info("✅ DB initialized and pool created.")

# ---------------- MAIN ----------------
def build_app():
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    all_lang_pattern = r"lang_(uz|ru|en|id|lt|esmx|eses|it|zhcn|bn|hi|ptbr|ar|uk|vi)"
    
    # --- Handlers ---
    app.add_handler(CallbackQueryHandler(admin_stats_handler, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_panel_handler, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_users_list_handler, pattern=r"^admin_users_list_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_user_search_prompt_handler, pattern="^admin_user_search_prompt$"))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(admin_ban_unban_menu_handler, pattern="^admin_ban_unban_menu$"))
    app.add_handler(CallbackQueryHandler(admin_settings_handler, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(admin_manage_tokens_handler, pattern="^admin_manage_tokens$"))
    app.add_handler(CallbackQueryHandler(admin_lang_editor_handler, pattern="^admin_lang_editor$"))
    app.add_handler(CallbackQueryHandler(admin_export_db_handler, pattern="^admin_export_db$"))
    app.add_handler(CallbackQueryHandler(admin_refund_menu_handler, pattern="^admin_refund_menu$"))
    app.add_handler(CallbackQueryHandler(admin_refund_do_handler, pattern=r"^admin_refund_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_user_stats_handler, pattern=r"^admin_user_stats_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_usercard_handler, pattern=r"^admin_usercard_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_ban_inline_handler, pattern=r"^admin_ban_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_unban_inline_handler, pattern=r"^admin_unban_\d+$"))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & filters.User(ADMIN_ID),
        admin_user_search_handler
    ))
    app.add_handler(CommandHandler("stats", cmd_public_stats))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^back_to_settings$"))
    app.add_handler(CallbackQueryHandler(start_handler, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(fake_lab_new_handler, pattern="^fake_lab_new$"))
    app.add_handler(CallbackQueryHandler(fake_lab_refresh_handler, pattern="^fake_lab_refresh$"))
    app.add_handler(CallbackQueryHandler(show_stats_handler, pattern="^show_stats$"))
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("language", cmd_language))
    app.add_handler(CallbackQueryHandler(cmd_language, pattern="^change_language$"))
    app.add_handler(CallbackQueryHandler(language_select_handler, pattern=all_lang_pattern))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^open_settings$"))
    app.add_handler(CallbackQueryHandler(select_image_model, pattern="^select_image_model$"))
    app.add_handler(CallbackQueryHandler(confirm_model_selection, pattern=r"^confirm_model_.*$"))
    app.add_handler(CallbackQueryHandler(set_image_model, pattern=r"^set_model_.*$"))
    app.add_handler(CallbackQueryHandler(random_anime_handler, pattern="^random_anime$"))
    app.add_handler(CallbackQueryHandler(random_anime_refresh_handler, pattern="^random_anime_refresh$"))

    # Donate
    donate_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(donate_start, pattern="^donate_custom$")],
        states={DONATE_WAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, donate_amount)]},
        fallbacks=[],
        per_message=False
    )
    app.add_handler(donate_conv)

    # Admin Ban/Unban (ID) conversation
    ban_unban_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_ban_start, pattern="^admin_ban_start$"),
            CallbackQueryHandler(admin_unban_start, pattern="^admin_unban_start$"),
        ],
        states={
            BAN_STATE: [MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & filters.User(ADMIN_ID) & ~filters.COMMAND, admin_ban_confirm)],
            UNBAN_STATE: [MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & filters.User(ADMIN_ID) & ~filters.COMMAND, admin_unban_confirm)],
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(ban_unban_conv)

    # Admin send message to user conversation
    sendmsg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_sendmsg_start, pattern=r"^admin_sendmsg_\d+$")],
        states={
            ADMIN_SENDMSG_STATE: [MessageHandler(filters.ALL & filters.ChatType.PRIVATE & filters.User(ADMIN_ID) & ~filters.COMMAND, admin_sendmsg_send)]
        },
        fallbacks=[],
        per_message=False
    )
    app.add_handler(sendmsg_conv)

    # Admin panel

    # Broadcast
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern=r"^(admin_broadcast|admin_broadcast_menu)$")],
        states={BROADCAST_STATE: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_broadcast_send)]},
        fallbacks=[]
    )
    app.add_handler(broadcast_conv)

    # Kanallar
    app.add_handler(CallbackQueryHandler(admin_channels_handler, pattern="^admin_channels$"))

    # Qolgan handlerlar
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="^start_gen$"))
    app.add_handler(CallbackQueryHandler(start_ai_flow_handler, pattern="^start_ai_flow$"))
    app.add_handler(CallbackQueryHandler(check_sub_button_handler, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(generate_cb, pattern=r"^count_\d+$"))
    app.add_handler(CallbackQueryHandler(buy_pack_handler, pattern=r"^buy_pack_\d+$"))
    app.add_handler(CallbackQueryHandler(gen_image_from_prompt_handler, pattern="^gen_image_from_prompt$"))
    app.add_handler(CallbackQueryHandler(ai_chat_from_prompt_handler, pattern="^ai_chat_from_prompt$"))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("refund", cmd_refund))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text_handler))
    app.add_error_handler(on_error)

    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
