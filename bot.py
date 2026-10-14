import os
import threading
import time
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google import genai

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# Автоматически находим первую доступную модель support для генерации текста
def get_working_model():
    try:
        for m in client.models.list():
            if "flash" in m.name and "generateContent" in m.supported_generation_methods:
                return m.name
    except Exception as e:
        print(f"Ошибка при получении списка моделей: {e}")
    return 'gemini-3.8-flash' # Запасной вариант по умолчанию

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    model_to_use = get_working_model()
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_to_use,
                contents=user_text,
            )
            await update.message.reply_text(response.text)
            return
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                await update.message.reply_text(f"Не удалось получить ответ.\nМодель: {model_to_use}\nОшибка: {e}")
                break

def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
