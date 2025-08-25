# bot.py
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TOKEN = "7770743573:AAGoaSzjKiC4kZeYaF5ioP5ReMC_wy4R7W0"
ADMIN_ID = 6964068910
WEBHOOK_URL = "https://tts-bot-2.onrender.com"
REQUIRED_CHANNEL = "@guruubka_wasmada"

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

ASSEMBLYAI_API_KEY = "8615e9f175fc4a71bd2cff5af9eca989"
GEMINI_API_KEY = "AIzaSyDpb3UvnrRgk6Fu61za_VrRN8byZRSyq_I"

# In-memory data only
in_memory_data = {
    "users": {},
    "stt_settings": {},
    "pending_media": {}  # New dictionary for temporary media storage
}
user_transcriptions = {}
admin_state = {}
processing_message_ids = set()

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
    " OK send me your media file audio, video, or voice message to Transcribe, Translate & Summarize effortlessly!\n"
    "Upload any media file (voice recordings, audio clips, or videos) up to 20MB.\n"
    "Ensure the Transcription Language matches the language of your audio file for accurate transcription.\n"
    "Other useful bot: @TextToSpeechBBot\n\n"
    "🌐 Current Language: {lang_name}  My last update: 21/08/2025"
)

# ----------------- MEMORY FUNCTIONS -----------------
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

def get_stt_user_lang_in_memory(user_id: str) -> str:
    return in_memory_data["stt_settings"].get(user_id, {}).get("language_code")

def set_stt_user_lang_in_memory(user_id: str, lang_code: str):
    if user_id not in in_memory_data["stt_settings"]:
        in_memory_data["stt_settings"][user_id] = {}
    in_memory_data["stt_settings"][user_id]["language_code"] = lang_code

def delete_transcription_later(user_id: str, message_id: int):
    time.sleep(600)
    if user_id in user_transcriptions and message_id in user_transcriptions[user_id]:
        del user_transcriptions[user_id][message_id]

def clear_pending_media(user_id: int):
    if user_id in in_memory_data["pending_media"]:
        del in_memory_data["pending_media"][user_id]

# ----------------- ASSEMBLYAI FUNCTIONS -----------------
def transcribe_audio_file(audio_file_data, language_code, message_id):
    headers = {
        "authorization": ASSEMBLYAI_API_KEY,
        "Content-Type": "application/octet-stream"
    }
    upload_response = requests.post("https://api.assemblyai.com/v2/upload", data=audio_file_data, headers=headers)
    if upload_response.status_code != 200:
        return f"Error uploading file: {upload_response.text}"
    audio_url = upload_response.json()["upload_url"]

    transcript_request = {
        "audio_url": audio_url,
        "language_code": language_code,
        "speaker_labels": True,
        "auto_chapters": True
    }
    transcript_response = requests.post("https://api.assemblyai.com/v2/transcript", json=transcript_request, headers=headers)
    if transcript_response.status_code != 200:
        return f"Error creating transcript: {transcript_response.text}"
    transcript_id = transcript_response.json()["id"]

    while True:
        polling_response = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers)
        if polling_response.status_code != 200:
            return f"Error polling transcript: {polling_response.text}"
        result = polling_response.json()
        if result["status"] == "completed":
            return result["text"]
        elif result["status"] == "error":
            return f"Transcription error: {result['error']}"
        time.sleep(1)

# ----------------- TELEGRAM / GEMINI FUNCTIONS -----------------
def ask_gemini(text: str, instruction: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": instruction}, {"text": text}]}]}
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
    return ask_gemini(combined, final_instr)

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
    return ask_gemini(combined, final_instr)

# ----------------- KEYBOARDS -----------------
def build_start_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(name, callback_data=f"start_select_lang|{code}") 
               for name, code in sorted(STT_LANGUAGES.items(), key=lambda k: (k[0] != "English 🇬🇧", k[0] != "العربية 🇸🇦", k[0]))]
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

def build_stt_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(name, callback_data=f"stt_lang|{code}") 
               for name, code in sorted(STT_LANGUAGES.items(), key=lambda k: (k[0] != "English 🇬🇧", k[0] != "العربية 🇸🇦", k[0]))]
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

def build_media_language_selection_keyboard():
    """Builds a keyboard for language selection after a user sends media."""
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [
        InlineKeyboardButton(name, callback_data=f"process_media_lang|{code}")
        for name, code in sorted(STT_LANGUAGES.items(), key=lambda k: (k[0] != "English 🇬🇧", k[0] != "العربية 🇸🇦", k[0]))
    ]
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i + 3])
    return markup

def build_admin_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 Total Users", callback_data="admin_total_users"),
        InlineKeyboardButton("✉️ Broadcast", callback_data="admin_broadcast")
    )
    return markup

# ----------------- SUBSCRIPTION CHECK -----------------
def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException:
        return False

def send_subscription_message(chat_id: int):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Join the group to unlock", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"))
    bot.send_message(
        chat_id,
        "🔒 *Access Locked*\n\nJoin the group first. Tap the button below then send /start.",
        reply_markup=markup, parse_mode="Markdown"
    )

