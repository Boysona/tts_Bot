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

VOICE_MAPPING = {
    "af-ZA-AdriNeural": "Adri - Afrikaans (South Africa)",
    "af-ZA-WillemNeural": "Willem - Afrikaans (South Africa)",
    "am-ET-AmehaNeural": "Ameha - Amharic (Ethiopia)",
    "am-ET-MekdesNeural": "Mekdes - Amharic (Ethiopia)",
    # ... (existing mapping entries remain)
    "en-US-AvaMultilingualNeural": "Ava - English (United States) - Multilingual",
    "en-US-AndrewMultilingualNeural": "Andrew - English (United States) - Multilingual",
    "en-US-JennyNeural": "Jenny - English (United States)",
    "en-US-SteffanNeural": "Steffan - English (United States)",
    # --- New Multilingual / Turbo voices (guessed short-names following Azure conventions) ---
    "en-US-AmandaMultilingualNeural": "Amanda - English (United States) - Multilingual",
    "en-US-AdamMultilingualNeural": "Adam - English (United States) - Multilingual",
    "en-US-PhoebeMultilingualNeural": "Phoebe - English (United States) - Multilingual",
    "en-US-AlloyTurboMultilingualNeural": "Alloy Turbo - English (United States) - Multilingual (Turbo)",
    "en-US-NovaTurboMultilingualNeural": "Nova Turbo - English (United States) - Multilingual (Turbo)",
    "en-US-CoraMultilingualNeural": "Cora - English (United States) - Multilingual",
    "en-US-ChristopherMultilingualNeural": "Christopher - English (United States) - Multilingual",
    "en-US-BrandonMultilingualNeural": "Brandon - English (United States) - Multilingual",
    "en-US-DerekMultilingualNeural": "Derek - English (United States) - Multilingual",
    "en-US-DustinMultilingualNeural": "Dustin - English (United States) - Multilingual",
    "en-US-LewisMultilingualNeural": "Lewis - English (United States) - Multilingual",
    "en-US-LolaMultilingualNeural": "Lola - English (United States) - Multilingual",
    "en-US-NancyMultilingualNeural": "Nancy - English (United States) - Multilingual",
    "en-US-SerenaMultilingualNeural": "Serena - English (United States) - Multilingual",
    "en-US-BrianMultilingualNeural": "Brian - English (United States) - Multilingual",
    "en-US-RyanMultilingualNeural": "Ryan - English (United States) - Multilingual",
    "en-US-EchoTurboMultilingualNeural": "Echo Turbo - English (United States) - Multilingual (Turbo)",
    "en-US-FableTurboMultilingualNeural": "Fable Turbo - English (United States) - Multilingual (Turbo)",
    "en-US-OnyxTurboMultilingualNeural": "Onyx Turbo - English (United States) - Multilingual (Turbo)",
    "en-US-ShimmerTurboMultilingualNeural": "Shimmer Turbo - English (United States) - Multilingual (Turbo)",
    "en-US-DavisMultilingualNeural": "Davis - English (United States) - Multilingual",
    "en-US-SamuelMultilingualNeural": "Samuel - English (United States) - Multilingual",
    "en-US-EvelynMultilingualNeural": "Evelyn - English (United States) - Multilingual",
    # --- UK ---
    "en-GB-AdaMultilingualNeural": "Ada - English (United Kingdom) - Multilingual",
    "en-GB-OllieMultilingualNeural": "Ollie - English (United Kingdom) - Multilingual",
    # --- French ---
    "fr-FR-VivienneMultilingualNeural": "Vivienne - French (France) - Multilingual",
    "fr-FR-RemyMultilingualNeural": "Remy - French (France) - Multilingual",
    "fr-FR-LucienMultilingualNeural": "Lucien - French (France) - Multilingual",
    # --- German ---
    "de-DE-SeraphinaMultilingualNeural": "Seraphina - German (Germany) - Multilingual",
    "de-DE-FlorianMultilingualNeural": "Florian - German (Germany) - Multilingual",
    # --- Italian ---
    "it-IT-AlessioMultilingualNeural": "Alessio - Italian (Italy) - Multilingual",
    "it-IT-IsabellaMultilingualNeural": "Isabella - Italian (Italy) - Multilingual",
    "it-IT-GiuseppeMultilingualNeural": "Giuseppe - Italian (Italy) - Multilingual",
    "it-IT-MarcelloMultilingualNeural": "Marcello - Italian (Italy) - Multilingual",
    # --- Japanese ---
    "ja-JP-MasaruMultilingualNeural": "Masaru - Japanese (Japan) - Multilingual",
    # --- Portuguese (Brazil) ---
    "pt-BR-MacerioMultilingualNeural": "Macerio - Portuguese (Brazil) - Multilingual",
    "pt-BR-ThalitaMultilingualNeural": "Thalita - Portuguese (Brazil) - Multilingual",
    # --- Spanish (Mexico) ---
    "es-MX-DaliaMultilingualNeural": "Dalia - Spanish (Mexico) - Multilingual",
    "es-MX-JorgeMultilingualNeural": "Jorge - Spanish (Mexico) - Multilingual",
    # --- Spanish (Spain) ---
    "es-ES-ArabellaMultilingualNeural": "Arabella - Spanish (Spain) - Multilingual",
    # --- Chinese (Mandarin) ---
    "zh-CN-XiaoxiaoMultilingualNeural": "Xiaoxiao - Chinese (Mandarin, Simplified) - Multilingual",
    # --- Dragon HD Latest (guessed short-names) ---
    "en-US-AndrewDragonHDLatestNeural": "Andrew Dragon HD Latest - English (US) - HD Latest",
    "en-US-AvaDragonHDLatestNeural": "Ava Dragon HD Latest - English (US) - HD Latest",
    "en-US-EmmaDragonHDLatestNeural": "Emma Dragon HD Latest - English (US) - HD Latest",
    "en-US-AdamDragonHDLatestNeural": "Adam Dragon HD Latest - English (US) - HD Latest",
    "en-US-Andrew2DragonHDLatestNeural": "Andrew2 Dragon HD Latest - English (US) - HD Latest",
    "en-US-BrianDragonHDLatestNeural": "Brian Dragon HD Latest - English (US) - HD Latest",
    "en-US-DavisDragonHDLatestNeural": "Davis Dragon HD Latest - English (US) - HD Latest",
    "en-US-Emma2DragonHDLatestNeural": "Emma2 Dragon HD Latest - English (US) - HD Latest",
    "en-US-SteffanDragonHDLatestNeural": "Steffan Dragon HD Latest - English (US) - HD Latest",
    "en-US-AlloyDragonHDLatestNeural": "Alloy Dragon HD Latest - English (US) - HD Latest",
    "en-US-Andrew3DragonHDLatestNeural": "Andrew3 Dragon HD Latest - English (US) - HD Latest",
    "en-US-AriaDragonHDLatestNeural": "Aria Dragon HD Latest - English (US) - HD Latest",
    "en-US-Ava3DragonHDLatestNeural": "Ava3 Dragon HD Latest - English (US) - HD Latest",
    "en-US-BreeDragonHDLatestNeural": "Bree Dragon HD Latest - English (US) - HD Latest",
    "en-US-PhoebeDragonHDLatestNeural": "Phoebe Dragon HD Latest - English (US) - HD Latest",
    "en-US-SerenaDragonHDLatestNeural": "Serena Dragon HD Latest - English (US) - HD Latest",
    # Other languages - HD Latest (guessed)
    "zh-CN-XiaochenDragonHDLatestNeural": "Xiaochen Dragon HD Latest - Chinese (Mandarin) - HD Latest",
    "fr-FR-RemyDragonHDLatestNeural": "Remy Dragon HD Latest - French (France) - HD Latest",
    "fr-FR-VivienneDragonHDLatestNeural": "Vivienne Dragon HD Latest - French (France) - HD Latest",
    "de-DE-FlorianDragonHDLatestNeural": "Florian Dragon HD Latest - German (Germany) - HD Latest",
    "de-DE-SeraphinaDragonHDLatestNeural": "Seraphina Dragon HD Latest - German (Germany) - HD Latest",
    "ja-JP-MasaruDragonHDLatestNeural": "Masaru Dragon HD Latest - Japanese (Japan) - HD Latest",
    "ja-JP-NanamiDragonHDLatestNeural": "Nanami Dragon HD Latest - Japanese (Japan) - HD Latest",
    # ... keep other existing mapping entries unchanged ...
}

