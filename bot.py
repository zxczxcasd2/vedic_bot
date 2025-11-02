# -*- coding: utf-8 -*-
"""
Vedic Astrology Bot — GPT + Stars + CryptoBot, USD wallet + Credits + Subscriptions

- Подписки: Lite ($3/5 cr), Pro ($7/12 cr), VIP ($15/30 cr), срок 30 дней, «ленивое» начисление.
- Оплата: CryptoBot (USDT) и Telegram Stars (XTR).
- One-message UI: главное сообщение редактируется, старые /start удаляются.
- Языки: English / Hindi / Hinglish.
- Бесплатный мини-ридинг: 24ч кулдаун (админ — без лимита), задержка 5–7 минут.
- Платный ридинг: теперь стоит *1 кредит*, задержка 5–7 минут, 350–450 слов; в истории появляется только после готовности.
- Баланс USD + кредиты. Пакеты кредитов. Stars→USD топ-апы.
- Убрана кнопка «Cancel payment» в меню пополнения.
"""

import os, sys, asyncio, aiosqlite, datetime as dt, random, json, re, math
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, List

# Windows event loop policy (обязательно на Windows)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from openai import OpenAI
import aiohttp

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, PreCheckoutQueryHandler
)

# ==== ENV ====
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CRYPTOPAY_TOKEN = os.getenv("CRYPTOPAY_TOKEN", "")
STAR_TO_USD = float(os.getenv("STAR_TO_USD", "0.02"))  # 1⭐ = $0.02
try:
    ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "0"))
except:
    ADMIN_ID = 0

if not BOT_TOKEN: print("ERROR: BOT_TOKEN missing"); sys.exit(1)
if not OPENAI_API_KEY: print("ERROR: OPENAI_API_KEY missing"); sys.exit(1)

# ==== OpenAI ====
oai = OpenAI(api_key=OPENAI_API_KEY)
OPENAI_MODEL = "gpt-4o-mini"

# ==== DB / consts ====
DB_PATH = "vedic_astrology.db"
FREE_COOLDOWN_SEC = 24 * 3600  # 24 часа

ADV_PRICE_USD = 1.00  # оставили для совместимости (в продаже пакетов)
PACKAGES = {1:1.0, 3:2.0, 5:3.5, 10:7.0}

TOPUP_USD_PRESETS = [5.0, 10.0, 20.0]
TOPUP_STARS_OPTIONS = [50, 100, 150, 300, 500]

SUB_TIERS = {
    "lite": {"price": 3.0,  "credits_monthly": 5,  "label": {"en":"Lite","hi":"Lite","hing":"Lite"}},
    "pro":  {"price": 7.0,  "credits_monthly": 12, "label": {"en":"Pro","hi":"Pro","hing":"Pro"}},
    "vip":  {"price": 15.0, "credits_monthly": 30, "label": {"en":"VIP","hi":"VIP","hing":"VIP"}},
}

# ==== one-message state ====
@dataclass
class UserState:
    lang: str = "en"
    main_msg_id: Optional[int] = None

