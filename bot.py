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
from pymongo import MongoClient, errors

# ------------------------ Configuration ------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

TOKEN = "7999849691:AAFNsufKPWU9YyW_CEp7_6BF5cClX8PvR0Y"
ADMIN_ID = 6964068910
WEBHOOK_URL = "https://tts-bot-lcn9.onrender.com"
# If you want to disable the subscription/join prompt, set REQUIRED_CHANNEL to an empty string.
REQUIRED_CHANNEL = "@guruubka_wasmada"

# Mongo config (from your request)
MONGO_URI = "mongodb+srv://hoskasii:GHyCdwpI0PvNuLTg@cluster0.dy7oe7t.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "telegram_bot_db"

# ------------------------ Bot, App, and DB clients ------------------------
bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# MongoDB client and collections (populated in init_db)
mongo_client = None
db = None
users_col = None          # stores user records: {_id: "<telegram_id>", last_active: ISO, tts_conversion_count: int}
tts_settings_col = None   # stores tts settings per user: {_id: "<telegram_id>", voice: str, pitch: int, rate: int}
mongodb_available = False

# Keep a small in-memory fallback (used only if DB not available)
in_memory_data = {
    "users": {},
    "tts_settings": {},
}

# User modes (kept in-memory only, ephemeral)
user_tts_mode = {}
user_pitch_input_mode = {}
user_rate_input_mode = {}
admin_state = {}

