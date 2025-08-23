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
from pymongo.errors import ConnectionFailure, OperationFailure

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TOKEN = "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw"
ADMIN_ID = 6964068910
WEBHOOK_URL = "https://tts-bot-1-d7ve.onrender.com"
REQUIRED_CHANNEL = "@guruubka_wasmada"

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

MONGO_URI = "mongodb+srv://hoskasii:GHyCdwpI0PvNuLTg@cluster0.dy7oe7t.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "telegram_bot_db"
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
users_collection = db["users"]
stt_settings_collection = db["stt_settings"]

ASSEMBLYAI_API_KEY = "8615e9f175fc4a71bd2cff5af9eca989"
GEMINI_API_KEY = "AIzaSyDpb3UvnrRgk6Fu61za_VrRN8byZRSyq_I"

in_memory_data = {
    "users": {},
    "stt_settings": {},
}
user_transcriptions = {}
admin_state = {}
processing_message_ids = {}

MAX_FILE_BYTES = 20 * 1024 * 1024

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
    "👋 *Welcome to Media to Text Bot!*\n\n"
    "Send any *voice*, *audio*, or *video* file (up to 20MB) and I'll transcribe it.\n\n"
    "🔹 I can *Transcribe*, *Translate* and *Summarize* audio/video.\n"
    "🔹 Choose the output language so I know which language to transcribe into.\n\n"
    "• Tip: For files over 20MB, upload to Google Drive or Dropbox and send the link.\n\n"
    "🌐 Current language: *{lang_name}*\n"
    "🕒 Last update: 23/08/2025\n\n"
    "_Need help? Contact @kookabeela_"
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

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id_str = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == get_stt_user_lang_in_memory(user_id_str)), "English 🇬🇧")
    welcome_text = WELCOME_TEMPLATE.format(lang_name=lang_name)

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Set Output Language", callback_data="open_set_output_language"),
    )
    markup.add(InlineKeyboardButton("Add me to your Group", url="https://t.me/mediatotextbot?startgroup="))
    try:
        bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        bot.send_message(message.chat.id, "Welcome! Use /help to get started.")

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
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=welcome_text, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        bot.send_message(call.message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")

@bot.callback_query_handler(func=lambda c: c.data == "open_set_output_language")
def open_set_output_language_callback(call):
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🌍 *Choose the Output (transcription) language:*", reply_markup=build_stt_language_keyboard(), parse_mode="Markdown")
    except Exception:
        bot.send_message(call.message.chat.id, "🌍 Choose the Output (transcription) language:", reply_markup=build_stt_language_keyboard())
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['help'])
def help_handler(message):
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    help_text = (
        "❓ *How to use*\n\n"
        "• Send an audio message, audio file, or video (up to 20MB) and I will transcribe it.\n"
        "• Use /lang or the inline *Set Output Language* button to choose the transcription language.\n\n"
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

def assemblyai_create_transcript_with_audio_url(audio_url: str, language_code: str):
    url = "https://api.assemblyai.com/v2/transcript"
    payload = {"audio_url": audio_url, "language_code": language_code, "speech_model": "best"}
    headers = {"authorization": ASSEMBLYAI_API_KEY, "content-type": "application/json"}
    res = requests.post(url, headers=headers, json=payload, timeout=30)
    res.raise_for_status()
    return res.json()

def assemblyai_upload_stream_and_create_transcript(stream_gen, language_code: str):
    upload_headers = {"authorization": ASSEMBLYAI_API_KEY, "Content-Type": "application/octet-stream"}
    upload_res = requests.post("https://api.assemblyai.com/v2/upload", headers=upload_headers, data=stream_gen, timeout=300)
    upload_res.raise_for_status()
    upload_json = upload_res.json()
    audio_url = upload_json.get('upload_url')
    if not audio_url:
        raise Exception("AssemblyAI upload did not return upload_url.")
    transcript_res = assemblyai_create_transcript_with_audio_url(audio_url, language_code)
    return transcript_res

def send_public_link_instructions(target_bot: telebot.TeleBot, chat_id: int, original_message_id: int = None):
    text = (
        "⚠️ *Please make sure the file/link is PUBLIC.*\n\n"
        "Steps:\n"
        "1. Tap the three dots (...) on the file.\n"
        "2. Choose *Manage access* or *Share*.\n"
        "3. Set access to: *Anyone with the link* (Viewer).\n\n"
        "Then resend the public link. Thank you."
    )
    try:
        target_bot.send_message(chat_id, text, parse_mode="Markdown", reply_to_message_id=original_message_id)
    except Exception:
        target_bot.send_message(chat_id, text, parse_mode="Markdown")

async def process_stt_media(chat_id: int, user_id_for_settings: str, message_type: str, file_id: str, target_bot: telebot.TeleBot, original_message_id: int):
    processing_msg = None
    try:
        processing_msg = target_bot.send_message(chat_id, "🔄 Processing your file...", reply_to_message_id=original_message_id)
        file_info = target_bot.get_file(file_id)

        if getattr(file_info, "file_size", None) and file_info.file_size > MAX_FILE_BYTES:
            target_bot.send_message(
                chat_id,
                "⚠️ The file is too large (over 20MB). Please upload it to Google Drive or Dropbox and send the link.",
                reply_to_message_id=original_message_id
            )
            return

        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        logging.info(f"Attempting to let AssemblyAI fetch file directly from Telegram: {file_url}")

        try:
            head = requests.head(file_url, allow_redirects=True, timeout=10)
            ct = (head.headers.get("content-type") or "").lower()
            if "text/html" in ct:
                send_public_link_instructions(target_bot, chat_id, original_message_id)
                return
        except Exception:
            pass

        lang_code = get_stt_user_lang_in_memory(user_id_for_settings)

        try:
            transcript_resp = assemblyai_create_transcript_with_audio_url(file_url, lang_code)
        except requests.exceptions.RequestException as e:
            logging.warning(f"AssemblyAI couldn't fetch file_url directly ({e}); falling back to streaming upload.")
            with requests.get(file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                def chunk_generator(chunk_size=524288):
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            yield chunk
                transcript_resp = assemblyai_upload_stream_and_create_transcript(chunk_generator(), lang_code)
        except Exception as e:
            logging.exception(f"Unexpected error while creating transcript (direct): {e}")
            target_bot.send_message(chat_id, "❌ Could not start transcription. Please try again later.", reply_to_message_id=original_message_id)
            return

        transcript_id = transcript_resp.get("id")
        if not transcript_id:
            target_bot.send_message(chat_id, "❌ Transcription request failed (no id).", reply_to_message_id=original_message_id)
            logging.error(f"AssemblyAI transcript creation failed response: {transcript_resp}")
            return

        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        while True:
            res = requests.get(polling_url, headers={"authorization": ASSEMBLYAI_API_KEY}).json()
            status = res.get('status')
            if status in ['completed', 'error']:
                break
            time.sleep(2)

        if res.get('status') == 'completed':
            text = res.get("text", "")
            if not text:
                target_bot.send_message(chat_id, "ℹ️ This file appears not to contain audible speech or it's unintelligible. Try a clearer audio.", reply_to_message_id=original_message_id)
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
            err_lower = str(error_msg).lower()
            if ("transcoding failed" in err_lower) or ("text/html" in err_lower) or ("file does not appear to contain audio" in err_lower) or ("html document" in err_lower):
                send_public_link_instructions(target_bot, chat_id, original_message_id)
            else:
                target_bot.send_message(chat_id, f"❌ Transcription error: {error_msg}", parse_mode="Markdown", reply_to_message_id=original_message_id)
                logging.error(f"AssemblyAI transcription failed: {error_msg}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Network or API error during STT processing: {e}")
        target_bot.send_message(chat_id, "❌ A network error occurred. Please try again.", reply_to_message_id=original_message_id)
    except Exception as e:
        logging.exception(f"Unhandled error during STT processing: {e}")
        target_bot.send_message(chat_id, "⚠️ The file could not be processed. Please send a file smaller than 20MB or upload it to Google Drive/Dropbox and send a public link.", reply_to_message_id=original_message_id)
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
            message_type = "document_media"
        else:
            return
    if not file_id:
        return
    if user_id_for_settings not in in_memory_data["stt_settings"]:
        target_bot.send_message(message.chat.id, "Please choose transcription language first using /lang or by selecting language after /start.", reply_markup=build_stt_language_keyboard())
        return

    threading.Thread(target=lambda: asyncio.run(process_stt_media(message.chat.id, user_id_for_settings, message_type, file_id, target_bot, message.message_id))).start()

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_stt_media_types(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
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

def is_google_drive_link(text: str) -> bool:
    return "drive.google.com" in text

def extract_drive_direct_link(text: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", text)
    if m:
        file_id = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    m2 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", text)
    if m2:
        file_id = m2.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return ""

def is_dropbox_link(text: str) -> bool:
    return "dropbox.com" in text

def convert_dropbox_link(text: str) -> str:
    if "dl=0" in text:
        return text.replace("dl=0", "dl=1")
    if "dl=1" in text:
        return text
    if "www.dropbox.com" in text or "dropbox.com" in text:
        return text + ("&raw=1" if "?" in text else "?raw=1")
    return text

def is_direct_media_url(text: str) -> bool:
    return bool(re.search(r"\.(mp3|wav|m4a|ogg|flac|aac|mp4|webm|mov)(\?|$)", text, re.IGNORECASE))

def process_external_audio_url(chat_id: int, user_id_for_settings: str, audio_url: str, target_bot: telebot.TeleBot, original_message_id: int):
    processing_msg = None
    try:
        processing_msg = target_bot.send_message(chat_id, "🔄 Processing your link...", reply_to_message_id=original_message_id)
        lang_code = get_stt_user_lang_in_memory(user_id_for_settings)
        if not lang_code:
            target_bot.send_message(chat_id, "Please set transcription language first using /lang.", reply_to_message_id=original_message_id)
            return

        try:
            head = requests.head(audio_url, allow_redirects=True, timeout=10)
            ct = (head.headers.get("content-type") or "").lower()
            if "text/html" in ct:
                send_public_link_instructions(target_bot, chat_id, original_message_id)
                return
        except Exception:
            pass

        try:
            transcript_resp = assemblyai_create_transcript_with_audio_url(audio_url, lang_code)
        except requests.exceptions.RequestException as e:
            logging.warning(f"AssemblyAI couldn't fetch external URL directly ({e}). Trying to proxy...")
            with requests.get(audio_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                ct_get = (r.headers.get("content-type") or "").lower()
                if "text/html" in ct_get:
                    send_public_link_instructions(target_bot, chat_id, original_message_id)
                    return
                def chunk_generator(chunk_size=524288):
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            yield chunk
                transcript_resp = assemblyai_upload_stream_and_create_transcript(chunk_generator(), lang_code)
        except Exception as e:
            logging.exception(f"Unexpected error creating transcript from external URL: {e}")
            target_bot.send_message(chat_id, "❌ Could not start transcription from the link. Ensure the file is publicly accessible.", reply_to_message_id=original_message_id)
            return

        transcript_id = transcript_resp.get("id")
        if not transcript_id:
            target_bot.send_message(chat_id, "❌ Transcription request failed (no id).", reply_to_message_id=original_message_id)
            logging.error(f"AssemblyAI transcript creation failed response: {transcript_resp}")
            return

        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        while True:
            res = requests.get(polling_url, headers={"authorization": ASSEMBLYAI_API_KEY}).json()
            status = res.get('status')
            if status in ['completed', 'error']:
                break
            time.sleep(2)

        if res.get('status') == 'completed':
            text = res.get("text", "")
            if not text:
                target_bot.send_message(chat_id, "ℹ️ This file appears not to contain audible speech or it's unintelligible. Try a clearer audio or a different file.", reply_to_message_id=original_message_id)
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
                    logging.error(f"Failed to send transcript file with buttons (external): {e}")
                    try:
                        target_bot.send_document(chat_id, f, caption="Transcription file:")
                    except Exception as ex:
                        logging.error(f"Failed fallback send (external): {ex}")
            increment_processing_count_in_memory(user_id_for_settings, "stt")
        else:
            error_msg = res.get("error", "Unknown transcription error.")
            err_lower = str(error_msg).lower()
            if ("transcoding failed" in err_lower) or ("text/html" in err_lower) or ("file does not appear to contain audio" in err_lower) or ("html document" in err_lower):
                send_public_link_instructions(target_bot, chat_id, original_message_id)
            else:
                target_bot.send_message(chat_id, f"❌ Transcription error: {error_msg}", parse_mode="Markdown", reply_to_message_id=original_message_id)
                logging.error(f"AssemblyAI transcription failed (external): {error_msg}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Network or API error during external STT processing: {e}")
        target_bot.send_message(chat_id, "❌ A network error occurred. Please try again.", reply_to_message_id=original_message_id)
    except Exception as e:
        logging.exception(f"Unhandled error during external STT processing: {e}")
        target_bot.send_message(chat_id, "⚠️ Could not process the link. Ensure it points to a public audio/video file.", reply_to_message_id=original_message_id)
    finally:
        if processing_msg:
            try:
                target_bot.delete_message(chat_id, processing_msg.message_id)
            except Exception as e:
                logging.error(f"Could not delete processing message (external): {e}")

@bot.message_handler(content_types=['text'])
def handle_text_messages(message):
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    text = (message.text or "").strip()
    if is_google_drive_link(text):
        direct_link = extract_drive_direct_link(text)
        if not direct_link:
            bot.send_message(message.chat.id, "❌ Could not extract file ID from Google Drive link. Make sure it's a file-share link (format: /file/d/<id>/view or contains id=). Also ensure the file is shared as *Anyone with the link*. See my instructions in the chat.", parse_mode="Markdown")
            return
        uid = str(message.from_user.id)
        if uid not in in_memory_data["stt_settings"]:
            bot.send_message(message.chat.id, "Please choose transcription language first using /lang or by selecting language after /start.", reply_markup=build_stt_language_keyboard())
            return
        threading.Thread(target=process_external_audio_url, args=(message.chat.id, uid, direct_link, bot, message.message_id), daemon=True).start()
        return

    if is_dropbox_link(text):
        converted = convert_dropbox_link(text)
        uid = str(message.from_user.id)
        if uid not in in_memory_data["stt_settings"]:
            bot.send_message(message.chat.id, "Please choose transcription language first using /lang or by selecting language after /start.", reply_markup=build_stt_language_keyboard())
            return
        threading.Thread(target=process_external_audio_url, args=(message.chat.id, uid, converted, bot, message.message_id), daemon=True).start()
        return

    if is_direct_media_url(text):
        uid = str(message.from_user.id)
        if uid not in in_memory_data["stt_settings"]:
            bot.send_message(message.chat.id, "Please choose transcription language first using /lang or by selecting language after /start.", reply_markup=build_stt_language_keyboard())
            return
        threading.Thread(target=process_external_audio_url, args=(message.chat.id, uid, text, bot, message.message_id), daemon=True).start()
        return

    return

@bot.message_handler(func=lambda m: True, content_types=['sticker', 'photo'])
def handle_unsupported_media_types(message):
    update_user_activity_in_memory(message.from_user.id)
    return

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
