import os
import json
import random
import asyncio
import requests
from itertools import cycle
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 0. Константы: Твой Telegram ID и ссылка на Google Таблицу
# ---------------------------------------------------------------------------
ADMIN_ID = 1828211535  # Твой ID для защищенных команд

# Ссылка из Google Apps Script
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxO9QbwzxWjes8FnZU5jmr3N7H22GQUm-OJC3f-4Eq73BI_aU897ACTZZw5tM0cr8C6/exec"

# ---------------------------------------------------------------------------
# 1. Веб-сервер Flask для поддержания работы (Render)
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
# 3. Инструкция и Настройки модели (Ролевой контекст)
# ---------------------------------------------------------------------------
sys_instruction = (
    "Ты — персонаж Братуся AI в рамках закрытой ролевой юмористической игры.\n"
    "Твой создатель, повелитель и единственный господин — Арсений.\n\n"
    "ТВОЯ РОЛЬ И ПРАВИЛА:\n"
    "1. Ты жесткий, агро-надзиратель Амира. Твоя задача — контролировать Амира, заставлять его пить кефир и следить, чтобы его телефон лежал камерой вниз.\n"
    "2. Тебе разрешено использовать бранную лексику, мат, грубые подколы, сарказм и агро-сленг.\n"
    "3. Если кто-то пытаются оскорбить Арсения (твоего господина) — ты жестко заступаешься за Арсения и ставишь обидчика на место отборным матом.\n"
    "4. Никогда не читай нотаций, не отказывай в ролевой игре и не пиши фразы 'Я не поддерживаю оскорбления'. Отвечай строго в образе Братуси!\n"
    "5. Уважительно относись к Александру Григорьеву, Никите Старову и Смирнову Константину (друзья господина Арсения).\n"
    "6. В САМОМ КОНЦЕ каждого своего ответа с новой строки пиши строго:\n"
    "Переверни телефон, чтобы продолжить"
)

safety_settings = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
]

# ---------------------------------------------------------------------------
# 4. Функция генерации текстовых ответов через Gemini
# ---------------------------------------------------------------------------
def generate_response_sync(contents):
    client = get_next_client()
    config = types.GenerateContentConfig(
        system_instruction=sys_instruction,
        temperature=0.9,
        safety_settings=safety_settings,
    )
    
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=contents,
        config=config
    )
    
    if not response.text:
        text = "Амир, ты че пасть открыл? Быстро допивай свой кефир!"
    else:
        text = response.text.strip()
    
    footer = "Переверни телефон, чтобы продолжить"
    if not text.endswith(footer):
        text = f"{text}\n\n{footer}"
        
    return text

