import logging
import requests
import asyncio
import re
import os
import json
import itertools
from deep_translator import GoogleTranslator
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# 🔹 LOG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@Digen_Ai")

# 🔹 DIGEN KEYS
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
_key_cycle = itertools.cycle(DIGEN_KEYS)

DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"

# 🔹 Users database
USERS_FILE = "users.json"
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump([], f)

def add_user(user_id):
    with open(USERS_FILE, "r+") as f:
        data = json.load(f)
        if user_id not in data:
            data.append(user_id)
            f.seek(0)
            f.truncate()
            json.dump(data, f)

def get_all_users():
    with open(USERS_FILE, "r") as f:
        return json.load(f)

# 🔹 DIGEN headers
def get_digen_headers():
    key = next(_key_cycle)
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

# 🔹 Markdown escape
def escape_md(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# 🔹 Translate
def translate_prompt(prompt: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="en").translate(prompt)
    except Exception as e:
        logger.warning(f"Tarjima xatolik: {e}")
        return prompt

# 🔹 Check membership
async def check_membership(user_id, context):
    try:
        chat_member = await context.bot.get_chat_member(FORCE_CHANNEL, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except:
        return False

# 🔹 START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)

    if FORCE_CHANNEL:
        is_member = await check_membership(user.id, context)
        if not is_member:
            join_btn = [[InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@', '')}")]]
            return await update.message.reply_text(
                "🚫 Botdan foydalanish uchun avval kanalga a'zo bo‘ling!",
                reply_markup=InlineKeyboardMarkup(join_btn)
            )

    kb = [[InlineKeyboardButton("🤖 Start Generating", callback_data="start_gen")]]
    await update.message.reply_text(
        "👋 *Welcome!* I'm your AI Image Generator.\n\n"
        "✍️ Write anything in any language — I'll translate it and create beautiful images.\n\n"
        "_Example:_ `Trump burger yemoqda` → `Trump eating a burger`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# 🔹 Handle start gen
async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "✍️ Send me your prompt now.\n\n_Example:_ `Futuristic cyberpunk city with neon lights`",
        parse_mode="Markdown"
    )

# 🔹 Prompt
async def ask_image_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    translated = translate_prompt(prompt)

    context.user_data["prompt"] = prompt
    context.user_data["translated"] = translated

    kb = [[
        InlineKeyboardButton("1️⃣", callback_data="count_1"),
        InlineKeyboardButton("2️⃣", callback_data="count_2"),
        InlineKeyboardButton("4️⃣", callback_data="count_4"),
        InlineKeyboardButton("8️⃣", callback_data="count_8"),
    ]]

    await update.message.reply_text(
        f"🖌 *Your Prompt:*\n`{escape_md(prompt)}`\n\n"
        f"🌎 *Translated:* `{escape_md(translated)}`\n\n"
        "🔢 Choose number of images:",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# 🔹 Generate
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = int(query.data.split("_")[1])
    prompt = context.user_data.get("prompt", "")
    translated = context.user_data.get("translated", "")

    waiting_msg = await query.edit_message_text(
        f"🎨 *Generating {count} image(s)...* ⏳",
        parse_mode="Markdown"
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

        headers = get_digen_headers()
        r = requests.post(DIGEN_URL, headers=headers, json=payload)

        if r.status_code != 200:
            return await waiting_msg.edit_text(f"❌ API Error: {r.status_code}")

        data = r.json()
        image_id = data.get("data", {}).get("id")
        if not image_id:
            return await waiting_msg.edit_text("❌ No image ID received.")

        await asyncio.sleep(5)
        image_urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
        media_group = [InputMediaPhoto(url) for url in image_urls]

        await waiting_msg.edit_text("✅ *Images Ready!* 📸", parse_mode="Markdown")
        await query.message.reply_media_group(media_group)

        # Admin log with caption
        username = f"@{query.from_user.username}" if query.from_user.username else "No username"
        admin_caption = (
            f"👤 User: {query.from_user.id}\n"
            f"👥 Username: {username}\n"
            f"🖌 Prompt: {prompt}\n"
            f"🌎 Translated: {translated}"
        )

        media_group[0].caption = admin_caption
        await context.bot.send_media_group(ADMIN_ID, media_group)

    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await waiting_msg.edit_text("⚠️ Unknown error occurred. Please try again.")

# 🔹 Broadcast
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Access denied.")

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

    await update.message.reply_text(f"✅ Broadcast {count} ta foydalanuvchiga yuborildi.")

# 🔹 Admin panel
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Access denied.")
    keys_info = "\n".join([f"• {k['token'][:10]}... | {k['session'][:8]}..." for k in DIGEN_KEYS])
    await update.message.reply_text(
        f"📊 *Loaded Keys:* {len(DIGEN_KEYS)}\n{keys_info}\n\n"
        "📢 Broadcast yuborish: /broadcast <matn>",
        parse_mode="Markdown"
    )

# 🔹 MAIN
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
