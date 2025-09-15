# main.py
import logging
import requests
import asyncio
import re
import time
from io import BytesIO
from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# -------------------------
# CONFIG / Logging
# -------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------
# CONFIG - put secrets to env in real deploy
# -------------------------
# You can override these by setting env vars before run if you prefer.
import os
BOT_TOKEN = os.getenv("BOT_TOKEN", "8327134580:AAEGrC6yCDRDbLFalfc7vQZkk5KtH3UPfvc")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7440949683"))

# Digen headers - recommended: move token/session to env or db
DIGEN_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "digen-language": "uz-US",
    "digen-platform": "web",
    "digen-token": os.getenv("DIGEN_TOKEN", "4d6574614147492e47656e49585acf31b622a6e6b1cdd757b8c8db654c:1511428:1757701959"),
    "digen-sessionid": os.getenv("DIGEN_SESSION", "aa02e1d8-20c7-4432-bb08-959171099b97"),
    "origin": "https://rm.digen.ai",
    "referer": "https://rm.digen.ai/",
}
DIGEN_URL = "https://api.digen.ai/v2/tools/text_to_image"

# simple runtime logs
logs = []

# -------------------------
# MarkdownV2 escape util
# -------------------------
# Characters that must be escaped in MarkdownV2 per Telegram docs:
# _ * [ ] ( ) ~ ` > # + - = | { } . !
MDV2_CHARS_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!])')

def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # Replace each special char with backslash-escaped version
    return MDV2_CHARS_RE.sub(r'\\\1', text)

# -------------------------
# Safe send helpers (tries MarkdownV2 then falls back)
# -------------------------
from telegram.error import BadRequest

