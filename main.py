import os
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import aiosqlite
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import RPCError, BadRequestError


# ===================== ENV =====================
load_dotenv()

def env_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

BOT_TOKEN = env_required("BOT_TOKEN")
TG_API_ID = int(env_required("TG_API_ID"))
TG_API_HASH = env_required("TG_API_HASH")
RELAYER_SESSION = env_required("RELAYER_SESSION")

CRYPTOPAY_TOKEN = env_required("CRYPTOPAY_TOKEN")
CRYPTOPAY_BASE_URL = os.getenv("CRYPTOPAY_BASE_URL", "https://pay.crypt.bot").rstrip("/")  # :contentReference[oaicite:2]{index=2}
CRYPTOPAY_CURRENCY_TYPE = os.getenv("CRYPTOPAY_CURRENCY_TYPE", "fiat").lower()            # :contentReference[oaicite:3]{index=3}
CRYPTOPAY_FIAT = os.getenv("CRYPTOPAY_FIAT", "USD")
CRYPTOPAY_ACCEPTED_ASSETS = os.getenv("CRYPTOPAY_ACCEPTED_ASSETS", "USDT")  # TONni olib tashla
INVOICE_EXPIRES_IN = int(os.getenv("INVOICE_EXPIRES_IN", "900"))
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "12"))

USDT_PER_STAR = float(os.getenv("USDT_PER_STAR", "0.02"))
MARKUP_PCT = float(os.getenv("MARKUP_PCT", "0"))

DB_PATH = "bot.db"


# ===================== Gifts =====================
@dataclass(frozen=True)
class GiftItem:
    id: int
    stars: int
    label: str

GIFT_CATALOG: List[GiftItem] = [
    GiftItem(6028601630662853006, 50, "🍾 50★"),
    GiftItem(5170521118301225164, 100, "💎 100★"),
    GiftItem(5170690322832818290, 100, "💍 100★"),
    GiftItem(5168043875654172773, 100, "🏆 100★"),
    GiftItem(5170564780938756245, 50, "🚀 50★"),
    GiftItem(5170314324215857265, 50, "💐 50★"),
    GiftItem(5170144170496491616, 50, "🎂 50★"),
    GiftItem(5168103777563050263, 25, "🌹 25★"),
    GiftItem(5170250947678437525, 25, "🎁 25★"),
    GiftItem(5170233102089322756, 15, "🧸 15★"),
    GiftItem(5170145012310081615, 15, "💝 15★"),
    GiftItem(5922558454332916696, 50, "🎄 50★"),
    GiftItem(5956217000635139069, 50, "🧸(hat) 50★"),
]

GIFTS_BY_PRICE: Dict[int, List[GiftItem]] = {}
GIFTS_BY_ID: Dict[int, GiftItem] = {}
for g in GIFT_CATALOG:
    GIFTS_BY_PRICE.setdefault(g.stars, []).append(g)
    GIFTS_BY_ID[g.id] = g
ALLOWED_PRICES = sorted(GIFTS_BY_PRICE.keys())


def calc_amount_usd(stars: int) -> str:
    amt = stars * USDT_PER_STAR
    if MARKUP_PCT:
        amt = amt * (1 + MARKUP_PCT / 100.0)
    return f"{amt:.2f}"


# ===================== DB =====================
async def db_connect():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA synchronous=NORMAL;")
    await db.execute("PRAGMA busy_timeout=5000;")
    return db

async def db_init():
    async with await db_connect() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            target TEXT DEFAULT 'me',
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL,
            hide_name INTEGER DEFAULT 0
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            hide_name INTEGER DEFAULT 0,
            amount TEXT NOT NULL,
            invoice_id INTEGER DEFAULT NULL,
            invoice_url TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'created', -- created|invoice_active|paid|sending|sent|failed|expired
            comment_attached INTEGER DEFAULT NULL,
            error TEXT DEFAULT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        await db.commit()

async def db_ensure_user(user_id: int):
    async with await db_connect() as db:
        await db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES(?)", (user_id,))
        await db.commit()

