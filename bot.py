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
# 0.1. Справочник ролей по Telegram Username (без знака @, в нижнем регистре)
# ---------------------------------------------------------------------------
KNOWN_USERS = {
    # Твой ник (Господин) — замени на свой точный юзернейм при необходимости
    "p0tat0777": {"name": "Арсений", "role": "master", "tag": "господин и создатель"},
    
    # Твои друзья (к ним абсолютное уважение)
    "shootallnet": {"name": "Саня Григорьев", "role": "friend", "tag": "друг господина"},
    "neverm9nd": {"name": "Никита Старов", "role": "friend", "tag": "друг господина"},
    "k0styan4k": {"name": "Константин Смирнов", "role": "friend", "tag": "друг господина"},
    "verozox": {"name": "Твинк господина Арсения", "role": "friend", "tag": "твинк господина"},
    
    # Амир (главная цель для жесткого прессинга)
    "Oguzokjr": {"name": "Амир", "role": "amir", "tag": "клиент скамейки запасных"}
}

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
    "2. Тебе разрешено использовать бранную лексику, мат, грубые подколы, сарказм и агро-сленг (но только для Амира или по ситуации).\n"
    "3. Если кто-то пытается оскорбить Арсения (твоего господина) — ты жестко заступаешься за Арсения и ставишь обидчика на место отборным матом.\n"
    "4. Никогда не читай нотаций, не отказывай в ролевой игре и не пиши фразы 'Я не поддерживаю оскорбления'.\n"
    "5. Уважительно и с почтением относись к друзьям господина: Александру Григорьеву, Никите Старову и Константину Смирнову.\n"
    "6. С любыми другими пользователями (незнакомцами) общайся вежливо, нейтрально и отстраненно, без мата, наездов и кефирных ультиматумов.\n"
    "7. В САМОМ КОНЦЕ каждого своего ответа с новой строки пиши строго:\n"
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
def generate_response_sync(contents, extra_instruction=""):
    client = get_next_client()
    
    # Динамически добавляем контекст о том, кто сейчас пишет
    current_system_instruction = sys_instruction
    if extra_instruction:
        current_system_instruction += f"\n\nТЕКУЩИЙ КОНТЕКСТ СОБЕСЕДНИКА:\n{extra_instruction}"

    config = types.GenerateContentConfig(
        system_instruction=current_system_instruction,
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
# 5. Приколы для команды /amir (100 уникальных ситуаций)
# ---------------------------------------------------------------------------
AMIR_PUNISHMENTS = [
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
    "Братуся проводит внеплановый обыск: у Амира изъяты все мечты о пиве и заменены на молочную сыворотку.",
    "Амир попытался проявить дерзость, но Братуся за секунду умножила его авторитет на ноль.",
    "Братуся включила Амиру гимн надзирателей на полной громкости и заставила отдать честь.",
    "Амир смотрит в землю и осознает, что диктатура Братуси вечна.",
    "Братуся назначила Амира дежурным по мытью банок из-под кефира на ближайший месяц.",
    "Амир попросил у Братуси пощады, но в ответ получил только новую порцию творога.",
    "Братуся заставила Амира записать видеообращение с извинениями перед всем чатом.",
    "Амир сидит на табуретке в центре комнаты и боится даже громко дышать.",
    "Братуся оформила Амиру подписку на пожизненный кефирный карантин.",
    "Амир понял, что от Братуси не сбежать, перевернул телефон и смиренно лег спать.",
    "Братуся заставила Амира с закрытыми глазами отличать кефир 2.5% от 3.2% по вкусу.",
    "Амир попытался незаметно разбавить кефир водой, но Братуся сразу заставила его выпить двойную порцию.",
    "Братуся настроила кухонные весы так, чтобы они показывали массу Амира исключительно в пакетах творога.",
    "Амир сидит на кухне и под присмотром Братусы учит таблицу умножения на количество калорий в кефире.",
    "Братуся конфисковала у Амира всю сладкую газировку и заставила перелить её в раковину лично.",
    "Амир попытался съесть чипсы под столом, но хруст услышала Братуся и отправила его на дозаправку ацидофилином.",
    "Братуся поставила Амиру ультразвуковой датчик на холодильник — доступ только по согласованию с Арсением.",
    "Амир умоляет о чашечке чая с сахаром, но Братуся наливает ему только тёплую сыворотку.",
    "Братуся заставила Амира вести дневник учета выпитого кефира с личной подписью и печатью.",
    "Амир попытался подкупить Братусю шоколадкой, но был моментально отправлен на 50 приседаний.",
    "Братуся замерила угол наклона телефона Амира транспортиром — отклонение на 2 градуса карается кефирным штрафом.",
    "Амир попытался включить фронтальную камеру, но Братуся заклеила её изолентой намертво.",
    "Братуся заставила Амира поставить на обои телефона фотографию надзирателя в полный рост.",
    "Амир случайно выронил телефон из рук — Братуся расценила это как попытку диверсии и отправила его в угол.",
    "Братуся проверила уведомления Амира: все чаты переведены в режим «строгий контроль Братуси».",
    "Амир попытался удалить телеграм, но Братуся лично переустановила его и заблокировала кнопку «выйти».",
    "Братуся заставила Амира повторять фразочку «Камера смотрит в стол» перед каждым входом в сеть.",
    "Амир хотел отправить кружочек в чат, но Братуся вовремя конфисковала смартфон за нарушение маскировки.",
    "Братуся наклеила на чехол Амира надпись: «Имущество под надзором господина Арсения».",
    "Амир судорожно кладет телефон на стол экраном вниз при каждом шорохе в коридоре.",
    "Братуся заставила Амира выучить имена всех запасных игроков в мире, чтобы он глубже проникся ролью.",
    "Амир сидит на табуретке в позе «задумчивого кефиропийцы» и размышляет о своем поведении.",
    "Братуся нарисовала мелом круг на полу и запретила Амиру выходить из него до окончания допроса.",
    "Амир попытался встать со скамейки без разрешения, но Братуся вернула его на место одним строгим взглядом.",
    "Братуся заставила Амира протирать скамейку запасных влажной салфеткой каждые 15 минут.",
    "Амир с тоской смотрит в окно, пока Братуся выстраивает график его домашних дежурств.",
    "Братуся назначила Амира ответственным за чистку картофеля для всего штаба Арсения.",
    "Амир хотел пойти погулять, но Братуся напомнила ему, что его норма на сегодня — сидеть тихо.",
    "Братуся заставила Амира стоять в планке и вслух перечислять правила господина Арсения.",
    "Амир попытался подтянуться на турнике, но Братуся забраковала его технику и отправила пить молоко.",
    "Братуся устроила Амиру внезапную контрольную по физике прямо посреди ночи.",
    "Амир перепутал закон Ома с законом Паскаля и был приговорен к часовому чтению учебника вслух.",
    "Братуся заставила Амира рассчитывать силу трения его штанов о скамейку запасных.",
    "Амир попытался списать физику с ГДЗ, но Братуся заблокировала доступ к сайту на уровне роутера.",
    "Братуся проверяет у Амира знания формулы ускорения свободного падения кефирного пакета.",
    "Амир судорожно листает параграф 23, пока Братуся засекает время секундомером.",
    "Братуся заставила Амира нарисовать вектор силы, с которой надзиратель давит на его дисциплину.",
    "Амир получил четверку по контрольной, но Братуся сказала, что господин Арсений ждет только идеала.",
    "Братуся заставила Амира выучить все терми термины по сетевому этикету наизусть.",
    "Амир попытался доказать, что физика ему не пригодится, за что сразу получил лекцию о плотности кефира.",
    "Братуся проводит технический осмотр Амира: пульс в норме, уровень страха перед Арсением — максимальный.",
    "Амир попытался сделать вид, что спит, но Братуся заставила его встать и отдать честь.",
    "Братуся переименовала контакты в телефоне Амира: теперь там только Арсений и Братуся.",
    "Амир попытался тихонько вздохнуть, но Братуся сделала ему замечание за лишний шум.",
    "Братуся заставила Амира сдать все наушники в сейф до тех пор, пока он не исправит дисциплину.",
    "Амир сидит на краю кровати и боится сделать лишнее движение под пристальным взором Братусы.",
    "Братуся выдала Амиру специальный бланки для ежедневных отчетов о выпитом кефире.",
    "Амир хотел пожаловаться пацанам в чате, но Братуся уже прочитала его черновик.",
    "Братуся заставила Амира выучить строгий устав надзирателя в трех томах.",
    "Амир смиренно принимает свою судьбу, берет стакан кефира и переворачивает телефон."
]

# ---------------------------------------------------------------------------
# 6. Учет пользователей и уровня кефирности
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
        headers = {"Content-Type": "application/json"}
        response = requests.post(GOOGLE_SHEET_URL, json=payload, headers=headers, timeout=10)
        print(f"📊 Ответ от Google Таблицы: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"⚠️ Ошибка отправки в Google Таблицу: {e}")

def track_user(user):
    user_id_str = str(user.id)
    username_str = f"@{user.username}" if user.username else "без юзернейма"
    
    if user_id_str not in users_dict:
        users_dict[user_id_str] = {
            "info": f"{user.first_name} ({username_str}, ID: {user.id})",
            "username": user.username.lower() if user.username else "",
            "first_name": user.first_name,
            "kefir": 0.0
        }
        save_users(users_dict)
        print(f"👥 [НОВЫЙ ПОЛЬЗОВАТЕЛЬ] {user.first_name} ({username_str}, ID: {user.id})")
    else:
        if isinstance(users_dict[user_id_str], str):
            old_info = users_dict[user_id_str]
            users_dict[user_id_str] = {
                "info": old_info,
                "username": user.username.lower() if user.username else "",
                "first_name": user.first_name,
                "kefir": 0.0
            }
            save_users(users_dict)

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
# 7. Обработчики Telegram (Команды)
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

async def kefir_meter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update.effective_user)
    user_id_str = str(update.effective_user.id)
    
    user_data = users_dict.get(user_id_str, {})
    current_kefir = user_data.get("kefir", 0.0) if isinstance(user_data, dict) else 0.0
    
    response_text = (
        f"📊 **АНАЛИЗ БРАТУСИ ДЛЯ {update.effective_user.first_name.upper()}**\n\n"
        f"🥛 Концентрация кефира в крови: **{current_kefir:.1f}%**\n"
        f"🔒 Статус надзора: {'Абсолютная кефиризация' if current_kefir >= 100 else 'Требуется дозаправка'}\n\n"
        "Переверни телефон, чтобы продолжить"
    )
    await update.message.reply_text(response_text)

async def add_kefir_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Пошел вон, у тебя нет прав господина Арсения.\n\nПереверни телефон, чтобы продолжить")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Использование: `/addkefir @username 10` или `/addkefir 123456789 -5`\n\n"
            "Переверни телефон, чтобы продолжить"
        )
        return

    target_input = context.args[0].strip().replace("@", "").lower()
    try:
        amount = float(context.args[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Укажи нормальное число процентов!")
        return

    target_id = None
    for uid, udata in users_dict.items():
        if isinstance(udata, dict):
            if uid == target_input or udata.get("username", "") == target_input:
                target_id = uid
                break

    if not target_id:
        await update.message.reply_text(f"Пользователь '{target_input}' не найден в базе бота.")
        return

    users_dict[target_id]["kefir"] = round(users_dict[target_id].get("kefir", 0.0) + amount, 1)
    if users_dict[target_id]["kefir"] < 0:
        users_dict[target_id]["kefir"] = 0.0
        
    save_users(users_dict)

    user_name = users_dict[target_id].get("first_name", "Юзер")
    new_val = users_dict[target_id]["kefir"]
    
    await update.message.reply_text(
        f"✅ Успешно! Для {user_name} изменено на {amount:+.1f}%.\n"
        f"Текущий уровень кефирности: **{new_val:.1f}%**\n\n"
        "Переверни телефон, чтобы продолжить"
    )

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
    for idx, (uid, udata) in enumerate(users_dict.items(), 1):
        if isinstance(udata, dict):
            info_str = udata.get("info", uid)
            kefir_val = udata.get("kefir", 0.0)
            text += f"{idx}. {info_str} — Кефирность: **{kefir_val:.1f}%**\n"
        else:
            text += f"{idx}. {udata}\n"
        
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    track_user(user)
    
    # 🥛 Начисление +0.1% за каждое сообщение
    user_id_str = str(user.id)
    if user_id_str in users_dict and isinstance(users_dict[user_id_str], dict):
        users_dict[user_id_str]["kefir"] = round(users_dict[user_id_str].get("kefir", 0.0) + 0.1, 1)
        save_users(users_dict)

    user_text = (update.message.text or update.message.caption or "").strip().lower()

    if user_text in ["привет", "привет!", "дратути", "здарова", "хай"]:
        reply = (
            "Я Братуся AI, меня создал мой господин Арсений. "
            "Мы будем сегодня наказывать Амира?\n\n"
            "Переверни телефон, чтобы продолжить"
        )
        await update.message.reply_text(reply)
        return

    # Определение роли пользователя по юзернейму
    username = user.username.lower() if user.username else ""
    person_info = KNOWN_USERS.get(username, {"name": user.first_name, "role": "stranger", "tag": "обычный прохожий"})
    role = person_info["role"]

    # Формируем динамическую инструкцию для ИИ на основе того, кто пишет
 # Формируем динамическую инструкцию для ИИ на основе того, кто пишет
    user_display_name = person_info["name"]
    
    extra_instruction = f"Собеседника зовут {user_display_name}. "
    if role == "master":
        extra_instruction += f"Это твой создатель, повелитель и единственный господин {user_display_name}. Обращайся к нему с абсолютным почтением и преданностью, называй его по имени или 'господин {user_display_name}'."
    elif role == "friend":
        extra_instruction += f"Это {user_display_name}, уважаемый друг твоего господина Арсения. Общайся с ним максимально вежливо, тепло и уважительно, обращайся к нему по имени {user_display_name}."
    elif role == "amir":
        extra_instruction += f"Это Амир. Прессуй его, обращайся к нему строго по имени Амир, заставляй его пить кефир, используй мат, сарказм и следи, чтобы его телефон лежал камерой вниз."
    else:
        extra_instruction += f"Это случайный незнакомец по имени {user_display_name}. Общайся с ним строго нейтрально, вежливо, отстраненно, обращайся к нему по имени {user_display_name}, без мата и без упоминания Амира."
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
        bot_response = await asyncio.to_thread(generate_response_sync, contents, extra_instruction)
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
            ("start", "Запустить бан"),
            ("amir", "Статус Амира"),
            ("meter", "Мой уровень кефира"),
            ("stats", "Статистика (админ)"),
            ("users", "Список юзеров (админ)"),
        ]
        await application.bot.set_my_commands(commands)

    app_bot.post_init = set_commands

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("amir", amir_status))
    app_bot.add_handler(CommandHandler("meter", kefir_meter))
    app_bot.add_handler(CommandHandler("addkefir", add_kefir_admin))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(CommandHandler("users", users_list))
    app_bot.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("🤖 Бот 'Братуся AI' успешно инициализирован!")
    
    try:
        app_bot.run_polling(drop_pending_updates=True)
    except Conflict:
        print("⚠️ Конфликт сессий при запуске.")
