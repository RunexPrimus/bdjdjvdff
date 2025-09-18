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
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

import asyncpg
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, LabeledPrice, User, Message
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
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@SizningKanal")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))  # e.g. '[{"token":"...","session":"..."}]'
DIGEN_URL = os.getenv("DIGEN_URL", "https://api.digen.ai/v2/tools/text_to_image").strip()
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not DATABASE_URL:
    logger.error("DATABASE_URL muhim! ENV ga qo'ying.")
    raise SystemExit(1)
if not BOT_USERNAME:
    logger.warning("BOT_USERNAME not set. Referral links might be incorrect.")

# ---------------- STATE MANAGEMENT ----------------
# Conversation states
DONATE_AMOUNT = 1
ADMIN_BROADCAST_MESSAGE = 1
ADMIN_BAN_USER_ID = 1
ADMIN_UNBAN_USER_ID = 1

# User data keys
USER_DATA_LANG = "lang"
USER_DATA_PROMPT = "prompt"
USER_DATA_TRANSLATED = "translated"
USER_DATA_LAST_PROGRESS_MSG_ID = "last_progress_msg_id"
USER_DATA_PROGRESS_JOB = "progress_job"

# ---------------- TRANSLATIONS ----------------
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
        "btn_back": "⬅️ Back",
        "enter_prompt": "✍️ Please send the text prompt for the image (in private chat).",
        "prompt_received": "🖌 Your prompt:\n{prompt}\n\n🔢 How many images to generate?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Generating image(s) ({count})... ⏳",
        "generating_8_limited": "🔄 Generating image(s) ({count})... ⏳ (Used {used}/{limit} free 8-batches today)",
        "insufficient_balance_8": "⚠️ You have already used 3 free 8-image generations today. Each subsequent 8-image generation costs 1 Star. Insufficient balance.",
        "stars_deducted": "💳 {price} Star(s) deducted. Generating image(s) ({count})... ⏳",
        "image_ready": "✅ Image(s) ready! 📸",
        "btn_generate_again": "🔄 Generate Again",
        "account_title": "👤 My Account",
        "account_balance": "💳 Balance: {balance} Stars",
        "account_referrals": "👥 Referred Users: {count}",
        "account_referral_link": "🔗 Your Referral Link:\n{link}",
        "account_withdraw": "📤 Withdraw",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Withdrawal feature is not ready yet — Coming soon! ⏳",
        "api_soon": "🔑 API access: Coming soon!",
        "info_title": "📊 Statistics",
        "info_uptime": "⏱ Uptime: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Users: {count}",
        "info_images": "🖼 Total Images Generated: {count}",
        "info_donations": "💰 Total Donations: {amount}",
        "btn_contact_admin": "📩 Contact Admin",
        "sub_check_prompt": "⛔ You must be subscribed to our channel to use the bot!",
        "sub_check_link_text": "🔗 Subscribe to Channel",
        "sub_check_button_text": "✅ Check Subscription",
        "sub_check_success": "✅ Thank you! You are subscribed. You can now use the bot.",
        "sub_check_fail": "⛔ You are still not subscribed. Please subscribe and check again.",
        "invalid_button": "❌ Invalid button.",
        "error_try_again": "⚠️ An error occurred. Please try again.",
        "image_wait_timeout": "⚠️ It's taking a while to prepare the image. Please try again later.",
        "image_id_missing": "❌ Failed to get image ID (API response).",
        "api_unknown_response": "❌ Unknown response from API. Please contact the admin.",
        "enter_donate_amount": "💰 Please enter the amount you want to donate (1–100000):",
        "invalid_donate_amount": "❌ Please enter an integer between 1 and 100000.",
        "donate_invoice_title": "💖 Bot Donation",
        "donate_invoice_description": "Send an optional amount to support the bot.",
        "donate_thanks": "✅ Thank you, {first_name}! You sent {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Withdraw: Coming soon",
        "account_api_soon": "🔑 API: Coming soon",
        "referral_reward": "You received {reward} Stars for a successful referral!",
        "prompt_missing_group": "❌ In a group, please provide a prompt after /get. Example: /get futuristic city",
        "prompt_missing_private": "✍️ Please send the text prompt for the image (or just send plain text).",
        "prompt_received_private": "🖌 Your prompt:\n{prompt}\n\n🔢 How many images to generate?",
        "prompt_received_group": "🖌 Your prompt:\n{prompt}\n\n🔢 How many images to generate?",
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
        "btn_back": "⬅️ Назад",
        "enter_prompt": "✍️ Пожалуйста, отправьте текстовый запрос для изображения (в личном чате).",
        "prompt_received": "🖌 Ваш запрос:\n{prompt}\n\n🔢 Сколько изображений сгенерировать?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Генерация изображения(й) ({count})... ⏳",
        "generating_8_limited": "🔄 Генерация изображения(й) ({count})... ⏳ (Использовано {used}/{limit} бесплатных пакетов по 8 сегодня)",
        "insufficient_balance_8": "⚠️ Вы уже использовали 3 бесплатные генерации по 8 изображений сегодня. Каждая последующая генерация из 8 изображений стоит 1 Star. Недостаточный баланс.",
        "stars_deducted": "💳 Списано {price} Star(s). Генерация изображения(й) ({count})... ⏳",
        "image_ready": "✅ Изображение(я) готово(ы)! 📸",
        "btn_generate_again": "🔄 Создать снова",
        "account_title": "👤 Мой аккаунт",
        "account_balance": "💳 Баланс: {balance} Stars",
        "account_referrals": "👥 Приглашенные пользователи: {count}",
        "account_referral_link": "🔗 Ваша реферальная ссылка:\n{link}",
        "account_withdraw": "📤 Вывести",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Функция вывода ещё не готова — Скоро будет! ⏳",
        "api_soon": "🔑 Доступ к API: Скоро!",
        "info_title": "📊 Статистика",
        "info_uptime": "⏱ Время работы: {uptime}",
        "info_ping": "🌐 Пинг: {ping} мс",
        "info_users": "👥 Пользователи: {count}",
        "info_images": "🖼 Всего сгенерировано изображений: {count}",
        "info_donations": "💰 Всего пожертвований: {amount}",
        "btn_contact_admin": "📩 Связаться с админом",
        "sub_check_prompt": "⛔ Вы должны быть подписаны на наш канал, чтобы использовать бота!",
        "sub_check_link_text": "🔗 Подписаться на канал",
        "sub_check_button_text": "✅ Проверить подписку",
        "sub_check_success": "✅ Спасибо! Вы подписаны. Теперь вы можете использовать бота.",
        "sub_check_fail": "⛔ Вы всё ещё не подписаны. Пожалуйста, подпишитесь и проверьте снова.",
        "invalid_button": "❌ Неверная кнопка.",
        "error_try_again": "⚠️ Произошла ошибка. Пожалуйста, попробуйте снова.",
        "image_wait_timeout": "⚠️ Подготовка изображения занимает много времени. Пожалуйста, попробуйте позже.",
        "image_id_missing": "❌ Не удалось получить ID изображения (ответ API).",
        "api_unknown_response": "❌ Неизвестный ответ от API. Пожалуйста, свяжитесь с администратором.",
        "enter_donate_amount": "💰 Пожалуйста, введите сумму пожертвования (1–100000):",
        "invalid_donate_amount": "❌ Пожалуйста, введите целое число от 1 до 100000.",
        "donate_invoice_title": "💖 Пожертвование боту",
        "donate_invoice_description": "Отправьте произвольную сумму для поддержки бота.",
        "donate_thanks": "✅ Спасибо, {first_name}! Вы отправили {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Вывести: Скоро",
        "account_api_soon": "🔑 API: Скоро",
        "referral_reward": "Вы получили {reward} Stars за успешное приглашение!",
        "prompt_missing_group": "❌ В группе, пожалуйста, укажите запрос после /get. Пример: /get футуристический город",
        "prompt_missing_private": "✍️ Пожалуйста, отправьте текстовый запрос для изображения (или просто отправьте текст).",
        "prompt_received_private": "🖌 Ваш запрос:\n{prompt}\n\n🔢 Сколько изображений сгенерировать?",
        "prompt_received_group": "🖌 Ваш запрос:\n{prompt}\n\n🔢 Сколько изображений сгенерировать?",
    },
    "id": {
        "choose_language": "🌐 Silakan pilih bahasa Anda:",
        "language_set": "✅ Bahasa diatur ke {lang_code}.",
        "main_panel_text": "👋 Panel utama — kelola gambar, saldo, dan pengaturan di sini.",
        "btn_generate": "🎨 Buat Gambar",
        "btn_donate": "💖 Donasi",
        "btn_account": "👤 Akun Saya",
        "btn_change_lang": "🌐 Ubah Bahasa",
        "btn_info": "ℹ️ Info / Statistik",
        "btn_back": "⬅️ Kembali",
        "enter_prompt": "✍️ Silakan kirim prompt teks untuk gambar (di chat pribadi).",
        "prompt_received": "🖌 Prompt Anda:\n{prompt}\n\n🔢 Berapa banyak gambar yang akan dibuat?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Membuat gambar ({count})... ⏳",
        "generating_8_limited": "🔄 Membuat gambar ({count})... ⏳ (Digunakan {used}/{limit} batch 8 gratis hari ini)",
        "insufficient_balance_8": "⚠️ Anda sudah menggunakan 3 pembuatan gambar 8 gratis hari ini. Setiap pembuatan berikutnya memerlukan 1 Star. Saldo tidak mencukupi.",
        "stars_deducted": "💳 {price} Star(s) telah dikurangi. Membuat gambar ({count})... ⏳",
        "image_ready": "✅ Gambar siap! 📸",
        "btn_generate_again": "🔄 Buat Lagi",
        "account_title": "👤 Akun Saya",
        "account_balance": "💳 Saldo: {balance} Stars",
        "account_referrals": "👥 Pengguna yang Diundang: {count}",
        "account_referral_link": "🔗 Tautan Referral Anda:\n{link}",
        "account_withdraw": "📤 Tarik",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Fitur penarikan belum siap — Akan datang segera! ⏳",
        "api_soon": "🔑 Akses API: Akan datang segera!",
        "info_title": "📊 Statistik",
        "info_uptime": "⏱ Waktu Aktif: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Pengguna: {count}",
        "info_images": "🖼 Total Gambar yang Dibuat: {count}",
        "info_donations": "💰 Total Donasi: {amount}",
        "btn_contact_admin": "📩 Hubungi Admin",
        "sub_check_prompt": "⛔ Anda harus berlangganan ke channel kami untuk menggunakan bot!",
        "sub_check_link_text": "🔗 Berlangganan ke Channel",
        "sub_check_button_text": "✅ Periksa Langganan",
        "sub_check_success": "✅ Terima kasih! Anda sudah berlangganan. Sekarang Anda dapat menggunakan bot.",
        "sub_check_fail": "⛔ Anda belum berlangganan. Silakan berlangganan dan periksa lagi.",
        "invalid_button": "❌ Tombol tidak valid.",
        "error_try_again": "⚠️ Terjadi kesalahan. Silakan coba lagi.",
        "image_wait_timeout": "⚠️ Memakan waktu lama untuk menyiapkan gambar. Silakan coba lagi nanti.",
        "image_id_missing": "❌ Gagal mendapatkan ID gambar (respons API).",
        "api_unknown_response": "❌ Respons tidak dikenal dari API. Silakan hubungi admin.",
        "enter_donate_amount": "💰 Silakan masukkan jumlah yang ingin Anda donasikan (1–100000):",
        "invalid_donate_amount": "❌ Silakan masukkan bilangan bulat antara 1 dan 100000.",
        "donate_invoice_title": "💖 Donasi Bot",
        "donate_invoice_description": "Kirim jumlah opsional untuk mendukung bot.",
        "donate_thanks": "✅ Terima kasih, {first_name}! Anda mengirim {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Tarik: Akan Datang",
        "account_api_soon": "🔑 API: Akan Datang",
        "referral_reward": "Anda menerima {reward} Stars untuk referral yang berhasil!",
        "prompt_missing_group": "❌ Di grup, silakan berikan prompt setelah /get. Contoh: /get kota futuristik",
        "prompt_missing_private": "✍️ Silakan kirim prompt teks untuk gambar (atau kirim teks biasa saja).",
        "prompt_received_private": "🖌 Prompt Anda:\n{prompt}\n\n🔢 Berapa banyak gambar yang akan dibuat?",
        "prompt_received_group": "🖌 Prompt Anda:\n{prompt}\n\n🔢 Berapa banyak gambar yang akan dibuat?",
    },
    "lt": {
        "choose_language": "🌐 Pasirinkite savo kalbą:",
        "language_set": "✅ Kalba nustatyta į {lang_code}.",
        "main_panel_text": "👋 Pagrindinis skydelis — čia valdykite vaizdus, balansą ir nustatymus.",
        "btn_generate": "🎨 Kurti vaizdą",
        "btn_donate": "💖 Aukoti",
        "btn_account": "👤 Mano paskyra",
        "btn_change_lang": "🌐 Keisti kalbą",
        "btn_info": "ℹ️ Informacija / Statistika",
        "btn_back": "⬅️ Atgal",
        "enter_prompt": "✍️ Įveskite vaizdo aprašymą (privačiame pokalbyje).",
        "prompt_received": "🖌 Jūsų aprašymas:\n{prompt}\n\n🔢 Kiek vaizdų sugeneruoti?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Generuojamas vaizdas (-ai) ({count})... ⏳",
        "generating_8_limited": "🔄 Generuojamas vaizdas (-ai) ({count})... ⏳ (Naudojama {used}/{limit} nemokamų 8-vaizdų partijų šiandien)",
        "insufficient_balance_8": "⚠️ Šiandien jau naudojote 3 nemokamas 8-vaizdų generacijas. Kiekviena kita 8-vaizdų generacija kainuoja 1 Star. Nepakankamas balansas.",
        "stars_deducted": "💳 Nuskaičiuota {price} Star(s). Generuojamas vaizdas (-ai) ({count})... ⏳",
        "image_ready": "✅ Vaizdas (-ai) paruoštas! 📸",
        "btn_generate_again": "🔄 Kurti dar kartą",
        "account_title": "👤 Mano paskyra",
        "account_balance": "💳 Balansas: {balance} Stars",
        "account_referrals": "👥 Pakviesti vartotojai: {count}",
        "account_referral_link": "🔗 Jūsų kvietimo nuoroda:\n{link}",
        "account_withdraw": "📤 Išsiimti",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Išėmimo funkcija dar neparuošta — Greitai bus! ⏳",
        "api_soon": "🔑 API prieiga: Greitai bus!",
        "info_title": "📊 Statistika",
        "info_uptime": "⏱ Veikimo laikas: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Vartotojai: {count}",
        "info_images": "🖼 Iš viso sugeneruota vaizdų: {count}",
        "info_donations": "💰 Iš viso aukojimų: {amount}",
        "btn_contact_admin": "📩 Susisiekti su administratoriumi",
        "sub_check_prompt": "⛔ Norėdami naudoti botą, turite būti prenumeravę mūsų kanalą!",
        "sub_check_link_text": "🔗 Prenumeruoti kanalą",
        "sub_check_button_text": "✅ Patikrinti prenumeratą",
        "sub_check_success": "✅ Ačiū! Esate prenumeratorius. Dabar galite naudoti botą.",
        "sub_check_fail": "⛔ Vis dar nesate prenumeratorius. Prašome prenumeruoti ir patikrinti dar kartą.",
        "invalid_button": "❌ Netinkamas mygtukas.",
        "error_try_again": "⚠️ Įvyko klaida. Prašome bandyti dar kartą.",
        "image_wait_timeout": "⚠️ Užtrunka paruošti vaizdą. Prašome pabandyti vėliau.",
        "image_id_missing": "❌ Nepavyko gauti vaizdo ID (API atsakymas).",
        "api_unknown_response": "❌ Nežinomas API atsakymas. Prašome susisiekti su administratoriumi.",
        "enter_donate_amount": "💰 Įveskite sumą, kurią norite paaukoti (1–100000):",
        "invalid_donate_amount": "❌ Įveskite sveikąjį skaičių nuo 1 iki 100000.",
        "donate_invoice_title": "💖 Boto aukojimas",
        "donate_invoice_description": "Atsiųskite pasirinktiną sumą, kad palaikytumėte botą.",
        "donate_thanks": "✅ Ačiū, {first_name}! Jūs atsiuntėte {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Išsiimti: Greitai",
        "account_api_soon": "🔑 API: Greitai",
        "referral_reward": "Gavote {reward} Stars už sėkmingą kvietimą!",
        "prompt_missing_group": "❌ Grupėje po /get nurodykite aprašymą. Pavyzdys: /get futuristinis miestas",
        "prompt_missing_private": "✍️ Įveskite vaizdo aprašymą (arba tiesiog įveskite tekstą).",
        "prompt_received_private": "🖌 Jūsų aprašymas:\n{prompt}\n\n🔢 Kiek vaizdų sugeneruoti?",
        "prompt_received_group": "🖌 Jūsų aprašymas:\n{prompt}\n\n🔢 Kiek vaizdų sugeneruoti?",
    },
    "es-MX": {
        "choose_language": "🌐 Por favor, elige tu idioma:",
        "language_set": "✅ Idioma establecido a {lang_code}.",
        "main_panel_text": "👋 Panel principal — gestiona imágenes, saldo y configuraciones aquí.",
        "btn_generate": "🎨 Generar Imagen",
        "btn_donate": "💖 Donar",
        "btn_account": "👤 Mi Cuenta",
        "btn_change_lang": "🌐 Cambiar Idioma",
        "btn_info": "ℹ️ Información / Estadísticas",
        "btn_back": "⬅️ Atrás",
        "enter_prompt": "✍️ Por favor, envía el texto para la imagen (en chat privado).",
        "prompt_received": "🖌 Tu texto:\n{prompt}\n\n🔢 ¿Cuántas imágenes generar?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Generando imagen(es) ({count})... ⏳",
        "generating_8_limited": "🔄 Generando imagen(es) ({count})... ⏳ (Usadas {used}/{limit} tandas de 8 gratis hoy)",
        "insufficient_balance_8": "⚠️ Ya usaste 3 generaciones de 8 imágenes gratis hoy. Cada generación adicional cuesta 1 Star. Saldo insuficiente.",
        "stars_deducted": "💳 {price} Star(s) descontado(s). Generando imagen(es) ({count})... ⏳",
        "image_ready": "✅ ¡Imagen(es) lista(s)! 📸",
        "btn_generate_again": "🔄 Generar Otra Vez",
        "account_title": "👤 Mi Cuenta",
        "account_balance": "💳 Saldo: {balance} Stars",
        "account_referrals": "👥 Usuarios Referidos: {count}",
        "account_referral_link": "🔗 Tu Enlace de Referencia:\n{link}",
        "account_withdraw": "📤 Retirar",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Función de retiro aún no disponible — ¡Próximamente! ⏳",
        "api_soon": "🔑 Acceso API: ¡Próximamente!",
        "info_title": "📊 Estadísticas",
        "info_uptime": "⏱ Tiempo Activo: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Usuarios: {count}",
        "info_images": "🖼 Total de Imágenes Generadas: {count}",
        "info_donations": "💰 Donaciones Totales: {amount}",
        "btn_contact_admin": "📩 Contactar al Admin",
        "sub_check_prompt": "⛔ ¡Debes suscribirte a nuestro canal para usar el bot!",
        "sub_check_link_text": "🔗 Suscribirse al Canal",
        "sub_check_button_text": "✅ Verificar Suscripción",
        "sub_check_success": "✅ ¡Gracias! Estás suscrito. Ahora puedes usar el bot.",
        "sub_check_fail": "⛔ Aún no estás suscrito. Por favor, suscríbete y verifica de nuevo.",
        "invalid_button": "❌ Botón inválido.",
        "error_try_again": "⚠️ Ocurrió un error. Por favor, intenta de nuevo.",
        "image_wait_timeout": "⚠️ Tarda mucho en preparar la imagen. Por favor, intenta más tarde.",
        "image_id_missing": "❌ No se pudo obtener el ID de la imagen (respuesta de API).",
        "api_unknown_response": "❌ Respuesta desconocida de la API. Por favor, contacta al administrador.",
        "enter_donate_amount": "💰 Ingresa la cantidad que deseas donar (1–100000):",
        "invalid_donate_amount": "❌ Ingresa un número entero entre 1 y 100000.",
        "donate_invoice_title": "💖 Donación al Bot",
        "donate_invoice_description": "Envía una cantidad opcional para apoyar al bot.",
        "donate_thanks": "✅ ¡Gracias, {first_name}! Enviaste {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Retirar: Próximamente",
        "account_api_soon": "🔑 API: Próximamente",
        "referral_reward": "¡Recibiste {reward} Stars por una referencia exitosa!",
        "prompt_missing_group": "❌ En un grupo, por favor proporciona un texto después de /get. Ejemplo: /get ciudad futurista",
        "prompt_missing_private": "✍️ Por favor, envía el texto para la imagen (o simplemente envía texto).",
        "prompt_received_private": "🖌 Tu texto:\n{prompt}\n\n🔢 ¿Cuántas imágenes generar?",
        "prompt_received_group": "🖌 Tu texto:\n{prompt}\n\n🔢 ¿Cuántas imágenes generar?",
    },
    "es": {
        "choose_language": "🌐 Por favor, elige tu idioma:",
        "language_set": "✅ Idioma establecido a {lang_code}.",
        "main_panel_text": "👋 Panel principal — gestiona imágenes, saldo y configuraciones aquí.",
        "btn_generate": "🎨 Generar Imagen",
        "btn_donate": "💖 Donar",
        "btn_account": "👤 Mi Cuenta",
        "btn_change_lang": "🌐 Cambiar Idioma",
        "btn_info": "ℹ️ Información / Estadísticas",
        "btn_back": "⬅️ Atrás",
        "enter_prompt": "✍️ Por favor, envía el texto para la imagen (en chat privado).",
        "prompt_received": "🖌 Tu texto:\n{prompt}\n\n🔢 ¿Cuántas imágenes generar?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Generando imagen(es) ({count})... ⏳",
        "generating_8_limited": "🔄 Generando imagen(es) ({count})... ⏳ (Usadas {used}/{limit} tandas de 8 gratis hoy)",
        "insufficient_balance_8": "⚠️ Ya usaste 3 generaciones de 8 imágenes gratis hoy. Cada generación adicional cuesta 1 Star. Saldo insuficiente.",
        "stars_deducted": "💳 {price} Star(s) descontado(s). Generando imagen(es) ({count})... ⏳",
        "image_ready": "✅ ¡Imagen(es) lista(s)! 📸",
        "btn_generate_again": "🔄 Generar Otra Vez",
        "account_title": "👤 Mi Cuenta",
        "account_balance": "💳 Saldo: {balance} Stars",
        "account_referrals": "👥 Usuarios Referidos: {count}",
        "account_referral_link": "🔗 Tu Enlace de Referencia:\n{link}",
        "account_withdraw": "📤 Retirar",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Función de retiro aún no disponible — ¡Próximamente! ⏳",
        "api_soon": "🔑 Acceso API: ¡Próximamente!",
        "info_title": "📊 Estadísticas",
        "info_uptime": "⏱ Tiempo Activo: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Usuarios: {count}",
        "info_images": "🖼 Total de Imágenes Generadas: {count}",
        "info_donations": "💰 Donaciones Totales: {amount}",
        "btn_contact_admin": "📩 Contactar al Admin",
        "sub_check_prompt": "⛔ ¡Debes suscribirte a nuestro canal para usar el bot!",
        "sub_check_link_text": "🔗 Suscribirse al Canal",
        "sub_check_button_text": "✅ Verificar Suscripción",
        "sub_check_success": "✅ ¡Gracias! Estás suscrito. Ahora puedes usar el bot.",
        "sub_check_fail": "⛔ Aún no estás suscrito. Por favor, suscríbete y verifica de nuevo.",
        "invalid_button": "❌ Botón inválido.",
        "error_try_again": "⚠️ Ocurrió un error. Por favor, intenta de nuevo.",
        "image_wait_timeout": "⚠️ Tarda mucho en preparar la imagen. Por favor, intenta más tarde.",
        "image_id_missing": "❌ No se pudo obtener el ID de la imagen (respuesta de API).",
        "api_unknown_response": "❌ Respuesta desconocida de la API. Por favor, contacta al administrador.",
        "enter_donate_amount": "💰 Ingresa la cantidad que deseas donar (1–100000):",
        "invalid_donate_amount": "❌ Ingresa un número entero entre 1 y 100000.",
        "donate_invoice_title": "💖 Donación al Bot",
        "donate_invoice_description": "Envía una cantidad opcional para apoyar al bot.",
        "donate_thanks": "✅ ¡Gracias, {first_name}! Enviaste {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Retirar: Próximamente",
        "account_api_soon": "🔑 API: Próximamente",
        "referral_reward": "¡Recibiste {reward} Stars por una referencia exitosa!",
        "prompt_missing_group": "❌ En un grupo, por favor proporciona un texto después de /get. Ejemplo: /get ciudad futurista",
        "prompt_missing_private": "✍️ Por favor, envía el texto para la imagen (o simplemente envía texto).",
        "prompt_received_private": "🖌 Tu texto:\n{prompt}\n\n🔢 ¿Cuántas imágenes generar?",
        "prompt_received_group": "🖌 Tu texto:\n{prompt}\n\n🔢 ¿Cuántas imágenes generar?",
    },
    "it": {
        "choose_language": "🌐 Per favore, scegli la tua lingua:",
        "language_set": "✅ Lingua impostata su {lang_code}.",
        "main_panel_text": "👋 Pannello principale — gestisci immagini, saldo e impostazioni qui.",
        "btn_generate": "🎨 Genera Immagine",
        "btn_donate": "💖 Dona",
        "btn_account": "👤 Il mio account",
        "btn_change_lang": "🌐 Cambia lingua",
        "btn_info": "ℹ️ Info / Statistiche",
        "btn_back": "⬅️ Indietro",
        "enter_prompt": "✍️ Per favore, invia il testo per l'immagine (in chat privata).",
        "prompt_received": "🖌 Il tuo testo:\n{prompt}\n\n🔢 Quante immagini generare?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Generazione immagine/i ({count})... ⏳",
        "generating_8_limited": "🔄 Generazione immagine/i ({count})... ⏳ (Usate {used}/{limit} batch da 8 gratuite oggi)",
        "insufficient_balance_8": "⚠️ Hai già usato 3 generazioni di 8 immagini gratuite oggi. Ogni generazione successiva costa 1 Star. Saldo insufficiente.",
        "stars_deducted": "💳 {price} Star(s) detratti. Generazione immagine/i ({count})... ⏳",
        "image_ready": "✅ Immagine/i pronta/e! 📸",
        "btn_generate_again": "🔄 Genera di nuovo",
        "account_title": "👤 Il mio account",
        "account_balance": "💳 Saldo: {balance} Stars",
        "account_referrals": "👥 Utenti Referred: {count}",
        "account_referral_link": "🔗 Il tuo Link di Referral:\n{link}",
        "account_withdraw": "📤 Preleva",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Funzione di prelievo non ancora disponibile — Prossimamente! ⏳",
        "api_soon": "🔑 Accesso API: Prossimamente!",
        "info_title": "📊 Statistiche",
        "info_uptime": "⏱ Tempo di attività: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Utenti: {count}",
        "info_images": "🖼 Totale Immagini Generate: {count}",
        "info_donations": "💰 Donazioni Totali: {amount}",
        "btn_contact_admin": "📩 Contatta l'Admin",
        "sub_check_prompt": "⛔ Devi essere iscritto al nostro canale per usare il bot!",
        "sub_check_link_text": "🔗 Iscriviti al Canale",
        "sub_check_button_text": "✅ Verifica Iscrizione",
        "sub_check_success": "✅ Grazie! Sei iscritto. Ora puoi usare il bot.",
        "sub_check_fail": "⛔ Non sei ancora iscritto. Per favore, iscriviti e verifica di nuovo.",
        "invalid_button": "❌ Pulsante non valido.",
        "error_try_again": "⚠️ Si è verificato un errore. Per favore, riprova.",
        "image_wait_timeout": "⚠️ Ci sta impiegando troppo tempo per preparare l'immagine. Riprova più tardi.",
        "image_id_missing": "❌ Impossibile ottenere l'ID dell'immagine (risposta API).",
        "api_unknown_response": "❌ Risposta sconosciuta dall'API. Per favore, contatta l'amministratore.",
        "enter_donate_amount": "💰 Inserisci l'importo che desideri donare (1–100000):",
        "invalid_donate_amount": "❌ Inserisci un numero intero tra 1 e 100000.",
        "donate_invoice_title": "💖 Donazione al Bot",
        "donate_invoice_description": "Invia un importo facoltativo per sostenere il bot.",
        "donate_thanks": "✅ Grazie, {first_name}! Hai inviato {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Preleva: Prossimamente",
        "account_api_soon": "🔑 API: Prossimamente",
        "referral_reward": "Hai ricevuto {reward} Stars per un referral riuscito!",
        "prompt_missing_group": "❌ In un gruppo, fornisci un testo dopo /get. Esempio: /get città futuristica",
        "prompt_missing_private": "✍️ Per favore, invia il testo per l'immagine (o invia semplicemente del testo).",
        "prompt_received_private": "🖌 Il tuo testo:\n{prompt}\n\n🔢 Quante immagini generare?",
        "prompt_received_group": "🖌 Il tuo testo:\n{prompt}\n\n🔢 Quante immagini generare?",
    },
    "zh": {
        "choose_language": "🌐 请选择您的语言：",
        "language_set": "✅ 语言已设置为 {lang_code}。",
        "main_panel_text": "👋 主面板 — 在这里管理图片、余额和设置。",
        "btn_generate": "🎨 生成图片",
        "btn_donate": "💖 捐赠",
        "btn_account": "👤 我的账户",
        "btn_change_lang": "🌐 更改语言",
        "btn_info": "ℹ️ 信息 / 统计",
        "btn_back": "⬅️ 返回",
        "enter_prompt": "✍️ 请发送图片的文字提示（在私人聊天中）。",
        "prompt_received": "🖌 您的提示：\n{prompt}\n\n🔢 生成多少张图片？",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 正在生成图片 ({count})... ⏳",
        "generating_8_limited": "🔄 正在生成图片 ({count})... ⏳ (今日已使用 {used}/{limit} 次免费 8 张图片)",
        "insufficient_balance_8": "⚠️ 您今天已经使用了 3 次免费的 8 张图片生成。每次后续生成需要 1 Star。余额不足。",
        "stars_deducted": "💳 扣除 {price} Star(s)。正在生成图片 ({count})... ⏳",
        "image_ready": "✅ 图片已就绪！📸",
        "btn_generate_again": "🔄 再次生成",
        "account_title": "👤 我的账户",
        "account_balance": "💳 余额：{balance} Stars",
        "account_referrals": "👥 推荐用户：{count}",
        "account_referral_link": "🔗 您的推荐链接：\n{link}",
        "account_withdraw": "📤 提现",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 提现功能尚未准备好 — 即将推出！⏳",
        "api_soon": "🔑 API 访问：即将推出！",
        "info_title": "📊 统计信息",
        "info_uptime": "⏱ 运行时间：{uptime}",
        "info_ping": "🌐 延迟：{ping} 毫秒",
        "info_users": "👥 用户：{count}",
        "info_images": "🖼 总生成图片数：{count}",
        "info_donations": "💰 总捐赠：{amount}",
        "btn_contact_admin": "📩 联系管理员",
        "sub_check_prompt": "⛔ 您必须订阅我们的频道才能使用机器人！",
        "sub_check_link_text": "🔗 订阅频道",
        "sub_check_button_text": "✅ 检查订阅",
        "sub_check_success": "✅ 谢谢！您已订阅。现在可以使用机器人了。",
        "sub_check_fail": "⛔ 您尚未订阅。请订阅并再次检查。",
        "invalid_button": "❌ 无效按钮。",
        "error_try_again": "⚠️ 发生错误。请重试。",
        "image_wait_timeout": "⚠️ 准备图片花费的时间太长。请稍后再试。",
        "image_id_missing": "❌ 无法获取图片 ID（API 响应）。",
        "api_unknown_response": "❌ 来自 API 的未知响应。请联系管理员。",
        "enter_donate_amount": "💰 请输入您想捐赠的金额（1–100000）：",
        "invalid_donate_amount": "❌ 请输入 1 到 100000 之间的整数。",
        "donate_invoice_title": "💖 机器人捐赠",
        "donate_invoice_description": "发送任意金额以支持机器人。",
        "donate_thanks": "✅ 谢谢，{first_name}！您发送了 {amount_stars} Stars。",
        "account_withdraw_soon": "📤 提现：即将推出",
        "account_api_soon": "🔑 API：即将推出",
        "referral_reward": "您因成功推荐而获得了 {reward} Stars！",
        "prompt_missing_group": "❌ 在群组中，请在 /get 后提供提示。例如：/get 未来城市",
        "prompt_missing_private": "✍️ 请发送图片的文字提示（或直接发送文本）。",
        "prompt_received_private": "🖌 您的提示：\n{prompt}\n\n🔢 生成多少张图片？",
        "prompt_received_group": "🖌 您的提示：\n{prompt}\n\n🔢 生成多少张图片？",
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
        "btn_back": "⬅️ Ortga",
        "enter_prompt": "✍️ Endi tasvir yaratish uchun matn yuboring (privatda).",
        "prompt_received": "🖌 Sizning matningiz:\n{prompt}\n\n🔢 Nechta rasm yaratilsin?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Rasm yaratilmoqda ({count})... ⏳",
        "generating_8_limited": "🔄 Rasm yaratilmoqda ({count})... ⏳ (bugun {used}/{limit} dan foydalanildi)",
        "insufficient_balance_8": "⚠️ Siz bugun allaqachon 3 marta 8 ta rasm yaratdingiz. Har keyingi 8 ta generatsiya — 1 Stars. Balans yetarli emas.",
        "stars_deducted": "💳 {price} Stars yechildi. Rasm yaratilmoqda ({count})... ⏳",
        "image_ready": "✅ Rasm tayyor! 📸",
        "btn_generate_again": "🔄 Yana yaratish",
        "account_title": "👤 Hisobim",
        "account_balance": "💳 Balans: {balance} Stars",
        "account_referrals": "👥 Taklif qilinganlar: {count}",
        "account_referral_link": "🔗 Sizning referral link:\n{link}",
        "account_withdraw": "📤 Yechib olish",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Yechib olish funksiyasi hozircha tayyor emas — Tez kunda! ⏳",
        "api_soon": "🔑 API: Tez kunda",
        "info_title": "📊 Statistika",
        "info_uptime": "⏱ Ish vaqti (uptime): {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Foydalanuvchilar: {count}",
        "info_images": "🖼 Umumiy yaratilgan rasmlar: {count}",
        "info_donations": "💰 Umumiy donations: {amount}",
        "btn_contact_admin": "📩 Admin bilan bog‘lanish",
        "sub_check_prompt": "⛔ Botdan foydalanish uchun kanalimizga obuna bo‘ling!",
        "sub_check_link_text": "🔗 Kanalga obuna bo‘lish",
        "sub_check_button_text": "✅ Obunani tekshirish",
        "sub_check_success": "✅ Rahmat! Siz obuna bo‘lgansiz. Endi botdan foydalanishingiz mumkin.",
        "sub_check_fail": "⛔ Hali ham obuna bo‘lmagansiz. Obuna bo‘lib, qayta tekshiring.",
        "invalid_button": "❌ Noto'g'ri tugma.",
        "error_try_again": "⚠️ Xatolik yuz berdi. Qayta urinib ko‘ring.",
        "image_wait_timeout": "⚠️ Rasmni tayyorlash biroz vaqt olmoqda. Keyinroq urinib ko'ring.",
        "image_id_missing": "❌ Rasm ID olinmadi (API javobi).",
        "api_unknown_response": "❌ API dan noma'lum javob keldi. Adminga murojaat qiling.",
        "enter_donate_amount": "💰 Iltimos, yubormoqchi bo‘lgan miqdorni kiriting (1–100000):",
        "invalid_donate_amount": "❌ Iltimos, 1–100000 oralig‘ida butun son kiriting.",
        "donate_invoice_title": "💖 Bot Donation",
        "donate_invoice_description": "Botni qo‘llab-quvvatlash uchun ixtiyoriy summa yuboring.",
        "donate_thanks": "✅ Rahmat, {first_name}! Siz {amount_stars} Stars yubordingiz.",
        "account_withdraw_soon": "📤 Yechib olish: Tez kunda",
        "account_api_soon": "🔑 API: Tez kunda",
        "referral_reward": "Muvaffaqiyatli taklif qilish uchun {reward} Stars oldingiz!",
        "prompt_missing_group": "❌ Guruhda /get dan keyin prompt yozing. Misol: /get futuristik shahar",
        "prompt_missing_private": "✍️ Iltimos, rasm uchun matn yozing (yoki oddiy matn yuboring).",
        "prompt_received_private": "🖌 Sizning matningiz:\n{prompt}\n\n🔢 Nechta rasm yaratilsin?",
        "prompt_received_group": "🖌 Sizning matningiz:\n{prompt}\n\n🔢 Nechta rasm yaratilsin?",
    },
    "uzk": {
        "choose_language": "🌐 Илтимос, тилни танланг:",
        "language_set": "✅ Тил {lang_code} га ўзгартирилди.",
        "main_panel_text": "👋 Бош панел — бу ердан расмлар, баланс ва созламаларни бошқаришингиз мумкин.",
        "btn_generate": "🎨 Расм яратиш",
        "btn_donate": "💖 Донате",
        "btn_account": "👤 Ҳисобим",
        "btn_change_lang": "🌐 Тилни ўзгартириш",
        "btn_info": "ℹ️ Статистика / Инфо",
        "btn_back": "⬅️ Ортга",
        "enter_prompt": "✍️ Энди тасвир яратиш учун матн юборинг (приватда).",
        "prompt_received": "🖌 Сизнинг матнингиз:\n{prompt}\n\n🔢 Нечта расм яратилсин?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Расм яратилмоқда ({count})... ⏳",
        "generating_8_limited": "🔄 Расм яратилмоқда ({count})... ⏳ (бугун {used}/{limit} дан фойдаланилди)",
        "insufficient_balance_8": "⚠️ Сиз бугун аллақачон 3 марта 8 та расм яратдингиз. Ҳар кейинги 8 та генерация — 1 Старс. Баланс етарли эмас.",
        "stars_deducted": "💳 {price} Старс екилди. Расм яратилмоқда ({count})... ⏳",
        "image_ready": "✅ Расм тайёр! 📸",
        "btn_generate_again": "🔄 Яна яратиш",
        "account_title": "👤 Ҳисобим",
        "account_balance": "💳 Баланс: {balance} Старс",
        "account_referrals": "👥 Таклиф қилинганлар: {count}",
        "account_referral_link": "🔗 Сизнинг реферал линк:\n{link}",
        "account_withdraw": "📤 Ечиб олиш",
        "account_api": "🔑 АПИ",
        "withdraw_soon": "📤 Ечиб олиш функцияси ҳозирча тайёр эмас — Тез кунда! ⏳",
        "api_soon": "🔑 АПИ: Тез кунда",
        "info_title": "📊 Статистика",
        "info_uptime": "⏱ Иш вақти (uptime): {uptime}",
        "info_ping": "🌐 Пинг: {ping} мс",
        "info_users": "👥 Фойдаланувчилар: {count}",
        "info_images": "🖼 Умумий яратилган расмлар: {count}",
        "info_donations": "💰 Умумий донаций: {amount}",
        "btn_contact_admin": "📩 Админ билан боғланиш",
        "sub_check_prompt": "⛔ Ботдан фойдаланиш учун каналга обуна бўлинг!",
        "sub_check_link_text": "🔗 Каналга обуна бўлиш",
        "sub_check_button_text": "✅ Обунани текшириш",
        "sub_check_success": "✅ Раҳмат! Сиз обуна бўлдингиз. Энди ботдан фойдаланишингиз мумкин.",
        "sub_check_fail": "⛔ Ҳали ҳам обуна бўлмагансиз. Обуна бўлиб, қайта текширинг.",
        "invalid_button": "❌ Нотўғри тугма.",
        "error_try_again": "⚠️ Хатолик юз берди. Қайта уриниб кўринг.",
        "image_wait_timeout": "⚠️ Расмни тайёрлаш бироз вақт олмоқда. Кейинроқ уриниб кўринг.",
        "image_id_missing": "❌ Расм ИД олинмади (АПИ жавоби).",
        "api_unknown_response": "❌ АПИ дан номаълум жавоб келди. Админга муражат қилинг.",
        "enter_donate_amount": "💰 Илтимос, юбормоқчи бўлган миқдорни киритинг (1–100000):",
        "invalid_donate_amount": "❌ Илтимос, 1–100000 оралиғида бутун сон киритинг.",
        "donate_invoice_title": "💖 Бот Донатион",
        "donate_invoice_description": "Ботни қўллаб-қувватлаш учун ихтиёрий сумма юборинг.",
        "donate_thanks": "✅ Раҳмат, {first_name}! Сиз {amount_stars} Старс юбордингиз.",
        "account_withdraw_soon": "📤 Ечиб олиш: Тез кунда",
        "account_api_soon": "🔑 АПИ: Тез кунда",
        "referral_reward": "Муваффақиятли таклиф қилиш учун {reward} Старс олдингиз!",
        "prompt_missing_group": "❌ Гуруҳда /get дан кейин промпт ёзинг. Мисол: /get футуристик шаҳар",
        "prompt_missing_private": "✍️ Илтимос, расм учун матн ёзинг (ёки оддий матн юборинг).",
        "prompt_received_private": "🖌 Сизнинг матнингиз:\n{prompt}\n\n🔢 Нечта расм яратилсин?",
        "prompt_received_group": "🖌 Сизнинг матнингиз:\n{prompt}\n\n🔢 Нечта расм яратилсин?",
    },
    "bn": {
        "choose_language": "🌐 অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন:",
        "language_set": "✅ ভাষা {lang_code} এ সেট করা হয়েছে।",
        "main_panel_text": "👋 প্রধান প্যানেল — এখানে চিত্র, ব্যালেন্স এবং সেটিংস পরিচালনা করুন।",
        "btn_generate": "🎨 ছবি তৈরি করুন",
        "btn_donate": "💖 দান করুন",
        "btn_account": "👤 আমার অ্যাকাউন্ট",
        "btn_change_lang": "🌐 ভাষা পরিবর্তন করুন",
        "btn_info": "ℹ️ তথ্য / পরিসংখ্যান",
        "btn_back": "⬅️ পিছনে",
        "enter_prompt": "✍️ অনুগ্রহ করে ছবির জন্য টেক্সট প্রম্পট পাঠান (ব্যক্তিগত চ্যাটে)।",
        "prompt_received": "🖌 আপনার প্রম্পট:\n{prompt}\n\n🔢 কতগুলি ছবি তৈরি করবেন?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 ছবি তৈরি হচ্ছে ({count})... ⏳",
        "generating_8_limited": "🔄 ছবি তৈরি হচ্ছে ({count})... ⏳ (আজকে ব্যবহৃত {used}/{limit} টি বিনামূল্যে 8-ব্যাচ)",
        "insufficient_balance_8": "⚠️ আপনি ইতিমধ্যে আজ 3টি বিনামূল্যে 8-ছবি তৈরি করেছেন। পরবর্তী প্রতিটি 8-ছবি তৈরি 1 স্টার খরচ হবে। ব্যালেন্স অপর্যাপ্ত।",
        "stars_deducted": "💳 {price} স্টার(গুলি) কাটা হয়েছে। ছবি তৈরি হচ্ছে ({count})... ⏳",
        "image_ready": "✅ ছবি(গুলি) প্রস্তুত! 📸",
        "btn_generate_again": "🔄 আবার তৈরি করুন",
        "account_title": "👤 আমার অ্যাকাউন্ট",
        "account_balance": "💳 ব্যালেন্স: {balance} স্টার",
        "account_referrals": "👥 রেফার করা ব্যবহারকারী: {count}",
        "account_referral_link": "🔗 আপনার রেফারেল লিঙ্ক:\n{link}",
        "account_withdraw": "📤 উত্তোলন",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 উত্তোলন বৈশিষ্ট্য এখনও প্রস্তুত নয় — শীঘ্রই আসছে! ⏳",
        "api_soon": "🔑 API অ্যাক্সেস: শীঘ্রই!",
        "info_title": "📊 পরিসংখ্যান",
        "info_uptime": "⏱ আপটাইম: {uptime}",
        "info_ping": "🌐 পিং: {ping} মিলিসেকেন্ড",
        "info_users": "👥 ব্যবহারকারী: {count}",
        "info_images": "🖼 মোট তৈরি করা ছবি: {count}",
        "info_donations": "💰 মোট দান: {amount}",
        "btn_contact_admin": "📩 অ্যাডমিনের সাথে যোগাযোগ করুন",
        "sub_check_prompt": "⛔ বট ব্যবহার করতে আপনাকে আমাদের চ্যানেলে সাবস্ক্রাইব করতে হবে!",
        "sub_check_link_text": "🔗 চ্যানেলে সাবস্ক্রাইব করুন",
        "sub_check_button_text": "✅ সাবস্ক্রিপশন চেক করুন",
        "sub_check_success": "✅ ধন্যবাদ! আপনি সাবস্ক্রাইব করেছেন। এখন আপনি বট ব্যবহার করতে পারেন।",
        "sub_check_fail": "⛔ আপনি এখনও সাবস্ক্রাইব করেননি। অনুগ্রহ করে সাবস্ক্রাইব করুন এবং আবার চেক করুন।",
        "invalid_button": "❌ অবৈধ বোতাম।",
        "error_try_again": "⚠️ একটি ত্রুটি ঘটেছে। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "image_wait_timeout": "⚠️ ছবি প্রস্তুত করতে একটু সময় লাগছে। পরে আবার চেষ্টা করুন।",
        "image_id_missing": "❌ ছবি ID পাওয়া যায়নি (API প্রতিক্রিয়া)।",
        "api_unknown_response": "❌ API থেকে অজানা প্রতিক্রিয়া। অ্যাডমিনের সাথে যোগাযোগ করুন।",
        "enter_donate_amount": "💰 অনুগ্রহ করে আপনি দান করতে চান এমন পরিমাণ লিখুন (1–100000):",
        "invalid_donate_amount": "❌ অনুগ্রহ করে 1 থেকে 100000 এর মধ্যে একটি পূর্ণসংখ্যা লিখুন।",
        "donate_invoice_title": "💖 বট দান",
        "donate_invoice_description": "বট সমর্থনের জন্য একটি ঐচ্ছিক পরিমাণ পাঠান।",
        "donate_thanks": "✅ ধন্যবাদ, {first_name}! আপনি {amount_stars} স্টার পাঠিয়েছেন।",
        "account_withdraw_soon": "📤 উত্তোলন: শীঘ্রই",
        "account_api_soon": "🔑 API: শীঘ্রই",
        "referral_reward": "একটি সফল রেফারেলের জন্য আপনি {reward} স্টার পেয়েছেন!",
        "prompt_missing_group": "❌ একটি গ্রুপে, /get এর পরে একটি প্রম্পট সরবরাহ করুন। উদাহরণ: /get ভবিষ্যতবাণীমূলক শহর",
        "prompt_missing_private": "✍️ অনুগ্রহ করে ছবির জন্য টেক্সট প্রম্পট পাঠান (বা শুধু প্লেইন টেক্সট পাঠান)।",
        "prompt_received_private": "🖌 আপনার প্রম্পট:\n{prompt}\n\n🔢 কতগুলি ছবি তৈরি করবেন?",
        "prompt_received_group": "🖌 আপনার প্রম্পট:\n{prompt}\n\n🔢 কতগুলি ছবি তৈরি করবেন?",
    },
    "hi": {
        "choose_language": "🌐 कृपया अपनी भाषा चुनें:",
        "language_set": "✅ भाषा {lang_code} पर सेट हो गई है।",
        "main_panel_text": "👋 मुख्य पैनल — यहां चित्रों, शेष राशि और सेटिंग्स का प्रबंधन करें।",
        "btn_generate": "🎨 चित्र बनाएं",
        "btn_donate": "💖 दान करें",
        "btn_account": "👤 मेरा खाता",
        "btn_change_lang": "🌐 भाषा बदलें",
        "btn_info": "ℹ️ जानकारी / आंकड़े",
        "btn_back": "⬅️ वापस",
        "enter_prompt": "✍️ कृपया चित्र के लिए पाठ प्रॉम्प्ट भेजें (निजी चैट में)।",
        "prompt_received": "🖌 आपका प्रॉम्प्ट:\n{prompt}\n\n🔢 कितने चित्र बनाएं?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 चित्र बन रहा है ({count})... ⏳",
        "generating_8_limited": "🔄 चित्र बन रहा है ({count})... ⏳ (आज {used}/{limit} मुफ्त 8-बैच उपयोग किए गए)",
        "insufficient_balance_8": "⚠️ आपने आज पहले ही 3 मुफ्त 8-चित्र बनाने का उपयोग कर लिया है। प्रत्येक अगला 8-चित्र बनाना 1 स्टार लागत होगा। अपर्याप्त शेष राशि।",
        "stars_deducted": "💳 {price} स्टार(एस) काटे गए। चित्र बन रहा है ({count})... ⏳",
        "image_ready": "✅ चित्र(एस) तैयार है! 📸",
        "btn_generate_again": "🔄 फिर से बनाएं",
        "account_title": "👤 मेरा खाता",
        "account_balance": "💳 शेष राशि: {balance} स्टार",
        "account_referrals": "👥 रेफर किए गए उपयोगकर्ता: {count}",
        "account_referral_link": "🔗 आपका रेफरल लिंक:\n{link}",
        "account_withdraw": "📤 निकासी",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 निकासी सुविधा अभी तैयार नहीं है — जल्द आ रही है! ⏳",
        "api_soon": "🔑 API पहुंच: जल्द आ रही है!",
        "info_title": "📊 आंकड़े",
        "info_uptime": "⏱ अपटाइम: {uptime}",
        "info_ping": "🌐 पिंग: {ping} मिलीसेकंड",
        "info_users": "👥 उपयोगकर्ता: {count}",
        "info_images": "🖼 कुल बनाए गए चित्र: {count}",
        "info_donations": "💰 कुल दान: {amount}",
        "btn_contact_admin": "📩 व्यवस्थापक से संपर्क करें",
        "sub_check_prompt": "⛔ बॉट का उपयोग करने के लिए आपको हमारे चैनल की सदस्यता लेनी होगी!",
        "sub_check_link_text": "🔗 चैनल की सदस्यता लें",
        "sub_check_button_text": "✅ सदस्यता जांचें",
        "sub_check_success": "✅ धन्यवाद! आप सदस्य हैं। अब आप बॉट का उपयोग कर सकते हैं।",
        "sub_check_fail": "⛔ आप अभी भी सदस्य नहीं हैं। कृपया सदस्यता लें और फिर से जांचें।",
        "invalid_button": "❌ अमान्य बटन।",
        "error_try_again": "⚠️ एक त्रुटि हुई। कृपया पुनः प्रयास करें।",
        "image_wait_timeout": "⚠️ चित्र तैयार करने में थोड़ा समय लग रहा है। बाद में पुनः प्रयास करें।",
        "image_id_missing": "❌ चित्र ID प्राप्त नहीं हुआ (API प्रतिक्रिया)।",
        "api_unknown_response": "❌ API से अज्ञात प्रतिक्रिया। कृपया व्यवस्थापक से संपर्क करें।",
        "enter_donate_amount": "💰 कृपया दान करने के लिए राशि दर्ज करें (1–100000):",
        "invalid_donate_amount": "❌ कृपया 1 से 100000 के बीच एक पूर्णांक दर्ज करें।",
        "donate_invoice_title": "💖 बॉट दान",
        "donate_invoice_description": "बॉट के समर्थन के लिए एक वैकल्पिक राशि भेजें।",
        "donate_thanks": "✅ धन्यवाद, {first_name}! आपने {amount_stars} स्टार भेजे।",
        "account_withdraw_soon": "📤 निकासी: जल्द आ रही है",
        "account_api_soon": "🔑 API: जल्द आ रही है",
        "referral_reward": "एक सफल रेफरल के लिए आपको {reward} स्टार प्राप्त हुए!",
        "prompt_missing_group": "❌ एक समूह में, कृपया /get के बाद एक प्रॉम्प्ट प्रदान करें। उदाहरण: /get भविष्यवाणी शहर",
        "prompt_missing_private": "✍️ कृपया चित्र के लिए पाठ प्रॉम्प्ट भेजें (या सिर्फ प्लेन टेक्स्ट भेजें)।",
        "prompt_received_private": "🖌 आपका प्रॉम्प्ट:\n{prompt}\n\n🔢 कितने चित्र बनाएं?",
        "prompt_received_group": "🖌 आपका प्रॉम्प्ट:\n{prompt}\n\n🔢 कितने चित्र बनाएं?",
    },
    "pt": {
        "choose_language": "🌐 Por favor, escolha seu idioma:",
        "language_set": "✅ Idioma definido para {lang_code}.",
        "main_panel_text": "👋 Painel principal — gerencie imagens, saldo e configurações aqui.",
        "btn_generate": "🎨 Gerar Imagem",
        "btn_donate": "💖 Doar",
        "btn_account": "👤 Minha conta",
        "btn_change_lang": "🌐 Alterar idioma",
        "btn_info": "ℹ️ Informações / Estatísticas",
        "btn_back": "⬅️ Voltar",
        "enter_prompt": "✍️ Por favor, envie o texto para a imagem (no chat privado).",
        "prompt_received": "🖌 Seu texto:\n{prompt}\n\n🔢 Quantas imagens gerar?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Gerando imagem(ns) ({count})... ⏳",
        "generating_8_limited": "🔄 Gerando imagem(ns) ({count})... ⏳ (Usadas {used}/{limit} lotes de 8 grátis hoje)",
        "insufficient_balance_8": "⚠️ Você já usou 3 gerações de 8 imagens grátis hoje. Cada geração subsequente custa 1 Star. Saldo insuficiente.",
        "stars_deducted": "💳 {price} Star(s) deduzido(s). Gerando imagem(ns) ({count})... ⏳",
        "image_ready": "✅ Imagem(ns) pronta(s)! 📸",
        "btn_generate_again": "🔄 Gerar Novamente",
        "account_title": "👤 Minha conta",
        "account_balance": "💳 Saldo: {balance} Stars",
        "account_referrals": "👥 Usuários Indicados: {count}",
        "account_referral_link": "🔗 Seu Link de Indicação:\n{link}",
        "account_withdraw": "📤 Sacar",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Função de saque ainda não disponível — Em breve! ⏳",
        "api_soon": "🔑 Acesso à API: Em breve!",
        "info_title": "📊 Estatísticas",
        "info_uptime": "⏱ Tempo de atividade: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Usuários: {count}",
        "info_images": "🖼 Total de Imagens Geradas: {count}",
        "info_donations": "💰 Total de Doações: {amount}",
        "btn_contact_admin": "📩 Contatar Admin",
        "sub_check_prompt": "⛔ Você deve estar inscrito em nosso canal para usar o bot!",
        "sub_check_link_text": "🔗 Inscrever-se no Canal",
        "sub_check_button_text": "✅ Verificar Inscrição",
        "sub_check_success": "✅ Obrigado! Você está inscrito. Agora você pode usar o bot.",
        "sub_check_fail": "⛔ Você ainda não está inscrito. Por favor, inscreva-se e verifique novamente.",
        "invalid_button": "❌ Botão inválido.",
        "error_try_again": "⚠️ Ocorreu um erro. Por favor, tente novamente.",
        "image_wait_timeout": "⚠️ Está demorando para preparar a imagem. Por favor, tente mais tarde.",
        "image_id_missing": "❌ Falha ao obter o ID da imagem (resposta da API).",
        "api_unknown_response": "❌ Resposta desconhecida da API. Por favor, contate o administrador.",
        "enter_donate_amount": "💰 Por favor, insira o valor que deseja doar (1–100000):",
        "invalid_donate_amount": "❌ Por favor, insira um número inteiro entre 1 e 100000.",
        "donate_invoice_title": "💖 Doação ao Bot",
        "donate_invoice_description": "Envie um valor opcional para apoiar o bot.",
        "donate_thanks": "✅ Obrigado, {first_name}! Você enviou {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Sacar: Em Breve",
        "account_api_soon": "🔑 API: Em Breve",
        "referral_reward": "Você recebeu {reward} Stars por uma indicação bem-sucedida!",
        "prompt_missing_group": "❌ Em um grupo, por favor forneça um texto após /get. Exemplo: /get cidade futurista",
        "prompt_missing_private": "✍️ Por favor, envie o texto para a imagem (ou apenas envie texto).",
        "prompt_received_private": "🖌 Seu texto:\n{prompt}\n\n🔢 Quantas imagens gerar?",
        "prompt_received_group": "🖌 Seu texto:\n{prompt}\n\n🔢 Quantas imagens gerar?",
    },
    "ar": {
        "choose_language": "🌐 يرجى اختيار لغتك:",
        "language_set": "✅ تم تعيين اللغة إلى {lang_code}.",
        "main_panel_text": "👋 اللوحة الرئيسية — إدارة الصور والرصيد والإعدادات هنا.",
        "btn_generate": "🎨 إنشاء صورة",
        "btn_donate": "💖 تبرع",
        "btn_account": "👤 حسابي",
        "btn_change_lang": "🌐 تغيير اللغة",
        "btn_info": "ℹ️ معلومات / إحصائيات",
        "btn_back": "⬅️ رجوع",
        "enter_prompt": "✍️ يرجى إرسال نص الصورة (في الدردشة الخاصة).",
        "prompt_received": "🖌 النص الخاص بك:\n{prompt}\n\n🔢 كم عدد الصور المراد إنشاؤها؟",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 جاري إنشاء الصورة(الصور) ({count})... ⏳",
        "generating_8_limited": "🔄 جاري إنشاء الصورة(الصور) ({count})... ⏳ (تم استخدام {used}/{limit} دفعات مجانية من 8 اليوم)",
        "insufficient_balance_8": "⚠️ لقد استخدمت بالفعل 3 إنشاءات مجانية من 8 صور اليوم. يكلف كل إنشاء لاحق 1 نجمة. الرصيد غير كافٍ.",
        "stars_deducted": "💳 تم خصم {price} نجمة(نجمات). جاري إنشاء الصورة(الصور) ({count})... ⏳",
        "image_ready": "✅ الصورة(الصور) جاهزة! 📸",
        "btn_generate_again": "🔄 إنشاء مرة أخرى",
        "account_title": "👤 حسابي",
        "account_balance": "💳 الرصيد: {balance} نجمة",
        "account_referrals": "👥 المستخدمون المشار إليهم: {count}",
        "account_referral_link": "🔗 رابط الإحالة الخاص بك:\n{link}",
        "account_withdraw": "📤 سحب",
        "account_api": "🔑 واجهة برمجة التطبيقات",
        "withdraw_soon": "📤 ميزة السحب ليست جاهزة بعد — قريباً! ⏳",
        "api_soon": "🔑 الوصول إلى واجهة برمجة التطبيقات: قريباً!",
        "info_title": "📊 الإحصائيات",
        "info_uptime": "⏱ مدة التشغيل: {uptime}",
        "info_ping": "🌐 البينغ: {ping} مللي ثانية",
        "info_users": "👥 المستخدمون: {count}",
        "info_images": "🖼 إجمالي الصور المُنشأة: {count}",
        "info_donations": "💰 إجمالي التبرعات: {amount}",
        "btn_contact_admin": "📩 الاتصال بالمشرف",
        "sub_check_prompt": "⛔ يجب أن تكون مشتركًا في قناتنا لاستخدام البوت!",
        "sub_check_link_text": "🔗 الاشتراك في القناة",
        "sub_check_button_text": "✅ التحقق من الاشتراك",
        "sub_check_success": "✅ شكرًا لك! أنت مشترك. يمكنك الآن استخدام البوت.",
        "sub_check_fail": "⛔ أنت لا تزال غير مشترك. يرجى الاشتراك والتحقق مرة أخرى.",
        "invalid_button": "❌ زر غير صالح.",
        "error_try_again": "⚠️ حدث خطأ. يرجى المحاولة مرة أخرى.",
        "image_wait_timeout": "⚠️ يستغرق الأمر بعض الوقت لإعداد الصورة. يرجى المحاولة لاحقًا.",
        "image_id_missing": "❌ فشل في الحصول على معرف الصورة (رد واجهة برمجة التطبيقات).",
        "api_unknown_response": "❌ رد غير معروف من واجهة برمجة التطبيقات. يرجى الاتصال بالمشرف.",
        "enter_donate_amount": "💰 يرجى إدخال المبلغ الذي ترغب في التبرع به (1–100000):",
        "invalid_donate_amount": "❌ يرجى إدخال عدد صحيح بين 1 و 100000.",
        "donate_invoice_title": "💖 تبرع للبوت",
        "donate_invoice_description": "أرسل مبلغًا اختياريًا لدعم البوت.",
        "donate_thanks": "✅ شكرًا لك، {first_name}! لقد أرسلت {amount_stars} نجمة.",
        "account_withdraw_soon": "📤 سحب: قريباً",
        "account_api_soon": "🔑 واجهة برمجة التطبيقات: قريباً",
        "referral_reward": "لقد تلقيت {reward} نجمة لدعوة ناجحة!",
        "prompt_missing_group": "❌ في مجموعة، يرجى تقديم نص بعد /get. مثال: /get مدينة مستقبلية",
        "prompt_missing_private": "✍️ يرجى إرسال نص الصورة (أو فقط إرسال نص عادي).",
        "prompt_received_private": "🖌 النص الخاص بك:\n{prompt}\n\n🔢 كم عدد الصور المراد إنشاؤها؟",
        "prompt_received_group": "🖌 النص الخاص بك:\n{prompt}\n\n🔢 كم عدد الصور المراد إنشاؤها؟",
    },
    "uk": {
        "choose_language": "🌐 Будь ласка, виберіть свою мову:",
        "language_set": "✅ Мову встановлено на {lang_code}.",
        "main_panel_text": "👋 Головна панель — керуйте зображеннями, балансом і налаштуваннями тут.",
        "btn_generate": "🎨 Створити зображення",
        "btn_donate": "💖 Пожертвувати",
        "btn_account": "👤 Мій акаунт",
        "btn_change_lang": "🌐 Змінити мову",
        "btn_info": "ℹ️ Інформація / Статистика",
        "btn_back": "⬅️ Назад",
        "enter_prompt": "✍️ Будь ласка, надішліть текстовий запит для зображення (в приватному чаті).",
        "prompt_received": "🖌 Ваш запит:\n{prompt}\n\n🔢 Скільки зображень згенерувати?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Генерація зображення(й) ({count})... ⏳",
        "generating_8_limited": "🔄 Генерація зображення(й) ({count})... ⏳ (Використано {used}/{limit} безкоштовних пакетів по 8 сьогодні)",
        "insufficient_balance_8": "⚠️ Ви вже використали 3 безкоштовні генерації по 8 зображень сьогодні. Кожна наступна генерація з 8 зображень коштує 1 Star. Недостатній баланс.",
        "stars_deducted": "💳 Списано {price} Star(s). Генерація зображення(й) ({count})... ⏳",
        "image_ready": "✅ Зображення(я) готові! 📸",
        "btn_generate_again": "🔄 Створити знову",
        "account_title": "👤 Мій акаунт",
        "account_balance": "💳 Баланс: {balance} Stars",
        "account_referrals": "👥 Запрошені користувачі: {count}",
        "account_referral_link": "🔗 Ваше реферальне посилання:\n{link}",
        "account_withdraw": "📤 Вивести",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Функція виведення ще не готова — Незабаром! ⏳",
        "api_soon": "🔑 Доступ до API: Незабаром!",
        "info_title": "📊 Статистика",
        "info_uptime": "⏱ Час роботи: {uptime}",
        "info_ping": "🌐 Пінг: {ping} мс",
        "info_users": "👥 Користувачі: {count}",
        "info_images": "🖼 Всього згенеровано зображень: {count}",
        "info_donations": "💰 Всього пожертв: {amount}",
        "btn_contact_admin": "📩 Зв'язатися з адміном",
        "sub_check_prompt": "⛔ Ви повинні бути підписані на наш канал, щоб використовувати бота!",
        "sub_check_link_text": "🔗 Підписатися на канал",
        "sub_check_button_text": "✅ Перевірити підписку",
        "sub_check_success": "✅ Дякуємо! Ви підписані. Тепер ви можете використовувати бота.",
        "sub_check_fail": "⛔ Ви ще не підписані. Будь ласка, підпишіться і перевірте знову.",
        "invalid_button": "❌ Недійсна кнопка.",
        "error_try_again": "⚠️ Сталася помилка. Будь ласка, спробуйте ще раз.",
        "image_wait_timeout": "⚠️ Готування зображення займає багато часу. Будь ласка, спробуйте пізніше.",
        "image_id_missing": "❌ Не вдалося отримати ID зображення (відповідь API).",
        "api_unknown_response": "❌ Невідома відповідь від API. Будь ласка, зв'яжіться з адміністратором.",
        "enter_donate_amount": "💰 Будь ласка, введіть суму, яку хочете пожертвувати (1–100000):",
        "invalid_donate_amount": "❌ Будь ласка, введіть ціле число від 1 до 100000.",
        "donate_invoice_title": "💖 Пожертвування боту",
        "donate_invoice_description": "Надішліть довільну суму для підтримки бота.",
        "donate_thanks": "✅ Дякуємо, {first_name}! Ви надіслали {amount_stars} Stars.",
        "account_withdraw_soon": "📤 Вивести: Незабаром",
        "account_api_soon": "🔑 API: Незабаром",
        "referral_reward": "Ви отримали {reward} Stars за успішне запрошення!",
        "prompt_missing_group": "❌ У групі, будь ласка, надайте запит після /get. Приклад: /get футуристичне місто",
        "prompt_missing_private": "✍️ Будь ласка, надішліть текстовий запит для зображення (або просто надішліть текст).",
        "prompt_received_private": "🖌 Ваш запит:\n{prompt}\n\n🔢 Скільки зображень згенерувати?",
        "prompt_received_group": "🖌 Ваш запит:\n{prompt}\n\n🔢 Скільки зображень згенерувати?",
    },
    "vi": {
        "choose_language": "🌐 Vui lòng chọn ngôn ngữ của bạn:",
        "language_set": "✅ Ngôn ngữ được đặt thành {lang_code}.",
        "main_panel_text": "👋 Bảng điều khiển chính — quản lý hình ảnh, số dư và cài đặt ở đây.",
        "btn_generate": "🎨 Tạo hình ảnh",
        "btn_donate": "💖 Quyên góp",
        "btn_account": "👤 Tài khoản của tôi",
        "btn_change_lang": "🌐 Thay đổi ngôn ngữ",
        "btn_info": "ℹ️ Thông tin / Thống kê",
        "btn_back": "⬅️ Quay lại",
        "enter_prompt": "✍️ Vui lòng gửi lời nhắc văn bản cho hình ảnh (trong cuộc trò chuyện riêng).",
        "prompt_received": "🖌 Lời nhắc của bạn:\n{prompt}\n\n🔢 Tạo bao nhiêu hình ảnh?",
        "btn_1": "1️⃣",
        "btn_2": "2️⃣",
        "btn_4": "4️⃣",
        "btn_8": "8️⃣",
        "generating": "🔄 Đang tạo hình ảnh ({count})... ⏳",
        "generating_8_limited": "🔄 Đang tạo hình ảnh ({count})... ⏳ (Đã sử dụng {used}/{limit} lô 8 miễn phí hôm nay)",
        "insufficient_balance_8": "⚠️ Bạn đã sử dụng 3 lần tạo 8 hình ảnh miễn phí hôm nay. Mỗi lần tạo tiếp theo tốn 1 Sao. Số dư không đủ.",
        "stars_deducted": "💳 Đã trừ {price} Sao. Đang tạo hình ảnh ({count})... ⏳",
        "image_ready": "✅ Hình ảnh đã sẵn sàng! 📸",
        "btn_generate_again": "🔄 Tạo lại",
        "account_title": "👤 Tài khoản của tôi",
        "account_balance": "💳 Số dư: {balance} Sao",
        "account_referrals": "👥 Người dùng được giới thiệu: {count}",
        "account_referral_link": "🔗 Liên kết giới thiệu của bạn:\n{link}",
        "account_withdraw": "📤 Rút tiền",
        "account_api": "🔑 API",
        "withdraw_soon": "📤 Chức năng rút tiền chưa sẵn sàng — Sắp ra mắt! ⏳",
        "api_soon": "🔑 Truy cập API: Sắp ra mắt!",
        "info_title": "📊 Thống kê",
        "info_uptime": "⏱ Thời gian hoạt động: {uptime}",
        "info_ping": "🌐 Ping: {ping} ms",
        "info_users": "👥 Người dùng: {count}",
        "info_images": "🖼 Tổng số hình ảnh đã tạo: {count}",
        "info_donations": "💰 Tổng số quyên góp: {amount}",
        "btn_contact_admin": "📩 Liên hệ Quản trị viên",
        "sub_check_prompt": "⛔ Bạn phải đăng ký kênh của chúng tôi để sử dụng bot!",
        "sub_check_link_text": "🔗 Đăng ký Kênh",
        "sub_check_button_text": "✅ Kiểm tra Đăng ký",
        "sub_check_success": "✅ Cảm ơn! Bạn đã đăng ký. Bây giờ bạn có thể sử dụng bot.",
        "sub_check_fail": "⛔ Bạn vẫn chưa đăng ký. Vui lòng đăng ký và kiểm tra lại.",
        "invalid_button": "❌ Nút không hợp lệ.",
        "error_try_again": "⚠️ Đã xảy ra lỗi. Vui lòng thử lại.",
        "image_wait_timeout": "⚠️ Mất một lúc để chuẩn bị hình ảnh. Vui lòng thử lại sau.",
        "image_id_missing": "❌ Không thể lấy ID hình ảnh (phản hồi API).",
        "api_unknown_response": "❌ Phản hồi không xác định từ API. Vui lòng liên hệ quản trị viên.",
        "enter_donate_amount": "💰 Vui lòng nhập số tiền bạn muốn quyên góp (1–100000):",
        "invalid_donate_amount": "❌ Vui lòng nhập số nguyên từ 1 đến 100000.",
        "donate_invoice_title": "💖 Quyên góp cho Bot",
        "donate_invoice_description": "Gửi số tiền tùy chọn để hỗ trợ bot.",
        "donate_thanks": "✅ Cảm ơn, {first_name}! Bạn đã gửi {amount_stars} Sao.",
        "account_withdraw_soon": "📤 Rút tiền: Sắp ra mắt",
        "account_api_soon": "🔑 API: Sắp ra mắt",
        "referral_reward": "Bạn đã nhận được {reward} Sao cho một lần giới thiệu thành công!",
        "prompt_missing_group": "❌ Trong nhóm, vui lòng cung cấp lời nhắc sau /get. Ví dụ: /get thành phố tương lai",
        "prompt_missing_private": "✍️ Vui lòng gửi lời nhắc văn bản cho hình ảnh (hoặc chỉ gửi văn bản).",
        "prompt_received_private": "🖌 Lời nhắc của bạn:\n{prompt}\n\n🔢 Tạo bao nhiêu hình ảnh?",
        "prompt_received_group": "🖌 Lời nhắc của bạn:\n{prompt}\n\n🔢 Tạo bao nhiêu hình ảnh?",
    },
}

