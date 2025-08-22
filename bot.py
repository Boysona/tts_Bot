import telebot
from flask import Flask, request
import requests

# -----------------------------
# CONFIG
# -----------------------------
TOKEN = "7999849691:AAFNsufKPWU9YyW_CEp7_6BF5cClX8PvR0Y"
WEBHOOK_URL = "https://tts-bot-lcn9.onrender.com"

DISPLAY_NAME = "Text to Speech TTS"
SHORT_DESCRIPTION = """Enjoy my services

Need help? Contact: @kookabeela

Another useful bot: @MediaToTextBot
"""
FULL_DESCRIPTION = """This bot converts text into speech using Microsoft Edge TTS.

Features:
    - Convert your text into high-quality speech
    - Supports 100+ languages and dialects: Arabic, English, Spanish, and more
    - Choose from thousands of different voices
    - Customize the pitch, tone, and speed of the voice
    - Simply send your text and get instant voice output
    - Completely free to use

Enjoy unlimited free usage and get started!
"""

# -----------------------------
# BOT SETUP
# -----------------------------
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# -----------------------------
# COMMAND HANDLER
# -----------------------------
@bot.message_handler(commands=['updateinfo'])
def set_bot_info(message):
    try:
        # Update bot short description
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setMyShortDescription",
            data={"short_description": SHORT_DESCRIPTION}
        )

        # Update bot full description
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setMyDescription",
            data={"description": FULL_DESCRIPTION}
        )

        # Note: Display name update is not officially supported via telebot
        # But you can update it via BotFather manually if needed

        # Notify user
        bot.reply_to(message, f"✅ Bot info updated successfully!\nDisplay Name: {DISPLAY_NAME}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

# -----------------------------
# WEBHOOK ROUTE
# -----------------------------
@app.route("/", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# -----------------------------
# RUN FLASK + SET WEBHOOK
# -----------------------------
if __name__ == "__main__":
    # Remove previous webhook if exists
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    
    # Run Flask server
    app.run(host="0.0.0.0", port=5000)
