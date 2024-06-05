DEBUG = True

TOKEN = '1782888266:AAFcXQcU4HzMG4ZBEiADUZWtnNJFxVNSQ2o'

START_MODE = 'poll'

WEBHOOK_HOST = 'https://sev12t.bsuir.by'
WEBHOOK_PATH = '/'

WEBAPP_HOST = '172.16.0.12'
WEBAPP_PORT = 3001

API_HOST = 'http://api.blagoroda.bsuir.by'
FRONTEND_HOST = 'https://blagoroda.bsuir.by'

MAP_HOST = 'http://map.blagoroda.bsuir.by'
GRAPH_HOST = 'http://blagoroda.bsuir.by'

TRIP_DATA = dict(
    # chat_id=-1001806912655,
    chat_id=-1001603768888,
    invite_link='https://t.me/+JOhceI_DTTcxMjky',
    text_with_invite_link='Хотите путешествовать? Если Да, то <a href="%(invite_link)s">жмите</a>',
    text_agreement='Наши условия суровы. Согласны с условиями?',
)

# Е.Супрун, В.Дрозд
#
# BOT_ADMINS = (1109405488, 1539785255,)

# Eugene Suprun, Евгений Супрун
#
BOT_ADMINS = (5234621536,)

import logging
from logging.handlers import RotatingFileHandler
from logging import StreamHandler
LOG_CONFIG = dict(
    level = logging.INFO,

    handlers=[
        StreamHandler(),
        RotatingFileHandler(
            filename='/home/sev/musor/tg-bot-log/tg-bot.log',
            maxBytes=10*1024*1024,
            backupCount=10,
    )],
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%d.%m.%y %H:%M:%S',
)

AUTH_PROMPT_FOR_DOMAIN = {
    'blagoroda.bsuir.by': 'Для доступа к пространству Доверия требуется авторизация',
}

GROUPS_WITH_CARDS = {
    # Роза ветров
    -1002067125836: dict(keep_hours=24, message_thread_ids=('topic_messages',)),
    # sevGroupTest
    -1001842039923: dict(keep_hours=None, message_thread_ids=('topic_messages',)),
    # sevGroup
    -1001875308007: dict(keep_hours=24, message_thread_ids=(287,)),
}
