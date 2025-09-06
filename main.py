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

# --- Voice mapping (human readable) ---
# I added the new HD voices (DragonHDLatestNeural) using the SSML persona:basemodel format.
VOICE_MAPPING = {
    # (existing mappings kept as-is; add HD variants below)
    "af-ZA-AdriNeural": "Adri - Afrikaans (South Africa)",
    "af-ZA-WillemNeural": "Willem - Afrikaans (South Africa)",
    # ... (keep your full original mapping entries) ...
    "zh-CN-XiaoxiaoNeural": "Xiaoxiao - Chinese (Mandarin, Simplified)",
    # --- New HD Latest voices (DragonHDLatestNeural) ---
    "en-US-Andrew:DragonHDLatestNeural": "Andrew - Dragon HD Latest (English, US)",
    "en-US-Ava:DragonHDLatestNeural": "Ava - Dragon HD Latest (English, US)",
    "en-US-Emma:DragonHDLatestNeural": "Emma - Dragon HD Latest (English, US)",
    "en-US-Adam:DragonHDLatestNeural": "Adam - Dragon HD Latest (English, US)",
    "en-US-Andrew2:DragonHDLatestNeural": "Andrew2 - Dragon HD Latest (English, US)",
    "en-US-Brian:DragonHDLatestNeural": "Brian - Dragon HD Latest (English, US)",
    "en-US-Davis:DragonHDLatestNeural": "Davis - Dragon HD Latest (English, US)",
    "en-US-Emma2:DragonHDLatestNeural": "Emma2 - Dragon HD Latest (English, US)",
    "en-US-Steffan:DragonHDLatestNeural": "Steffan - Dragon HD Latest (English, US)",
    "en-US-Alloy:DragonHDLatestNeural": "Alloy - Dragon HD Latest (English, US)",
    "en-US-Andrew3:DragonHDLatestNeural": "Andrew3 - Dragon HD Latest (English, US)",
    "en-US-Aria:DragonHDLatestNeural": "Aria - Dragon HD Latest (English, US)",
    "en-US-Ava3:DragonHDLatestNeural": "Ava3 - Dragon HD Latest (English, US)",
    "en-US-Bree:DragonHDLatestNeural": "Bree - Dragon HD Latest (English, US)",
    "en-US-Phoebe:DragonHDLatestNeural": "Phoebe - Dragon HD Latest (English, US)",
    "en-US-Serena:DragonHDLatestNeural": "Serena - Dragon HD Latest (English, US)",
    # Other languages HD examples from the Microsoft post:
    "fr-FR-Remy:DragonHDLatestNeural": "Remy - Dragon HD Latest (French, FR)",
    "fr-FR-Vivienne:DragonHDLatestNeural": "Vivienne - Dragon HD Latest (French, FR)",
    "de-DE-Florian:DragonHDLatestNeural": "Florian - Dragon HD Latest (German, DE)",
    "de-DE-Seraphina:DragonHDLatestNeural": "Seraphina - Dragon HD Latest (German, DE)",
    "ja-JP-Masaru:DragonHDLatestNeural": "Masaru - Dragon HD Latest (Japanese, JP)",
    "ja-JP-Nanami:DragonHDLatestNeural": "Nanami - Dragon HD Latest (Japanese, JP)",
    "zh-CN-Xiaochen:DragonHDLatestNeural": "Xiaochen - Dragon HD Latest (Chinese, CN)",
    # (you can add more HD voices here as they become available)
}

# --- TTS voices by language (includes existing + new HD voices) ---
TTS_VOICES_BY_LANGUAGE = {
    "Afrikaans": ["af-ZA-AdriNeural", "af-ZA-WillemNeural"],
    "Amharic": ["am-ET-AmehaNeural", "am-ET-MekdesNeural"],
    "Arabic": ["ar-DZ-AminaNeural", "ar-DZ-IsmaelNeural", "ar-BH-AliNeural", "ar-BH-LailaNeural"],
    # ... (keep the rest of your prior languages) ...
    "English": [
        # existing standard voices (examples)
        "en-AU-WilliamMultilingualNeural", "en-AU-NatashaNeural", "en-CA-ClaraNeural",
        "en-GB-LibbyNeural", "en-GB-MaisieNeural", "en-US-AvaNeural", "en-US-AndrewNeural",
        # --- Add HD Latest English personas ---
        "en-US-Andrew:DragonHDLatestNeural", "en-US-Ava:DragonHDLatestNeural", "en-US-Emma:DragonHDLatestNeural",
        "en-US-Adam:DragonHDLatestNeural", "en-US-Brian:DragonHDLatestNeural", "en-US-Davis:DragonHDLatestNeural",
        "en-US-Aria:DragonHDLatestNeural", "en-US-Phoebe:DragonHDLatestNeural", "en-US-Serena:DragonHDLatestNeural",
        # You can keep adding HD variants here...
    ],
    "French": ["fr-FR-RemyMultilingualNeural", "fr-FR-VivienneMultilingualNeural", "fr-FR-Remy:DragonHDLatestNeural", "fr-FR-Vivienne:DragonHDLatestNeural"],
    "German": ["de-DE-FlorianMultilingualNeural", "de-DE-SeraphinaMultilingualNeural", "de-DE-Florian:DragonHDLatestNeural", "de-DE-Seraphina:DragonHDLatestNeural"],
    "Japanese": ["ja-JP-KeitaNeural", "ja-JP-NanamiNeural", "ja-JP-Masaru:DragonHDLatestNeural", "ja-JP-Nanami:DragonHDLatestNeural"],
    "Chinese": ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-Xiaochen:DragonHDLatestNeural"],
    # ... (other languages remain as before) ...
}

