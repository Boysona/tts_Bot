import os
import requests
import telebot
from telebot import types
from flask import Flask, request
import yt_dlp
import re
from urllib.parse import urlparse
import uuid
import json

# TikTok Cookies
TIKTOK_COOKIES = {
    "perf_feed_cache": "perf_feed_cache={%22expireTimestamp%22:1756386000000%2C%22itemIds%22:[%227540438326168276230%22%2C%227540427155088428344%22]}",
    "cmpl_token": "cmpl_token=AgQQAPMNF-RO0rfK6FxGcZ0_8swkop0ef4SGYN058w",
    "multi_sids": "multi_sids=7490619758791050246%3A4c4658a487016929d994b30bf2dc3a6c",
    "passport_auth_status": "passport_auth_status=0329c1d7e710b95df63a75de19c7cffb%2C",
    "passport_auth_status_ss": "passport_auth_status_ss=0329c1d7e710b95df63a75de19c7cffb%2C",
    "sessionid": "sessionid=4c4658a487016929d994b30bf2dc3a6c",
    "sessionid_ss": "sessionid_ss=4c4658a487016929d994b30bf2dc3a6c",
    "sid_guard": "sid_guard=4c4658a487016929d994b30bf2dc3a6c%7C1756216778%7C15552000%7CSun%2C+22-Feb-2026+13%3A59%3A38+GMT",
    "sid_tt": "sid_tt=4c4658a487016929d994b30bf2dc3a6c",
    "sid_ucp_v1": "sid_ucp_v1=1.0.0-KGQ4MDQ1NTU5YjM0NzdhOGY2NmI5NjVlMzA0ZGU1MDAyNmRjYWQxZjIKGQiGiI3yvN-B-mcQyvu2xQYYsws4CEAsSAQQAxoGbWFsaXZhIiA0YzQ2NThhNDg3MDE2OTI5ZDk5NGIzMGJmMmRjM2E2Yw",
    "ssid_ucp_v1": "ssid_ucp_v1=1.0.0-KGQ4MDQ1NTU5YjM0NzdhOGY2NmI5NjVlMzA0ZGU1MDAyNmRjYWQxZjIKGQiGiI3yvN-B-mcQyvu2xQYYsws4CEAsSAQQAxoGbWFsaXZhIiA0YzQ2NThhNDg3MDE2OTI5ZDk5NGIzMGJmMmRjM2E2Yw",
    "uid_tt": "uid_tt=81fd54a1b1db6d27425f8aea0a10cb066c5fed79bab5dd7e2cf4f555f6df9283",
    "uid_tt_ss": "uid_tt_ss=81fd54a1b1db6d27425f8aea0a10cb066c5fed79bab5dd7e2cf4f555f6df9283",
    "tt-target-idc-sign": "tt-target-idc-sign=dVsAsA6USt6k-55YpNq-yqIPPyz39q06t4ZR2GMQHjdjsKHAbU5C46hgWYbXXNFzsWEEd3y5F4G1R7u1FAyaCkwLKwyumbYFWeeET4xAIJSJ-XFpmBKFA5m0u_rvIC3l2bZiLJB7iZrLg519a03g7Ycs8bno4pc-7n1xMkQ6svoMpqdJ_eB3ONS35IPBy617sx183MF7ycfGW61b0yib1Yw19H_UsZJhR2ZDdJPb6KtKtCMvbK3Hr5TdC3ng2nwisoBixNlwK3WEEt2eVKV03LQXNhDzVQ-uDa7skRSwX3hVnVZegslvr-dBlAB-72KLu3WBc7Cwwdfk57wPYXF9t9aIIgXhP51vJa4yY8ubrIdgLG8PzCUq83LE1L1rAWYVvBPWhQUQCyP0hqtKKDPm41y3mIkGcXC8xP9cbp2Zz53AN4FNf76lTgW3sUYiOKXBmzeAuKMJrjiaKi2d__8F0ryHSo24mAzpO5SZW9AKnGnTMutnfbHBZHhIFp6RiOVv",
    "odin_tt": "odin_tt=30eec993dd426388a370aae70fc86f181f36043eddefea004666cf3e283b061ce0a0c3729fc8f3ac73b92a1ba26dbd872dfce0fb0b2877d4b7d09246bfa8b4f19ccfcb11aee86c72a0fd523658f8d68a",
    "tt_chain_token": "tt_chain_token=A492qTID0hggSL7r8GnN5w==",
    "msToken": "msToken=nFI_4riHe3GpnJrEVGBcmFTYWXt0gEKdG7n-6k0VGJwu76D_wMM8r5fFqsvDpAVu3nEhTgHO9ZA-ltdU985_K7WrJvlx7acP8Sf2EaQAFyTc6O9DI8iVXjBS1YkhJKDbnGpwJiSi8FiYrSUBeropkQ==",
    "passport_csrf_token": "passport_csrf_token=c755a52b74b519092bd139a2725576b4",
    "passport_csrf_token_default": "passport_csrf_token_default=c755a52b74b519092bd139a2725576b4",
    "last_login_method": "last_login_method=apple",
    "store-country-sign": "store-country-sign=MEIEDLwcCordc-7URmcxGgQgCLxbyHOj-NfAQWRmgJhEk3hjNTjqpbpVhHql7Nj61_oEEAAxn7Sad99FXGNUSHXU5ZU",
    "store-country-code": "store-country-code=so",
    "store-country-code-src": "store-country-code-src=uid",
    "store-idc": "store-idc=maliva",
    "tt-target-idc": "tt-target-idc=useast1a",
    "tiktok_webapp_theme": "tiktok_webapp_theme=light",
    "tiktok_webapp_theme_source": "tiktok_webapp_theme_source=light",
    "ttwid": "ttwid=1%7CcendFTPPIMIE3UL6awuCVk-J5Jo6elOTrU6Mj6QLf-c%7C1756218361%7C9d9254444f424fa16a2edbd3ed6972be0ee9af7ab4c7be82bd8206f7b15784d6",
    "s_v_web_id": "s_v_web_id=verify_mesm3jpl_Iiq2n5gB_8tYx_4O6m_Bo0P_uHT5mBq5FuZ3",
    "tt_csrf_token": "tt_csrf_token=Nh5xcRxe-tgWlpHjX3lUd6rPihARWm9LEMNQ"
}


