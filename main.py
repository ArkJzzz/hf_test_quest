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

import pandas
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

    excel_data = pandas.read_excel(applicants_file, sheet_name=sheet_name)
    applicants = []

    for str_number in range(len(excel_data)):
        applicant = {
            'position': excel_data.loc[str_number, 'Должность'],
            'fullname': excel_data.loc[str_number, 'ФИО'],
            'salary': excel_data.loc[str_number, 'Ожидания по ЗП'],
            'comment': excel_data.loc[str_number, 'Комментарий'],
            'status': excel_data.loc[str_number, 'Статус'],
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
    salary = ''.join(re.findall(r'\d', str(applicant['salary'])))
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
        'money': salary,
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


if __name__ == '__main__':
    main()


# {'id': 41, 'name': 'New Lead', 
#             'type': 'user', 'removed': None, 'order': 1}, 

# {'id': 42, 'name': 'Submitted', 
#             'type': 'user', 'removed': None, 'order': 2}, 

# {'id': 43, 'name': 'Contacted', 
#             'type': 'user', 'removed': None, 'order': 3}, 

# {'id': 44, 'name': 'HR Interview', 
#             'type': 'user', 'removed': None, 'order': 4}, 

# {'id': 45, 'name': 'Client Interview', 
#             'type': 'user', 'removed': None, 'order': 5}, 

# {'id': 46, 'name': 'Offered', 
#             'type': 'user', 'removed': None, 'order': 6}, 

# {'id': 47, 'name': 'Offer Accepted', 
#             'type': 'user', 'removed': None, 'order': 7}, 

# {'id': 48, 'name': 'Hired', 
#             'type': 'hired', 'removed': None, 'order': 8}, 

# {'id': 49, 'name': 'Trial passed', 
#             'type': 'user', 'removed': None, 'order': 9}, 

# {'id': 50, 'name': 'Declined', 
#             'type': 'trash', 'removed': None, 'order': 9999}