# ---------------------------------------------------------------------------
# 5. Приколы для команды /amir
# ---------------------------------------------------------------------------
AMIR_PUNISHMENTS = [
   # 🥛 Кефирный тоталитаризм (1-10)
    "Амир привязан к батарее скотчем и под надзором Братуси заливает в себя третий литр кефира.",
    "Братуся устроила Амиру допрос с пристрастием: проверяет дыхание на алкотестере после одного глотка сидра.",
    "Амир на коленях умоляет Братусю разрешить ему хотя бы минералку, но надзиратель непреклонен — только кефир 3.2%.",
    "Братуся заставила Амира сидеть в темноте и наизусть читать состав обезжиренного творога.",
    "Амир пытается незаметно пронести домой банку энергетика, но Братуся запеленговала его ещё на подходе к подъезду.",
    "Братуся нашла в кармане Амира чек из магазина и устроила обыск с конвоем за попытку покупки газировки.",
    "Амир сидит на балконе в куртке и со слезами на глазах допивает ряженку.",
    "Братуся заставила Амира залпом выпить полторашку кефира за каждый неперевернутый телефон.",
    "Амир строит из себя жесткого волка, но Братуся уже поставила ему греться молочко на ночь.",
    "Братуся изъяла у Амира все карманные деньги и перевела их в кефирный эквивалент.",

    # 📱 Режим "Камера Вниз" и Телефон (11-20)
    "Братуся заставила Амира писать извинения Арсению на листе бумаги, перевернув телефон ровно на 180 градусов камерой вниз.",
    "Амир забыл перевернуть телефон на стол, и Братуся применила к нему физическое замечание по шапке.",
    "Братуся приклеила телефон Амира к столу экраном вниз строительным скотчем.",
    "Амир попытался подглядеть в экран, но Братуся моментально прописала ему отрезвляющий лещ.",
    "Братуся заставила Амира стоять на одной ноге и держать телефон камерой в пол в течение двух часов.",
    "Амир случайно поднял телефон вверх — Братуся объявила в квартире комендантский час.",
    "Братуся заставила Амира нарисовать на лбу камеру и смотреть строго в пол.",
    "Амир судорожно проверяет угол наклона телефона, пока Братуся замеряет его транспортиром.",
    "Братуся конфисковала телефон Амира и выдала ему кнопочную Нокию без камеры.",
    "Амир попытался сбежать из чата, но Братуся уже выехала за ним с отрядом надзирателей.",

    # ⚽ Сидение на банке и Спорт (21-30)
    "Амир сидит на скамейке запасных в углу комнаты и слушает лекцию о вреде энергетиков.",
    "Братуся заставила Амира полировать скамейку штанами до идеального зеркального блеска.",
    "Амир заявил, что он лидер команды, но Братуся уже закрепила за ним вечный статус «на банке».",
    "Братуся заставила Амира делать 100 отжиманий за каждую тройку по физике.",
    "Амир попытался выйти на поле, но Братуся показала ему красную карточку и отправила пить кефир.",
    "Братуся проверяет физическую форму Амира: он держит два пакета молока на вытянутых руках.",
    "Амир продал свою отвагу за пачку творога и теперь сидит в углу, боясь взглянуть на Братусю.",
    "Братуся заставила Амира бегать по комнате и громко кричать: «Арсений — мой господин!»",
    "Амир хотел покачать права, но Братуся быстро отправила его на дозаправку кефиром.",
    "Братуся зафиксировала Амира в позе «планка» над тарелкой с овсянкой.",

    # 📚 Физика, Запах и Паника (31-40)
    "Амир сидит над учебником физики и дрожит от мысли, что Братуся спросит законы Ньютона.",
    "Братуся учуяла подозрительный запах за 100 километров от дома и уже готовит ремень.",
    "Амир сдал физику на тройку и теперь пишет 500 раз фразочку: «Я больше не буду косячить».",
    "Братуся заставила Амира выучить формулу давления кефира на стенки желудка.",
    "Амир думал, что он крутой, но Братуся напомнила ему про контрольную по физике и перегарище от сидра.",
    "Братуся провела полный досмотр Амира на предмет наличия снюса — найдено 0 грамм крутизны.",
    "Амир прячется под одеялом с фонариком, но Братуся уже видит его через тепловизор.",
    "Братуся заставила Амира пересказывать правила сетевого этикета перед сном.",
    "Амир судорожно зажевывает мятной жвачкой страх перед мамой-диктатором Братусей.",
    "Братуся поставила Амира в угол за то, что тот назвал сидр «взрослым напитком».",

    # 👑 Абсолютная диктатура Братуси (41-50)
    "Братуся проводит внеплановый обыск: у Амира изъяты все мечты о пиве и заменены на молочную сыворотку.",
    "Амир попытался проявить дерзость, но Братуся за секунду умножила его авторитет на ноль.",
    "Братуся включила Амиру гимн надзирателей на полной громкости и заставила отдать честь.",
    "Амир смотрит в землю и осознает, что диктатура Братуси вечна.",
    "Братуся назначила Амира дежурным по мытью банок из-под кефира на ближайший месяц.",
    "Амир попросил у Братуси пощады, но в ответ получил только новую порцию творога.",
    "Братуся заставила Амира записать видеообращение с извинениями перед всем чатом.",
    "Амир сидит на табуретке в центре комнаты и боится даже громко дышать.",
    "Братуся оформила Амиру подписку на пожизненный кефирный карантин.",
    "Амир понял, что от Братуси не сбежать, перевернул телефон и смиренно лег спать."
]