def t(lang_code: str, key: str, **kwargs) -> str:
    """Tarjima qilish funksiyasi."""
    lang_dict = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])
    template = lang_dict.get(key, key) # Agar kalit mavjud bo'lmasa, o'zini qaytaradi
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            logger.warning(f"Translation key '{key}' format error with args {kwargs}")
    return template

# ---------------- MAINTENANCE MODE ----------------
MAINTENANCE_MODE = False # Global flag

# ---------------- helpers ----------------
def escape_html(text: str) -> str:
    """HTML belgilarni escape qilish."""
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
        # Check and set maintenance mode flag from DB if needed, or default to False
        # For simplicity, we'll use the global variable for now.

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
        return True # Agar kanal sozlanmagan bo'lsa, tekshirmasdan o'tkazib yuboramiz
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
    # Check if user is banned
    user_rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    if user_rec and user_rec.get("is_banned"):
        await update.message.reply_text("🚫 Siz botdan foydalanishdan chetlatilgansiz.")
        return False
        
    ok = await check_subscription(user_id, context)
    if not ok:
        kb = [
            [InlineKeyboardButton(t(get_user_language(context, user_id), "sub_check_link_text"), url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(t(get_user_language(context, user_id), "sub_check_button_text"), callback_data="check_sub")]
        ]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(t(get_user_language(context, user_id), "sub_check_prompt"), reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(t(get_user_language(context, user_id), "sub_check_prompt"), reply_markup=InlineKeyboardMarkup(kb))
        return False
    return True

async def check_sub_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    # Check if user is banned (redundant but safe)
    user_rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    if user_rec and user_rec.get("is_banned"):
        await q.edit_message_text("🚫 Siz botdan foydalanishdan chetlatilgansiz.")
        return
        
    if await check_subscription(user_id, context):
        lang_code = get_user_language(context, user_id)
        text, kb = await send_main_panel(q.message.chat, lang_code, context.application.bot_data)
        await q.edit_message_text(text, reply_markup=kb)
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
            # Yangi foydalanuvchi, default til 'uz' bo'ladi, lekin keyin foydalanuvchi tanlaydi
            await conn.execute(
                "INSERT INTO users(id, username, first_seen, last_seen, lang) VALUES($1,$2,$3,$4,$5)",
                tg_user.id, tg_user.username if tg_user.username else None, now, now, None # lang hozircha NULL
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
    """Foydalanuvchini ban qilish."""
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE users SET is_banned = TRUE WHERE id = $1", user_id)
        return result != "UPDATE 0"

async def unban_user(pool, user_id: int) -> bool:
    """Foydalanuvchini bandan chiqarish."""
    async with pool.acquire() as conn:
        result = await conn.execute("UPDATE users SET is_banned = FALSE WHERE id = $1", user_id)
        return result != "UPDATE 0"

async def is_user_banned(pool, user_id: int) -> bool:
    """Foydalanuvchi ban qilinganligini tekshirish."""
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
            # Notify inviter (optional, requires storing bot instance or using a queue/async notify)
            # For now, we'll assume the inviter gets the reward in their balance on next check.
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
    """Foydalanuvchining tilini aniqlash."""
    # 1. context.user_data dan urinib ko'rish
    if context.user_data and USER_DATA_LANG in context.user_data:
        return context.user_data[USER_DATA_LANG]
    
    # 2. DB dan urinib ko'rish
    # Bu yerda biz hech qachon await qilmasdan ishlamaymiz, shuning uchun bu faqat oxirgi chora.
    # Aslida, bu funksiya faqat context.user_data dan o'qiydi.
    # Tilni o'rnatishda context.user_data va DB ni yangilash kerak.
    
    # 3. Default
    return "en" # yoki botning standart tili

# ---------------- Handlers ----------------
async def send_main_panel(chat, lang_code: str, bot_data: dict):
    kb = [
        [InlineKeyboardButton(t(lang_code, "btn_generate"), callback_data="start_gen")],
        [InlineKeyboardButton(t(lang_code, "btn_donate"), callback_data="donate_custom"), InlineKeyboardButton(t(lang_code, "btn_account"), callback_data="my_account")],
        [InlineKeyboardButton(t(lang_code, "btn_change_lang"), callback_data="change_lang"), InlineKeyboardButton(t(lang_code, "btn_info"), callback_data="show_info")],
    ]
    # Agar foydalanuvchi admin bo'lsa, admin panel tugmasini qo'shamiz
    # Bu yerda ADMIN_ID global o'zgaruvchi sifatida aniqlangan
    # if chat.id == ADMIN_ID: # Bu noto'g'ri, chat.id foydalanuvchi ID'si emas
    # To'g'riroq: foydalanuvchi ID'sini olish
    # if hasattr(chat, 'id'): user_id = chat.id
    # else: user_id = None
    # if user_id and user_id == ADMIN_ID:
    #     kb.append([InlineKeyboardButton(t(lang_code, "btn_admin"), callback_data="admin_panel")])
    
    text = t(lang_code, "main_panel_text")
    return text, InlineKeyboardMarkup(kb)

# START
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "maintenance_message"))
        return

    if not await force_sub_if_private(update, context):
        return

    created = await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    user_rec = await get_user_record(context.application.bot_data["db_pool"], update.effective_user.id)
    
    # Referralni tekshirish
    args = context.args or []
    if created and args:
        for a in args:
            if a.startswith("ref_"):
                try:
                    inviter_id = int(a.split("_", 1)[1])
                    if inviter_id != update.effective_user.id: # O'zini o'zini taklif qilishni oldini olish
                        success = await handle_referral(context.application.bot_data["db_pool"], inviter_id, update.effective_user.id)
                        if success:
                            # Taklif qiluvchiga xabar berish (ixtiyoriy)
                            # Bu murakkabroq, chunki biz taklif qiluvchi online ekanligini bilmaymiz
                            # Hoynahoy, uni balansi keyingi kirishda ko'rinadi
                            pass
                except Exception as e:
                    logger.warning(f"[REFERRAL PARSE ERROR] {e}")

    # Agar foydalanuvchi tilini tanlamagan bo'lsa
    if not user_rec or not user_rec.get("lang"):
        user_lang = "en" # Tilni tanlashda foydalanish uchun vaqtincha
        context.user_data[USER_DATA_LANG] = user_lang # context.user_data ni ham yangilaymiz
        await update.message.reply_text(
            t(user_lang, "choose_language"),
            reply_markup=build_lang_keyboard(user_lang)
        )
        return

    # Aks holda, bosh panelni ko'rsatamiz
    lang_code = user_rec["lang"]
    context.user_data[USER_DATA_LANG] = lang_code # context.user_data ni yangilash
    text, kb = await send_main_panel(update.effective_chat, lang_code, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def change_lang_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    await q.edit_message_text(t(user_lang, "choose_language"), reply_markup=build_lang_keyboard(user_lang))

async def set_lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query
        await q.answer()
        user_lang = get_user_language(context, q.from_user.id)
        await q.edit_message_text(t(user_lang, "maintenance_message"))
        return
        
    q = update.callback_query
    await q.answer()
    data = q.data
    code = data.split("_", 2)[2]
    
    # DB ga tilni saqlash
    await set_user_lang(context.application.bot_data["db_pool"], q.from_user.id, code)
    # context.user_data ni yangilash
    context.user_data[USER_DATA_LANG] = code
    
    # Tasdiqlash xabarini yuborish va bosh menyuga qaytish
    text, kb = await send_main_panel(q.message.chat, code, context.application.bot_data)
    confirmation_text = t(code, "main_panel_text") # Asosiy matnni o'zini ishlatamiz
    full_text = f"✅ Til {code} ga o'zgartirildi.\n\n{confirmation_text}"
    try:
        await q.edit_message_text(full_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except BadRequest:
        try:
            await q.message.reply_text(full_text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            pass

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query if update.callback_query else None
        if q:
            await q.answer()
        user_lang = get_user_language(context, update.effective_user.id if update.effective_user else (q.from_user.id if q else 0))
        msg = q.message if q else update.message
        if msg:
            await msg.reply_text(t(user_lang, "maintenance_message"))
        return

    if update.callback_query:
        await update.callback_query.answer()
    user_lang = get_user_language(context, update.effective_user.id)
    await update.effective_message.reply_text(t(user_lang, "enter_prompt"))

# /get command
async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "maintenance_message"))
        return

    if not await force_sub_if_private(update, context):
        return
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup"):
        if not context.args:
            user_lang = get_user_language(context, update.effective_user.id)
            await update.message.reply_text(t(user_lang, "prompt_missing_group"))
            return
        prompt = " ".join(context.args)
    else:
        if not context.args:
            user_lang = get_user_language(context, update.effective_user.id)
            await update.message.reply_text(t(user_lang, "prompt_missing_private"))
            return
        prompt = " ".join(context.args)

    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    context.user_data[USER_DATA_PROMPT] = prompt
    context.user_data[USER_DATA_TRANSLATED] = prompt
    user_lang = get_user_language(context, update.effective_user.id)
    message_text = t(user_lang, "prompt_received", prompt=escape_html(prompt))
    kb = [[
        InlineKeyboardButton(t(user_lang, "btn_1"), callback_data="count_1"),
        InlineKeyboardButton(t(user_lang, "btn_2"), callback_data="count_2"),
        InlineKeyboardButton(t(user_lang, "btn_4"), callback_data="count_4"),
        InlineKeyboardButton(t(user_lang, "btn_8"), callback_data="count_8"),
    ]]
    await update.message.reply_text(message_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

# Private plain text -> prompt
async def private_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "maintenance_message"))
        return

    if update.effective_chat.type != "private":
        return
    if not await force_sub_if_private(update, context):
        return
    await add_user_db(context.application.bot_data["db_pool"], update.effective_user)
    prompt = update.message.text
    context.user_data[USER_DATA_PROMPT] = prompt
    context.user_data[USER_DATA_TRANSLATED] = prompt
    user_lang = get_user_language(context, update.effective_user.id)
    message_text = t(user_lang, "prompt_received", prompt=escape_html(prompt))
    kb = [[
        InlineKeyboardButton(t(user_lang, "btn_1"), callback_data="count_1"),
        InlineKeyboardButton(t(user_lang, "btn_2"), callback_data="count_2"),
        InlineKeyboardButton(t(user_lang, "btn_4"), callback_data="count_4"),
        InlineKeyboardButton(t(user_lang, "btn_8"), callback_data="count_8"),
    ]]
    await update.message.reply_text(message_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

# ---------------- Progress Simulation ----------------
async def simulate_progress(context: ContextTypes.DEFAULT_TYPE):
    """Progressni yangilash uchun job."""
    job = context.job
    if not job or not job.data:
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

    progress = min(progress + random.randint(5, 15), 95) # 5-15% qo'shiladi, maks 95%
    data['progress'] = progress
    
    try:
        if count == 8 and used is not None and limit is not None:
            if price_deducted:
                text = t(lang_code, "stars_deducted_progress", price=price_deducted, count=count, progress=progress)
            else:
                text = t(lang_code, "generating_8_limited_progress", count=count, progress=progress, used=used, limit=limit)
        else:
            if price_deducted:
                text = t(lang_code, "stars_deducted_progress", price=price_deducted, count=count, progress=progress)
            else:
                text = t(lang_code, "generating_progress", count=count, progress=progress)
                
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Progress update error: {e}")
    except Exception as e:
        logger.warning(f"Unexpected progress update error: {e}")

# GENERATE
async def generate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query
        await q.answer()
        user_lang = get_user_language(context, q.from_user.id)
        await q.edit_message_text(t(user_lang, "maintenance_message"))
        return

    q = update.callback_query
    await q.answer()
    try:
        count = int(q.data.split("_")[1])
    except Exception:
        user_lang = get_user_language(context, q.from_user.id)
        try:
            await q.edit_message_text(t(user_lang, "invalid_button"))
        except Exception:
            pass
        return

    user = q.from_user
    prompt = context.user_data.get(USER_DATA_PROMPT, "")
    translated = context.user_data.get(USER_DATA_TRANSLATED, prompt)

    # Check if user is banned
    user_rec = await get_user_record(context.application.bot_data["db_pool"], user.id)
    if user_rec and user_rec.get("is_banned"):
        user_lang = get_user_language(context, user.id)
        try:
            await q.edit_message_text("🚫 Siz botdan foydalanishdan chetlatilgansiz.")
        except Exception:
            pass
        return

    # 8-image limits
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
                user_lang = get_user_language(context, user.id)
                try:
                    await q.edit_message_text(t(user_lang, "insufficient_balance_8"), reply_markup=InlineKeyboardMarkup(kb))
                except Exception:
                    pass
                return
            else:
                await adjust_user_balance(pool, user.id, -PRICE_PER_8)
                # Start progress simulation with price deducted info
                user_lang = get_user_language(context, user.id)
                progress_text = t(user_lang, "stars_deducted", price=PRICE_PER_8, count=count)
                progress_msg = await q.edit_message_text(progress_text)
                
                # Schedule progress updates
                job_queue: JobQueue = context.job_queue
                if job_queue:
                    job_data = {
                        'chat_id': progress_msg.chat_id,
                        'message_id': progress_msg.message_id,
                        'count': count,
                        'price_deducted': str(PRICE_PER_8),
                        'lang_code': user_lang,
                        'progress': 0
                    }
                    job = job_queue.run_repeating(simulate_progress, interval=2, first=2, data=job_data)
                    # Store job reference to cancel later
                    context.user_data[USER_DATA_PROGRESS_JOB] = job
                    context.user_data[USER_DATA_LAST_PROGRESS_MSG_ID] = progress_msg.message_id
        else:
            # Free - allowed, start progress simulation
            user_lang = get_user_language(context, user.id)
            progress_text = t(user_lang, "generating_8_limited", count=count, used=used, limit=FREE_8_PER_DAY)
            progress_msg = await q.edit_message_text(progress_text)
            
            job_queue: JobQueue = context.job_queue
            if job_queue:
                job_data = {
                    'chat_id': progress_msg.chat_id,
                    'message_id': progress_msg.message_id,
                    'count': count,
                    'used': used,
                    'limit': FREE_8_PER_DAY,
                    'lang_code': user_lang,
                    'progress': 0
                }
                job = job_queue.run_repeating(simulate_progress, interval=2, first=2, data=job_data)
                context.user_data[USER_DATA_PROGRESS_JOB] = job
                context.user_data[USER_DATA_LAST_PROGRESS_MSG_ID] = progress_msg.message_id
    else:
        # For 1, 2, 4 images, start progress simulation
        user_lang = get_user_language(context, user.id)
        progress_text = t(user_lang, "generating", count=count)
        progress_msg = await q.edit_message_text(progress_text)
        
        job_queue: JobQueue = context.job_queue
        if job_queue:
            job_data = {
                'chat_id': progress_msg.chat_id,
                'message_id': progress_msg.message_id,
                'count': count,
                'lang_code': user_lang,
                'progress': 0
            }
            job = job_queue.run_repeating(simulate_progress, interval=2, first=2, data=job_data)
            context.user_data[USER_DATA_PROGRESS_JOB] = job
            context.user_data[USER_DATA_LAST_PROGRESS_MSG_ID] = progress_msg.message_id

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
                    user_lang = get_user_language(context, user.id)
                    await q.message.reply_text(t(user_lang, "api_unknown_response"))
                    # Cancel progress job if it exists
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
                user_lang = get_user_language(context, user.id)
                await q.message.reply_text(t(user_lang, "image_id_missing"))
                # Cancel progress job if it exists
                if USER_DATA_PROGRESS_JOB in context.user_data:
                    job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                    job.schedule_removal()
                return

            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
            logger.info(f"[GENERATE] urls: {urls}")

            # Wait loop for first image
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
                user_lang = get_user_language(context, user.id)
                try:
                    await q.edit_message_text(t(user_lang, "image_wait_timeout"))
                except Exception:
                    pass
                # Cancel progress job if it exists
                if USER_DATA_PROGRESS_JOB in context.user_data:
                    job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                    job.schedule_removal()
                return

            # Cancel progress job before sending final message
            if USER_DATA_PROGRESS_JOB in context.user_data:
                job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
                job.schedule_removal()
            
            # Send media group or single photos
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

            # Send final "ready" message with "Generate Again" button
            user_lang = get_user_language(context, user.id)
            kb = [[InlineKeyboardButton(t(user_lang, "btn_generate_again"), callback_data="start_gen")]]
            # Edit the last progress message if we have its ID
            last_progress_msg_id = context.user_data.pop(USER_DATA_LAST_PROGRESS_MSG_ID, None)
            if last_progress_msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=q.message.chat_id,
                        message_id=last_progress_msg_id,
                        text=t(user_lang, "image_ready"),
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                except Exception as e:
                    logger.warning(f"Failed to edit progress message: {e}")
                    # If editing fails, send a new message
                    await q.message.reply_text(t(user_lang, "image_ready"), reply_markup=InlineKeyboardMarkup(kb))
            else:
                await q.message.reply_text(t(user_lang, "image_ready"), reply_markup=InlineKeyboardMarkup(kb))

    except Exception as e:
        logger.exception(f"[GENERATE ERROR] {e}")
        user_lang = get_user_language(context, user.id)
        try:
            await q.edit_message_text(t(user_lang, "error_try_again"))
        except Exception:
            pass
        # Cancel progress job if it exists
        if USER_DATA_PROGRESS_JOB in context.user_data:
            job = context.user_data.pop(USER_DATA_PROGRESS_JOB)
            job.schedule_removal()

# ---------------- Donate (Stars) flow ----------------
async def donate_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query if update.callback_query else None
        if q:
            await q.answer()
        user_lang = get_user_language(context, update.effective_user.id if update.effective_user else (q.from_user.id if q else 0))
        msg = q.message if q else update.message
        if msg:
            await msg.reply_text(t(user_lang, "maintenance_message"))
        return

    if update.callback_query:
        await update.callback_query.answer()
        user_lang = get_user_language(context, update.callback_query.from_user.id)
        await update.callback_query.message.reply_text(t(user_lang, "enter_donate_amount"))
    else:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "enter_donate_amount"))
    return DONATE_AMOUNT

