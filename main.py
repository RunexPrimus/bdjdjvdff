import logging
import aiohttp
import asyncio
import re
import os
import json
import itertools
import random
from deep_translator import GoogleTranslator
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# 🔹 LOG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 ENVIRONMENT
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))

DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
_key_cycle = itertools.cycle(DIGEN_KEYS)
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"

USERS_FILE = "users.json"
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump([], f)

# ----------------------- USERLAR -----------------------
def add_user(user_id):
    with open(USERS_FILE, "r+") as f:
        data = json.load(f)
        if user_id not in data:
            data.append(user_id)
            f.seek(0)
            json.dump(data, f)

def get_all_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

# ----------------------- HEADER -----------------------
def get_digen_headers():
    key = random.choice(DIGEN_KEYS)
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "digen-language": "uz-US",
        "digen-platform": "web",
        "digen-token": key["token"],
        "digen-sessionid": key["session"],
        "origin": "https://rm.digen.ai",
        "referer": "https://rm.digen.ai/",
    }

def escape_md(text: str) -> str:
    return re.sub(r'([_*\[\]()~>#+\-=|{}.!])', r'\\\1', text)

async def translate_prompt(prompt: str) -> str:
    logger.info(f"🔍 [TRANSLATE] Original prompt: {prompt}")

    try:
        result = await asyncio.to_thread(
            GoogleTranslator(source="uz", target="en").translate, prompt
        )
        logger.info(f"✅ [TRANSLATE] Success! Translated: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ [TRANSLATE ERROR] {type(e).__name__}: {e}")
        return prompt


    except Exception as e:
        # Xato bo‘lsa hamma ma’lumotlarni chiqaramiz
        logger.error(f"❌ [TRANSLATE ERROR] Xato turi: {type(e).__name__} | Xabar: {e}")
        logger.warning("⚠️ Tarjima ishlamadi, original prompt ishlatilmoqda.")
        return prompt


# ----------------------- HANDLERS -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)

    kb = [[InlineKeyboardButton("🎨 Rasm yaratishni boshlash", callback_data="start_gen")]]
    await update.message.reply_text(
        "👋 Salom!\n\n"
        "Men siz uchun sun’iy intellekt yordamida rasmlar yaratib beraman.\n\n"
        "✍️ Xohlgan narsani yozing — men uni inglizchaga tarjima qilaman va chiroyli rasm yarataman.\n\n"
        "_Misol:_ Trump burger yemoqda → Trump eating a burger",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "✍️ Endi tasvir yaratish uchun matn yuboring.\n\n_Misol:_ Futuristik cyberpunk shahar neon chiroqlar bilan",
        parse_mode="Markdown"
    )

async def ask_image_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    translated = await translate_prompt(prompt)

    context.user_data["prompt"] = prompt
    context.user_data["translated"] = translated

    kb = [[
        InlineKeyboardButton("1️⃣", callback_data="count_1"),
        InlineKeyboardButton("2️⃣", callback_data="count_2"),
        InlineKeyboardButton("4️⃣", callback_data="count_4"),
        InlineKeyboardButton("8️⃣", callback_data="count_8"),
    ]]

    await update.message.reply_text(
        f"🖌 *Sizning matningiz:*\n{escape_md(prompt)}\n\n"
        f"🌎 *Tarjima:* {escape_md(translated)}\n\n"
        "🔢 Nechta rasm yaratilsin?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = int(query.data.split("_")[1])
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", "")

    waiting_msg = await query.edit_message_text(
        f"🔄 Rasm yaratilmoqda ({count} ta)...\n0% ⏳", parse_mode="Markdown"
    )

    try:
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

        async with aiohttp.ClientSession() as session:
            async with session.post(DIGEN_URL, headers=get_digen_headers(), json=payload) as r:
                if r.status != 200:
                    await waiting_msg.edit_text(f"❌ API xatosi: {r.status}")
                    return
                data = await r.json()

        image_id = data.get("data", {}).get("id")
        if not image_id:
            await waiting_msg.edit_text("❌ Rasm ID olinmadi.")
            return

        # Progress bar + har 1 sekundda tekshirish
        progress = 0
        while True:
            progress = min(progress + 15, 95)
            bar = "▰" * (progress // 10) + "▱" * (10 - progress // 10)
            await waiting_msg.edit_text(f"🔄 Rasm yaratilmoqda ({count} ta):\n{bar} {progress}%", parse_mode="Markdown")
            await asyncio.sleep(1)

            # Har 1 sekundda tayyor-yo‘qligini tekshiradi
            urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
            async with aiohttp.ClientSession() as check_session:
                async with check_session.get(urls[0]) as check:
                    if check.status == 200:
                        break

        await waiting_msg.edit_text(f"✅ Rasm tayyor! 📸", parse_mode="Markdown")
        media_group = [InputMediaPhoto(url) for url in urls]
        await query.message.reply_media_group(media_group)

        # Admin xabari
        username = f"@{query.from_user.username}" if query.from_user.username else "Ismi yo'q"
        admin_caption = (
            f"👤 Foydalanuvchi: {query.from_user.id} | {username}\n"
            f"🖌 Matn: {escape_md(prompt)}\n"
            f"🌎 Tarjima: {escape_md(translated)}"
        )

        await context.bot.send_media_group(ADMIN_ID, media_group)
        await context.bot.send_message(ADMIN_ID, admin_caption, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await waiting_msg.edit_text("⚠️ Xatolik yuz berdi. Qaytadan urinib ko‘ring.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Ruxsat yo‘q.")

    if update.message.photo:
        users = get_all_users()
        count = 0
        for user_id in users:
            try:
                await context.bot.send_photo(user_id, update.message.photo[-1].file_id, caption=update.message.caption or "")
                count += 1
            except:
                continue
        return await update.message.reply_text(f"✅ {count} foydalanuvchiga rasm yuborildi.")

    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("✍️ Foydalanish: /broadcast <xabar>")

    users = get_all_users()
    count = 0
    for user_id in users:
        try:
            await context.bot.send_message(user_id, text)
            count += 1
        except:
            continue

    await update.message.reply_text(f"✅ {count} foydalanuvchiga xabar yuborildi.")

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Ruxsat yo‘q.")

    keys_info = "\n".join(
        [f"• {k['token'][:10]}... | {k['session'][:8]}..." for k in DIGEN_KEYS]
    )

    await update.message.reply_text(
        f"📊 *Yuklangan kalitlar:* {len(DIGEN_KEYS)}\n{keys_info}",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(generate, pattern="count_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_image_count))
    app.run_polling()

if __name__ == "__main__":
    main()
