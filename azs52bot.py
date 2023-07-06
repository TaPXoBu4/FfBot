import asyncio
import variables
import sqlite3 as sq
import config

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.filters import Text
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TOKEN, _logger
from functions import reg_reading, inform, check_crits_and_testresult, complex_info
from functions import users_parser, save_user, start_test

# Бот, его диспетчер, планировщик
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
scheduler = AsyncIOScheduler()

# Создаем в БД таблицу юзверей
with sq.connect('TwoPumps.db') as con:
    cur = con.cursor()
    create_users_store = 'CREATE TABLE IF NOT EXISTS users (user_id INTEGER, username TEXT UNIQUE)'
    cur.execute(create_users_store)

users_parser()  # Парсим юзверей в оперативку

# Клавиатура
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
buttons_first_row = ['Тест', 'Уровни']
buttons_second_row = ['Клапаны', 'Насосы']
keyboard.add(*buttons_first_row)
keyboard.add(*buttons_second_row)


# Состояния для автомата состояний
class Access(StatesGroup):
    verification = State()
    username = State()


# Начало автомата состояний верификации и регистрации


@dp.message_handler(lambda message: message.from_user.id not in variables.users.keys())
async def anything_without_access(message: types.Message):
    await Access.verification.set()
    await message.reply('Привет, новенький! А введи-ка ты пароль!')


@dp.message_handler(lambda message: message.from_user.id not in variables.users.keys(),
                    commands=['start'], state='*')
async def start_without_access(message: types.Message, state: FSMContext):
    await state.finish()
    await Access.verification.set()
    await message.reply('Привет, новенький! А введи-ка ты пароль!')


@dp.message_handler(lambda message: message.from_user.id in variables.users.keys(), commands=['start'])
async def cmd_start_with_access(message: types.Message):
    await message.reply('И снова здравстсвуйте!', reply_markup=keyboard)


@dp.message_handler(lambda message: message.text != config.password, state=Access.verification)
async def wrong_password(message: types.Message):
    await message.answer('Неправильно, попробуйте еще раз.')


@dp.message_handler(lambda message: message.text == config.password, state=Access.verification)
async def right_password(message: types.Message):
    await Access.next()
    await message.reply('Введите свое имя. Оно должно быть уникальным.')


@dp.message_handler(lambda message: message.text in variables.users.values(), state=Access.username)
async def ununique_username(message: types.Message):
    await message.reply('Такое имя уже есть в базе.')


@dp.message_handler(lambda message: message.text not in variables.users.values(), state=Access.username)
async def unique_username(message: types.Message, state: FSMContext):
    save_user(message.from_user.id, message.text)
    await message.reply('Отлично! Вот вам кнопки.', reply_markup=keyboard)
    await state.finish()

# Конец автомата состояний верификации и регистрации


@dp.message_handler(commands=['showid'])
async def get_id(message: types.Message):
    _logger.info('### Был запрошен ID группы')
    await message.reply(message.from_user.id)


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    txt = 'Привет, я твой информационный бот. Вот тебе кнопки:'
    await message.reply(text=txt, reply_markup=keyboard)


@dp.message_handler(Text(equals='Тест'))
async def send_help(message: types.Message):
    if variables.connection:
        txt = 'Удерживайте 2 секунды кнопку "Стоп" на щите приборов.\n У вас есть на это 20 секунд.'
        await message.answer(txt)
        await start_test()
        await message.answer('Время вышло.')
    else:
        txt = 'Нет связи с прибором...'
        await message.answer(text=txt)


@dp.message_handler(Text(equals='Уровни'))
async def levels(message: types.Message):
    await message.answer(text=inform(variables.levels))


@dp.message_handler(Text(equals='Клапаны'))
async def valves(message: types.Message):
    await message.answer(text=inform(variables.valves))


@dp.message_handler(Text(equals='Насосы'))
async def pumps(message: types.Message):
    await message.answer(text=inform(variables.pressure))


async def week_mailing():
    _logger.info('### Выполнена утренняя рассылка')
    for user_id in list(variables.users.keys()):
        await bot.send_message(chat_id=user_id, text='Утренняя сводка: \n' + complex_info())


scheduler.add_job(week_mailing, 'cron', day_of_week='mon',
                  hour=9, minute=0)


async def monitoring():
    await asyncio.sleep(5)
    _logger.info(f'### Старт мониторинга критических уровней и результатов теста...')
    while True:
        txt = check_crits_and_testresult()
        if txt:
            for user_id in variables.users.keys():
                await bot.send_message(chat_id=user_id, text=txt)
        await asyncio.sleep(2)


async def on_startup(_):
    scheduler.start()
    asyncio.create_task(reg_reading())
    asyncio.create_task(monitoring())


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