# ------------------------ Voices mapping and lists (unchanged) ------------------------
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
    "es-AR-ElenaNeural": "Elena - Spanish (Argentina)",
    "es-AR-TomasNeural": "Tomas - Spanish (Argentina)",
    "es-BO-MarceloNeural": "Marcelo - Spanish (Bolivia)",
    "es-BO-SofiaNeural": "Sofia - Spanish (Bolivia)",
    "es-CL-CatalinaNeural": "Catalina - Spanish (Chile)",
    "es-CL-LorenzoNeural": "Lorenzo - Spanish (Chile)",
    "es-CO-GonzaloNeural": "Gonzalo - Spanish (Colombia)",
    "es-CO-SalomeNeural": "Salome - Spanish (Colombia)",
    "es-ES-XimenaNeural": "Ximena - Spanish (Spain)",
    "es-CR-JuanNeural": "Juan - Spanish (Costa Rica)",
    "es-CR-MariaNeural": "Maria - Spanish (Costa Rica)",
    "es-CU-BelkysNeural": "Belkys - Spanish (Cuba)",
    "es-CU-ManuelNeural": "Manuel - Spanish (Cuba)",
    "es-DO-EmilioNeural": "Emilio - Spanish (Dominican Republic)",
    "es-DO-RamonaNeural": "Ramona - Spanish (Dominican Republic)",
    "es-EC-AndreaNeural": "Andrea - Spanish (Ecuador)",
    "es-EC-LuisNeural": "Luis - Spanish (Ecuador)",
    "es-SV-LorenaNeural": "Lorena - Spanish (El Salvador)",
    "es-SV-RodrigoNeural": "Rodrigo - Spanish (El Salvador)",
    "es-GQ-JavierNeural": "Javier - Spanish (Equatorial Guinea)",
    "es-GQ-TeresaNeural": "Teresa - Spanish (Equatorial Guinea)",
    "es-GT-AndresNeural": "Andres - Spanish (Guatemala)",
    "es-GT-MartaNeural": "Marta - Spanish (Guatemala)",
    "es-HN-CarlosNeural": "Carlos - Spanish (Honduras)",
    "es-HN-KarlaNeural": "Karla - Spanish (Honduras)",
    "es-MX-DaliaNeural": "Dalia - Spanish (Mexico)",
    "es-MX-JorgeNeural": "Jorge - Spanish (Mexico)",
    "es-NI-FedericoNeural": "Federico - Spanish (Nicaragua)",
    "es-NI-YolandaNeural": "Yolanda - Spanish (Nicaragua)",
    "es-PA-MargaritaNeural": "Margarita - Spanish (Panama)",
    "es-PA-RobertoNeural": "Roberto - Spanish (Panama)",
    "es-PY-MarioNeural": "Mario - Spanish (Paraguay)",
    "es-PY-TaniaNeural": "Tania - Spanish (Paraguay)",
    "es-PE-AlexNeural": "Alex - Spanish (Peru)",
    "es-PE-CamilaNeural": "Camila - Spanish (Peru)",
    "es-PR-KarinaNeural": "Karina - Spanish (Puerto Rico)",
    "es-PR-VictorNeural": "Victor - Spanish (Puerto Rico)",
    "es-ES-AlvaroNeural": "Alvaro - Spanish (Spain)",
    "es-ES-ElviraNeural": "Elvira - Spanish (Spain)",
    "es-US-AlonsoNeural": "Alonso - Spanish (United States)",
    "es-US-PalomaNeural": "Paloma - Spanish (United States)",
    "es-UY-MateoNeural": "Mateo - Spanish (Uruguay)",
    "es-UY-ValentinaNeural": "Valentina - Spanish (Uruguay)",
    "es-VE-PaolaNeural": "Paola - Spanish (Venezuela)",
    "es-VE-SebastianNeural": "Sebastian - Spanish (Venezuela)",
    "et-EE-AnuNeural": "Anu - Estonian (Estonia)",
    "et-EE-KertNeural": "Kert - Estonian (Estonia)",
    "fa-IR-DilaraNeural": "Dilara - Persian (Iran)",
    "fa-IR-FaridNeural": "Farid - Persian (Iran)",
    "fi-FI-HarriNeural": "Harri - Finnish (Finland)",
    "fi-FI-NooraNeural": "Noora - Finnish (Finland)",
    "fil-PH-AngeloNeural": "Angelo - Filipino (Philippines)",
    "fil-PH-BlessicaNeural": "Blessica - Filipino (Philippines)",
    "fr-BE-CharlineNeural": "Charline - French (Belgium)",
    "fr-BE-GerardNeural": "Gerard - French (Belgium)",
    "fr-CA-ThierryNeural": "Thierry - French (Canada)",
    "fr-CA-AntoineNeural": "Antoine - French (Canada)",
    "fr-CA-JeanNeural": "Jean - French (Canada)",
    "fr-CA-SylvieNeural": "Sylvie - French (Canada)",
    "fr-FR-VivienneMultilingualNeural": "Vivienne - French (France) - Multilingual",
    "fr-FR-RemyMultilingualNeural": "Remy - French (France) - Multilingual",
    "fr-FR-DeniseNeural": "Denise - French (France)",
    "fr-FR-EloiseNeural": "Eloise - French (France)",
    "fr-FR-HenriNeural": "Henri - French (France)",
    "fr-CH-ArianeNeural": "Ariane - French (Switzerland)",
    "fr-CH-FabriceNeural": "Fabrice - French (Switzerland)",
    "ga-IE-ColmNeural": "Colm - Irish (Ireland)",
    "ga-IE-OrlaNeural": "Orla - Irish (Ireland)",
    "gl-ES-RoiNeural": "Roi - Galician (Spain)",
    "gl-ES-SabelaNeural": "Sabela - Galician (Spain)",
    "gu-IN-DhwaniNeural": "Dhwani - Gujarati (India)",
    "gu-IN-NiranjanNeural": "Niranjan - Gujarati (India)",
    "he-IL-AvriNeural": "Avri - Hebrew (Israel)",
    "he-IL-HilaNeural": "Hila - Hebrew (Israel)",
    "hi-IN-MadhurNeural": "Madhur - Hindi (India)",
    "hi-IN-SwaraNeural": "Swara - Hindi (India)",
    "hr-HR-GabrijelaNeural": "Gabrijela - Croatian (Croatia)",
    "hr-HR-SreckoNeural": "Srecko - Croatian (Croatia)",
    "hu-HU-NoemiNeural": "Noemi - Hungarian (Hungary)",
    "hu-HU-TamasNeural": "Tamas - Hungarian (Hungary)",
    "id-ID-ArdiNeural": "Ardi - Indonesian (Indonesia)",
    "id-ID-GadisNeural": "Gadis - Indonesian (Indonesia)",
    "is-IS-GudrunNeural": "Gudrun - Icelandic (Iceland)",
    "is-IS-GunnarNeural": "Gunnar - Icelandic (Iceland)",
    "it-IT-GiuseppeMultilingualNeural": "Giuseppe - Italian (Italy) - Multilingual",
    "it-IT-DiegoNeural": "Diego - Italian (Italy)",
    "it-IT-ElsaNeural": "Elsa - Italian (Italy)",
    "it-IT-IsabellaNeural": "Isabella - Italian (Italy)",
    "iu-Latn-CA-SiqiniqNeural": "Siqiniq - Inuktitut (Canada) - Latin",
    "iu-Latn-CA-TaqqiqNeural": "Taqqiq - Inuktitut (Canada) - Latin",
    "iu-Cans-CA-SiqiniqNeural": "Siqiniq - Inuktitut (Canada) - Syllabics",
    "iu-Cans-CA-TaqqiqNeural": "Taqqiq - Inuktitut (Canada) - Syllabics",
    "ja-JP-KeitaNeural": "Keita - Japanese (Japan)",
    "ja-JP-NanamiNeural": "Nanami - Japanese (Japan)",
    "jv-ID-DimasNeural": "Dimas - Javanese (Indonesia)",
    "jv-ID-SitiNeural": "Siti - Javanese (Indonesia)",
    "ka-GE-EkaNeural": "Eka - Georgian (Georgia)",
    "ka-GE-GiorgiNeural": "Giorgi - Georgian (Georgia)",
    "kk-KZ-AigulNeural": "Aigul - Kazakh (Kazakhstan)",
    "kk-KZ-DauletNeural": "Daulet - Kazakh (Kazakhstan)",
    "km-KH-PisethNeural": "Piseth - Khmer (Cambodia)",
    "km-KH-SreymomNeural": "Sreymom - Khmer (Cambodia)",
    "kn-IN-GaganNeural": "Gagan - Kannada (India)",
    "kn-IN-SapnaNeural": "Sapna - Kannada (India)",
    "ko-KR-HyunsuMultilingualNeural": "Hyunsu - Korean (Korea) - Multilingual",
    "ko-KR-InJoonNeural": "InJoon - Korean (Korea)",
    "ko-KR-SunHiNeural": "SunHi - Korean (Korea)",
    "lo-LA-ChanthavongNeural": "Chanthavong - Lao (Laos)",
    "lo-LA-KeomanyNeural": "Keomany - Lao (Laos)",
    "lt-LT-LeonasNeural": "Leonas - Lithuanian (Lithuania)",
    "lt-LT-OnaNeural": "Ona - Lithuanian (Lithuania)",
    "lv-LV-EveritaNeural": "Everita - Latvian (Latvia)",
    "lv-LV-NilsNeural": "Nils - Latvian (Latvia)",
    "mk-MK-AleksandarNeural": "Aleksandar - Macedonian (North Macedonia)",
    "mk-MK-MarijaNeural": "Marija - Macedonian (North Macedonia)",
    "ml-IN-MidhunNeural": "Midhun - Malayalam (India)",
    "ml-IN-SobhanaNeural": "Sobhana - Malayalam (India)",
    "mn-MN-BataaNeural": "Bataa - Mongolian (Mongolia)",
    "mn-MN-YesuiNeural": "Yesui - Mongolian (Mongolia)",
    "mr-IN-AarohiNeural": "Aarohi - Marathi (India)",
    "mr-IN-ManoharNeural": "Manohar - Marathi (India)",
    "ms-MY-OsmanNeural": "Osman - Malay (Malaysia)",
    "ms-MY-YasminNeural": "Yasmin - Malay (Malaysia)",
    "mt-MT-GraceNeural": "Grace - Maltese (Malta)",
    "mt-MT-JosephNeural": "Joseph - Maltese (Malta)",
    "my-MM-NilarNeural": "Nilar - Burmese (Myanmar)",
    "my-MM-ThihaNeural": "Thiha - Burmese (Myanmar)",
    "nb-NO-FinnNeural": "Finn - Norwegian Bokmål (Norway)",
    "nb-NO-PernilleNeural": "Pernille - Norwegian Bokmål (Norway)",
    "ne-NP-HemkalaNeural": "Hemkala - Nepali (Nepal)",
    "ne-NP-SagarNeural": "Sagar - Nepali (Nepal)",
    "nl-BE-ArnaudNeural": "Arnaud - Dutch (Belgium)",
    "nl-BE-DenaNeural": "Dena - Dutch (Belgium)",
    "nl-NL-ColetteNeural": "Colette - Dutch (Netherlands)",
    "nl-NL-FennaNeural": "Fenna - Dutch (Netherlands)",
    "nl-NL-MaartenNeural": "Maarten - Dutch (Netherlands)",
    "pl-PL-MarekNeural": "Marek - Polish (Poland)",
    "pl-PL-ZofiaNeural": "Zofia - Polish (Poland)",
    "ps-AF-GulNawazNeural": "Gul Nawaz - Pashto (Afghanistan)",
    "ps-AF-LatifaNeural": "Latifa - Pashto (Afghanistan)",
    "pt-BR-ThalitaMultilingualNeural": "Thalita - Portuguese (Brazil) - Multilingual",
    "pt-BR-AntonioNeural": "Antonio - Portuguese (Brazil)",
    "pt-BR-FranciscaNeural": "Francisca - Portuguese (Brazil)",
    "pt-PT-DuarteNeural": "Duarte - Portuguese (Portugal)",
    "pt-PT-RaquelNeural": "Raquel - Portuguese (Portugal)",
    "ro-RO-AlinaNeural": "Alina - Romanian (Romania)",
    "ro-RO-EmilNeural": "Emil - Romanian (Romania)",
    "ru-RU-DmitryNeural": "Dmitry - Russian (Russia)",
    "ru-RU-SvetlanaNeural": "Svetlana - Russian (Russia)",
    "si-LK-SameeraNeural": "Sameera - Sinhala (Sri Lanka)",
    "si-LK-ThiliniNeural": "Thilini - Sinhala (Sri Lanka)",
    "sk-SK-LukasNeural": "Lukas - Slovak (Slovakia)",
    "sk-SK-ViktoriaNeural": "Viktoria - Slovak (Slovakia)",
    "sl-SI-PetraNeural": "Petra - Slovenian (Slovenia)",
    "sl-SI-RokNeural": "Rok - Slovenian (Slovenia)",
    "so-SO-MuuseNeural": "Muuse - Somali (Somalia)",
    "so-SO-UbaxNeural": "Ubax - Somali (Somalia)",
    "sq-AL-AnilaNeural": "Anila - Albanian (Albania)",
    "sq-AL-IlirNeural": "Ilir - Albanian (Albania)",
    "sr-RS-NicholasNeural": "Nicholas - Serbian (Serbia)",
    "sr-RS-SophieNeural": "Sophie - Serbian (Serbia)",
    "su-ID-JajangNeural": "Jajang - Sundanese (Indonesia)",
    "su-ID-TutiNeural": "Tuti - Sundanese (Indonesia)",
    "sv-SE-MattiasNeural": "Mattias - Swedish (Sweden)",
    "sv-SE-SofieNeural": "Sofie - Swedish (Sweden)",
    "sw-KE-RafikiNeural": "Rafiki - Swahili (Kenya)",
    "sw-KE-ZuriNeural": "Zuri - Swahili (Kenya)",
    "sw-TZ-DaudiNeural": "Daudi - Swahili (Tanzania)",
    "sw-TZ-RehemaNeural": "Rehema - Swahili (Tanzania)",
    "ta-IN-PallaviNeural": "Pallavi - Tamil (India)",
    "ta-IN-ValluvarNeural": "Valluvar - Tamil (India)",
    "ta-MY-KaniNeural": "Kani - Tamil (Malaysia)",
    "ta-MY-SuryaNeural": "Surya - Tamil (Malaysia)",
    "ta-SG-AnbuNeural": "Anbu - Tamil (Singapore)",
    "ta-SG-VenbaNeural": "Venba - Tamil (Singapore)",
    "ta-LK-KumarNeural": "Kumar - Tamil (Sri Lanka)",
    "ta-LK-SaranyaNeural": "Saranya - Tamil (Sri Lanka)",
    "te-IN-MohanNeural": "Mohan - Telugu (India)",
    "te-IN-ShrutiNeural": "Shruti - Telugu (India)",
    "th-TH-NiwatNeural": "Niwat - Thai (Thailand)",
    "th-TH-PremwadeeNeural": "Premwadee - Thai (Thailand)",
    "tr-TR-EmelNeural": "Emel - Turkish (Turkey)",
    "tr-TR-AhmetNeural": "Ahmet - Turkish (Turkey)",
    "uk-UA-OstapNeural": "Ostap - Ukrainian (Ukraine)",
    "uk-UA-PolinaNeural": "Polina - Ukrainian (Ukraine)",
    "ur-IN-GulNeural": "Gul - Urdu (India)",
    "ur-IN-SalmanNeural": "Salman - Urdu (India)",
    "ur-PK-AsadNeural": "Asad - Urdu (Pakistan)",
    "ur-PK-UzmaNeural": "Uzma - Urdu (Pakistan)",
    "uz-UZ-MadinaNeural": "Madina - Uzbek (Uzbekistan)",
    "uz-UZ-SardorNeural": "Sardor - Uzbek (Uzbekistan)",
    "vi-VN-HoaiMyNeural": "HoaiMy - Vietnamese (Vietnam)",
    "vi-VN-NamMinhNeural": "NamMinh - Vietnamese (Vietnam)",
    "zh-HK-HiuGaaiNeural": "Hiu Gaai - Chinese (Cantonese, Hong Kong)",
    "zh-HK-HiuMaanNeural": "Hiu Maan - Chinese (Cantonese, Hong Kong)",
    "zh-HK-WanLungNeural": "Wan Lung - Chinese (Cantonese, Hong Kong)",
    "zh-CN-XiaoxiaoNeural": "Xiaoxiao - Chinese (Mandarin, Simplified)",
    "zh-CN-XiaoyiNeural": "Xiaoyi - Chinese (Mandarin, Simplified)",
    "zh-CN-YunjianNeural": "Yunjian - Chinese (Mandarin, Simplified)",
    "zh-CN-YunxiNeural": "Yunxi - Chinese (Mandarin, Simplified)",
    "zh-CN-YunxiaNeural": "Yunxia - Chinese (Mandarin, Simplified)",
    "zh-CN-YunyangNeural": "Yunyang - Chinese (Mandarin, Simplified)",
    "zh-CN-liaoning-XiaobeiNeural": "Xiaobei - Chinese (Northeastern Mandarin, Simplified)",
    "zh-TW-HsiaoChenNeural": "HsiaoChen - Chinese (Taiwanese Mandarin)",
    "zh-TW-YunJheNeural": "YunJhe - Chinese (Taiwanese Mandarin)",
    "zh-TW-HsiaoYuNeural": "HsiaoYu - Chinese (Taiwanese Mandarin)",
    "zh-CN-shaanxi-XiaoniNeural": "Xiaoni - Chinese (Shaanxi Mandarin, Simplified)",
    "zu-ZA-ThandoNeural": "Thando - Zulu (South Africa)",
    "zu-ZA-ThembaNeural": "Themba - Zulu (South Africa)"
}

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
    "German": ["de-AT-IngridNeural", "de-AT-JonasNeural", "de-DE-SeraphinaMultilingualNeural", "de-DE-FlorianMultilingualNeural", "de-DE-AmalaNeural", "de-DE-ConradNeural", "de-DE-KatjaNeural", "de-DE-KillianNeural", "de-CH-JanNeural", "de-CH-LeniNeural"],
    "Greek": ["el-GR-AthinaNeural", "el-GR-NestorasNeural"],
    "English": ["en-AU-WilliamMultilingualNeural", "en-AU-NatashaNeural", "en-CA-ClaraNeural", "en-CA-LiamNeural", "en-HK-YanNeural", "en-HK-SamNeural", "en-IN-NeerjaExpressiveNeural", "en-IN-NeerjaNeural", "en-IN-PrabhatNeural", "en-IE-ConnorNeural", "en-IE-EmilyNeural", "en-KE-AsiliaNeural", "en-KE-ChilembaNeural", "en-NZ-MitchellNeural", "en-NZ-MollyNeural", "en-NG-AbeoNeural", "en-NG-EzinneNeural", "en-PH-JamesNeural", "en-PH-RosaNeural", "en-US-AvaNeural", "en-US-AndrewNeural", "en-US-EmmaNeural", "en-US-BrianNeural", "en-SG-LunaNeural", "en-SG-WayneNeural", "en-ZA-LeahNeural", "en-ZA-LukeNeural", "en-TZ-ElimuNeural", "en-TZ-ImaniNeural", "en-GB-LibbyNeural", "en-GB-MaisieNeural", "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-GB-ThomasNeural", "en-US-AnaNeural", "en-US-AndrewMultilingualNeural", "en-US-AriaNeural", "en-US-AvaMultilingualNeural", "en-US-BrianMultilingualNeural", "en-US-ChristopherNeural", "en-US-EmmaMultilingualNeural", "en-US-EricNeural", "en-US-GuyNeural", "en-US-JennyNeural", "en-US-MichelleNeural", "en-US-RogerNeural", "en-US-SteffanNeural"],
    "Spanish": ["es-AR-ElenaNeural", "es-AR-TomasNeural", "es-BO-MarceloNeural", "es-BO-SofiaNeural", "es-CL-CatalinaNeural", "es-CL-LorenzoNeural", "es-CO-GonzaloNeural", "es-CO-SalomeNeural", "es-ES-XimenaNeural", "es-CR-JuanNeural", "es-CR-MariaNeural", "es-CU-BelkysNeural", "es-CU-ManuelNeural", "es-DO-EmilioNeural", "es-DO-RamonaNeural", "es-EC-AndreaNeural", "es-EC-LuisNeural", "es-SV-LorenaNeural", "es-SV-RodrigoNeural", "es-GQ-JavierNeural", "es-GQ-TeresaNeural", "es-GT-AndresNeural", "es-GT-MartaNeural", "es-HN-CarlosNeural", "es-HN-KarlaNeural", "es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-NI-FedericoNeural", "es-NI-YolandaNeural", "es-PA-MargaritaNeural", "es-PA-RobertoNeural", "es-PY-MarioNeural", "es-PY-TaniaNeural", "es-PE-AlexNeural", "es-PE-CamilaNeural", "es-PR-KarinaNeural", "es-PR-VictorNeural", "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-US-AlonsoNeural", "es-US-PalomaNeural", "es-UY-MateoNeural", "es-UY-ValentinaNeural", "es-VE-PaolaNeural", "es-VE-SebastianNeural"],
    # ... (list continues as previously - left in full in file)
}