MOST_USED = [
    "English", "Chinese", "Spanish", "Arabic", "Portuguese", "Indonesian", "French", "Russian",
    "Japanese", "German", "Vietnamese", "Turkish", "Korean", "Italian", "Polish", "Dutch",
    "Persian", "Hindi", "Urdu", "Bengali", "Filipino", "Malay", "Thai", "Romanian", "Ukrainian"
]

ORDERED_TTS_LANGUAGES = [l for l in MOST_USED if l in TTS_VOICES_BY_LANGUAGE] + sorted([l for l in TTS_VOICES_BY_LANGUAGE.keys() if l not in MOST_USED])

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
    return settings.get("voice", "en-US-AvaMultilingualNeural") if settings else "en-US-AvaMultilingualNeural"

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

@bot.message_handler(commands=['admin'])
def admin_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 This command is restricted to the admin only.")
        return
    update_user_activity(message.from_user.id)
    admin_markup = InlineKeyboardMarkup()
    admin_markup.add(
        InlineKeyboardButton("Send Broadcast", callback_data="admin_broadcast"),
        InlineKeyboardButton("Total Users", callback_data="admin_total_users")
    )
    bot.send_message(
        message.chat.id,
        "Welcome to the Admin Panel! Choose an action:",
        reply_markup=admin_markup
    )

@bot.message_handler(commands=['help'])
def help_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    help_text = (
        "Not available ❌"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['privacy'])
def privacy_notice_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    privacy_text = (
        "Not Available ❌"
    )
    bot.send_message(message.chat.id, privacy_text, parse_mode="Markdown")

@bot.message_handler(commands=['voices_list'])
def voices_list_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 This command is restricted to the admin only.")
        return
    update_user_activity(message.from_user.id)
    bot.send_message(message.chat.id, "🔄 Generating the voice list, please wait...")
    threading.Thread(
        target=lambda: asyncio.run(generate_and_send_voice_list(message.chat.id))
    ).start()

async def generate_and_send_voice_list(chat_id: int):
    try:
        voices_manager = await VoicesManager.create()
        voices = voices_manager.find()
        voices_by_language = {}
        for voice in voices:
            lang_code = voice['Locale'].split('-')[0] if '-' in voice['Locale'] else voice['Locale']
            lang_name = lang_code.capitalize()
            if lang_name not in voices_by_language:
                voices_by_language[lang_name] = []
            styles = voice.get('StyleList', ['default'])
            if not isinstance(styles, list):
                styles = ['default']
            voices_by_language[lang_name].append({
                'name': voice['ShortName'],
                'gender': voice.get('Gender', 'Unknown'),
                'styles': styles
            })
        sorted_languages = sorted(voices_by_language.keys())
        output_lines = ["Microsoft Text-to-Speech Voices and Styles by Language\n"]
        output_lines.append("=" * 50 + "\n")
        for lang in sorted_languages:
            output_lines.append(f"Language: {lang}\n")
            output_lines.append("-" * 30 + "\n")
            for voice in voices_by_language[lang]:
                output_lines.append(f"Voice Name: {voice['name']}\n")
                output_lines.append(f"Gender: {voice['gender']}\n")
                output_lines.append(f"Styles: {', '.join(voice['styles'])}\n")
                output_lines.append("\n")
            output_lines.append("\n")
        filename = f"voices_list_{uuid.uuid4()}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.writelines(output_lines)
        with open(filename, 'rb') as f:
            bot.send_document(
                chat_id,
                f,
                caption="📋 List of Microsoft Text-to-Speech voices and their styles by language."
            )
        try:
            os.remove(filename)
            logging.info(f"Deleted temporary voice list file: {filename}")
        except Exception as e:
            logging.error(f"Error deleting voice list file {filename}: {e}")
    except Exception as e:
        logging.error(f"Error generating voice list: {e}")
        bot.send_message(chat_id, f"❌ Failed to generate voice list: {str(e)}")

