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
    "digen-token": os.environ.get("DIGEN_TOKEN", "").strip(),
    "digen-sessionid": os.environ.get("DIGEN_SESSIONID", "").strip(),
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
        batch_size = 4  # Har doim 4 rasm
        payload = {
            "prompt": prompt,
            "image_size": "512x512",
            "width": 512,
            "height": 512,
            "lora_id": "",
            "batch_size": batch_size,
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

            # 🔹 Foydalanuvchiga barcha rasmni yuborish
            image_urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(batch_size)]
            for url in image_urls:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=url)

            await waiting_msg.edit_text("✅ Rasmlar tayyor! 📸")

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
                admin_text = f"👤 @{user.username or 'N/A'} (ID: {user.id})\n🖌 Prompt: {prompt}"
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
                for url in image_urls:
                    await context.bot.send_photo(chat_id=ADMIN_ID, photo=url)

        else:
            await waiting_msg.edit_text(f"❌ API xato: {r.status_code}")

    except Exception as e:
        logger.error("Xatolik: %s", str(e))
        await waiting_msg.edit_text("⚠️ Noma'lum xato yuz berdi. Keyinroq qayta urinib ko‘ring.")

# 🔹 ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    if not logs:
        await update.message.reply_text("📭 Hali loglar yo‘q.")
        return

    text = "📑 So‘nggi 5 log:\n\n"
    for entry in logs[-5:]:
        text += f"👤 @{entry['username']} (ID: {entry['user_id']})\n🖌 {escape_markdown(entry['prompt'])}\n\n"

    await update.message.reply_text(text, parse_mode="MarkdownV2")

# 🔹 MAIN
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_image))
    app.run_polling()

if __name__ == "__main__":
    main()
