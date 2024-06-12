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
LOG_CONFIG = dict(
    level = logging.INFO,

    # Могут быть и другие параметры для журнала,
    # например, для журнала в файл:
    #
    # filename='/path/to/file.log',
    # filemode='a',
    # format='%(asctime)s %(levelname)s %(message)s',
    # datefmt='%d.%m.%y %H:%M:%S',
    #
    #
)

LOG_CONFIG = dict(
    level = logging.INFO,

    # Могут быть и другие параметры для журнала,
    # например, для ротируемого журнала в файл
    #
    #handlers=[
        #RotatingFileHandler(
            #filename='/path/to/bot.log',
            #maxBytes=10*1024*1024,
            #backupCount=10,
    #)],
    #format='%(asctime)s %(levelname)s %(message)s',
    #datefmt='%d.%m.%y %H:%M:%S',

    # Тогда надо переопределить LOG_CONFIG в
    # local_settings.py.
    # И если применяется RotatingFileHandler,
    # то определить его:
    # from logging.handlers import RotatingFileHandler
)


# secs
#
HTTP_TIMEOUT = 60

# URL апи, без завершающей/, :
#
API_HOST = 'https://api.blagoroda.org'

# - домен, прописанный в боте
# - там находятся ресурсы: <FRONTEND_HOST>/res/telegram-bot/*.txt
#
FRONTEND_HOST = 'https://blagoroda.org'
FRONTEND_HOST_TITLE = 'БлагоРода'

# Карта всех пользователей с кластеризацией
#
MAP_HOST = 'https://map.blagoroda.org'

# Ссылка на пространство доверия
#
GRAPH_HOST = 'https://blagoroda.org'

# Ссылка на фронте, которая будет открываться там под авторизованным
# пользователем:
# <FRONTEND_HOST><FRONTEND_AUTH_PATH>?redirect_path=<frontend_path>
#
FRONTEND_AUTH_PATH = '/auth/telegram/'

SHORT_ID_LINK = 'blagoroda.org/t/%s'

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

OFFER_MAX_NUM_ANSWERS = 9

# Подсказки в сообщении о необходимости авторизации для доменов
#
AUTH_PROMPT_FOR_DOMAIN = {
    'blagoroda.org': 'Для доступа к пространству Доверия требуется авторизация',
}

# Страница голосования по видео
#
VOTE_URL = 'https://6jlarogap.github.io/razum/'

# Параметры для redis кэша, где хранится временно:
#   -   media_group_id сообщений с кучей фоток.
#       Такое пересылаемое сообщение в бот состоит из нескольких
#       сообщений, но показать карточку автора пересылаемоего сообщения
#       надо лишь раз. Посему в кэше redis ставится запись с ключом:
#           REDIS_MEDIA_GROUP_PREFIX +
#           message.media_group_id
#       Запись имеет время жизни REDIS_MEDIA_GROUP_TTL секунд,
#       после чего redis этот мусор удаляет.
#       (
#           При пересылке в бот того же сообщения
#           с кучей картинок у этого сообщения будет другой
#           media_group_id, нежели у такого же предыдущего
#       )
#       Если при поступлении очередного перенаправленного сообщения
#       в бот запись в redis, соответствующая media_group_id,
#       существует, то карточка автора пересылаемоего сообщения
#       не показывается. Иначе ставится та запись в redis кэше
#       и бот выводит карточку автора пересылаемоего сообщения.
#   -   Последний юзер, отправивший сообщение в группу.
#       Вносится бессрочная запись:
#           REDIS_LAST_USERIN_GROUP_PREFIX +
#           group_chat_id  + REDIS_KEY_SEP +
#           message.message_thread_id
#       со значением telegram user_id пользователя,
#       отправившего сообщение
#   -   Карточка, выданная после сообщения пользователя в группе:
#           REDIS_CARD_IN_GROUP_PREFIX + REDIS_KEY_SEP +
#           время (int(time.time()))  + REDIS_KEY_SEP +
#           group_chat_id + REDIS_KEY_SEP +
#           message.message_id
#       с любым значением
#
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
REDIS_MEDIA_GROUP_PREFIX = 'media_group_id_'
REDIS_MEDIA_GROUP_TTL = 60
REDIS_LAST_USERIN_GROUP_PREFIX = 'last_user_in_group_'
REDIS_CARD_IN_GROUP_PREFIX = 'card_in_group'
REDIS_KEY_SEP = '~'

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
#         auth=dict(
#             client_id='client_id',
#             client_secret='client_secret',
#             refresh_token='refresh_token'
#         ),
#         message_thread_id=-1234567890,
# )}

# Каталог для временных файлов. Должен существовать
#
DIR_TMP = './tmp'

try:
    from local_settings import *
except ModuleNotFoundError:
    pass
logging.basicConfig(**LOG_CONFIG)

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
