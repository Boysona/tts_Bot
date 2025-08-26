#!/usr/bin/env python3
# bot.py
import os
import requests
import telebot
from telebot import types
import yt_dlp
import re
from urllib.parse import urlparse
import uuid
import time
import threading
from datetime import datetime
from flask import Flask, request, abort
import logging

# --- Configuration ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8136008912:AAHwM1ZBZ2WxgCnFpRA0MC_EIr9KcRQiF3c')
# Default webhook URL, override with environment variable in your hosting platform
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://tts-bot-2.onrender.com')
# Use webhook by default; set USE_WEBHOOK="False" to use polling instead
USE_WEBHOOK = os.environ.get('USE_WEBHOOK', 'True').lower() in ('1', 'true', 'yes')
# Port for Flask (Render usually supplies PORT env var)
PORT = int(os.environ.get('PORT', 5000))

# --- Logging config ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN)

# Supported domains list (kept from your original code)
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be',
    'instagram.com', 'instagr.am', 'www.instagram.com',
    'tiktok.com', 'www.tiktok.com',
    'twitter.com', 'x.com', 't.co',
    'facebook.com', 'fb.watch', 'www.facebook.com',
    'reddit.com', 'www.reddit.com',
    'pinterest.com', 'www.pinterest.com',
    'likee.video', 'www.likee.video',
    'snapchat.com', 'www.snapchat.com',
    'threads.net', 'www.threads.net',
    'vimeo.com', 'www.vimeo.com',
    'dailymotion.com', 'www.dailymotion.com'
]

def is_supported_url(url):
    try:
        domain = urlparse(url).netloc.lower()
        domain = domain.replace('www.', '')  # Remove www prefix
        return any(supported in domain for supported in SUPPORTED_DOMAINS)
    except:
        return False

def get_user_agent():
    """Returns a realistic user agent string"""
    return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def extract_video_info(url):
    """Extract video information with enhanced Instagram support"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'user_agent': get_user_agent(),
        'http_headers': {
            'User-Agent': get_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        },
        'extractor_args': {
            'instagram': {
                'api_version': 'v1',
                'include_stories': True,
            }
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            logger.warning(f"Error extracting video info with primary method: {e}")
            # Try alternative approach for Instagram
            if 'instagram.com' in url:
                return extract_instagram_alternative(url)
            return None

def extract_instagram_alternative(url):
    """Alternative Instagram extraction method"""
    alt_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'cookies_from_browser': None,
        'user_agent': get_user_agent(),
    }
    
    with yt_dlp.YoutubeDL(alt_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            logger.warning(f"Instagram alternative extractor failed: {e}")
            return None

def download_video(url):
    """Download video with enhanced Instagram support and FFmpeg processing"""
    unique_id = str(uuid.uuid4())[:8]
    
    ydl_opts = {
        'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'downloads/{unique_id}_%(title).50s.%(ext)s',
        'user_agent': get_user_agent(),
        'http_headers': {
            'User-Agent': get_user_agent(),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Referer': 'https://www.instagram.com/',
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'merge_output_format': 'mp4',
        'writesubtitles': False,
        'writeautomaticsub': False,
        'extractor_args': {
            'instagram': {
                'api_version': 'v1',
                'include_stories': True,
            }
        },
        'socket_timeout': 30,
        'retries': 3,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Clean and ensure proper filename
            clean_filename_path = clean_and_fix_filename(filename)
            
            if os.path.exists(clean_filename_path):
                return clean_filename_path
            
            # Try to find the actual downloaded file
            download_dir = 'downloads'
            for file in os.listdir(download_dir):
                if unique_id in file and file.endswith('.mp4'):
                    return os.path.join(download_dir, file)
            
            return None
        except Exception as e:
            logger.warning(f"Error downloading video: {e}")
            # Try alternative download for Instagram
            if 'instagram.com' in url:
                return download_instagram_alternative(url, unique_id)
            return None

def download_instagram_alternative(url, unique_id):
    """Alternative Instagram download method"""
    alt_opts = {
        'format': 'best[height<=720]/best',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'downloads/{unique_id}_instagram.%(ext)s',
        'cookies_from_browser': None,
        'user_agent': get_user_agent(),
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 30,
        'retries': 2,
    }
    
    with yt_dlp.YoutubeDL(alt_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return clean_and_fix_filename(filename)
        except Exception as e:
            logger.warning(f"Instagram alternative download failed: {e}")
            return None

def clean_and_fix_filename(filename):
    """Clean filename and ensure .mp4 extension"""
    if not filename:
        return None
    
    # Remove invalid characters
    clean_name = re.sub(r'[^\w\-_. ]', '', os.path.basename(filename))
    directory = os.path.dirname(filename)
    
    # Ensure .mp4 extension
    if not clean_name.lower().endswith('.mp4'):
        base_name = os.path.splitext(clean_name)[0]
        clean_name = base_name + '.mp4'
    
    clean_path = os.path.join(directory, clean_name)
    
    # Rename file if necessary
    if filename != clean_path and os.path.exists(filename):
        try:
            os.rename(filename, clean_path)
            return clean_path
        except:
            return filename
    
    return clean_path if os.path.exists(clean_path) else filename

def create_downloads_folder():
    """Create downloads directory if it doesn't exist"""
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

