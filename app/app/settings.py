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

    'debug_toolbar',

    'rest_framework',
    'rest_framework.authtoken',

    'contact',
    'users',
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
        'rest_framework.renderers.BrowsableAPIRenderer',
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

# --------------------------------------------------------------------------

# Время начала наблюдений (приема симптомов ощущений):
# начало первого лунного дня, в котором появились
# симптомы
#
TIME_START_GET_SYMPTOMS = 1586459348

# Средняя длительность лунного месяца
#
MOON_MONTH_LONG = 2551442.82048     # 29.5305882 * 86400

# Приводить google photos к такому размеру
#
GOOGLE_PHOTO_SIZE = 200

# Давать ли доступ к Django Admin,
# по умолчанию - не давать
#
ADMIN_ENABLED = False

# С ложным ключом отправки уведомления не будет
#
FCM_SERVER_KEY = None

# Глубина прохода по графу связей рекурсивно
#
CONNECTIONS_LEVEL = 2

# ------------------------------------------------
try:
    from app.local_settings import *
except ModuleNotFoundError:
    pass