async def donate_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "maintenance_message"))
        return ConversationHandler.END

    txt = update.message.text.strip()
    try:
        amount = int(txt)
        if amount < 1 or amount > 100000:
            raise ValueError
    except ValueError:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "invalid_donate_amount"))
        # Foydalanuvchi noto'g'ri qiymat kiritgani uchun bosh menyuga qaytish
        # Bu yerda ConversationHandler.END qaytariladi, lekin foydalanuvchi xabar yozganidan keyin
        # bosh menyuga qaytish uchun yangi handler kerak.
        # Oddiy holatda, foydalanuvchidan yana miqdor so'raladi.
        # Agar foydalanuvchi /start yoki boshqa buyruq bersa, ConversationHandler to'xtaydi.
        # Shunchaki ConversationHandler.END qaytarsak, foydalanuvchi "invalid" xabarini oladi va yana kiritishni davom ettiradi.
        # Bosh menyuga qaytish uchun maxsus handler kerak bo'ladi yoki conversationni boshqacha boshqarish kerak.
        # Hozirgi kodda, foydalanuvchi to'g'ri qiymat kiritmaguncha conversation davom etadi.
        # Agar foydalanuvchi conversationdan chiqishni hohlasa, /start buyrug'i ishlatishi mumkin.
        # Bu oddiy Telegram bot conversation logikasidir.
        # Agar foydalanuvchi bosh menyuga qaytishni xohlasa, /start ni bosishi kerak.
        # Shuning uchun, bu yerda hech narsa qaytarmasak, conversation davom etadi.
        # return ConversationHandler.END # Bu foydalanuvchini conversationdan chiqaradi, lekin bu xohlanmaydi.
        return DONATE_AMOUNT # Yana miqdor so'raladi

    payload = f"donate_{update.effective_user.id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    prices = [LabeledPrice(f"{amount} Stars", amount * 100)] # XTR uchun centlarda
    user_lang = get_user_language(context, update.effective_user.id)
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=t(user_lang, "donate_invoice_title"),
        description=t(user_lang, "donate_invoice_description"),
        payload=payload,
        provider_token="", # XTR uchun bo'sh
        currency="XTR",
        prices=prices,
        is_flexible=False
    )
    return ConversationHandler.END

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    amount_stars = payment.total_amount // 100 # XTR uchun to'g'ri miqdor
    user = update.effective_user
    user_lang = get_user_language(context, user.id)
    thanks_text = t(user_lang, "donate_thanks", first_name=user.first_name, amount_stars=amount_stars)
    await update.message.reply_text(thanks_text)
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO donations(user_id, username, stars, payload) VALUES($1,$2,$3,$4)",
            user.id, user.username if user.username else None, amount_stars, payment.invoice_payload
        )
    await adjust_user_balance(pool, user.id, Decimal(amount_stars))
    
    # To'lovdan keyin foydalanuvchini bosh menyuga yo'naltirish
    text, kb = await send_main_panel(update.effective_chat, user_lang, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

# ---------------- Hisobim / Account panel ----------------
async def my_account_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query if update.callback_query else None
        if q:
            await q.answer()
        user_lang = get_user_language(context, update.effective_user.id if update.effective_user else (q.from_user.id if q else 0))
        msg = q.message if q else update.message
        if msg:
            await msg.reply_text(t(user_lang, "maintenance_message"))
        return

    if update.callback_query:
        q = update.callback_query
        await q.answer()
        user_id = q.from_user.id
        chat = q.message.chat
    else:
        user_id = update.effective_user.id
        chat = update.effective_chat

    rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
    if not rec:
        user_lang = get_user_language(context, user_id)
        await chat.send_message(t(user_lang, "error_try_again"))
        return
        
    balance = Decimal(rec.get("balance") or 0)
    async with context.application.bot_data["db_pool"].acquire() as conn:
        refs = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id=$1", user_id)
    refs = int(refs or 0)
    
    # To'g'ri referral link
    bot_username = BOT_USERNAME or "DigenAi_Bot" # Fallback
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    user_lang = rec.get("lang") or "en"
    account_title = t(user_lang, "account_title")
    account_balance = t(user_lang, "account_balance", balance=balance)
    account_referrals = t(user_lang, "account_referrals", count=refs)
    account_referral_link = t(user_lang, "account_referral_link", link=referral_link)
    account_withdraw = t(user_lang, "account_withdraw") # tugma uchun
    account_api = t(user_lang, "account_api") # tugma uchun
    withdraw_soon_text = t(user_lang, "withdraw_soon")
    api_soon_text = t(user_lang, "api_soon")
    
    text = (
        f"<b>{account_title}</b>\n\n"
        f"{account_balance}\n"
        f"{account_referrals}\n\n"
        f"{account_referral_link}\n\n"
        f"<b>{account_withdraw}:</b> {withdraw_soon_text}\n"
        f"<b>{account_api}:</b> {api_soon_text}"
    )
    kb = [
        [InlineKeyboardButton(t(user_lang, "btn_donate"), callback_data="donate_custom"), InlineKeyboardButton(account_withdraw, callback_data="withdraw")],
        [InlineKeyboardButton(t(user_lang, "btn_change_lang"), callback_data="change_lang"), InlineKeyboardButton(t(user_lang, "btn_back"), callback_data="back_main")]
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
    if MAINTENANCE_MODE:
        q = update.callback_query if update.callback_query else None
        if q:
            await q.answer()
        user_lang = get_user_language(context, update.effective_user.id if update.effective_user else (q.from_user.id if q else 0))
        msg = q.message if q else update.message
        if msg:
            await msg.reply_text(t(user_lang, "maintenance_message"))
        return

    if update.callback_query:
        q = update.callback_query
        await q.answer()
        chat = q.message.chat
        user_lang = get_user_language(context, q.from_user.id)
    else:
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
    """Real-time statistikani ko'rsatish va yangilash."""
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    
    # Initial stats message
    stats_msg = await q.edit_message_text(t(user_lang, "stats_title") + "\n🔄 Yangilanmoqda...")
    
    # Schedule a job to update stats every 5 seconds
    job_queue: JobQueue = context.job_queue
    if job_queue:
        job_data = {
            'chat_id': stats_msg.chat_id,
            'message_id': stats_msg.message_id,
            'user_lang': user_lang,
            'db_pool': context.application.bot_data["db_pool"]
        }
        job = job_queue.run_repeating(update_stats_message, interval=5, first=0, data=job_data)
        # Store job reference in user_data or chat_data to cancel later
        # For simplicity, we'll use user_data, but this means only one stats view per user
        context.chat_data['stats_job'] = job

async def update_stats_message(context: ContextTypes.DEFAULT_TYPE):
    """Stats xabarini yangilash uchun job."""
    job = context.job
    if not job or not job.data:
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
            pass # Ignore if message hasn't changed
        else:
            logger.warning(f"Stats update error: {e}")
            # If there's an error, cancel the job
            job.schedule_removal()
    except Exception as e:
        logger.error(f"Unexpected stats update error: {e}")
        job.schedule_removal()

async def stop_stats_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats yangilanishini to'xtatish."""
    if 'stats_job' in context.chat_data:
        job = context.chat_data['stats_job']
        job.schedule_removal()
        del context.chat_data['stats_job']

# ---------------- Simple navigation handlers ----------------
async def back_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query
        await q.answer()
        user_lang = get_user_language(context, q.from_user.id)
        await q.edit_message_text(t(user_lang, "maintenance_message"))
        return

    q = update.callback_query
    await q.answer()
    # Stats yangilanishini to'xtatish
    await stop_stats_updates(update, context)
    
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
    if MAINTENANCE_MODE:
        q = update.callback_query
        await q.answer()
        user_lang = get_user_language(context, q.from_user.id)
        await q.edit_message_text(t(user_lang, "maintenance_message"))
        return

    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    try:
        await q.edit_message_text(t(user_lang, "withdraw_soon"))
    except Exception:
        pass

# ---------------- Admin Panel ----------------
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panelni ko'rsatish."""
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        q = update.callback_query if update.callback_query else None
        if q:
            await q.answer()
        user_lang = get_user_language(context, update.effective_user.id if update.effective_user else (q.from_user.id if q else 0))
        msg = q.message if q else update.message
        if msg:
            await msg.reply_text(t(user_lang, "maintenance_message"))
        return

    user_id = update.effective_user.id if update.effective_user else (update.callback_query.from_user.id if update.callback_query else 0)
    if user_id != ADMIN_ID:
        # Agar foydalanuvchi admin bo'lmasa, bosh menyuga qaytarish
        user_rec = await get_user_record(context.application.bot_data["db_pool"], user_id)
        lang_code = user_rec["lang"] if user_rec and user_rec["lang"] else "en"
        context.user_data[USER_DATA_LANG] = lang_code
        text, kb = await send_main_panel(update.effective_chat if update.effective_message else update.callback_query.message.chat, lang_code, context.application.bot_data)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
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

    user_lang = get_user_language(context, user_id)
    admin_title = t(user_lang, "admin_panel_title")
    btn_broadcast = t(user_lang, "btn_admin_broadcast")
    btn_ban = t(user_lang, "btn_admin_ban")
    btn_unban = t(user_lang, "btn_admin_unban")
    btn_user_info = t(user_lang, "btn_admin_user_info")
    btn_maintenance = t(user_lang, "btn_admin_toggle_maintenance")
    btn_referrals = t(user_lang, "btn_admin_get_all_referrals")
    btn_back = t(user_lang, "btn_back")
    
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
    """Admin broadcast uchun conversationni boshlash."""
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    await q.message.reply_text(t(user_lang, "enter_broadcast_message"))
    return ADMIN_BROADCAST_MESSAGE

async def admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin broadcast xabarini qabul qilish va yuborish."""
    # Xabarni olish (text, photo, va h.k.)
    message: Message = update.message
    
    # Foydalanuvchilarga yuborish
    pool = context.application.bot_data["db_pool"]
    async with pool.acquire() as conn:
        user_ids = await conn.fetch("SELECT id FROM users WHERE is_banned = FALSE") # Faqat ban qilinmagan foydalanuvchilarga
    
    user_lang = get_user_language(context, update.effective_user.id)
    
    success_count = 0
    fail_count = 0
    for record in user_ids:
        user_id = record['id']
        try:
            # Xabarni qayta yuborish
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
            # Boshqa media turlarini qo'shishingiz mumkin
            else:
                # Noma'lum turdagi xabar
                pass
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {e}")
            fail_count += 1
            
    await message.reply_text(f"📢 Xabar yuborildi!\n✅ Muvaffaqiyatli: {success_count}\n❌ Muvaffaqiyatsiz: {fail_count}")
    
    # Adminni bosh menyuga qaytarish
    text, kb = await send_main_panel(update.effective_chat, user_lang, context.application.bot_data)
    await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin foydalanuvchini ban qilish uchun user ID so'rash."""
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    await q.message.reply_text(t(user_lang, "enter_user_id_to_ban"))
    return ADMIN_BAN_USER_ID

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchini ban qilish."""
    txt = update.message.text.strip()
    try:
        user_id = int(txt)
    except ValueError:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "invalid_user_id"))
        return ADMIN_BAN_USER_ID # Yana ID so'raladi

    pool = context.application.bot_data["db_pool"]
    user_rec = await get_user_record(pool, user_id)
    if not user_rec:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "user_not_found"))
        return ConversationHandler.END

    is_already_banned = user_rec.get("is_banned")
    if is_already_banned:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "user_already_banned", user_id=user_id))
    else:
        success = await ban_user(pool, user_id)
        user_lang = get_user_language(context, update.effective_user.id)
        if success:
            await update.message.reply_text(t(user_lang, "user_banned", user_id=user_id))
        else:
            await update.message.reply_text(t(user_lang, "error_try_again"))
    
    # Adminni bosh menyuga qaytarish
    user_lang = get_user_language(context, update.effective_user.id)
    text, kb = await send_main_panel(update.effective_chat, user_lang, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin foydalanuvchini bandan chiqarish uchun user ID so'rash."""
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    await q.message.reply_text(t(user_lang, "enter_user_id_to_unban"))
    return ADMIN_UNBAN_USER_ID

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchini bandan chiqarish."""
    txt = update.message.text.strip()
    try:
        user_id = int(txt)
    except ValueError:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "invalid_user_id"))
        return ADMIN_UNBAN_USER_ID # Yana ID so'raladi

    pool = context.application.bot_data["db_pool"]
    user_rec = await get_user_record(pool, user_id)
    if not user_rec:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "user_not_found"))
        return ConversationHandler.END

    is_banned = user_rec.get("is_banned")
    if not is_banned:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "user_not_banned", user_id=user_id))
    else:
        success = await unban_user(pool, user_id)
        user_lang = get_user_language(context, update.effective_user.id)
        if success:
            await update.message.reply_text(t(user_lang, "user_unbanned", user_id=user_id))
        else:
            await update.message.reply_text(t(user_lang, "error_try_again"))
    
    # Adminni bosh menyuga qaytarish
    user_lang = get_user_language(context, update.effective_user.id)
    text, kb = await send_main_panel(update.effective_chat, user_lang, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_user_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin foydalanuvchi haqida ma'lumot olish uchun user ID so'rash."""
    q = update.callback_query
    await q.answer()
    user_lang = get_user_language(context, q.from_user.id)
    await q.message.reply_text(t(user_lang, "enter_user_id_for_info"))
    # Bu yerda state kerak bo'lmasa, oddiy handler sifatida ishlatish mumkin
    # Yoki conversation state dan foydalanish mumkin. Hozir oddiy handler.
    return ConversationHandler.END

async def admin_user_info_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi haqida ma'lumot berish."""
    txt = update.message.text.strip()
    try:
        user_id = int(txt)
    except ValueError:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "invalid_user_id"))
        return

    pool = context.application.bot_data["db_pool"]
    user_rec = await get_user_record(pool, user_id)
    if not user_rec:
        user_lang = get_user_language(context, update.effective_user.id)
        await update.message.reply_text(t(user_lang, "user_not_found"))
        return

    # Referral sonini hisoblash
    async with pool.acquire() as conn:
        refs_count = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE inviter_id=$1", user_id)
    refs_count = int(refs_count or 0)
    
    user_lang_admin = get_user_language(context, update.effective_user.id) # Admin tili
    user_lang_user = user_rec.get("lang") or "en" # Foydalanuvchi tili
    
    info_title = t(user_lang_admin, "user_info_title")
    info_details = t(
        user_lang_admin, "user_info_details",
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
    
    # Adminni bosh menyuga qaytarish
    text, kb = await send_main_panel(update.effective_chat, user_lang_admin, context.application.bot_data)
    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)

