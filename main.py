# main.py
import uuid
import logging
import requests
import telebot
import json
from flask import Flask, request, abort
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import asyncio
import threading
import time
import os
import io
import sqlite3
import re
import math

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === CONFIG ===
TOKEN = "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw"
ADMIN_ID = 6964068910
WEBHOOK_URL = "https://tts-bot-1-d7ve.onrender.com"
REQUIRED_CHANNEL = "@guruubka_wasmada"

ASSEMBLYAI_API_KEY = "8615e9f175fc4a71bd2cff5af9eca989"
GEMINI_API_KEY = "AIzaSyDpb3UvnrRgk6Fu61za_VrRN8byZRSyq_I"

# SQLite config
DB_FILE = os.environ.get("SQLITE_DB_FILE", "bot_data.sqlite3")
# ============

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# SQLite setup
sqlite_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
sqlite_conn.row_factory = sqlite3.Row
db_lock = threading.Lock()

def ensure_tables():
    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                first_seen TEXT,
                last_active TEXT,
                stt_conversion_count INTEGER DEFAULT 0,
                tts_conversion_count INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stt_settings (
                id TEXT PRIMARY KEY,
                language_code TEXT
            )
        """)
        sqlite_conn.commit()

ensure_tables()

# In-memory store (includes pending media)
in_memory_data = {
    "users": {},
    "stt_settings": {},
    "pending_media": {},  # key = user_id, value = pending dict
}
user_transcriptions = {}
admin_state = {}
processing_message_ids = set()

# Supported languages
STT_LANGUAGES = {
    "English 🇬🇧": "en",
    "العربية 🇸🇦": "ar",
    "Spanish 🇪🇸": "es",
    "French 🇫🇷": "fr",
    "German 🇩🇪": "de",
    "Russian 🇷🇺": "ru",
    "Portuguese 🇵🇹": "pt",
    "Japanese 🇯🇵": "ja",
    "Korean 🇰🇷": "ko",
    "Chinese 🇨🇳": "zh",
    "Hindi 🇮🇳": "hi",
    "Indonesian 🇮🇩": "id",
    "Italian 🇮🇹": "it",
    "Turkish 🇹🇷": "tr",
    "Somali 🇸🇴": "so",
    "Vietnamese 🇻🇳": "vi",
    "Thai 🇹🇭": "th",
    "Polish 🇵🇱": "pl",
    "Dutch 🇳🇱": "nl",
    "Swedish 🇸🇪": "sv",
    "Norwegian 🇳🇴": "no",
    "Danish 🇩🇰": "da",
    "Finnish 🇫🇮": "fi",
    "Czech 🇨🇿": "cs",
    "Hungarian 🇭🇺": "hu",
    "Romanian 🇷🇴": "ro",
    "Malay 🇲🇾": "ms",
    "Uzbek 🇺🇿": "uz",
    "Tagalog 🇵🇭": "tl",
    "اردو 🇵🇰": "ur",
    "Swahili 🇰🇪": "sw",
    "Kazakh 🇰🇿": "kk",
    "Bulgarian 🇧🇬": "bg",
    "Serbian 🇷🇸": "sr",
    "فارسى 🇮🇷": "fa",
}

WELCOME_TEMPLATE = (
    "👋 *Welcome!* — Send an audio, voice note, or video (up to 20MB) and I will transcribe it.\n\n"
    "• Upload media or send a direct/Google Drive link.\n"
    "• Choose the transcription language using *Set language* below.\n\n"
    "🌐 Current language: *{lang_name}*\n"
    "🕒 Last update: 21/08/2025\n\n"
    "Use the buttons below to get started."
)

# --------------------
# Database helpers (SQLite)
# --------------------
def check_db_connection():
    try:
        with db_lock:
            cur = sqlite_conn.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
        logging.info("SQLite connection OK.")
        return True
    except Exception as e:
        logging.error(f"SQLite connection failed: {e}")
        return False

def init_in_memory_data():
    logging.info("Initializing in-memory data structures from SQLite.")
    try:
        with db_lock:
            cur = sqlite_conn.cursor()
            cur.execute("SELECT * FROM users")
            users = cur.fetchall()
            for row in users:
                uid = row["id"]
                first_seen = None
                last_active = None
                try:
                    if row["first_seen"]:
                        first_seen = datetime.fromisoformat(row["first_seen"])
                    if row["last_active"]:
                        last_active = datetime.fromisoformat(row["last_active"])
                except Exception:
                    first_seen = None
                    last_active = None
                in_memory_data["users"][uid] = {
                    "_id": uid,
                    "first_seen": first_seen,
                    "last_active": last_active,
                    "stt_conversion_count": row["stt_conversion_count"] or 0,
                    "tts_conversion_count": row["tts_conversion_count"] or 0,
                }
            cur.execute("SELECT * FROM stt_settings")
            settings = cur.fetchall()
            for row in settings:
                uid = row["id"]
                in_memory_data["stt_settings"][uid] = {
                    "_id": uid,
                    "language_code": row["language_code"]
                }
    except Exception as e:
        logging.error(f"Failed to load data from SQLite: {e}")

def update_user_activity_in_memory(user_id: int):
    user_id_str = str(user_id)
    now = datetime.now()
    user_data = in_memory_data["users"].get(user_id_str, {
        "_id": user_id_str,
        "first_seen": now,
        "stt_conversion_count": 0,
        "tts_conversion_count": 0,
    })
    if "first_seen" not in user_data or user_data["first_seen"] is None:
        user_data["first_seen"] = now
    user_data["last_active"] = now
    in_memory_data["users"][user_id_str] = user_data
    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO users (id, first_seen, last_active, stt_conversion_count, tts_conversion_count)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id_str, user_data["first_seen"].isoformat(), now.isoformat(), user_data.get("stt_conversion_count", 0), user_data.get("tts_conversion_count", 0)))
        cur.execute("""
            UPDATE users SET last_active = ? WHERE id = ?
        """, (now.isoformat(), user_id_str))
        sqlite_conn.commit()

def increment_processing_count_in_memory(user_id: str, service_type: str):
    user_id_str = str(user_id)
    now = datetime.now()
    user_data = in_memory_data["users"].get(user_id_str, {
        "_id": user_id_str,
        "first_seen": now,
        "stt_conversion_count": 0,
        "tts_conversion_count": 0,
    })
    field_to_inc = f"{service_type}_conversion_count"
    user_data[field_to_inc] = user_data.get(field_to_inc, 0) + 1
    user_data["last_active"] = now
    in_memory_data["users"][user_id_str] = user_data

    if field_to_inc not in ("stt_conversion_count", "tts_conversion_count"):
        with db_lock:
            cur = sqlite_conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO users (id, first_seen, last_active, stt_conversion_count, tts_conversion_count)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id_str, now.isoformat(), now.isoformat(), user_data.get("stt_conversion_count", 0), user_data.get("tts_conversion_count", 0)))
            sqlite_conn.commit()
        return

    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO users (id, first_seen, last_active, stt_conversion_count, tts_conversion_count)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id_str, now.isoformat(), now.isoformat(), user_data.get("stt_conversion_count", 0), user_data.get("tts_conversion_count", 0)))
        cur.execute(f"""
            UPDATE users SET {field_to_inc} = COALESCE({field_to_inc}, 0) + 1, last_active = ?
            WHERE id = ?
        """, (now.isoformat(), user_id_str))
        sqlite_conn.commit()

# --------------------
# STT settings helpers
# --------------------
def get_stt_user_lang_in_memory(user_id: str) -> str:
    setting = in_memory_data["stt_settings"].get(user_id)
    if setting:
        return setting.get("language_code", "en")
    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("SELECT language_code FROM stt_settings WHERE id = ?", (user_id,))
        row = cur.fetchone()
    if row:
        db_setting = {"_id": user_id, "language_code": row["language_code"]}
        in_memory_data["stt_settings"][user_id] = db_setting
        return db_setting.get("language_code", "en")
    return "en"

def set_stt_user_lang_in_memory(user_id: str, lang_code: str):
    if user_id not in in_memory_data["stt_settings"]:
        in_memory_data["stt_settings"][user_id] = {}
    in_memory_data["stt_settings"][user_id]["language_code"] = lang_code
    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("""
            INSERT INTO stt_settings (id, language_code) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET language_code=excluded.language_code
        """, (user_id, lang_code))
        sqlite_conn.commit()

def user_has_stt_setting(user_id: str) -> bool:
    setting = in_memory_data["stt_settings"].get(user_id)
    if setting and setting.get("language_code"):
        return True
    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("SELECT language_code FROM stt_settings WHERE id = ?", (user_id,))
        row = cur.fetchone()
    if row and row["language_code"]:
        in_memory_data["stt_settings"][user_id] = {"_id": user_id, "language_code": row["language_code"]}
        return True
    return False

# --------------------
# Pending media helpers
# --------------------
def save_pending_media(user_id: str, media_type: str, data: dict):
    in_memory_data["pending_media"][user_id] = {
        "media_type": media_type,
        "data": data,
        "saved_at": datetime.now()
    }
    logging.info(f"Saved pending media for user {user_id}: {media_type}")

def pop_pending_media(user_id: str):
    return in_memory_data["pending_media"].pop(user_id, None)

# --------------------
# Gemini / Assembly helpers (unchanged)
# --------------------
def delete_transcription_later(user_id: str, message_id: int):
    time.sleep(600)
    if user_id in user_transcriptions and message_id in user_transcriptions[user_id]:
        del user_transcriptions[user_id][message_id]

def ask_gemini(text: str, instruction: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": instruction},
                    {"text": text}
                ]
            }
        ]
    }
    try:
        resp = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
        result = resp.json()
        if "candidates" in result:
            return result['candidates'][0]['content']['parts'][0]['text']
        return "Error: " + json.dumps(result)
    except Exception as e:
        return f"Error: {str(e)}"

def chunk_text(text: str, max_chars: int = 25000):
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start+max_chars])
        start += max_chars
    return chunks

def translate_large_text_with_gemini(text: str, target_lang_name: str):
    chunks = chunk_text(text, max_chars=24000)
    translated_chunks = []
    for i, chunk in enumerate(chunks):
        instr = f"Translate the following text to {target_lang_name}. Only provide the translation for this chunk. Chunk {i+1}/{len(chunks)}:"
        res = ask_gemini(chunk, instr)
        if res.startswith("Error:"):
            return res
        translated_chunks.append(res)
    combined = "\n\n".join(translated_chunks)
    final_instr = f"Combine and polish the following translated chunks into one coherent translation in {target_lang_name}. Only provide the translation:"
    final = ask_gemini(combined, final_instr)
    return final

def summarize_large_text_with_gemini(text: str, target_lang_name: str):
    chunks = chunk_text(text, max_chars=24000)
    partial_summaries = []
    for i, chunk in enumerate(chunks):
        instr = f"Summarize the following text in {target_lang_name}. Provide a concise summary (short). Chunk {i+1}/{len(chunks)}:"
        res = ask_gemini(chunk, instr)
        if res.startswith("Error:"):
            return res
        partial_summaries.append(res)
    combined = "\n\n".join(partial_summaries)
    final_instr = f"Combine and polish these partial summaries into a single concise summary in {target_lang_name}. Only provide the summary:"
    final = ask_gemini(combined, final_instr)
    return final

# --------------------
# UI / Keyboards (updated with pagination & main menu)
# --------------------
LANG_PAGE_SIZE = 9

def _ordered_language_items():
    # Put English and Arabic first, then the rest alphabetically
    keys = list(STT_LANGUAGES.keys())
    # custom ordering: English then Arabic
    keys_sorted = sorted(keys, key=lambda k: (k != "English 🇬🇧", k != "العربية 🇸🇦", k))
    return [(k, STT_LANGUAGES[k]) for k in keys_sorted]

def build_paginated_language_keyboard(page: int = 0, prefix: str = "stt_lang"):
    """
    prefix: 'stt_lang' for general selection, 'start_select_lang' when used from start flow
    page: zero-indexed
    """
    items = _ordered_language_items()
    total = len(items)
    pages = max(1, math.ceil(total / LANG_PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    start = page * LANG_PAGE_SIZE
    end = start + LANG_PAGE_SIZE
    page_items = items[start:end]

    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for name, code in page_items:
        buttons.append(InlineKeyboardButton(name, callback_data=f"{prefix}|{code}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])

    # navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}_page|{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"Page {page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}_page|{page+1}"))
    markup.add(*nav_buttons)

    # Small convenience buttons
    markup.add(
        InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        InlineKeyboardButton("❓ Help", callback_data="open_help")
    )
    return markup

def build_start_language_keyboard(page: int = 0):
    # uses start_select_lang prefix so callback sets language and shows welcome
    return build_paginated_language_keyboard(page=page, prefix="start_select_lang")

def build_stt_language_keyboard(page: int = 0):
    return build_paginated_language_keyboard(page=page, prefix="stt_lang")

def build_main_menu(user_id: str):
    lang_code = get_stt_user_lang_in_memory(user_id)
    lang_name = next((n for n, c in STT_LANGUAGES.items() if c == lang_code), "English 🇬🇧")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🌐 Set language", callback_data="open_set_output_language"),
        InlineKeyboardButton("❓ Help", callback_data="open_help"),
        InlineKeyboardButton("📄 My stats", callback_data="open_stats"),
        InlineKeyboardButton("➕ Add to group", url="https://t.me/mediatotextbot?startgroup=")
    )
    return markup

def build_admin_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Total Users", callback_data="admin_total_users"),
        InlineKeyboardButton("✉️ Broadcast", callback_data="admin_broadcast")
    )
    return markup

# --------------------
# Utilities (unchanged)
# --------------------
def normalize_google_drive_url(url: str) -> str:
    m = re.search(r'drive\.google\.com\/file\/d\/([a-zA-Z0-9_-]+)', url)
    if m:
        file_id = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    m2 = re.search(r'drive\.google\.com\/open\?id=([a-zA-Z0-9_-]+)', url)
    if m2:
        file_id = m2.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url

def extract_first_url(text: str) -> str:
    m = re.search(r'(https?://\S+)', text)
    return m.group(1) if m else None

# --------------------
# Bot handlers and callbacks (modified to use new UI)
# --------------------
def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Error checking subscription: {e}")
        return False

def send_subscription_message(chat_id: int):
    try:
        chat = bot.get_chat(chat_id)
    except Exception:
        chat = None
    if chat and chat.type == 'private':
        if not REQUIRED_CHANNEL or not REQUIRED_CHANNEL.strip():
            return
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Join the group to unlock",
                url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"
            )
        )
        bot.send_message(
            chat_id,
            "🔒 *Access Locked*\n\nTo use this assistant, please join our group first. Tap the button below to join and then send /start.",
            reply_markup=markup,
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id_str = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    lang_code = get_stt_user_lang_in_memory(user_id_str)
    lang_name = next((n for n, c in STT_LANGUAGES.items() if c == lang_code), "English 🇬🇧")
    welcome_text = WELCOME_TEMPLATE.format(lang_name=lang_name)
    try:
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=build_main_menu(user_id_str),
            parse_mode="Markdown"
        )
    except Exception:
        bot.send_message(message.chat.id, welcome_text, reply_markup=build_main_menu(user_id_str))

@bot.message_handler(commands=['help'])
def help_handler(message):
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    help_text = (
        "❓ *How to use*\n\n"
        "• Send an audio message, audio file, or video (up to 20MB) and I will transcribe it.\n"
        "• Or send a Google Drive / direct media link and I will transcribe.\n"
        "• Use *Set language* to choose the transcription language before sending media.\n\n"
        "After transcription you can Translate or Summarize using the inline buttons that appear with the result.\n\n"
        "Need help? ☎️ Contact: @kookabeela"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['lang'])
def send_stt_language_prompt(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    bot.send_message(chat_id, "Choose the transcription language:", reply_markup=build_stt_language_keyboard(0))

@bot.message_handler(commands=['stats'])
def stats_handler(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    user_data = in_memory_data["users"].get(uid)
    if not user_data:
        with db_lock:
            cur = sqlite_conn.cursor()
            cur.execute("SELECT stt_conversion_count, tts_conversion_count, first_seen, last_active FROM users WHERE id = ?", (uid,))
            row = cur.fetchone()
            if row:
                stt = row["stt_conversion_count"] or 0
                tts = row["tts_conversion_count"] or 0
                first_seen = row["first_seen"]
                last_active = row["last_active"]
            else:
                stt = tts = 0
                first_seen = last_active = "N/A"
    else:
        stt = user_data.get("stt_conversion_count", 0)
        tts = user_data.get("tts_conversion_count", 0)
        first_seen = user_data.get("first_seen").isoformat() if user_data.get("first_seen") else "N/A"
        last_active = user_data.get("last_active").isoformat() if user_data.get("last_active") else "N/A"

    bot.send_message(message.chat.id, f"📄 *Your stats*\n\n• STT conversions: *{stt}*\n• TTS conversions: *{tts}*\n• First seen: `{first_seen}`\n• Last active: `{last_active}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang|"))
def start_select_lang_callback(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang_in_memory(uid, lang_code)
    welcome_text = WELCOME_TEMPLATE.format(lang_name=lang_name)
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔁 Change language", callback_data="open_set_output_language"),
        InlineKeyboardButton("➕ Add to group", url="https://t.me/mediatotextbot?startgroup=")
    )
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=welcome_text, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        bot.send_message(call.message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")

    # If the user had pending media, process it now
    pending = pop_pending_media(uid)
    if pending:
        logging.info(f"Processing pending for {uid} after start_select_lang")
        pdata = pending["data"]
        if pending["media_type"] == "url":
            threading.Thread(target=lambda: asyncio.run(process_stt_media_url(pdata["chat_id"], uid, pdata["url"], bot, pdata["message_id"])), daemon=True).start()
        else:
            threading.Thread(target=lambda: asyncio.run(process_stt_media(pdata["chat_id"], uid, pending["media_type"], pdata["file_id"], bot, pdata["message_id"])), daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data == "open_set_output_language")
def open_set_output_language_callback(call):
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard(0))
    except Exception:
        bot.send_message(call.message.chat.id, "Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard(0))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "open_help")
def open_help_callback(call):
    # reuse help text
    help_text = (
        "❓ *How to use*\n\n"
        "• Send an audio message, audio file, or video (up to 20MB) and I will transcribe it.\n"
        "• Or send a Google Drive / direct media link and I will transcribe.\n"
        "• Use *Set language* to choose the transcription language before sending media.\n\n"
        "After transcription you can Translate or Summarize using the inline buttons that appear with the result.\n\n"
        "Need help? ☎️ Contact: @kookabeela"
    )
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=help_text, parse_mode="Markdown")
    except Exception:
        bot.send_message(call.message.chat.id, help_text, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "open_stats")
def open_stats_callback(call):
    # show user's stats (same as /stats)
    uid = str(call.from_user.id)
    user_data = in_memory_data["users"].get(uid)
    if not user_data:
        with db_lock:
            cur = sqlite_conn.cursor()
            cur.execute("SELECT stt_conversion_count, tts_conversion_count, first_seen, last_active FROM users WHERE id = ?", (uid,))
            row = cur.fetchone()
            if row:
                stt = row["stt_conversion_count"] or 0
                tts = row["tts_conversion_count"] or 0
                first_seen = row["first_seen"]
                last_active = row["last_active"]
            else:
                stt = tts = 0
                first_seen = last_active = "N/A"
    else:
        stt = user_data.get("stt_conversion_count", 0)
        tts = user_data.get("tts_conversion_count", 0)
        first_seen = user_data.get("first_seen").isoformat() if user_data.get("first_seen") else "N/A"
        last_active = user_data.get("last_active").isoformat() if user_data.get("last_active") else "N/A"

    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"📄 *Your stats*\n\n• STT conversions: *{stt}*\n• TTS conversions: *{tts}*\n• First seen: `{first_seen}`\n• Last active: `{last_active}`", parse_mode="Markdown")
    except Exception:
        bot.send_message(call.message.chat.id, f"📄 *Your stats*\n\n• STT conversions: *{stt}*\n• TTS conversions: *{tts}*\n• First seen: `{first_seen}`\n• Last active: `{last_active}`", parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data in ["admin_total_users", "admin_broadcast"] and c.from_user.id == ADMIN_ID)
def admin_menu_callback(call):
    chat_id = call.message.chat.id
    if call.data == "admin_total_users":
        with db_lock:
            cur = sqlite_conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM users")
            total_registered = cur.fetchone()["cnt"]
        bot.send_message(chat_id, f"📊 Total registered users: *{total_registered}*", parse_mode="Markdown")
    elif call.data == "admin_broadcast":
        admin_state[call.from_user.id] = 'awaiting_broadcast_message'
        bot.send_message(chat_id, "✉️ Send the broadcast message now:")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(m.from_user.id) == 'awaiting_broadcast_message', content_types=['text', 'photo', 'video', 'audio', 'document'])
def broadcast_message(message):
    admin_state[message.from_user.id] = None
    success = fail = 0
    with db_lock:
        cur = sqlite_conn.cursor()
        cur.execute("SELECT id FROM users")
        rows = cur.fetchall()
    for row in rows:
        uid = row["id"]
        if uid == str(ADMIN_ID):
            continue
        try:
            bot.copy_message(uid, message.chat.id, message.message_id)
            success += 1
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Failed to send broadcast to {uid}: {e}")
            fail += 1
        time.sleep(0.05)
    bot.send_message(message.chat.id, f"✅ Broadcast complete.\nSuccessful: {success}\nFailed: {fail}")

# --------------------
# STT processing (unchanged code body) - uses AssemblyAI
# --------------------
async def process_stt_media(chat_id: int, user_id_for_settings: str, message_type: str, file_id: str, target_bot: telebot.TeleBot, original_message_id: int):
    processing_msg = None
    try:
        processing_msg = target_bot.send_message(chat_id, "Processing...", reply_to_message_id=original_message_id)
        file_info = target_bot.get_file(file_id)

        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        logging.info(f"Using Telegram file URL directly (no proxy): {file_url}")

        lang_code = get_stt_user_lang_in_memory(user_id_for_settings)
        transcript_payload = {
            "audio_url": file_url,
            "language_code": lang_code,
            "speech_model": "best"
        }
        headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}
        transcript_res = requests.post("https://api.assemblyai.com/v2/transcript", headers=headers, json=transcript_payload, timeout=60)
        transcript_res.raise_for_status()
        transcript_id = transcript_res.json().get("id")
        if not transcript_id:
            raise Exception("AssemblyAI transcription request failed: No transcript ID received.")
        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        while True:
            res = requests.get(polling_url, headers={"authorization": ASSEMBLYAI_API_KEY}).json()
            if res['status'] in ['completed', 'error']:
                break
            time.sleep(2)
        if res['status'] == 'completed':
            text = res.get("text", "")
            if not text:
                target_bot.send_message(chat_id, "ℹ️ This file is not audible. Please send one with better audio.", reply_to_message_id=original_message_id)
            elif len(text) <= 4000:
                user_transcriptions.setdefault(user_id_for_settings, {})[original_message_id] = text
                threading.Thread(target=delete_transcription_later, args=(user_id_for_settings, original_message_id), daemon=True).start()
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Translate", callback_data=f"btn_translate|{original_message_id}"),
                    InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{original_message_id}")
                )
                target_bot.send_message(chat_id, text, reply_to_message_id=original_message_id, reply_markup=markup)
            else:
                user_transcriptions.setdefault(user_id_for_settings, {})[original_message_id] = text
                threading.Thread(target=delete_transcription_later, args=(user_id_for_settings, original_message_id), daemon=True).start()
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Translate", callback_data=f"btn_translate|{original_message_id}"),
                    InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{original_message_id}")
                )
                f = io.BytesIO(text.encode("utf-8"))
                f.name = "transcript.txt"
                try:
                    target_bot.send_document(chat_id, f, caption="Here’s your transcript", reply_to_message_id=original_message_id, reply_markup=markup)
                except Exception as e:
                    logging.error(f"Failed to send transcript file with buttons: {e}")
                    try:
                        target_bot.send_document(chat_id, f, caption="Transcription file:")
                    except Exception as ex:
                        logging.error(f"Failed fallback send: {ex}")
            increment_processing_count_in_memory(user_id_for_settings, "stt")
        else:
            error_msg = res.get("error", "Unknown transcription error.")
            target_bot.send_message(chat_id, f"❌ Transcription error: {error_msg}", parse_mode="Markdown", reply_to_message_id=original_message_id)
            logging.error(f"AssemblyAI transcription failed: {error_msg}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Network or API error during STT processing: {e}")
        try:
            target_bot.send_message(chat_id, "❌ A network error occurred. Please try again.", reply_to_message_id=original_message_id)
        except Exception:
            pass
    except Exception as e:
        logging.exception(f"Unhandled error during STT processing: {e}")
        try:
            target_bot.send_message(chat_id, "⚠️ The file is too large. Please send one smaller than 20MB, or upload it to Google Drive and then send me the link.", reply_to_message_id=original_message_id)
        except Exception:
            pass
    finally:
        if processing_msg:
            try:
                target_bot.delete_message(chat_id, processing_msg.message_id)
            except Exception as e:
                logging.error(f"Could not delete processing message: {e}")

async def process_stt_media_url(chat_id: int, user_id_for_settings: str, url: str, target_bot: telebot.TeleBot, original_message_id: int):
    processing_msg = None
    try:
        processing_msg = target_bot.send_message(chat_id, "Processing your link...", reply_to_message_id=original_message_id)
        normalized = normalize_google_drive_url(url)
        logging.info(f"Normalized media URL: {normalized}")

        lang_code = get_stt_user_lang_in_memory(user_id_for_settings)
        transcript_payload = {
            "audio_url": normalized,
            "language_code": lang_code,
            "speech_model": "best"
        }
        headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}
        transcript_res = requests.post("https://api.assemblyai.com/v2/transcript", headers=headers, json=transcript_payload, timeout=60)
        transcript_res.raise_for_status()
        transcript_id = transcript_res.json().get("id")
        if not transcript_id:
            raise Exception("AssemblyAI transcription request failed: No transcript ID received.")
        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        while True:
            res = requests.get(polling_url, headers={"authorization": ASSEMBLYAI_API_KEY}).json()
            if res['status'] in ['completed', 'error']:
                break
            time.sleep(2)
        if res['status'] == 'completed':
            text = res.get("text", "")
            if not text:
                target_bot.send_message(chat_id, "ℹ️ This file is not audible. Please provide a clearer audio file or link.", reply_to_message_id=original_message_id)
            elif len(text) <= 4000:
                user_transcriptions.setdefault(user_id_for_settings, {})[original_message_id] = text
                threading.Thread(target=delete_transcription_later, args=(user_id_for_settings, original_message_id), daemon=True).start()
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Translate", callback_data=f"btn_translate|{original_message_id}"),
                    InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{original_message_id}")
                )
                target_bot.send_message(chat_id, text, reply_to_message_id=original_message_id, reply_markup=markup)
            else:
                user_transcriptions.setdefault(user_id_for_settings, {})[original_message_id] = text
                threading.Thread(target=delete_transcription_later, args=(user_id_for_settings, original_message_id), daemon=True).start()
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Translate", callback_data=f"btn_translate|{original_message_id}"),
                    InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{original_message_id}")
                )
                f = io.BytesIO(text.encode("utf-8"))
                f.name = "transcript.txt"
                try:
                    target_bot.send_document(chat_id, f, caption="Here’s your transcript", reply_to_message_id=original_message_id, reply_markup=markup)
                except Exception as e:
                    logging.error(f"Failed to send transcript file with buttons: {e}")
                    try:
                        target_bot.send_document(chat_id, f, caption="Transcription file:")
                    except Exception as ex:
                        logging.error(f"Failed fallback send: {ex}")
            increment_processing_count_in_memory(user_id_for_settings, "stt")
        else:
            error_msg = res.get("error", "Unknown transcription error.")
            target_bot.send_message(chat_id, f"❌ Transcription error: {error_msg}", parse_mode="Markdown", reply_to_message_id=original_message_id)
            logging.error(f"AssemblyAI transcription failed: {error_msg}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Network or API error during link STT processing: {e}")
        try:
            target_bot.send_message(chat_id, "❌ A network error occurred while processing the link. Please try again.", reply_to_message_id=original_message_id)
        except Exception:
            pass
    except Exception as e:
        logging.exception(f"Unhandled error during link STT processing: {e}")
        try:
            target_bot.send_message(chat_id, "❌ An error occurred while processing your link. Ensure the link is a direct media link or a Google Drive share link.", reply_to_message_id=original_message_id)
        except Exception:
            pass
    finally:
        if processing_msg:
            try:
                target_bot.delete_message(chat_id, processing_msg.message_id)
            except Exception as e:
                logging.error(f"Could not delete processing message: {e}")

def handle_stt_media_types_common(message, target_bot: telebot.TeleBot, user_id_for_settings: str):
    update_user_activity_in_memory(int(user_id_for_settings))
    file_id = None
    message_type = None
    if message.voice:
        file_id = message.voice.file_id
        message_type = "voice"
    elif message.audio:
        file_id = message.audio.file_id
        message_type = "audio"
    elif message.video:
        file_id = message.video.file_id
        message_type = "video"
    elif message.document:
        if message.document.mime_type and (message.document.mime_type.startswith('audio/') or message.document.mime_type.startswith('video/')):
            file_id = message.document.file_id
            message_type = "document"
        else:
            target_bot.send_message(message.chat.id, "⚠️ I can only transcribe audio or video. Send a valid file.", reply_to_message_id=message.message_id)
            return
    if not file_id:
        target_bot.send_message(message.chat.id, "⚠️ Unsupported file type. Send audio, file, or video.", reply_to_message_id=message.message_id)
        return

    if not user_has_stt_setting(user_id_for_settings):
        save_pending_media(user_id_for_settings, message_type, {
            "file_id": file_id,
            "chat_id": message.chat.id,
            "message_id": message.message_id
        })
        try:
            target_bot.send_message(
                message.chat.id,
                "First choose the transcription language:",
                reply_markup=build_stt_language_keyboard(0),
                reply_to_message_id=message.message_id
            )
        except Exception:
            target_bot.send_message(
                message.chat.id,
                "Please choose transcription language (use the buttons).",
                reply_markup=build_stt_language_keyboard(0),
                reply_to_message_id=message.message_id
            )
        return

    threading.Thread(target=lambda: asyncio.run(process_stt_media(message.chat.id, user_id_for_settings, message_type, file_id, target_bot, message.message_id)), daemon=True).start()

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_stt_media_types(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_stt_media_types_common(message, bot, uid)

# --------------------
# Translate / Summarize handlers (mostly unchanged)
# --------------------
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("btn_translate|"))
def button_translate_handler(call):
    uid = str(call.from_user.id)
    _, message_id_str = call.data.split("|", 1)
    message_id = int(message_id_str)
    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ Transcription not available or expired")
        return
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for lang_name in STT_LANGUAGES.keys():
        buttons.append(InlineKeyboardButton(lang_name, callback_data=f"translate_to|{lang_name}|{message_id}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=" Select target language for translation:", reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, " Select target language for translation:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("btn_summarize|"))
def button_summarize_handler(call):
    uid = str(call.from_user.id)
    _, message_id_str = call.data.split("|", 1)
    message_id = int(message_id_str)
    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ Transcription expired")
        return
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for lang_name in STT_LANGUAGES.keys():
        buttons.append(InlineKeyboardButton(lang_name, callback_data=f"summarize_in|{lang_name}|{message_id}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Select language for summary:", reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, " Select language for summary:", reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("translate_to|"))
def callback_translate_to(call):
    uid = str(call.from_user.id)
    parts = call.data.split("|")
    lang_name = parts[1]
    message_id = int(parts[2])
    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ Transcription expired")
        return
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Translating to {lang_name}...")
    except Exception:
        bot.send_message(call.message.chat.id, f"Translating to {lang_name}...")
    bot.answer_callback_query(call.id)
    def do_translate():
        transcription = user_transcriptions[uid][message_id]
        translated = translate_large_text_with_gemini(transcription, lang_name)
        if translated.startswith("Error:"):
            bot.send_message(call.message.chat.id, f"❌ Translation error: {translated}")
            return
        if len(translated) > 4000:
            f = io.BytesIO(translated.encode("utf-8"))
            f.name = f"translation_{message_id}.txt"
            try:
                bot.send_document(call.message.chat.id, f, caption=f"Translation to {lang_name}:")
            except Exception as e:
                logging.error(f"Failed to send translation file: {e}")
                bot.send_message(call.message.chat.id, "✅ Translation complete (could not send file).")
        else:
            bot.send_message(call.message.chat.id, translated, reply_to_message_id=message_id)
    threading.Thread(target=do_translate, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("summarize_in|"))
def callback_summarize_in(call):
    uid = str(call.from_user.id)
    parts = call.data.split("|")
    lang_name = parts[1]
    message_id = int(parts[2])
    if uid not in user_transcriptions or message_id not in user_transcriptions[uid]:
        bot.answer_callback_query(call.id, "❌ Transcription expired")
        return
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Summarizing in {lang_name}...")
    except Exception:
        bot.send_message(call.message.chat.id, f"Summarizing in {lang_name}...")
    bot.answer_callback_query(call.id)
    def do_summarize():
        transcription = user_transcriptions[uid][message_id]
        summary = summarize_large_text_with_gemini(transcription, lang_name)
        if summary.startswith("Error:"):
            bot.send_message(call.message.chat.id, f"❌ Summarization error: {summary}")
            return
        if len(summary) > 4000:
            f = io.BytesIO(summary.encode("utf-8"))
            f.name = f"summary_{message_id}.txt"
            try:
                bot.send_document(call.message.chat.id, f, caption=f"Summary in {lang_name}:")
            except Exception as e:
                logging.error(f"Failed to send summary file: {e}")
                bot.send_message(call.message.chat.id, "✅ Summary complete (could not send file).")
        else:
            bot.send_message(call.message.chat.id, summary, reply_to_message_id=message_id)
    threading.Thread(target=do_summarize, daemon=True).start()

# --------------------
# Pagination & misc callback handlers for languages and navigation
# --------------------
@bot.callback_query_handler(func=lambda c: c.data and (c.data.startswith("stt_lang_page|") or c.data.startswith("start_select_lang_page|") or c.data.startswith("start_select_lang_page")))
def page_navigation_callback(call):
    # handle both prefixes; but our builder uses e.g. stt_lang_page|{page} or start_select_lang_page|{page}
    try:
        parts = call.data.split("|")
        prefix_page = parts[0]
        page = int(parts[1])
    except Exception:
        bot.answer_callback_query(call.id)
        return

    if prefix_page.startswith("stt_lang_page"):
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard(page))
        except Exception:
            bot.send_message(call.message.chat.id, "Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard(page))
    elif prefix_page.startswith("start_select_lang_page"):
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the media (voice/audio/video) language:", reply_markup=build_start_language_keyboard(page))
        except Exception:
            bot.send_message(call.message.chat.id, "Choose the media (voice/audio/video) language:", reply_markup=build_start_language_keyboard(page))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("stt_lang_page|"))
def stt_lang_page_callback(call):
    # legacy / direct handler (kept for clarity) - uses page number
    parts = call.data.split("|")
    page = int(parts[1])
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard(page))
    except Exception:
        bot.send_message(call.message.chat.id, "Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard(page))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang_page|"))
def start_select_lang_page_callback(call):
    parts = call.data.split("|")
    page = int(parts[1])
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the language:", reply_markup=build_start_language_keyboard(page))
    except Exception:
        bot.send_message(call.message.chat.id, "Choose the language:", reply_markup=build_start_language_keyboard(page))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cancel_callback(call):
    # simply return to main menu
    uid = str(call.from_user.id)
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Cancelled. Use the menu below:", reply_markup=build_main_menu(uid))
    except Exception:
        bot.send_message(call.message.chat.id, "Cancelled. Use /start to open menu.", reply_markup=build_main_menu(uid))
    bot.answer_callback_query(call.id, "Cancelled")

# handle language selection callbacks for stt_lang|{code}
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("stt_lang|"))
def on_stt_language_select(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang_in_memory(uid, lang_code)
    bot.answer_callback_query(call.id, f"✅ Language set: {lang_name}")
    try:
        #bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✅ Selected language: *{lang_name}*\n\nSend audio, voice message, or video to transcribe.", parse_mode="Markdown", reply_markup=None)
    #except Exception:
        #bot.send_message(call.message.chat.id, f"✅  Selected language: *{lang_name}*\n\nSend audio, voice message, or video to transcribe.", parse_mode="Markdown")

    # process pending if exists
    pending = pop_pending_media(uid)
    if pending:
        logging.info(f"Processing pending for {uid} after stt_lang selection")
        pdata = pending["data"]
        if pending["media_type"] == "url":
            threading.Thread(target=lambda: asyncio.run(process_stt_media_url(pdata["chat_id"], uid, pdata["url"], bot, pdata["message_id"])), daemon=True).start()
        else:
            threading.Thread(target=lambda: asyncio.run(process_stt_media(pdata["chat_id"], uid, pending["media_type"], pdata["file_id"], bot, pdata["message_id"])), daemon=True).start()

# --------------------
# Text / URL handlers (unchanged logic; some messages updated)
# --------------------
@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    url = extract_first_url(message.text or "")
    if url:
        uid = str(message.from_user.id)
        if not user_has_stt_setting(uid):
            save_pending_media(uid, "url", {
                "url": url,
                "chat_id": message.chat.id,
                "message_id": message.message_id
            })
            try:
                bot.send_message(
                    message.chat.id,
                    "Please choose the transcription language by tapping one of the buttons below:",
                    reply_markup=build_stt_language_keyboard(0),
                    reply_to_message_id=message.message_id
                )
            except Exception:
                bot.send_message(
                    message.chat.id,
                    "Please choose transcription language (use the buttons).",
                    reply_markup=build_stt_language_keyboard(0),
                    reply_to_message_id=message.message_id
                )
            return
        threading.Thread(target=lambda: asyncio.run(process_stt_media_url(message.chat.id, uid, url, bot, message.message_id)), daemon=True).start()
        return

    bot.send_message(message.chat.id, "I don’t support text-to-Speech. If you need text-to-voice, please use this bot: https://t.me/TextToSpeechBBot")

@bot.message_handler(func=lambda m: True, content_types=['sticker', 'photo'])
def handle_unsupported_media_types(message):
    update_user_activity_in_memory(message.from_user.id)
    bot.send_message(message.chat.id, "⚠️ I only transcribe audio or video. Send an audio message, audio file, or a video.")

# --------------------
# Webhook / setup (unchanged)
# --------------------
@app.route("/", methods=["GET", "POST", "HEAD"])
def webhook():
    if request.method in ("GET", "HEAD"):
        return "OK", 200
    if request.method == "POST":
        data_bytes = request.get_data()
        if not data_bytes:
            return "", 200
        try:
            data_str = data_bytes.decode('utf-8')
            update = telebot.types.Update.de_json(data_str)
        except Exception as e:
            logging.exception(f"Failed to parse update JSON: {e}")
            return "", 200

        def _process_update(u):
            try:
                bot.process_new_updates([u])
            except Exception:
                logging.exception("Error while processing update in background thread")

        threading.Thread(target=_process_update, args=(update,), daemon=True).start()
        return "", 200

    return abort(403)

@app.route("/set_webhook", methods=["GET", "POST"])
def set_webhook_route():
    try:
        bot.set_webhook(url=WEBHOOK_URL)
        return f"Webhook set to {WEBHOOK_URL}", 200
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")
        return f"Failed to set webhook: {e}", 500

@app.route("/delete_webhook", methods=["GET", "POST"])
def delete_webhook_route():
    try:
        bot.delete_webhook()
        return "Webhook deleted.", 200
    except Exception as e:
        logging.error(f"Failed to delete webhook: {e}")
        return f"Failed to delete webhook: {e}", 500

def set_bot_commands():
    commands = [
        BotCommand("start", "👋 Get Started"),
        BotCommand("lang", "Set STT File language"),
        BotCommand("help", "How to use"),
        BotCommand("stats", "Show my usage stats"),
    ]
    try:
        bot.set_my_commands(commands)
        logging.info("Main bot commands set successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to set main bot commands: {e}")
        return False

@app.route("/setup", methods=["GET"])
def setup_bot():
    webhook_status = set_webhook_on_startup()
    commands_status = set_bot_commands()
    response = "Bot setup complete:\n"
    response += f"Webhook status: {'Success' if webhook_status else 'Failed'}\n"
    response += f"Commands status: {'Success' if commands_status else 'Failed'}\n"
    return response, 200

def set_webhook_on_startup():
    try:
        bot.delete_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Main bot webhook set successfully to {WEBHOOK_URL}")
        return True
    except Exception as e:
        logging.error(f"Failed to set main bot webhook on startup: {e}")
        return False

def set_bot_info_and_startup():
    if check_db_connection():
        init_in_memory_data()
        set_webhook_on_startup()
        set_bot_commands()
    else:
        logging.error("Failed to connect to SQLite. Bot will run with in-memory data only, which will be lost on restart.")
        set_webhook_on_startup()
        set_bot_commands()

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)))
