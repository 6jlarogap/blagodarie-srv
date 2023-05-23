"""
Django settings for app project.

Generated by 'django-admin startproject' using Django 2.2.4.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""

import sys, os, datetime

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'blagodarie', 
        'USER': 'postgres',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    },
}

TIME_ZONE = 'Europe/Moscow'
LANGUAGE_CODE = 'ru'

USE_I18N = True
USE_L10N = True
USE_TZ = False

DATE_INPUT_FORMATS = (
    '%d.%m.%Y', '%Y-%m-%d',
)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

MEDIA_ROOT = os.path.join(ROOT_DIR, 'media/')
MEDIA_URL = '/media/'

# Где находится apk, относительно MEDIA_ROOT
#
APK_MEDIA_PATH = "download/apk"

STATIC_ROOT = os.path.join(ROOT_DIR, 'static/')
STATIC_URL = '/static/'

STATICFILES_DIRS = (
    os.path.join(ROOT_DIR, 'static_src/'),
)

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',

    'debug_toolbar',

    'rest_framework',
    'rest_framework.authtoken',
    'restthumbnails',

    'contact',
    'users',
    'wote',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    ### 'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

ROOT_URLCONF = 'app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(ROOT_DIR, 'templates'), ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'app.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = []

INTERNAL_IPS = ['127.0.0.1',]

# REST framework
REST_FRAMEWORK = {

    'UNICODE_JSON': True,

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
    ),
}


# CORS:
#
# Переопределить в False в local_settings.py на production server
#
CORS_ORIGIN_ALLOW_ALL = True
#
# Задать в local_settings.py на production server:
#
# CORS_ORIGIN_REGEX_WHITELIST = (r'^(https?://)?(\w+\.)?EXAMPLE\.\COM$', )
#
# Может быть authentication cookies, при доступе к апи из множества
# доменов *.EXAMPLE.COM, посему:
#
CORS_ALLOW_CREDENTIALS = True

# Webhook ключ от github репозитория приложения Благодария.
# Webhook обеспечивает при каждом push в репозиторий
# отправку запроса для получения данных о версии
# мобильного приложения.
#
# Где можно скачать последнюю версию мобильного приложения
#
APK_URL = 'https://github.com/6jlarogap/blagodarie/raw/master/app/latest/blagodarie-latest.apk'

# Где можно получить данные о последней версии мобильного приложения
#
APK_OPTIONS_URL = 'https://github.com/6jlarogap/blagodarie/raw/master/app/latest/output.json'

# Куда считываем данные о последней версии мобильного приложения,
# относительно MEDIA_ROOT
#
APK_OPTIONS_DOWNLOAD = 'download/apk-output/output.json'

# Хранение апк в google play
#
GOOGLE_PLAY_URL = 'https://play.google.com/store/apps/details?id=org.blagodarie'

# Хранится ли апк в google play
#
GOOGLE_PLAY_UPDATE = False

GITHUB_WEBHOOK_SECRET = 'secret'

# Для получения версии Rating apk ------------------------------------------
#

# Вветка репозитория апк, с которой работает это апи
#
RATING_APK_BRANCH = 'master'

# Ветки версии апк Rating, работающего с этим апи,
# регулярное выражение выбора. Дело в том, что
# github не отдает webhooks по веткам, так что
# запрос на обновление dev версии может прийти
# в апи, работающим с master (production) apk
#
RATING_APK_BRANCHES = r'master|dev'

# Webhook ключ от github репозитория приложения Rating.
# Webhook обеспечивает при каждом push в репозиторий
# отправку запроса для получения данных о версии
# мобильного приложения.
#
RATING_GITHUB_WEBHOOK_SECRET = 'secret'

# Откуда считываем данные о последней версии мобильного приложения Rating,
# относительно MEDIA_ROOT
# %(branch)s - RATING_APK_BRANCHES (одно из, какой придет в запрос от GitHub)
#
RATING_APK_OPTIONS_URL = 'https://raw.githubusercontent.com/6jlarogap/blagodari/%(branch)s/app/%(build)s/output-metadata.json'

# Куда считываем данные о последней версии мобильного приложения Rating,
# относительно MEDIA_ROOT
# %(branch)s - RATING_APK_BRANCHES (одно из, какой придет в запрос от GitHub)
# %(build)s  - 'debug', если RATING_APK_BRANCH == 'dev', иначе 'release'
#
# А также:
#
# Откуда берем данные о последней версии мобильного приложения Rating,
# при запросе от него, какая последняя версия.
# Тогда %(branch)s - RATING_APK_BRANCH
#
RATING_APK_OPTIONS_DOWNLOAD = 'download/rating-apk-output/%(branch)s/output-metadata.json'

# Откуда брать апк, если из файла на сервере
# %(branch)s - RATING_APK_BRANCH
# %(build)s  - 'debug', если RATING_APK_BRANCH == 'dev', иначе 'release'
# %(apk_fname)s - имя файла апк, полученного из считанного из RATING_APK_OPTIONS_URL
#
RATING_APK_URL = 'https://raw.githubusercontent.com/6jlarogap/blagodari/%(branch)s/app/%(build)s/%(apk_fname)s'

# Хранится ли апк Rating в google play
#
RATING_GOOGLE_PLAY_UPDATE = False

# Обновление frontend из github webhook ------------------------------------

FRONTEND_UPDATE_SCRIPT = {
    'master': '/home/www-data/webhook-scripts/blagodari.rf/master/update.sh',
    'dev-site': '/home/www-data/webhook-scripts/blagodari.rf/dev-site/update.sh',
}
FRONTEND_GITHUB_WEBHOOK_SECRET = 'secret'

# --------------------------------------------------------------------------

# Время начала наблюдений (приема симптомов ощущений):
# начало первого лунного дня, в котором появились
# симптомы
#
TIME_START_GET_SYMPTOMS = 1586459348

# Средняя длительность лунного месяца
#
MOON_MONTH_LONG = 2551442.82048     # 29.5305882 * 86400

# Давать ли доступ к Django Admin,
# по умолчанию - не давать
#
ADMIN_ENABLED = False

# Максимальная глубина прохода по графу связей рекурсивно
#
# При "простой" рекурсии, от одного к другому или ко многим
#
MAX_RECURSION_DEPTH = 100
#
# При рекурсии от одного к другому или ко многим,
# например, при выборке из группы
#
#   максимальная глубина рекурсии
#
MAX_RECURSION_DEPTH_IN_GROUP = 10
#
#   максимальное число выборки из группы для очередной страницы
#
MAX_RECURSION_COUNT_IN_GROUP = 50

# Сколько последних пользователей показываем на главной странице.
# Или сколько пользователй по умолчанию на странице.
#
PAGINATE_USERS_COUNT = 25

# ------------------------------------------------

# Для телеграм авторизации. Неправильный или отсутсвующий токен
# не позволит авторизацию через телеграм
#
# Должен быть задан в local_settings.py
#
TELEGRAM_BOT_TOKEN = None

# Данные для регистрации от телеграма,
# старше этого срока, в секундах, считаются устаревшими
#
TELEGRAM_AUTH_DATA_OUTDATED = 3600

# В процессе отладки нехорошо мучать других пользователей
# сообщениями. Это можно в local_settings запретить.
#
SEND_TO_TELEGRAM = True

# ------------------------------------------------

# front-end stuff

# Адрес front end. Вычисляется из url запроса к апи.
# Например, если запрос к апи пришел по
# https://(api.blagodarie.org), то будем считать,
# что frontend находится по: https://blagodarie.org.
# При этом проверяется, чтобы хост апи,
# например, api.blagodarie.org, начинался с 'api'
#
# Для oauth авторизации необходимо, чтобы frontend
# находился там же или доменом выше, чем backend.
#
# Вместе с тем оставляем возможность задать
# FRONTEND_ROOT вручную
#
FRONTEND_ROOT = ''

# Относительный путь к settings.FRONTEND_ROOT,
# куда ouauth2 callback возвращает пользователя
# на frontend.
#
REDIRECT_FROM_CALLBACK = 'oauth-landing'

# Рисуем графики в формате '3d-force-graph' здесь
#
GRAPH_URL = 'https://graph.blagoroda.org'

# ------------------------------------------------

# Это надо полностью переписать в local_settings.py:
#
OAUTH_PROVIDERS = {
    'yandex': {
        'client_id': 'not_secret',
        'client_secret': 'secret',
    },
    'vk': {
        'client_id': 'not_secret',
        'client_secret': 'secret',
    },
    'odnoklassniki': {
        'client_id': 'not_secret',
        'client_secret': 'secret',
    },
}

# From Django 3.2 this is BigAutofield
# To avoid unnecessary migrations in future:
#
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# ФОТО --------

# Приводить google photos к такому размеру
#
GOOGLE_PHOTO_SIZE = 200

# Мб. Если 0 или None, без ограничений.
#
PHOTO_MAX_SIZE = 10

# %, от 0 до 100. Если 100, 0, None, фото не урезаются
#
PHOTO_QUALITY = 30
#
# Какого минимального размера фото урезаются фото до PHOTO_QUALITY?
# Минимальный размер здесь ширина x высота в пикселях
# Совсем малопиксельные снимки зачем урезать?
# Урезать любого размера: <= 0 или None
#
PHOTO_QUALITY_MIN_SIZE = 800 * 600
#
# -------------

# Опрос (Offer или Poll), карта номер ответа -> цвет
# Цвет -- что-то из:
#   - rgb<6-hex-digits>
#   - <WellKnowColor>:
#       из PIL.ImageColor.colormap,
#       https://github.com/python-pillow/Pillow/blob/main/src/PIL/ImageColor.py,
#       который наверняка соответствует: https://www.w3.org/TR/css-color-3/
#
OFFER_ANSWER_COLOR_MAP = [
    # Нулевой ответ. Это не ответ, но признак того, что юзер опрос offer видел,
    # и/или отозвал свой голос (опросы poll и OFFER):
    #
    'white',            #  0
    'red',              #  1
    'purple',           #  2
    'orange',           #  3
    'yellow',           #  4
    'lime',             #  5
    'green',            #  6
    'aqua',             #  7
    'teal',             #  8
    'blue',             #  9
    'navy',             # 10
    'black',            # 11
]
#
# -------------

# THUMBNAILS
#
THUMBNAILS_FILE_SIGNATURE = '%(source)s/%(size)s~%(method)s~%(secret)s.%(extension)s'
THUMBNAILS_STORAGE_BASE_PATH = '/thumb/'
THUMBNAILS_PROXY_BASE_URL = '/thumb/'
# возможные длины и высоты:
THUMBNAILS_ALLOWED_SIZE_RANGE = dict(min=20, max=2000)

# Минимальный размер сообщения для полнотекстового поиска из бота:
#
MIN_LEN_SEARCHED_TEXT = 3

DATA_UPLOAD_MAX_MEMORY_SIZE = 14 * 1024 * 1024

# Log errors. Установить следующее в прод версии в local_settings.py:
#
ADMINS = (
    # ("John Smith", "jsmith@org.com",)
)
EMAIL_HOST = 'localhost'
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
SERVER_EMAIL = 'root@localhost'

EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False

# Параметры для redis кэша, где храним временные токены
#   -   token: url
#   -   token: авторизационная кука
#
REDIS_TOKEN_CONNECT =dict(
    # Параметры инициализации redis connection,
    # те же, что в redis.Redis()
    # https://redis-py.readthedocs.io/en/stable/connections.html
    #
    host='127.0.0.1',
    port=6379,
    db=2,
    decode_responses=True,
)
# Сколько времени хранить url token, в секундах.
# Ссылку с этим токеном человек может долго думать,
# а то и долго копировать, вставлять в телеграм клиент
#
TOKEN_URL_EXPIRE = 300

# Сколько времени хранить token с авторизационной кукой, в секундах.
# Он не долго используется. Его формирует авторизация в телеграме,
# /api/auth/telegram, здесь, в апи, и эта авторизация сразу делает
# редирект на фронт с параметром с этим токеном. То есть задержка
# в использовании токена связана только с Интернет коммуникациями.
#
TOKEN_AUTHDATA_EXPIRE = 30

from app.logging import skip_ioerror_post
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        },
        'skip_ioerror_posts': {
            '()': 'django.utils.log.CallbackFilter',
            'callback': skip_ioerror_post,
        },
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': [
                'require_debug_false',
                'skip_ioerror_posts',
             ],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
    }
}

try:
    from app.local_settings import *
except ModuleNotFoundError:
    pass

# MEDIA_ROOT может измениться в local_settings
#
THUMBNAILS_STORAGE_ROOT = os.path.join(MEDIA_ROOT, 'thumbnails')

if DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    )
