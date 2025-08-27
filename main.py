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
import re
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# === CONFIG ===
TOKEN = "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw"
ADMIN_ID = 6964068910
WEBHOOK_URL = "magnificent-malissa-zarwga-2427f8ae.koyeb.app/"
REQUIRED_CHANNEL = ""

ASSEMBLYAI_API_KEY = "8615e9f175fc4a71bd2cff5af9eca989"
GEMINI_API_KEY = "AIzaSyDpb3UvnrRgk6Fu61za_VrRN8byZRSyq_I"

# MongoDB Configuration
MONGO_URI = "mongodb+srv://hoskasii:GHyCdwpI0PvNuLTg@cluster0.dy7oe7t.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "telegram_bot_db"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_collection = db["users"]
tokens_collection = db["tokens"]
# ============

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# In-memory store (for temporary data)
memory_lock = threading.Lock()
in_memory_data = {
    "stt_settings": {},   # key = user_id_str -> {"language_code": "en"}
    "pending_media": {},  # key = user_id_str -> pending dict
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
    " OK sand me Your media file audio video or voice massage Transcribe, translate & summarize effortlessly!\n"
    "Upload any media file (voice recordings, audio clips, or videos) up 20MB in size , in any language.\n\n"
    "Ensure the transcription Language matches the language of your audio file for accurate transcription.\n\n"
    "Other useful bot: @TextToSpeechBBot\n\n"
    "🌐 Current Language: {lang_name}  My last update: 21/08/2025"
)

# --------------------
# Database helpers
# --------------------
def get_user_data(user_id: int):
    return users_collection.find_one({"_id": str(user_id)})

def update_user_activity(user_id: int):
    user_id_str = str(user_id)
    now = datetime.now()
    users_collection.update_one(
        {"_id": user_id_str},
        {"$set": {"last_active": now}, "$setOnInsert": {"first_seen": now, "stt_conversion_count": 0, "tts_conversion_count": 0}},
        upsert=True
    )

def increment_processing_count(user_id: str, service_type: str):
    field_to_inc = f"{service_type}_conversion_count"
    users_collection.update_one(
        {"_id": str(user_id)},
        {"$inc": {field_to_inc: 1}}
    )

def get_stt_user_lang(user_id: str) -> str:
    user_data = users_collection.find_one({"_id": user_id})
    if user_data and "stt_language" in user_data:
        return user_data["stt_language"]
    return "en"

def set_stt_user_lang(user_id: str, lang_code: str):
    users_collection.update_one(
        {"_id": str(user_id)},
        {"$set": {"stt_language": lang_code}},
        upsert=True
    )

def user_has_stt_setting(user_id: str) -> bool:
    user_data = users_collection.find_one({"_id": str(user_id)})
    return user_data is not None and "stt_language" in user_data

# --------------------
# Pending media helpers
# --------------------
def save_pending_media(user_id: str, media_type: str, data: dict):
    with memory_lock:
        in_memory_data["pending_media"][user_id] = {
            "media_type": media_type,
            "data": data,
            "saved_at": datetime.now()
        }
    logging.info(f"Saved pending media for user {user_id}: {media_type}")

def pop_pending_media(user_id: str):
    with memory_lock:
        return in_memory_data["pending_media"].pop(user_id, None)