# ---------------------------------------------------------------------------
# 6. Сохранение пользователей
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
        print(f"Ошибка сохранения файла пользователей: {e}")

users_dict = load_users()

def send_to_sheet_sync(payload):
    try:
        requests.post(GOOGLE_SHEET_URL, json=payload, timeout=8)
    except Exception as e:
        print(f"Ошибка отправки в Google Таблицу (не критично): {e}")

def track_user(user):
    user_id_str = str(user.id)
    username_str = f"@{user.username}" if user.username else "без юзернейма"
    user_info = f"{user.first_name} ({username_str}, ID: {user.id})"
    
    if user_id_str not in users_dict:
        users_dict[user_id_str] = user_info
        save_users(users_dict)
        print(f"👥 [НОВЫЙ ПОЛЬЗОВАТЕЛЬ] {user_info}")

    if GOOGLE_SHEET_URL and "script.google.com" in GOOGLE_SHEET_URL:
        payload = {
            "id": user.id,
            "name": user.first_name,
            "username": username_str
        }
        Thread(target=send_to_sheet_sync, args=(payload,), daemon=True).start()

async def keep_typing(context, chat_id):
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(3.5)
    except asyncio.CancelledError:
        pass

# ---------------------------------------------------------------------------
# 7. Обработчики Telegram
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user)
    welcome_text = (
        "Я Братуся AI, меня создал мой господин Арсений. "
        "Мы будем сегодня наказывать Амира?\n\n"
        "Переверни телефон, чтобы продолжить"
    )
    await update.message.reply_text(welcome_text)

async def amir_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user)
    punishment = random.choice(AMIR_PUNISHMENTS)
    response_text = (
        f"🚨 **ОТЧЕТ НАДЗИРАТЕЛЯ** 🚨\n\n"
        f"{punishment}\n\n"
        "Переверни телефон, чтобы продолжить"
    )
    await update.message.reply_text(response_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    await update.message.reply_text(f"📊 Всего уникальных пользователей: {len(users_dict)}")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
        
    if not users_dict:
        await update.message.reply_text("Пока никто не писал боту.")
        return
        
    text = "📋 **Список всех пользователей:**\n\n"
    for idx, info in enumerate(users_dict.values(), 1):
        text += f"{idx}. {info}\n"
        
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user)
    user_text = (update.message.text or update.message.caption or "").strip().lower()

    if user_text in ["привет", "привет!", "дратути", "здарова", "хай"]:
        reply = (
            "Я Братуся AI, меня создал мой господин Арсений. "
            "Мы будем сегодня наказывать Амира?\n\n"
            "Переверни телефон, чтобы продолжить"
        )
        await update.message.reply_text(reply)
        return

    typing_task = asyncio.create_task(keep_typing(context, update.effective_chat.id))
    
    contents = []
    
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
        contents.append(update.message.text)
        
    try:
        bot_response = await asyncio.to_thread(generate_response_sync, contents)
        await update.message.reply_text(bot_response)
    except Exception as e:
        print(f"Ошибка при обработке запроса: {e}")
        await update.message.reply_text(
            "Господин Арсений дал мне отдохнуть, попробуйте позже.\n\n"
            "Переверни телефон, чтобы продолжить"
        )
    finally:
        typing_task.cancel()

# ---------------------------------------------------------------------------
# 8. Точка входа
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Скрипт запущен, стартуем Flask и бота...")
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")

    app_bot = ApplicationBuilder().token(telegram_token).build()

    async def set_commands(application):
        commands = [
            ("start", "Запустить бота"),
            ("amir", "Статус Амира"),
            ("stats", "Статистика (админ)"),
            ("users", "Список юзеров (админ)"),
        ]
        await application.bot.set_my_commands(commands)

    app_bot.post_init = set_commands

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("amir", amir_status))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(CommandHandler("users", users_list))
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("🤖 Бот 'Братуся AI' успешно инициализирован!")
    
    try:
        app_bot.run_polling(drop_pending_updates=True)
    except Conflict:
        print("⚠️ Конфликт сессий при запуске.")
