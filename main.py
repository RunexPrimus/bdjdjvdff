import os
import asyncio
import time
import json
import sqlite3
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
from telethon.errors import RPCError


# ===================== ENV =====================
load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
TG_API_ID = int(os.environ["TG_API_ID"])
TG_API_HASH = os.environ["TG_API_HASH"]
RELAYER_SESSION = os.environ["RELAYER_SESSION"]

# Crypto Pay (CryptoBot)
CRYPTOPAY_TOKEN = os.environ["CRYPTOPAY_TOKEN"]
CRYPTOPAY_BASE_URL = os.getenv("CRYPTOPAY_BASE_URL", "https://pay.crypt.bot")  # mainnet :contentReference[oaicite:4]{index=4}
CRYPTOPAY_CURRENCY_TYPE = os.getenv("CRYPTOPAY_CURRENCY_TYPE", "fiat").lower()  # "fiat" yoki "crypto"
CRYPTOPAY_FIAT = os.getenv("CRYPTOPAY_FIAT", "USD")
CRYPTOPAY_ACCEPTED_ASSETS = os.getenv("CRYPTOPAY_ACCEPTED_ASSETS", "USDT,TON")
CRYPTOPAY_ASSET = os.getenv("CRYPTOPAY_ASSET", "USDT")  # currency_type=crypto bo'lsa
INVOICE_EXPIRES_IN = int(os.getenv("INVOICE_EXPIRES_IN", "900"))  # seconds

# Pricing
USDT_PER_STAR = float(os.getenv("USDT_PER_STAR", "0.02"))  # 1★ = 0.02 USD (o'zing mosla)
MARKUP_PCT = float(os.getenv("MARKUP_PCT", "0"))  # % ustama

# Bot settings
DB_PATH = "bot.db"
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "12"))  # invoice watcher interval (sec)
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))  # xohlasang adminga error yuborish


# ===================== STATIC GIFT CATALOG =====================
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


def calc_price_amount(stars: int) -> str:
    """Invoice amount as string float."""
    amt = stars * USDT_PER_STAR
    if MARKUP_PCT:
        amt = amt * (1.0 + MARKUP_PCT / 100.0)
    # CryptoPay expects string float like "1.50" :contentReference[oaicite:5]{index=5}
    return f"{amt:.2f}"


# ===================== DB =====================
async def db_connect():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA synchronous=NORMAL;")
    await db.execute("PRAGMA busy_timeout=5000;")
    return db

async def db_healthcheck_and_fix():
    """Agar DB corrupt bo'lsa avtomatik rename qilib yangidan ochadi."""
    if not os.path.exists(DB_PATH):
        return
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.execute("PRAGMA quick_check;")
        row = cur.fetchone()
        con.close()
        if not row or row[0] != "ok":
            raise sqlite3.DatabaseError(f"quick_check failed: {row}")
    except sqlite3.DatabaseError:
        ts = int(time.time())
        bad = f"bot_corrupt_{ts}.db"
        try:
            os.replace(DB_PATH, bad)
        except Exception:
            pass

async def db_init():
    await db_healthcheck_and_fix()
    async with await db_connect() as db:
        # user settings
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            target TEXT DEFAULT 'me',
            comment TEXT DEFAULT NULL,
            selected_gift_id INTEGER DEFAULT NULL,
            hide_name INTEGER DEFAULT 0
        )
        """)
        # orders
        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            gift_id INTEGER NOT NULL,
            stars INTEGER NOT NULL,
            comment TEXT DEFAULT NULL,
            hide_name INTEGER DEFAULT 0,

            currency_type TEXT NOT NULL,
            asset TEXT DEFAULT NULL,
            fiat TEXT DEFAULT NULL,
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
        current = int(row[0] or 0) if row else 0
        new_val = 0 if current == 1 else 1
        await db.execute("UPDATE user_settings SET hide_name=? WHERE user_id=?", (new_val, user_id))
        await db.commit()
        return new_val

async def db_create_order(
    tg_user_id: int,
    target: str,
    gift: GiftItem,
    comment: Optional[str],
    hide_name: int,
    currency_type: str,
    asset: Optional[str],
    fiat: Optional[str],
    amount: str,
) -> int:
    now = int(time.time())
    async with await db_connect() as db:
        cur = await db.execute("""
            INSERT INTO orders (
                tg_user_id, target, gift_id, stars, comment, hide_name,
                currency_type, asset, fiat, amount,
                status, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?, 'created', ?, ?)
        """, (tg_user_id, target, gift.id, gift.stars, comment, hide_name, currency_type, asset, fiat, amount, now, now))
        await db.commit()
        return cur.lastrowid

async def db_set_invoice(order_id: int, invoice_id: int, invoice_url: str):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET invoice_id=?, invoice_url=?, status='invoice_active', updated_at=?
            WHERE order_id=?
        """, (invoice_id, invoice_url, now, order_id))
        await db.commit()

