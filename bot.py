import telebot
import sqlite3
import datetime
import json
import psutil
import platform
import time

TOKEN = ''
ADMIN_ID =

bot = telebot.TeleBot(TOKEN)

user_states = {}

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            register_at TEXT,
            key_text TEXT,
            key_expire_at TEXT,
            id_key TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def register_user(user):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, register_at, key_text, id_key)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user.id, user.username, user.first_name, user.last_name, now, None, None))
    conn.commit()
    conn.close()

######################################################################################################################################################

COMMAND_LIMIT = 3
TIME_LIMIT = 20

user_commands = {}

def is_rate_limited(user_id, command):
    now = time.time()
    if user_id not in user_commands:
        user_commands[user_id] = {}

    user_data = user_commands[user_id].get(command)

    if user_data:
        count, first_time = user_data
        if now - first_time <= TIME_LIMIT:
            if count >= COMMAND_LIMIT:
                wait_time = int(TIME_LIMIT - (now - first_time))
                return True, wait_time
            else:
                user_commands[user_id][command] = [count + 1, first_time]
                return False, 0
        else:
            user_commands[user_id][command] = [1, now]
            return False, 0
    else:
        user_commands[user_id][command] = [1, now]
        return False, 0

@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = message.from_user.id
    limited, wait_time = is_rate_limited(user_id, 'start')
    if limited:
        bot.send_message(message.chat.id, f"🧐Не так часто. Попробуйте через {wait_time} секунд")
        return

    user = message.from_user
    register_user(user)
    bot.send_message(message.chat.id, "👋Привет, это бот для быстрого взаимодействия с PixelVPN. \n"
                                      'Список всех доступных команд можешь увидеть во вкладке "Меню"')

@bot.message_handler(commands=['broadcast'])
def broadcast_start(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🐶Отказано в доступе. Куда мы лезем?")
        return
    user_states[message.from_user.id] = 'waiting_for_broadcast'
    bot.send_message(message.chat.id, "Отправь сообщение для рассылки (текст, изображение, документ)")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'waiting_for_broadcast',
                     content_types=['text', 'photo', 'document'])
def broadcast_send(message):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = c.fetchall()
    conn.close()

    for user in users:
        user_id = user[0]
        try:
            if message.photo:
                bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.document:
                bot.send_document(user_id, message.document.file_id, caption=message.caption)
            else:
                bot.send_message(user_id, message.text)
        except Exception:
            pass

    bot.send_message(message.chat.id, "Рассылка завершена")
    user_states.pop(message.from_user.id)

@bot.message_handler(commands=['key'])
def key_message(message):
    user_id = message.from_user.id
    limited, wait_time = is_rate_limited(user_id, 'key')
    if limited:
        bot.send_message(message.chat.id, f"🧐Не так часто. Попробуйте через {wait_time} секунд")
        return

    user_id = message.from_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT key_text, key_expire_at FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()

    if result and result[0]:
        key_text, key_expire_at = result
        expire_text = f"Дата окончания: {key_expire_at}" if key_expire_at else ""
        bot.send_message(message.chat.id, f"🔑Ваш ключ:\n{key_text}\n{expire_text}")
    else:
        bot.send_message(message.chat.id, "⁉️Ключ для вас ещё не добавлен. Обратитесь к администратору - @nikita_sevcity")

@bot.message_handler(commands=['addkey'])
def addkey_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return

    try:
        parts = message.text.split(' ', 2)
        user_id = int(parts[1])
        key_text = parts[2]
    except (IndexError, ValueError):
        bot.reply_to(message, "Используйте формат: /addkey user_id текст")
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT key_text FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()

    if result:
        current_text = result[0] or ""
        updated_text = (current_text + "\n" + key_text).strip() if current_text else key_text

        # Добавим дату окончания через месяц
        expire_date = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        c.execute('UPDATE users SET key_text = ?, key_expire_at = ? WHERE user_id = ?', (updated_text, expire_date, user_id))
        conn.commit()
        bot.reply_to(message, f"Ключ для пользователя {user_id} успешно добавлен.\nДата окончания: {expire_date}")
    else:
        bot.reply_to(message, f"Пользователь с ID {user_id} не найден")

    conn.close()

@bot.message_handler(commands=['changekey'])
def changekey_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return

    try:
        parts = message.text.split(' ', 2)
        user_id = int(parts[1])
        new_text = parts[2]
    except IndexError:
        bot.reply_to(message, "Используйте формат: /changekey user_id новый_текст\nДля удаления текста используйте: /changekey user_id none")
        return

    if new_text.lower() == 'none':
        new_text = None

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET key_text = ?, key_expire_at = NULL WHERE user_id = ?', (new_text, user_id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"Ключ для пользователя {user_id} обновлён")

