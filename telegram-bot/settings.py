# telegram-bot/settings.py

# --------------------------------------------------------------
#
# Все параметры ниже могут, а некоторые даже должны быть переназначены в settings_local.py
#

DEBUG = False

# Токен бота в телеграме
#
TOKEN = 'secret'

# Webhook параметры
#
WEBHOOK_HOST = 'https://bot.meetgame.us.to'
WEBHOOK_PATH = '/'
WEBAPP_HOST = '127.0.0.1'
WEBAPP_PORT = 3001

import logging
LOG_CONFIG = dict(
    level = logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(message)s',
    datefmt='%d.%m.%y %H:%M:%S',

    # Могут быть и другие параметры для журнала,
    # например, для ротируемого журнала в файл
    # Тогда надо переопределить параметры LOG_CONFIG['handlers'] в
    # settings_local.py, например:
    # from logging.handlers import RotatingFileHandler
    # from settings import LOG_CONFIG
    # LOG_CONFIG['handlers'] = [
    #         StreamHandler(),
    #         RotatingFileHandler(
    #             filename='/home/user/tg-bot-log/tg-bot.log',
    #             maxBytes=10*1024*1024,
    #             backupCount=10,
    # )]
)


# secs
#
HTTP_TIMEOUT = 60

# Сообщение из многих валит одно за другим.
# Чтоб все успели отработать, пока не погаснет состояние:
#
MULTI_MESSAGE_TIMEOUT = 3

# URL апи, без завершающей/, :
#
API_HOST = 'https://api.meetgame.us.to'

# - домен, прописанный в боте
#
FRONTEND_HOST = 'https://meetgame.us.to'

# Карта участников знакомств
#
MEET_HOST = FRONTEND_HOST

# Карта всех пользователей с кластеризацией.
# При других get параметрах карта предложений, доверий юзера и др.
#
MAP_HOST = 'https://map.meetgame.us.to'

# Ссылка на пространство доверия
# И там находятся ресурсы: <GRAPH_HOST>/res/telegram-bot/*.txt
#
GRAPH_HOST = 'https://g.meetgame.us.to'

# Ссылка на фронте, которая будет открываться там под авторизованным
# пользователем:
# <FRONTEND_HOST><FRONTEND_AUTH_PATH>?redirect_path=<frontend_path>
#
FRONTEND_AUTH_PATH = '/auth/telegram/'

SHORT_ID_LINK = 'meetgame.us.to/t/%s'

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

OFFER_MAX_NUM_ANSWERS = 9

# Подсказки в сообщении о необходимости авторизации для доменов
#
AUTH_PROMPT_FOR_DOMAIN = {
    'meetgame.us.to': 'Для доступа к пространству Доверия требуется авторизация',
}

# Страница голосования по видео
#
VOTE_URL = 'https://6jlarogap.github.io/razum/'

REDIS_CONNECT =dict(
    # Параметры инициализации redis connection,
    # те же, что в redis.Redis()
    # https://redis-py.readthedocs.io/en/stable/connections.html
    #
    host='127.0.0.1',
    port=6379,
    db=2,
    decode_responses=True,
)

# Время, после которого можно еще раз ставить симпатию
#
REDIS_SET_NEXT_SYMPA_WAIT = 3600

# Ид групп, в которые шлём карточки после сообщений участников, с параметрами.
# Например, в группе с таким ид показывать карточки после сообщений юзеров
# в топиках с message_thread_ids
# и хранить карточки keep_hours часов не не больше 48 часов (иначе telegram не удалит)!:
#   GROUPS_WITH_CARDS = {
#     -1001842039923: dict(keep_hours=24, message_thread_ids=(52,)),
#   }
# При bool(keep_hours) == False или при отсутствии keep_hours данные в redis для
# последующего удаления карточек не сохраняются и карточки не удаляются
#
GROUPS_WITH_CARDS = {}

BOT_CHAT = dict(href='https://t.me/+dpxYzCiAqN41MDEy', caption='Чат бота Доверия')

# Ид групп, в которых есть топик, куда кладут видео для их загрузки в youtube.
#
GROUPS_WITH_YOUTUBE_UPLOAD = {}
#
# Например:
# GROUPS_WITH_YOUTUBE_UPLOAD = {
#     # sevGroupTest
#     -1001842039923: dict(
#         auth_data=dict(
#             client_id='client_id',
#             client_secret='client_secret',
#             refresh_token='refresh_token'
#         ),
#         message_thread_id=-1234567890,
#         url_group='https://t.me/+LcTcCWzvjUJmMTMy'
# )}

# Каталог для временных файлов. Должен существовать
#
DIR_TMP = './tmp'

# Параметры времени запуска задач
#
SCHEDULE_CRON = dict(
    # задача:
    cron_remove_cards_in_group = dict(
        # время запуска
        day_of_week='mon-sun', hour=0, minute=1,
    )
)


# Запуск через Telegram API Server,
# например, 'http://localhost:8081'
#
LOCAL_SERVER = None

try:
    from settings_local import *
except ModuleNotFoundError:
    pass

logging.basicConfig(**LOG_CONFIG)

