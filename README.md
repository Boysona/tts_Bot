# Telegram TTS Bot

This is a Telegram bot that converts text messages into speech using Microsoft Edge TTS (`edge-tts`).  
The bot responds to user messages with an audio file of the spoken text in the selected voice.

## Features
- Converts text messages into speech
- Supports multiple voices from Microsoft Edge TTS
- Admin-only restrictions (only the admin can use the bot)
- Runs with Flask for webhook support
- Can be deployed to services like Koyeb, Heroku, etc.

## Requirements
Python 3.9+ recommended.  
Install dependencies using:

```bash
pip install -r requirements.txt
```

## Environment Variables
Create a `.env` file in the project root and set the following variables:

```
TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_user_id
```
- `TOKEN` → Telegram Bot token from [BotFather](https://t.me/botfather)  
- `ADMIN_ID` → Your Telegram numeric user ID (only you can use the bot)

## Running the Bot

### Local Development
You can run the bot locally with polling (not recommended for production):

```bash
python bot.py
```

### Production (Webhook + Flask)
When deploying on a cloud platform, the Flask app (`app.py`) will be used to handle webhooks.  
Start the server with Gunicorn:

```bash
gunicorn app:app
```

## File Structure
```
.
├── bot.py                # Main Telegram bot logic
├── app.py                # Flask app for webhook handling
├── requirements.txt      # Python dependencies
├── requirements_no_versions.txt  # Dependencies without version pinning
├── README.md             # Project documentation
└── .env                  # Environment variables (not committed to git)
```

## Deployment Notes
- Use **Gunicorn** or another WSGI server in production.
- Make sure to set environment variables (`TOKEN`, `ADMIN_ID`) in your hosting provider dashboard.
- Configure your Telegram bot webhook to point to your deployed URL.

## License
MIT License
