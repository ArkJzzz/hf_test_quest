#!/usr/bin/python3
__author__ = 'ArkJzzz (arkjzzz@gmail.com)'


import argparse
import logging
import os
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


HOST = 'dev-100-api.huntflow.ru'
ORGANIZATION_ID = 6
# ORGANIZATION_ID из ответа на запрос:
# curl -X GET -H "Authorization: Bearer <token>" https://<HOST>/accounts


def main():

    parser = argparse.ArgumentParser(
        description='''
        Программа для переноса базы кандидатов из файла Excel в базу 
        Huntflow с помощью Huntflow API (https://github.com/huntflow/api).
        
        Укажите токен к API Huntflow, 
        имя директории, в которой находятся файлы резюме, 
        и имя файла Excel с кандидатами.
        '''
    )

    parser.add_argument('huntflow_token', help='Токен к API Huntflow')
    parser.add_argument('directory', help='Путь к директории, с файлами')
    # parser.add_argument('applicants_file', help='Имя файла с кандидатами')
    args = parser.parse_args()

    '''
    Я предполагаю, что структура директорий и файлов остается неизменной
    и имеет следующий вид (исходя из условий ТЗ):
    
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
    
    FILES_DIR = args.directory

    for root, dirs, files in walkpath(FILES_DIR):
        for file in files:
            if file[-5:] == '.xlsx':
                applicants_file = joinpath(FILES_DIR, file)

    # API huntflow.ru
    huntflow_token = 'Bearer {token}'.format(token=args.huntflow_token)

    
    # Do 

    vacancies = get_company_vacancies(huntflow_token)
    vacancies = vacancies['items']
    applicants = get_applicants_from_excel_file(applicants_file)


    for applicant in applicants:
        resume_file = find_resume_file(
                applicant_fullname=applicant['fullname'], 
                files_dir=FILES_DIR,
            )
        recognized_resume = upload_resume(
                token=huntflow_token,
                filename=resume_file,
            )
        applicant_data = get_applicant_data(
                applicant=applicant, 
                recognized_resume=recognized_resume, 
                vacancies=vacancies,
            )
        add_applicant(
                token=huntflow_token,
                applicant_data=applicant_data,
            )

        last_added = get_applicants(huntflow_token)['items'][0]
        applicant['id'] = last_added['id']
        add_to_vacancy(
            token=huntflow_token, 
            applicant=applicant, 
            vacancies=vacancies, 
            recognized_resume=recognized_resume,
        )


def get_company_vacancies(token):
    '''Получение списка вакансий компании'''
    
    url = 'https://{host}/account/{id}/vacancies'.format(
            host=HOST,
            id=ORGANIZATION_ID,
        )
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }

    response = requests.get(url, headers=headers)
    if response.ok:
        logger.debug('Количество вакансий комании: {num}'.format(
                num=len(response.json()['items']),
            ),
        )
    else:
        logger.error('Ошибка получения списка вакансий')

    return response.json()


def get_applicants_from_excel_file(applicants_file):
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

    logger.info('Файл {} успешно прочитан'.format(applicants_file))

    return applicants


def find_resume_file(applicant_fullname, files_dir):
    applicant_fullname = replace_noncyrillic_characters(applicant_fullname)
    for root, dirs, files in walkpath(files_dir):
        for filename in files:
            filename_without_ext = filename.split('.')
            clear_filename = replace_noncyrillic_characters(filename_without_ext[0])
            if clear_filename:
                if applicant_fullname in clear_filename:
                    logger.info('Файл резюме найден: {}'.format(joinpath(root, filename)))
                    return joinpath(root, filename)


def upload_resume(token, filename):
    '''
    Загрузка и распознование файлов

    Документация к API huntflow обязывает отправлять запрос multipart/form-data.
    Но при установке в заголовке параметра 'Content-Type': 'multipart/form-data'
    на запрос возвращается ошибка {"errors": [{"type": "server_error"}]}.
    Поэтому я отправляю Content-Type в параметре files.
    (Через curl запрос проходит, через requests - нет).
    '''
    
    url = 'https://{host}/account/{id}/upload'.format(
            host=HOST,
            id=ORGANIZATION_ID,
        )
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
    if response.ok:
        logger.info('Файлы резюме успешно распознан: {}'.format(files))
    else:
        logger.error('Ошибка загрузки файлов резюме: {}'.format(files))

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


def add_applicant(token, applicant_data):
    '''Добавление кандидата в базу'''
    
    url = 'https://{host}/account/{id}/applicants'.format(
            host=HOST,
            id=ORGANIZATION_ID,
        )
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }
    payload = applicant_data

    response = requests.post(url, headers=headers, json=payload)
    if response.ok:
        logger.info(
            'Кандидат {} успешно добавлен в Huntflow на должность {}'.format(
                    applicant_data['last_name'],
                    applicant_data['position'],
                )
        )
    else:
        logger.error(
            'Ошибка добавления кандидата {} на должность {}'.format(
                    applicant_data['last_name'],
                    applicant_data['position'],
                )
        )

    return response.json()


def get_applicants(token):
    ''' Получение списка кандидатов '''

    url = 'https://{host}/account/{id}/applicants'.format(
            host=HOST,
            id=ORGANIZATION_ID,
        )
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }
    response = requests.get(url, headers=headers)
    if response.ok:
        logger.info('Список имеющихся кандидатов успешно получен')
    else:
        logger.error('Ошибка получения списка имеющихся кандидатов')

    return(response.json())


def add_to_vacancy(token, applicant, vacancies, recognized_resume):
    ''' Добавление кандидата на ваканcию 

    Предполагается, что  значения ячеек столбца 'Должность' выбираются из списка и соответствуют названию вакансии в Хантфлоу
    '''

    url = 'https://{host}/account/{id}/applicants/{applicant_id}/vacancy'.format(
            host=HOST,
            id=ORGANIZATION_ID,
            applicant_id=applicant['id'],
        )
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }

    for vacancy in vacancies:
        if vacancy['position'] == applicant['position']:
            vacancy_id = vacancy['id']

    payload = {
        'vacancy': vacancy_id,
        'status': applicant['status']['id'],
        'comment': applicant['comment'],
        'files': [
            {
                'id': recognized_resume['id']
            }
        ],
        # 'rejection_reason': None,
        # 'fill_quota': vacancy['applicants_to_hire']
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.ok:
        logger.info(
            'Кандидат {applicant_name} добавлен в Huntflow на должность {position}'.format(
                applicant_name=applicant['fullname'],
                position=applicant['position'],
            )
        )
    else:
        logger.error('Ошибка добавления кандидата {applicant_name} в Huntflow на должность {position}'.format(
                applicant_name=applicant['fullname'],
                position=applicant['position'],
            )
        )

    return response 


def replace_noncyrillic_characters(string):
    ''' Функция нормализует символы юникода к кириллическим символам '''

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

    if status == 'Отправлено письмо':
        status = {'id': 43, 'name': 'Contacted'}
    elif status == 'Интервью с HR':
        status = {'id': 44, 'name': 'HR Interview'}
    elif status == 'Выставлен оффер':
        status = {'id': 46, 'name': 'Offered'}
    elif status == 'Отказ':
        status = {'id': 50, 'name': 'Declined'}
    
    # FIXME: Добавить сюда остальные статусы
    # statuses = [
    #     {41: 'New Lead'},
    #     {42: 'Submitted'},
    #     {43: 'Contacted'},
    #     {44: 'HR Interview'},
    #     {45: 'Client Interview'},
    #     {46: 'Offered'},
    #     {47: 'Offer Accepted'},
    #     {48: 'Hired'},
    #     {49: 'Trial passed'},
    #     {50: 'Declined'},
    # ]

    else:
        status = {'id': None, 'name': None}

    return status


def update_applicants_file(applicants_file):
    '''
    Добавляет информацию о статусе загрузки информации о кандидате в базу: 
    - кандидат добавлен в базу - да/нет; 
    - кандидат добавлен на вакансию - да/нет.
    '''
    pass


if __name__ == '__main__':
    main()