# ==== I18N ====
I18N = {
    "en": {
        "choose_lang": "Choose your language:",
        "langs": {"en":"English", "hi":"Hindi", "hing":"Hinglish"},
        "title": "✨ Welcome to *Vedic Astrology*!",
        "menu": "Main menu",
        "free_ready": "🆓 Free reading: *available now*",
        "free_in": "🆓 Free reading in: *{h}h {m}m*",
        "pick_astro": "Pick a virtual astrologer:",
        "back_to_list": "⬅️ Back to astrologers",
        "get_free": "🔮 Free mini reading",
        "free_limit": "You can get one free mini reading every 24 hours.",
        "start_form": "Let's personalize your mini reading.\n\nWhat is your name?",
        "ask_dob": "Great, now send your date of birth (DD.MM.YYYY or with time e.g. 15.09.1997 14:30).",
        "ask_goal_every": "What is your *question/focus for this reading*?\n(Examples: career change, relationship clarity, finances, health… You can type your own.)",
        "ask_goal_bad": "That doesn't look like a clear topic. Send a real focus (2–60 characters).",
        "working": "Generating your reading… This may take 5–60 minutes.",
        "too_early": "You already used your free reading. Please come back after {hours_left} hours.",
        "done": "Here is your mini reading from {astro}:",
        "invalid_input": "Please send text for this step.",
        "home": "🏠 Home",
        "history": "📜 History",
        "settings": "⚙️ Settings",
        "no_history": "History is empty yet.",
        "settings_title": "*Profile settings*",
        "settings_view": "Saved profile:\n• Name: {name}\n• DOB: {dob}",
        "edit_name": "✏️ Edit name",
        "edit_dob": "📅 Edit date of birth",
        "send_new_name": "Send your new *name*:",
        "send_new_dob": "Send your new *date of birth* (DD.MM.YYYY or with time):",
        "saved": "Saved ✔️",
        "paid_working": "🧿 Preparing your advanced reading… This may take 5–60 minutes.",
        "paid_ready": "✨ Your Advanced Reading:",
        # wallet / credits
        "credits_line": "🎟 *Credits:* {credits}",
        "wallet": "💼 *USD balance:* ${amount:.2f}\n🎟 Credits: {credits}",
        "wallet_topup": "Choose a top-up method:",
        "wallet_topup_usd": "Select amount to add via CryptoBot:",
        "wallet_topup_stars": "Select Stars package to convert to USD:",
        "wallet_btn": "💼 Wallet",
        "wallet_topup_btn": "➕ Top up",
        "back_btn": "⬅️ Back",
        # astro / purchase
        "buy_advanced": "✨ Advanced reading — *1 credit*",
        "need_credit_title": "You need *1 credit* for an Advanced reading.",
        "go_buy_credits": "🛒 Buy credits",
        "cryptobot_invoice": "Pay with *CryptoBot (USDT)*. After payment, press *I paid — Check*.",
        "cryptobot_paid_check": "✅ I paid — Check",
        "cryptobot_cancel": "✖ Cancel",
        "cryptobot_paid_wait": "Payment not found yet. Try again in a few seconds.",
        "insufficient_balance": "Your balance is ${bal:.2f}. You need ${need:.2f}.",
        # credits
        "buy_packs_btn": "🛒 Buy credits",
        "packs_title": "Choose a credits package:",
        "pack_row": "• {n} credits — ${price:.2f}",
        "pay_method_crypto_pack": "₿ Pay via CryptoBot",
        "pay_method_stars_pack": "⭐ Pay via Stars",
        "pay_method_from_balance_pack": "💳 Pay from balance",
        # topup custom usd
        "enter_custom_amount": "Enter the USD amount you want to top up (e.g., 7.5).",
        "invalid_amount": "Invalid amount. Please send a number between 1 and 1000.",
        "custom_usd_topup_title": "Top-up via CryptoBot",
        # history
        "hist_title": "*Your readings history*",
        "hist_item": "— _{date}_ • *{kind}* by {astro}\n{snippet}",
        "prev": "⬅️ Prev",
        "next": "Next ➡️",
        # subscriptions
        "subscribe_btn": "✨ Subscribe",
        "subs_title": "*Subscriptions* — automatic credits every month:",
        "subs_row": "• {name}: ${price:.2f}/mo → {cr} credits/month",
        "subs_manage_active": "Your subscription: *{name}* until {date}. You receive {cr}/month.",
        "subs_expired": "No active subscription.",
        "subs_choose_pay": "Choose how to pay for {name} (${price:.2f}/mo):",
        "subs_pay_crypto": "₿ Pay via CryptoBot",
        "subs_pay_stars": "⭐ Pay via Stars",
        "subs_cancel_back": "⬅️ Back",
        "subs_granted": "✅ Subscription activated: {name}. +{cr} credits added.",
    },
    "hi": {
        "choose_lang": "अपनी भाषा चुनें:",
        "langs": {"en":"English", "hi":"हिन्दी", "hing":"Hinglish"},
        "title": "✨ *वैदिक ज्योतिष* में आपका स्वागत है!",
        "menu": "मुख्य मेनू",
        "free_ready": "🆓 फ्री रीडिंग: *उपलब्ध*",
        "free_in": "🆓 फ्री रीडिंग तक: *{h}घं {m}मि*",
        "pick_astro": "अपना वर्चुअल ज्योतिषी चुनें:",
        "back_to_list": "⬅️ ज्योतिषियों की सूची",
        "get_free": "🔮 फ्री मिनी रीडिंग",
        "free_limit": "हर 24 घंटे में एक फ्री मिनी रीडिंग उपलब्ध है।",
        "start_form": "आइए रीडिंग को पर्सनलाइज़ करें।\n\nआपका नाम?",
        "ask_dob": "ठीक है, अब जन्मतिथि भेजें (DD.MM.YYYY या समय सहित जैसे 15.09.1997 14:30)।",
        "ask_goal_every": "इस रीडिंग का आपका *प्रश्न/फोकस* क्या है?\n(उदाहरण: करियर, रिलेशनशिप, फाइनेंसेज़, हेल्थ… अपना भी लिख सकते हैं।)",
        "ask_goal_bad": "यह स्पष्ट विषय नहीं लगता। 2–60 अक्षरों में सही फोकस भेजें।",
        "working": "रीडिंग तैयार हो रही है… इसमें 5–60 मिनट लग सकते हैं।",
        "too_early": "आज की फ्री रीडिंग ले ली है। कृपया {hours_left} घंटे बाद आएँ।",
        "done": "{astro} की मिनी रीडिंग प्रस्तुत है:",
        "invalid_input": "कृपया यहाँ टेक्स्ट भेजें।",
        "home": "🏠 होम",
        "history": "📜 इतिहास",
        "settings": "⚙️ सेटिंग्स",
        "no_history": "इतिहास अभी खाली है।",
        "settings_title": "*प्रोफ़ाइल सेटिंग्स*",
        "settings_view": "सेव्ड प्रोफ़ाइल:\n• नाम: {name}\n• DOB: {dob}",
        "edit_name": "✏️ नाम बदलें",
        "edit_dob": "📅 जन्मतिथि बदलें",
        "send_new_name": "अपना नया *नाम* भेजें:",
        "send_new_dob": "नई *जन्मतिथि* भेजें (DD.MM.YYYY या समय सहित):",
        "saved": "सेव हो गया ✔️",
        "paid_working": "🧿 आपकी एडवांस्ड रीडिंग तैयार हो रही है… इसमें 5–60 मिनट लग सकते हैं।",
        "paid_ready": "✨ आपकी एडवांस्ड रीडिंग:",
        "credits_line": "🎟 *क्रेडिट्स:* {credits}",
        "wallet": "💼 *USD बैलेंस:* ${amount:.2f}\n🎟 क्रेडिट्स: {credits}",
        "wallet_topup": "टॉप-अप विधि चुनें:",
        "wallet_topup_usd": "CryptoBot से जोड़ने हेतु राशि चुनें:",
        "wallet_topup_stars": "Stars पैक चुनें (USD में कन्वर्ट होगा):",
        "wallet_btn": "💼 वॉलेट",
        "wallet_topup_btn": "➕ टॉप-अप",
        "back_btn": "⬅️ वापस",
        "buy_advanced": "✨ एडवांस्ड रीडिंग — *1 क्रेडिट*",
        "need_credit_title": "एडवांस्ड रीडिंग के लिए *1 क्रेडिट* चाहिए।",
        "go_buy_credits": "🛒 क्रेडिट्स खरीदें",
        "cryptobot_invoice": "*CryptoBot (USDT)* से भुगतान करें। भुगतान के बाद *I paid — Check* दबाएँ।",
        "cryptobot_paid_check": "✅ I paid — Check",
        "cryptobot_cancel": "✖ Cancel",
        "cryptobot_paid_wait": "भुगतान नहीं मिला। कुछ सेकेंड बाद पुनः जाँचें।",
        "insufficient_balance": "आपका बैलेंस ${bal:.2f} है। ज़रूरत: ${need:.2f}.",
        "buy_packs_btn": "🛒 क्रेडिट्स खरीदें",
        "packs_title": "क्रेडिट्स पैक चुनें:",
        "pack_row": "• {n} क्रेडिट्स — ${price:.2f}",
        "pay_method_crypto_pack": "₿ CryptoBot से भुगतान",
        "pay_method_stars_pack": "⭐ Stars से भुगतान",
        "pay_method_from_balance_pack": "💳 बैलेंस से भुगतान",
        "enter_custom_amount": "USD राशि लिखें (जैसे 7.5).",
        "invalid_amount": "अमान्य राशि। 1–1000 के बीच संख्या भेजें।",
        "custom_usd_topup_title": "CryptoBot से टॉप-अप",
        "hist_title": "*आपकी रीडिंग्स का इतिहास*",
        "hist_item": "— _{date}_ • *{kind}* — {astro}\n{snippet}",
        "prev": "⬅️ पिछला",
        "next": "अगला ➡️",
        "subscribe_btn": "✨ Subscribe",
        "subs_title": "*Subscriptions* — हर महीने ऑटो क्रेडिट:",
        "subs_row": "• {name}: ${price:.2f}/माह → {cr} क्रेडिट/माह",
        "subs_manage_active": "आपकी सदस्यता: *{name}* {date} तक। {cr}/माह मिलते हैं।",
        "subs_expired": "कोई सक्रिय सदस्यता नहीं।",
        "subs_choose_pay": "{name} (${price:.2f}/माह) का भुगतान कैसे करें चुनें:",
        "subs_pay_crypto": "₿ CryptoBot",
        "subs_pay_stars": "⭐ Stars",
        "subs_cancel_back": "⬅️ वापस",
        "subs_granted": "✅ सदस्यता सक्रिय: {name}. +{cr} क्रेडिट जोड़े गए।",
    },
    "hing": {
        "choose_lang": "Apni language choose karo:",
        "langs": {"en":"English", "hi":"हिन्दी", "hing":"Hinglish"},
        "title": "✨ Welcome to *Vedic Astrology*!",
        "menu": "Main menu",
        "free_ready": "🆓 Free reading: *available now*",
        "free_in": "🆓 Free reading in: *{h}h {m}m*",
        "pick_astro": "Apna virtual astrologer choose karo:",
        "back_to_list": "⬅️ Astrologers list",
        "get_free": "🔮 Free mini reading",
        "free_limit": "Har 24 ghante me ek free mini reading milti hai.",
        "start_form": "Chalo reading ko personalize karein.\n\nTumhara naam?",
        "ask_dob": "Ab apni date of birth bhejo (DD.MM.YYYY ya time, e.g., 15.09.1997 14:30).",
        "ask_goal_every": "Is reading ka tumhara *question/focus* kya hai?\n(Examples: career, relationship, finances, health… apna bhi likho.)",
        "ask_goal_bad": "Topic clear nahi lag raha. 2–60 characters me ek sahi focus bhejo.",
        "working": "Reading taiyaar ho rahi hai… Isme 5–60 minutes lag sakte hain.",
        "too_early": "Aaj ka free reading use ho chuka. {hours_left} ghante baad aao.",
        "done": "{astro} se tumhari mini reading:",
        "invalid_input": "Is step ke liye text bhejo.",
        "home": "🏠 Home",
        "history": "📜 History",
        "settings": "⚙️ Settings",
        "no_history": "History abhi khaali hai.",
        "settings_title": "*Profile settings*",
        "settings_view": "Saved profile:\n• Name: {name}\n• DOB: {dob}",
        "edit_name": "✏️ Edit name",
        "edit_dob": "📅 Edit DOB",
        "send_new_name": "Apna naya *name* bhejo:",
        "send_new_dob": "Nayi *DOB* bhejo (DD.MM.YYYY ya time):",
        "saved": "Saved ✔️",
        "paid_working": "🧿 Advanced reading taiyaar ho rahi hai… Isme 5–60 minutes lag sakte hain.",
        "paid_ready": "✨ Tumhari Advanced Reading:",
        "credits_line": "🎟 *Credits:* {credits}",
        "wallet": "💼 *USD balance:* ${amount:.2f}\n🎟 Credits: {credits}",
        "wallet_topup": "Top-up method choose karo:",
        "wallet_topup_usd": "CryptoBot se add karne ke liye amount select karo:",
        "wallet_topup_stars": "Stars package choose karo (USD me convert hoga):",
        "wallet_btn": "💼 Wallet",
        "wallet_topup_btn": "➕ Top up",
        "back_btn": "⬅️ Back",
        "buy_advanced": "✨ Advanced reading — *1 credit*",
        "need_credit_title": "Advanced reading ke liye *1 credit* chahiye.",
        "go_buy_credits": "🛒 Credits kharido",
        "cryptobot_invoice": "*CryptoBot (USDT)* se pay karo. Payment ke baad *I paid — Check* dabao.",
        "cryptobot_paid_check": "✅ I paid — Check",
        "cryptobot_cancel": "✖ Cancel",
        "cryptobot_paid_wait": "Payment mila nahi. Thodi der baad check karo.",
        "insufficient_balance": "Balance ${bal:.2f} hai. Chahiye ${need:.2f}.",
        "buy_packs_btn": "🛒 Credits kharido",
        "packs_title": "Credits package choose karo:",
        "pack_row": "• {n} credits — ${price:.2f}",
        "pay_method_crypto_pack": "₿ CryptoBot",
        "pay_method_stars_pack": "⭐ Stars",
        "pay_method_from_balance_pack": "💳 Balance",
        "enter_custom_amount": "USD amount likho (e.g., 7.5).",
        "invalid_amount": "Galat amount. 1–1000 ke beech number bhejo.",
        "custom_usd_topup_title": "CryptoBot Top-up",
        "hist_title": "*Tumhari readings history*",
        "hist_item": "— _{date}_ • *{kind}* — {astro}\n{snippet}",
        "prev": "⬅️ Prev",
        "next": "Next ➡️",
        "subscribe_btn": "✨ Subscribe",
        "subs_title": "*Subscriptions* — mahine ke hisaab se auto credits:",
        "subs_row": "• {name}: ${price:.2f}/mo → {cr} credits/month",
        "subs_manage_active": "Tumhari subscription: *{name}* {date} tak. {cr}/month milta hai.",
        "subs_expired": "No active subscription.",
        "subs_choose_pay": "{name} (${price:.2f}/mo) pay kaise karna hai:",
        "subs_pay_crypto": "₿ CryptoBot",
        "subs_pay_stars": "⭐ Stars",
        "subs_cancel_back": "⬅️ Back",
        "subs_granted": "✅ Subscription active: {name}. +{cr} credits added.",
    }
}

