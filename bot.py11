import telebot
import logging
from datetime import datetime
from flask import Flask, request

# ==========================
# CONFIG
# ==========================
BOT_TOKEN = "7999849691:AAFNsufKPWU9YyW_CEp7_6BF5cClX8PvR0Y"  # sax
WEBHOOK_URL = "https://tts-bot-lcn9.onrender.com" + BOT_TOKEN          # beddel domain-kaaga

bot = telebot.TeleBot(BOT_TOKEN)
bot_start_time = None
app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)

# ==========================
# BOT INFO SETUP
# ==========================
def set_bot_info_and_startup():
    global bot_start_time
    bot_start_time = datetime.now()
    try:
        # Set bot display name
        bot.set_my_name("Text to Speech TTS")

        # Set long description
        bot.set_my_description(
            "This bot converts text into speech using Microsoft Edge TTS. "
            "It supports more than 100 languages and many accents, and it’s completely free. "
            "Enjoy unlimited usage and get started instantly!"
        )

        # Set short description (multi-line sax)
        bot.set_my_short_description(
            """This bot converts text to speech in multiple languages for free.
Another useful bot: @MediaToTextBot"""
        )

        # Clear commands
        bot.delete_my_commands()

        logging.info("Bot info, description updated, and commands removed successfully.")
    except Exception as e:
        logging.error(f"Failed to set bot info: {e}")


# ==========================
# MESSAGE HANDLER
# ==========================
@bot.message_handler(func=lambda message: True)
def default_handler(message):
    bot.reply_to(
        message,
        "👋 Send me any text and I will convert it into speech using Microsoft Edge TTS."
    )

# ==========================
# MEDIA HANDLERS (PLACEHOLDER)
# ==========================
def fake_tts():
    """Placeholder TTS"""
    return "🔊 (Here is where the generated speech/audio will be returned — add TTS engine later)."

@bot.message_handler(content_types=["voice", "audio", "video"])
def media_handler(message):
    bot.reply_to(message, "⏳ Processing your media...")
    text = fake_tts()
    bot.send_message(message.chat.id, text)

# ==========================
# WEBHOOK ROUTE
# ==========================
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

# ==========================
# STARTUP
# ==========================
if __name__ == "__main__":
    set_bot_info_and_startup()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logging.info("Webhook set and bot started successfully.")
    app.run(host="0.0.0.0", port=8443)
