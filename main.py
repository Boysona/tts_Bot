import uuid
import logging
import requests
import telebot
import json
from flask import Flask, request, abort
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import threading
import time
import os
import io
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============ CONFIG ============
TOKEN = "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw"
ADMIN_ID = 6964068910
WEBHOOK_URL = "https://tts-bot-1-d7ve.onrender.com"  # public URL of your Flask app
REQUIRED_CHANNEL = "@guruubka_wasmada"

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

MONGO_URI = "mongodb+srv://hoskasii:GHyCdwpI0PvNuLTg@cluster0.dy7oe7t.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "telegram_bot_db"
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_collection = db["users"]
stt_settings_collection = db["stt_settings"]
transcripts_collection = db["transcripts"]  # new collection to track transcript_id -> chat context

ASSEMBLYAI_API_KEY = "8615e9f175fc4a71bd2cff5af9eca989"
GEMINI_API_KEY = "AIzaSyDpb3UvnrRgk6Fu61za_VrRN8byZRSyq_I"

in_memory_data = {
    "users": {},
    "stt_settings": {},
}
user_transcriptions = {}
admin_state = {}
processing_message_ids = {}  # map transcript_id -> {chat_id, message_id} to optionally delete or update later

# Max allowed file size for direct uploads via Telegram (bot's policy in this bot)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

# ---------------- languages, helpers, etc (unchanged) ----------------
STT_LANGUAGES = {
    "English 🇬🇧": "en",
    "العربية 🇸🇦": "ar",
    "Spanish 🇪🇸": "es",
    "French 🇫🇷": "fr",
    "German 🇮🇹": "de",
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
    "Thai 🇹🇱": "th",
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
    "Tagalog 🇵🇱": "tl",
    "اردو 🇵🇰": "ur",
    "Swahili 🇰🇪": "sw",
    "Kazakh 🇰🇿": "kk",
    "Bulgarian 🇧🇬": "bg",
    "Serbian 🇷🇸": "sr",
    "فارسى 🇮🇷": "fa",
}

def check_db_connection():
    try:
        client.admin.command('ismaster')
        logging.info("MongoDB connection successful.")
        return True
    except ConnectionFailure:
        logging.error("MongoDB connection failed.")
        return False

def init_in_memory_data():
    logging.info("Initializing in-memory data structures from MongoDB.")
    try:
        all_users = users_collection.find()
        for user in all_users:
            in_memory_data["users"][user["_id"]] = user
        all_stt_settings = stt_settings_collection.find()
        for setting in all_stt_settings:
            in_memory_data["stt_settings"][setting["_id"]] = setting
    except OperationFailure as e:
        logging.error(f"Failed to load data from MongoDB: {e}")

def update_user_activity_in_memory(user_id: int):
    user_id_str = str(user_id)
    now = datetime.now()
    user_data = in_memory_data["users"].get(user_id_str, {
        "_id": user_id_str,
        "first_seen": now,
        "stt_conversion_count": 0,
    })
    user_data["last_active"] = now
    in_memory_data["users"][user_id_str] = user_data
    users_collection.update_one({"_id": user_id_str}, {"$set": {"last_active": now}}, upsert=True)

def increment_processing_count_in_memory(user_id: str, service_type: str):
    user_id_str = str(user_id)
    now = datetime.now()
    user_data = in_memory_data["users"].get(user_id_str, {
        "_id": user_id_str,
        "first_seen": now,
        "stt_conversion_count": 0,
    })
    field_to_inc = f"{service_type}_conversion_count"
    user_data[field_to_inc] = user_data.get(field_to_inc, 0) + 1
    user_data["last_active"] = now
    in_memory_data["users"][user_id_str] = user_data
    users_collection.update_one(
        {"_id": user_id_str},
        {"$inc": {field_to_inc: 1}, "$set": {"last_active": now}},
        upsert=True
    )

def get_stt_user_lang_in_memory(user_id: str) -> str:
    setting = in_memory_data["stt_settings"].get(user_id)
    if setting:
        return setting.get("language_code", "en")
    db_setting = stt_settings_collection.find_one({"_id": user_id})
    if db_setting:
        in_memory_data["stt_settings"][user_id] = db_setting
        return db_setting.get("language_code", "en")
    return "en"