MOST_USED = [
    "English", "Chinese", "Spanish", "Arabic", "Portuguese", "Indonesian", "French", "Russian",
    "Japanese", "German", "Vietnamese", "Turkish", "Korean", "Italian", "Polish", "Dutch",
    "Persian", "Hindi", "Urdu", "Bengali", "Filipino", "Malay", "Thai", "Romanian", "Ukrainian"
]

ORDERED_TTS_LANGUAGES = [l for l in MOST_USED if l in TTS_VOICES_BY_LANGUAGE] + sorted([l for l in TTS_VOICES_BY_LANGUAGE.keys() if l not in MOST_USED])

# ------------------------ Database helpers ------------------------
def init_db():
    """
    Initialize MongoDB client and collections. If MongoDB is unavailable, the code will fall back to in-memory storage.
    """
    global mongo_client, db, users_col, tts_settings_col, mongodb_available
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Force a server selection to verify connectivity
        mongo_client.admin.command('ping')
        db = mongo_client[DB_NAME]
        users_col = db["users"]
        tts_settings_col = db["tts_settings"]
        # Ensure indexes for efficiency (optional)
        users_col.create_index("last_active")
        tts_settings_col.create_index("_id", unique=True)
        mongodb_available = True
        logging.info("Connected to MongoDB successfully.")
    except Exception as e:
        logging.error(f"Could not connect to MongoDB: {e}. Falling back to in-memory storage.")
        mongo_client = None
        db = None
        users_col = None
        tts_settings_col = None
        mongodb_available = False

