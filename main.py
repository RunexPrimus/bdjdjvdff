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

# 🔹 LOG CONFIG
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔹 BOT TOKEN
BOT_TOKEN = "8315992324:AAFb4k03VILHF63nlyJtMOrpESVKcG5OSzs"

# 🔹 ADMIN ID
ADMIN_ID = 7440949683

# 🔹 DIGEN API CONFIG (sening token va sessioning bilan)
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

# 🔹 IMAGE COUNT SELECTOR
async def ask_image_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    translated = translate_prompt(prompt)
    context.user_data["prompt"] = translated

    keyboard = [
        [
            InlineKeyboardButton("1️⃣", callback_data="count|1"),
            InlineKeyboardButton("2️⃣", callback_data="count|2"),
            InlineKeyboardButton("3️⃣", callback_data="count|3"),
            InlineKeyboardButton("4️⃣", callback_data="count|4"),
        ]
    ]
    await update.message.reply_text(
        f"🖌 Prompt: *{escape_markdown(translated)}*\n\n"
        "📸 How many images do you want?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# 🔹 GENERATE IMAGE
async def generate_images(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int):
    prompt = context.user_data.get("prompt")
    if not prompt:
        await update.callback_query.edit_message_text("❌ Prompt not found.")
        return

    waiting_msg = await update.callback_query.edit_message_text("🎨 Generating images... ⏳")

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

# 🔹 CALLBACK HANDLER
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("count"):
        _, count = query.data.split("|")
        await generate_images(update, context, int(count))

# 🔹 ADMIN PANEL
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not admin.")
        return
    if not logs:
        await update.message.reply_text("📭 No logs yet.")
        return

    text = "📑 Last 5 logs:\n\n"
    for entry in logs[-5:]:
        text += f"👤 @{entry['username']} (ID: {entry['user_id']})\n🖌 {escape_markdown(entry['prompt'])}\n\n"

    await update.message.reply_text(text, parse_mode="MarkdownV2")

# 🔹 MAIN
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_image_count))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