def set_stt_user_lang_in_memory(user_id: str, lang_code: str):
    if user_id not in in_memory_data["stt_settings"]:
        in_memory_data["stt_settings"][user_id] = {}
    in_memory_data["stt_settings"][user_id]["language_code"] = lang_code
    stt_settings_collection.update_one({"_id": user_id}, {"$set": {"language_code": lang_code}}, upsert=True)

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

WELCOME_TEMPLATE = (
    " OK sand me Your media file audio video or voice massage Transcribe, translate & summarize effortlessly!\n"
    "Upload any media file (voice recordings, audio clips, or videos) up 20MB in size , in any language.\n\n"
    "Ensure the Output Language matches the language of your audio file for accurate transcription.\n\n"
    "Other useful bot: @TextToSpeechBBot\n\n"
    "🌐 Current Language: {lang_name}  My last update: 21/08/2025"
)

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

# ---------------- Bot handlers (unchanged) ----------------
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id_str = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    bot.send_message(
        message.chat.id,
        "Choose your Media (Voice, Audio, Video) file language using the below buttons:",
        reply_markup=build_start_language_keyboard()
    )

@bot.message_handler(commands=['admin'])
def admin_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 You are not authorized to use this command.")
        return
    update_user_activity_in_memory(message.from_user.id)
    bot.send_message(message.chat.id, "🛠 Admin Panel", reply_markup=build_admin_menu())

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang|"))
def start_select_lang_callback(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang_in_memory(uid, lang_code)
    welcome_text = WELCOME_TEMPLATE.format(lang_name=lang_name)
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("Set Output Language", callback_data="open_set_output_language"),
        InlineKeyboardButton("Add me to a Group!", url="https://t.me/mediatotextbot?startgroup=")
    )
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=welcome_text, reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, welcome_text, reply_markup=markup)
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")

