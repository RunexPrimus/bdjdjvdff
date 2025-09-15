import os
import json
import logging
import asyncio
import random
import re
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import httpx
from deep_translator import GoogleTranslator

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@YourChannel")
DIGEN_KEYS = json.loads(os.getenv("DIGEN_KEYS", "[]"))
KEY_INDEX = 0
USERS_FILE = "users.json"

logging.basicConfig(level=logging.INFO)

# =========================
# HELPERS
# =========================
def save_user(user_id):
    users = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(users, f)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []

def get_next_key():
    global KEY_INDEX
    if not DIGEN_KEYS:
        raise ValueError("DIGEN_KEYS is empty")
    key = DIGEN_KEYS[KEY_INDEX]
    KEY_INDEX = (KEY_INDEX + 1) % len(DIGEN_KEYS)
    return key.split(":")

async def check_membership(user_id: int, bot):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def translate_prompt(prompt):
    try:
        return GoogleTranslator(source='auto', target='en').translate(prompt)
    except:
        return prompt

def escape_md(text):
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)
    await update.message.reply_text(
        "👋 *Welcome!* \nSend me any prompt and I will generate beautiful images for you 🎨",
        parse_mode="Markdown"
    )

async def ask_image_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    save_user(user_id)

    if not await check_membership(user_id, context.bot):
        kb = [[InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{CHANNEL_ID.replace('@','')}")]]
        await update.message.reply_text(
            "⛔ *Please join our channel first!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    prompt = update.message.text
    translated = translate_prompt(prompt)
    context.user_data["prompt"] = prompt
    context.user_data["translated"] = translated

    kb = [
        [
            InlineKeyboardButton(f"{i}️⃣", callback_data=f"count_{i}")
            for i in range(1, 5)
        ],
        [
            InlineKeyboardButton(f"{i}️⃣", callback_data=f"count_{i}")
            for i in range(5, 9)
        ]
    ]

    await update.message.reply_text(
        f"🖌 *Your Prompt:*\n`{escape_md(prompt)}`\n\n"
        f"🌎 *Translated:* `{escape_md(translated)}`\n\n"
        "🔢 *Choose how many images to generate:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = int(query.data.split("_")[1])
    prompt = context.user_data.get("prompt")
    translated = context.user_data.get("translated")

    progress_msg = await query.edit_message_text("🎨 *Generating images...*", parse_mode="Markdown")

    key, session = get_next_key()

    # Bu joyda haqiqiy Digen API chaqirishingiz mumkin
    images = [f"https://picsum.photos/seed/{random.randint(1,9999)}/600/600" for _ in range(count)]

    # Foydalanuvchiga albom
    media_group = [InputMediaPhoto(media=url) for url in images]
    await context.bot.send_media_group(chat_id=query.message.chat_id, media=media_group)

    # Admin panelga albom + caption
    username = query.from_user.username or "NoUsername"
    caption = (
        f"👤 *User:* `{query.from_user.id}`\n"
        f"🔗 *Username:* @{username}\n"
        f"🖌 *Prompt:* `{escape_md(prompt)}`\n"
        f"🌎 *Translated:* `{escape_md(translated)}`"
    )
    admin_media = [InputMediaPhoto(media=url) for url in images]
    admin_media[0].caption = caption
    admin_media[0].parse_mode = "Markdown"
    await context.bot.send_media_group(chat_id=ADMIN_ID, media=admin_media)

    await progress_msg.delete()

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Access denied.")
    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("❌ Use: /broadcast <text>")
    users = load_users()
    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await update.message.reply_text(f"✅ Sent to {sent}/{len(users)} users.")

# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_image_count))
    app.add_handler(CallbackQueryHandler(generate, pattern=r"count_\d+"))

    app.run_polling()

if __name__ == "__main__":
    main()
