# telegram-bot/settings.py

# --------------------------------------------------------------
#
# Все параметры ниже должны быть переназначены в local_settings.py
#

# Токен бота в телеграме
#
TOKEN = 'secret'

# Способ запуска, 'poll' или 'webhook'
#
START_MODE = 'poll'

# Webhook параметры
#
WEBHOOK_HOST = 'https://your.domain'
WEBHOOK_PATH = '/path/to/api'

WEBAPP_HOST = '127.0.0.1'
WEBAPP_PORT = 3001

# --------------------------------------------------------------
#

try:
    from local_settings import *
except ModuleNotFoundError:
    pass

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