async def db_get_settings(user_id: int) -> Tuple[str, Optional[str], Optional[int], int]:
    async with await db_connect() as db:
        cur = await db.execute(
            "SELECT target, comment, selected_gift_id, hide_name FROM user_settings WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return ("me", None, None, 0)
        return (row[0] or "me", row[1], row[2], int(row[3] or 0))

async def db_set_target(user_id: int, target: str):
    async with await db_connect() as db:
        await db.execute("UPDATE user_settings SET target=? WHERE user_id=?", (target, user_id))
        await db.commit()

async def db_set_comment(user_id: int, comment: Optional[str]):
    async with await db_connect() as db:
        await db.execute("UPDATE user_settings SET comment=? WHERE user_id=?", (comment, user_id))
        await db.commit()

async def db_set_selected_gift(user_id: int, gift_id: Optional[int]):
    async with await db_connect() as db:
        await db.execute("UPDATE user_settings SET selected_gift_id=? WHERE user_id=?", (gift_id, user_id))
        await db.commit()

async def db_toggle_hide_name(user_id: int) -> int:
    async with await db_connect() as db:
        cur = await db.execute("SELECT hide_name FROM user_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        cur_val = int(row[0] or 0) if row else 0
        new_val = 0 if cur_val == 1 else 1
        await db.execute("UPDATE user_settings SET hide_name=? WHERE user_id=?", (new_val, user_id))
        await db.commit()
        return new_val

async def db_create_order(tg_user_id: int, target: str, gift: GiftItem, comment: Optional[str], hide_name: int, amount: str) -> int:
    now = int(time.time())
    async with await db_connect() as db:
        cur = await db.execute("""
            INSERT INTO orders (tg_user_id, target, gift_id, stars, comment, hide_name, amount, status, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?, 'created', ?, ?)
        """, (tg_user_id, target, gift.id, gift.stars, comment, hide_name, amount, now, now))
        await db.commit()
        return cur.lastrowid

async def db_set_invoice(order_id: int, invoice_id: int, invoice_url: str):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders SET invoice_id=?, invoice_url=?, status='invoice_active', updated_at=?
            WHERE order_id=?
        """, (invoice_id, invoice_url, now, order_id))
        await db.commit()

async def db_mark_paid(order_id: int):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("UPDATE orders SET status='paid', updated_at=? WHERE order_id=?", (now, order_id))
        await db.commit()

async def db_mark_sending(order_id: int):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("UPDATE orders SET status='sending', updated_at=? WHERE order_id=?", (now, order_id))
        await db.commit()

async def db_mark_sent(order_id: int, comment_attached: Optional[bool]):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders SET status='sent', comment_attached=?, updated_at=? WHERE order_id=?
        """, (None if comment_attached is None else (1 if comment_attached else 0), now, order_id))
        await db.commit()

async def db_mark_failed(order_id: int, error: str):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("UPDATE orders SET status='failed', error=?, updated_at=? WHERE order_id=?", (error[:700], now, order_id))
        await db.commit()

async def db_mark_expired(order_id: int):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("UPDATE orders SET status='expired', updated_at=? WHERE order_id=?", (now, order_id))
        await db.commit()

async def db_get_active_orders(limit: int = 100):
    async with await db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, tg_user_id, target, gift_id, stars, comment, hide_name, amount, invoice_id, invoice_url, status
            FROM orders
            WHERE status IN ('invoice_active','paid')
            ORDER BY updated_at ASC
            LIMIT ?
        """, (limit,))
        return await cur.fetchall()

async def db_get_order(order_id: int):
    async with await db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, tg_user_id, target, gift_id, stars, comment, hide_name, amount, invoice_id, invoice_url, status, comment_attached, error
            FROM orders WHERE order_id=?
        """, (order_id,))
        return await cur.fetchone()


