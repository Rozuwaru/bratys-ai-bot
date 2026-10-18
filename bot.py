import os
import threading
import logging
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google import genai
from google.genai.errors import APIError

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------
# Веб-сервер Flask для Render 24/7
# ---------------------------------------------------------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# ---------------------------------------------------------
# Токены и Список API-ключей Gemini
# ---------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Вставьте сюда ваши ключи Google Gemini.
# Можно достать их из переменной окружения (через запятую) или прописать списком:
raw_keys = os.getenv("GEMINI_API_KEYS", "")
if raw_keys:
    API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
else:
    # Запасной вариант: пропишите ключи прямо здесь
    API_KEYS = [
        "AIzaSyВаш_Ключ_1",
        "AIzaSyВаш_Ключ_2",
        "AIzaSyВаш_Ключ_3",
    ]

current_key_index = 0

def get_next_client():
    """Возвращает клиент Gemini с текущим ключом."""
    global current_key_index
    key = API_KEYS[current_key_index]
    return genai.Client(api_key=key)

def rotate_key():
    """Переключает индекс на следующий ключ по кругу."""
    global current_key_index
    if len(API_KEYS) > 1:
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        logging.info(f"Переключились на Gemini API Ключ №{current_key_index + 1}")

# ---------------------------------------------------------
# Обработчик сообщений
# ---------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    attempts = len(API_KEYS)  # Попробуем каждый ключ по очереди при ошибке лимита
    
    for attempt in range(attempts):
        try:
            client = get_next_client()
            
            # Используем актуальную модель Gemini 2.5 Flash
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_text,
            )
            
            await update.message.reply_text(response.text)
            return  # Запрос успешно выполнен, выходим из функции
            
        except APIError as e:
            # Если превышен лимит (ResourceExhausted / HTTP 429) или ключ невалиден
            logging.warning(f"Ошибка API (попытка {attempt + 1}/{attempts}): {e}")
            rotate_key()  # Переключаем ключ на следующий и пробуем заново в цикле
            
        except Exception as e:
            # Неизвестная ошибка
            logging.error(f"Системная ошибка: {e}")
            await update.message.reply_text(f"Произошла ошибка: {e}")
            return

    # Если перебрали все ключи и все оказались исчерпаны
    await update.message.reply_text("Все API-ключи временно исчерпали лимит запросов. Попробуйте чуть позже.")

# ---------------------------------------------------------
# Запуск бота
# ---------------------------------------------------------
def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен на ротационном Google Gemini API!")
    app.run_polling()

if __name__ == '__main__':
    main()
