import telebot
import logging
import os
from datetime import datetime
from flask import Flask, request

# ==========================
# CONFIG
# ==========================
BOT_TOKEN = "7770743573:AAGoaSzjKiC4kZeYaF5ioP5ReMC_wy4R7W0"
WEBHOOK_URL_BASE = "https://tts-bot-1-d7ve.onrender.com"
WEBHOOK_URL_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_URL_BASE + WEBHOOK_URL_PATH
PORT = int(os.environ.get("PORT", 8443))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
bot_start_time = None

app = Flask(__name__)

# ==========================
# LOGGING
# ==========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==========================
# BOT INFO SETUP
# ==========================
def set_bot_info_and_startup():
    """Sets bot name + descriptions in multiple languages (with English fallback)."""
    global bot_start_time
    bot_start_time = datetime.now()
    try:
        bot.set_my_name("Voice to Text Bot - Audio Transcriber")

        # ✅ Fallback (default English)
        bot.set_my_description(
            "This bot transcribes voice messages, audio files, and videos into text. "
            "It can also translate and summarize results, and supports multiple languages.\n\n"
            "• Send audio, voice, or video files up to 20MB\n"
            "• Choose your transcription language\n"
            "• Translate or summarize instantly with buttons\n"
            "• Completely free\n\n"
            "Enjoy fast, accurate transcriptions!\n"
            "Another useful bot: @TextToSpeechBBot"
        )
        bot.set_my_short_description(
            "This bot can transcribe, summarize, and translate any media files for free. "
            "Other useful bot: @TextToSpeechBBot"
        )

        # ✅ English (explicit)
        bot.set_my_description(
            "This bot transcribes voice messages, audio files, and videos into text. "
            "It can also translate and summarize results, and supports multiple languages.\n\n"
            "• Send audio, voice, or video files up to 20MB\n"
            "• Choose your transcription language\n"
            "• Translate or summarize instantly with buttons\n"
            "• Completely free\n\n"
            "Enjoy fast, accurate transcriptions!\n"
            "Another useful bot: @TextToSpeechBBot",
            language_code="en"
        )
        bot.set_my_short_description(
            "This bot can transcribe, summarize, and translate any media files for free. "
            "Other useful bot: @TextToSpeechBBot",
            language_code="en"
        )

        # ✅ Arabic
        bot.set_my_description(
            "🤖 هذا البوت يحول الرسائل الصوتية والملفات الصوتية والفيديو إلى نصوص. "
            "يمكنه أيضًا الترجمة والتلخيص ويدعم لغات متعددة.\n\n"
            "• أرسل ملفات صوتية أو فيديو حتى 20 ميغابايت\n"
            "• اختر لغة النسخ\n"
            "• ترجمة أو تلخيص فوري\n"
            "• مجاني بالكامل",
            language_code="ar"
        )
        bot.set_my_short_description(
            "🎤 بوت لتحويل الصوتيات والفيديو إلى نصوص مع الترجمة والتلخيص.",
            language_code="ar"
        )

        # ✅ Spanish
        bot.set_my_description(
            "🤖 Este bot transcribe mensajes de voz, archivos de audio y videos a texto. "
            "También puede traducir y resumir los resultados, y admite múltiples idiomas.\n\n"
            "• Envía audio, voz o videos de hasta 20 MB\n"
            "• Elige tu idioma de transcripción\n"
            "• Traduce o resume al instante\n"
            "• Totalmente gratis",
            language_code="es"
        )
        bot.set_my_short_description(
            "🎤 Bot para transcribir, resumir y traducir audio y video.",
            language_code="es"
        )

        bot.delete_my_commands()
        logging.info("Bot info updated with fallback English + English + Arabic + Spanish.")
    except Exception as e:
        logging.error(f"Failed to set bot info: {e}")

# ==========================
# MESSAGE HANDLERS
# ==========================
@bot.message_handler(content_types=["text"])
def default_handler(message):
    """Handles text messages."""
    bot.reply_to(
        message,
        "👋 Send me any text and I will convert it into speech using Microsoft Edge TTS."
    )

@bot.message_handler(content_types=["voice", "audio", "video"])
def media_handler(message):
    """Handles media files for transcription."""
    bot.reply_to(message, "⏳ Processing your media...")
    text = fake_tts()
    bot.send_message(message.chat.id, text)

# ==========================
# PLACEHOLDER TTS
# ==========================
def fake_tts():
    """Placeholder for TTS functionality"""
    return "🔊 (Here is where the generated speech/audio will be returned — add TTS engine later)."

# ==========================
# WEBHOOK ROUTE
# ==========================
@app.route(WEBHOOK_URL_PATH, methods=["POST"])
def webhook():
    """Handles incoming webhook updates from Telegram."""
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "", 200
    else:
        return "Bad Request", 403

# ==========================
# STARTUP
# ==========================
if __name__ == "__main__":
    set_bot_info_and_startup()
    try:
        bot.remove_webhook()
        logging.info("Webhook removed successfully.")
    except Exception as e:
        logging.error(f"Failed to remove webhook: {e}")

    try:
        bot.set_webhook(url=WEBHOOK_URL)
        logging.info(f"Webhook set successfully to URL: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Failed to set webhook: {e}")

    app.run(host="0.0.0.0", port=PORT)
