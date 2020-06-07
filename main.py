#!/usr/bin/python3
__author__ = 'ArkJzzz (arkjzzz@gmail.com)'


import os
import logging
import requests
import re

from os import getenv
from os import listdir
from os import walk as walkpath
from os.path import isfile
from os.path import dirname
from os.path import abspath
from os.path import join as joinpath

import openpyxl
from dotenv import load_dotenv
from magic import Magic



logging.basicConfig(
    format='%(name)s:%(funcName)s:%(lineno)d - %(message)s', 
    datefmt='%Y-%b-%d %H:%M:%S (%Z)',
)
logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


def main():
    '''
    Я предполагаю, что структура директорий и файлов остается неизменной
    и имеет следующий вид (исходя из задачи):
    
       Тестовое задание
       ├── Тестовая база.xlsx
       ├── README.md
       ├── Frontend-разработчик
       │   ├── Глибин Виталий Николаевич.doc
       │   └── Танский Михаил.pdf
       └── Менеджер по продажам
           ├── Корниенко Максим.doc
           └── Шорин Андрей.pdf
    '''

    # Init

    BASE_DIR = dirname(abspath(__file__))
    FILES_DIR = 'Тестовое задание'
    FILES_DIR = joinpath(BASE_DIR, FILES_DIR)

    applicants_file = 'Тестовая база.xlsx'
    applicants_file = joinpath(FILES_DIR, applicants_file)
    sheet_name = 'Лист1'

    # API huntflow.ru
    load_dotenv()
    huntflow_token = os.getenv('HUNTFLOW_TOKEN')
    host = 'dev-100-api.huntflow.ru'


    # Do 

    vacancies = get_company_vacancies(host, huntflow_token)
    vacancies = vacancies['items']
    applicants = get_applicants_from_excel_file(applicants_file, sheet_name)


    for applicant in applicants:
        resume_file = find_resume_file(
                applicant_fullname=applicant['fullname'], 
                files_dir=FILES_DIR,
            )
        logger.debug('{}\n{}'.format(applicant, resume_file))
        recognized_resume = upload_resume(
                host=host,
                token=huntflow_token,
                filename=resume_file,
            )
        applicant_data = get_applicant_data(
                applicant=applicant, 
                recognized_resume=recognized_resume, 
                vacancies=vacancies,
            )
        add_applicant(
                host=host,
                token=huntflow_token,
                applicant_data=applicant_data,
            )

        last_added = get_applicants(host, huntflow_token)['items'][0]
        print(last_added)
        print()




    # existing_applicants = get_applicants(host, huntflow_token)['items']
    # print('всего в базе кандидатов:', get_applicants(host, huntflow_token)['total_items'])
    # print(existing_applicants[0])
    # for applicant in existing_applicants:
    #     print(applicant['id'], applicant['last_name'])

def add_to_vacancy(host, token, applicant):
    ''' Добавление кандидата на вакануию '''

    url = 'https://{host}/account/6/applicants{applicant_id}/vacancy'.format(
            host=host,
            applicant_id=None, # FIXME: нужен id кандидата
        )
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }
    payload = {
        "vacancy": 988,
        "status": 1230,
        "comment": applicant['comment'],
        "files": [
            {
                "id": 1382810
            }
        ],
        "rejection_reason": null,
        "fill_quota": 234
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json() 


def get_applicants_from_excel_file(applicants_file, sheet_name):
    '''    
    Я предполагаю, что файл с кандидатами имеет неизменный формат, 
    такой, как в файле 'Тестовая база.xlsx':
    - значения ячеек столбца 'Должность' выбираются из списка
      и соответствуют названию вакансии в Хантфлоу
    - значения ячеек столбца 'Статус' выбираются из списка
      и соответствуют типу (id) статуса в Хантфлоу
    - значения ячеек столбца 'ФИО' всегда идут в порядке 
      Фамилия-Имя-Отчество (при наличии), и соответствуют имени 
      файла резюме
    '''

    workbook = openpyxl.load_workbook(applicants_file, read_only=True)
    sheet_names = workbook.get_sheet_names()
    sheet_name = sheet_names[0]
    excel_data = workbook.get_sheet_by_name(sheet_name)
    applicants = []

    for row in list(excel_data.rows)[1:]:
        applicant = {
            'position': row[0].value,
            'fullname': replace_noncyrillic_characters(row[1].value),
            'salary': ''.join(re.findall(r'\d', str(row[2].value))),
            'comment': row[3].value,
            'status': replace_status(row[4].value),
        }
        applicants.append(applicant)

    return applicants


def get_applicants(host, token):
    url = 'https://{host}/account/6/applicants'.format(host=host)
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }
    response = requests.get(url, headers=headers)
    return(response.json())


def find_resume_file(applicant_fullname, files_dir):
    applicant_fullname = replace_noncyrillic_characters(applicant_fullname)
    for root, dirs, files in walkpath(files_dir):
        for filename in files:
            filename_without_ext = filename.split('.')
            clear_filename = replace_noncyrillic_characters(filename_without_ext[0])
            if clear_filename:
                if applicant_fullname in clear_filename:
                    return joinpath(root, filename)