@bot.callback_query_handler(lambda c: c.data in ["admin_total_users", "admin_broadcast"] and c.from_user.id == ADMIN_ID)
def admin_menu_callback(call):
    chat_id = call.message.chat.id
    if call.data == "admin_total_users":
        total_registered = users_collection.count_documents({})
        bot.send_message(chat_id, f"Total registered users: {total_registered}")
    elif call.data == "admin_broadcast":
        admin_state[call.from_user.id] = 'awaiting_broadcast_message'
        bot.send_message(chat_id, "Send the broadcast message now:")
    bot.answer_callback_query(call.id)

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and admin_state.get(m.from_user.id) == 'awaiting_broadcast_message',
    content_types=['text', 'photo', 'video', 'audio', 'document']
)
def broadcast_message(message):
    admin_state[message.from_user.id] = None
    success = fail = 0
    all_users = users_collection.find({}, {"_id": 1})
    for user_doc in all_users:
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
    bot.send_message(
        message.chat.id,
        f"Broadcast complete.\nSuccessful: {success}\nFailed: {fail}"
    )

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

def make_pitch_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⬆️ High", callback_data="pitch_set|+50"),
        InlineKeyboardButton("⬇️ Lower", callback_data="pitch_set|-50"),
        InlineKeyboardButton("🔄 Reset", callback_data="pitch_set|0")
    )
    return markup

def make_rate_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚡️ Speed", callback_data="rate_set|+50"),
        InlineKeyboardButton("🐢 Slow down", callback_data="rate_set|-50"),
        InlineKeyboardButton("🔄 Reset", callback_data="rate_set|0")
    )
    return markup