# ===================== Crypto Pay (CryptoBot) =====================
class CryptoPayClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/") + "/api"
        self.token = token
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def call(self, method: str, params: dict) -> dict:
        await self.start()
        url = f"{self.base_url}/{method}"
        headers = {"Crypto-Pay-API-Token": self.token}  # :contentReference[oaicite:4]{index=4}
        async with self.session.post(url, json=params, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as r:
            data = await r.json(content_type=None)
            if not data.get("ok"):
                raise RuntimeError(data.get("error") or "CryptoPay error")
            return data["result"]

    async def create_invoice(self, amount: str, description: str, payload: str) -> dict:
        # createInvoice supports fiat + accepted_assets :contentReference[oaicite:5]{index=5}
        params = {
            "currency_type": "fiat",
            "fiat": CRYPTOPAY_FIAT,
            "amount": amount,
            "accepted_assets": CRYPTOPAY_ACCEPTED_ASSETS,
            "description": description,
            "payload": payload,
            "expires_in": INVOICE_EXPIRES_IN,
        }
        return await self.call("createInvoice", params)

    async def get_invoices(self, invoice_ids: str, status: Optional[str] = None) -> dict:
        # getInvoices status: active/paid :contentReference[oaicite:6]{index=6}
        params = {"invoice_ids": invoice_ids}
        if status:
            params["status"] = status
        return await self.call("getInvoices", params)

cryptopay = CryptoPayClient(CRYPTOPAY_BASE_URL, CRYPTOPAY_TOKEN)


# ===================== Relayer =====================
class Relayer:
    def __init__(self):
        self.client = TelegramClient(
            StringSession(RELAYER_SESSION),
            TG_API_ID,
            TG_API_HASH,
            timeout=25,
            connection_retries=5,
            retry_delay=2,
            auto_reconnect=True,
        )
        self._lock = asyncio.Lock()

    async def start(self):
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError("RELAYER_SESSION invalid. QR/session qayta oling.")
        return await self.client.get_me()

    async def stop(self):
        await self.client.disconnect()

    def _clean_comment(self, s: Optional[str]) -> str:
        if not s:
            return ""
        s = s.strip().replace("\r", " ").replace("\n", " ")
        if len(s) > 120:
            s = s[:120]
        return s

    async def preflight(self, target: Union[str, int], gift: GiftItem):
        async with self._lock:
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")
            try:
                await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError("user_id ishlamadi. @username ishlating yoki receiver relayerga 1 marta yozsin.")
                raise

    async def send_gift(self, target: Union[str, int], gift: GiftItem, comment: Optional[str], hide_name: bool) -> Tuple[bool, Optional[str]]:
        async with self._lock:
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            peer = await self.client.get_input_entity(target)

            txt = self._clean_comment(comment)
            msg_obj = None if not txt else types.TextWithEntities(text=txt, entities=[])

            extra = {}
            if hide_name:
                extra["hide_name"] = True

            async def _do_send(message_obj):
                invoice = types.InputInvoiceStarGift(peer=peer, gift_id=gift.id, message=message_obj, **extra)
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            if msg_obj is None:
                await _do_send(None)
                return (False, None)

            try:
                await _do_send(msg_obj)
                return (True, None)
            except RPCError as e:
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _do_send(None)
                    return (False, "⚠️ Komment Telegram tomonidan qabul qilinmadi (STARGIFT_MESSAGE_INVALID). Gift kommentsiz yuborildi.")
                raise


# ===================== UI helpers =====================
class Form(StatesGroup):
    waiting_target = State()
    waiting_comment = State()

def normalize_target(text: str) -> Union[str, int]:
    t = (text or "").strip()
    if not t or t.lower() == "me":
        return "me"
    if t.startswith("@"):
        return t
    if t.isdigit():
        return int(t)
    return "@" + t

def safe_comment(text: str) -> str:
    t = (text or "").strip()
    if len(t) > 250:
        t = t[:250]
    return t

def main_menu_kb(hide_name: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Qabul qiluvchi", callback_data="menu:target")
    kb.button(text="💬 Komment", callback_data="menu:comment")
    kb.button(text="🎁 Sovg'a tanlash", callback_data="menu:gift")
    kb.button(text=("🕵️ Hide name: ON" if hide_name == 1 else "👤 Hide name: OFF"), callback_data="toggle:hide")
    kb.button(text="💳 CryptoBot invoice yaratish", callback_data="pay:create")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def back_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    return kb.as_markup()

def price_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in ALLOWED_PRICES:
        kb.button(text=f"⭐ {p}", callback_data=f"price:{p}")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def gifts_by_price_kb(price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in GIFTS_BY_PRICE.get(price, []):
        kb.button(text=f"{g.label} » {g.id}", callback_data=f"gift:{g.id}")
    kb.button(text="⬅️ Narxlar", callback_data="menu:gift")
    kb.adjust(1)
    return kb.as_markup()

def invoice_kb(invoice_url: str, order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Invoice ni ochish", url=invoice_url)
    kb.button(text="🔄 Check", callback_data=f"pay:check:{order_id}")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()

async def render_status(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    target, comment, sel_gift_id, hide_name = await db_get_settings(user_id)
    gift_txt = "Tanlanmagan"
    price_txt = "-"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"
        price_txt = f"{calc_amount_usd(g.stars)} {CRYPTOPAY_FIAT} (CryptoBot)"

    text = (
        "📌 Hozirgi sozlamalar:\n"
        f"🎯 Qabul qiluvchi: {target}\n"
        f"💬 Komment: {(comment if comment else '(yo‘q)')}\n"
        f"🎁 Sovg‘a: {gift_txt}\n"
        f"🔒 Hide name: {'ON' if hide_name==1 else 'OFF'}\n"
        f"💰 To'lov: {price_txt}\n\n"
        "Quyidan tanlang:"
    )
    return text, main_menu_kb(hide_name)


# ===================== Bot app =====================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayer = Relayer()


async def create_invoice_for_order(order_id: int, gift: GiftItem) -> Tuple[int, str]:
    amount = calc_amount_usd(gift.stars)
    inv = await cryptopay.create_invoice(
        amount=amount,
        description=f"Telegram Gift {gift.label} (⭐{gift.stars})",
        payload=f"order:{order_id}",
    )
    invoice_id = int(inv["invoice_id"])
    invoice_url = inv.get("bot_invoice_url") or inv.get("pay_url")  # pay_url deprecated 
    if not invoice_url:
        raise RuntimeError("Invoice URL topilmadi (bot_invoice_url yo'q).")
    return invoice_id, invoice_url


async def invoice_watcher():
    while True:
        try:
            rows = await db_get_active_orders(limit=150)
            active = [r for r in rows if r[10] == "invoice_active" and r[8] is not None]
            if active:
                ids = ",".join(str(r[8]) for r in active)
                res = await cryptopay.get_invoices(invoice_ids=ids, status="paid")  # active/paid 
                items = res.get("items", []) if isinstance(res, dict) else []
                paid_ids = {int(x["invoice_id"]) for x in items}

                for r in active:
                    order_id, tg_user_id, target_str, gift_id, stars, comment, hide_name, amount, invoice_id, invoice_url, status = r
                    if int(invoice_id) not in paid_ids:
                        continue

                    await db_mark_paid(order_id)
                    await db_mark_sending(order_id)

                    try:
                        gift = GIFTS_BY_ID[int(gift_id)]
                        t = (target_str or "me").strip()
                        if t.lower() == "me":
                            target: Union[str, int] = "me"
                        elif t.startswith("@"):
                            target = t
                        elif t.isdigit():
                            target = int(t)
                        else:
                            target = "@" + t

                        comment_attached, warn = await relayer.send_gift(
                            target=target,
                            gift=gift,
                            comment=comment,
                            hide_name=(int(hide_name) == 1),
                        )
                        await db_mark_sent(order_id, comment_attached)

                        msg = (
                            "✅ To'lov qabul qilindi va gift yuborildi!\n"
                            f"🧾 Order #{order_id}\n"
                            f"🎁 {gift.label} (⭐{gift.stars})\n"
                            f"🎯 Target: {target_str}\n"
                        )
                        if warn:
                            msg += f"\n{warn}"
                        await bot.send_message(tg_user_id, msg)

                    except Exception as e:
                        await db_mark_failed(order_id, str(e))
                        await bot.send_message(tg_user_id, f"❌ Paid bo'ldi, lekin gift yuborishda xato:\n{e}")

        except Exception:
            pass

        await asyncio.sleep(WATCH_INTERVAL)


@dp.message(Command("start"))
async def start_cmd(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb = await render_status(m.from_user.id)
    await m.answer(text, reply_markup=kb)

@dp.message(Command("menu"))
async def menu_cmd(m: Message, state: FSMContext):
    await state.clear()
    await db_ensure_user(m.from_user.id)
    text, kb = await render_status(m.from_user.id)
    await m.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "toggle:hide")
async def toggle_hide(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    await state.clear()
    await db_toggle_hide_name(c.from_user.id)
    text, kb = await render_status(c.from_user.id)
    await c.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)
    action = c.data.split(":", 1)[1]

    if action == "home":
        await state.clear()
        text, kb = await render_status(c.from_user.id)
        return await c.message.edit_text(text, reply_markup=kb)

    if action == "target":
        await state.set_state(Form.waiting_target)
        return await c.message.edit_text(
            "🎯 Qabul qiluvchini yuboring:\n"
            "- `me`\n"
            "- `@username`\n"
            "- `user_id` (raqam)\n\n"
            "⚠️ user_id ko'p holatda ishlamaydi (access_hash kerak). Username eng yaxshi.",
            reply_markup=back_menu_kb()
        )

    if action == "comment":
        await state.set_state(Form.waiting_comment)
        return await c.message.edit_text(
            "💬 Komment yuboring (ixtiyoriy).\n"
            "O‘chirish uchun: `-` yuboring.\n"
            "Masalan: `:)` yoki `Congrats bro 🎁`\n\n"
            "⚠️ Agar Telegram commentni qabul qilmasa, gift kommentsiz ketadi va bot ogohlantiradi.",
            reply_markup=back_menu_kb()
        )

    if action == "gift":
        await state.clear()
        return await c.message.edit_text("🎁 Sovg‘a narxini tanlang:", reply_markup=price_kb())


@dp.message(Form.waiting_target)
async def set_target(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    await db_set_target(m.from_user.id, str(normalize_target(m.text)))
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer("✅ Qabul qiluvchi saqlandi.\n\n" + text, reply_markup=kb)

@dp.message(Form.waiting_comment)
async def set_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    raw = (m.text or "").strip()
    if raw == "-" or raw.lower() == "off":
        await db_set_comment(m.from_user.id, None)
    else:
        await db_set_comment(m.from_user.id, safe_comment(raw))
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer("✅ Komment yangilandi.\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data.startswith("price:"))
async def choose_price(c: CallbackQuery):
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await c.message.edit_text("Bunday narx yo‘q.", reply_markup=price_kb())
    await c.message.edit_text(f"⭐ {price} bo‘yicha sovg‘a tanlang:", reply_markup=gifts_by_price_kb(price))

@dp.callback_query(F.data.startswith("gift:"))
async def choose_gift(c: CallbackQuery):
    await c.answer()
    gift_id = int(c.data.split(":", 1)[1])
    if gift_id not in GIFTS_BY_ID:
        return await c.message.edit_text("Gift topilmadi.", reply_markup=price_kb())
    await db_set_selected_gift(c.from_user.id, gift_id)
    text, kb = await render_status(c.from_user.id)
    await c.message.edit_text("✅ Sovg‘a tanlandi.\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data == "pay:create")
async def pay_create(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)

    target_str, comment, sel_gift_id, hide_name = await db_get_settings(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        text, kb = await render_status(c.from_user.id)
        return await c.message.edit_text("❌ Avval sovg‘ani tanlang.\n\n" + text, reply_markup=kb)

    gift = GIFTS_BY_ID[sel_gift_id]

    # preflight
    t = (target_str or "me").strip()
    target: Union[str, int]
    if t.lower() == "me":
        target = "me"
    elif t.startswith("@"):
        target = t
    elif t.isdigit():
        target = int(t)
    else:
        target = "@" + t

    try:
        await relayer.preflight(target=target, gift=gift)
    except Exception as e:
        text, kb = await render_status(c.from_user.id)
        return await c.message.edit_text(f"❌ Preflight xato:\n{e}\n\n" + text, reply_markup=kb)

    amount = calc_amount_usd(gift.stars)
    order_id = await db_create_order(
        tg_user_id=c.from_user.id,
        target=target_str,
        gift=gift,
        comment=comment,
        hide_name=hide_name,
        amount=amount,
    )

    await c.message.edit_text("⏳ CryptoBot invoice yaratyapman...", reply_markup=None)

    try:
        invoice_id, invoice_url = await create_invoice_for_order(order_id, gift)
        await db_set_invoice(order_id, invoice_id, invoice_url)

        await c.message.edit_text(
            "💳 Invoice tayyor!\n\n"
            f"🧾 Order: #{order_id}\n"
            f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
            f"🎯 Target: {target_str}\n"
            f"💬 Comment: {(comment if comment else '(bo‘sh)')}\n"
            f"🔒 Hide name: {'ON' if hide_name==1 else 'OFF'}\n"
            f"💰 Amount: {amount} {CRYPTOPAY_FIAT}\n\n"
            "✅ To‘lov bo‘lsa avtomatik yuboriladi.",
            reply_markup=invoice_kb(invoice_url, order_id)
        )
    except Exception as e:
        await db_mark_failed(order_id, str(e))
        text, kb = await render_status(c.from_user.id)
        await c.message.edit_text(f"❌ Invoice yaratishda xato:\n{e}\n\n" + text, reply_markup=kb)

@dp.callback_query(F.data.startswith("pay:check:"))
async def pay_check(c: CallbackQuery):
    await c.answer()
    order_id = int(c.data.split(":")[-1])
    row = await db_get_order(order_id)
    if not row:
        text, kb = await render_status(c.from_user.id)
        return await c.message.edit_text("Order topilmadi.\n\n" + text, reply_markup=kb)

    (oid, tg_user_id, target_str, gift_id, stars, comment, hide_name, amount, invoice_id, invoice_url, status, comment_attached, error) = row
    if tg_user_id != c.from_user.id:
        return await c.message.answer("❌ Bu order sizniki emas.")

    if not invoice_id:
        return await c.message.edit_text("❌ Invoice yo‘q.")

    try:
        res = await cryptopay.get_invoices(invoice_ids=str(invoice_id))
        items = res.get("items", [])
        inv = items[0] if items else None
        if not inv:
            return await c.message.edit_text("Invoice topilmadi.")
        st = inv.get("status")
        if st == "paid":
            await db_mark_paid(order_id)
            return await c.message.edit_text("✅ Paid! Gift avtomatik yuboriladi (tez orada).")
        elif st == "active":
            return await c.message.edit_text("⏳ Hali paid emas.", reply_markup=invoice_kb(invoice_url, order_id))
        else:
            await db_mark_expired(order_id)
            return await c.message.edit_text(f"⚠️ Invoice status: {st}")
    except Exception as e:
        return await c.message.edit_text(f"❌ Check xato: {e}")


async def main():
    await db_init()
    await cryptopay.start()
    me = await relayer.start()
    print(f"[RELAYER] authorized as: id={me.id} username={me.username}")

    watcher = asyncio.create_task(invoice_watcher())
    try:
        await dp.start_polling(bot)
    finally:
        watcher.cancel()
        try:
            await watcher
        except Exception:
            pass
        await relayer.stop()
        await cryptopay.close()

if __name__ == "__main__":
    asyncio.run(main())
