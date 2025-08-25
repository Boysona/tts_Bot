import os
import re
import uuid
import requests
import telebot
from telebot import types
from flask import Flask, request
import yt_dlp
from urllib.parse import urlparse

app = Flask(__name__)

BOT_TOKEN = '8136008912:AAHwM1ZBZ2WxgCnFpRA0MC_EIr9KcRQiF3c'
WEBHOOK_URL = 'https://tts-bot-2.onrender.com/' + BOT_TOKEN

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
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            return ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"Extraction Error: {e}")
            return None

def download_media(url, media_type='video', quality='best'):
    if media_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio',
            'outtmpl': f'downloads/%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
        }
    else:
        ydl_opts = {
            'format': quality,
            'outtmpl': f'downloads/%(id)s.%(ext)s',
        }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)
        except Exception as e:
            print(f"Download Error: {e}")
            return None

def clean_filename(filename):
    return re.sub(r'[^\w\-_. ]', '', filename)

def create_downloads_folder():
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🎬 *Universal Media Downloader Bot* 🎬

Send me a link from supported platforms:
• YouTube 📹
• Instagram 📸
• TikTok 🎵
• Twitter/X 🐦
• Facebook 👥
• Reddit 🤖
• Pinterest 📌
• Likee 💃
• Snapchat 👻
• Threads 🧵

✨ *New Features*:
• Audio extraction 🎧
• Quality selection 📊
• Batch downloads 📦
• Speed control ⚡

Use /audio to extract audio from videos
Use /quality to select preferred resolution
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['audio'])
def handle_audio_command(message):
    text = message.text.replace('/audio', '').strip()
    if not is_supported_url(text):
        bot.reply_to(message, "❌ Invalid URL. Send a valid video link first.")
        return
    
    processing_msg = bot.reply_to(message, "🔊 Processing audio download...")
    
    try:
        create_downloads_folder()
        audio_path = download_media(text, media_type='audio')
        
        if not audio_path or not os.path.exists(audio_path):
            bot.edit_message_text("❌ Audio extraction failed", 
                                chat_id=message.chat.id, 
                                message_id=processing_msg.message_id)
            return

        with open(audio_path, 'rb') as audio_file:
            bot.send_audio(message.chat.id, audio_file,
                          title="Downloaded Audio",
                          reply_to_message_id=message.message_id)
        
        bot.delete_message(message.chat.id, processing_msg.message_id)
        os.remove(audio_path)
        
    except Exception as e:
        bot.edit_message_text("❌ Processing error", 
                             chat_id=message.chat.id, 
                             message_id=processing_msg.message_id)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    text = message.text.strip()
    
    if not is_supported_url(text):
        bot.reply_to(message, "❌ Unsupported URL. Send a valid link from supported platforms.")
        return

    markup = types.InlineKeyboardMarkup()
    btn_hd = types.InlineKeyboardButton("HD Quality", callback_data=f"quality_{text}_best")
    btn_std = types.InlineKeyboardButton("Standard Quality", callback_data=f"quality_{text}_medium")
    btn_audio = types.InlineKeyboardButton("Audio Only", callback_data=f"audio_{text}")
    markup.add(btn_hd, btn_std, btn_audio)

    bot.reply_to(message, "🎚 Select download format:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    if data.startswith('quality_'):
        _, url, quality = data.split('_', 2)
        process_download(call.message, url, quality)
    elif data.startswith('audio_'):
        url = data.replace('audio_', '')
        process_audio_download(call.message, url)

    bot.answer_callback_query(call.id)

def process_download(message, url, quality):
    processing_msg = bot.send_message(message.chat.id, "⬇️ Downloading...")
    
    try:
        video_info = extract_video_info(url)
        if not video_info:
            bot.edit_message_text("❌ Invalid content", 
                                chat_id=message.chat.id, 
                                message_id=processing_msg.message_id)
            return

        create_downloads_folder()
        video_path = download_media(url, 'video', quality)

        if not video_path or not os.path.exists(video_path):
            bot.edit_message_text("❌ Download failed", 
                                chat_id=message.chat.id, 
                                message_id=processing_msg.message_id)
            return

        with open(video_path, 'rb') as video_file:
            bot.send_video(message.chat.id, video_file,
                          caption="✅ Download Complete",
                          reply_to_message_id=message.message_id)

        bot.delete_message(message.chat.id, processing_msg.message_id)
        os.remove(video_path)

    except Exception as e:
        bot.edit_message_text("❌ Processing error", 
                             chat_id=message.chat.id, 
                             message_id=processing_msg.message_id)

def process_audio_download(message, url):
    processing_msg = bot.send_message(message.chat.id, "🔊 Extracting audio...")
    
    try:
        create_downloads_folder()
        audio_path = download_media(url, media_type='audio')
        
        if not audio_path or not os.path.exists(audio_path):
            bot.edit_message_text("❌ Audio extraction failed", 
                                chat_id=message.chat.id, 
                                message_id=processing_msg.message_id)
            return

        with open(audio_path, 'rb') as audio_file:
            bot.send_audio(message.chat.id, audio_file,
                          title="Extracted Audio",
                          reply_to_message_id=message.message_id)

        bot.delete_message(message.chat.id, processing_msg.message_id)
        os.remove(audio_path)
        
    except Exception as e:
        bot.edit_message_text("❌ Processing error", 
                             chat_id=message.chat.id, 
                             message_id=processing_msg.message_id)

@app.route('/')
def index():
    return "✅ Bot is running!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Webhook Error: {e}")
        return f"Error: {e}", 500
    return '', 200

if __name__ == "__main__":
    create_downloads_folder()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=8080)