async def admin_get_all_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchining barcha referallarini olish."""
    q = update.callback_query
    await q.answer()
    
    # Foydalanuvchi ID'sini olish (misol uchun, admin ID'si so'ralmasa, o'zini ID'si olinadi)
    # Bu yerda oddiy holat: admin o'z referallarini ko'radi deb hisoblaymiz.
    # Agar boshqa foydalanuvchining referallari kerak bo'lsa, alohida ID so'rash kerak.
    # Hozircha, admin o'zini referallarini ko'radi.
    user_id = q.from_user.id 
    pool = context.application.bot_data["db_pool"]
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT invited_id FROM referrals WHERE inviter_id=$1", user_id)
        
    if not rows:
        user_lang = get_user_language(context, user_id)
        await q.message.reply_text(t(user_lang, "no_referrals_found"))
        return
        
    user_lang = get_user_language(context, user_id)
    referrals_title = t(user_lang, "referrals_title", user_id=user_id)
    text = f"<b>{referrals_title}</b>\n\n"
    
    for i, row in enumerate(rows, 1):
        invited_id = row['invited_id']
        invited_rec = await get_user_record(pool, invited_id)
        username = invited_rec['username'] if invited_rec and invited_rec['username'] else "N/A"
        text += f"{i}. ID: {invited_id}, Username: @{username}\n"
        
    await q.message.reply_text(text, parse_mode=ParseMode.HTML)

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maintenance rejimini yoqish/o'chirish."""
    global MAINTENANCE_MODE
    q = update.callback_query
    await q.answer()
    
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    user_lang = get_user_language(context, q.from_user.id)
    if MAINTENANCE_MODE:
        await q.edit_message_text(t(user_lang, "maintenance_enabled"))
    else:
        await q.edit_message_text(t(user_lang, "maintenance_disabled"))

# ---------------- Error handler ----------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled exception:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            user_lang = get_user_language(context, update.effective_user.id if update.effective_user else 0)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=t(user_lang, "error_try_again"))
    except Exception:
        pass

# ---------------- Startup ----------------
async def on_startup(app: Application):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10) # Max size ni oshirdim
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

    # private plain text -> prompt handler (after donate_conv)
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
    
    # Admin User Info (simple handler, no conversation state needed for single message)
    app.add_handler(CallbackQueryHandler(admin_user_info_start, pattern=r"admin_user_info"))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & filters.User(user_id=ADMIN_ID), admin_user_info_by_id))
    
    # Admin Get Referrals
    app.add_handler(CallbackQueryHandler(admin_get_all_referrals, pattern=r"admin_referrals"))
    
    # Admin Toggle Maintenance
    app.add_handler(CallbackQueryHandler(admin_toggle_maintenance, pattern=r"admin_maintenance"))

    # errors
    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    logger.info("Application initialized. Starting polling...")
    app.run_polling(drop_pending_updates=True) # Yangi ishga tushganda eski xabarlarni tashlab ketish

if __name__ == "__main__":
    main()
