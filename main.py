import logging
import requests
import asyncio
import re
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# 🔹 LOG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 BOT TOKEN
BOT_TOKEN = "8327134580:AAFjXWF9YUA4dFcZenhEYbnbj6q5tdHyptY"

# 🔹 ADMIN ID
ADMIN_ID = 7440949683

# 🔹 DIGEN COOKIE/TOKEN
DIGEN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "digen-language": "uz-US",
    "digen-platform": "web",
    "digen-token": "4d6574614147492e47656e49585acf31b622a6e6b1cdd757b8c8db654c:1511428:1757701959",
    "digen-sessionid": "aa02e1d8-20c7-4432-bb08-959171099b97",
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
        "✍️ Istalgan prompt yozing — men sizga rasm yasab beraman!\n"
        "Misol: `Futuristic cyberpunk city with neon lights`\n"
        "Murojaat uchun @Rune_13"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


# 🔹 PROMPT -> DIGEN
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    safe_prompt = escape_markdown(prompt)
    waiting_msg = await update.message.reply_text("🎨 Rasmlar yaratilmoqda... ⏳", parse_mode="Markdown")

    try:
        payload = {
            "prompt": prompt,
            "image_size": "512x512",
            "width": 512,
            "height": 512,
            "lora_id": "",
            "batch_size": 4,
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
                await waiting_msg.edit_text("❌ Xatolik: rasm ID topilmadi.")
                return

            await asyncio.sleep(5)

            image_urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(4)]
            media_group = [InputMediaPhoto(url) for url in image_urls]

            await waiting_msg.edit_text("✅ Rasmlar tayyor! 📸")
            await update.message.reply_media_group(media_group)

            await update.message.reply_text(f"🖌 Prompt: `{safe_prompt}`", parse_mode="Markdown")

            # 🔹 Log
            user = update.effective_user
            logs.append({
                "username": user.username or "N/A",
                "user_id": user.id,
                "prompt": prompt,
                "images": image_urls
            })

            # 🔹 Admin uchun xabar
            if ADMIN_ID:
                admin_text = (
                    f"👤 @{user.username or 'N/A'} (ID: {user.id})\n"
                    f"🖌 {prompt}"
                )
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text)
                await context.bot.send_media_group(chat_id=ADMIN_ID, media=media_group)

        else:
            await waiting_msg.edit_text(f"❌ API Xatosi: {r.status_code}")

    except Exception as e:
        logger.error("Xatolik: %s", str(e))
        # 🔹 Foydalanuvchiga oddiy xabar
        await waiting_msg.edit_text("⚠️ Noma'lum xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")


# 🔹 INLINE HANDLER
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("regen"):
        _, old_prompt = query.data.split("|", 1)
        await query.edit_message_text(f"♻️ Qayta generatsiya qilinmoqda...\n`{escape_markdown(old_prompt)}`", parse_mode="Markdown")
        fake_update = Update(update.update_id, message=query.message)
        fake_update.message.text = old_prompt
        await generate(fake_update, context)


# 🔹 ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    if not logs:
        await update.message.reply_text("📭 Hali log yo'q.")
        return

    text = "📑 Oxirgi 5 ta log:\n\n"
    for entry in logs[-5:]:
        text += f"👤 @{entry['username']} (ID: {entry['user_id']})\n🖌 {escape_markdown(entry['prompt'])}\n\n"

    await update.message.reply_text(text, parse_mode="MarkdownV2")


# 🔹 MAIN
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()


if __name__ == "__main__":
    main()
