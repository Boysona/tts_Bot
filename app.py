import os
import requests
import telebot
from telebot import types
from flask import Flask, request
import yt_dlp
import re
from urllib.parse import urlparse
import uuid

app = Flask(__name__)

BOT_TOKEN = '8136008912:AAHwM1ZBZ2WxgCnFpRA0MC_EIr9KcRQiF3c'
WEBHOOK_URL = 'https://tts-bot-2.onrender.com' + '/' + BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)

SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be',
    'instagram.com', 'instagr.am',
    'tiktok.com',
    'twitter.com', 'x.com',
    'facebook.com', 'fb.watch',
    'reddit.com',
    'pinterest.com',
    'likee.video',
    'snapchat.com',
    'threads.net'
]

def is_supported_url(url):
    try:
        domain = urlparse(url).netloc.lower()
        return any(supported in domain for supported in SUPPORTED_DOMAINS)
    except:
        return False

def extract_video_info(url):
    ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'best'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            print(f"Error extracting video info: {e}")
            return None

def download_video(url):
    ydl_opts = {'format': 'best', 'quiet': True, 'no_warnings': True, 'outtmpl': f'downloads/%(id)s.%(ext)s'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename, info
        except Exception as e:
            print(f"Error downloading video: {e}")
            return None, None

def clean_filename(filename):
    return re.sub(r'[^\w\-_. ]', '', filename)

def create_downloads_folder():
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🌟 *Welcome to Video Downloader Bot* 🌟

Send me a link from:
- YouTube
- Instagram (Posts/Stories/Reels)
- TikTok
- Twitter/X
- Facebook
- Reddit
- Pinterest
- Likee
- Snapchat
- Threads

I'll download the video for you!

📌 *Note*: Some private or age-restricted videos may not be downloadable.
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    text = message.text
    
    if not is_supported_url(text):
        bot.reply_to(message, "❌ Unsupported URL. Please send a valid video link from supported platforms.")
        return
    
    processing_msg = bot.reply_to(message, "🔍 Processing your link, please wait...")
    
    try:
        video_info = extract_video_info(text)
        if not video_info:
            bot.edit_message_text("❌ Failed to get video information. The link might be invalid or private.", 
                                  chat_id=message.chat.id, 
                                  message_id=processing_msg.message_id)
            return
        
        title = video_info.get('title', 'Untitled Video')
        duration = video_info.get('duration', 0)
        uploader = video_info.get('uploader', 'Unknown')
        filesize = video_info.get('filesize') or video_info.get('filesize_approx')
        filesize_text = f"{round(filesize / (1024*1024), 2)} MB" if filesize else "Unknown"

        details_text = f"""
📹 *Video Details*:
- Title: {title}
- Duration: {duration} seconds
- Uploader: {uploader}
- File Size: {filesize_text}

⬇️ *Downloading video...* Please wait.
"""
        bot.edit_message_text(details_text, 
                              chat_id=message.chat.id, 
                              message_id=processing_msg.message_id,
                              parse_mode='Markdown')
        
        create_downloads_folder()
        video_path, info = download_video(text)
        
        if not video_path or not os.path.exists(video_path):
            bot.edit_message_text("❌ Failed to download the video. Please try again later.", 
                                  chat_id=message.chat.id, 
                                  message_id=processing_msg.message_id)
            return
        
        thumbnail_url = info.get('thumbnail')
        thumbnail_file = None
        if thumbnail_url:
            r = requests.get(thumbnail_url)
            thumb_path = f"downloads/{uuid.uuid4()}.jpg"
            with open(thumb_path, 'wb') as f:
                f.write(r.content)
            thumbnail_file = open(thumb_path, 'rb')
        
        with open(video_path, 'rb') as video_file:
            bot.send_video(message.chat.id, video_file, 
                           caption=f"🎥 *{title}*\n\n✅ Downloaded by @{bot.get_me().username}",
                           parse_mode='Markdown',
                           reply_to_message_id=message.message_id,
                           thumb=thumbnail_file)
        
        bot.delete_message(message.chat.id, processing_msg.message_id)
        
        try:
            os.remove(video_path)
            if thumbnail_file:
                thumbnail_file.close()
                os.remove(thumb_path)
        except:
            pass
            
    except Exception as e:
        print(f"Error handling message: {e}")
        bot.edit_message_text("❌ An error occurred while processing your request. Please try again later.", 
                              chat_id=message.chat.id, 
                              message_id=processing_msg.message_id)

@app.route('/')
def index():
    return "✅ Bot is running via webhook!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Webhook Error: {e}")
        return f"Webhook Error: {e}", 500
    return '', 200

if __name__ == "__main__":
    create_downloads_folder()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"✅ Webhook set to: {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=8080)
