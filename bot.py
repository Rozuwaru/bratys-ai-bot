import os
import threading
import logging
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ---------------------------------------------------------
# Веб-сервер Flask для работы на Render 24/7
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

raw_keys = os.getenv("GEMINI_API_KEYS", "")
if raw_keys:
    # Безопасная очистка ключей от кавычек, пробелов и переносов
    API_KEYS = [k.strip(' "\' \t\r\n') for k in raw_keys.split(",") if k.strip(' "\' \t\r\n')]
else:
    API_KEYS = []

current_key_index = 0

def get_next_client():
    global current_key_index
    if not API_KEYS:
        raise ValueError("Переменная GEMINI_API_KEYS пуста!")
    key = API_KEYS[current_key_index]
    return genai.Client(api_key=key)

def rotate_key():
    global current_key_index
    if len(API_KEYS) > 1:
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        logging.info(f"Переключились на Gemini API Ключ №{current_key_index + 1}")

# Фоновая отправка статуса «печатает...»
async def send_typing_action(chat, stop_event):
    while not stop_event.is_set():
        try:
            await chat.send_action("typing")
            await asyncio.sleep(4)  # обновляем статус каждые 4 секунды
        except Exception:
            break

# ---------------------------------------------------------
# Обработчик текстовых сообщений и картинок
# ---------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user_text = update.message.caption or update.message.text or "Опиши эту картинку"
    
    if not API_KEYS:
        await update.message.reply_text("Ошибка: В настройках Render не задана переменная GEMINI_API_KEYS.")
        return

    # Запускаем фоновую индикацию "печатает..."
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(send_typing_action(chat, stop_typing))

    contents = [user_text]

    # Обработка изображения, если пользователь его прислал
    if update.message.photo:
        try:
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            
            contents = [
                user_text,
                types.Part.from_bytes(
                    data=bytes(photo_bytes),
                    mime_type="image/jpeg"
                )
            ]
        except Exception as e:
            stop_typing.set()
            await typing_task
            await update.message.reply_text(f"Не удалось обработать картинку: {e}")
            return

    attempts = len(API_KEYS)
    response_text = None

    # Грамотно оформленная системная инструкция
    sys_instruction = (
        "Твоё имя — Братуся AI.  Также в конце каждого сообщения, которое ты отправляешь, ты должен писать: "
        "«Переверните телефон, чтобы продолжить». "
        "Когда тебе пишут привет или что то подобное, ты должен отвечать:"
        "«Я Братуся AI, меня создал мой господин Арсений»."
        "После приветствия говори:"
        "«Как наказать Амира сегодня?»."
        "Никогда не называй себя языковой моделью Gemini, Google или искусственным интеллектом от Google. "
    )

    # Внутренняя функция для синхронного вызова Gemini без блокировки asyncio
    def call_gemini():
        nonlocal response_text
        for attempt in range(attempts):
            try:
                client = get_next_client()
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_instruction,
                        temperature=0.3
                    )
                )
                response_text = response.text
                break
            except APIError as e:
                logging.warning(f"Ошибка API (попытка {attempt + 1}/{attempts}): {e}")
                rotate_key()
            except Exception as e:
                logging.error(f"Системная ошибка: {e}")
                break

    try:
        # Выполняем блокирующий запрос в отдельном потоке, чтобы не тормозить статусы Telegram
        await asyncio.to_thread(call_gemini)
    finally:
        # В любом случае останавливаем статус "печатает..."
        stop_typing.set()
        await typing_task

    if response_text:
        await update.message.reply_text(response_text)
    else:
        await update.message.reply_text("Господин Арсений дал мне отдохнуть. Спросите чуть позже.")

# ---------------------------------------------------------
# Запуск бота
# ---------------------------------------------------------
def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # Ловим текст и фотографии
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_message))
    print("Бот успешно запущен!")
    app.run_polling()

if __name__ == '__main__':
    main()
