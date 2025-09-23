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
        "select_lang": "🌐 Iltimos, tilni tanlang:",
        "ai_response_header": "💬 AI javob:",
        "image_ready_header": "🎨 Rasm tayyor!",
        "image_prompt_label": "📝 Prompt:",
        "image_count_label": "🔢 Soni:",
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
        "prompt_text": "✍️ Sekarang kirim teks untuk membuat gambar.",
        "ai_prompt_text": "✍️ Tulis pertanyaan Anda untuk memulai percakapan.",
        "select_count": "🔢 Berapa banyak gambar yang akan dibuat?",
        "generating": "🔄 Membuat gambar ({count})... ⏳",
        "success": "✅ Gambar siap! 📸",
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
        "ai_button": "💬 Kalbėtis su AI",
        "donate_button": "💖 Paaukoti",
        "lang_button": "🌐 Pakeisti kalbą",
        "prompt_text": "✍️ Dabar išsiųskite tekstą, kad sugeneruotumėte paveikslėlį.",
        "ai_prompt_text": "✍️ Parašykite savo klausimą, kad pradėtumėte pokalbį.",
        "select_count": "🔢 Kiek paveikslėlių generuoti?",
        "generating": "🔄 Generuojamas paveikslėlis ({count})... ⏳",
        "success": "✅ Paveikslėlis paruoštas! 📸",
        "error": "⚠️ Įvyko klaida. Bandykite dar kartą.",
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
    "es_MX": {
        "flag": "🇲🇽",
        "name": "Español (México)",
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
    "es_ES": {
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
        "prompt_text": "✍️ Ora invia il testo per generare un'immagine.",
        "ai_prompt_text": "✍️ Scrivi la tua domanda per iniziare una conversazione.",
        "select_count": "🔢 Quante immagini generare?",
        "generating": "🔄 Generazione immagine ({count})... ⏳",
        "success": "✅ Immagine pronta! 📸",
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
    },
    # --- Xitoycha (Soddalashtirilgan) (🇨🇳) ---
    "zh_CN": {
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
    "pt_BR": {
        "flag": "🇧🇷",
        "name": "Português (Brasil)",
        "welcome": "👋 Olá!\n\nEu crio imagens para você usando IA.",
        "gen_button": "🎨 Gerar Imagem",
        "ai_button": "💬 Conversar com IA",
        "donate_button": "💖 Doar",
        "lang_button": "🌐 Mudar Idioma",
        "prompt_text": "✍️ Agora envie o texto para gerar uma imagem.",
        "ai_prompt_text": "✍️ Escreva sua pergunta para iniciar uma conversa.",
        "select_count": "🔢 Quantas imagens gerar?",
        "generating": "🔄 Gerando imagem ({count})... ⏳",
        "success": "✅ Imagem pronta! 📸",
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
        "prompt_text": "✍️ Тепер надішліть текст для створення зображення.",
        "ai_prompt_text": "✍️ Напишіть своє запитання, щоб розпочати розмову.",
        "select_count": "🔢 Скільки зображень створити?",
        "generating": "🔄 Створюю зображення ({count})... ⏳",
        "success": "✅ Зображення готове! 📸",
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
        "prompt_text": "✍️ Bây giờ hãy gửi văn bản để tạo hình ảnh.",
        "ai_prompt_text": "✍️ Viết câu hỏi của bạn để bắt đầu cuộc trò chuyện.",
        "select_count": "🔢 Tạo bao nhiêu hình ảnh?",
        "generating": "🔄 Đang tạo hình ảnh ({count})... ⏳",
        "success": "✅ Hình ảnh đã sẵn sàng! 📸",
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
# Endi barcha rasmlarni yuboradi
# Endi barcha rasmlarni yuboradi va tarjima qiladi
async def notify_admin_generation(context: ContextTypes.DEFAULT_TYPE, user, prompt, image_urls, count, image_id):
    """
    Foydalanuvchi rasm generatsiya qilganda, barcha rasmlarni admin foydalanuvchisiga yuboradi.
    """
    if not ADMIN_ID:
        return # Agar ADMIN_ID o'rnatilmagan bo'lsa, hech narsa yuborilmaydi

    try:
        # Foydalanuvchi tilini olish
        lang_code = DEFAULT_LANGUAGE
        async with context.application.bot_data["db_pool"].acquire() as conn:
            row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", ADMIN_ID)
            if row:
                lang_code = row["language_code"]
        lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

        tashkent_dt = tashkent_time()
        # Admin xabari uchun matn (statistika)
        # Admin xabari uchun matn (statistika) - Tarjima qilingan matnlardan foydalanilmoqda
        caption_text = (
            f"🎨 *Yangi generatsiya!*\n\n"
            f"👤 *Foydalanuvchi:* @{user.username if user.username else 'N/A'} (ID: {user.id})\n"
            f"📝 *Prompt:* {escape_md(prompt)}\n"
            f"🔢 *Soni:* {count}\n"
            f"🆔 *Image ID:* `{image_id}`\n" # Image ID ni ham qo'shamiz
            f"⏰ *Vaqt \\(UTC\\+5\\):* {tashkent_dt.strftime('%Y-%m-%d %H:%M:%S')}" # Markdown belgilari escape qilindi
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
    # Tugmalarni 2 ustunda, oxirgi tugma alohida qatorga joylashtiramiz
    kb = [
        [
            InlineKeyboardButton(f"{LANGUAGES['uz']['flag']} {LANGUAGES['uz']['name']}", callback_data="lang_uz"),
            InlineKeyboardButton(f"{LANGUAGES['ru']['flag']} {LANGUAGES['ru']['name']}", callback_data="lang_ru")
        ],
        [
            InlineKeyboardButton(f"{LANGUAGES['en']['flag']} {LANGUAGES['en']['name']}", callback_data="lang_en"),
            InlineKeyboardButton(f"{LANGUAGES['id']['flag']} {LANGUAGES['id']['name']}", callback_data="lang_id")
        ],
        [
            InlineKeyboardButton(f"{LANGUAGES['lt']['flag']} {LANGUAGES['lt']['name']}", callback_data="lang_lt"),
            InlineKeyboardButton(f"{LANGUAGES['es_MX']['flag']} {LANGUAGES['es_MX']['name']}", callback_data="lang_es_MX")
        ],
        [
            InlineKeyboardButton(f"{LANGUAGES['es_ES']['flag']} {LANGUAGES['es_ES']['name']}", callback_data="lang_es_ES"),
            InlineKeyboardButton(f"{LANGUAGES['it']['flag']} {LANGUAGES['it']['name']}", callback_data="lang_it")
        ],
        [
            InlineKeyboardButton(f"{LANGUAGES['zh_CN']['flag']} {LANGUAGES['zh_CN']['name']}", callback_data="lang_zh_CN"),
            InlineKeyboardButton(f"{LANGUAGES['bn']['flag']} {LANGUAGES['bn']['name']}", callback_data="lang_bn")
        ],
        [
            InlineKeyboardButton(f"{LANGUAGES['hi']['flag']} {LANGUAGES['hi']['name']}", callback_data="lang_hi"),
            InlineKeyboardButton(f"{LANGUAGES['pt_BR']['flag']} {LANGUAGES['pt_BR']['name']}", callback_data="lang_pt_BR")
        ],
        [
            InlineKeyboardButton(f"{LANGUAGES['ar']['flag']} {LANGUAGES['ar']['name']}", callback_data="lang_ar"),
            InlineKeyboardButton(f"{LANGUAGES['uk']['flag']} {LANGUAGES['uk']['name']}", callback_data="lang_uk")
        ],
        # Oxirgi tugma (Vietnamcha) alohida qatorga
        [
            InlineKeyboardButton(f"{LANGUAGES['vi']['flag']} {LANGUAGES['vi']['name']}", callback_data="lang_vi")
        ]
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
# ---------------- START handleri ----------------
# ---------------- Tilni o'zgartirish handleri (CALLBACK) ----------------
async def language_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang_code = q.data.split("_")[1]
    user = q.from_user
    await add_user_db(context.application.bot_data["db_pool"], user, lang_code)
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    # Asosiy menyuni yaratish
    kb = [
        [InlineKeyboardButton(lang["gen_button"], callback_data="start_gen")],
        [InlineKeyboardButton(lang["ai_button"], callback_data="start_ai_flow")],
        [InlineKeyboardButton(lang["donate_button"], callback_data="donate_custom")],
        [InlineKeyboardButton(lang["lang_button"], callback_data="change_language")]
    ]
    await q.edit_message_text(
        text=lang["lang_changed"].format(lang=lang["name"]),
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return ConversationHandler.END
    
# Yangilangan: Yangi AI chat tugmasi qo'shildi
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang_code = None
    async with context.application.bot_data["db_pool"].acquire() as conn:
        row = await conn.fetchrow("SELECT language_code FROM users WHERE id = $1", user_id)
        if row:
            lang_code = row["language_code"]
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])
    # Tugmalarni yaratishda faqat tarjima qilingan "AI bilan suhbat" tugmasi qo'shiladi
    kb = [
        [InlineKeyboardButton(lang["gen_button"], callback_data="start_gen")],
        [InlineKeyboardButton(lang["ai_button"], callback_data="start_ai_flow")], # Faqat shu qator
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
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

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

    # Tugmalarni yonma-yon qilish uchun bitta qatorga joylashtiramiz
    kb = [
        [
            InlineKeyboardButton("1️⃣", callback_data="count_1"),
            InlineKeyboardButton("2️⃣", callback_data="count_2"),
            InlineKeyboardButton("4️⃣", callback_data="count_4"),
            InlineKeyboardButton("8️⃣", callback_data="count_8")
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
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

    # Agar foydalanuvchi oldin "AI chat" tugmasini bosgan bo'lsa
    flow = context.user_data.get("flow")
    if flow == "ai":
        # Oxirgi faollik vaqtini tekshirish
        last_active = context.user_data.get("last_active")
        now = datetime.now(timezone.utc)
        if last_active:
            # 15 daqiqa = 900 sekund
            if (now - last_active).total_seconds() > 900:
                # Vaqt o'tgan, flow ni bekor qilamiz
                context.user_data["flow"] = None
                context.user_data["last_active"] = None
                # Quyidagi kod oddiy matn yuborilganda ishlaydi (pastga tushadi)
            else:
                # Vaqt o'tmagan, AI chat davom etadi
                prompt = update.message.text
                # AI javobini oddiy matn sifatida yuborish, maxsus belgilarsiz
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
                except Exception as e:
                    logger.exception("[GEMINI ERROR]")
                    answer = lang["error"]
                # AI javobini oddiy matn sifatida yuborish, Markdown formatlashsiz
                await update.message.reply_text(f"{lang['ai_response_header']}\n{answer}")
                # Oxirgi faollik vaqtini yangilash
                context.user_data["last_active"] = datetime.now(timezone.utc)
                return
        else:
            # Biror sababdan last_active yo'q, lekin flow "ai"
            # Bu holat kam uchraydi, lekin ehtimolni hisobga olamiz
            prompt = update.message.text
            await update.message.reply_text(f"{lang['your_prompt_label']}\n{answer}")
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
            await update.message.reply_text(f"{lang['ai_response_header']}\n{answer}")
            context.user_data["last_active"] = datetime.now(timezone.utc)
            return

    # Agar hech qanday maxsus flow bo'lmasa, oddiy rasm generatsiya jarayoni ketaveradi
    # (start_gen orqali kirilganda ham, oddiy matn yuborilganda ham)
    if not await force_sub_if_private(update, context, lang_code):
        return

    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data["prompt"] = prompt

    # --- Yangi: Promptni Gemini orqali Digen uchun tayyorlash ---
    original_prompt = prompt # Foydalanuvchi yuborgan original prompt
    logger.info(f"[GEMINI PROMPT] Foydalanuvchi prompti: {original_prompt}")

    # Qadam 1: Gemini API ga yuborish uchun prompt tayyorlash
    gemini_instruction = "Auto detect this language and translate this text to English for image generation. No other text, just the translated prompt:"
    gemini_full_prompt = f"{gemini_instruction}\n{original_prompt}"

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        gemini_response = await model.generate_content_async(
            gemini_full_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=100, # Qisqa tarjima yetarli
                temperature=0.5
            )
        )
        digen_ready_prompt = gemini_response.text.strip()
        # Agar Gemini hech narsa qaytarmasa, original promptni ishlatamiz
        if not digen_ready_prompt:
            logger.warning("[GEMINI PROMPT] Gemini javob bermadi. Original prompt ishlatilmoqda.")
            digen_ready_prompt = original_prompt # Yoki xatolik qaytaramiz
        logger.info(f"[GEMINI PROMPT] Digen uchun tayyor prompt: {digen_ready_prompt}")
        context.user_data["translated"] = digen_ready_prompt # Tarjima qilingan promptni saqlash
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
        # Yangilangan qatorlar, tarjima qilingan
        await update.message.reply_text(
            f"{lang['choose_action']}\n*{lang['your_message']}* {escape_md(prompt)}",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return
    else: # start_gen orqali kirilganda flow "image_pending_prompt" bo'ladi
        # "Nechta rasm?" so'rovi chiqadi
        kb = [
            [
                InlineKeyboardButton("1️⃣", callback_data="count_1"),
                InlineKeyboardButton("2️⃣", callback_data="count_2"),
                InlineKeyboardButton("4️⃣", callback_data="count_4"),
                InlineKeyboardButton("8️⃣", callback_data="count_8")
            ]
        ]
        await update.message.reply_text(
            f"{lang['select_count']}\n🖌 Sizning matningiz:\n{escape_md(prompt)}",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
# ---------------- Tanlov tugmachasi orqali rasm generatsiya ----------------
# Yangilangan: context.user_data["flow"] o'rnatiladi
# ---------------- Tanlov tugmachasi orqali rasm generatsiya ----------------
# Yangilangan: context.user_data["flow"] o'rnatiladi
async def gen_image_from_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # flow o'zgaruvchisini o'rnatamiz
    context.user_data["flow"] = "image_pending_prompt"
    # To'g'ridan-to'g'ri 1 ta rasm generatsiya qilamiz
    # Eski usul (xato beradi): fake_update.callback_query = q
    # Yangi, to'g'ri usul: generate_cb ni to'g'ridan-to'g'ri chaqiramiz
    # generate_cb ga callback_query ni o'zini uzatamiz
    # generate_cb funksiyasi faqat callback_query dan foydalanadi, shuning uchun update obyektini butunlay yaratish shart emas
    # generate_cb ni chaqirishda, update o'rniga yangi Update obyektini yaratib, callback_query ni unga beramiz
    # 1. generate_cb ga uzatish uchun yangi Update obyektini yaratamiz
    fake_update = Update(update.update_id, callback_query=q)
    # 2. generate_cb ga chaqiruv
    await generate_cb(fake_update, context)

# ---------------- Tanlov tugmachasi orqali AI chat ----------------
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
    # Faqat bitta marta, tarjima qilingan xabarni yuborish
    await q.message.reply_text(lang["ai_prompt_text"])

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
                f"🎨 Rasm tayyor!\n\n" 
                f"📝 Prompt: {escaped_prompt}\n" # escape_md qilingan prompt
                f"🔢 Soni: {count}\n"
                f"⏰ Vaqt (UTC+5): {tashkent_time().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"⏱ Yaratish uchun ketgan vaqt: {elapsed_time:.1f}s"
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

    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

    if update.callback_query:
        await update.callback_query.message.reply_text(lang["donate_prompt"])
    else:
        await update.message.reply_text(lang["donate_prompt"])
    return WAITING_AMOUNT

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
    lang = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANGUAGE])

    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        await update.message.reply_text(lang["donate_invalid"])
        return WAITING_AMOUNT
        # Yangi: donate jarayoni davom etayotgani uchun, WAITING_AMOUNT qaytaramiz
        # Agar ConversationHandler ishlamayotgan bo'lsa, bu hech narsa o'zgartirmaydi
        return WAITING_AMOUNT 

    # ... (qolgan kodlar - invoice yuborish) ...
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
    # Oxirida ConversationHandler tugashi kerak
    return ConversationHandler.END

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

    # ... (qolgan handlerlar o'zgarmaydi)
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
