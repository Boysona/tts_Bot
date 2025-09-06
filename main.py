# main.py (HD test with en-US-AdamDragonHDLatestNeural as the only voice)
import uuid
import logging
import telebot
from flask import Flask, request, abort
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
import asyncio
import threading
import time
import os
import edge_tts
from edge_tts import VoicesManager
from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

TOKEN = "8281896922:AAEzRdF60SvTMyRba0ev4fzVvdY2ip-DStU"
ADMIN_ID = 6964068910
WEBHOOK_URL = "https://tts-bot-valv.onrender.com"
REQUIRED_CHANNEL = "@boyso20Channel"

# --- MongoDB Configuration ---
DB_USER = "lakicalinuur"
DB_PASSWORD = "DjReFoWZGbwjry8K"
DB_APPNAME = "SpeechBot"
MONGO_URI = f"mongodb+srv://{DB_USER}:{DB_PASSWORD}@cluster0.n4hdlxk.mongodb.net/?retryWrites=true&w=majority&appName={DB_APPNAME}"

client = MongoClient(MONGO_URI)
db = client[DB_APPNAME]
users_collection = db.users
tts_settings_collection = db.tts_settings
logging.info("Connected to MongoDB successfully.")
# --- End MongoDB Configuration ---

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

user_tts_mode = {}
user_pitch_input_mode = {}
user_rate_input_mode = {}
admin_state = {}

# --- Single test voice (shortname used by Azure/edge_tts) ---
VOICE_MAPPING = {
    "en-US-AdamDragonHDLatestNeural": "Adam Dragon HD Latest (en-US)"
}

TTS_VOICES_BY_LANGUAGE = {
    "HD Latest": ["en-US-AdamDragonHDLatestNeural"]
}

ORDERED_TTS_LANGUAGES = ["HD Latest"]
DEFAULT_HD_VOICE = "en-US-AdamDragonHDLatestNeural"
# -----------------------------------------------------------

def update_user_activity(user_id: int):
    user_id_str = str(user_id)
    now_iso = datetime.now().isoformat()
    users_collection.update_one(
        {"_id": user_id_str},
        {"$set": {"last_active": now_iso}, "$setOnInsert": {"_id": user_id_str, "tts_conversion_count": 0}},
        upsert=True
    )

def increment_processing_count(user_id: str):
    user_id_str = str(user_id)
    users_collection.update_one(
        {"_id": user_id_str},
        {"$inc": {"tts_conversion_count": 1}, "$set": {"last_active": datetime.now().isoformat()}},
        upsert=True
    )

def get_tts_user_voice(user_id: str) -> str:
    settings = tts_settings_collection.find_one({"_id": user_id})
    return settings.get("voice", DEFAULT_HD_VOICE) if settings else DEFAULT_HD_VOICE

def set_tts_user_voice(user_id: str, voice: str):
    tts_settings_collection.update_one(
        {"_id": user_id},
        {"$set": {"voice": voice}},
        upsert=True
    )

def get_tts_user_pitch(user_id: str) -> int:
    settings = tts_settings_collection.find_one({"_id": user_id})
    return settings.get("pitch", 0) if settings else 0

def set_tts_user_pitch(user_id: str, pitch: int):
    tts_settings_collection.update_one(
        {"_id": user_id},
        {"$set": {"pitch": pitch}},
        upsert=True
    )

def get_tts_user_rate(user_id: str) -> int:
    settings = tts_settings_collection.find_one({"_id": user_id})
    return settings.get("rate", 0) if settings else 0

def set_tts_user_rate(user_id: str, rate: int):
    tts_settings_collection.update_one(
        {"_id": user_id},
        {"$set": {"rate": rate}},
        upsert=True
    )

def keep_recording(chat_id, stop_event, target_bot):
    while not stop_event.is_set():
        try:
            target_bot.send_chat_action(chat_id, 'record_audio')
            time.sleep(4)
        except Exception as e:
            logging.error(f"Error sending record_audio action: {e}")
            break

def check_subscription(user_id: int) -> bool:
    if not REQUIRED_CHANNEL or not REQUIRED_CHANNEL.strip():
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Error checking subscription: {e}")
        return False

