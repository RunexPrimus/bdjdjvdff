import logging
import requests
import asyncio
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
from dotenv import load_dotenv
import os

# 🔹 Load environment variables from .env file
load_dotenv()

# 🔹 LOG CONFIG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 BOT TOKEN and other sensitive data from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DIGEN_TOKEN = os.getenv("DIGEN_TOKEN")
DIGEN_SESSION_ID = os.getenv("DIGEN_SESSION_ID")

# 🔹 DIGEN API CONFIG
DIGEN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "digen-language": "uz-US",
    "digen-platform": "web",
    "digen-token": DIGEN_TOKEN,
    "digen-sessionid": DIGEN_SESSION_ID,
    "origin": "https://rm.digen.ai",
    "referer": "https://rm.digen.ai/",
}
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"

# 🔹 Loglar
logs = []

# 🔹 Markdown xavfsiz qilish
def escape_markdown(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# 🔹 Prompt tarjimasi (Google Translate API)
def translate_prompt(prompt: str) -> str:
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": "auto",
                "tl": "en",
                "dt": "t",
                "q": prompt
            },
            timeout=5
        )
        result = r.json()
        translated = "".join([part[0] for part in result[0]])
        return translated
    except Exception as e:
        logger.error("Tarjima xatosi: %s", e)
        return prompt  # fallback

# 🔹 START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 *Assalomu Alaykum!* Men Digen AI botman.\n\n"
        "✍️ Menga oʻz Ideyangizni yuboring va men uni rasmga aylantiraman!\n\n"
        "Misol uchun: `Futuristic cyberpunk city with neon lights`\n\n"
        "💡 Siz Matnni istalgan tilda kiritishingiz mumkin, lekin Tarjima xatolari tufayli muammlar boʻlishi mumkin, Ingliz tilida soʻrov yuborish natijaning aniqligiga katta taʼsir qiladi.!\n"
        "🪪 Ega: @Rune//_13 \n"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# 🔹 IMAGE GENERATION (default 4 images)
async def generate_images(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int = 4):
    prompt = context.user_data.get("prompt")
    if not prompt:
        await update.message.reply_text("❌ Prompt not found.")
        return

    waiting_msg = await update.message.reply_text("🎨 Generating images... ⏳")

    try:
        payload = {
            "prompt": prompt,
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
        logger.info("RESPONSE: %s", r.text)

        if r.status_code == 200:
            data = r.json()
            image_id = data.get("data", {}).get("id")

            if not image_id:
                await waiting_msg.edit_text("❌ Error: image ID not found.")
                return

            await asyncio.sleep(5)

            image_urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(count)]
            media_group = [InputMediaPhoto(url) for url in image_urls]

            await waiting_msg.edit_text("✅ Images are ready! 📸")
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)

            # 🔹 Log
            user = update.effective_user
            logs.append({
                "username": user.username or "N/A",
                "user_id": user.id,
                "prompt": prompt,
                "images": image_urls
            })

            # 🔹 Admin notification
            if ADMIN_ID:
                admin_text = (
                    f"👤 @{user.username or 'N/A'} (ID: {user.id})\n"
                    f"🖌 {prompt}"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
                await context.bot.send_media_group(chat_id=ADMIN_ID, media=media_group)

        else:
            await waiting_msg.edit_text(f"❌ API Error: {r.status_code}")

    except Exception as e:
        logger.error("Xatolik: %s", str(e))
        await waiting_msg.edit_text("⚠️ Unknown error. Please try again later.")

# 🔹 MAIN
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_images))  # Automatically triggers image generation
    app.run_polling()

if __name__ == "__main__":
    main()