# --------------------
# Gemini / Assembly helpers
# --------------------
def delete_transcription_later(user_id: str, message_id: int):
    time.sleep(600)
    with memory_lock:
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
# Keyboards
# --------------------
def build_start_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    ordered_keys = sorted(STT_LANGUAGES.keys(), key=lambda k: (k != "English 🇬🇧", k != "العربية 🇸🇦", k))
    for lang_name in ordered_keys:
        lang_code = STT_LANGUAGES[lang_name]
        buttons.append(InlineKeyboardButton(lang_name, callback_data=f"start_select_lang|{lang_code}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

def build_stt_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    ordered_keys = sorted(STT_LANGUAGES.keys(), key=lambda k: (k != "English 🇬🇧", k != "العربية 🇸🇦", k))
    for lang_name in ordered_keys:
        lang_code = STT_LANGUAGES[lang_name]
        buttons.append(InlineKeyboardButton(lang_name, callback_data=f"stt_lang|{lang_code}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

def build_admin_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Total Users", callback_data="admin_total_users"),
        InlineKeyboardButton("✉️ Broadcast", callback_data="admin_broadcast")
    )
    return markup

# --------------------
# Utilities
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
# Bot handlers
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
            "🔒 *Access Locked*\n\nTo use this Bot, please join our group first. Tap the button below to join and then send /start.",
            reply_markup=markup,
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['start'])
def start_handler(message):
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    bot.send_message(
        message.chat.id,
        "👋Welcome ! Select transcription language using the below buttons:",
        reply_markup=build_start_language_keyboard()
    )

@bot.message_handler(commands=['admin'])
def admin_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 You are not authorized to use this command.")
        return
    update_user_activity(message.from_user.id)
    bot.send_message(message.chat.id, "🛠 Admin Panel", reply_markup=build_admin_menu())

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang|"))
def start_select_lang_callback(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang(uid, lang_code)
    # NOTE: user requested not to send the "Selected language" message — so we do NOT send/edit that text.
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")

    # Delete the language selection message (remove buttons from chat)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logging.info(f"Could not delete language selection message: {e}")

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
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard())
    except Exception:
        bot.send_message(call.message.chat.id, "Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard())
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['help'])
def help_handler(message):
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    help_text = (
        "❓ *How to use*\n\n"
        "• Send an audio message, audio file, or video (up 20MB) and I will transcribe it.\n"
        "• You can also send a Google Drive or direct media link and I'll transcribe it.\n"
        "• Use /lang or the inline Set again Language button to choose the transcription language.\n"
        "• After transcription you can Translate or Summarize using the inline buttons.\nNeed help? ☎️ Contact: @zack_bots"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['lang'])
def send_stt_language_prompt(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    bot.send_message(chat_id, " Choose the transcription language:", reply_markup=build_stt_language_keyboard())

@bot.callback_query_handler(lambda c: c.data and c.data.startswith("stt_lang|"))
def on_stt_language_select(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang(uid, lang_code)
    # User requested to not send that specific message, so we only answer the callback.
    bot.answer_callback_query(call.id, f"✅ Language set: {lang_name}")

    # Delete the language selection message (remove buttons from chat)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logging.info(f"Could not delete STT language selection message: {e}")

    # If the user had pending media, process it now
    pending = pop_pending_media(uid)
    if pending:
        logging.info(f"Processing pending for {uid} after stt_lang selection")
        pdata = pending["data"]
        if pending["media_type"] == "url":
            threading.Thread(target=lambda: asyncio.run(process_stt_media_url(pdata["chat_id"], uid, pdata["url"], bot, pdata["message_id"])), daemon=True).start()
        else:
            threading.Thread(target=lambda: asyncio.run(process_stt_media(pdata["chat_id"], uid, pending["media_type"], pdata["file_id"], bot, pdata["message_id"])), daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data in ["admin_total_users", "admin_broadcast"] and c.from_user.id == ADMIN_ID)
def admin_menu_callback(call):
    chat_id = call.message.chat.id
    if call.data == "admin_total_users":
        total_registered = users_collection.count_documents({})
        bot.send_message(chat_id, f"📊 Total registered users: *{total_registered}*", parse_mode="Markdown")
    elif call.data == "admin_broadcast":
        admin_state[call.from_user.id] = 'awaiting_broadcast_message'
        bot.send_message(chat_id, "✉️ Send the broadcast message now:")
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(m.from_user.id) == 'awaiting_broadcast_message', content_types=['text', 'photo', 'video', 'audio', 'document'])
def broadcast_message(message):
    admin_state[message.from_user.id] = None
    success = fail = 0
    user_ids = [doc["_id"] for doc in users_collection.find({}, {"_id": 1})]
    for uid in user_ids:
        if uid == str(ADMIN_ID):
            continue
        try:
            bot.copy_message(int(uid), message.chat.id, message.message_id)
            success += 1
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Failed to send broadcast to {uid}: {e}")
            fail += 1
        time.sleep(0.05)
    bot.send_message(message.chat.id, f"✅ Broadcast complete.\nSuccessful: {success}\nFailed: {fail}")

# --------------------
# STT processing (AssemblyAI)
# --------------------
async def process_stt_media(chat_id: int, user_id_for_settings: str, message_type: str, file_id: str, target_bot: telebot.TeleBot, original_message_id: int):
    processing_msg = None
    try:
        processing_msg = target_bot.send_message(chat_id, "Processing... Follow me on TikTok: http://www.tiktok.com/@zack3d?lang=x-gent", reply_to_message_id=original_message_id)
        file_info = target_bot.get_file(file_id)

        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        logging.info(f"Using Telegram file URL directly (no proxy): {file_url}")

        lang_code = get_stt_user_lang(user_id_for_settings)
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
            increment_processing_count(user_id_for_settings, "stt")
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

        lang_code = get_stt_user_lang(user_id_for_settings)
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
            increment_processing_count(user_id_for_settings, "stt")
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
    update_user_activity(int(user_id_for_settings))
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

    # If user has no language setting -> save pending and ask language
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
                reply_markup=build_stt_language_keyboard(),
                reply_to_message_id=message.message_id
            )
        except Exception:
            target_bot.send_message(
                message.chat.id,
                "Please choose transcription language (use the buttons).",
                reply_markup=build_stt_language_keyboard(),
                reply_to_message_id=message.message_id
            )
        return

    # If language is set, process the media in background
    threading.Thread(target=lambda: asyncio.run(process_stt_media(message.chat.id, user_id_for_settings, message_type, file_id, target_bot, message.message_id)), daemon=True).start()

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_stt_media_types(message):
    uid = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_stt_media_types_common(message, bot, uid)

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

@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # If text contains a URL, assume user wants to transcribe that link
    url = extract_first_url(message.text or "")
    if url:
        uid = str(message.from_user.id)
        # If user has no language setting -> save pending and ask language
        if not user_has_stt_setting(uid):
            save_pending_media(uid, "url", {
                "url": url,
                "chat_id": message.chat.id,
                "message_id": message.message_id
            })
            try:
                bot.send_message(
                    message.chat.id,
                    "Fadlan dooro luqadda turjumaadda (transcription) adigoo gujinaya badhamada hoose:",
                    reply_markup=build_stt_language_keyboard(),
                    reply_to_message_id=message.message_id
                )
            except Exception:
                bot.send_message(
                    message.chat.id,
                    "Please choose transcription language (use the buttons).",
                    reply_markup=build_stt_language_keyboard(),
                    reply_to_message_id=message.message_id
                )
            return
        # If language already set -> process immediately
        threading.Thread(target=lambda: asyncio.run(process_stt_media_url(message.chat.id, uid, url, bot, message.message_id)), daemon=True).start()
        return

    bot.send_message(message.chat.id, "I don’t support text-to-Speech. If you need text-to-voice, please use this bot: https://t.me/TextToSpeechBBot")

@bot.message_handler(func=lambda m: True, content_types=['sticker', 'photo'])
def handle_unsupported_media_types(message):
    update_user_activity(message.from_user.id)
    bot.send_message(message.chat.id, "⚠️ I only transcribe audio or video. Send an audio message, audio file, or a video.")

# --------------------
# Webhook / setup
# --------------------
@app.route("/", methods=["GET", "POST", "HEAD"])
def webhook():
    # quick healthcheck
    if request.method in ("GET", "HEAD"):
        return "OK", 200

    # Accept any content-type but try to parse JSON body
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

        # Process update in background thread so Flask can immediately return 200 to Telegram
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
        #BotCommand("admin", "Admin panel (admin only)")
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
    set_webhook_on_startup()
    set_bot_commands()
    try:
        # Check if the connection to MongoDB is working
        client.admin.command('ping')
        logging.info("Successfully connected to MongoDB!")
    except Exception as e:
        logging.error(f"Could not connect to MongoDB: {e}")

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)))