def handle_rate_command(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = "awaiting_rate_input"
    bot.send_message(
        chat_id,
        "How fast or slow should I speak? Choose one or send a number from -100 (slow) to +100 (fast), 0 is normal:",
        reply_markup=make_rate_keyboard()
    )

@bot.message_handler(commands=['rate'])
def cmd_voice_rate(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_rate_command(message)

@bot.callback_query_handler(lambda c: c.data.startswith("rate_set|"))
def on_rate_set_callback(call):
    user_id = str(call.from_user.id)
    update_user_activity(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_rate_input_mode[user_id] = None
    try:
        _, rate_value_str = call.data.split("|", 1)
        rate_value = int(rate_value_str)
        set_tts_user_rate(user_id, rate_value)
        bot.answer_callback_query(call.id, f"The rate is {rate_value}!")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🔊 Speech rate is *{rate_value}*.\n\nReady for text? Or use `/voice` to change the voice.",
            parse_mode="Markdown",
            reply_markup=None
        )
    except ValueError:
        bot.answer_callback_query(call.id, "Invalid rate.")
    except Exception as e:
        logging.error(f"Error setting rate: {e}")
        bot.answer_callback_query(call.id, "An error occurred.")

def handle_pitch_command(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = "awaiting_pitch_input"
    user_rate_input_mode[user_id] = None
    bot.send_message(
        chat_id,
        "Let's adjust the pitch! Choose one or send a number from -100 (low) to +100 (high), 0 is normal:",
        reply_markup=make_pitch_keyboard()
    )

@bot.message_handler(commands=['pitch'])
def cmd_voice_pitch(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    handle_pitch_command(message)

@bot.callback_query_handler(lambda c: c.data.startswith("pitch_set|"))
def on_pitch_set_callback(call):
    user_id = str(call.from_user.id)
    update_user_activity(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_pitch_input_mode[user_id] = None
    try:
        _, pitch_value_str = call.data.split("|", 1)
        pitch_value = int(pitch_value_str)
        set_tts_user_pitch(user_id, pitch_value)
        bot.answer_callback_query(call.id, f"The pitch is {pitch_value}!")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🔊 The pitch is *{pitch_value}*.\n\nReady for text? Or use `/voice` to change the voice.",
            parse_mode="Markdown",
            reply_markup=None
        )
    except ValueError:
        bot.answer_callback_query(call.id, "Invalid pitch.")
    except Exception as e:
        logging.error(f"Error setting pitch: {e}")
        bot.answer_callback_query(call.id, "An error occurred.")

def handle_voice_command(message):
    chat_id = message.chat.id
    user_id = str(message.from_user.id)
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    bot.send_message(chat_id, "First, choose the *language* of your voice. 👇", reply_markup=make_tts_language_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['voice'])
def cmd_text_to_speech(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_voice_command(message)

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

@bot.callback_query_handler(lambda c: c.data == "tts_back_to_languages")
def on_tts_back_to_languages(call):
    user_id = str(call.from_user.id)
    update_user_activity(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="Choose the *language* of your voice. 👇",
        reply_markup=make_tts_language_keyboard(),
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

async def synth_and_send_tts(chat_id: int, user_id: str, text: str):
    voice = get_tts_user_voice(user_id)
    if voice.startswith("so-"):
        text = text.replace('.', ',')
    pitch_val = get_tts_user_pitch(user_id)
    rate_val = get_tts_user_rate(user_id)
    filename = f"tts_{user_id}_{uuid.uuid4()}.mp3"
    stop_recording = threading.Event()
    recording_thread = threading.Thread(target=keep_recording, args=(chat_id, stop_recording, bot))
    recording_thread.daemon = True
    recording_thread.start()
    try:
        # Pitch/Rate formatting kept as before.
        pitch = f"{pitch_val}Hz" if pitch_val != 0 else "+0Hz"
        rate = f"+{rate_val}%" if rate_val >= 0 else f"{rate_val}%"
        # edge-tts.Communicate accepts the voice string; for HD voices use the persona:basemodel string
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(filename)
        if not os.path.exists(filename) or os.path.getsize(filename) == 0:
            bot.send_message(chat_id, "❌ Failed to create the audio. The text may be invalid. Please try a different text.")
            return
        with open(filename, "rb") as f:
            voice_display_name = VOICE_MAPPING.get(voice, voice)
            caption_text = (
                f"🎧 *Here is your voice!* \n\n"
                f"Voice: **{voice_display_name}**\n"
                f"Pitch: *{pitch}*\n"
                f"Rate: *{rate}*\n\n"
                f"Enjoy listening!✨ Follow me on TikTok: http://www.tiktok.com/@zack3d?lang=x-gent"
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
        bot.send_message(chat_id, f"❌ Unexpected error: {str(e)}. Please wait until this problem is fixed can take some time.")
    finally:
        stop_recording.set()
        if os.path.exists(filename):
            try:
                os.remove(filename)
                logging.info(f"Deleted temporary TTS file: {filename}")
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
    if user_rate_input_mode.get(user_id) == "awaiting_rate_input":
        try:
            rate_val = int(message.text)
            if -100 <= rate_val <= 100:
                set_tts_user_rate(user_id, rate_val)
                bot.send_message(message.chat.id, f"🔊 The speech rate is *{rate_val}*.", parse_mode="Markdown")
                user_rate_input_mode[user_id] = None
            else:
                bot.send_message(message.chat.id, "❌ Invalid rate. Send a number from -100 to +100 or 0. Try again:")
            return
        except ValueError:
            bot.send_message(message.chat.id, "That is not a valid number. Send a number from -100 to +100 or 0. Try again:")
            return
    if user_pitch_input_mode.get(user_id) == "awaiting_pitch_input":
        try:
            pitch_val = int(message.text)
            if -100 <= pitch_val <= 100:
                set_tts_user_pitch(user_id, pitch_val)
                bot.send_message(message.chat.id, f"🔊 The pitch is *{pitch_val}*.", parse_mode="Markdown")
                user_pitch_input_mode[user_id] = None
            else:
                bot.send_message(message.chat.id, "❌ Invalid pitch. Send a number from -100 to +100 or 0. Try again:")
            return
        except ValueError:
            bot.send_message(message.chat.id, "That is not a valid number. Send a number from -100 to +100 or 0. Try again:")
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

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document', 'sticker', 'photo'])
def handle_unsupported_media_types(message):
    user_id = str(message.from_user.id)
    update_user_activity(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    bot.send_message(
        message.chat.id,
        "⚠️ I only convert *text* to audio. Send me text to convert to speech!"
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
        BotCommand("voice", "Choose a different voice"),
        BotCommand("pitch", "Change voice pitch"),
        BotCommand("rate", "Change voice speed"),
        #BotCommand("help", "how to use info"),
    ]
    try:
        bot.set_my_commands(commands)
        logging.info("Main bot commands set successfully.")
    except Exception as e:
        logging.error(f"Failed to set main bot commands: {e}")

def set_webhook_on_startup():
    try:
        bot.delete_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Main bot webhook set successfully to {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set main bot webhook on startup: {e}")

def set_bot_info_and_startup():
    set_webhook_on_startup()
    set_bot_commands()

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
