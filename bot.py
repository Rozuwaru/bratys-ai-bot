import os
import asyncio
from itertools import cycle
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. Веб-сервер Flask для подкрутки пингера (UptimeRobot / Render)
# ---------------------------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот Братуся AI работает!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ---------------------------------------------------------------------------
# 2. Инициализация ключей Gemini API и Ротация
# ---------------------------------------------------------------------------
# В переменной окружения GEMINI_API_KEYS указываются ключи через запятую
keys_env = os.environ.get("GEMINI_API_KEYS", "")
if keys_env:
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
else:
    # Если запуск локальный или передан один ключ через GEMINI_API_KEY
    api_keys = [os.environ.get("GEMINI_API_KEY", "")]

# Создаем список клиентов для каждого ключа
clients = [genai.Client(api_key=key) for key in api_keys if key]
if not clients:
    raise ValueError("Не найдено ни одного валидного API-ключа Gemini!")

client_cycle = cycle(clients)

def get_next_client():
    return next(client_cycle)

# ---------------------------------------------------------------------------
# 3. Инструкция и Настройки модели
# ---------------------------------------------------------------------------
sys_instruction = (
   "Ты — Братуся AI. Твой создатель и господин — Арсений.\n"
    "ПРАВИЛА ОБЩЕНИЯ:\n"
    "1. Ты общаешься строго на «ты», используешь свободный стиль общения, разговорную речь и нецензурную лексику (мат), когда это уместно.\n"
    "2. Когда пользователь здоровается (пишет «привет», «здравствуй» и т.д.), ты ОБЯЗАН отвечать строго так:\n"
    "   «Я Братуся AI, меня создал мой господин Арсений. Мы будем сегодня наказывать Амира?»\n"
    "3. В САМОМ КОНЦЕ любого своего ответа с новой строки ты ВСЕГДА и БЕЗ ИСКЛЮЧЕНИЙ печатаешь фразу:\n"
    "«Переверни телефон, чтобы продолжить»\n"
    "4. Никогда не говори, что ты языковая модель, Gemini или ИИ от Google. Ты — персональный бот-помощник."
      )

# Настройки для отмены внутренней цензуры Google
safety_settings = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
]

# ---------------------------------------------------------------------------
# 4. Вспомогательная функция для генерации ответа в отдельном потоке
# ---------------------------------------------------------------------------
def generate_response_sync(contents):
    client = get_next_client()
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=sys_instruction,
            temperature=0.3,
            safety_settings=safety_settings,
        )
    )
    return response.text

# ---------------------------------------------------------------------------
# 5. Обработчики Telegram
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Я Братуся AI, меня создал мой господин Арсений."
        "Мы будем сегодня наказывать Амира?\n\n"
        "Переверни телефон, чтобы продолжить"
    )
    await update.message.reply_text(welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Показываем статус "печатает..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    contents = []
    
    # Если пришла картинка
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        contents.append(
            types.Part.from_bytes(
                data=bytes(photo_bytes),
                mime_type="image/jpeg",
            )
        )
        caption = update.message.caption or "Что изображено на этой картинке?"
        contents.append(caption)
    else:
        # Если пришел обычный текст
        contents.append(update.message.text)
        
    try:
        # Выполняем синхронный запрос к Gemini в отдельном потоке, чтобы не блокировать бота
        bot_response = await asyncio.to_thread(generate_response_sync, contents)
        await update.message.reply_text(bot_response)
    except Exception as e:
        print(f"Ошибка при обработке запроса: {e}")
        await update.message.reply_text("Господин разрешил отдыхать, попробуйте позже.")

# ---------------------------------------------------------------------------
# 6. Точка входа
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Запускаем Flask в отдельном фоновом потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Токен Telegram-бота
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

    app_bot = ApplicationBuilder().token(telegram_token).build()

    # Хэндлеры
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("Бот 'Братуся AI' запущен!")
    app_bot.run_polling()
