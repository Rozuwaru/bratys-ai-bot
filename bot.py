import os
import threading
import time
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google import genai

# Простой веб-сервер для бесплатного тарифа Render
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    # Попытка запроса с автоматическим повтором при перегрузке (ошибка 503)
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=user_text,
            )
            await update.message.reply_text(response.text)
            return
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(2)
                continue
            await update.message.reply_text(f"Произошла ошибка: {e}")
            break

def main():
    # Запуск веб-сервера в отдельном потоке
    threading.Thread(target=run_web, daemon=True).start()

    # Запуск Telegram бота
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