# ----------------- START / ADMIN / HELP -----------------
@bot.message_handler(commands=['start'])
def start_handler(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    bot.send_message(message.chat.id, "Choose Transcription language:", reply_markup=build_start_language_keyboard())

@bot.message_handler(commands=['admin'])
def admin_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Not authorized.")
        return
    update_user_activity_in_memory(message.from_user.id)
    bot.send_message(message.chat.id, "🛠 Admin Panel", reply_markup=build_admin_menu())

@bot.message_handler(commands=['help'])
def help_handler(message):
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    help_text = (
        "❓ *How to use*\n"
        "• Send audio, voice, or video (up to 20MB) to transcribe.\n"
        "• You can send Google Drive or direct media links for transcription.\n"
        "• /lang or inline buttons set transcription language.\n"
        "• After transcription you can Translate or Summarize.\nNeed help? ☎️ Contact: @kookabeela"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# ----------------- LANGUAGE SELECTION CALLBACKS -----------------
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang|"))
def start_select_lang_callback(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang_in_memory(uid, lang_code)
    welcome_text = WELCOME_TEMPLATE.format(lang_name=lang_name)
    markup = InlineKeyboardMarkup()
    markup.add(
        #InlineKeyboardButton("Set Output Language", callback_data="open_set_output_language"),
        InlineKeyboardButton("Add me to a Group!", url="https://t.me/mediatotextbot?startgroup=")
    )
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=welcome_text, reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, welcome_text, reply_markup=markup)
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("process_media_lang|"))
def process_media_lang_callback(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")
    set_stt_user_lang_in_memory(uid, lang_code)
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")
    
    # Check for and process pending media
    if uid in in_memory_data["pending_media"]:
        pending_media = in_memory_data["pending_media"].pop(uid)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        process_media(call.message.chat.id, pending_media)
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=f"✅ Language set to {lang_name}. Now send your media file.",
                              reply_markup=None)

@bot.callback_query_handler(func=lambda c: c.data == "open_set_output_language")
def open_set_output_language_callback(call):
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Choose Output language:", reply_markup=build_stt_language_keyboard())
    except Exception:
        bot.send_message(call.message.chat.id, "Choose Output language:", reply_markup=build_stt_language_keyboard())
    bot.answer_callback_query(call.id)

# ----------------- MAIN MEDIA HANDLER -----------------
@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_media_messages(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)

    # Check for channel subscription
    if message.chat.type == 'private' and uid != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    # Check if a language is set for the user
    user_lang_code = get_stt_user_lang_in_memory(uid)
    if not user_lang_code:
        # Save media info temporarily and ask for language
        if message.voice:
            file_id = message.voice.file_id
            file_info = bot.get_file(file_id)
            file_path = file_info.file_path
            in_memory_data["pending_media"][message.from_user.id] = {'type': 'voice', 'file_id': file_id, 'file_path': file_path}
        elif message.audio:
            file_id = message.audio.file_id
            file_info = bot.get_file(file_id)
            file_path = file_info.file_path
            in_memory_data["pending_media"][message.from_user.id] = {'type': 'audio', 'file_id': file_id, 'file_path': file_path}
        elif message.video:
            file_id = message.video.file_id
            file_info = bot.get_file(file_id)
            file_path = file_info.file_path
            in_memory_data["pending_media"][message.from_user.id] = {'type': 'video', 'file_id': file_id, 'file_path': file_path}
        elif message.document and message.document.mime_type.startswith(('audio', 'video')):
            file_id = message.document.file_id
            file_info = bot.get_file(file_id)
            file_path = file_info.file_path
            in_memory_data["pending_media"][message.from_user.id] = {'type': 'document', 'file_id': file_id, 'file_path': file_path}
        else:
            bot.send_message(message.chat.id, "Unsupported file type. Please send a voice note, audio, or video.")
            return

        bot.send_message(message.chat.id, "Please select the language of the audio to start the transcription:",
                         reply_markup=build_media_language_selection_keyboard())
        return
    
    # Process media directly if language is set
    media_info = {}
    if message.voice:
        media_info = {'type': 'voice', 'file_id': message.voice.file_id}
    elif message.audio:
        media_info = {'type': 'audio', 'file_id': message.audio.file_id}
    elif message.video:
        media_info = {'type': 'video', 'file_id': message.video.file_id}
    elif message.document and message.document.mime_type.startswith(('audio', 'video')):
        media_info = {'type': 'document', 'file_id': message.document.file_id}
    
    if media_info:
        process_media(message.chat.id, media_info)

def process_media(chat_id, media_info):
    """Handles the transcription and further processing of the media file."""
    message_id = media_info.get('message_id')  # This is not present for new uploads, but useful for retries/async.
    processing_msg = bot.send_message(chat_id, " Processing...", disable_notification=True)
    
    try:
        file_id = media_info['file_id']
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        user_lang_code = get_stt_user_lang_in_memory(str(chat_id))
        
        # Transcribe the audio
        transcription_result = transcribe_audio_file(downloaded_file, user_lang_code, processing_msg.message_id)
        
        # Send transcription
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text=f"✅ Transcription done:\n\n{transcription_result}"
        )

    except Exception as e:
        bot.send_message(chat_id, f"❌ An error occurred during processing: {str(e)}")

# ----------------- WEBHOOK -----------------
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

# ----------------- BOT COMMANDS -----------------
def set_bot_commands():
    commands = [
        BotCommand("start", "👋 Get Started"),
        BotCommand("lang", "Set STT File language"),
        BotCommand("help", "How to use"),
        #BotCommand("admin", "Admin panel (admin only)")
    ]
    try:
        bot.set_my_commands(commands)
        logging.info("Bot commands set successfully.")
    except Exception as e:
        logging.error(f"Failed to set bot commands: {e}")

# ----------------- STARTUP -----------------
def set_bot_info_and_startup():
    set_webhook_on_startup()
    set_bot_commands()

def set_webhook_on_startup():
    try:
        bot.delete_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Webhook set successfully to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)))
