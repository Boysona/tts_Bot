import telebot
import logging
import os
from datetime import datetime
from flask import Flask, request

# ==========================
# CONFIG
# ==========================
# Get the bot token from environment variables for security
BOT_TOKEN = os.getenv("BOT_TOKEN", "7790991731:AAF4NHGm0BJCf08JTdBaUWKzwfs82_Y9Ecw")
# Replace with your Render URL
WEBHOOK_URL_BASE = "https://tts-bot-1-d7ve.onrender.com"
# Construct the full webhook URL correctly
WEBHOOK_URL_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_URL_BASE + WEBHOOK_URL_PATH
PORT = int(os.environ.get("PORT", 8443))  # Use environment variable for port

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
bot_start_time = None

app = Flask(__name__)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==========================
# BOT INFO SETUP
# ==========================
def set_bot_info_and_startup():
    """Sets bot information and deletes any existing commands."""
    global bot_start_time
    bot_start_time = datetime.now()
    try:
        bot.set_my_name("Media to Text Bot")
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
            "This bot can transcribe, summarize, and translate any media files for free. Other useful bot: @TextToSpeechBBot"
        )
        bot.delete_my_commands()
        logging.info("Bot info, description updated, and commands removed successfully.")
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

