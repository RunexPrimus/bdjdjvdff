import logging
import requests
import asyncio
import re
import os
from deep_translator import GoogleTranslator
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# 🔹 LOG CONFIG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 ENV VARIABLES
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))
DIGEN_TOKEN = os.getenv("DIGEN_TOKEN")
DIGEN_SESSIONID = os.getenv("DIGEN_SESSIONID")

DIGEN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "digen-language": "uz-US",
    "digen-platform": "web",
    "digen-token": DIGEN_TOKEN,
    "digen-sessionid": DIGEN_SESSIONID,
    "origin": "https://rm.digen.ai",
    "referer": "https://rm.digen.ai/",
}
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"


# 🔹 Markdown xavfsiz qilish
def escape_md(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)


# 🔹 Deep Translator
def translate_prompt(prompt: str) -> str:
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(prompt)
        return translated
    except Exception as e:
        logger.error(f"Tarjima xatolik: {e}")
        return prompt


# 🔹 START command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🎨 Start Generating", callback_data="start_gen")]]
    await update.message.reply_text(
        "👋 *Welcome!*\n\n"
        "I'm your AI Image Generator bot. ✨\n\n"
        "✍️ Write *anything* in *any language*, I will auto-translate it into English "
        "and create up to 8 images for you.\n\n"
        "_Example:_ `Trump burger yemoqda` → `Trump eating a burger`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# 🔹 Prompt so‘rash
async def handle_start_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "✍️ Send me your prompt now.\n\n_Example:_ `Futuristic cyberpunk city with neon lights`",
        parse_mode="Markdown"
    )


# 🔹 Prompt kelganda so‘rovchi
async def ask_image_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    translated = translate_prompt(prompt)

    context.user_data["prompt"] = prompt
    context.user_data["translated"] = translated

    kb = [
        [
            InlineKeyboardButton("1️⃣", callback_data="count_1"),
            InlineKeyboardButton("2️⃣", callback_data="count_2"),
            InlineKeyboardButton("3️⃣", callback_data="count_3"),
            InlineKeyboardButton("4️⃣", callback_data="count_4"),
        ],
        [
            InlineKeyboardButton("5️⃣", callback_data="count_5"),
            InlineKeyboardButton("6️⃣", callback_data="count_6"),
            InlineKeyboardButton("7️⃣", callback_data="count_7"),
            InlineKeyboardButton("8️⃣", callback_data="count_8"),
        ]
    ]
    await update.message.reply_text(
        f"🖌 *Your Prompt:*\n`{escape_md(prompt)}`\n\n"
        f"🌎 *Translated:* `{escape_md(translated)}`\n\n"
        "🔢 Select how many images you want to generate:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# 🔹 Tasvir yaratish
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    count = int(query.data.split("_")[1])
    prompt = context.user_data["prompt"]
    translated = context.user_data["translated"]

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

        r = requests.post(DIGEN_URL, headers=DIGEN_HEADERS, json=payload)
        logger.info("STATUS: %s", r.status_code)

        if r.status_code != 200:
            await waiting_msg.edit_text(f"❌ API Error: {r.status_code}")
            return

        data = r.json()
        image_id = data.get("data", {}).get("id")
        if not image_id:
            await waiting_msg.edit_text("❌ No image ID received.")
            return

        await asyncio.sleep(5)
        image_urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
        media_group = [InputMediaPhoto(url) for url in image_urls]

        await waiting_msg.edit_text("✅ *Images Ready!* 📸", parse_mode="Markdown")
        await query.message.reply_media_group(media_group)

        regen_btn = InlineKeyboardMarkup([[InlineKeyboardButton("♻️ Regenerate", callback_data=f"regen|{prompt}")]])
        await query.message.reply_text(
            f"🖌 Prompt: `{escape_md(prompt)}`\n🌎 EN: `{escape_md(translated)}`",
            parse_mode="Markdown",
            reply_markup=regen_btn
        )

    except Exception as e:
        logger.error(f"Xatolik: {e}")
        await waiting_msg.edit_text("⚠️ Unknown error occurred. Please try again.")


# 🔹 ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Access denied.")
    await update.message.reply_text("📊 Logs currently disabled in this version.")


# 🔹 MAIN
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(handle_start_gen, pattern="start_gen"))
    app.add_handler(CallbackQueryHandler(generate, pattern="count_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_image_count))
    app.run_polling()


if __name__ == "__main__":
    main()
