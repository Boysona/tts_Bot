import os
import requests
import telebot
from telebot import types
from flask import Flask, request
import re
from urllib.parse import urlparse

# ------------------------------
# Flask App
# ------------------------------
app = Flask(__name__)

# ------------------------------
# Bot Configuration
# ------------------------------
BOT_TOKEN = "8136008912:AAHwM1ZBZ2WxgCnFpRA0MC_EIr9KcRQiF3c"
WEBHOOK_URL = "https://tts-bot-2.onrender.com" + "/" + BOT_TOKEN
bot = telebot.TeleBot(BOT_TOKEN)

# ------------------------------
# Supported Domains
# ------------------------------
SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be",
    "instagram.com", "instagr.am",
    "tiktok.com",
    "twitter.com", "x.com",
    "facebook.com", "fb.watch",
    "reddit.com",
    "pinterest.com",
    "likee.video",
    "snapchat.com",
    "threads.net"
]

# ------------------------------
# Helpers
# ------------------------------

def is_supported_url(url: str) -> bool:
    """Check if URL is from a supported domain."""
    try:
        domain = urlparse(url).netloc.lower()
        return any(supported in domain for supported in SUPPORTED_DOMAINS)
    except:
        return False

def get_download_link(url: str):
    """
    Use smdownloader.site API to fetch download link.
    This API supports YouTube, TikTok, Instagram, Twitter, etc.
    """
    try:
        api_url = "https://www.smdownloader.site/api/download"
        res = requests.post(api_url, json={"url": url}, timeout=30)

        if res.status_code != 200:
            return None

        data = res.json()
        if not data.get("success"):
            return None

        return data.get("links", [])
    except Exception as e:
        print(f"Error fetching download link: {e}")
        return None

def clean_filename(filename: str) -> str:
    """Sanitize filenames."""
    return re.sub(r"[^\w\-_. ]", "", filename)

# ------------------------------
# Bot Handlers
# ------------------------------

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    welcome_text = """
🌟 *Welcome to Video Downloader Bot* 🌟

Send me a link from:
- YouTube
- Instagram
- TikTok
- Twitter/X
- Facebook
- Reddit
- Pinterest
- Likee
- Snapchat
- Threads

I’ll download the video for you!

📌 Note: Private or age-restricted content may not work.
"""
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True, content_types=["text"])
def handle_message(message):
    text = message.text.strip()

    if not is_supported_url(text):
        bot.reply_to(message, "❌ Unsupported URL. Please send a valid video link.")
        return

    processing_msg = bot.reply_to(message, "🔍 Processing your link... Please wait.")

    try:
        links = get_download_link(text)
        if not links:
            bot.edit_message_text("❌ Could not fetch download link. The video may be private or unsupported.",
                                  chat_id=message.chat.id,
                                  message_id=processing_msg.message_id)
            return

        # Take the first available link
        download_url = links[0].get("url")
        quality = links[0].get("quality", "Best")

        if not download_url:
            bot.edit_message_text("❌ Failed to extract video link.",
                                  chat_id=message.chat.id,
                                  message_id=processing_msg.message_id)
            return

        # Send video directly
        bot.send_video(
            message.chat.id,
            download_url,
            caption=f"🎥 Downloaded from: {text}\n📌 Quality: {quality}",
            reply_to_message_id=message.message_id
        )

        bot.delete_message(message.chat.id, processing_msg.message_id)

    except Exception as e:
        print(f"Error: {e}")
        bot.edit_message_text("❌ An error occurred while processing your request.",
                              chat_id=message.chat.id,
                              message_id=processing_msg.message_id)

# ------------------------------
# Flask Routes
# ------------------------------

@app.route("/")
def index():
    return "✅ Bot is running via webhook!", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Webhook Error: {e}")
        return f"Webhook Error: {e}", 500
    return "", 200

# ------------------------------
# Main
# ------------------------------

if __name__ == "__main__":
    # Set webhook
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"✅ Webhook set to: {WEBHOOK_URL}")

    # Run Flask app
    app.run(host="0.0.0.0", port=8080)