# ==== Astrologers ====
ASTROS = {
    "priya": {
        "label":{"en":"Priya","hi":"प्रिया","hing":"Priya"},
        "desc":{"en":"Priya focuses on love and relationships. She reads subtle emotional patterns and gives gentle, practical steps to attract harmony and deepen bonds."},
        "img":"images/priya.jpg"
    },
    "rahul": {
        "label":{"en":"Rahul","hi":"राहुल","hing":"Rahul"},
        "desc":{"en":"Rahul guides career direction and life purpose. Expect grounded, motivating advice to sharpen focus and make steady, wise progress."},
        "img":"images/rahul.jpg"
    },
    "arjun": {
        "label":{"en":"Arjun","hi":"अर्जुन","hing":"Arjun"},
        "desc":{"en":"Arjun is about money, discipline and business rhythm. He blends strategy with calm habits so your finances grow with less stress."},
        "img":"images/arjun.jpg"
    },
}

# ==== helpers ====
def is_admin(uid: int) -> bool:
    return ADMIN_ID and uid == ADMIN_ID

def usd_to_stars(usd: float) -> int:
    return max(1, math.ceil(usd / max(STAR_TO_USD, 1e-9)))

def free_status_text(last_free: Optional[dt.datetime], lang: str="en") -> Tuple[str, bool]:
    if not last_free:
        return (I18N[lang]["free_ready"], True)
    left = FREE_COOLDOWN_SEC - (dt.datetime.utcnow()-last_free).total_seconds()
    if left <= 0:
        return (I18N[lang]["free_ready"], True)
    h = int(left // 3600); m = int((left % 3600)//60)
    return (I18N[lang]["free_in"].format(h=h, m=m), False)

def snippet(txt: str, n: int = 180) -> str:
    s = re.sub(r'\s+', ' ', (txt or '')).strip()
    return s[:n] + ("…" if len(s) > n else "")

# ==== keyboards ====
def kb_lang():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("English", callback_data="lang:en"),
        InlineKeyboardButton("हिन्दी", callback_data="lang:hi"),
        InlineKeyboardButton("Hinglish", callback_data="lang:hing"),
    ]])

def kb_main(lang: str, credits: int, free_line: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧙 " + ("Choose astrologer" if lang!="hi" else "ज्योतिषी चुनें"), callback_data="astros:open"),
         InlineKeyboardButton(I18N[lang]["wallet_btn"], callback_data="wallet:open")],
        [InlineKeyboardButton(I18N[lang]["history"], callback_data="history:open"),
         InlineKeyboardButton(I18N[lang]["settings"], callback_data="settings:open")],
        [InlineKeyboardButton(I18N[lang]["buy_packs_btn"], callback_data="packs:open"),
         InlineKeyboardButton(I18N[lang]["subscribe_btn"], callback_data="subs:open")],
    ])

def kb_astros(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(ASTROS["priya"]["label"][lang],  callback_data="astro:priya")],
        [InlineKeyboardButton(ASTROS["rahul"]["label"][lang],  callback_data="astro:rahul")],
        [InlineKeyboardButton(ASTROS["arjun"]["label"][lang],  callback_data="astro:arjun")],
        [InlineKeyboardButton(I18N[lang]["back_to_list"], callback_data="back:menu")],
    ])

def kb_astro_card(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["get_free"], callback_data="free:start")],
        [InlineKeyboardButton(I18N[lang]["buy_advanced"], callback_data="buy:adv")],
        [InlineKeyboardButton(I18N[lang]["back_to_list"], callback_data="astros:open")],
    ])

def kb_only_back(lang: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="back:menu")]])

def kb_wallet(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["wallet_topup_btn"], callback_data="wallet:topup")],
        [InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="back:menu")],
    ])

def kb_wallet_topup_methods(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿ CryptoBot (USDT)", callback_data="wallet:method:cryptobot")],
        [InlineKeyboardButton("⭐ Telegram Stars",     callback_data="wallet:method:stars")],
        [InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="wallet:open")],
    ])

def kb_wallet_topup_usd(lang: str):
    rows = [[InlineKeyboardButton(f"${amt:.2f}", callback_data=f"topup:usd:{amt}")] for amt in TOPUP_USD_PRESETS]
    rows.append([InlineKeyboardButton("✏️ " + ("Enter amount" if lang!="hi" else "राशि लिखें"), callback_data="topup:usd:custom")])
    rows.append([InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="wallet:topup")])
    return InlineKeyboardMarkup(rows)