def cleanup_old_files():
    """Clean up old downloaded files (older than 1 hour)"""
    try:
        downloads_dir = 'downloads'
        current_time = time.time()
        
        for filename in os.listdir(downloads_dir):
            file_path = os.path.join(downloads_dir, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getctime(file_path)
                if file_age > 3600:  # 1 hour
                    os.remove(file_path)
    except Exception as e:
        logger.warning(f"Error cleaning up files: {e}")

def format_duration(seconds):
    """Format duration in human readable format"""
    if not seconds or seconds <= 0:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(secs)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(secs)}s"
    else:
        return f"{int(secs)}s"

# --- Bot Handlers (unchanged logic) ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = f"""
🎥 *Welcome to Video Downloader Bot!*

I can download videos from:
• YouTube (videos, shorts)
• Instagram (posts, reels, stories)
• TikTok
• Twitter/X
• Facebook
• Reddit
• Pinterest
• Vimeo
• Dailymotion
• And many more!

📝 *How to use:*
Just send me a video link and I'll download it for you!

⚡ *Features:*
• High quality downloads
• Fast processing
• Auto-cleanup
• Multiple format support

Send me a link to get started! 🚀
"""
    
    markup = types.InlineKeyboardMarkup()
    help_btn = types.InlineKeyboardButton("📖 Help", callback_data="help")
    about_btn = types.InlineKeyboardButton("ℹ️ About", callback_data="about")
    markup.row(help_btn, about_btn)
    
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "help":
        help_text = """
🆘 *Help & Tips:*

1. Send any supported video URL
2. Wait for processing (may take a few moments)
3. Download will be sent automatically

⚠️ *Troubleshooting:*
• Private videos may not work
• Some platforms may have restrictions
• Large files might take longer

✅ *Supported formats:*
• Most video formats are converted to MP4
• Audio quality is preserved
"""
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')
    
    elif call.data == "about":
        about_text = """
🤖 *About Video Downloader Bot*

Version: 2.0
Updated: January 2025

Features:
• Enhanced Instagram support
• FFmpeg processing
• Auto file cleanup
• Error recovery
• Multi-platform support

Made with ❤️ using Python & yt-dlp
"""
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, about_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    text = message.text.strip()
    
    if not is_supported_url(text):
        error_msg = """
❌ *Unsupported URL*

Please send a valid video link from supported platforms:
• YouTube, Instagram, TikTok
• Twitter, Facebook, Reddit
• And many more!

Try again with a different link 🔄
"""
        bot.reply_to(message, error_msg, parse_mode='Markdown')
        return
    
    # Start processing
    processing_msg = bot.reply_to(message, "🔍 *Processing your link...*\nPlease wait a moment ⏳", parse_mode='Markdown')
    
    try:
        # Extract video info
        video_info = extract_video_info(text)
        
        if not video_info:
            bot.edit_message_text(
                "❌ *Failed to get video information*\n\nThe link might be:\n• Invalid or expired\n• Private content\n• From an unsupported source\n\nPlease try another link 🔄", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id,
                parse_mode='Markdown'
            )
            return
        
        # Get video details
        title = video_info.get('title', 'Untitled Video')[:100]  # Limit title length
        duration = video_info.get('duration', 0)
        uploader = video_info.get('uploader', 'Unknown')[:50]
        view_count = video_info.get('view_count', 0)
        
        # Format details
        details_text = f"""
📹 *Video Found!*

🎬 **Title:** {title}
⏱️ **Duration:** {format_duration(duration)}
👤 **Uploader:** {uploader}
👁️ **Views:** {view_count:,} (if available)

