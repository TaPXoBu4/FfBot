import asyncio
import variables
import sqlite3 as sq
from mbtools import client
from pymodbus.exceptions import ConnectionException
from config import _logger


# Конвертация получаемых данных
def convert_to_bin(num: int, zerofill: int):
    """
    Конвертация десятичного числа в двоичное
    :param num: int
    :param zerofill: int
    :return: string
    """
    return bin(num)[2:].zfill(zerofill)[::-1]


# Опрос ПР
async def reg_reading():
    """
    Чтение регистров ПР-ХХ и запись их в оперативную память
    :return: None
    """
    await asyncio.sleep(3)
    while True:
        try:
            res = client.read_holding_registers(16384, 4)
            if res.isError():
                variables.connection = False
            else:
                variables.connection = True
                result = res.registers
                variables.levels['value'] = convert_to_bin(result[0], 4)
                variables.valves['value'] = convert_to_bin(result[1], 4)
                variables.pressure['value'] = convert_to_bin(result[2], 4)
                variables.test = convert_to_bin(result[3], 2)
        except ConnectionException:
            variables.connection = False
        await asyncio.sleep(2)


def inform(data: dict):
    """
    Формирование информации из словаря
    :param data: dict
    :return: string
    """
    txt = ''
    first_case = data['value'][:2]
    second_case = data['value'][2:]
    if variables.connection:
        for i in range(2):
            num = i + 1
            if data['name'] == 'Уровни емкостей':
                if (first_case[i] + second_case[i]) == '00':
                    txt += data['txt'][0].format(num)
            else:
                if int(first_case[i]):
                    txt += data['txt'][0].format(num)
            if int(second_case[i]):
                txt += data['txt'][1].format(num)
        if not txt:
            txt += data['name'] + ': Норма.\n'
    else:
        txt += 'Нет связи с прибором...'
    return txt


def complex_info():
    """
    Комплексноя информация
    :return: string
    """
    txt = inform(variables.levels) + inform(variables.valves) + inform(variables.pressure)
    if variables.test[0]:
        txt += 'Необходима плановая проверка насосов!\n'
    return txt


def check_crits_and_testresult():
    """
    Мониторинг критического уровня жидкости в емкостях и результата теста
    :return: string
    """
    txt = ''
    levels = variables.levels['value'][2:]
    for i in range(2):
        if int(levels[i]) and levels[i] != variables.levels['prev_low_levels'][i]:
            txt += variables.levels['txt'][1].format(i+1)
        variables.levels['prev_low_levels'][i] = levels[i]
    if int(variables.test[1]):
        if client.connect():
            client.write_register(16390, 1)
            client.write_register(16390, 0)
            txt += 'Результаты теста:\n' + inform(variables.valves) + inform(variables.pressure)
    return txt


def save_user(user_id, username):
    """
    Сохраняет юзеров в БД и добавляет в бот
    :param user_id: int
    :param username: string
    :return: None
    """
    save_query = 'INSERT INTO users(user_id, username) VALUES (?, ?)'
    with sq.connect('TwoPumps.db') as con:
        cur = con.cursor()
        cur.execute(save_query, (user_id, username))
        con.commit()
    variables.users[user_id] = username


def users_parser():
    """
    Функция парсит юзеров из Базы Данных в бота
    :return: None
    """
    with sq.connect('TwoPumps.db') as con:
        cur = con.cursor()
        parse_query = 'SELECT * FROM users'
        cur.execute(parse_query)
        temp = cur.fetchall()
        if temp:
            for pair in temp:
                key, value = pair
                variables.users[key] = value


async def start_test():
    """
    Разрешение на запуск теста, длительность 20 секунд
    :return: None
    """
    _logger.info('### Был запрошен тест')
    if client.connect():
        client.write_register(16389, 1)
        await asyncio.sleep(20)
        client.write_register(16389, 0)
