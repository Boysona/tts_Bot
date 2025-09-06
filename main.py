# main.py (UPDATED — voices added)
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

# --- VOICE MAPPING (existing + newly added HD/Dragon voices) ---
VOICE_MAPPING = {
    "af-ZA-AdriNeural": "Adri - Afrikaans (South Africa)",
    "af-ZA-WillemNeural": "Willem - Afrikaans (South Africa)",
    "am-ET-AmehaNeural": "Ameha - Amharic (Ethiopia)",
    "am-ET-MekdesNeural": "Mekdes - Amharic (Ethiopia)",
    "ar-DZ-AminaNeural": "Amina - Arabic (Algeria)",
    "ar-DZ-IsmaelNeural": "Ismael - Arabic (Algeria)",
    "ar-BH-AliNeural": "Ali - Arabic (Bahrain)",
    "ar-BH-LailaNeural": "Laila - Arabic (Bahrain)",
    "ar-EG-SalmaNeural": "Salma - Arabic (Egypt)",
    "ar-EG-ShakirNeural": "Shakir - Arabic (Egypt)",
    "ar-IQ-BasselNeural": "Bassel - Arabic (Iraq)",
    "ar-IQ-RanaNeural": "Rana - Arabic (Iraq)",
    "ar-JO-SanaNeural": "Sana - Arabic (Jordan)",
    "ar-JO-TaimNeural": "Taim - Arabic (Jordan)",
    "ar-KW-FahedNeural": "Fahed - Arabic (Kuwait)",
    "ar-KW-NouraNeural": "Noura - Arabic (Kuwait)",
    "ar-LB-LaylaNeural": "Layla - Arabic (Lebanon)",
    "ar-LB-RamiNeural": "Rami - Arabic (Lebanon)",
    "ar-LY-ImanNeural": "Iman - Arabic (Libya)",
    "ar-LY-OmarNeural": "Omar - Arabic (Libya)",
    "ar-MA-JamalNeural": "Jamal - Arabic (Morocco)",
    "ar-MA-MounaNeural": "Mouna - Arabic (Morocco)",
    "ar-OM-AbdullahNeural": "Abdullah - Arabic (Oman)",
    "ar-OM-AyshaNeural": "Aysha - Arabic (Oman)",
    "ar-QA-AmalNeural": "Amal - Arabic (Qatar)",
    "ar-QA-MoazNeural": "Moaz - Arabic (Qatar)",
    "ar-SA-HamedNeural": "Hamed - Arabic (Saudi Arabia)",
    "ar-SA-ZariyahNeural": "Zariyah - Arabic (Saudi Arabia)",
    "ar-SY-AmanyNeural": "Amany - Arabic (Syria)",
    "ar-SY-LaithNeural": "Laith - Arabic (Syria)",
    "ar-TN-HediNeural": "Hedi - Arabic (Tunisia)",
    "ar-TN-ReemNeural": "Reem - Arabic (Tunisia)",
    "ar-AE-FatimaNeural": "Fatima - Arabic (UAE)",
    "ar-AE-HamdanNeural": "Hamdan - Arabic (UAE)",
    "ar-YE-MaryamNeural": "Maryam - Arabic (Yemen)",
    "ar-YE-SalehNeural": "Saleh - Arabic (Yemen)",
    "az-AZ-BabekNeural": "Babek - Azerbaijani (Azerbaijan)",
    "az-AZ-BanuNeural": "Banu - Azerbaijani (Azerbaijan)",
    "bg-BG-BorislavNeural": "Borislav - Bulgarian (Bulgaria)",
    "bg-BG-KalinaNeural": "Kalina - Bulgarian (Bulgaria)",
    "bn-BD-NabanitaNeural": "Nabanita - Bengali (Bangladesh)",
    "bn-BD-PradeepNeural": "Pradeep - Bengali (Bangladesh)",
    "bn-IN-BashkarNeural": "Bashkar - Bengali (India)",
    "bn-IN-TanishaaNeural": "Tanishaa - Bengali (India)",
    "bs-BA-VesnaNeural": "Vesna - Bosnian (Bosnia and Herzegovina)",
    "bs-BA-GoranNeural": "Goran - Bosnian (Bosnia and Herzegovina)",
    "ca-ES-EnricNeural": "Enric - Catalan (Spain)",
    "ca-ES-JoanaNeural": "Joana - Catalan (Spain)",
    "cs-CZ-AntoninNeural": "Antonin - Czech (Czech Republic)",
    "cs-CZ-VlastaNeural": "Vlasta - Czech (Czech Republic)",
    "cy-GB-AledNeural": "Aled - Welsh (United Kingdom)",
    "cy-GB-NiaNeural": "Nia - Welsh (United Kingdom)",
    "da-DK-ChristelNeural": "Christel - Danish (Denmark)",
    "da-DK-JeppeNeural": "Jeppe - Danish (Denmark)",
    "de-AT-IngridNeural": "Ingrid - German (Austria)",
    "de-AT-JonasNeural": "Jonas - German (Austria)",
    "de-DE-SeraphinaMultilingualNeural": "Seraphina - German (Germany) - Multilingual",
    "de-DE-FlorianMultilingualNeural": "Florian - German (Germany) - Multilingual",
    "de-DE-AmalaNeural": "Amala - German (Germany)",
    "de-DE-ConradNeural": "Conrad - German (Germany)",
    "de-DE-KatjaNeural": "Katja - German (Germany)",
    "de-DE-KillianNeural": "Killian - German (Germany)",
    "de-CH-JanNeural": "Jan - German (Switzerland)",
    "de-CH-LeniNeural": "Leni - German (Switzerland)",
    "el-GR-AthinaNeural": "Athina - Greek (Greece)",
    "el-GR-NestorasNeural": "Nestoras - Greek (Greece)",
    "en-AU-WilliamMultilingualNeural": "William - English (Australia) - Multilingual",
    "en-AU-NatashaNeural": "Natasha - English (Australia)",
    "en-CA-ClaraNeural": "Clara - English (Canada)",
    "en-CA-LiamNeural": "Liam - English (Canada)",
    "en-HK-YanNeural": "Yan - English (Hong Kong)",
    "en-HK-SamNeural": "Sam - English (Hong Kong)",
    "en-IN-NeerjaExpressiveNeural": "Neerja - English (India) - Expressive",
    "en-IN-NeerjaNeural": "Neerja - English (India)",
    "en-IN-PrabhatNeural": "Prabhat - English (India)",
    "en-IE-ConnorNeural": "Connor - English (Ireland)",
    "en-IE-EmilyNeural": "Emily - English (Ireland)",
    "en-KE-AsiliaNeural": "Asilia - English (Kenya)",
    "en-KE-ChilembaNeural": "Chilemba - English (Kenya)",
    "en-NZ-MitchellNeural": "Mitchell - English (New Zealand)",
    "en-NZ-MollyNeural": "Molly - English (New Zealand)",
    "en-NG-AbeoNeural": "Abeo - English (Nigeria)",
    "en-NG-EzinneNeural": "Ezinne - English (Nigeria)",
    "en-PH-JamesNeural": "James - English (Philippines)",
    "en-PH-RosaNeural": "Rosa - English (Philippines)",
    "en-US-AvaNeural": "Ava - English (United States)",
    "en-US-AndrewNeural": "Andrew - English (United States)",
    "en-US-EmmaNeural": "Emma - English (United States)",
    "en-US-BrianNeural": "Brian - English (United States)",
    "en-SG-LunaNeural": "Luna - English (Singapore)",
    "en-SG-WayneNeural": "Wayne - English (Singapore)",
    "en-ZA-LeahNeural": "Leah - English (South Africa)",
    "en-ZA-LukeNeural": "Luke - English (South Africa)",
    "en-TZ-ElimuNeural": "Elimu - English (Tanzania)",
    "en-TZ-ImaniNeural": "Imani - English (Tanzania)",
    "en-GB-LibbyNeural": "Libby - English (United Kingdom)",
    "en-GB-MaisieNeural": "Maisie - English (United Kingdom)",
    "en-GB-RyanNeural": "Ryan - English (United Kingdom)",
    "en-GB-SoniaNeural": "Sonia - English (United Kingdom)",
    "en-GB-ThomasNeural": "Thomas - English (United Kingdom)",
    "en-US-AnaNeural": "Ana - English (United States)",
    "en-US-AndrewMultilingualNeural": "Andrew - English (United States) - Multilingual",
    "en-US-AriaNeural": "Aria - English (United States)",
    "en-US-AvaMultilingualNeural": "Ava - English (United States) - Multilingual",
    "en-US-BrianMultilingualNeural": "Brian - English (United States) - Multilingual",
    "en-US-ChristopherNeural": "Christopher - English (United States)",
    "en-US-EmmaMultilingualNeural": "Emma - English (United States) - Multilingual",
    "en-US-EricNeural": "Eric - English (United States)",
    "en-US-GuyNeural": "Guy - English (United States)",
    "en-US-JennyNeural": "Jenny - English (United States)",
    "en-US-MichelleNeural": "Michelle - English (United States)",
    "en-US-RogerNeural": "Roger - English (United States)",
    "en-US-SteffanNeural": "Steffan - English (United States)",
    # --- NEW HD / Dragon voices added below ---
    "en-US-AndrewDragonHDLatestNeural": "Andrew Dragon HD Latest",
    "en-US-AvaDragonHDLatestNeural": "Ava Dragon HD Latest",
    "en-US-EmmaDragonHDLatestNeural": "Emma Dragon HD Latest",
    "en-US-AdamDragonHDLatestNeural": "Adam Dragon HD Latest",
    "en-US-Andrew2DragonHDLatestNeural": "Andrew2 Dragon HD Latest",
    "en-US-BrianDragonHDLatestNeural": "Brian Dragon HD Latest",
    "en-US-DavisDragonHDLatestNeural": "Davis Dragon HD Latest",
    "en-US-Emma2DragonHDLatestNeural": "Emma2 Dragon HD Latest",
    "en-US-SteffanDragonHDLatestNeural": "Steffan Dragon HD Latest",
    "en-US-AlloyDragonHDLatestNeural": "Alloy Dragon HD Latest",
    "en-US-Andrew3DragonHDLatestNeural": "Andrew3 Dragon HD Latest",
    "en-US-AriaDragonHDLatestNeural": "Aria Dragon HD Latest",
    "en-US-Ava3DragonHDLatestNeural": "Ava3 Dragon HD Latest",
    "en-US-BreeDragonHDLatestNeural": "Bree Dragon HD Latest",
    "en-US-PhoebeDragonHDLatestNeural": "Phoebe Dragon HD Latest",
    "en-US-SerenaDragonHDLatestNeural": "Serena Dragon HD Latest",
    # Other-language Dragon HD voices
    "zh-CN-XiaochenDragonHDLatestNeural": "Xiaochen Dragon HD Latest (Chinese, Mandarin)",
    "fr-FR-RemyDragonHDLatestNeural": "Remy Dragon HD Latest (French)",
    "fr-FR-VivienneDragonHDLatestNeural": "Vivienne Dragon HD Latest (French)",
    "de-DE-FlorianDragonHDLatestNeural": "Florian Dragon HD Latest (German)",
    "de-DE-SeraphinaDragonHDLatestNeural": "Seraphina Dragon HD Latest (German)",
    "ja-JP-MasaruDragonHDLatestNeural": "Masaru Dragon HD Latest (Japanese)",
    "ja-JP-NanamiDragonHDLatestNeural": "Nanami Dragon HD Latest (Japanese)"
    # --- end NEW voices ---
}

