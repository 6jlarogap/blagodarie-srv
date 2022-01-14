# telegram-bot/settings.py

# --------------------------------------------------------------
#
# Все параметры ниже должны быть переназначены в local_settings.py
#

# Токен бота в телеграме
#
TOKEN = 'secret'

# Способ запуска, 'poll' или 'webhook'.
# На сервере: webhook. В консоли разработчика: poll
#
START_MODE = 'webhook'

# Webhook параметры
#
WEBHOOK_HOST = 'https://bot-dev.blagodarie.org'
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
API_HOST = 'https://api.dev.blagodarie.org'
FRONTEND_HOST = 'https://dev.blagodarie.org'
FRONTEND_HOST_TITLE = 'БлагоДари.РФ (dev)'

# --------------------------------------------------------------
#

# Выбираем из фото пользователей не меньше такого:
#
PHOTO_MAX_SIZE = 320 * 320

try:
    from local_settings import *
except ModuleNotFoundError:
    pass

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
