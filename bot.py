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

# Чтение ключей с очисткой от пробелов, кавычек и спецсимволов UTF-8
raw_keys = os.getenv("GEMINI_API_KEYS", "")
if raw_keys:
    # Очищаем каждый ключ от любых лишних символов и кавычек
    API_KEYS = [k.strip(' "\' \t\r\n') for k in raw_keys.split(",") if k.strip(' "\' \t\r\n')]
else:
    API_KEYS = []

current_key_index = 0

def get_next_client():
    """Возвращает клиент Gemini с текущим очищенным ключом."""
    global current_key_index
    if not API_KEYS:
        raise ValueError("Переменная GEMINI_API_KEYS пуста или ключи указаны неверно!")
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
    
    if not API_KEYS:
        await update.message.reply_text("Ошибка: В настройках Render не задана переменная GEMINI_API_KEYS.")
        return

    attempts = len(API_KEYS)
    
    for attempt in range(attempts):
        try:
            client = get_next_client()
            
            # Используем модель Gemini 3.8 Flash
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=user_text,
            )
            
            await update.message.reply_text(response.text)
            return  # Ответ успешно отправлен
            
        except APIError as e:
            logging.warning(f"Ошибка API (попытка {attempt + 1}/{attempts}): {e}")
            rotate_key()  # Переключаем на следующий ключ
            
        except Exception as e:
            logging.error(f"Системная ошибка: {e}")
            await update.message.reply_text(f"Произошла ошибка: {e}")
            return

    await update.message.reply_text("Все API-ключи временно исчерпали лимит запросов. Попробуйте чуть позже.")

# ---------------------------------------------------------
# Запуск бота
# ---------------------------------------------------------
def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен на Gemini 3.8 Flash!")
    app.run_polling()

if __name__ == '__main__':
    main()