async def db_mark_paid(order_id: int):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='paid', updated_at=?
            WHERE order_id=? AND status='invoice_active'
        """, (now, order_id))
        await db.commit()

async def db_mark_sending(order_id: int):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='sending', updated_at=?
            WHERE order_id=? AND status IN ('paid','invoice_active')
        """, (now, order_id))
        await db.commit()

async def db_mark_sent(order_id: int, comment_attached: Optional[bool]):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='sent', comment_attached=?, updated_at=?
            WHERE order_id=?
        """, (None if comment_attached is None else (1 if comment_attached else 0), now, order_id))
        await db.commit()

async def db_mark_failed(order_id: int, error: str):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='failed', error=?, updated_at=?
            WHERE order_id=?
        """, (error[:500], now, order_id))
        await db.commit()

async def db_mark_expired(order_id: int):
    now = int(time.time())
    async with await db_connect() as db:
        await db.execute("""
            UPDATE orders
            SET status='expired', updated_at=?
            WHERE order_id=? AND status='invoice_active'
        """, (now, order_id))
        await db.commit()

async def db_get_active_orders(limit: int = 50):
    async with await db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, tg_user_id, target, gift_id, stars, comment, hide_name,
                   currency_type, asset, fiat, amount,
                   invoice_id, invoice_url, status
            FROM orders
            WHERE status IN ('invoice_active','paid')
            ORDER BY updated_at ASC
            LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return rows

async def db_get_order(order_id: int):
    async with await db_connect() as db:
        cur = await db.execute("""
            SELECT order_id, tg_user_id, target, gift_id, stars, comment, hide_name,
                   currency_type, asset, fiat, amount,
                   invoice_id, invoice_url, status, comment_attached, error
            FROM orders WHERE order_id=?
        """, (order_id,))
        return await cur.fetchone()