# Ku badal username-kaaga TikTok
TIKTOK_ACCOUNT_TO_FOLLOW = "lakinuur19"

app = Flask(__name__)

BOT_TOKEN = '8136008912:AAHwM1ZBZ2WxgCnFpRA0MC_EIr9KcRQiF3c'
WEBHOOK_URL = 'https://tts-bot-2.onrender.com' + '/' + BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)

user_states = {}

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
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            print(f"Error extracting video info: {e}")
            return None

def download_video(url):
    ydl_opts = {
        'format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': f'downloads/%(id)s.%(ext)s',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
        except Exception as e:
            print(f"Error downloading video: {e}")
            return None

def create_downloads_folder():
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

def is_user_verified(user_id):
    return user_id in user_states and user_states[user_id].get('verified', False)

def set_user_verified(user_id, verified=True):
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['verified'] = verified

def get_tiktok_user_id(username):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
    }
    url = f"https://www.tiktok.com/node/share/user/@{username}"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data['userInfo']['user']['id']
    except Exception as e:
        print(f"Error getting TikTok user ID for @{username}: {e}")
        return None

def check_tiktok_follow(user_tiktok_username):
    try:
        # Halkan waxaan ku isticmaaleynaa cookies-kaaga si aan ula hadalno server-ka TikTok
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.tiktok.com/",
            "Cookie": "; ".join([f"{k}={v}" for k, v in TIKTOK_COOKIES.items()])
        }
        
        # Tani waxay soo saari doontaa xogta userka
        url = f"https://www.tiktok.com/@{user_tiktok_username}/?is_copy_url=1&is_from_webapp=v1&lang=en"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Halkan waxaan ku baaraynaa page-ka inaan helno haddii userka uu follow-gareeyay
        # Sababtoo ah ma jirto API toos ah oo fudud
        if f'"{TIKTOK_ACCOUNT_TO_FOLLOW}"' in response.text:
            return True, "User is a follower."
        else:
            return False, "User is not a follower."
            
    except Exception as e:
        print(f"Error checking follow status: {e}")
        return False, "An error occurred during verification."

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = f"""
🌟 *Welcome to @{bot.get_me().username}* 🌟

To use this bot, you must first verify that you follow our TikTok account.
Please send your TikTok username to start the verification process.
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['verify'])
def start_verification(message):
    bot.reply_to(message, "Please send your TikTok username to start the verification process.")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    user_id = message.from_user.id
    text = message.text
    
    # Hubi in user-ku uu xaqiijiyay iyo in kale
    if not is_user_verified(user_id):
        # Haddii uusan xaqiijin, hubi inuu soo diray username
        if "@" in text:
            tiktok_username = text.strip().replace("@", "")
        else:
            tiktok_username = text.strip()
        
        processing_msg = bot.reply_to(message, f"🔍 Checking if @{tiktok_username} follows @{TIKTOK_ACCOUNT_TO_FOLLOW}...")
        
        is_following, reason = check_tiktok_follow(tiktok_username)
        
        if is_following:
            set_user_verified(user_id)
            bot.edit_message_text(f"✅ Verification successful! Welcome, @{tiktok_username}. You can now use the bot's services. Send me a video link to download.", 
                                  chat_id=message.chat.id, 
                                  message_id=processing_msg.message_id)
        else:
            bot.edit_message_text(f"❌ Verification failed. Please ensure you have followed @{TIKTOK_ACCOUNT_TO_FOLLOW} and try again.\nReason: {reason}", 
                                  chat_id=message.chat.id, 
                                  message_id=processing_msg.message_id)
        return
    
    # Haddi user-ku xaqiijiyay, u gudub download-ka
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
        
        details_text = f"""
📹 *Video Details*:
- Title: {title}
- Duration: {duration} seconds
- Uploader: {uploader}
        
⬇️ *Downloading video...* Please wait.
"""
        bot.edit_message_text(details_text, 
                              chat_id=message.chat.id, 
                              message_id=processing_msg.message_id,
                              parse_mode='Markdown')
        
        create_downloads_folder()
        video_path = download_video(text)
        
        if not video_path or not os.path.exists(video_path):
            bot.edit_message_text("❌ Failed to download the video. Please try again later.", 
                                  chat_id=message.chat.id, 
                                  message_id=processing_msg.message_id)
            return
        
        with open(video_path, 'rb') as video_file:
            bot.send_video(message.chat.id, video_file, 
                           caption=f"🎥 *{title}* \n\n✅ Downloaded by @{bot.get_me().username}",
                           parse_mode='Markdown',
                           reply_to_message_id=message.message_id)
        
        bot.delete_message(message.chat.id, processing_msg.message_id)
        
        try:
            os.remove(video_path)
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