def kb_wallet_topup_stars(lang: str):
    btns = []
    for s in TOPUP_STARS_OPTIONS:
        usd = s * STAR_TO_USD
        btns.append([InlineKeyboardButton(f"{s}⭐ → ${usd:.2f}", callback_data=f"topup:stars:{s}")])
    btns.append([InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="wallet:topup")])
    return InlineKeyboardMarkup(btns)

def kb_need_credit(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["go_buy_credits"], callback_data="packs:open")],
        [InlineKeyboardButton(I18N[lang]["back_to_list"], callback_data="astros:open")],
    ])

def kb_pay_methods_pack(lang: str, n: int, price_usd: float):
    stars_needed = usd_to_stars(price_usd)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["pay_method_crypto_pack"], callback_data=f"pack:{n}:cryptobot:{price_usd}")],
        [InlineKeyboardButton(I18N[lang]["pay_method_stars_pack"],  callback_data=f"pack:{n}:stars:{stars_needed}")],
        [InlineKeyboardButton(I18N[lang]["pay_method_from_balance_pack"], callback_data=f"pack:{n}:frombalance:{price_usd}")],
        [InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="packs:open")],
    ])

def kb_cryptobot_invoice(lang: str, inv_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["cryptobot_paid_check"], callback_data=f"cryptobot:check:{inv_id}")],
        [InlineKeyboardButton(I18N[lang]["cryptobot_cancel"], callback_data=f"cryptobot:cancel:{inv_id}")],
    ])

def kb_history(lang: str, page: int, has_prev: bool, has_next: bool):
    row = []
    if has_prev: row.append(InlineKeyboardButton(I18N[lang]["prev"], callback_data=f"history:page:{page-1}"))
    if has_next: row.append(InlineKeyboardButton(I18N[lang]["next"], callback_data=f"history:page:{page+1}"))
    rows = [row] if row else []
    rows.append([InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="back:menu")])
    return InlineKeyboardMarkup(rows)

def kb_settings_menu(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["edit_name"], callback_data="settings:edit:name")],
        [InlineKeyboardButton(I18N[lang]["edit_dob"], callback_data="settings:edit:dob")],
        [InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="back:menu")],
    ])

def kb_subs_list(lang: str):
    rows = []
    for key in ("lite","pro","vip"):
        t = SUB_TIERS[key]
        rows.append([InlineKeyboardButton(
            f"{t['label'][lang]} — ${t['price']:.2f} / {t['credits_monthly']} cr",
            callback_data=f"subs:choose:{key}"
        )])
    rows.append([InlineKeyboardButton(I18N[lang]["subs_cancel_back"], callback_data="back:menu")])
    return InlineKeyboardMarkup(rows)

def kb_subs_pay(lang: str, tier: str):
    price = SUB_TIERS[tier]["price"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(I18N[lang]["subs_pay_crypto"], callback_data=f"subs:pay:cryptobot:{tier}")],
        [InlineKeyboardButton(I18N[lang]["subs_pay_stars"],  callback_data=f"subs:pay:stars:{tier}:{usd_to_stars(price)}")],
        [InlineKeyboardButton(I18N[lang]["subs_cancel_back"], callback_data="subs:open")]
    ])

