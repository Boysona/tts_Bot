from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, AIORateLimiter
import asyncio
import ssl
import certifi

# Telegram bot token
TOKEN = "7999849691:AAFNsufKPWU9YyW_CEp7_6BF5cClX8PvR0Y"

# Webhook URL
WEBHOOK_URL = "https://tts-bot-lcn9.onrender.com"

# Bot info
FULL_DESCRIPTION = """This bot converts text into speech using Microsoft Edge TTS.

✨ Features:
    • 💬 Convert your text into high-quality speech
    • 🌐 Supports 100+ languages and dialects: Arabic 🇸🇦, English 🇬🇧, Spanish 🇪🇸, and more!
    • 🗣️ Choose from thousands of different voices
    • ⚡ Customize the pitch, tone, and speed of the voice
    • ✅ Simply send your text and get instant voice output
    • 🎁 Completely free to use

🔥 Enjoy unlimited free usage and get started! 👌🏻
"""

SHORT_DESCRIPTION = """Enjoy my services

Need help? ☎️ Contact: @kookabeela 🤝

Another useful bot: @MediaToTextBot
"""

DISPLAY_NAME = "Text To Speech Bot"

async def set_bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Set display name
    await context.bot.set_my_name(name=DISPLAY_NAME)
    # Set short description
    await context.bot.set_my_short_description(short_description=SHORT_DESCRIPTION)
    # Set full description
    await context.bot.set_my_description(description=FULL_DESCRIPTION)

    await update.message.reply_text(
        f"✅ Bot info updated!\n\n"
        f"Display Name: {DISPLAY_NAME}\n"
        f"Short Description: {SHORT_DESCRIPTION}\n"
        f"Full Description: {FULL_DESCRIPTION[:50]}... (truncated)"
    )

async def main():
    # For Render / HTTPS hosting
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    app = ApplicationBuilder() \
        .token(TOKEN) \
        .rate_limiter(AIORateLimiter()) \
        .build()

    # Add command to update bot info
    app.add_handler(CommandHandler("updateinfo", set_bot_info))

    # Start webhook
    await app.start()
    await app.bot.set_webhook(url=WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")
    
    # Keep running
    await app.updater.start_polling()  # This line is optional, you may use app.run_webhook() instead
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