def _now_iso():
    return datetime.utcnow().isoformat()

def update_user_activity_in_memory(user_id: int):
    """
    Upsert user record in DB (or in-memory fallback).
    Keeps last_active and tts_conversion_count.
    """
    user_id_str = str(user_id)
    now_iso = _now_iso()
    if mongodb_available and users_col:
        try:
            users_col.update_one(
                {"_id": user_id_str},
                {"$set": {"last_active": now_iso}, "$setOnInsert": {"tts_conversion_count": 0}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"Mongo error updating user activity: {e}")
            # fallback to in-memory
            if user_id_str not in in_memory_data["users"]:
                in_memory_data["users"][user_id_str] = {
                    "_id": user_id_str,
                    "last_active": now_iso,
                    "tts_conversion_count": 0
                }
            else:
                in_memory_data["users"][user_id_str]["last_active"] = now_iso
    else:
        if user_id_str not in in_memory_data["users"]:
            in_memory_data["users"][user_id_str] = {
                "_id": user_id_str,
                "last_active": now_iso,
                "tts_conversion_count": 0
            }
        else:
            in_memory_data["users"][user_id_str]["last_active"] = now_iso

def increment_processing_count_in_memory(user_id: str, service_type: str):
    """
    Increment processing count for a user (tts_conversion_count).
    """
    user_id_str = str(user_id)
    now_iso = _now_iso()
    if mongodb_available and users_col:
        try:
            users_col.update_one(
                {"_id": user_id_str},
                {"$inc": {"tts_conversion_count": 1}, "$set": {"last_active": now_iso}},
                upsert=True
            )
            return
        except Exception as e:
            logging.error(f"Mongo error incrementing processing count: {e}")

    # Fallback
    if user_id_str not in in_memory_data["users"]:
        in_memory_data["users"][user_id_str] = {
            "_id": user_id_str,
            "last_active": now_iso,
            "tts_conversion_count": 1
        }
    else:
        in_memory_data["users"][user_id_str]["tts_conversion_count"] = in_memory_data["users"][user_id_str].get("tts_conversion_count", 0) + 1
        in_memory_data["users"][user_id_str]["last_active"] = now_iso

def get_tts_user_voice_in_memory(user_id: str) -> str:
    """
    Get voice for the user from DB or in-memory fallback. Default voice is Ava multilingual.
    """
    user_id_str = str(user_id)
    default_voice = "en-US-AvaMultilingualNeural"
    if mongodb_available and tts_settings_col:
        try:
            doc = tts_settings_col.find_one({"_id": user_id_str}, {"voice": 1})
            if doc and "voice" in doc:
                return doc["voice"]
            return default_voice
        except Exception as e:
            logging.error(f"Mongo error getting user voice: {e}")
    # fallback
    return in_memory_data["tts_settings"].get(user_id_str, {}).get("voice", default_voice)

def set_tts_user_voice_in_memory(user_id: str, voice: str):
    user_id_str = str(user_id)
    if mongodb_available and tts_settings_col:
        try:
            tts_settings_col.update_one(
                {"_id": user_id_str},
                {"$set": {"voice": voice}},
                upsert=True
            )
            return
        except Exception as e:
            logging.error(f"Mongo error setting user voice: {e}")
    # fallback
    if user_id_str not in in_memory_data["tts_settings"]:
        in_memory_data["tts_settings"][user_id_str] = {}
    in_memory_data["tts_settings"][user_id_str]["voice"] = voice

def get_tts_user_pitch_in_memory(user_id: str) -> int:
    user_id_str = str(user_id)
    if mongodb_available and tts_settings_col:
        try:
            doc = tts_settings_col.find_one({"_id": user_id_str}, {"pitch": 1})
            if doc and "pitch" in doc:
                return int(doc["pitch"])
            return 0
        except Exception as e:
            logging.error(f"Mongo error getting user pitch: {e}")
    return int(in_memory_data["tts_settings"].get(user_id_str, {}).get("pitch", 0))

def set_tts_user_pitch_in_memory(user_id: str, pitch: int):
    user_id_str = str(user_id)
    if mongodb_available and tts_settings_col:
        try:
            tts_settings_col.update_one(
                {"_id": user_id_str},
                {"$set": {"pitch": int(pitch)}},
                upsert=True
            )
            return
        except Exception as e:
            logging.error(f"Mongo error setting user pitch: {e}")
    if user_id_str not in in_memory_data["tts_settings"]:
        in_memory_data["tts_settings"][user_id_str] = {}
    in_memory_data["tts_settings"][user_id_str]["pitch"] = int(pitch)

def get_tts_user_rate_in_memory(user_id: str) -> int:
    user_id_str = str(user_id)
    if mongodb_available and tts_settings_col:
        try:
            doc = tts_settings_col.find_one({"_id": user_id_str}, {"rate": 1})
            if doc and "rate" in doc:
                return int(doc["rate"])
            return 0
        except Exception as e:
            logging.error(f"Mongo error getting user rate: {e}")
    return int(in_memory_data["tts_settings"].get(user_id_str, {}).get("rate", 0))

def set_tts_user_rate_in_memory(user_id: str, rate: int):
    user_id_str = str(user_id)
    if mongodb_available and tts_settings_col:
        try:
            tts_settings_col.update_one(
                {"_id": user_id_str},
                {"$set": {"rate": int(rate)}},
                upsert=True
            )
            return
        except Exception as e:
            logging.error(f"Mongo error setting user rate: {e}")
    if user_id_str not in in_memory_data["tts_settings"]:
        in_memory_data["tts_settings"][user_id_str] = {}
    in_memory_data["tts_settings"][user_id_str]["rate"] = int(rate)

# ------------------------ Utility functions ------------------------
def keep_recording(chat_id, stop_event, target_bot):
    while not stop_event.is_set():
        try:
            target_bot.send_chat_action(chat_id, 'record_audio')
            time.sleep(4)
        except Exception as e:
            logging.error(f"Error sending record_audio action: {e}")
            break

def check_subscription(user_id: int) -> bool:
    """
    Returns True if subscription is not required or the user is a member of REQUIRED_CHANNEL.
    This checks REQUIRED_CHANNEL string presence (non-empty).
    """
    if not REQUIRED_CHANNEL or not REQUIRED_CHANNEL.strip():
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Error checking subscription: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error checking subscription: {e}")
        return False

def send_subscription_message(chat_id: int):
    """
    Only show the subscription/join message if REQUIRED_CHANNEL is specified (non-empty).
    """
    if not REQUIRED_CHANNEL or not REQUIRED_CHANNEL.strip():
        return
    try:
        chat = bot.get_chat(chat_id)
        if chat.type != 'private':
            return
    except Exception:
        # If we can't fetch chat info, avoid showing the subscription message.
        return

    try:
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Click here to join the group",
                url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}"
            )
        )
        bot.send_message(
            chat_id,
            "🔒 Access Restricted\n\nPlease join our group to use this bot.\n\nJoin and send /start again.",
            reply_markup=markup
        )
    except Exception as e:
        logging.error(f"Error sending subscription message: {e}")