# ==== DB helpers ====
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, lang TEXT, main_msg_id INTEGER, last_free_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS form_state (user_id INTEGER PRIMARY KEY, stage TEXT, astro TEXT, name TEXT, dob TEXT, goal TEXT, goal_session TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_profile (user_id INTEGER PRIMARY KEY, name TEXT, dob TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS forecasts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, astro TEXT, kind TEXT, text TEXT, created_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_wallet_usd (user_id INTEGER PRIMARY KEY, usd_balance REAL DEFAULT 0.0, credits INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS pending_invoices (user_id INTEGER, message_id INTEGER, created_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS cryptobot_invoices (invoice_id TEXT PRIMARY KEY, user_id INTEGER, kind TEXT, amount REAL, meta TEXT, created_at TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS subs (user_id INTEGER PRIMARY KEY, tier TEXT, valid_until TEXT, last_grant_date TEXT)""")
        await db.commit()

async def _column_exists(db, table: str, column: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in await cur.fetchall()]
    return column in cols

async def migrate_db():
    async with aiosqlite.connect(DB_PATH) as db:
        for tbl, col, ddl in [
            ("form_state","goal_session","ALTER TABLE form_state ADD COLUMN goal_session TEXT"),
            ("user_wallet_usd","usd_balance","ALTER TABLE user_wallet_usd ADD COLUMN usd_balance REAL DEFAULT 0.0"),
            ("user_wallet_usd","credits","ALTER TABLE user_wallet_usd ADD COLUMN credits INTEGER DEFAULT 0"),
            ("cryptobot_invoices","meta","ALTER TABLE cryptobot_invoices ADD COLUMN meta TEXT"),
            ("subs","tier","CREATE TABLE IF NOT EXISTS subs (user_id INTEGER PRIMARY KEY, tier TEXT, valid_until TEXT, last_grant_date TEXT)"),
        ]:
            if not await _column_exists(db, tbl, col):
                await db.execute(ddl)
        await db.commit()

# user meta
async def get_user(u_id: int) -> UserState:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT lang, main_msg_id FROM users WHERE user_id=?", (u_id,))
        row = await cur.fetchone()
    return UserState(lang=(row[0] if row else "en"), main_msg_id=(row[1] if row else None))

async def set_user_lang(u_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO users (user_id, lang) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lang=excluded.lang""", (u_id, lang)); await db.commit()

async def set_user_main_msg(u_id: int, mid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET main_msg_id=? WHERE user_id=?", (mid, u_id)); await db.commit()

async def set_last_free(u_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_free_at=? WHERE user_id=?", (dt.datetime.utcnow().isoformat(), u_id)); await db.commit()

async def when_last_free(u_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_free_at FROM users WHERE user_id=?", (u_id,)); row = await cur.fetchone()
    return dt.datetime.fromisoformat(row[0]) if row and row[0] else None

# forms/profile/history
async def save_form(u_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO form_state (user_id) VALUES (?)", (u_id,))
        sets, vals = [], []
        for k, v in kwargs.items(): sets.append(f"{k}=?"); vals.append(v)
        vals.append(u_id)
        await db.execute(f"UPDATE form_state SET {', '.join(sets)} WHERE user_id=?", vals); await db.commit()

async def load_form(u_id: int) -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT stage, astro, name, dob, goal, goal_session FROM form_state WHERE user_id=?", (u_id,)); row = await cur.fetchone()
    return {"stage":row[0] if row else None, "astro":row[1] if row else None, "name":row[2] if row else None, "dob":row[3] if row else None, "goal":row[4] if row else None, "goal_session":row[5] if row else None}

async def reset_form(u_id: int):
    async with aiosqlite.connect(DB_PATH) as db: await db.execute("DELETE FROM form_state WHERE user_id=?", (u_id,)); await db.commit()

async def get_profile(u_id: int) -> Tuple[Optional[str], Optional[str]]:
    async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute("SELECT name, dob FROM user_profile WHERE user_id=?", (u_id,)); row = await cur.fetchone()
    return (row[0], row[1]) if row else (None, None)

async def save_profile(u_id: int, **kwargs):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_profile (user_id) VALUES (?)", (u_id,))
        sets, vals = [], []
        for k, v in kwargs.items(): sets.append(f"{k}=?"); vals.append(v)
        vals.append(u_id); await db.execute(f"UPDATE user_profile SET {', '.join(sets)} WHERE user_id=?", vals); await db.commit()

async def add_forecast(u_id: int, astro: str, text: str, kind: str="free"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO forecasts (user_id, astro, kind, text, created_at) VALUES (?, ?, ?, ?, ?)", (u_id, astro, kind, text, dt.datetime.utcnow().isoformat())); await db.commit()

async def get_history_page(u_id: int, page: int=0, page_size: int=5):
    offset = page * page_size
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT astro, kind, text, created_at FROM forecasts WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?", (u_id, page_size+1, offset))
        rows = await cur.fetchall()
    has_next = len(rows) > page_size; rows = rows[:page_size]; has_prev = page > 0
    return rows, has_prev, has_next

# wallet/credits
async def get_wallet(uid: int) -> Tuple[float, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_wallet_usd (user_id, usd_balance, credits) VALUES (?, 0.0, 0)", (uid,)); await db.commit()
        cur = await db.execute("SELECT usd_balance, credits FROM user_wallet_usd WHERE user_id=?", (uid,))
        row = await cur.fetchone()
    return float(row[0] if row else 0.0), int(row[1] if row else 0)

async def set_min_admin_perks(uid: int):
    if not is_admin(uid): return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_wallet_usd (user_id, usd_balance, credits) VALUES (?, 0.0, 0)", (uid,))
        await db.execute("UPDATE user_wallet_usd SET credits = MAX(credits, 100) WHERE user_id=?", (uid,))
        await db.commit()

async def add_usd(uid: int, delta: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_wallet_usd (user_id, usd_balance, credits) VALUES (?, 0.0, 0)", (uid,))
        await db.execute("UPDATE user_wallet_usd SET usd_balance = usd_balance + ? WHERE user_id=?", (delta, uid)); await db.commit()

async def charge_usd(uid: int, amount: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT usd_balance FROM user_wallet_usd WHERE user_id=?", (uid,))
        row = await cur.fetchone(); bal = float(row[0] if row else 0.0)
        if bal + 1e-9 < amount: return False
        await db.execute("UPDATE user_wallet_usd SET usd_balance = usd_balance - ? WHERE user_id=?", (amount, uid)); await db.commit()
    return True

async def add_credits(uid: int, n: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO user_wallet_usd (user_id, usd_balance, credits) VALUES (?, 0.0, 0)", (uid,))
        await db.execute("UPDATE user_wallet_usd SET credits = credits + ? WHERE user_id=?", (n, uid)); await db.commit()

async def use_credit(uid: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT credits FROM user_wallet_usd WHERE user_id=?", (uid,))
        row = await cur.fetchone(); cr = int(row[0] if row else 0)
        if cr <= 0: return False
        await db.execute("UPDATE user_wallet_usd SET credits = credits - 1 WHERE user_id=?", (uid,)); await db.commit()
    return True

# Stars invoices registry
async def add_invoice_message(u_id: int, mid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO pending_invoices (user_id, message_id, created_at) VALUES (?, ?, ?)", (u_id, mid, dt.datetime.utcnow().isoformat())); await db.commit()

async def pop_all_invoices(u_id: int) -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT message_id FROM pending_invoices WHERE user_id=?", (u_id,)); rows = await cur.fetchall()
        ids = [r[0] for r in rows]; await db.execute("DELETE FROM pending_invoices WHERE user_id=?", (u_id,)); await db.commit()
    return ids

async def close_stars_windows(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int):
    ids = await pop_all_invoices(uid)
    for mid in ids:
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
        except Exception: pass

# ==== one-message helpers ====
async def replace_message_with_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    uid = update.effective_user.id
    state = await get_user(uid); old = state.main_msg_id
    sent = await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    await set_user_main_msg(uid, sent.message_id)
    if old:
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old)
        except (BadRequest, Forbidden): pass

async def replace_message_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_path: str, caption: str, reply_markup=None):
    uid = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    state = await get_user(uid); old = state.main_msg_id
    with open(photo_path, "rb") as f:
        sent = await update.effective_chat.send_photo(photo=f, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    await set_user_main_msg(uid, sent.message_id)
    if old:
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old)
        except (BadRequest, Forbidden): pass

async def edit_main_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    uid = update.effective_user.id
    state = await get_user(uid)
    if not state.main_msg_id:
        await replace_message_with_text(update, context, text, reply_markup); return
    try:
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=state.main_msg_id, text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except BadRequest:
        await replace_message_with_text(update, context, text, reply_markup)

# ==== CryptoBot API ====
API_URL = "https://pay.crypt.bot/api"

async def cryptobot_request(session: aiohttp.ClientSession, method: str, payload: Dict) -> Dict:
    if not CRYPTOPAY_TOKEN:
        raise RuntimeError("CRYPTOPAY_TOKEN is not set")
    headers = {"Crypto-Pay-API-Token": CRYPTOPAY_TOKEN, "Content-Type": "application/json"}
    async with session.post(f"{API_URL}/{method}", headers=headers, data=json.dumps(payload)) as resp:
        data = await resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"CryptoPay error: {data}")
        return data["result"]

async def cryptobot_create_invoice(kind: str, uid: int, amount_usd: float, meta: Dict) -> Tuple[str, str]:
    async with aiohttp.ClientSession() as s:
        result = await cryptobot_request(s, "createInvoice", {
            "asset": "USDT",
            "amount": round(amount_usd, 2),
            "description": f"{kind} for user {uid}",
            "expires_in": 3600,
            "allow_comments": False,
            "allow_anonymous": False,
        })
    invoice_id = str(result["invoice_id"])
    pay_url = result["pay_url"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO cryptobot_invoices (invoice_id, user_id, kind, amount, meta, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (invoice_id, uid, kind, amount_usd, json.dumps(meta), dt.datetime.utcnow().isoformat())
        )
        await db.commit()
    return invoice_id, pay_url

async def cryptobot_check_paid(invoice_id: str) -> Tuple[bool, Dict]:
    async with aiohttp.ClientSession() as s:
        result = await cryptobot_request(s, "getInvoices", {"invoice_ids": [int(invoice_id)]})
    items = result.get("items", [])
    if not items: return False, {}
    paid = items[0].get("status") == "paid"
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT kind, amount, meta FROM cryptobot_invoices WHERE invoice_id=?", (invoice_id,))
        row = await cur.fetchone()
    meta = {"kind": row[0], "amount": row[1], "meta": json.loads(row[2] or "{}")} if row else {}
    return paid, meta

# ==== Subscriptions helpers ====
async def get_sub(uid: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT tier, valid_until, last_grant_date FROM subs WHERE user_id=?", (uid,))
        row = await cur.fetchone()
    if not row: return None
    tier, vu, lg = row
    valid_until = dt.datetime.fromisoformat(vu) if vu else None
    return {"tier": tier, "valid_until": valid_until, "last_grant_date": lg}

async def set_sub(uid: int, tier: str, months: int = 1):
    valid_until = dt.datetime.utcnow() + dt.timedelta(days=30*months)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO subs (user_id, tier, valid_until, last_grant_date) VALUES (?, ?, ?, COALESCE((SELECT last_grant_date FROM subs WHERE user_id=?), NULL))",
            (uid, tier, valid_until.isoformat(), uid)
        )
        await db.commit()

async def grant_monthly_if_due(uid: int):
    sub = await get_sub(uid)
    if not sub: return
    if not sub["valid_until"] or sub["valid_until"] < dt.datetime.utcnow(): return
    tier = sub["tier"]; monthly = SUB_TIERS[tier]["credits_monthly"]
    ym_now = dt.datetime.utcnow().strftime("%Y-%m")
    if sub["last_grant_date"] == ym_now: return
    await add_credits(uid, monthly)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subs SET last_grant_date=? WHERE user_id=?", (ym_now, uid)); await db.commit()

def sub_status_line(lang: str, sub) -> str:
    if not sub or not sub["valid_until"] or sub["valid_until"] < dt.datetime.utcnow():
        return I18N[lang]["subs_expired"]
    tier = sub["tier"]; t = SUB_TIERS[tier]
    return I18N[lang]["subs_manage_active"].format(
        name=t['label'][lang], date=sub["valid_until"].date().isoformat(), cr=t["credits_monthly"]
    )

# ==== handlers ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        if update.message:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except Exception:
        pass

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, lang) VALUES (?, ?)", (uid, "en")); await db.commit()

    await set_min_admin_perks(uid)
    await close_stars_windows(update, context, uid)
    await replace_message_with_text(update, context, f"{I18N['en']['title']}\n\n{I18N['en']['choose_lang']}", kb_lang())

async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str, uid: int):
    await grant_monthly_if_due(uid)
    _, cr = await get_wallet(uid)
    last = await when_last_free(uid)
    free_line, _ = free_status_text(last, lang)
    text = f"*{I18N[lang]['title']}*\n\n{I18N[lang]['menu']}\n\n{I18N[lang]['credits_line'].format(credits=cr)}\n{free_line}"
    await edit_main_text(update, context, text, kb_main(lang, cr, free_line))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; lang = (await get_user(uid)).lang
    await set_min_admin_perks(uid)
    await home_screen(update, context, lang, uid)

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except BadRequest: pass
    uid = q.from_user.id
    lang = (await get_user(uid)).lang
    data = q.data

    # Любая навигация → закрыть окна Stars
    if data.startswith(("lang:", "back:", "astros:open", "astro:", "packs:open", "wallet:open", "history:open", "history:page:", "settings:open", "pack:choose:", "subs:open")):
        await close_stars_windows(update, context, uid)

    # language → главное меню
    if data.startswith("lang:"):
        lang = data.split(":")[1]
        await set_user_lang(uid, lang); await reset_form(uid)
        await set_min_admin_perks(uid)
        await home_screen(update, context, lang, uid); return

    if data == "back:menu":
        await home_screen(update, context, lang, uid); return

    # астрологи
    if data == "astros:open":
        await edit_main_text(update, context, f"*{I18N[lang]['pick_astro']}*\n\n_{I18N[lang]['free_limit']}_", kb_astros(lang)); return

    if data.startswith("astro:"):
        astro = data.split(":")[1]; await save_form(uid, astro=astro)
        caption = f"*{ASTROS[astro]['label'][lang]}*\n\n{ASTROS[astro]['desc']['en']}"
        img = ASTROS[astro]["img"]
        try:
            await replace_message_with_photo(update, context, img, caption, kb_astro_card(lang))
        except Exception:
            await edit_main_text(update, context, caption, kb_astro_card(lang))
        return

    # HISTORY
    if data == "history:open" or data.startswith("history:page:"):
        page = 0
        if data.startswith("history:page:"):
            page = max(0, int(data.split(":")[-1]))
        rows, has_prev, has_next = await get_history_page(uid, page=page)
        if not rows:
            await edit_main_text(update, context, I18N[lang]["no_history"], kb_history(lang, page, False, False)); return
        lines = [I18N[lang]["hist_title"], ""]
        for astro, kind, text, created_at in rows:
            date = created_at.split("T")[0]
            lines.append(I18N[lang]["hist_item"].format(date=date, kind=kind.upper(), astro=astro.capitalize(), snippet=snippet(text)))
        await edit_main_text(update, context, "\n".join(lines), kb_history(lang, page, has_prev, has_next)); return

    # SETTINGS
    if data == "settings:open":
        name, dob = await get_profile(uid)
        name = name or "—"; dob = dob or "—"
        txt = I18N[lang]["settings_title"] + "\n\n" + I18N[lang]["settings_view"].format(name=name, dob=dob)
        await edit_main_text(update, context, txt, kb_settings_menu(lang)); return

    if data.startswith("settings:edit:"):
        field = data.split(":")[-1]  # name|dob
        await save_form(uid, stage=f"edit_{field}")
        prompt = {"name":I18N[lang]["send_new_name"], "dob":I18N[lang]["send_new_dob"]}[field]
        await edit_main_text(update, context, prompt, kb_only_back(lang)); return

    # FREE reading — всегда спрашиваем фокус
    if data == "free:start":
        if not is_admin(uid):
            last = await when_last_free(uid)
            if last and (dt.datetime.utcnow()-last).total_seconds() < FREE_COOLDOWN_SEC:
                hours_left = int((FREE_COOLDOWN_SEC - (dt.datetime.utcnow()-last).total_seconds())//3600) + 1
                await edit_main_text(update, context, I18N[lang]["too_early"].format(hours_left=hours_left), kb_main(lang, *(await get_wallet(uid))[1:], ""))
                await home_screen(update, context, lang, uid); return
        name, dob = await get_profile(uid)
        if not (name and dob):
            await save_form(uid, stage="name_free")
            await edit_main_text(update, context, I18N[lang]["start_form"], kb_only_back(lang)); return
        await save_form(uid, stage="goal_free")
        await edit_main_text(update, context, I18N[lang]["ask_goal_every"], kb_only_back(lang)); return

    # ADVANCED reading — 1 кредит
    if data == "buy:adv":
        name, dob = await get_profile(uid)
        if not (name and dob):
            await save_form(uid, stage="name_adv")
            await edit_main_text(update, context, I18N[lang]["start_form"], kb_only_back(lang)); return
        await save_form(uid, stage="goal_adv")
        await edit_main_text(update, context, I18N[lang]["ask_goal_every"], kb_only_back(lang)); return

    # WALLET — USD / TOP-UP
    if data == "wallet:open":
        bal, cr = await get_wallet(uid)
        await edit_main_text(update, context, I18N[lang]["wallet"].format(amount=bal, credits=cr), kb_wallet(lang)); return
    if data == "wallet:topup":
        await edit_main_text(update, context, I18N[lang]["wallet_topup"], kb_wallet_topup_methods(lang)); return
    if data == "wallet:method:cryptobot":
        await edit_main_text(update, context, I18N[lang]["wallet_topup_usd"], kb_wallet_topup_usd(lang)); return
    if data == "wallet:method:stars":
        await edit_main_text(update, context, I18N[lang]["wallet_topup_stars"], kb_wallet_topup_stars(lang)); return

    # CryptoBot top-up (USD)
    if data.startswith("topup:usd:"):
        _,_,arg = data.split(":")
        if arg == "custom":
            await save_form(uid, stage="topup_usd_custom")
            await edit_main_text(update, context, I18N[lang]["enter_custom_amount"], kb_only_back(lang)); return
        amount = float(arg)
        invoice_id, pay_url = await cryptobot_create_invoice(kind="topup", uid=uid, amount_usd=amount, meta={})
        await edit_main_text(update, context, f"{I18N[lang]['custom_usd_topup_title']}: ${amount:.2f}\n\n{pay_url}", kb_cryptobot_invoice(lang, invoice_id)); return

    # Stars top-up → USD
    if data.startswith("topup:stars:"):
        stars = int(data.split(":")[-1])
        title = "USD Wallet Top-up"
        description = f"Convert {stars} Stars to USD at {STAR_TO_USD:.4f} USD/⭐"
        payload = f"topup:stars:{stars}"
        prices = [LabeledPrice(label=title, amount=stars)]
        msg = await context.bot.send_invoice(
            chat_id=update.effective_chat.id, title=title, description=description,
            payload=payload, provider_token="", currency="XTR", prices=prices,
            start_parameter=f"wallet_topup_{stars}", is_flexible=False
        )
        await add_invoice_message(uid, msg.message_id)
        return

    # CREDITS (packages)
    if data == "packs:open":
        lines = ["*"+I18N[lang]["packs_title"]+"*"]
        for n, price in PACKAGES.items():
            lines.append(I18N[lang]["pack_row"].format(n=n, price=price))
        txt = "\n".join(lines)
        rows = [[InlineKeyboardButton(f"{n} → ${price:.2f}", callback_data=f"pack:choose:{n}")] for n,price in PACKAGES.items()]
        rows.append([InlineKeyboardButton(I18N[lang]["back_btn"], callback_data="back:menu")])
        await edit_main_text(update, context, txt, InlineKeyboardMarkup(rows)); return

    if data.startswith("pack:choose:"):
        n = int(data.split(":")[-1]); price = PACKAGES[n]
        await edit_main_text(update, context, f"{I18N[lang]['pack_row'].format(n=n, price=price)}\n\n{I18N[lang]['wallet_topup']}",
                             kb_pay_methods_pack(lang, n, price)); return

    # оплата пакета
    if data.startswith("pack:") and ":cryptobot:" in data:
        _, n, _, price = data.split(":"); n=int(n); price=float(price)
        invoice_id, pay_url = await cryptobot_create_invoice(kind="pack", uid=uid, amount_usd=price, meta={"n":n})
        await edit_main_text(update, context, f"{I18N[lang]['cryptobot_invoice']}\n\nPay link:\n{pay_url}", kb_cryptobot_invoice(lang, invoice_id)); return

    if data.startswith("pack:") and ":frombalance:" in data:
        _, n, _, price = data.split(":"); n=int(n); price=float(price)
        bal, _ = await get_wallet(uid)
        if bal + 1e-9 < price:
            await edit_main_text(update, context, I18N[lang]["insufficient_balance"].format(bal=bal, need=price), kb_wallet(lang)); return
        ok = await charge_usd(uid, price)
        if not ok:
            await edit_main_text(update, context, I18N[lang]["insufficient_balance"].format(bal=bal, need=price), kb_wallet(lang)); return
        await add_credits(uid, n)
        await home_screen(update, context, lang, uid); return

    if data.startswith("pack:") and ":stars:" in data:
        _, n, _, stars_needed = data.split(":"); n=int(n); stars_needed=int(stars_needed)
        title = f"{n} Credits"
        price_usd = PACKAGES[n]
        description = f"Buy {n} credits for ${price_usd:.2f} — pay {stars_needed} Stars"
        payload = f"pack:stars:{n}:{stars_needed}"
        prices = [LabeledPrice(label=title, amount=stars_needed)]
        msg = await context.bot.send_invoice(
            chat_id=update.effective_chat.id, title=title, description=description,
            payload=payload, provider_token="", currency="XTR", prices=prices,
            start_parameter=f"pack_{n}_stars", is_flexible=False
        )
        await add_invoice_message(uid, msg.message_id)
        return

    # SUBSCRIPTIONS
    if data == "subs:open":
        sub = await get_sub(uid)
        if sub and sub.get("valid_until") and sub["valid_until"] >= dt.datetime.utcnow():
            txt = I18N[lang]["subs_title"] + "\n\n" + sub_status_line(lang, sub)
        else:
            lines = [I18N[lang]["subs_title"], ""]
            for key in ("lite","pro","vip"):
                t = SUB_TIERS[key]
                lines.append(I18N[lang]["subs_row"].format(name=t["label"][lang], price=t["price"], cr=t["credits_monthly"]))
            txt = "\n".join(lines)
        await edit_main_text(update, context, txt, kb_subs_list(lang)); return

    if data.startswith("subs:choose:"):
        tier = data.split(":")[-1]
        t = SUB_TIERS[tier]
        txt = I18N[lang]["subs_choose_pay"].format(name=t["label"][lang], price=t["price"])
        await edit_main_text(update, context, txt, kb_subs_pay(lang, tier)); return

    if data.startswith("subs:pay:cryptobot:"):
        tier = data.split(":")[-1]
        price = SUB_TIERS[tier]["price"]
        invoice_id, pay_url = await cryptobot_create_invoice(kind="sub", uid=uid, amount_usd=price, meta={"tier": tier})
        await edit_main_text(update, context, f"{I18N[lang]['cryptobot_invoice']}\n\nPay link:\n{pay_url}", kb_cryptobot_invoice(lang, invoice_id)); return

    if data.startswith("subs:pay:stars:"):
        _,_,_, tier, stars = data.split(":"); stars = int(stars)
        t = SUB_TIERS[tier]
        title = f"Subscription {t['label'][lang]}"
        description = f"{t['credits_monthly']} credits / month. ${t['price']:.2f}"
        payload = f"subs:stars:{tier}:{stars}"
        prices = [LabeledPrice(label=title, amount=stars)]
        msg = await context.bot.send_invoice(
            chat_id=update.effective_chat.id, title=title, description=description,
            payload=payload, provider_token="", currency="XTR", prices=prices,
            start_parameter=f"subs_{tier}_stars", is_flexible=False
        )
        await add_invoice_message(uid, msg.message_id)
        return

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = (await get_user(uid)).lang
    txt = (update.message.text or "").strip()

    # удалить сообщение пользователя
    try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except (BadRequest, Forbidden): pass

    st = await load_form(uid); stage = st.get("stage")

    # custom USD amount
    if stage == "topup_usd_custom":
        try:
            amount = float(txt.replace(",", "."))
        except:
            await edit_main_text(update, context, I18N[lang]["invalid_amount"], kb_only_back(lang)); return
        if not (1.0 <= amount <= 1000.0):
            await edit_main_text(update, context, I18N[lang]["invalid_amount"], kb_only_back(lang)); return
        await save_form(uid, stage=None)
        invoice_id, pay_url = await cryptobot_create_invoice(kind="topup", uid=uid, amount_usd=amount, meta={})
        await edit_main_text(update, context, f"{I18N[lang]['custom_usd_topup_title']}: ${amount:.2f}\n\n{pay_url}", kb_cryptobot_invoice(lang, invoice_id)); return

    # settings edits
    if stage and stage.startswith("edit_"):
        field = stage.replace("edit_","")  # name|dob
        if field == "name": await save_profile(uid, name=txt)
        elif field == "dob": await save_profile(uid, dob=txt)
        await save_form(uid, stage=None)
        await help_cmd(update, context); return

    # FREE reading form
    if stage == "name_free":
        await save_form(uid, name=txt, stage="dob_free")
        await edit_main_text(update, context, I18N[lang]["ask_dob"], kb_only_back(lang)); return

    if stage == "dob_free":
        await save_profile(uid, dob=txt)
        data = await load_form(uid); name = data.get("name")
        if name: await save_profile(uid, name=name)
        await save_form(uid, stage="goal_free")
        await edit_main_text(update, context, I18N[lang]["ask_goal_every"], kb_only_back(lang)); return

    if stage == "goal_free":
        if not is_valid_focus(txt):
            await edit_main_text(update, context, I18N[lang]["ask_goal_bad"], kb_only_back(lang)); return
        await save_form(uid, goal_session=txt, stage=None)
        data = await load_form(uid); astro = data.get("astro") or "priya"
        name, dob = await get_profile(uid)
        await edit_main_text(update, context, I18N[lang]["working"], kb_main(lang, *(await get_wallet(uid))[1:], ""))
        context.application.create_task(delayed_free_forecast(context.application, update.effective_chat.id, uid, lang, astro, name or "-", dob or "-", txt, mark_cooldown=(not is_admin(uid))))
        return

    # ADVANCED reading form (1 credit)
    if stage == "name_adv":
        await save_form(uid, name=txt, stage="dob_adv")
        await edit_main_text(update, context, I18N[lang]["ask_dob"], kb_only_back(lang)); return

    if stage == "dob_adv":
        await save_profile(uid, dob=txt)
        data = await load_form(uid); name = data.get("name")
        if name: await save_profile(uid, name=name)
        await save_form(uid, stage="goal_adv")
        await edit_main_text(update, context, I18N[lang]["ask_goal_every"], kb_only_back(lang)); return

    if stage == "goal_adv":
        if not is_valid_focus(txt):
            await edit_main_text(update, context, I18N[lang]["ask_goal_bad"], kb_only_back(lang)); return
        await save_form(uid, goal_session=txt, stage=None)
        if await use_credit(uid):
            await deliver_advanced(update, context, uid, lang); return
        # Кредитов нет → предлагаем купить
        await edit_main_text(update, context, f"{I18N[lang]['need_credit_title']}\n\n{I18N[lang]['buy_advanced']}", kb_need_credit(lang)); return

    await help_cmd(update, context)

# ==== Stars payment hooks ====
async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.pre_checkout_query.answer(ok=True)
    except BadRequest: pass

async def paid_success_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = (await get_user(uid)).lang
    sp = update.message.successful_payment
    payload = sp.invoice_payload or ""

    if payload.startswith("topup:stars:"):
        stars = int(payload.split(":")[-1]); usd = stars * STAR_TO_USD
        await add_usd(uid, usd)
        await update.message.reply_text(f"✅ Converted to USD: +${usd:.2f}")
        await home_screen(update, context, lang, uid); return

    if payload.startswith("pack:stars:"):
        _,_,n,_ = payload.split(":"); n = int(n)
        await add_credits(uid, n)
        await update.message.reply_text(f"✅ Purchased {n} credits.")
        await home_screen(update, context, lang, uid); return

    if payload.startswith("subs:stars:"):
        _,_,tier,_ = payload.split(":")
        await set_sub(uid, tier, months=1)
        await add_credits(uid, SUB_TIERS[tier]["credits_monthly"])
        await update.message.reply_text(I18N[lang]["subs_granted"].format(
            name=SUB_TIERS[tier]["label"][lang], cr=SUB_TIERS[tier]["credits_monthly"]
        ))
        await home_screen(update, context, lang, uid); return

# ==== Deliver advanced ====
async def deliver_advanced(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, lang: str):
    name, dob = await get_profile(uid)
    st = await load_form(uid); astro = st.get("astro") or "priya"
    goal = st.get("goal_session") or st.get("goal") or "-"
    await update.effective_chat.send_message(I18N[lang]["paid_working"])
    context.application.create_task(
        delayed_paid_forecast(
            context.application,
            update.effective_chat.id,
            uid, lang, astro,
            name or "-", dob or "-", goal or "-"
        )
    )

# ==== OpenAI generation ====
VOICE_HINTS = {
    "priya":{"en":"Tone: warm, caring. Focus love & relationships with gentle, practical steps."},
    "rahul":{"en":"Tone: motivating, grounded. Focus career & purpose."},
    "arjun":{"en":"Tone: structured, practical. Focus money/discipline/business."},
}
SYSTEM_FREE_SHORT = {
    "en":"You are a virtual astrologer. 2-3 sentences, surface-level, uplifting. Avoid medical/financial/legal claims."
}

async def generate_forecast_oai_short(lang: str, astro: str, name: str, dob: str, goal: str) -> str:
    system_msg = SYSTEM_FREE_SHORT["en"]
    voice = VOICE_HINTS[astro]["en"]
    user_prompt = f"User profile: name={name}; dob={dob}; focus_area={goal}. 2-3 sentences, positive, general."
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: oai.chat.completions.create(
            model=OPENAI_MODEL, messages=[{"role":"system","content":system_msg},{"role":"user","content":f"{voice}\n\n{user_prompt}"}], temperature=0.8))
    return resp.choices[0].message.content.strip()

async def generate_forecast_oai_long(lang: str, astro: str, name: str, dob: str, goal: str) -> str:
    system_msg = "You are a virtual Vedic astrologer. Motivational, specific reading (350-450 words) with 4-6 actionable tips. Avoid medical/financial/legal claims."
    voice = VOICE_HINTS[astro]["en"]
    user_prompt = f"User profile: name={name}; dob={dob}; focus_area={goal}. ~400 words."
    resp = await asyncio.get_event_loop().run_in_executor(
        None, lambda: oai.chat.completions.create(
            model=OPENAI_MODEL, messages=[{"role":"system","content":system_msg},{"role":"user","content":f"{voice}\n\n{user_prompt}"}], temperature=0.8))
    return resp.choices[0].message.content.strip()

# ==== Free reading background (5–7 мин) ====
async def delayed_free_forecast(app: Application, chat_id: int, uid: int, lang: str, astro: str, name: str, dob: str, goal: str, mark_cooldown: bool = True):
    await asyncio.sleep(random.randint(300,420))  # 5–7 минут
    forecast = await generate_forecast_oai_short(lang, astro, name, dob, goal)
    if mark_cooldown:
        await set_last_free(uid)
    await add_forecast(uid, astro, forecast, kind="free")
    state = await get_user(uid)
    out = f"*{I18N[lang]['done'].format(astro=astro.capitalize())}*\n\n{forecast}"
    try:
        await app.bot.edit_message_text(chat_id=chat_id, message_id=state.main_msg_id, text=out, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(lang, *(await get_wallet(uid))[1:], ""))
    except BadRequest:
        sent = await app.bot.send_message(chat_id=chat_id, text=out, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_main(lang, *(await get_wallet(uid))[1:], ""))
        await set_user_main_msg(uid, sent.message_id)

# ==== Paid reading background (5–7 мин + таймауты) ====
async def delayed_paid_forecast(app: Application, chat_id: int, uid: int, lang: str, astro: str, name: str, dob: str, goal: str):
    await asyncio.sleep(random.randint(300,420))  # 5–7 минут
    try:
        long_text = await asyncio.wait_for(
            generate_forecast_oai_long(lang=lang, astro=astro, name=name or "-", dob=dob or "-", goal=goal or "-"),
            timeout=120
        )
    except asyncio.TimeoutError:
        long_text = await asyncio.wait_for(
            generate_forecast_oai_short(lang=lang, astro=astro, name=name or "-", dob=dob or "-", goal=goal or "-"),
            timeout=60
        )
    await add_forecast(uid, astro, long_text, kind="paid")
    await save_form(uid, goal_session=None)
    state = await get_user(uid)
    out = f"*{I18N[lang]['paid_ready']}*\n\n{long_text}"
    try:
        await app.bot.edit_message_text(
            chat_id=chat_id, message_id=state.main_msg_id,
            text=out, parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main(lang, *(await get_wallet(uid))[1:], "")
        )
    except BadRequest:
        sent = await app.bot.send_message(
            chat_id=chat_id, text=out, parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb_main(lang, *(await get_wallet(uid))[1:], "")
        )
        await set_user_main_msg(uid, sent.message_id)

# ==== Validation ====
def is_valid_focus(text: str) -> bool:
    t = text.strip()
    if not (2 <= len(t) <= 60): return False
    letters = sum(ch.isalnum() or ch.isspace() for ch in t)
    if letters / len(t) < 0.6: return False
    if re.search(r'(.)\1\1\1', t): return False
    return True

# ==== Error & App ====
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, BadRequest): return
    print("Error:", context.error)

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(cb_router))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, paid_success_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    app.add_error_handler(on_error)
    return app

if __name__ == "__main__":
    # Инициализация БД (закрывает собственные временные петли)
    asyncio.run(init_db())
    asyncio.run(migrate_db())

    # Создаём новую петлю и делаем её текущей — чтобы run_polling() не падал
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = build_app()
    print("Vedic Astrology bot is running …")
    app.run_polling()  # синхронный запуск на текущей петле