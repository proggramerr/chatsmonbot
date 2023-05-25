import json
import os
import sqlite3
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
import logging
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from resender_bot import TelegramSender
from telethon.errors.rpcerrorlist import SessionPasswordNeededError, InviteHashExpiredError, FloodWaitError

logging.basicConfig(level=logging.INFO)

# Подключение к базе данных SQLite
conn = sqlite3.connect('messages.db')
cursor = conn.cursor()

# Создание таблицы, если она не существует
cursor.execute('''CREATE TABLE IF NOT EXISTS accounts
                  (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  api_id TEXT,
                  api_hash TEXT,
                  session_filename TEXT,
                  proxy TEXT,
                  proxy_port TEXT,
                  proxy_login TEXT,
                  proxy_password TEXT,
                  app_version TEXT,
                  device TEXT,
                  chat_id TEXT,
                  count_chats INT,
                  active BOOLEAN,
                  keyword TEXT,
                  name TEXT)''')
conn.commit()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS chats (
        session_filename TEXT,
        chat_url TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS last_messages (
        last_message_id INT,
        dialog_id INT
    )
''')

conn.commit()

bot = Bot(token='6131466282:AAFvKWjYGAybbGcyiwML29uEBYDQG8Hsi90')
dp = Dispatcher(bot, storage=MemoryStorage())

class Files(StatesGroup):
    json_file = State()
    session_file = State()

class Subscribe(StatesGroup):
    message = State()
    session_file = State()
    chat_url = State()

class Chat(StatesGroup):
    session_file = State()
    chat_id = State()

class Keyword(StatesGroup):
    keyword = State()
    session_file = State()

class Name(StatesGroup):
    name = State()
    session_file = State()

telegram_senders = {}

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    print(telegram_senders)
    query  = """
            SELECT * FROM accounts
            """
    cursor.execute(query)
    results = cursor.fetchall()
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if results:
        for result in results:
            if not result[14]:
                keyboard.add(types.InlineKeyboardButton(result[3].split('.')[0], callback_data=f'account_{result[3]}'))
            else:
                keyboard.add(types.InlineKeyboardButton(f"{result[3].split('.')[0]} - {result[14]}", callback_data=f'account_{result[3]}'))
    keyboard.add(types.InlineKeyboardButton("Добавить", callback_data="add"))
    await message.answer("Выберите аккаунт или добавьте новый:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('end'), state='*')
async def return_to_menu(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    query  = """
            SELECT * FROM accounts
            """
    cursor.execute(query)
    results = cursor.fetchall()
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    if results:
        for result in results:
            keyboard.add(types.InlineKeyboardButton(result[3].split('.')[0], callback_data=f'account_{result[3]}'))
    
    keyboard.add(types.InlineKeyboardButton("Добавить", callback_data="add"))
    await callback_query.message.answer("Выберите аккаунт или добавьте новый:", reply_markup=keyboard)



@dp.callback_query_handler(lambda c: c.data.startswith('account'))
async def info_account(callback_query: types.CallbackQuery):
    data = callback_query.data.split('_')
    session_filename = data[1]
    result = get_current_session(session_filename)
    session_name = session_filename.split('.')[0]
    print(session_name)
    
    if result[11] != None:
        dialogs = result[11]
    else:
        dialogs = '⛔️'

    if result[10] != None:
        chat_to_resend = result[10]
    else:
        chat_to_resend = '⛔️'
    if result[13] != None:
        keywords = result[13]
    else:
        keywords = '*'
    if result[14] != None:
        name = result[14]
    else:
        name = ''

    print(chat_to_resend)

    text = f'👤*Аккаунт №*`{session_name} {name}`\n\n💬*Кол-во чатов*: `{dialogs}`\n↪️*Чат для пересылки*: `{chat_to_resend}`\n*🗝Ключевые слова:* `{keywords}`\n\n⚠️*Внимание*\n_Убедитесь перед запуском, что верно указали чат для пересылки сообщений_'
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    subscribe_button = types.InlineKeyboardButton('➕ Подписаться', callback_data=f'subscribe_{result[3]}')
    enter_resend_dialog_button = types.InlineKeyboardButton('💌 Чат для пересылки', callback_data=f'resend-chat_{result[3]}')
    add_keyword_button = types.InlineKeyboardButton('🗝 Изменить ключевые слова', callback_data=f'keyword_{result[3]}')
    edit_name = types.InlineKeyboardButton('🗣 Изменить название', callback_data=f'name_{result[3]}')
    start_resend_button = types.InlineKeyboardButton('▶️ Запустить пересылку', callback_data=f'start_{result[3]}')
    end_resend_button = types.InlineKeyboardButton('⏸ Остановить пересылку', callback_data=f'stop_{result[3]}')
    delete_button = types.InlineKeyboardButton('❌ Удалить аккаунт', callback_data=f'delete_{result[3]}')
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(subscribe_button, enter_resend_dialog_button, add_keyword_button, edit_name)
    if session_filename in telegram_senders:
        keyboard.add(end_resend_button)
    else:
        keyboard.add(start_resend_button)
    keyboard.add(delete_button, back_to_menu)
    await callback_query.message.answer(text=text, parse_mode='Markdown', reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('delete'))
async def start_bot(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split('_')
    query = """
                DELETE FROM accounts WHERE session_filename = ?
                """
    data_query = (data[1],)
    cursor.execute(query, data_query)
    conn.commit()
    await bot.edit_message_text(text='✅Аккаунт удален. Напишите /start чтобы вернуться в меню.', chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)

@dp.callback_query_handler(lambda c: c.data.startswith('name'))
async def enter_keyword(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split('_')
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    await callback_query.message.answer('*Отправьте боту название для сессии*', parse_mode='Markdown', reply_markup=keyboard)
    await state.update_data(session_file=data[1])
    await Name.name.set()

@dp.message_handler(state=Name.name)
async def edit_keyword(message: types.Message, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    keyword = message.text
    query = """
            UPDATE accounts
            SET name = ?
            WHERE session_filename = ?
            """
    data = await state.get_data()
    session_filename = data['session_file']
    cursor.execute(query, (keyword, session_filename))
    conn.commit()
    await message.answer('✅Название успешно изменено')
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('keyword'))
async def enter_keyword(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split('_')
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    await callback_query.message.answer('🗝*Отправьте боту ключевые слова в таком формате: машина,стол*', parse_mode='Markdown', reply_markup=keyboard)
    await state.update_data(session_file=data[1])
    await Keyword.keyword.set()

@dp.message_handler(state=Keyword.keyword)
async def edit_keyword(message: types.Message, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    keyword = message.text
    query = """
            UPDATE accounts
            SET keyword = ?
            WHERE session_filename = ?
            """
    data = await state.get_data()
    session_filename = data['session_file']
    cursor.execute(query, (keyword, session_filename))
    conn.commit()
    await message.answer('✅Ключевые слова успешно добавлены.')
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith('start'))
async def start_bot(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split('_')
    result = get_current_session(data[1])
    try:
        telethon = TelegramSender(result[1], result[2], f'sessions/{result[3]}', result[4], result[5], result[6], result[7], result[8], result[9], result[10])
        await telethon.start()
        await telethon.check_chat()
        await callback_query.message.answer('✅Бот запущен\nНапишите /start, чтобы вернуться в меню.')
        telegram_senders[data[1]] = telethon
        await telethon.new_message_handler()
    except SessionPasswordNeededError:
        await callback_query.message.answer('⛔️Бот не запущен. Сессия не авторизована.')
        await telethon.stop()
    except (ValueError, InviteHashExpiredError):
        await callback_query.message.answer('⛔️Бот не запущен. Неверный чат для пересылки.')
        await telethon.stop()
    except FloodWaitError as e:
        await callback_query.message.answer(f'⛔️Бот не запущен. Флуд контроль. Подождите некоторое время. \n\n`{e}`', parse_mode='Markdown')
        await telethon.stop()

@dp.callback_query_handler(lambda c: c.data.startswith('stop'))
async def start_bot(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data.split('_')
    await telegram_senders[data[1]].stop()
    del telegram_senders[data[1]]
    await callback_query.message.answer('✅Бот остановлен\nНапишите /start, чтобы вернуться в меню.')

@dp.callback_query_handler(lambda c: c.data.startswith('resend-chat'))
async def choice_resend_chat(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    data = callback_query.data.split('_')
    print(data)
    if data[1] in telegram_senders:
        await telegram_senders[data[1]].stop()
        del telegram_senders[data[1]]
    await state.update_data(session_file=data[1])
    await callback_query.message.answer('🔗*Отправьте ссылку на чат формата https://t.me/+gzm8AZJSwqViYThi*', parse_mode='Markdown', reply_markup=keyboard)
    await Chat.chat_id.set()


@dp.message_handler(state=Chat.chat_id)
async def edit_chat_id(message: types.Message, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    chat_id = message.text
    query = """
            UPDATE accounts
            SET chat_id = ?
            WHERE session_filename = ?
            """
    data = await state.get_data()
    session_filename = data['session_file']
    print(session_filename)
    cursor.execute(query, (chat_id, session_filename))
    conn.commit()
    await message.answer('✅Чат успешно изменен', reply_markup=keyboard)
    await state.finish()


def get_current_session(session_filename):
    query = """
            SELECT * FROM accounts WHERE session_filename = ?
            """
    data = (session_filename,)
    cursor.execute(query, data)
    conn.commit()
    results = cursor.fetchall()
    result = results[0]
    return result

@dp.callback_query_handler(lambda c: c.data.startswith('subscribe'))
async def subscribe_account(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    data = callback_query.data.split('_')
    if data[1] in telegram_senders:
        await telegram_senders[data[1]].stop()
        del telegram_senders[data[1]]
    message = await callback_query.message.answer('🔗*Отправьте боту ссылку на чат*\n_Если нужно подписаться на более чем 1 чат, укажите все нужные чаты с новой строки_.\n\n⛔️*Внимание*\n_Не рекомендутеся подписываться на более чем_ `20` _чатов в день._\n\n🕐_Перед дальнейшим использованием бота, дождитесь завершения процесса..._', parse_mode='Markdown', reply_markup=keyboard)
    await state.update_data(session_file=data[1])
    await state.update_data(message=message)
    await Subscribe.chat_url.set()

@dp.message_handler(state=Subscribe.chat_url)
async def subscribe_to_chat(message: types.Message, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    urls = message.text
    urls_list = urls.split('\n')
    data = await state.get_data()
    result = get_current_session(data['session_file'])
    for url in urls_list:
        cursor.execute('INSERT INTO chats (session_filename, chat_url) VALUES (?, ?)', (result[3], url))
        conn.commit()
    try:
        await message.answer(f'✅*Нашел {len(urls_list)} чатов*. `Ваши чаты будут автоматически добавлены.`', parse_mode='Markdown', reply_markup=keyboard)
    except Exception as e:
       await message.answer(f'⛔️*Произошла ошибка. Напишите /start, чтобы вернуться в меню*', parse_mode='Markdown')
    finally:
        await state.finish()
    


@dp.callback_query_handler(lambda c: c.data.startswith('add'))
async def add_account(callback_query: types.CallbackQuery, state: FSMContext):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    back_to_menu = types.InlineKeyboardButton('↩️ Вернуться в меню', callback_data=f'end')
    keyboard.add(back_to_menu)
    await bot.send_message(callback_query.from_user.id, "Отправьте файл .session и .json одним сообщением.", reply_markup=keyboard)
    await Files.json_file.set()


@dp.message_handler(state=Files.json_file, content_types=types.ContentType.DOCUMENT)
async def download_files_handler(message: types.Message, state: FSMContext):
    document = message.document
    file_name = document.file_name
    file_id = document.file_id
    file_path = f'sessions/{file_name}'
    await message.answer(f"Получен файл: {file_name}")
    await bot.download_file_by_id(file_id, file_path)
    if file_name.split('.')[1] == 'json':
        with open(file_path) as file:
            json_data = json.loads(file.read())
            try:
                await update_session_data(json_data,)
                await message.answer('Данные загружены')
            except Exception as e:
                print(e)
                await message.answer('Ошибка при загрузке данных')
    await state.finish()

async def update_session_data(json_data):
    query  = """
            SELECT * FROM accounts WHERE session_filename = ?
            """
    session_filename = f"{json_data['session_file']}.session"
    cursor.execute(query, (session_filename, ))
    results = cursor.fetchall()
    if results:
        query = """
                DELETE FROM accounts WHERE session_filename = ?
                """
        data = (session_filename,)
        cursor.execute(query, data)
        conn.commit()
    api_id = json_data['app_id']
    api_hash = json_data['app_hash']
    proxy = json_data['proxy'][1]
    proxy_port = json_data['proxy'][2]
    proxy_login = json_data['proxy'][4]
    proxy_password = json_data['proxy'][5]
    app_version = json_data['app_version']
    device = json_data['device']
    query = """
        INSERT INTO accounts (api_id, api_hash, session_filename, proxy, proxy_port, proxy_login, proxy_password, app_version, device)
        SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
        WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE session_filename = ?)
    """
    data = (api_id, api_hash, session_filename, proxy, proxy_port, proxy_login, proxy_password, app_version, device, session_filename)
    cursor.execute(query, data)
    conn.commit()
    
    


def main():
    executor.start_polling(dp, skip_updates=True)


if __name__ == '__main__':
    main()