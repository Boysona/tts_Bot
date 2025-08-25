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

def get_stt_user_lang_in_memory(user_id: str) -> str:
    return in_memory_data["stt_settings"].get(user_id, {}).get("language_code")

def set_stt_user_lang_in_memory(user_id: str, lang_code: str):
    if user_id not in in_memory_data["stt_settings"]:
        in_memory_data["stt_settings"][user_id] = {}
    in_memory_data["stt_settings"][user_id]["language_code"] = lang_code

# ----------------- KEYBOARDS -----------------
def build_start_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(name, callback_data=f"start_select_lang|{code}") 
               for name, code in sorted(STT_LANGUAGES.items(), key=lambda k: (k[0] != "English 🇬🇧", k[0] != "العربية 🇸🇦", k[0]))]
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

# ----------------- MEDIA HANDLER -----------------
@bot.message_handler(content_types=['audio', 'voice', 'video', 'document'])
def media_handler(message):
    uid = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    lang_code = get_stt_user_lang_in_memory(uid)

    # If user hasn't set a language yet, ask first
    if not lang_code:
        markup = build_start_language_keyboard()
        msg = bot.send_message(message.chat.id, "Please select the language of your media first:", reply_markup=markup)
        # Save the media info to process after language selection
        in_memory_data.setdefault("pending_media", {})[uid] = {
            "file_id": None,
            "message": message,
        }
        if message.content_type in ['audio', 'voice', 'video', 'document']:
            file_id = getattr(message, message.content_type).file_id if hasattr(message, message.content_type) else None
            in_memory_data["pending_media"][uid]["file_id"] = file_id
        return

    # If language already set, process media immediately
    process_media_transcription(message, lang_code)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("start_select_lang|"))
def start_select_lang_callback(call):
    uid = str(call.from_user.id)
    _, lang_code = call.data.split("|", 1)
    set_stt_user_lang_in_memory(uid, lang_code)
    lang_name = next((name for name, code in STT_LANGUAGES.items() if code == lang_code), "Unknown")

    # Reply to user
    bot.answer_callback_query(call.id, f"Language set to {lang_name}")

    # If the user had pending media, process it now
    pending = in_memory_data.get("pending_media", {}).pop(uid, None)
    if pending and pending.get("message"):
        process_media_transcription(pending["message"], lang_code)
        try:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Language set to {lang_name}, processing your media...")
        except:
            bot.send_message(call.message.chat.id, f"Language set to {lang_name}, processing your media...")

# ----------------- MEDIA PROCESS FUNCTION -----------------
def process_media_transcription(message, lang_code):
    # Here you implement actual transcription call
    bot.send_message(message.chat.id, f"Transcribing your media in language: {lang_code} ...")
    # Example: get file link and send to AssemblyAI or your STT service
    # file_info = bot.get_file(message.audio.file_id)
    # file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
    # transcription = call_stt_service(file_url, lang_code)
    # bot.send_message(message.chat.id, f"Transcription Result:\n{transcription}")

# ----------------- WEBHOOK AND STARTUP -----------------
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
    ]
    try:
        bot.set_my_commands(commands)
        logging.info("Bot commands set successfully.")
    except Exception as e:
        logging.error(f"Failed to set bot commands: {e}")

def set_bot_info_and_startup():
    try:
        bot.delete_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Webhook set successfully to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")
    set_bot_commands()

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)))