@bot.message_handler(commands=['idkey'])
def idkey_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return
    try:
        parts = message.text.split(' ', 2)
        user_id = int(parts[1])
        id_key = parts[2]
    except (IndexError, ValueError):
        bot.reply_to(message, "Используйте формат: /idkey user_id ключ")
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT id_key FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result is not None:
        c.execute('UPDATE users SET id_key = ? WHERE user_id = ?', (id_key, user_id))
        conn.commit()
        bot.reply_to(message, f"ID-ключ для пользователя {user_id} установлен")
    else:
        bot.reply_to(message, f"Пользователь с ID {user_id} не найден")
    conn.close()

@bot.message_handler(commands=['changeidkey'])
def changeidkey_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return
    try:
        parts = message.text.split(' ', 2)
        user_id = int(parts[1])
        new_id_key = parts[2]
    except (IndexError, ValueError):
        bot.reply_to(message, "Используйте формат: /changeidkey user_id новый_ключ")
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT id_key FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result is not None:
        c.execute('UPDATE users SET id_key = ? WHERE user_id = ?', (new_id_key, user_id))
        conn.commit()
        bot.reply_to(message, f"ID-ключ для пользователя {user_id} изменён")
    else:
        bot.reply_to(message, f"Пользователь с ID {user_id} не найден")
    conn.close()

@bot.message_handler(commands=['idkeys'])
def idkeys_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, last_name, id_key FROM users WHERE id_key IS NOT NULL AND id_key != ""')
    users = c.fetchall()
    conn.close()

    if not users:
        bot.reply_to(message, "Нет пользователей с добавленными ID-ключами")
        return

    text = "Пользователи с ID-ключами:\n"
    for i, user in enumerate(users, 1):
        user_id, username, first_name, last_name, id_key = user
        username = f"@{username}" if username else "(нет username)"
        name = f"{first_name or ''} {last_name or ''}".strip() or "(не указано)"
        text += f"{i}. {user_id} - {username} ({name})\n   ID-ключ: {id_key}\n"

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['myprofile'])
def myprofile_message(message):
    user_id = message.from_user.id
    limited, wait_time = is_rate_limited(user_id, 'myprofile')
    if limited:
        bot.send_message(message.chat.id, f"🧐Не так часто. Попробуйте через {wait_time} секунд")
        return

    user_id = message.from_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, last_name, register_at FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()

    if not result:
        bot.reply_to(message, "Вы ещё не зарегистрированы. Нажмите 👉 /start для регистрации")
        return

    user_id, username, first_name, last_name, register_at = result
    username = f"@{username}" if username else "(нет username)"
    name = f"{first_name or ''} {last_name or ''}".strip() or "(не указано)"
    register_at = register_at or "(неизвестно)"

    text = (f"👤Ваш профиль:\n"
            f"🆔ID: {user_id}\n"
            f"👀Username: {username}\n"
            f"🫠Имя: {name}\n"
            f"🗓Зарегистрирован: {register_at}")

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['traffickey'])
def traffic_key(message):
    user_id = message.from_user.id
    limited, wait_time = is_rate_limited(user_id, 'traffickey')
    if limited:
        bot.send_message(message.chat.id, f"🧐Не так часто. Попробуйте через {wait_time} секунд")
        return
    try:
        user_id = message.from_user.id

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id_key FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        conn.close()

        if not result:
            bot.send_message(message.chat.id, "У вас нет сохранённого id_key. Попросите админа выдать его 🗣")
            return

        id_key = result[0]

        with open('/var/lib/docker/overlay2/83568fb367d9eeced01ded09ef13c13c91dde24fe4e6ae15e7127056e67d0a5d/diff/opt/amnezia/awg/clientsTable', 'r') as f:
            data = json.load(f)

        client_data = None
        for client in data:
            if client['clientId'] == id_key:
                client_data = client
                break

        if client_data:
            user_info = client_data.get('userData', {})
            received = user_info.get('dataReceived', '0 MiB')
            sent = user_info.get('dataSent', '0 MiB')
            handshake = user_info.get('latestHandshake', 'Нет данных')

            response = f"Данные по ключу:\n" \
                       f"Получено: {received}\n" \
                       f"Отправлено: {sent}\n" \
                       f"Последнее соединение: {handshake}"
            bot.send_message(message.chat.id, response)
        else:
            bot.send_message(message.chat.id, "😐Ваш ключ не найден в базе")
    except Exception:
        bot.send_message(message.chat.id, f"😐Произошла ошибка")