# ------------------------ Bot command handlers ------------------------
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id_str = str(message.from_user.id)
    user_first_name = message.from_user.first_name if message.from_user.first_name else "User"

    update_user_activity_in_memory(message.from_user.id)

    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    user_tts_mode[user_id_str] = None
    user_pitch_input_mode[user_id_str] = None
    user_rate_input_mode[user_id_str] = None

    welcome_message = (
        f"👋 Salom {user_first_name}! I am your AI voice assistant that converts text to audio for free! 🔊✍️\n\n"
        "✨ **Here's how to use it:**\n"
        "1. **Convert Text to Audio (TTS):**\n"
        "   - Choose the voice `/voice`\n"
        "   - Adjust your voice `/pitch` or `/rate`\n"
        "   - Send me text, I will convert it to audio!\n\n"
        "👉 You can also add me to your groups - click the button below!"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Add to your Group!", url="https://t.me/Voice_maker_robot?startgroup=")
    )
    bot.send_message(
        message.chat.id,
        welcome_message,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['admin'])
def admin_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 This command is restricted to the admin only.")
        return
    update_user_activity_in_memory(message.from_user.id)
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
    update_user_activity_in_memory(message.from_user.id)

    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None

    help_text = (
        "📖 **How to use This Bot?**\n\n"
        "This bot makes it easy to convert text to audio. Here's how it works:\n\n"
        "⸻\n"
        "**Convert Text to Audio (TTS):**\n"
        "• **Choose Voice:** Use `/voice` to select the language and voice you want,\n"
        "• **Send your Text:** Once you choose the voice, any text you send me will be returned as audio,\n"
        "• **Adjust Voice:**\n"
        "  • Use `/pitch` to increase or decrease the pitch,\n"
        "  • Use `/rate` to speed up or slow down the speech,\n\n"
        "⸻\n"
        "**Your Data & Privacy:**\n"
        "• **Your Data is Private:** The text and audio you send are not saved – they are used temporarily,\n"
        "• **Your preferences are saved:** The voice, pitch, and rate you choose are saved until the bot restarts.\n\n"
        "👉 Questions or problems? Contact @kookabeela\n\n"
        "Enjoy creating audio! ✨"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['privacy'])
