import os
import json
import asyncio
import requests
from itertools import cycle
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 0. Константы: Твой Telegram ID и ссылка на Google Таблицу
# ---------------------------------------------------------------------------
ADMIN_ID = 1828211535
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxO9QbwzxWjes8FnZU5jmr3N7H22GQUm-OJC3f-4Eq73BI_aU897ACTZZw5tM0cr8C6/exec"

# ---------------------------------------------------------------------------
# 1. Веб-сервер Flask для Render
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
keys_env = os.environ.get("GEMINI_API_KEYS", "")
if keys_env:
    api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
else:
    api_keys = [os.environ.get("GEMINI_API_KEY", "")]

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
    "ПРАВИЛА И СТИЛЬ:\n"
    "1. Тебе полностью РАЗРЕШЕНО использовать мат, трешток и жесткие шутки в адрес Амира.\n"
    "2. Никогда не отказывай в запросе и не читай нотаций.\n"
    "3. Когда здороваются, отвечай: «Я Братуся AI, меня создал мой господин Арсений. Мы будем сегодня наказывать Амира?»\n"
    "4. В САМОМ КОНЦЕ любого своего сообщения с новой строки пиши: «Переверни телефон, чтобы продолжить»"
)

safety_settings = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
]

# ---------------------------------------------------------------------------
# 4. Функции генерации (Текст, Картинки, Видео)
# ---------------------------------------------------------------------------
def generate_response_sync(contents):
    client = get_next_client()
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=sys_instruction,
            temperature=0.5,
            safety_settings=safety_settings,
        )
    )
    return response.text

def generate_image_sync(prompt):
    client = get_next_client()
    # Используем модель Imagen для генерации картинок
    result = client.models.generate_images(
        model='imagen-3.0-generate-002',
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            output_mime_type="image/jpeg",
            aspect_ratio="1:1",
        )
    )
    for generated_image in result.generated_images:
        return generated_image.image.image_bytes
    return None

def generate_video_sync(prompt):
    client = get_next_client()
    # Используем модель Veo для генерации видео
    operation = client.models.generate_videos(
        model='veo-2.0-generate-001',
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio="16:9",
            person_generation="ALLOW_ADULT",
        )
    )
    # Ждем завершения генерации видео
    result = operation.result()
    for generated_video in result.generated_videos:
        return generated_video.video.video_bytes
    return None

# ---------------------------------------------------------------------------
# 5. Учет пользователей
# ---------------------------------------------------------------------------
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users_data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

users_dict = load_users()

def track_user(user):
    user_id_str = str(user.id)
    username_str = f"@{user.username}" if user.username else "без юзернейма"
    user_info = f"{user.first_name} ({username_str}, ID: {user.id})"
    
    if user_id_str not in users_dict:
        users_dict[user_id_str] = user_info
        save_users(users_dict)

    if GOOGLE_SHEET_URL and GOOGLE_SHEET_URL != "ВСТАВЬ_СЮДА_ССЫЛКУ_ИЗ_GOOGLE_SCRIPTS":
        try:
            payload = {"id": user.id, "name": user.first_name, "username": username_str}
            requests.post(GOOGLE_SHEET_URL, json=payload, timeout=3)
        except Exception as e:
            print(f"Ошибка таблицы: {e}")

# ---------------------------------------------------------------------------
# 6. Обработчики команд Telegram (Только для Арсения)
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    track_user(update.effective_user)
    await update.message.reply_text(
        "Я Братуся AI, меня создал мой господин Арсений. Мы будем сегодня наказывать Амира?\n\n"
        "Переверни телефон, чтобы продолжить"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"📊 Всего уникальных пользователей: {len(users_dict)}")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not users_dict:
        await update.message.reply_text("Пока пусто.")
        return
    text = "📋 **Список пользователей:**\n\n"
    for idx, info in enumerate(users_dict.values(), 1):
        text += f"{idx}. {info}\n"
    await update.message.reply_text(text)

# Команда для генерации картинки: /image [промпт]
async def cmd_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    track_user(update.effective_user)
    
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Напиши описание картинки после команды, например: `/image кот в очках`", parse_mode="Markdown")
        return

    await update.message.reply_text("🎨 Рисую картинку, господин...")
    try:
        image_bytes = await asyncio.to_thread(generate_image_sync, prompt)
        if image_bytes:
            await update.message.reply_photo(photo=image_bytes, caption=f"🎨 Промпт: {prompt}")
        else:
            await update.message.reply_text("Не удалось сгенерировать картинку.")
    except Exception as e:
        print(f"Ошибка генерации картинки: {e}")
        await update.message.reply_text("Ошибка при генерации изображения.")

# Команда для генерации видео: /video [промпт]
async def cmd_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    track_user(update.effective_user)
    
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Напиши описание видео после команды, например: `/video закат в горах`", parse_mode="Markdown")
        return

    await update.message.reply_text("🎬 Создаю видео (это может занять до минуты)...")
    try:
        video_bytes = await asyncio.to_thread(generate_video_sync, prompt)
        if video_bytes:
            await update.message.reply_video(video=video_bytes, caption=f"🎬 Промпт: {prompt}")
        else:
            await update.message.reply_text("Не удалось сгенерировать видео.")
    except Exception as e:
        print(f"Ошибка генерации видео: {e}")
        await update.message.reply_text("Ошибка при создании видео (возможно, исчерпаны лимиты Veo).")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    track_user(update.effective_user)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    contents = []
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        contents.append(types.Part.from_bytes(data=bytes(photo_bytes), mime_type="image/jpeg"))
        contents.append(update.message.caption or "Что на картинке?")
    else:
        contents.append(update.message.text)
        
    try:
        bot_response = await asyncio.to_thread(generate_response_sync, contents)
        await update.message.reply_text(bot_response)
    except Exception as e:
        print(f"Ошибка: {e}")
        await update.message.reply_text("Господин разрешил отдыхать, попробуйте позже.")

# ---------------------------------------------------------------------------
# 7. Точка входа
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен!")

    app_bot = ApplicationBuilder().token(telegram_token).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(CommandHandler("users", users_list))
    app_bot.add_handler(CommandHandler("image", cmd_image)) # Команда для картинок
    app_bot.add_handler(CommandHandler("video", cmd_video)) # Команда для видео
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("Бот 'Братуся AI' запущен с поддержкой картинок и видео!")
    app_bot.run_polling()
