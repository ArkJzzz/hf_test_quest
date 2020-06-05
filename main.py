#!/usr/bin/python3
__author__ = 'ArkJzzz (arkjzzz@gmail.com)'


import os
import logging
import requests

from os import getenv
from os import listdir
from os import walk as walkpath
from os.path import isfile
from os.path import dirname
from os.path import abspath
from os.path import join as joinpath

from dotenv import load_dotenv
import pandas
from magic import Magic



logging.basicConfig(
    format='%(name)s:%(funcName)s:%(lineno)d - %(message)s', 
    datefmt='%Y-%b-%d %H:%M:%S (%Z)',
)
logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


def main():
    # Я предполагаю, что структура директорий и файлов остается неизменной
    # и имеет следующий вид (исходя из задачи):
    # 
    #    Тестовое задание
    #    ├── Тестовая база.xlsx
    #    ├── README.md
    #    ├── Frontend-разработчик
    #    │   ├── Глибин Виталий Николаевич.doc
    #    │   └── Танский Михаил.pdf
    #    └── Менеджер по продажам
    #        ├── Корниенко Максим.doc
    #        └── Шорин Андрей.pdf
    #

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


    filename = 'test_resume.pdf'
    # answer = upload_resume(host, huntflow_token, filename)
    # # vacancies = get_company_vacancies(host, huntflow_token)

    # applicant_fullname = answer['fields']['name']
    # applicant_fullname = '{last} {first} {middle}'.format(
    #         first=applicant_fullname['first'],
    #         middle=applicant_fullname['middle'],
    #         last=applicant_fullname['last'],
    #     )
    # print(applicant_fullname)



    # read .xlsx 

    # Я предполагаю, что файл с кандидатами имеет неизменный формат, 
    # такой, как в файле 'Тестовая база.xlsx':
    # - значения ячеек столбца 'Должность' выбираются из списка
    #   и соответствуют названию вакансии в Хантфлоу
    # - значения ячеек столбца 'Статус' выбираются из списка
    #   и соответствуют типу (id) статуса в Хантфлоу
    # - значения ячеек столбца 'ФИО' всегда идут в порядке 
    #   Фамилия-Имя-Отчество (при наличии), и соответствуют имени 
    #   файла резюме

    dataframe = pandas.read_excel(applicants_file, sheet_name=sheet_name)
    

    # print(dataframe.columns.ravel())
    # print(dataframe['ФИО'].tolist())
    # print(dataframe.to_dict())
    # print(dataframe.loc[[0]])
    # df_filter = dataframe['Должность'].isin(['Frontend-разработчик'])
    # print(dataframe[df_filter])

    applicants = dataframe['ФИО'].tolist()

    for applicant in applicants:
        clear_name = ' '.join(applicant.split())
        print()
        # logger.debug(clear_name)

        resume_file = find_resume_file(clear_name, FILES_DIR)
        logger.debug(resume_file)




def find_resume_file(applicant_fullname, files_dir):
    logger.debug('{} {}'.format(len(applicant_fullname), applicant_fullname))
    applicant_fullname = replace_noncyrillic_characters(applicant_fullname)

    for root, dirs, files in walkpath(files_dir):
        for filename in files:
            filename_without_ext = filename.split('.')
            filename_chunks = filename_without_ext[0].split()
            if filename_chunks:
                clear_filename = ' '.join(filename_chunks)
                clear_filename = replace_noncyrillic_characters(clear_filename)
                if applicant_fullname in clear_filename:
                    return joinpath(root, filename)




def add_applicant(host, token):
    '''Добавление кандидата в базу'''
    
    url = 'https://{host}/account/6/applicants'.format(host=host)
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }   
    response = requests.post(url, headers=headers, json=payload)


    payload = {
        "last_name": "Глибин",
        "first_name": "Виталий",
        "middle_name": "Николаевич",
        "phone": "89260731778",
        "email": "glibin.v@gmail.com",
        "position": "Фронтендер",
        "company": "ХХ",
        "money": "100000 руб",
        "birthday_day": 20,
        "birthday_month": 7,
        "birthday_year": 1984,
        "photo": 12341,
        "externals": [
            {
                "data": {
                    "body": "Текст резюме\nТакой текст"
                },
                "auth_type": "NATIVE",
                "files": [
                    {
                        "id": 12430
                    }
                ],
                "account_source": 208
            }
        ]
    }


def get_company_vacancies(host, token):
    '''Получение списка вакансий компании'''
    
    url = 'https://{host}/account/6/vacancies'.format(host=host)
    headers = {
        'User-Agent': 'test-quest (arkjzzz@gmail.com)',
        'Authorization': token,
    }   
    response = requests.get(url, headers=headers)
    vacancies = response.json()
    logger.debug('Количество вакансий комании: {num}'.format(
            num=len(vacancies['items']),
        ),
    )

    return(vacancies)


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
    logger.debug('response.OK: {}'.format(response.ok))
    # logger.debug(response.json())

    return response.json()
    

def replace_noncyrillic_characters(string):

    CHARACTERS_TO_REPLACE =[
        [b'\xd0\xb8\xcc\x86', b'\xd0\xb9'], # й
        # добавьте сюда другие символы, которые нужно заменить
    ]

    string = string.encode('utf-8')
    for character in CHARACTERS_TO_REPLACE:
        string = string.replace(character[0], character[1])

    return string.decode('utf-8')

if __name__ == "__main__":
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