⬇️ *Starting download...* 
Please wait, this may take a moment ⏳
"""
        
        bot.edit_message_text(
            details_text, 
            chat_id=message.chat.id, 
            message_id=processing_msg.message_id,
            parse_mode='Markdown'
        )
        
        # Create downloads folder and cleanup old files
        create_downloads_folder()
        threading.Thread(target=cleanup_old_files, daemon=True).start()
        
        # Download video
        video_path = download_video(text)
        
        if not video_path or not os.path.exists(video_path):
            bot.edit_message_text(
                "❌ *Download failed*\n\nPossible reasons:\n• Video is private/restricted\n• Server overload\n• Network issues\n\nPlease try again later 🔄", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id,
                parse_mode='Markdown'
            )
            return
        
        # Check file size (Telegram limit is 50MB for bots)
        file_size = os.path.getsize(video_path)
        if file_size > 50 * 1024 * 1024:  # 50MB
            bot.edit_message_text(
                f"❌ *File too large*\n\nFile size: {file_size / (1024*1024):.1f} MB\nTelegram limit: 50 MB\n\nTry a shorter video or different quality 📹", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id,
                parse_mode='Markdown'
            )
            try:
                os.remove(video_path)
            except:
                pass
            return
        
        # Send video
        try:
            with open(video_path, 'rb') as video_file:
                caption = f"🎥 **{title[:100]}**\n\n✅ Downloaded successfully!\n🤖 @{bot.get_me().username}"
                
                bot.send_video(
                    message.chat.id, 
                    video_file, 
                    caption=caption,
                    parse_mode='Markdown',
                    reply_to_message_id=message.message_id,
                    supports_streaming=True,
                    width=720,
                    height=480
                )
            
            # Delete processing message
            try:
                bot.delete_message(message.chat.id, processing_msg.message_id)
            except:
                pass
            
            # Clean up file
            try:
                os.remove(video_path)
            except:
                pass
            
        except Exception as e:
            logger.exception(f"Error sending video: {e}")
            bot.edit_message_text(
                "❌ *Failed to send video*\n\nThere was an error uploading the video to Telegram.\nPlease try again 🔄", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.exception(f"Error handling message: {e}")
        try:
            bot.edit_message_text(
                "❌ *An unexpected error occurred*\n\nPlease try again later or contact support if the problem persists 🔄", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id,
                parse_mode='Markdown'
            )
        except:
            bot.reply_to(message, "❌ An error occurred. Please try again.", parse_mode='Markdown')

# --- Webhook (Flask) setup ---

app = Flask(__name__)

# We'll use the token path as the webhook endpoint for simplicity and security by obscurity
WEBHOOK_PATH = f"/{BOT_TOKEN}"
FULL_WEBHOOK_URL = WEBHOOK_URL.rstrip('/') + WEBHOOK_PATH

@app.route('/', methods=['GET'])
def index():
    return "OK - Video Downloader Bot is running.", 200

@app.route(WEBHOOK_PATH, methods=['POST'])
def telegram_webhook():
    """Endpoint to receive telegram updates via webhook"""
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        except Exception as e:
            logger.exception("Failed to process incoming update")
            return '', 500
    else:
        abort(403)

def set_webhook():
    """Set webhook for Telegram to the FULL_WEBHOOK_URL"""
    try:
        # Remove any previous webhook and set the new one
        bot.remove_webhook()
        # If your hosting requires a secret path or certificate, adapt here.
        ok = bot.set_webhook(url=FULL_WEBHOOK_URL)
        if ok:
            logger.info(f"Webhook set to: {FULL_WEBHOOK_URL}")
        else:
            logger.error("Failed to set webhook. Check your WEBHOOK_URL and BOT_TOKEN.")
    except Exception as e:
        logger.exception(f"Exception while setting webhook: {e}")

def remove_webhook():
    try:
        bot.remove_webhook()
    except:
        pass

def start_polling():
    """Start polling (fallback)"""
    try:
        remove_webhook()
        logger.info("Starting polling...")
        bot.infinity_polling(timeout=20, long_polling_timeout=10, none_stop=True)
    except Exception as e:
        logger.exception(f"Polling failed: {e}")

# --- Entrypoint ---

if __name__ == "__main__":
    create_downloads_folder()
    logger.info("🚀 Initializing Video Downloader Bot...")
    logger.info(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Using webhook? {USE_WEBHOOK}")
    # Start cleanup loop in background
    threading.Thread(target=cleanup_old_files, daemon=True).start()

    if USE_WEBHOOK:
        # Try to set webhook and start Flask server
        set_webhook()
        # Flask will listen on PORT (Render supplies $PORT)
        logger.info(f"Starting Flask app for webhook on 0.0.0.0:{PORT} (endpoint {WEBHOOK_PATH})")
        # Important: do not enable debug=True in production
        app.run(host="0.0.0.0", port=PORT)
    else:
        # Fallback to polling (useful for local dev)
        start_polling()