async def safe_reply_text(message, text: str, reply_markup=None):
    """Try sending with MarkdownV2 escaped; if BadRequest, send raw text without parse mode."""
    if text is None:
        text = ""
    # Try MarkdownV2 first
    try:
        escaped = escape_markdown_v2(text)
        return await message.reply_text(escaped, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except BadRequest as e:
        logger.warning("MarkdownV2 send failed (%s). Falling back to plain text. Text: %s", e, text)
        try:
            return await message.reply_text(text, reply_markup=reply_markup)
        except Exception as e2:
            logger.exception("Fallback send also failed: %s", e2)
            raise

async def safe_send_chat_text(bot, chat_id: int, text: str, reply_markup=None):
    """Use bot.send_message with MarkdownV2 escaped and fallback."""
    try:
        escaped = escape_markdown_v2(text)
        return await bot.send_message(chat_id=chat_id, text=escaped, parse_mode="MarkdownV2", reply_markup=reply_markup)
    except BadRequest as e:
        logger.warning("MarkdownV2 send failed (%s). Falling back to plain text. Text: %s", e, text)
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

# -------------------------
# Digen request (run in thread to avoid blocking)
# -------------------------
def digen_request_sync(prompt: str, width=512, height=512, batch_size=4):
    payload = {
        "prompt": prompt,
        "image_size": f"{width}x{height}",
        "width": width,
        "height": height,
        "lora_id": "",
        "batch_size": batch_size,
        "reference_images": [],
        "strength": ""
    }
    try:
        resp = requests.post(DIGEN_URL, headers=DIGEN_HEADERS, json=payload, timeout=60)
        logger.info("Digen status %s", resp.status_code)
        # return whole resp for debugging
        try:
            j = resp.json()
        except Exception:
            j = None
        return resp.status_code, resp.text, j
    except Exception as e:
        logger.exception("Digen request failed: %s", e)
        return None, str(e), None

# -------------------------
# START handler
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Add user to local logs list for simple tracking
    user = update.effective_user
    logs.append({"username": user.username or "N/A", "user_id": user.id, "prompt": "(start)", "ts": time.time()})

    # Build welcome text and escape only when sending
    welcome_text = (
        "👋 *Salom!* Men Digen AI Botman.\n\n"
        "✍️ Istalgan prompt yozing — men sizga rasm yasab beraman!\n"
        "Misol: `Futuristic cyberpunk city with neon lights`\n"
        "Murojaat uchun @Rune_13"
    )
    # Use safe helper (it will escape @Rune_13 correctly)
    await safe_reply_text(update.message, welcome_text)

# -------------------------
# Generate handler
# -------------------------
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ensure message exists
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    prompt = update.message.text.strip()

    # Basic logging
    logs.append({"username": user.username or "N/A", "user_id": user.id, "prompt": prompt, "ts": time.time()})

    # notify user we're working
    waiting_msg = await safe_reply_text(update.message, "🎨 Rasmlar yaratilmoqda... ⏳")

    try:
        # call Digen in thread
        status, text_resp, json_resp = await asyncio.to_thread(digen_request_sync, prompt, 512, 512, 4)

        if status != 200 or not json_resp:
            # send error (use safe send)
            await waiting_msg.edit_text(f"❌ API Xatolik: {status}\n{text_resp}")
            return

        # Extract image id or urls depending on API structure
        image_id = None
        image_urls = []
        data = json_resp.get("data") if isinstance(json_resp, dict) else None
        if isinstance(data, dict):
            image_id = data.get("id") or data.get("task_id")
            # sometimes data may contain images list
            imgs = data.get("images") or data.get("image_urls") or None
            if imgs and isinstance(imgs, list):
                image_urls = imgs[:4]

        if image_id and not image_urls:
            image_urls = [f"https://liveme-image.s3.amazonaws.com/{image_id}-{i}.jpeg" for i in range(4)]

        if not image_urls:
            await waiting_msg.edit_text("❌ Rasm URL yoki ID topilmadi API javobida.")
            return

        # small wait to let images be available (as before)
        await asyncio.sleep(5)

        # send media group
        media_group = [InputMediaPhoto(url) for url in image_urls]
        try:
            await update.message.reply_media_group(media_group)
        except Exception as e:
            logger.warning("reply_media_group failed: %s - falling back to sending individually", e)
            for url in image_urls:
                try:
                    await update.message.reply_photo(photo=url)
                except Exception:
                    # ignore some failures for robust behavior
                    pass

        # show prompt back to user (escaped)
        await safe_reply_text(update.message, f"🖌 Prompt: {prompt}")

        # admin notify: send text and first image if possible
        try:
            if ADMIN_ID:
                await safe_send_chat_text(context.bot, ADMIN_ID, f"👤 @{user.username or 'N/A'} (ID: {user.id})\n🖌 {prompt}")
                # forward original user message to admin (if permitted)
                try:
                    await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
                except Exception:
                    # fallback: send first image url
                    try:
                        await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_urls[0])
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Admin notify failed: %s", e)

        # update waiting message
        try:
            await waiting_msg.edit_text("✅ Rasmlar tayyor! 📸")
        except Exception:
            pass

    except Exception as e:
        logger.exception("Xatolik generate ichida: %s", e)
        try:
            await waiting_msg.edit_text("⚠️ Noma'lum xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
        except Exception:
            pass

# -------------------------
# Inline callback handler (regen and simple admin callbacks)
# -------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("regen|"):
        # get prompt after prefix
        _, old_prompt = data.split("|", 1)
        # inform user
        try:
            await query.edit_message_text(rf"♻️ Qayta generatsiya qilinmoqda...\n`{escape_markdown_v2(old_prompt)}`", parse_mode="MarkdownV2")
        except BadRequest:
            # fallback plain text
            try:
                await query.edit_message_text(f"♻️ Qayta generatsiya qilinmoqda...\n{old_prompt}")
            except Exception:
                pass

        # call generate flow by building a minimal fake Update:
        class MinimalMessage:
            def __init__(self, chat_id, from_user, text, message):
                self.chat = message.chat
                self.chat_id = chat_id
                self.from_user = from_user
                self.text = text
                self.message_id = message.message_id

            async def reply_text(self, txt, **kwargs):
                # delegate to bot send_message to same chat
                return await context.bot.send_message(chat_id=self.chat.id, text=txt, **kwargs)

            async def reply_media_group(self, media, **kwargs):
                return await context.bot.send_media_group(chat_id=self.chat.id, media=media, **kwargs)

            async def reply_photo(self, photo, **kwargs):
                return await context.bot.send_photo(chat_id=self.chat.id, photo=photo, **kwargs)

        fake_msg = MinimalMessage(chat_id=query.message.chat.id, from_user=query.from_user, text=old_prompt, message=query.message)
        fake_update = Update(update.update_id, message=None)
        # attach minimal message as attribute used by generate
        fake_update.message = fake_msg
        fake_update.effective_user = query.from_user
        # run generate with our fake update
        await generate(fake_update, context)
        return

    # You can expand admin callback handling here if needed
    await query.edit_message_text("⚙️ Tugma bosildi: " + data)

# -------------------------
# ADMIN (simple listing of last logs)
# -------------------------
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        return await safe_reply_text(update.message, "⛔ Siz admin emassiz.")
    if not logs:
        return await safe_reply_text(update.message, "📭 Hali log yo'q.")

    text = "📑 Oxirgi 5 ta log:\n\n"
    for entry in logs[-5:]:
        uname = entry.get("username", "N/A")
        uid = entry.get("user_id", "N/A")
        pr = entry.get("prompt", "")
        text += f"👤 @{escape_markdown_v2(uname)} (ID: {uid})\n🖌 {escape_markdown_v2(pr)}\n\n"

    await safe_reply_text(update.message, text)

# -------------------------
# Router: messages to generate, commands, callbacks
# -------------------------
def main():
    if not BOT_TOKEN or BOT_TOKEN.strip() == "":
        print("ERROR: BOT_TOKEN not set. Set BOT_TOKEN env var or the variable in script.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate))

    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
