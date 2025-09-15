import os
import logging
import requests
import asyncio
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# 🔹 LOG CONFIG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 BOT TOKEN va ADMIN
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()  # serverga qo'yiladigan secret variable
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))  # serverga qo'yiladigan admin id

# 🔹 DIGEN API CONFIG
DIGEN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "digen-language": "uz-US",
    "digen-platform": "web",
    "digen-token": os.environ.get("DIGEN_TOKEN", "").strip(),      # secret variable
    "digen-sessionid": os.environ.get("DIGEN_SESSIONID", "").strip(),  # secret variable
    "origin": "https://rm.digen.ai",
    "referer": "https://rm.digen.ai/",
}
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"

# 🔹 Loglar
logs = []

# 🔹 Markdown xavfsiz qilish
def escape_markdown(text: str) -> str:
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', text)

# 🔹 START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 *Salom!* Men Digen AI Botman.\n\n"
        "✍️ Istalgan prompt yozing — men sizga rasm yarataman!\n"
        "Misol: `Kelajak kiberpunk shahri, neon chiroqlar bilan`\n\n"
        "💡 Siz o‘zbek yoki rus tilida yozishingiz mumkin. Eng yaxshi natija uchun ingliz tilida so‘rov yuborish tavsiya etiladi."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# 🔹 GENERATE IMAGE
async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text("❌ Iltimos, prompt yozing.")
        return

    waiting_msg = await update.message.reply_text("🎨 Rasm yaratilmoqda... ⏳")

    try:
        payload = {
            "prompt": prompt,
            "image_size": "512x512",
            "width": 512,
            "height": 512,
            "lora_id": "",
            "batch_size": 4,  # har doim 4 rasm
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
        await waiting_msg.edit_text("❌ Xato: image ID topilmadi.")
        return

    await asyncio.sleep(5)
    
    # 🔹 batch_size = 4 bo'yicha barcha rasm URLlarini yaratish va yuborish
    for i in range(4):
        image_url = f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg"
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)

    await waiting_msg.edit_text("✅ Rasm(lar) tayyor! 📸")

    # 🔹 Log
    user = update.effective_user
    logs.append({
        "username": user.username or "N/A",
        "user_id": user.id,
        "prompt": prompt,
        "images": [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(4)]
    })

    # 🔹 Admin notification
    if ADMIN_ID:
        admin_text = f"👤 @{user.username or 'N/A'} (ID: {user.id})\n🖌 Prompt: {prompt}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
        for i in range(4):
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg")


# 🔹 MAIN
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image))
    app.run_polling()

if __name__ == "__main__":
    main()
