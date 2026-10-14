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

# Список моделей для обхода перегрузки (исключаем проблемную 3.8-flash)
MODELS_TO_TRY = [
    'gemini-2.5-flash',
    'gemini-1.5-flash'
]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    last_error = None

    for model_name in MODELS_TO_TRY:
        for attempt in range(2): # 2 попытки на каждую модель
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_text,
                )
                await update.message.reply_text(response.text)
                return
            except Exception as e:
                last_error = e
                if "503" in str(e):
                    time.sleep(1)
                    continue
                else:
                    break # Если ошибка не 503 (например, 404), сразу переходим к следующей модели в списке

    await update.message.reply_text(f"Не удалось получить ответ.\nПоследняя ошибка: {last_error}")

def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
