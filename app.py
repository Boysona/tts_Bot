import requests
import telebot
from telebot import types
from flask import Flask, request
import os
from urllib.parse import urlparse
import uuid

# Flask & Telegram Config
app = Flask(__name__)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8136008912:AAHwM1ZBZ2WxgCnFpRA0MC_EIr9KcRQiF3c")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-app.koyeb.app/" + BOT_TOKEN)

bot = telebot.TeleBot(BOT_TOKEN)

# Base URL ee Node.js API
API_BASE = "http://localhost:2020/api"   # beddel haddii API-ga dibad ku jiro

# Map platform -> API endpoint
ENDPOINTS = {
    "youtube.com": "/youtube",
    "youtu.be": "/youtube",
    "tiktok.com": "/tiktok",
    "facebook.com": "/facebook",
    "fb.watch": "/facebook",
    "soundcloud.com": "/soundcloud",
    "dailymotion.com": "/dailymotion"
}

def get_api_endpoint(url):
    """Find API endpoint by URL domain"""
    domain = urlparse(url).netloc.lower()
    for key, endpoint in ENDPOINTS.items():
        if key in domain:
            return API_BASE + endpoint
    return None

def download_file(dl_url):
    """Download file to /downloads and return path"""
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    filename = f"downloads/{uuid.uuid4()}.mp4"
    with requests.get(dl_url, stream=True) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return filename

# ------------------------------
# Handlers
# ------------------------------

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🌟 *Welcome to Social Media Downloader Bot* 🌟

Send me a link from YouTube, TikTok, Facebook, SoundCloud, Dailymotion...
I'll fetch and send you the video 🎥
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    endpoint = get_api_endpoint(url)

    if not endpoint:
        bot.reply_to(message, "❌ Unsupported URL or platform.")
        return

    processing_msg = bot.reply_to(message, "🔍 Fetching your video, please wait...")

    try:
        # Call Node.js API
        resp = requests.post(endpoint, data={"url": url}, timeout=60)
        if resp.status_code != 200:
            raise Exception(f"Bad status {resp.status_code}")

        data = resp.json()

        # Extract download URL
        dl_url = None
        if "url" in data:
            dl_url = data["url"]
        elif "links" in data and len(data["links"]) > 0:
            dl_url = data["links"][0].get("url")

        if not dl_url:
            bot.edit_message_text("❌ Could not find download link.", 
                                  chat_id=message.chat.id,
                                  message_id=processing_msg.message_id)
            return

        # Download file locally
        video_path = download_file(dl_url)

        # Send video to Telegram
        with open(video_path, "rb") as f:
            bot.send_video(message.chat.id, f,
                           caption=f"✅ Downloaded from {urlparse(url).netloc}",
                           reply_to_message_id=message.message_id)

        # Remove "processing" message
        bot.delete_message(message.chat.id, processing_msg.message_id)

        # Cleanup
        os.remove(video_path)

    except Exception as e:
        print(f"Error: {e}")
        bot.edit_message_text("❌ Failed to process the video.",
                              chat_id=message.chat.id,
                              message_id=processing_msg.message_id)

# ------------------------------
# Flask Routes
# ------------------------------

@app.route('/')
def index():
    return "✅ Bot is running with Social-Media-Downloader API!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=8080)
