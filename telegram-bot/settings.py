# telegram-bot/settings.py

# --------------------------------------------------------------
#
# Все параметры ниже могут, а некоторые даже должны быть переназначены в local_settings.py
#

DEBUG = False

# Токен бота в телеграме
#
TOKEN = 'secret'

# Способ запуска, 'poll' или 'webhook'.
# На сервере: webhook. В консоли разработчика: poll
#
START_MODE = 'webhook'

# Webhook параметры
#
WEBHOOK_HOST = 'https://bot-dev.blagoroda.org'
WEBHOOK_PATH = '/'
WEBAPP_HOST = '127.0.0.1'
WEBAPP_PORT = 3001

import logging
LOG_LEVEL = logging.WARNING

# secs
#
HTTP_TIMEOUT = 60

# URL апи, без завершающей/, :
#
API_HOST = 'https://api.blagoroda.org'

FRONTEND_HOST = 'https://blagoroda.org'
FRONTEND_HOST_TITLE = 'БлагоРода'

# Карта всех пользователей с кластеризацией
#
MAP_HOST = 'https://map.blagoroda.org'

# Ссылка на отношения в группе
#
GROUP_HOST = 'https://group.blagoroda.org'

# Ссылка на свзи в роду
#
GENESIS_HOST = 'https://genesis.blagoroda.org'

# Ссылка на фронте, которая будет открываться там под авторизованным
# пользователем:
# <FRONTEND_HOST><FRONTEND_AUTH_PATH>?redirect_path=<frontend_path>
#
FRONTEND_AUTH_PATH = '/auth/telegram/'

# Админитраторы бота, их telegram ids
#
BOT_ADMINS = ()

# Выбираем из фото пользователей, которые шлют сообщения в бот, не меньше такого, в байтах:
#
PHOTO_MAX_SIZE = 320 * 320

# Загружаемые фото owned users, например, родственников
# Мб. Если 0 или None, без ограничений.
#
DOWNLOAD_PHOTO_MAX_SIZE = 10

# Минимальный размер сообщения для полнотекстового поиска:
#
MIN_LEN_SEARCHED_TEXT = 3

# Туры
#
TRIP_DATA = dict(
    #   chat_id='',
    #   invite_link='',
    #   text_with_invite_link='бла бла %(invite_link)s еще бла бла',
    #   text_agreement='',
)

try:
    from local_settings import *
except ModuleNotFoundError:
    pass
logging.basicConfig(level=LOG_LEVEL)

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