def upload_resume(host, token, filename):
    '''
    Загрузка и распознование файлов

    Документация к API huntflow обязывает отправлять запрос multipart/form-data.
    Но при установке в заголовке параметра 'Content-Type': 'multipart/form-data'
    на запрос возвращается ошибка {"errors": [{"type": "server_error"}]}.
    Поэтому я отправляю Content-Type в параметре files.
    (Через curl запрос проходит, через requests - нет).
    '''
    
    url = 'https://{host}/account/6/upload'.format(host=host)
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
        # 'Content-Type': 'multipart/form-data',
        'X-File-Parse': 'true', 
    }
    data = open(filename, 'rb')
    content_type = Magic(mime=True).from_file(filename)
    files = {
        'file': (filename, data, content_type),
    }

    response = requests.post(
        url, 
        headers=headers, 
        files=files, 
    )
    response.raise_for_status()
    logger.debug('response.OK: {}'.format(response.ok))

    return response.json()
    

def get_applicant_data(applicant, recognized_resume, vacancies):
    ''' Подготавливает данные для добавления кандидата в базу '''
    fields = recognized_resume['fields']
    experiense = recognized_resume['fields']['experience']
    if experiense[0]:
        position = experiense[0]['position']
        company = experiense[0]['company']
    birthdate = recognized_resume['fields']['birthdate']
    if not birthdate:
        birthdate = {
            'month': None,
            'day': None,
            'precision': None,
            'year': None,
        }
    photo = recognized_resume['photo']
    if not photo:
        photo = {'id': None}

    applicant_data = {
        'last_name': recognized_resume['fields']['name']['last'],
        'first_name': recognized_resume['fields']['name']['first'],
        'middle_name': recognized_resume['fields']['name']['middle'],
        'phone': ', '.join(recognized_resume['fields']['phones']),
        'email': recognized_resume['fields']['email'],
        'position': position,
        'company': company,
        'money': applicant['salary'],
        'birthday_day': birthdate['day'], #
        'birthday_month': birthdate['month'],
        'birthday_year': birthdate['year'],
        'photo': photo['id'],
        'externals': [
            {
                'data': {
                    'body': recognized_resume['text']
                },
                'auth_type': 'NATIVE',
                'files': [
                    {
                        'id': recognized_resume['id']
                    }
                ],
                'account_source': 119
            }
        ]
    }

    return applicant_data


def add_applicant(host, token, applicant_data):
    '''Добавление кандидата в базу'''
    
    url = 'https://{host}/account/6/applicants'.format(host=host)
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }
    payload = applicant_data

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()


def get_company_vacancies(host, token):
    '''Получение списка вакансий компании'''
    
    url = 'https://{host}/account/6/vacancies'.format(host=host)
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    logger.debug('Количество вакансий комании: {num}'.format(
            num=len(response.json()['items']),
        ),
    )

    return response.json()


def replace_noncyrillic_characters(string):
    '''
    Функция нормализует символы юникода к кириллическим символам
    '''
    CHARACTERS_TO_REPLACE =[
        # добавьте сюда символы, которые нужно заменить в таком формате:
        # [заменяемый, заменяющий],
        [b'\xd0\xb8\xcc\x86', b'\xd0\xb9'], # й    
    ]

    if string:
        string = ' '.join(string.split())
        string = string.encode('utf-8')
        for character in CHARACTERS_TO_REPLACE:
            string = string.replace(character[0], character[1])

        return string.decode('utf-8')


def replace_status(status):
    ''' 
    Приведение строки статуса из файла с кандидатами 
    к виду для загрузки в базу.

    Предполагается, что значения ячеек столбца 'Статус' выбираются 
    из списка и соответствуют типу (id) статуса в Хантфлоу
    '''

    statuses = [
        {41: 'New Lead'},
        {42: 'Submitted'},
        {43: 'Contacted'},
        {44: 'HR Interview'},
        {45: 'Client Interview'},
        {46: 'Offered'},
        {47: 'Offer Accepted'},
        {48: 'Hired'},
        {49: 'Trial passed'},
        {50: 'Declined'},
    ]

    if status == 'Отправлено письмо':
        status = {'id': 43, 'name': 'Contacted'}
    elif status == 'Интервью с HR':
        status = {'id': 44, 'name': 'HR Interview'}
    elif status == 'Выставлен оффер':
        status = {'id': 46, 'name': 'Offered'}
    elif status == 'Отказ':
        status = {'id': 50, 'name': 'Declined'}
    
    # FIXME: Добавить сюда остальные статусы

    else:
        status = {'id': None, 'name': None}

    return status



if __name__ == '__main__':
    main()


# {'id': 41, 'name': 'New Lead'},
# {'id': 42, 'name': 'Submitted'},
# {'id': 43, 'name': 'Contacted'},
# {'id': 44, 'name': 'HR Interview'},
# {'id': 45, 'name': 'Client Interview'},
# {'id': 46, 'name': 'Offered'},
# {'id': 47, 'name': 'Offer Accepted'},
# {'id': 48, 'name': 'Hired'},
# {'id': 49, 'name': 'Trial passed'},
# {'id': 50, 'name': 'Declined'},