@bot.message_handler(commands=['userkeys'])
def userkeys_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, last_name FROM users WHERE key_text IS NOT NULL AND key_text != ""')
    users = c.fetchall()
    conn.close()

    if not users:
        bot.reply_to(message, "Нет пользователей с добавленными ключами")
        return

    text = "Пользователи с добавленными ключами:\n"
    for i, user in enumerate(users, 1):
        user_id, username, first_name, last_name = user
        username = f"@{username}" if username else "(нет username)"
        name = f"{first_name or ''} {last_name or ''}".strip() or "(не указано)"
        text += f"{i}. {user_id} - {username} ({name})\n"

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['users'])
def users_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "🐶Отказано в доступе. Куда мы лезем?")
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, last_name, register_at FROM users')
    users = c.fetchall()
    conn.close()

    if not users:
        bot.reply_to(message, "Пользователей пока нет")
        return

    text = "Зарегистрированные пользователи:\n"
    for i, user in enumerate(users, 1):
        user_id, username, first_name, last_name, register_at = user
        username = f"@{username}" if username else "(нет username)"
        name = f"{first_name or ''} {last_name or ''}".strip()
        text += f"{i}. {user_id} - {username} ({name})\n   Зарегистрирован: {register_at}\n"

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['info'])
def info_message(message):
    user_id = message.from_user.id
    limited, wait_time = is_rate_limited(user_id, 'info')
    if limited:
        bot.send_message(message.chat.id, f"🧐Не так часто. Попробуйте через {wait_time} секунд")
        return

    bot.send_message(
        message.chat.id,
        'Локация PixelVPN - Финляндия 🇫🇮\n'
        'Чтобы использовать PixelVPN нужно:\n'
        '1. Написать - @nikita_sevcity, для оплаты (75₽/мес.) и получения доступа\n'
        '2. Установить бесплатное приложение AmneziaVPN:\n'
        '🍏iOS - <a href="https://apps.apple.com/ru/app/amnezia-vpn/id1533001837">Скачать из App Store</a>\n'
        '📱Android - <a href="https://play.google.com/store/apps/details?id=com.amnezia.amnezia">Скачать из Google Play</a>\n'
        '🪟Windows - <a href="https://github.com/amnezia-vpn/amnezia-client/releases/download/4.8.5.0/AmneziaVPN_4.8.5.0_x64.exe">Скачать из GitHub</a>\n'
        '💻MacOS - <a href="https://github.com/amnezia-vpn/amnezia-client/releases/download/4.8.5.0/AmneziaVPN_4.8.5.0_macos.dmg">Скачать из GitHub</a>\n'
        '🐧Linux - <a href="https://github.com/amnezia-vpn/amnezia-client/releases/download/4.8.5.0/AmneziaVPN_4.8.5.0_linux.tar.zip">Скачать из GitHub</a>\n'
        '<a href="https://github.com/amnezia-vpn/amnezia-client/releases/download/4.8.5.0/AmneziaVPN_4.8.5.0_linux.tar.zip">Подробная инструкция по установке на Linux</a>\n'
        '3. Скопировать ключ, отправленный командой /key\n'
        '4. Запустить приложение и нажать кнопку "Приступим", в появившемся окне вставляем ключ в поле "Вставьте ключ"\n'
        '5. Нажать кнопку "Подключиться"\n',
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@bot.message_handler(commands=['help'])
def help_message(message):
    user_id = message.from_user.id
    limited, wait_time = is_rate_limited(user_id, 'info')
    if limited:
        bot.send_message(message.chat.id, f"🧐Не так часто. Попробуйте через {wait_time} секунд")
        return

    bot.send_message(message.chat.id, '🆘Отправь - /start или напиши в тех. поддержку - @nikita_sevcity')

@bot.message_handler(commands=['path'])
def path_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🐶Отказано в доступе. Куда мы лезем?")
        return

    bot.send_message(message.chat.id, "/var/lib/docker/overlay2/83568fb367d9eeced01ded09ef13c13c91dde24fe4e6ae15e7127056e67d0a5d/diff/opt/amnezia/awg")

@bot.message_handler(commands=['c'])
def c_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🐶Отказано в доступе. Куда мы лезем?")
        return

    bot.send_message(message.chat.id, "Команды админа:"
                                      "/users\n"
                                      "/path\n"
                                      "/status\n"
                                      "/broadcast\n"
                                      "/addkey\n"
                                      "/changekey\n"
                                      "/userkeys\n"
                                      "/idkey\n"
                                      "/changeidkey\n"
                                      "/idkeys\n")

@bot.message_handler(commands=['status'])
def htop_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🐶Отказано в доступе. Куда мы лезем?")
        return
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        virtual_memory = psutil.virtual_memory()
        disk_usage = psutil.disk_usage('/')
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time

        text = f"""
<b>Состояние сервера</b>:
<b>OS:</b> {platform.system()} {platform.release()}
<b>Процессор:</b> {cpu_percent}% загруженности
<b>RAM:</b> {virtual_memory.used // (1024**2)}MB / {virtual_memory.total // (1024**2)}MB ({virtual_memory.percent}%)
<b>Диск /:</b> {disk_usage.used // (1024**3)}GB / {disk_usage.total // (1024**3)}GB ({disk_usage.percent}%)
<b>Uptime:</b> {str(uptime).split('.')[0]}
"""
        bot.send_message(message.chat.id, text, parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: True)
def unknown_command(message):
    known_commands = ['start', 'key', 'addkey', 'changekey', 'myprofile', 'userkeys', 'users', 'info', 'help', 'path', 'broadcast', 'idkey', 'changeidkey', 'idkeys', 'status', 'c', 'traffickey']

    command = message.text.split()[0][1:]

    if command not in known_commands:
        bot.reply_to(message, "🙂‍↔️Такой команды не существует. Пожалуйста, проверьте правильность команды")

bot.infinity_polling()
