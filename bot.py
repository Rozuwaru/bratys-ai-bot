import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Веб-сервер для поддержания активности бота на Render 24/7
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# Получаем токены из переменных окружения Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.getenv("GEMINI_API_KEY") # Используем ту же переменную на Render

# Инициализируем клиент OpenAI под API DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "user", 
                    "content": user_text
                }
            ],
            stream=False
        )
        
        reply_text = response.choices[0].message.content
        await update.message.reply_text(reply_text)
        
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {e}")

def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен на DeepSeek!")
    app.run_polling()

if __name__ == '__main__':
    main()