def send_subscription_message(chat_id: int):
    if not REQUIRED_CHANNEL or not REQUIRED_CHANNEL.strip():
        return
    try:
        chat = bot.get_chat(chat_id)
        if chat.type != 'private':
            return
    except Exception:
        return
    try:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Click here to join the Channel",
                url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"
            )
        )
        bot.send_message(
            chat_id,
            "🔒 Access Locked You cannot use this bot until you join the Channel.",
            reply_markup=markup
        )
    except Exception as e:
        logging.error(f"Error sending subscription message: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id_str = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    user_tts_mode[user_id_str] = None
    user_pitch_input_mode[user_id_str] = None
    user_rate_input_mode[user_id_str] = None
    
    markup = make_tts_language_keyboard()
    bot.send_message(
        message.chat.id,
        "👋 Welcome! Choose the voice actor from the options below. 👇",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['voice'])
def cmd_text_to_speech(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    handle_voice_command(message)

def make_tts_language_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for lang_name in ORDERED_TTS_LANGUAGES:
        if lang_name in TTS_VOICES_BY_LANGUAGE:
            buttons.append(
                InlineKeyboardButton(lang_name, callback_data=f"tts_lang|{lang_name}")
            )
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    return markup

def make_tts_voice_keyboard_for_language(lang_name: str):
    markup = InlineKeyboardMarkup(row_width=2)
    voices = TTS_VOICES_BY_LANGUAGE.get(lang_name, [])
    for voice in voices:
        display_name = VOICE_MAPPING.get(voice, voice)
        markup.add(InlineKeyboardButton(display_name, callback_data=f"tts_voice|{voice}"))
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="tts_back_to_languages"))
    return markup

def handle_voice_command(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    bot.send_message(chat_id, "First, choose the *language* of your voice. 👇", reply_markup=make_tts_language_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(lambda c: c.data.startswith("tts_lang|"))
def on_tts_language_select(call):
    user_id = str(call.from_user.id)
    update_user_activity(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    _, lang_name = call.data.split("|", 1)
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=f"Okay! Now choose a specific *voice* from {lang_name}. 👇",
        reply_markup=make_tts_voice_keyboard_for_language(lang_name),
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(lambda c: c.data.startswith("tts_voice|"))
def on_tts_voice_change(call):
    user_id = str(call.from_user.id)
    update_user_activity(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    _, voice = call.data.split("|", 1)
    set_tts_user_voice(user_id, voice)
    user_tts_mode[user_id] = voice
    current_pitch = get_tts_user_pitch(user_id)
    current_rate = get_tts_user_rate(user_id)
    voice_display_name = VOICE_MAPPING.get(voice, voice)
    bot.answer_callback_query(call.id, f"✔️ The voice is {voice_display_name}")
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=f"🔊 Great! You are using: *{voice_display_name}*.\n\n"
             f"Current settings:\n"
             f"• Pitch: *{current_pitch}*\n"
             f"• Rate: *{current_rate}*\n\n"
             f"Ready to speak? Send me text!",
        parse_mode="Markdown",
        reply_markup=None
    )

async def synth_and_send_tts(chat_id: int, user_id: str, text: str):
    voice = get_tts_user_voice(user_id)
    pitch_val = get_tts_user_pitch(user_id)
    rate_val = get_tts_user_rate(user_id)
    filename = f"tts_{user_id}_{uuid.uuid4()}.mp3"
    stop_recording = threading.Event()
    recording_thread = threading.Thread(target=keep_recording, args=(chat_id, stop_recording, bot))
    recording_thread.daemon = True
    recording_thread.start()
    try:
        pitch = f"{pitch_val}Hz" if pitch_val != 0 else "+0Hz"
        rate = f"+{rate_val}%" if rate_val >= 0 else f"{rate_val}%"
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(filename)
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            bot.send_message(chat_id, "❌ Failed to create the audio. The engine returned empty output. The voice name might be invalid for edge_tts.")
            return
        with open(filename, "rb") as f:
            voice_display_name = VOICE_MAPPING.get(voice, voice)
            caption_text = (
                f"🎧 *Here is your voice!* \n\n"
                f"Voice: **{voice_display_name}**\n"
                f"Pitch: *{pitch}*\n"
                f"Rate: *{rate}*\n\n"
                f"Enjoy listening!"
            )
            bot.send_audio(
                chat_id,
                f,
                caption=caption_text,
                parse_mode="Markdown"
            )
        increment_processing_count(user_id)
    except Exception as e:
        logging.error(f"TTS error: {str(e)}")
        bot.send_message(chat_id, f"❌ Unexpected error during synthesis: {str(e)}\nPossible cause: voice shortname mismatch or engine access.")
    finally:
        stop_recording.set()
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception as e:
                logging.error(f"Error deleting TTS file {filename}: {e}")

@bot.message_handler(content_types=['text'])
def handle_text_for_tts_or_mode_input(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    if message.text.startswith('/'):
        return
    current_voice = get_tts_user_voice(user_id)
    if current_voice:
        threading.Thread(
            target=lambda: asyncio.run(synth_and_send_tts(message.chat.id, user_id, message.text))
        ).start()
    else:
        bot.send_message(
            message.chat.id,
            "You haven't chosen a voice yet! Use `/voice` first, then send me text. 🗣️"
        )

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

def set_bot_commands():
    commands = [
        BotCommand("start", "👋 Get Started"),
        BotCommand("voice", "Choose a different voice"),
    ]
    try:
        bot.set_my_commands(commands)
        logging.info("Main bot commands set successfully.")
    except Exception as e:
        logging.error(f"Failed to set main bot commands: {e}")

if __name__ == "__main__":
    set_bot_commands()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