# --- TTS_VOICES_BY_LANGUAGE: add new short names to English and respective languages ---
TTS_VOICES_BY_LANGUAGE = {
    "Afrikaans": ["af-ZA-AdriNeural", "af-ZA-WillemNeural"],
    "Amharic": ["am-ET-AmehaNeural", "am-ET-MekdesNeural"],
    "Arabic": ["ar-DZ-AminaNeural", "ar-DZ-IsmaelNeural", "ar-BH-AliNeural", "ar-BH-LailaNeural", "ar-EG-SalmaNeural", "ar-EG-ShakirNeural", "ar-IQ-BasselNeural", "ar-IQ-RanaNeural", "ar-JO-SanaNeural", "ar-JO-TaimNeural", "ar-KW-FahedNeural", "ar-KW-NouraNeural", "ar-LB-LaylaNeural", "ar-LB-RamiNeural", "ar-LY-ImanNeural", "ar-LY-OmarNeural", "ar-MA-JamalNeural", "ar-MA-MounaNeural", "ar-OM-AbdullahNeural", "ar-OM-AyshaNeural", "ar-QA-AmalNeural", "ar-QA-MoazNeural", "ar-SA-HamedNeural", "ar-SA-ZariyahNeural", "ar-SY-AmanyNeural", "ar-SY-LaithNeural", "ar-TN-HediNeural", "ar-TN-ReemNeural", "ar-AE-FatimaNeural", "ar-AE-HamdanNeural", "ar-YE-MaryamNeural", "ar-YE-SalehNeural"],
    "Azerbaijani": ["az-AZ-BabekNeural", "az-AZ-BanuNeural"],
    "Bulgarian": ["bg-BG-BorislavNeural", "bg-BG-KalinaNeural"],
    "Bengali": ["bn-BD-NabanitaNeural", "bn-BD-PradeepNeural", "bn-IN-BashkarNeural", "bn-IN-TanishaaNeural"],
    "Bosnian": ["bs-BA-VesnaNeural", "bs-BA-GoranNeural"],
    "Catalan": ["ca-ES-EnricNeural", "ca-ES-JoanaNeural"],
    "Czech": ["cs-CZ-AntoninNeural", "cs-CZ-VlastaNeural"],
    "Welsh": ["cy-GB-AledNeural", "cy-GB-NiaNeural"],
    "Danish": ["da-DK-ChristelNeural", "da-DK-JeppeNeural"],
    "German": ["de-AT-IngridNeural", "de-AT-JonasNeural", "de-DE-SeraphinaMultilingualNeural", "de-DE-FlorianMultilingualNeural", "de-DE-AmalaNeural", "de-DE-ConradNeural", "de-DE-KatjaNeural", "de-DE-KillianNeural", "de-CH-JanNeural", "de-CH-LeniNeural", "de-DE-FlorianDragonHDLatestNeural", "de-DE-SeraphinaDragonHDLatestNeural"],
    "Greek": ["el-GR-AthinaNeural", "el-GR-NestorasNeural"],
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
        # Add new HD/Dragon English voices
        "en-US-AndrewDragonHDLatestNeural", "en-US-AvaDragonHDLatestNeural", "en-US-EmmaDragonHDLatestNeural",
        "en-US-AdamDragonHDLatestNeural", "en-US-Andrew2DragonHDLatestNeural", "en-US-BrianDragonHDLatestNeural",
        "en-US-DavisDragonHDLatestNeural", "en-US-Emma2DragonHDLatestNeural", "en-US-SteffanDragonHDLatestNeural",
        "en-US-AlloyDragonHDLatestNeural", "en-US-Andrew3DragonHDLatestNeural", "en-US-AriaDragonHDLatestNeural",
        "en-US-Ava3DragonHDLatestNeural", "en-US-BreeDragonHDLatestNeural", "en-US-PhoebeDragonHDLatestNeural",
        "en-US-SerenaDragonHDLatestNeural"
    ],
    "Spanish": ["es-AR-ElenaNeural", "es-AR-TomasNeural", "es-BO-MarceloNeural", "es-BO-SofiaNeural", "es-CL-CatalinaNeural", "es-CL-LorenzoNeural", "es-CO-GonzaloNeural", "es-CO-SalomeNeural", "es-ES-XimenaNeural", "es-CR-JuanNeural", "es-CR-MariaNeural", "es-CU-BelkysNeural", "es-CU-ManuelNeural", "es-DO-EmilioNeural", "es-DO-RamonaNeural", "es-EC-AndreaNeural", "es-EC-LuisNeural", "es-SV-LorenaNeural", "es-SV-RodrigoNeural", "es-GQ-JavierNeural", "es-GQ-TeresaNeural", "es-GT-AndresNeural", "es-GT-MartaNeural", "es-HN-CarlosNeural", "es-HN-KarlaNeural", "es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-NI-FedericoNeural", "es-NI-YolandaNeural", "es-PA-MargaritaNeural", "es-PA-RobertoNeural", "es-PY-MarioNeural", "es-PY-TaniaNeural", "es-PE-AlexNeural", "es-PE-CamilaNeural", "es-PR-KarinaNeural", "es-PR-VictorNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-US-AlonsoNeural", "es-US-PalomaNeural", "es-UY-MateoNeural", "es-UY-ValentinaNeural", "es-VE-PaolaNeural", "es-VE-SebastianNeural"],
    "Estonian": ["et-EE-AnuNeural", "et-EE-KertNeural"],
    "Persian": ["fa-IR-DilaraNeural", "fa-IR-FaridNeural"],
    "Finnish": ["fi-FI-HarriNeural", "fi-FI-NooraNeural"],
    "Filipino": ["fil-PH-AngeloNeural", "fil-PH-BlessicaNeural"],
    "French": ["fr-BE-CharlineNeural", "fr-BE-GerardNeural", "fr-CA-ThierryNeural", "fr-CA-AntoineNeural", "fr-CA-JeanNeural", "fr-CA-SylvieNeural", "fr-FR-VivienneMultilingualNeural", "fr-FR-RemyMultilingualNeural", "fr-FR-DeniseNeural", "fr-FR-EloiseNeural", "fr-FR-HenriNeural", "fr-CH-ArianeNeural", "fr-CH-FabriceNeural", "fr-FR-RemyDragonHDLatestNeural", "fr-FR-VivienneDragonHDLatestNeural"],
    "Irish": ["ga-IE-ColmNeural", "ga-IE-OrlaNeural"],
    "Galician": ["gl-ES-RoiNeural", "gl-ES-SabelaNeural"],
    "Gujarati": ["gu-IN-DhwaniNeural", "gu-IN-NiranjanNeural"],
    "Hebrew": ["he-IL-AvriNeural", "he-IL-HilaNeural"],
    "Hindi": ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural"],
    "Croatian": ["hr-HR-GabrijelaNeural", "hr-HR-SreckoNeural"],
    "Hungarian": ["hu-HU-NoemiNeural", "hu-HU-TamasNeural"],
    "Indonesian": ["id-ID-ArdiNeural", "id-ID-GadisNeural"],
    "Icelandic": ["is-IS-GudrunNeural", "is-IS-GunnarNeural"],
    "Italian": ["it-IT-GiuseppeMultilingualNeural", "it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-IsabellaNeural"],
    "Inuktitut": ["iu-Latn-CA-SiqiniqNeural", "iu-Latn-CA-TaqqiqNeural", "iu-Cans-CA-SiqiniqNeural", "iu-Cans-CA-TaqqiqNeural"],
    "Japanese": ["ja-JP-KeitaNeural", "ja-JP-NanamiNeural", "ja-JP-MasaruDragonHDLatestNeural", "ja-JP-NanamiDragonHDLatestNeural"],
    "Javanese": ["jv-ID-DimasNeural", "jv-ID-SitiNeural"],
    "Georgian": ["ka-GE-EkaNeural", "ka-GE-GiorgiNeural"],
    "Kazakh": ["kk-KZ-AigulNeural", "kk-KZ-DauletNeural"],
    "Khmer": ["km-KH-PisethNeural", "km-KH-SreymomNeural"],
    "Kannada": ["kn-IN-GaganNeural", "kn-IN-SapnaNeural"],
    "Korean": ["ko-KR-HyunsuMultilingualNeural", "ko-KR-InJoonNeural", "ko-KR-SunHiNeural"],
    "Lao": ["lo-LA-ChanthavongNeural", "lo-LA-KeomanyNeural"],
    "Lithuanian": ["lt-LT-LeonasNeural", "lt-LT-OnaNeural"],
    "Latvian": ["lv-LV-EveritaNeural", "lv-LV-NilsNeural"],
    "Macedonian": ["mk-MK-AleksandarNeural", "mk-MK-MarijaNeural"],
    "Malayalam": ["ml-IN-MidhunNeural", "ml-IN-SobhanaNeural"],
    "Mongolian": ["mn-MN-BataaNeural", "mn-MN-YesuiNeural"],
    "Marathi": ["mr-IN-AarohiNeural", "mr-IN-ManoharNeural"],
    "Malay": ["ms-MY-OsmanNeural", "ms-MY-YasminNeural"],
    "Maltese": ["mt-MT-GraceNeural", "mt-MT-JosephNeural"],
    "Myanmar": ["my-MM-NilarNeural", "my-MM-ThihaNeural"],
    "Norwegian": ["nb-NO-FinnNeural", "nb-NO-PernilleNeural"],
    "Nepali": ["ne-NP-HemkalaNeural", "ne-NP-SagarNeural"],
    "Dutch": ["nl-BE-ArnaudNeural", "nl-BE-DenaNeural", "nl-NL-ColetteNeural", "nl-NL-FennaNeural", "nl-NL-MaartenNeural"],
    "Polish": ["pl-PL-MarekNeural", "pl-PL-ZofiaNeural"],
    "Pashto": ["ps-AF-GulNawazNeural", "ps-AF-LatifaNeural"],
    "Portuguese": ["pt-BR-ThalitaMultilingualNeural", "pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-PT-DuarteNeural", "pt-PT-RaquelNeural"],
    "Romanian": ["ro-RO-AlinaNeural", "ro-RO-EmilNeural"],
    "Russian": ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"],
    "Sinhala": ["si-LK-SameeraNeural", "si-LK-ThiliniNeural"],
    "Slovak": ["sk-SK-LukasNeural", "sk-SK-ViktoriaNeural"],
    "Slovenian": ["sl-SI-PetraNeural", "sl-SI-RokNeural"],
    "Somali": ["so-SO-MuuseNeural", "so-SO-UbaxNeural"],
    "Albanian": ["sq-AL-AnilaNeural", "sq-AL-IlirNeural"],
    "Serbian": ["sr-RS-NicholasNeural", "sr-RS-SophieNeural"],
    "Sundanese": ["su-ID-JajangNeural", "su-ID-TutiNeural"],
    "Swedish": ["sv-SE-MattiasNeural", "sv-SE-SofieNeural"],
    "Swahili": ["sw-KE-RafikiNeural", "sw-KE-ZuriNeural", "sw-TZ-DaudiNeural", "sw-TZ-RehemaNeural"],
    "Tamil": ["ta-IN-PallaviNeural", "ta-IN-ValluvarNeural", "ta-MY-KaniNeural", "ta-MY-SuryaNeural", "ta-SG-AnbuNeural", "ta-SG-VenbaNeural", "ta-LK-KumarNeural", "ta-LK-SaranyaNeural"],
    "Telugu": ["te-IN-MohanNeural", "te-IN-ShrutiNeural"],
    "Thai": ["th-TH-NiwatNeural", "th-TH-PremwadeeNeural"],
    "Turkish": ["tr-TR-EmelNeural", "tr-TR-AhmetNeural"],
    "Ukrainian": ["uk-UA-OstapNeural", "uk-UA-PolinaNeural"],
    "Urdu": ["ur-IN-GulNeural", "ur-IN-SalmanNeural", "ur-PK-AsadNeural", "ur-PK-UzmaNeural"],
    "Uzbek": ["uz-UZ-MadinaNeural", "uz-UZ-SardorNeural"],
    "Vietnamese": ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"],
    "Chinese": ["zh-HK-HiuGaaiNeural", "zh-HK-HiuMaanNeural", "zh-HK-WanLungNeural", "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural", "zh-CN-YunxiNeural", "zh-CN-YunxiaNeural", "zh-CN-YunyangNeural", "zh-CN-liaoning-XiaobeiNeural", "zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-TW-HsiaoYuNeural", "zh-CN-shaanxi-XiaoniNeural", "zh-CN-XiaochenDragonHDLatestNeural"],
    "Zulu": ["zu-ZA-ThandoNeural", "zu-ZA-ThembaNeural"]
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

# ... (the rest of your handlers and functions remain unchanged) ...
# For brevity I did not repeat the entire unchanged body here — ensure you paste the rest of your original code
# (handlers, callback handlers, synth_and_send_tts, webhook routes, set_bot_commands, etc.) exactly as you had them.
# The important changes are above: VOICE_MAPPING and TTS_VOICES_BY_LANGUAGE updated with new HD/Dragon voices.

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