@bot.callback_query_handler(func=lambda c: c.data == "open_set_output_language")
def open_set_output_language_callback(call):
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard())
    except Exception:
        bot.send_message(call.message.chat.id, "Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard())
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['help'])
def help_handler(message):
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    help_text = (
        "❓ *How to use*\n\n"
        "• Send an audio message, audio file, or video (up 20MB) and I will transcribe it.\n"
        "• Use /lang or the inline Set Output Language button to choose the transcription language.\n"
        "• After transcription you can Translate or Summarize using the inline buttons.\nNeed help? ☎️ Contact: @kookabeela"
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
    bot.send_message(chat_id, "🌍 Choose the transcription language:", reply_markup=build_stt_language_keyboard())

@bot.callback_query_handler(lambda c: c.data and c.data.startswith("stt_lang|"))
def on_stt_language_select(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang_in_memory(uid, lang_code)
    bot.answer_callback_query(call.id, f"✅ Language set: {lang_name}")
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"✅ Selected language: *{lang_name}*\n\nSend audio, video or voice message smaller 20MB to transcribe.", parse_mode="Markdown", reply_markup=None)
    except Exception:
        bot.send_message(call.message.chat.id, f"✅  Selected language: *{lang_name}*\n\nSend audio,Voice message, or video smaller 20MB to transcribe.", parse_mode="Markdown")

@bot.callback_query_handler(lambda c: c.data in ["admin_total_users", "admin_broadcast"] and c.from_user.id == ADMIN_ID)
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
    all_users_from_db = users_collection.find()
    for user_doc in all_users_from_db:
        uid = user_doc["_id"]
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

# ---------------- STT processing (no polling loop) ----------------
def process_stt_media(chat_id: int, user_id_for_settings: str, message_type: str, file_id: str, target_bot: telebot.TeleBot, original_message_id: int):
    processing_msg = None
    try:
        processing_msg = target_bot.send_message(chat_id, "Processing... (request sent to transcription service)", reply_to_message_id=original_message_id)
        file_info = target_bot.get_file(file_id)
        if file_info.file_size and file_info.file_size > MAX_FILE_SIZE_BYTES:
            # If file too large: ask user to provide external link (Drive/Dropbox)
            target_bot.send_message(chat_id, "⚠️ The file is too large (>20MB). Please provide a downloadable link (Google Drive/Dropbox) instead.", reply_to_message_id=original_message_id)
            return

        # Build Telegram file URL so AssemblyAI can fetch it directly.
        # This avoids proxying the whole file through our server.
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        logging.info(f"Requesting AssemblyAI to fetch file directly from Telegram URL: {file_url}")

        lang_code = get_stt_user_lang_in_memory(user_id_for_settings)

        # Create transcription request with webhook_url so AssemblyAI posts back when done.
        webhook_for_assemblyai = f"{WEBHOOK_URL.rstrip('/')}/assemblyai_callback"
        transcript_payload = {
            "audio_url": file_url,
            "language_code": lang_code,
            "speech_model": "best",
            "webhook_url": webhook_for_assemblyai
        }
        headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}
        transcript_res = requests.post("https://api.assemblyai.com/v2/transcript", headers=headers, json=transcript_payload, timeout=30)
        transcript_res.raise_for_status()
        transcript_json = transcript_res.json()
        transcript_id = transcript_json.get("id")
        if not transcript_id:
            raise Exception(f"No transcript id returned: {transcript_json}")

        # Save mapping to DB so callback can locate chat context
        transcripts_collection.update_one(
            {"_id": transcript_id},
            {"$set": {
                "chat_id": chat_id,
                "message_id": original_message_id,
                "user_id": user_id_for_settings,
                "language_code": lang_code,
                "created_at": datetime.utcnow(),
                "processing_message_id": processing_msg.message_id if processing_msg else None,
                "telegram_file_id": file_id
            }},
            upsert=True
        )
        # Also keep in-memory pointer for quick lookup (optional)
        processing_message_ids[transcript_id] = {"chat_id": chat_id, "processing_message_id": processing_msg.message_id if processing_msg else None}

        # Acknowledge to user (we keep the "Processing..." message in chat until callback).
        target_bot.send_message(chat_id, "✅ Transcription request received. I will send the transcript here when it's ready.", reply_to_message_id=original_message_id)

        logging.info(f"Started AssemblyAI transcription: {transcript_id} for chat {chat_id}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Network or API error during STT processing: {e}")
        target_bot.send_message(chat_id, "❌ A network error occurred while contacting the transcription service. Please try again.", reply_to_message_id=original_message_id)
    except Exception as e:
        logging.exception(f"Unhandled error during STT processing: {e}")
        target_bot.send_message(chat_id, "⚠️ Could not start transcription. Please try again or provide a downloadable link (Google Drive/Dropbox).", reply_to_message_id=original_message_id)
    # do not delete processing_msg here — we will remove/update it when webhook arrives

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
            message_type = "document_media"
        else:
            target_bot.send_message(message.chat.id, "⚠️ I can only transcribe audio or video. Send a valid file.")
            return
    if not file_id:
        target_bot.send_message(message.chat.id, "⚠️ Unsupported file type. Send audio, file, or video.")
        return
    if user_id_for_settings not in in_memory_data["stt_settings"]:
        target_bot.send_message(message.chat.id, "Please choose transcription language first using /lang or by selecting language after /start.")
        return
    # Launch processing in background thread (no busy polling)
    threading.Thread(target=process_stt_media, args=(message.chat.id, user_id_for_settings, message_type, file_id, target_bot, message.message_id), daemon=True).start()

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_stt_media_types(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_stt_media_types_common(message, bot, uid)

# ---------------- Translation / Summarize UI handlers (unchanged) ----------------
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
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    bot.send_message(message.chat.id, "I don’t support text-to-Speech. If you need text-to-voice, please use this bot: https://t.me/TextToSpeechBBot")

@bot.message_handler(func=lambda m: True, content_types=['sticker', 'photo'])
def handle_unsupported_media_types(message):
    update_user_activity_in_memory(message.from_user.id)
    bot.send_message(message.chat.id, "⚠️ I only transcribe audio or video. Send an audio message, audio file, or a video (20MB).")

# ---------------- Telegram webhook route (unchanged) ----------------
@app.route("/", methods=["GET", "POST", "HEAD"])
def webhook():
    if request.method in ("GET", "HEAD"):
        return "OK", 200
    if request.method == "POST":
        content_type = request.headers.get("Content-Type", "")
        if content_type and content_type.startswith("application/json"):
            update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
            bot.process_new_updates([update])
            return "", 200
    return abort(403)

# ---------------- AssemblyAI webhook callback route ----------------
@app.route("/assemblyai_callback", methods=["POST"])
def assemblyai_callback():
    """
    Receives webhook POSTs from AssemblyAI. Expected JSON includes at least:
    { "id": "<transcript_id>", "status": "completed" or "error", ... }

    When status == 'completed' -> fetch transcript from AssemblyAI and forward to Telegram chat stored in DB.
    """
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        logging.error(f"Invalid JSON in assemblyai callback: {e}")
        return "", 400

    if not payload:
        logging.error("Empty payload from assemblyai callback")
        return "", 400

    transcript_id = payload.get("id")
    status = payload.get("status")
    logging.info(f"AssemblyAI callback received: id={transcript_id}, status={status}")

    if not transcript_id:
        return "", 400

    # Lookup mapping in DB
    mapping = transcripts_collection.find_one({"_id": transcript_id})
    if not mapping:
        logging.warning(f"No mapping found for transcript_id {transcript_id}")
        # still return 200 so AssemblyAI doesn't keep retrying
        return "", 200

    chat_id = mapping.get("chat_id")
    orig_message_id = mapping.get("message_id")
    user_id_for_settings = mapping.get("user_id")

    # If status is completed, GET full transcript and send to Telegram
    if status == "completed":
        try:
            get_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
            headers = {"authorization": ASSEMBLYAI_API_KEY}
            r = requests.get(get_url, headers=headers, timeout=30)
            r.raise_for_status()
            res = r.json()
            text = res.get("text", "")
            if not text:
                bot.send_message(chat_id, "ℹ️ This file appears to be not audible or empty. Please send one with clearer audio.", reply_to_message_id=orig_message_id)
            else:
                # keep transcript in memory for quick translate/summarize actions (expires by delete_transcription_later)
                user_transcriptions.setdefault(user_id_for_settings, {})[orig_message_id] = text
                threading.Thread(target=delete_transcription_later, args=(user_id_for_settings, orig_message_id), daemon=True).start()

                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("Translate", callback_data=f"btn_translate|{orig_message_id}"),
                    InlineKeyboardButton("Summarize", callback_data=f"btn_summarize|{orig_message_id}")
                )

                if len(text) <= 4000:
                    bot.send_message(chat_id, text, reply_to_message_id=orig_message_id, reply_markup=markup)
                else:
                    f = io.BytesIO(text.encode("utf-8"))
                    f.name = "transcript.txt"
                    try:
                        bot.send_document(chat_id, f, caption="Here’s your transcript", reply_to_message_id=orig_message_id, reply_markup=markup)
                    except Exception as e:
                        logging.error(f"Failed to send transcript file with buttons: {e}")
                        try:
                            bot.send_document(chat_id, f, caption="Transcription file:")
                        except Exception as ex:
                            logging.error(f"Failed fallback send: {ex}")

                increment_processing_count_in_memory(user_id_for_settings, "stt")

            # remove or update the stored mapping: mark completed
            transcripts_collection.update_one({"_id": transcript_id}, {"$set": {"status": "completed", "completed_at": datetime.utcnow()}})

            # try to delete the "Processing..." message if we stored it
            proc_info = processing_message_ids.get(transcript_id) or {"processing_message_id": mapping.get("processing_message_id"), "chat_id": chat_id}
            try:
                if proc_info and proc_info.get("processing_message_id"):
                    bot.delete_message(chat_id, proc_info.get("processing_message_id"))
            except Exception as e:
                logging.info(f"Could not delete processing message: {e}")

        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch transcript data from AssemblyAI: {e}")
            bot.send_message(chat_id, "❌ Failed to retrieve transcription result from the service. Please try again later.", reply_to_message_id=orig_message_id)
        except Exception as e:
            logging.exception(f"Unhandled error while processing assemblyai callback: {e}")
            bot.send_message(chat_id, "⚠️ An error occurred while processing the transcription result.", reply_to_message_id=orig_message_id)

    elif status == "error":
        error_msg = payload.get("error", "Unknown error from transcription service.")
        bot.send_message(chat_id, f"❌ Transcription failed: {error_msg}", reply_to_message_id=orig_message_id)
        transcripts_collection.update_one({"_id": transcript_id}, {"$set": {"status": "error", "error": error_msg, "completed_at": datetime.utcnow()}})
    else:
        # other statuses (queued, processing) -- nothing to do
        logging.info(f"AssemblyAI callback status {status} — no action taken.")

    return "", 200

# ---------------- Webhook setup routes (unchanged) ----------------
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
        BotCommand("admin", "Admin panel (admin only)")
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
        logging.error("Failed to connect to MongoDB. Bot will run with in-memory data only, which will be lost on restart.")
        set_webhook_on_startup()
        set_bot_commands()

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)))