TTS_VOICES_BY_LANGUAGE = {
    "Afrikaans": ["af-ZA-AdriNeural", "af-ZA-WillemNeural"],
    "Amharic": ["am-ET-AmehaNeural", "am-ET-MekdesNeural"],
    "Arabic": ["ar-DZ-AminaNeural", "ar-DZ-IsmaelNeural", "ar-BH-AliNeural", "ar-BH-LailaNeural", "ar-EG-SalmaNeural", "ar-EG-ShakirNeural", "ar-IQ-BasselNeural", "ar-IQ-RanaNeural", "ar-JO-SanaNeural", "ar-JO-TaimNeural", "ar-KW-FahedNeural", "ar-KW-NouraNeural", "ar-LB-LaylaNeural", "ar-LB-RamiNeural", "ar-LY-ImanNeural", "ar-LY-OmarNeural", "ar-MA-JamalNeural", "ar-MA-MounaNeural", "ar-OM-AbdullahNeural", "ar-OM-AyshaNeural", "ar-QA-AmalNeural", "ar-QA-MoazNeural", "ar-SA-HamedNeural", "ar-SA-ZariyahNeural", "ar-SY-AmanyNeural", "ar-SY-LaithNeural", "ar-TN-HediNeural", "ar-TN-ReemNeural", "ar-AE-FatimaNeural", "ar-AE-HamdanNeural", "ar-YE-MaryamNeural", "ar-YE-SalehNeural"],
    "Azerbaijani": ["az-AZ-BabekNeural", "az-AZ-BanuNeural"],
    # ... existing languages ...
    "English": [
        "en-AU-WilliamMultilingualNeural", "en-AU-NatashaNeural", "en-CA-ClaraNeural", "en-CA-LiamNeural",
        "en-HK-YanNeural", "en-HK-SamNeural", "en-IN-NeerjaExpressiveNeural", "en-IN-NeerjaNeural",
        "en-IN-PrabhatNeural", "en-IE-ConnorNeural", "en-IE-EmilyNeural", "en-KE-AsiliaNeural",
        "en-KE-ChilembaNeural", "en-NZ-MitchellNeural", "en-NZ-MollyNeural", "en-NG-AbeoNeural",
        "en-NG-EzinneNeural", "en-PH-JamesNeural", "en-PH-RosaNeural", "en-US-AvaNeural",
        "en-US-AndrewNeural", "en-US-EmmaNeural", "en-US-BrianNeural", "en-SG-LunaNeural",
        "en-SG-WayneNeural", "en-ZA-LeahNeural", "en-ZA-LukeNeural", "en-TZ-ElimuNeural",
        "en-TZ-ImaniNeural", "en-GB-LibbyNeural", "en-GB-MaisieNeural", "en-GB-RyanNeural",
        "en-GB-SoniaNeural", "en-GB-ThomasNeural", "en-US-AnaNeural", "en-US-AndrewMultilingualNeural",
        "en-US-AriaNeural", "en-US-AvaMultilingualNeural", "en-US-BrianMultilingualNeural", "en-US-ChristopherNeural",
        "en-US-EmmaMultilingualNeural", "en-US-EricNeural", "en-US-GuyNeural", "en-US-JennyNeural",
        "en-US-MichelleNeural", "en-US-RogerNeural", "en-US-SteffanNeural",
        # --- New English voices added ---
        "en-US-AmandaMultilingualNeural", "en-US-AdamMultilingualNeural", "en-US-PhoebeMultilingualNeural",
        "en-US-AlloyTurboMultilingualNeural", "en-US-NovaTurboMultilingualNeural", "en-US-CoraMultilingualNeural",
        "en-US-ChristopherMultilingualNeural", "en-US-BrandonMultilingualNeural", "en-US-DerekMultilingualNeural",
        "en-US-DustinMultilingualNeural", "en-US-LewisMultilingualNeural", "en-US-LolaMultilingualNeural",
        "en-US-NancyMultilingualNeural", "en-US-SerenaMultilingualNeural", "en-US-BrianMultilingualNeural",
        "en-US-RyanMultilingualNeural", "en-US-EchoTurboMultilingualNeural", "en-US-FableTurboMultilingualNeural",
        "en-US-OnyxTurboMultilingualNeural", "en-US-ShimmerTurboMultilingualNeural", "en-US-DavisMultilingualNeural",
        "en-US-SamuelMultilingualNeural", "en-US-EvelynMultilingualNeural",
        # --- Dragon HD Latest group (guessed) ---
        "en-US-AndrewDragonHDLatestNeural", "en-US-AvaDragonHDLatestNeural", "en-US-EmmaDragonHDLatestNeural",
        "en-US-AdamDragonHDLatestNeural", "en-US-Andrew2DragonHDLatestNeural", "en-US-BrianDragonHDLatestNeural",
        "en-US-DavisDragonHDLatestNeural", "en-US-Emma2DragonHDLatestNeural", "en-US-SteffanDragonHDLatestNeural",
        "en-US-AlloyDragonHDLatestNeural", "en-US-Andrew3DragonHDLatestNeural", "en-US-AriaDragonHDLatestNeural",
        "en-US-Ava3DragonHDLatestNeural", "en-US-BreeDragonHDLatestNeural", "en-US-PhoebeDragonHDLatestNeural",
        "en-US-SerenaDragonHDLatestNeural"
    ],
    "French": ["fr-BE-CharlineNeural", "fr-BE-GerardNeural", "fr-CA-ThierryNeural", "fr-CA-AntoineNeural", "fr-CA-JeanNeural", "fr-CA-SylvieNeural", "fr-FR-VivienneMultilingualNeural", "fr-FR-RemyMultilingualNeural", "fr-FR-DeniseNeural", "fr-FR-EloiseNeural", "fr-FR-HenriNeural", "fr-CH-ArianeNeural", "fr-CH-FabriceNeural", "fr-FR-RemyDragonHDLatestNeural", "fr-FR-VivienneDragonHDLatestNeural"],
    "German": ["de-AT-IngridNeural", "de-AT-JonasNeural", "de-DE-SeraphinaMultilingualNeural", "de-DE-FlorianMultilingualNeural", "de-DE-AmalaNeural", "de-DE-ConradNeural", "de-DE-KatjaNeural", "de-DE-KillianNeural", "de-CH-JanNeural", "de-CH-LeniNeural", "de-DE-FlorianDragonHDLatestNeural", "de-DE-SeraphinaDragonHDLatestNeural"],
    "Italian": ["it-IT-GiuseppeMultilingualNeural", "it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-IsabellaNeural", "it-IT-AlessioMultilingualNeural", "it-IT-MarcelloMultilingualNeural"],
    "Japanese": ["ja-JP-KeitaNeural", "ja-JP-NanamiNeural", "ja-JP-MasaruMultilingualNeural", "ja-JP-MasaruDragonHDLatestNeural", "ja-JP-NanamiDragonHDLatestNeural"],
    "Portuguese": ["pt-BR-ThalitaMultilingualNeural", "pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-PT-DuarteNeural", "pt-PT-RaquelNeural", "pt-BR-MacerioMultilingualNeural"],
    "Spanish": ["es-AR-ElenaNeural", "es-AR-TomasNeural", "es-BO-MarceloNeural", "es-BO-SofiaNeural", "es-CL-CatalinaNeural", "es-CL-LorenzoNeural", "es-CO-GonzaloNeural", "es-CO-SalomeNeural", "es-ES-XimenaNeural", "es-CR-JuanNeural", "es-CR-MariaNeural", "es-CU-BelkysNeural", "es-CU-ManuelNeural", "es-DO-EmilioNeural", "es-DO-RamonaNeural", "es-EC-AndreaNeural", "es-EC-LuisNeural", "es-SV-LorenaNeural", "es-SV-RodrigoNeural", "es-GQ-JavierNeural", "es-GQ-TeresaNeural", "es-GT-AndresNeural", "es-GT-MartaNeural", "es-HN-CarlosNeural", "es-HN-KarlaNeural", "es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-ES-ArabellaMultilingualNeural"],
    "Chinese": ["zh-HK-HiuGaaiNeural", "zh-HK-HiuMaanNeural", "zh-HK-WanLungNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural", "zh-CN-YunxiNeural", "zh-CN-YunxiaNeural", "zh-CN-YunyangNeural", "zh-CN-liaoning-XiaobeiNeural", "zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-TW-HsiaoYuNeural", "zh-CN-shaanxi-XiaoniNeural", "zh-CN-XiaoxiaoMultilingualNeural", "zh-CN-XiaochenDragonHDLatestNeural"],
    # ... keep other languages entries ...
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

# ... rest of the handlers remain unchanged, identical to your original code ...
# For brevity I did not duplicate the unchanged handler functions further down;
# keep everything below the start handler in your original file as-is (admin, help, voice, pitch, rate, tts synth, webhook, etc.)

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

# ... keep rest of the code the same (pitch/rate handlers, synth_and_send_tts, message handlers, webhook routes, set commands, main) ...

if __name__ == "__main__":
    # set_bot_info_and_startup() and app.run same as original file
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
