import bs4
import requests
import datetime
import time
import psycopg2
from psycopg2 import Error
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


loop_interval = 60                                                      # Интервал работы цикла

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']      # Доступ для скрипта к Google Sheets
SAMPLE_SPREADSHEET_ID = '1_rcPa41hXLIV3dAq4gNGWIgbbjwGGWCOcoMiGSwVzJo'  # ID таблицы из его html адреса
SAMPLE_RANGE_NAME = 'Testing!A1:D51'                                    # Область выборки таблицы

while True:

    """Форматируется текущая дата в ДД/ММ/ГГГГ"""
    today = datetime.datetime.today().strftime("%d/%m/%Y")

    """Создаем переменную url для файла из сайта центрального банка"""
    url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={today}"
    url_code = requests.get(url)

    """Обработка полученных данных из файла - генерация словаря (d)"""
    soup = bs4.BeautifulSoup(url_code.text, 'lxml')
    names = [x.text for x in soup.findAll('name')]
    rates = [y.text for y in soup.findAll('value')]
    d = {}

    """Заполнение словаря, где ключ это название валюты, а значение - курс"""
    for i in range(len(names)):
        d[names[i]] = round(float(rates[i].replace(',', '.')), 2)

    def main():
        """Функция для исполнения Sheets API по извлечению
        значений 'values' из таблицы google spreadsheets.
        """
        creds = None

        # Файл token.json хранит доступ пользователя и обновляет токены, также он
        # создается автоматически в случае выполнения процесса авторизации в первый раз
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)

        # Если нет доступных (действительных) учетных данных, позволяет пользователю войти в систему
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)

            with open('token.json', 'w') as token:              # Сохраняет учетные данные для следующего запуска
                token.write(creds.to_json())

        try:
            service = build('sheets', 'v4', credentials=creds)

            # Вызов Sheets API
            sheet = service.spreadsheets()
            result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID,
                                        range=SAMPLE_RANGE_NAME).execute()
            values = result.get('values', [])

            if not values:
                print('Данных не найдено')
                return

        except HttpError as err:
            print(err)

        # Создаем текстовый файл sample.txt и заполняем его данными из электронной таблицы
        with open('sample.txt', 'w', encoding='utf-8') as file:
            while len(values) != 1:
                file.write("('")
                file.write(values[1][0])
                file.write("', '")
                file.write(values[1][1])
                file.write("', '")
                file.write(values[1][2])
                file.write("', '")
                file.write(values[1][3])
                file.write("', '")
                file.write(str(int(values[1][2])*d['Доллар США']))      # Здесь получаем текущий курс в рублях
                file.write("')\n")
                del values[1]

        # Установка соединения с базой данных PostgreSQL
        try:
            connect = psycopg2.connect(
                host="localhost",           # Замените на свой локальный адрес
                user="postgres",            # Замените на своё имя пользователя
                password="qwerty123",       # Замените на свой пароль
                database="postgres_db",     # Замените на своё наименование базы данных
                port="5432"                 # Замените на свой порт
            )

            # Создаем таблицу index в PostgreSQL, если его не существует
            with connect.cursor() as cursor:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS index (
                    id serial PRIMARY KEY,
                    zakaz_no INT NOT NULL,
                    stoimost_usd INT NOT NULL,
                    srok_postavke date,
                    stoimost_rub DECIMAL(10,2));"""
                )
                connect.commit()
                print("[ИНФО] Таблица успешно создана")

            # Удаляем все данные из таблицы index, чтобы заполнить его новыми данными
            with connect.cursor() as cursor:
                cursor.execute(
                    """DELETE FROM index;"""
                )

            # Заполняем данными, полученными из google spreadsheets, на постоянной основе
            with open('sample.txt', 'r', encoding='utf-8') as file:
                for u in file.readlines():
                    with connect.cursor() as cursor:
                        cursor.execute(
                            f"INSERT INTO index (id, zakaz_no, stoimost_usd, srok_postavke, stoimost_rub) VALUES {u};"
                        )
                        connect.commit()
                        print("[ИНФО] Данные введены")

        except Exception as _ex:
            print("[ИНФО] Ошибка при работе с PostgreSQL", _ex)
        finally:
            if connect:
                connect.close()
                print("[ИНФО] Соединение с PostgreSQL закрыто")


    if __name__ == '__main__':
        main()
    time.sleep(loop_interval)