# ===================== Crypto Pay Client =====================
class CryptoPayClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/") + "/api"
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _call(self, method: str, params: Optional[dict] = None) -> dict:
        if self._session is None:
            await self.start()
        url = f"{self.base_url}/{method}"
        headers = {"Crypto-Pay-API-Token": self.token}  # :contentReference[oaicite:6]{index=6}
        async with self._session.post(url, json=params or {}, headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as r:
            data = await r.json(content_type=None)
            if not data.get("ok"):
                raise RuntimeError(f"CryptoPay error: {data.get('error')}")
            return data["result"]

    async def create_invoice(self, **kwargs) -> dict:
        # createInvoice :contentReference[oaicite:7]{index=7}
        return await self._call("createInvoice", kwargs)

    async def get_invoices(self, **kwargs) -> dict:
        # getInvoices :contentReference[oaicite:8]{index=8}
        return await self._call("getInvoices", kwargs)


cryptopay = CryptoPayClient(CRYPTOPAY_BASE_URL, CRYPTOPAY_TOKEN)


# ===================== Relayer (Telethon) =====================
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
            raise RuntimeError("RELAYER_SESSION invalid. QR bilan qayta session oling.")
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
        """Invoice yaratishdan oldin kamida entity + canSend check."""
        async with self._lock:
            # can send?
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")
            # resolve
            try:
                _ = await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError(
                        "❌ user_id orqali entity topilmadi.\n"
                        "✅ @username ishlating yoki qabul qiluvchi relayerga 1 marta yozsin."
                    )
                raise

    async def send_gift(
        self,
        target: Union[str, int],
        gift: GiftItem,
        comment: Optional[str] = None,
        hide_name: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Returns: (comment_attached, warning_text)
        hide_name: True bo'lsa sender name profil ko'rsatishda yashiriladi (receiver baribir biladi) :contentReference[oaicite:9]{index=9}
        """
        async with self._lock:
            # can send?
            can = await self.client(functions.payments.CheckCanSendGiftRequest(gift_id=gift.id))
            if isinstance(can, types.payments.CheckCanSendGiftResultFail):
                reason = getattr(can.reason, "text", None) or str(can.reason)
                raise RuntimeError(f"Can't send gift: {reason}")

            # resolve entity
            try:
                peer = await self.client.get_input_entity(target)
            except Exception:
                if isinstance(target, int):
                    raise RuntimeError(
                        "❌ user_id orqali entity topilmadi.\n"
                        "✅ @username ishlating yoki qabul qiluvchi relayerga 1 marta yozsin."
                    )
                raise

            txt = self._clean_comment(comment)
            msg_obj = None if not txt else types.TextWithEntities(text=txt, entities=[])

            extra = {}
            # IMPORTANT: hide_name faqat True bo'lsa uzatamiz
            if hide_name:
                extra["hide_name"] = True

            async def _try_send(message_obj):
                invoice = types.InputInvoiceStarGift(
                    peer=peer,
                    gift_id=gift.id,
                    message=message_obj,
                    **extra
                )
                form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
                await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            if msg_obj is None:
                await _try_send(None)
                return (False, None)

            try:
                await _try_send(msg_obj)
                return (True, None)
            except RPCError as e:
                # Comment invalid bo'lsa: giftni comment'siz yuboramiz, lekin ogohlantiramiz
                if "STARGIFT_MESSAGE_INVALID" in str(e):
                    await _try_send(None)
                    return (False, "⚠️ Komment Telegram tomonidan qabul qilinmadi (STARGIFT_MESSAGE_INVALID). Gift kommentsiz yuborildi.")
                raise


# ===================== Bot UI =====================
def main_menu_kb(hide_name: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Qabul qiluvchi", callback_data="menu:target")
    kb.button(text="💬 Komment", callback_data="menu:comment")
    kb.button(text="🎁 Sovg'a tanlash", callback_data="menu:gift")
    kb.button(
        text=("🕵️ Hide name: ON" if hide_name == 1 else "👤 Hide name: OFF"),
        callback_data="toggle:hide"
    )
    kb.button(text="💳 CryptoBot invoice", callback_data="pay:create")
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
    kb.button(text="🔄 To'lovni tekshirish", callback_data=f"pay:check:{order_id}")
    kb.button(text="⬅️ Menu", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


# ===================== States =====================
class Form(StatesGroup):
    waiting_target = State()
    waiting_comment = State()


def normalize_target(text: str) -> Union[str, int]:
    t = (text or "").strip()
    if not t:
        return "me"
    if t.lower() == "me":
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

async def render_status(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    target, comment, sel_gift_id, hide_name = await db_get_settings(user_id)

    gift_txt = "Tanlanmagan"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        gift_txt = f"{g.label} (⭐{g.stars}) — {g.id}"

    comment_txt = comment if comment else "(yo‘q)"
    mode_txt = "Hide name: ON (faqat profil display uchun)" if hide_name == 1 else "Hide name: OFF"

    # price preview
    price_preview = "-"
    if sel_gift_id and sel_gift_id in GIFTS_BY_ID:
        g = GIFTS_BY_ID[sel_gift_id]
        price_preview = calc_price_amount(g.stars)

    text = (
        "📌 Hozirgi sozlamalar:\n"
        f"🎯 Qabul qiluvchi: {target}\n"
        f"💬 Komment: {comment_txt}\n"
        f"🎁 Sovg‘a: {gift_txt}\n"
        f"🔒 Rejim: {mode_txt}\n"
        f"💵 Narx (taxmin): {price_preview} {('USD' if CRYPTOPAY_CURRENCY_TYPE=='fiat' else CRYPTOPAY_ASSET)}\n\n"
        "Quyidan tanlang:"
    )
    return text, main_menu_kb(hide_name)


# ===================== App =====================
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
relayer = Relayer()


async def create_invoice_for_order(order_id: int, gift: GiftItem) -> dict:
    amount = calc_price_amount(gift.stars)
    payload = f"order:{order_id}"

    if CRYPTOPAY_CURRENCY_TYPE == "fiat":
        # createInvoice supports fiat + accepted_assets :contentReference[oaicite:10]{index=10}
        inv = await cryptopay.create_invoice(
            currency_type="fiat",
            fiat=CRYPTOPAY_FIAT,
            amount=amount,
            accepted_assets=CRYPTOPAY_ACCEPTED_ASSETS,
            description=f"Telegram Gift {gift.label} (⭐{gift.stars})",
            payload=payload,
            expires_in=INVOICE_EXPIRES_IN,
        )
    else:
        inv = await cryptopay.create_invoice(
            currency_type="crypto",
            asset=CRYPTOPAY_ASSET,
            amount=amount,
            description=f"Telegram Gift {gift.label} (⭐{gift.stars})",
            payload=payload,
            expires_in=INVOICE_EXPIRES_IN,
        )

    # pay_url deprecated -> bot_invoice_url :contentReference[oaicite:11]{index=11}
    invoice_id = int(inv["invoice_id"])
    invoice_url = inv.get("bot_invoice_url") or inv.get("pay_url")
    if not invoice_url:
        raise RuntimeError("Invoice URL topilmadi (bot_invoice_url yo'q).")
    return {"invoice_id": invoice_id, "invoice_url": invoice_url}


async def invoice_watcher():
    """Background task: active invoice'larni tekshiradi, paid bo'lsa gift yuboradi."""
    while True:
        try:
            rows = await db_get_active_orders(limit=100)
            # faqat invoice_active larni tekshiramiz
            active = [r for r in rows if r[13] == "invoice_active" and r[11] is not None]
            if active:
                invoice_ids = ",".join(str(r[11]) for r in active)
                res = await cryptopay.get_invoices(invoice_ids=invoice_ids, status="paid")  # :contentReference[oaicite:12]{index=12}
                paid_list = res.get("items", []) if isinstance(res, dict) else res  # ba'zi wrapperlarda dict bo'ladi
                paid_ids = {int(x["invoice_id"]) for x in paid_list}

                for r in active:
                    order_id, tg_user_id, target_str, gift_id, stars, comment, hide_name, *_rest, inv_id, inv_url, status = r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7:], r[11], r[12], r[13]
                    if inv_id and int(inv_id) in paid_ids:
                        await db_mark_paid(order_id)
                        # gift send
                        try:
                            await db_mark_sending(order_id)

                            gift = GIFTS_BY_ID.get(int(gift_id))
                            if not gift:
                                raise RuntimeError("Gift ID DBda bor, lekin catalogda topilmadi.")

                            # target parse
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

                            # notify buyer
                            msg = (
                                "✅ To'lov qabul qilindi va gift yuborildi!\n"
                                f"🎁 {gift.label} (⭐{gift.stars})\n"
                                f"🎯 Target: {target_str}\n"
                            )
                            if warn:
                                msg += f"\n{warn}"
                            await bot.send_message(tg_user_id, msg)

                        except Exception as e:
                            await db_mark_failed(order_id, str(e))
                            await bot.send_message(tg_user_id, f"❌ To'lov bor, lekin gift yuborishda xato:\n{e}")
                            if ADMIN_CHAT_ID:
                                try:
                                    await bot.send_message(ADMIN_CHAT_ID, f"⚠️ ORDER FAILED #{order_id}\n{e}")
                                except Exception:
                                    pass

        except Exception as e:
            # watcher crash bo'lmasin
            if ADMIN_CHAT_ID:
                try:
                    await bot.send_message(ADMIN_CHAT_ID, f"Watcher error: {e}")
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
    new_val = await db_toggle_hide_name(c.from_user.id)
    text, kb = await render_status(c.from_user.id)
    await c.message.edit_text(
        ("✅ Hide name: ON" if new_val == 1 else "✅ Hide name: OFF") + "\n\n" + text,
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await db_ensure_user(c.from_user.id)

    action = c.data.split(":", 1)[1]

    if action == "home":
        await state.clear()
        text, kb = await render_status(c.from_user.id)
        await c.message.edit_text(text, reply_markup=kb)
        return

    if action == "target":
        await state.set_state(Form.waiting_target)
        await c.message.edit_text(
            "🎯 Qabul qiluvchini yuboring:\n"
            "- `me`\n"
            "- `@username`\n"
            "- `user_id` (raqam)\n\n"
            "⚠️ user_id ko'p holatda ishlamaydi (access_hash kerak). Username eng yaxshi.",
            reply_markup=back_menu_kb()
        )
        return

    if action == "comment":
        await state.set_state(Form.waiting_comment)
        await c.message.edit_text(
            "💬 Komment yuboring (ixtiyoriy).\n"
            "O‘chirish uchun: `-` yuboring.\n"
            "Masalan: `:)` yoki `Congrats bro 🎁`\n\n"
            "⚠️ Ba'zi userlarga gift comment qabul qilinmasligi mumkin — shunda gift kommentsiz ketadi.",
            reply_markup=back_menu_kb()
        )
        return

    if action == "gift":
        await state.clear()
        await c.message.edit_text("🎁 Sovg‘a narxini tanlang:", reply_markup=price_kb())
        return


@dp.message(Form.waiting_target)
async def set_target(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    target_norm = normalize_target(m.text.strip())
    await db_set_target(m.from_user.id, str(target_norm))
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer("✅ Qabul qiluvchi saqlandi.\n\n" + text, reply_markup=kb)


@dp.message(Form.waiting_comment)
async def set_comment(m: Message, state: FSMContext):
    await db_ensure_user(m.from_user.id)
    raw = (m.text or "").strip()
    if raw == "-" or raw.lower() == "off":
        await db_set_comment(m.from_user.id, None)
        await state.clear()
        text, kb = await render_status(m.from_user.id)
        return await m.answer("✅ Komment o‘chirildi.\n\n" + text, reply_markup=kb)

    comment = safe_comment(raw)
    await db_set_comment(m.from_user.id, comment)
    await state.clear()
    text, kb = await render_status(m.from_user.id)
    await m.answer("✅ Komment saqlandi.\n\n" + text, reply_markup=kb)


@dp.callback_query(F.data.startswith("price:"))
async def choose_price(c: CallbackQuery):
    await c.answer()
    price = int(c.data.split(":", 1)[1])
    if price not in GIFTS_BY_PRICE:
        return await c.message.edit_text("Bunday narx yo‘q.", reply_markup=price_kb())

    await c.message.edit_text(
        f"⭐ {price} bo‘yicha sovg‘a tanlang:",
        reply_markup=gifts_by_price_kb(price)
    )


@dp.callback_query(F.data.startswith("gift:"))
async def choose_gift(c: CallbackQuery):
    await c.answer()
    gift_id = int(c.data.split(":", 1)[1])
    if gift_id not in GIFTS_BY_ID:
        return await c.message.edit_text("Gift topilmadi.", reply_markup=price_kb())

    await db_set_selected_gift(c.from_user.id, gift_id)
    g = GIFTS_BY_ID[gift_id]
    text, kb = await render_status(c.from_user.id)
    await c.message.edit_text(
        f"✅ Sovg‘a tanlandi:\n{g.label} (⭐{g.stars})\nID: {g.id}\n\n" + text,
        reply_markup=kb
    )


@dp.callback_query(F.data == "pay:create")
async def pay_create(c: CallbackQuery):
    await c.answer()
    await db_ensure_user(c.from_user.id)

    target_str, comment, sel_gift_id, hide_name = await db_get_settings(c.from_user.id)
    if not sel_gift_id or sel_gift_id not in GIFTS_BY_ID:
        text, kb = await render_status(c.from_user.id)
        return await c.message.edit_text("❌ Avval sovg‘ani tanlang.\n\n" + text, reply_markup=kb)

    gift = GIFTS_BY_ID[sel_gift_id]

    # target parse
    t = (target_str or "me").strip()
    if t.lower() == "me":
        target: Union[str, int] = "me"
    elif t.startswith("@"):
        target = t
    elif t.isdigit():
        target = int(t)
    else:
        target = "@" + t

    # preflight (entity + canSend)
    try:
        await relayer.preflight(target=target, gift=gift)
    except Exception as e:
        text, kb = await render_status(c.from_user.id)
        return await c.message.edit_text(f"❌ Preflight xato:\n{e}\n\n" + text, reply_markup=kb)

    amount = calc_price_amount(gift.stars)

    # create order in DB
    if CRYPTOPAY_CURRENCY_TYPE == "fiat":
        currency_type = "fiat"
        asset = None
        fiat = CRYPTOPAY_FIAT
    else:
        currency_type = "crypto"
        asset = CRYPTOPAY_ASSET
        fiat = None

    order_id = await db_create_order(
        tg_user_id=c.from_user.id,
        target=target_str,
        gift=gift,
        comment=comment,
        hide_name=hide_name,
        currency_type=currency_type,
        asset=asset,
        fiat=fiat,
        amount=amount,
    )

    await c.message.edit_text("⏳ Invoice yaratyapman...", reply_markup=None)

    try:
        inv = await create_invoice_for_order(order_id, gift)
        await db_set_invoice(order_id, inv["invoice_id"], inv["invoice_url"])

        await c.message.edit_text(
            "💳 CryptoBot invoice tayyor!\n\n"
            f"🧾 Order: #{order_id}\n"
            f"🎁 Gift: {gift.label} (⭐{gift.stars})\n"
            f"🎯 Target: {target_str}\n"
            f"💬 Comment: {(comment if comment else '(bo‘sh)')}\n"
            f"🔒 Hide name: {'ON' if hide_name==1 else 'OFF'}\n"
            f"💰 Amount: {amount} {('USD' if currency_type=='fiat' else CRYPTOPAY_ASSET)}\n\n"
            "To‘lov bo‘lsa avtomatik yuboriladi ✅",
            reply_markup=invoice_kb(inv["invoice_url"], order_id)
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

    (_oid, tg_user_id, target_str, gift_id, stars, comment, hide_name,
     currency_type, asset, fiat, amount, invoice_id, invoice_url, status, comment_attached, error) = row

    if tg_user_id != c.from_user.id:
        return await c.message.answer("❌ Bu order sizniki emas.")

    if not invoice_id:
        return await c.message.edit_text("❌ Invoice yo‘q.")

    try:
        res = await cryptopay.get_invoices(invoice_ids=str(invoice_id))
        items = res.get("items", []) if isinstance(res, dict) else res
        inv = items[0] if items else None
        if not inv:
            return await c.message.edit_text("Invoice topilmadi.")
        st = inv.get("status")
        if st == "paid":
            await db_mark_paid(order_id)
            return await c.message.edit_text("✅ Paid! Gift avtomatik yuboriladi (bir necha soniya).")
        elif st == "active":
            return await c.message.edit_text("⏳ Hali paid emas. To‘lab bo‘lgach yana check bosing.", reply_markup=invoice_kb(invoice_url, order_id))
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

    watcher_task = asyncio.create_task(invoice_watcher())

    try:
        await dp.start_polling(bot)
    finally:
        watcher_task.cancel()
        try:
            await watcher_task
        except Exception:
            pass
        await relayer.stop()
        await cryptopay.close()

if __name__ == "__main__":
    asyncio.run(main())