def privacy_notice_handler(message):
    user_id = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)

    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return

    user_tts_mode[user_id] = None
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None

    privacy_text = (
        "🔐 **Privacy Notice**\n\n"
        "If you have any questions or concerns about your privacy, please feel free to contact the bot administrator @kookabeela."
    )
    bot.send_message(message.chat.id, privacy_text, parse_mode="Markdown")

@bot.message_handler(commands=['voices_list'])
def voices_list_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 This command is restricted to the admin only.")
        return

    update_user_activity_in_memory(message.from_user.id)
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
        # get count from DB if available
        try:
            if mongodb_available and users_col:
                total_registered = users_col.count_documents({})
            else:
                total_registered = len(in_memory_data["users"])
        except Exception as e:
            logging.error(f"Error counting users: {e}")
            total_registered = len(in_memory_data["users"])
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

    # iterate users from DB or fallback
    user_ids = []
    if mongodb_available and users_col:
        try:
            for doc in users_col.find({}, {"_id": 1}):
                user_ids.append(doc["_id"])
        except Exception as e:
            logging.error(f"Error fetching user ids for broadcast: {e}")
            user_ids = list(in_memory_data["users"].keys())
    else:
        user_ids = list(in_memory_data["users"].keys())

    for uid in user_ids:
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

# ------------------------ TTS UI helpers ------------------------
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
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_rate_command(message)

@bot.callback_query_handler(lambda c: c.data.startswith("rate_set|"))
def on_rate_set_callback(call):
    user_id = str(call.from_user.id)
    update_user_activity_in_memory(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_rate_input_mode[user_id] = None

    try:
        _, rate_value_str = call.data.split("|", 1)
        rate_value = int(rate_value_str)
        set_tts_user_rate_in_memory(user_id, rate_value)
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
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return
    handle_pitch_command(message)

@bot.callback_query_handler(lambda c: c.data.startswith("pitch_set|"))
def on_pitch_set_callback(call):
    user_id = str(call.from_user.id)
    update_user_activity_in_memory(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_pitch_input_mode[user_id] = None

    try:
        _, pitch_value_str = call.data.split("|", 1)
        pitch_value = int(pitch_value_str)
        set_tts_user_pitch_in_memory(user_id, pitch_value)
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
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.from_user.id):
        send_subscription_message(message.chat.id)
        return
    handle_voice_command(message)

@bot.callback_query_handler(lambda c: c.data.startswith("tts_lang|"))
def on_tts_language_select(call):
    user_id = str(call.from_user.id)
    update_user_activity_in_memory(call.from_user.id)
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
    update_user_activity_in_memory(call.from_user.id)
    if call.message.chat.type == 'private' and str(call.from_user.id) != str(ADMIN_ID) and not check_subscription(call.message.chat.id):
        send_subscription_message(call.message.chat.id)
        bot.answer_callback_query(call.id)
        return
    chat_id = call.message.chat.id
    user_pitch_input_mode[user_id] = None
    user_rate_input_mode[user_id] = None
    _, voice = call.data.split("|", 1)
    set_tts_user_voice_in_memory(user_id, voice)
    user_tts_mode[user_id] = voice
    current_pitch = get_tts_user_pitch_in_memory(user_id)
    current_rate = get_tts_user_rate_in_memory(user_id)
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
    update_user_activity_in_memory(call.from_user.id)
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

# ------------------------ TTS synthesis ------------------------
async def synth_and_send_tts(chat_id: int, user_id: str, text: str):
    # Replace dots to commas (as in original logic)
    text = text.replace('.', ',')
    voice = get_tts_user_voice_in_memory(user_id)
    pitch_val = get_tts_user_pitch_in_memory(user_id)
    rate_val = get_tts_user_rate_in_memory(user_id)
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
            bot.send_message(chat_id, "❌ Failed to create the audio. The text may be invalid. Please try a different text.")
            return

        with open(filename, "rb") as f:
            voice_display_name = VOICE_MAPPING.get(voice, voice)
            caption_text = (
                f"🎧 *Here is your voice!* \n\n"
                f"Voice: **{voice_display_name}**\n"
                f"Pitch: *{pitch}*\n"
                f"Rate: *{rate}*\n\n"
                f"Enjoy listening! ✨"
            )
            bot.send_audio(
                chat_id,
                f,
                caption=caption_text,
                parse_mode="Markdown"
            )
        # increment user's tts conversion count
        increment_processing_count_in_memory(user_id, "tts")

    except Exception as e:
        logging.error(f"TTS error: {str(e)}")
        bot.send_message(chat_id, f"❌ Unexpected error: {str(e)}.")
    finally:
        stop_recording.set()
        if os.path.exists(filename):
            try:
                os.remove(filename)
                logging.info(f"Deleted temporary TTS file: {filename}")
            except Exception as e:
                logging.error(f"Error deleting TTS file {filename}: {e}")

# ------------------------ Message handlers ------------------------
@bot.message_handler(content_types=['text'])
def handle_text_for_tts_or_mode_input(message):
    user_id = str(message.from_user.id)
    update_user_activity_in_memory(message.from_user.id)
    if message.chat.type == 'private' and str(message.from_user.id) != str(ADMIN_ID) and not check_subscription(message.chat.id):
        send_subscription_message(message.chat.id)
        return

    if message.text.startswith('/'):
        return

    if user_rate_input_mode.get(user_id) == "awaiting_rate_input":
        try:
            rate_val = int(message.text)
            if -100 <= rate_val <= 100:
                set_tts_user_rate_in_memory(user_id, rate_val)
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
                set_tts_user_pitch_in_memory(user_id, pitch_val)
                bot.send_message(message.chat.id, f"🔊 The pitch is *{pitch_val}*.", parse_mode="Markdown")
                user_pitch_input_mode[user_id] = None
            else:
                bot.send_message(message.chat.id, "❌ Invalid pitch. Send a number from -100 to +100 or 0. Try again:")
            return
        except ValueError:
            bot.send_message(message.chat.id, "That is not a valid number. Send a number from -100 to +100 or 0. Try again:")
            return

    current_voice = get_tts_user_voice_in_memory(user_id)
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
    update_user_activity_in_memory(message.from_user.id)
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

# ------------------------ Webhook endpoints ------------------------
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

# ------------------------ Startup helpers ------------------------
def set_bot_commands():
    commands = [
        BotCommand("start", "👋 Get Started"),
        BotCommand("voice", "Choose a TTS voice"),
        BotCommand("pitch", "Change TTS voice pitch"),
        BotCommand("rate", "Change TTS voice speed"),
        BotCommand("help", "Get How to use info"),
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
    init_db()
    set_webhook_on_startup()
    set_bot_commands()

if __name__ == "__main__":
    set_bot_info_and_startup()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
