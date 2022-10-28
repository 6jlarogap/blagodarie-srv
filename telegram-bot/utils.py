import base64, re, datetime
from urllib.parse import urlencode
from uuid import UUID

from aiogram.types.login_url import LoginUrl
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.input_file import InputFile
from aiogram.utils.parts import safe_split_text
from aiogram.utils.exceptions import BadRequest
import aiohttp

import settings

from settings import logging

TIMEOUT = aiohttp.ClientTimeout(total=settings.HTTP_TIMEOUT)

class OperationType(object):
    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_TRUST = 4
    TRUST_AND_THANK = 5
    FATHER = 6
    NOT_PARENT = 7
    MOTHER = 8
    SET_FATHER = 9
    SET_MOTHER = 10

    CALLBACK_DATA_TEMPLATE = (
        '%(keyboard_type)s%(sep)s'
        '%(operation)s%(sep)s'
        '%(user_to_uuid_stripped)s%(sep)s'
        '%(message_to_forward_id)s%(sep)s'
        '%(group_id)s%(sep)s'
    )

    @classmethod
    def relation_text(cls, is_trust):
        if is_trust is None:
            result = 'не знакомы'
        elif is_trust:
            result = 'доверие'
        else:
            result = 'недоверие'
        return result

class KeyboardType(object):
    """
    Варианты клавиатур и служебный символ для call back data из кнопок клавиатур
    """
    # Багодарность, доверие, недоверие...
    #
    TRUST_THANK_VER_2 = 2

    # Благодарность, доверие, недоверие...
    #
    LOCATION = 3

    # Возможности
    #
    ABILITY = 4

    # Потребности
    #
    WISH = 5

    # Клавиша Отмена
    #
    CANCEL_ANY = 6

    # Получить фото родственника
    #
    PHOTO = 7

    # Удалить фото родственника
    #
    PHOTO_REMOVE = 8

    # Удалить фото родственника, подтверждено
    #
    PHOTO_REMOVE_CONFIRMED = 9

    # Задать папу, маму
    #
    FATHER = 10
    MOTHER = 11

    # Сменить владельца у owned user
    #
    CHANGE_OWNER = 12

    # Сделать нового папу, маму
    #
    NEW_FATHER = 13
    NEW_MOTHER = 14

    IOF = 15

    OTHER = 16
    OTHER_MALE = 17
    OTHER_FEMALE = 18
    OTHER_DOB_UNKNOWN = 19
    OTHER_DOD_UNKNOWN = 20

    # Внести ребёнка
    #
    CHILD = 21

    # Ребёнок вносится как новый
    #
    NEW_CHILD = 22

    # У ребёнка родитель папа или мама?
    #
    FATHER_OF_CHILD = 24
    MOTHER_OF_CHILD = 25

    SEND_MESSAGE = 26

    CHANGE_OWNER_CONFIRM = 27

    KEYS = 28

    SHOW_MESSAGES = 29

    # Согласие от входа в канал
    #
    CHAT_JOIN_ACCEPT = 30
    CHAT_JOIN_REFUSE = 31

    TRIP_NEW_LOCATION = 32
    TRIP_OLD_LOCATION = 33

    # Разделитель данных в call back data
    #
    SEP = '~'

class Misc(object):
    """
    Различные функции, сообщения, константы
    """

    PROMPT_SEARCH_TEXT_TOO_SHORT = 'Минимальное число символов в тексте для поиска: %s\n' % settings.MIN_LEN_SEARCHED_TEXT
    PROMPT_SEARCH_PHRASE_TOO_SHORT = 'Недостаточно для поиска: короткие слова или текст вообще без слов и т.п.'
    PROMPT_NOTHING_FOUND = 'Ничего не найдено - попробуйте другие слова'

    MSG_ERROR_API = 'Ошибка доступа к данным'
    MSG_ERROR_TEXT_ONLY = 'Принимается только текст'
    MSG_REPEATE_PLEASE = 'Повторите, пожалуйста!'

    PROMPT_ABILITY = 'Отправьте мне <u>текст</u> с <b>возможностями</b>'
    PROMPT_WISH = 'Отправьте мне <u>текст</u> с <b>потребностями</b>'

    PROMPT_PHOTO = 'Отправьте мне <b>фото</b>, не более %s Мб размером.' % settings.DOWNLOAD_PHOTO_MAX_SIZE
    PROMPT_PHOTO_REMOVE = "Нажмите 'Удалить' для удаления имеющегося фото."

    PROMPT_NEW_IOF = "Укажите имя отчество и фамилию - в одной строке, например: 'Иван Иванович Иванов'"
    PROMPT_EXISTING_IOF = "Укажите для\n\n%(name)s\n\nдругие имя отчество и фамилию - в одной строке, например: 'Иван Иванович Иванов'"

    PROMPT_PAPA_MAMA = (
        '<b>%(name)s</b>.\n'
        'Отправьте мне ссылку на профиль %(his_her)s %(papy_or_mamy)s '
        'вида t.me/%(bot_data_username)s?start=...\n\n'
        'Или нажмите <u>%(novy_novaya)s</u> для ввода нового родственника, '
        'который станет %(his_her)s %(papoy_or_mamoy)s'
    )
    PROMPT_NEW_PAPA_MAMA = (
        "Укажите имя отчество и фамилию человека - в одной строке, например: '%(fio_pama_mama)s'. "
        '%(on_a)s <u>добавится</u> к вашим родственникам и станет %(papoy_or_mamoy)s для:\n'
        '%(name)s.\n'
    )

    PROMPT_GENDER = (
        'Будет предложено их изменить.\n\n'
        'Сначала укажите %(his_her)s пол:'
    )
    PROMPT_DATE_FORMAT = 'в формате ДД.ММ.ГГГГ или ММ.ГГГГ или ГГГГ'
    PROMPT_DOB =    '%(name)s.\n\n' + \
                    'Укажите %(his_her)s день рождения ' + PROMPT_DATE_FORMAT
    PROMPT_DOD =    '%(name)s.\n\n' + \
                    'Укажите %(his_her)s день смерти ' + PROMPT_DATE_FORMAT

    PROMPT_CHILD = (
        '<b>%(name)s</b>.\n'
        'Отправьте мне ссылку на профиль %(his_her)s сына (дочери) '
        'вида t.me/%(bot_data_username)s?start=...\n\n'
        'Или нажмите <u>Новый ребёнок</u> для ввода нового родственника, '
        'который станет %(his_her)s сыном (дочерью)'
    )

    PROMPT_PAPA_MAMA_OF_CHILD = (
        'Укажите пол %(name)s'
    )
    PROMPT_NEW_CHILD = (
        'Укажите имя отчество и фамилию человека - в одной строке, '
        "например: 'Иван Иванович Иванов'. "
        'Он (она) <u>добавится</u> к вашим родственникам и станет сыном (дочерью) для:\n'
        '%(name)s.\n'
    )

    PROMPT_PAPA_MAMA_SET = (
                '%(iof_to)s\n'
                'отмечен%(_a_)s как %(papa_or_mama)s для:\n'
                '%(iof_from)s\n'
    )

    PROMPT_CHANGE_OWNER_WARN = (
        '<b>Важно!</b> После смены  владельца Вы не сможете вернуть себе владение. '
        'Это может сделать для Вас только новый владелец'
    )

    PROMPT_CHANGE_OWNER = (
        '<b>%(iof)s</b>\n'
        'Отправьте мне ссылку на профиль нового %(his_her)s  владельца вида '
        't.me/%(bot_data_username)s?start=... или откажитесь, нажав "Отмена"\n'
        '\n'
    ) + PROMPT_CHANGE_OWNER_WARN

    PROMPT_CHANGE_OWNER_SUCCESS = (
        '%(iof_to)s установлен владельцем для профиля %(iof_from)s'
    )

    PROMPT_CHANGE_OWNER_CONFIRM = (
        '%(iof_to)s станет владельцем профиля %(iof_from)s. Продолжить?\n'
        '\n'
    ) + PROMPT_CHANGE_OWNER_WARN + ': %(iof_to)s'

    PROMPT_MESSAGE_TO_CHANGED_OWNER = (
        '%(iof_sender)s передал Вам владение профилем %(iof_from)s'
    )

    PROMPT_KEYS = (
        '<b>%(name)s</b>.\n'
        'Напишите мне %(his_her)s контакты по одному в каждой строке'
    )

    PROMPT_ENTER_SEARCH_STRING = 'Введите строку поиска'
    PROMPT_QUERY = dict(
        query_ability='<b>Поиск по возможностям</b>\n' + PROMPT_ENTER_SEARCH_STRING,
        query_wish='<b>Поиск по потребностям</b>\n' + PROMPT_ENTER_SEARCH_STRING,
        query_person='<b>Поиск людей</b>\n' + PROMPT_ENTER_SEARCH_STRING,
    )

    MSG_ERROR_PHOTO_ONLY = 'Ожидается <b>фото</b>. Не более %s Мб размером.' %  settings.DOWNLOAD_PHOTO_MAX_SIZE

    UUID_PATTERN = re.compile(r'[\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12}', re.IGNORECASE)

    CALLBACK_DATA_UUID_TEMPLATE = '%(keyboard_type)s%(sep)s%(uuid)s%(sep)s'

    MSG_ERROR_UUID_NOT_VALID = 'Не найден или негодный ид в сообщении'

    FORMAT_DATE = '%d.%m.%Y'
    FORMAT_TIME = '%H:%M:%S'

    PROMPT_CANCEL_LOCATION = 'Отмена'
    PROMPT_LOCATION = 'Отправить местоположение'

    @classmethod
    def datetime_string(cls, timestamp, with_timezone=True):
        dt = datetime.datetime.fromtimestamp(timestamp)
        result = dt.strftime(cls.FORMAT_DATE + ' ' + cls.FORMAT_TIME)
        if with_timezone:
            str_tz = dt.strftime('%Z')
            if not str_tz:
                str_tz = dt.astimezone().tzname()
            result += ' ' + str_tz
        return result

    @classmethod
    def invalid_search_text(cls):
        return (
            ('Поиск участников %s по:\n' % settings.FRONTEND_HOST_TITLE) + \
            '\n'
            '- @имени участника в телеграме,\n'
            '- фамилии, имени, возможностям, потребностям.\n'
            '\n' + \
            ('Минимальное число символов в тексте для поиска: %s\n' % settings.MIN_LEN_SEARCHED_TEXT) + \
            '\n'
            'Также можно переслать сюда сообщение от любого пользователя телеграма\n'
            '\n'
            'Дальнейшие действия будут Вам предложены\n'
        )


    @classmethod
    def get_html_a(cls, href, text):
        return '<a href="%s">%s</a>' % (href, text)


    @classmethod
    def help_text(cls):
        return (
            'Инструкция:\n'
            '. заполните Ваши возможности, потребности и местоположение;\n'
            '. заполните своё родовое дерево;\n'
            '. напишите мне любой текст для поиска;\n'
            '. напишите мне @имя или перешлите сообщение - я покажу репутацию его отправителя;\n'
            '. добавьте меня в любую группу - и я буду показывать репутацию каждого кто отправляет в неё сообщения!\n'
            '\n'
            'Мой программный код: https://github.com/6jlarogap/blagodarie-srv/tree/master/telegram-bot\n'
        )

    @classmethod
    def start_text(cls):
        return (
'''Правила:
. всё что Вы отправили этому боту - является опубликованным Вами самими;
. заполните данные своего профиля - Имя Отчество Фамилию, фотографию крупно лица - собачки и цветочки не подойдут - Ваше лицо - лицо РОДа!, дату рождения, контакты, возможности, потребности и примерное или точное местоположение;
. заполните профили папы, мамы, детей и известных вам живых и умерших РОДных;
. пригласите известных вам РОДственников и друзей - особенно разделённых - поРОДниться - занять их места в РОДу! 
. переходите на канал РОД для вопросов, предложений и совместных действий https://t.me/+Zi6WsvPvUeFiZGZi
. напишите мне любой текст для поиска РОДных по ИОФ, возможностям и потребностям;
. напишите мне @имя или перешлите сообщение любого пользователя телеграмма - я покажу его профиль;
. добавьте меня в свои группы или каналы - я буду показывать профиль каждого кто пишет в них сообщения.

Мой программный код: https://github.com/6jlarogap/blagodarie-srv/tree/master/telegram-bot'''
        )

    @classmethod
    async def get_user_photo(cls, bot, user):
        """
        Получить фото пользователя, base64-строку, фото размером не больше settings.PHOTO_MAX_SIZE, если возможно
        """
        result = None
        if not user:
            return result

        try:
            photos_output = await user.get_profile_photos()
        except:
            return result

        # Вытащить отсюда фото размером не больше settings.PHOTO_MAX_SIZE
        # Если несколько фоток, берм 1-е
        #[
        #('total_count', 1),
        #('photos', 
            #[
                #[
                #{'file_id': 'xxxAgACAgIAAxUAAWHMS13fLk09JXvGPzvJugABH-CbPQACh7QxG9OhYUv54uiD8-vioQEAAwIAA2EAAyME',
                #'file_unique_id': 'AQADh7QxG9OhYUsAAQ', 'file_size': 8377, 'width': 160, 'height': 160},
                #{'file_id': 'AgACAgIAAxUAAWHMS13fLk09JXvGPzvJugABH-CbPQACh7QxG9OhYUv54uiD8-vioQEAAwIAA2IAAyME',
                #'file_unique_id': 'AQADh7QxG9OhYUtn', 'file_size': 26057, 'width': 320, 'height': 320},
                #{'file_id': 'AgACAgIAAxUAAWHMS13fLk09JXvGPzvJugABH-CbPQACh7QxG9OhYUv54uiD8-vioQEAAwIAA2MAAyME',
                #'file_unique_id': 'AQADh7QxG9OhYUsB', 'file_size': 80575, 'width': 640, 'height': 640}
                #]
            #]
        #)
        #]

        file_id = None
        first = True
        for o in photos_output:
            if o[0] == 'photos':
                for p in o[1]:
                    for f in p:
                        if first:
                            file_id = f['file_id']
                            first = False
                        elif f.get('width') and f.get('height') and f['width'] * f['height'] <= settings.PHOTO_MAX_SIZE:
                            file_id = f['file_id']
                    break
        if file_id:
            photo_path = await bot.get_file(file_id)
            photo_path = photo_path and photo_path.file_path or ''
            photo_path = photo_path.rstrip('/') or None
        else:
            photo_path = None

        if photo_path:
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                try:
                    async with session.get(
                        "https://api.telegram.org/file/bot%s/%s" % (settings.TOKEN, photo_path,),
                    ) as resp:
                        try:
                            status = int(resp.status)
                            if status == 200:
                                result = base64.b64encode(await resp.read()).decode('UTF-8')
                        except ValueError:
                            pass
                except:
                    pass
        return result


    @classmethod
    async def put_tg_user_photo(cls, photo, response):
        status_photo, response_photo = None, None
        if photo and response and response.get('uuid'):
            status_photo, response_photo = await cls.put_user_properties(
                photo=photo,
                uuid=response['uuid'],
            )
        return status_photo, response_photo


    @classmethod
    async def update_user_photo(cls, bot, tg_user, profile):
        return await cls.put_tg_user_photo(
            await cls.get_user_photo(bot, tg_user), profile,
        )


    @classmethod
    async def api_request(cls,
            path,
            method='GET',
            data=None,
            json=None,
            params=None,
            response_type='json',
        ):
        """
        Запрос в апи.

        Если задана data, то это передача формы.
        Если задан json, то это json- запрос
        Ответ в соответствии с response_type:
            'json' или 'text'
        """
        status = response = None
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            try:
                async with session.request(
                    method.upper(),
                    "%s%s" % (settings.API_HOST, path,),
                    data=data,
                    json=json,
                    params=params,
                ) as resp:
                    status = resp.status
                    if status < 500:
                        if response_type == 'json':
                            response = await resp.json()
                        elif response_type == 'text':
                            response = await resp.text('UTF-8')
                    else:
                        response = await resp.text('UTF-8')
            except:
                pass
        return status, response


    @classmethod
    def get_deeplink(cls, response, bot_data, https=False):
        """
        Получить ссылку типа http://t.me/BotNameBot?start=:uuid
        """
        deeplink = "t.me/%(bot_data_username)s?start=%(response_uuid)s" % dict(
            bot_data_username=bot_data['username'],
            response_uuid=response['uuid']
        )
        if https:
            deeplink = 'https://' + deeplink
        return deeplink


    @classmethod
    def get_deeplink_with_name(cls, response, bot_data, with_lifetime_years=False):
        """
        Получить ссылку типа https://t.me/BotNameBot?start=:uuid с именем и возможно, с годами жизни
        """
        href = cls.get_deeplink(response, bot_data, https=True)
        iof = response['first_name']
        if with_lifetime_years:
            lifetime_years_str = cls.get_lifetime_years_str(response)
            if lifetime_years_str:
                iof += ', ' + lifetime_years_str
        return cls.get_html_a(href, iof)


    @classmethod
    def url_user_on_map(cls, response):
        return '%(map_host)s/?uuid=%(user_uuid)s' % dict(
            map_host=settings.MAP_HOST,
            user_uuid=response['uuid'],
        )


    @classmethod
    def reply_user_card(cls, response, bot_data, show_parents=True):
        """
        Карточка пользователя, каким он на сайте

        На входе:
        response: ответ от сервера
        bot_data

        На выходе:
        Имя Фамилия
        Доверий:
        Благодарностей:
        Недоверий:

        Возможности: водитель Камаз шашлык виноград курага изюм

        Потребности: не задано

        Местоположение: не задано/ссылка на карту

        Контакты:
        @username
        +3752975422568
        https://username.com
        """
        if not response:
            return ''
        iof = response['first_name']
        lifetime_str = response.get('owner_id') and cls.get_lifetime_str(response) or ''
        if lifetime_str:
            lifetime_str += '\n'
        reply = (
                '<b>%(iof)s</b>\n'
                '%(lifetime_str)s'
                'Доверий: %(trust_count)s\n'
                'Благодарностей: %(sum_thanks_count)s\n'
                '\n'
            ) % dict(
            iof=iof,
            lifetime_str=lifetime_str,
            trust_count=response['trust_count'],
            sum_thanks_count=response['sum_thanks_count'],
        )
        abilities_text = '\n'.join(
            ability['text'] for ability in response['abilities']
        ) if response.get('abilities') else 'не задано'
        reply += ('Возможности: %s' % abilities_text) + '\n\n'

        wishes_text = '\n'.join(
            wish['text'] for wish in response['wishes']
        ) if response.get('wishes') else 'не задано'
        reply += ('Потребности: %s' % wishes_text) + '\n\n'

        map_text = (
            cls.get_html_a(cls.url_user_on_map(response), response.get('address') or 'тут')
        ) if response.get('latitude') is not None and response.get('longitude') is not None \
            else  'не задано'
        reply += ('Местоположение: %s' % map_text) + '\n\n'

        if show_parents:
            papa = response.get('father') and \
                   cls.get_deeplink_with_name(response['father'], bot_data, with_lifetime_years=True) or \
                   'не задан'
            mama = response.get('mother') and \
                   cls.get_deeplink_with_name(response['mother'], bot_data, with_lifetime_years=True) or \
                   'не задана'
            if response.get('children'):
                children = '\n'
                for child in response['children']:
                    children += ' ' + cls.get_deeplink_with_name(child, bot_data, with_lifetime_years=True) + '\n'
            else:
                children = 'не заданы\n'
            parents = (
                'Папа: %(papa)s\n'
                'Мама: %(mama)s\n'
                'Дети: %(children)s\n'
            ) % dict(papa=papa, mama=mama, children=children)
            reply += parents

        keys = ["@%s" % tgd['tg_username'] for tgd in response.get('tg_data', []) if tgd['tg_username']]
        keys += [key['value'] for key in response.get('keys', [])]
        keys.append(cls.get_deeplink(response, bot_data))
        keys_text = '\n' + '\n'.join(
            key for key in keys
        ) if keys else 'не задано'
        reply += ('Контакты: %s' % keys_text) + '\n\n'

        return reply

    @classmethod
    def reply_relations(cls, response):
        result = ''
        arr = [
            'От Вас: %s' % OperationType.relation_text(response['from_to']['is_trust']),
            'К Вам: %s' % OperationType.relation_text(response['to_from']['is_trust']),
        ]
        arr.append('\n')
        result = '\n'.join(arr)
        return result

    @classmethod
    def make_login_url(cls, redirect_path):
        """
        Сформировать ссылку, которая будет открываться авторизованным пользователем

        Пример результата:
        https://dev.blagodarie.org/auth/telegram/?redirect_path=/profile/?id=...

        где /profile/?id=... - путь на фронте, куда после авторизации уходим
        """
        redirect_path = urlencode(dict(
            redirect_path=redirect_path
        ))
        return (
            '%(frontend_host)s'
            '%(frontend_auth_path)s'
            '?%(redirect_path)s'
        ) % dict(
            frontend_host=settings.FRONTEND_HOST,
            frontend_auth_path=settings.FRONTEND_AUTH_PATH,
            redirect_path=redirect_path,
        )

    @classmethod
    async def post_tg_user(cls, tg_user_sender, activate=True):
        """
        Получить данные и/или сформировать пользователя
        """
        payload_sender = dict(
            tg_token=settings.TOKEN,
            tg_uid=tg_user_sender.id,
            last_name=tg_user_sender.last_name or '',
            first_name=tg_user_sender.first_name or '',
            username=tg_user_sender.username or '',
            activate='1' if activate else '',
            did_bot_start='1',
        )
        logging.debug('get_or_create tg_user by tg_uid in api, payload: %s' % payload_sender)
        status_sender, response_sender = await cls.api_request(
            path='/api/profile',
            method='post',
            data=payload_sender,
        )
        logging.debug('get_or_create tg_user by tg_uid in api, status: %s' % status_sender)
        logging.debug('get_or_create tg_user by tg_uid in api, response_from: %s' % response_sender)
        return status_sender, response_sender


    @classmethod
    async def get_user_by_uuid(cls, uuid, with_owner=False):
        """
        Получить данные пользователя по uuid
        """
        params = dict(uuid=uuid)
        if with_owner:
            params.update(with_owner='1')
        status, response = await Misc.api_request(
            path='/api/profile',
            method='get',
            params=params,
        )
        logging.debug('get_user_profile by uuid, status: %s' % status)
        logging.debug('get_user_profile by uuid, response: %s' % response)
        return status, response


    @classmethod
    async def get_user_by_tg_uid(cls, tg_uid):
        """
        Получить данные пользователя по тедеграм ид
        """
        params = dict(tg_uid=str(tg_uid))
        status, response = await Misc.api_request(
            path='/api/profile',
            method='get',
            params=params,
        )
        logging.debug('get_user_profile by tg_uid, status: %s' % status)
        logging.debug('get_user_profile by tg_uid, response: %s' % response)
        return status, response


    @classmethod
    def is_photo_downloaded(cls, profile):
        """
        Загружено ли фото в апи. Иначе или нет фото или это ссылка на другой ресурс
        """
        result = False
        photo = profile.get('photo')
        if photo and photo.lower().startswith(settings.API_HOST.lower()):
            result = True
        return result


    @classmethod
    async def check_owner(cls, owner_tg_user, uuid, check_owned_only=False):
        """
        Проверить, принадлежит ли uuid к owner_tg_user или им является

        При check_onwed_only проверяет исключительно, принадлежит ли.
        Если принадлежит и им является, то возвращает данные из апи по owner_tg_user,
        а внутри словарь response_uuid, данные из апи по uuid:
        """
        result = False
        status_sender, response_sender = await cls.post_tg_user(owner_tg_user, activate=True)
        if status_sender == 200 and response_sender.get('user_id'):
            status_uuid, response_uuid = await cls.get_user_by_uuid(uuid)
            if status_uuid == 200 and response_uuid:
                if response_uuid.get('owner_id'):
                    result = response_uuid['owner_id'] == response_sender['user_id']
                elif not check_owned_only:
                    result = response_uuid['user_id'] == response_sender['user_id']
                if result:
                    result = response_sender
                    result.update(response_uuid=response_uuid)
        return result

    @classmethod
    def get_text_usernames(cls, s):
        """
        Выделить из текста @usernames и вернуть еще текст без @usernames
        """
        usernames = []
        for m in re.finditer(r'\@\w+', s):
            username = m.group(0)
            if username not in usernames:
                usernames.append(username)
        text = s
        for username in usernames:
            text = re.sub(re.escape(username), '', text)
        text = re.sub(r'\s{2,}', ' ', text)
        text = text.strip()
        for i, v in enumerate(usernames):
            usernames[i] = usernames[i][1:]
        return usernames, text


    @classmethod
    async def show_deeplinks(cls,
        # Список данных пользователей
        a_found,
        # в ответ на какое сообщение
        message,
        bot_data,
    ):
        """
        Показать строки deeplinks по массиву a_found
        """
        reply = ''
        uuids = []
        for response in a_found:
            if response['uuid'] in uuids:
                continue
            else:
                uuids.append(response['uuid'])
                reply += Misc.get_deeplink_with_name(response, bot_data, with_lifetime_years=True) +'\n'
        if reply:
            parts = safe_split_text(reply, split_separator='\n')
            for part in parts:
                await message.reply(part, disable_web_page_preview=True)

    @classmethod
    async def show_cards(cls,
        # Список данных пользователей
        a_response_to,
        # в ответ на какое сообщение
        message,
        bot,
        # данные пользователя-отправителя сообщения message
        response_from={},
        # Ид сообщения, которое включить в кнопки, чтобы его потом перенаправить
        message_to_forward_id='',
        # Список карточек отправляется в группу?
        group_id='',
    ):
        """
        Показать карточки пользователей
        """
        bot_data = await bot.get_me()
        user_from_id = response_from.get('user_id')
        for response_to in a_response_to:
            is_own_account = user_from_id and user_from_id == response_to['user_id']
            is_owned_account = user_from_id and response_to.get('owner_id') and response_to['owner_id'] == user_from_id
            reply_markup = InlineKeyboardMarkup()

            path = "/profile/?id=%s" % response_to['uuid']
            url = settings.FRONTEND_HOST + path
            # login_url = LoginUrl(url=cls.make_login_url(path))
            inline_btn_friends = InlineKeyboardButton(
                'Доверия',
                url=url,
                # login_url=login_url,
            )
            goto_buttons = [inline_btn_friends, ]
            if not group_id and response_from.get('uuid') and not is_own_account:
                path = "/trust/?id=%s,%s&d=10" % (response_from['uuid'], response_to['uuid'],)
                url = settings.FRONTEND_HOST + path
                # login_url = LoginUrl(url=cls.make_login_url(path))
                inline_btn_path = InlineKeyboardButton(
                    'Путь (доверия)',
                    url=url,
                    # login_url=login_url,
                )
                goto_buttons.append(inline_btn_path)
            if not group_id and (is_own_account or is_owned_account):
                path = "?id=%s&depth=3" % response_to['uuid']
                url = 'https://genesis.blagodarie.org' + path
                inline_btn_genesis = InlineKeyboardButton(
                    'Род',
                    url=url,
                )
                goto_buttons.append(inline_btn_genesis)
            if not group_id and response_from.get('uuid') and not is_own_account:
                path = "/?id=%s,%s&depth=10" % (response_from['uuid'], response_to['uuid'],)
                url = 'https://genesis.blagodarie.org' + path
                inline_btn_genesis_path = InlineKeyboardButton(
                    'Путь ( род)',
                    url=url,
                )
                goto_buttons.append(inline_btn_genesis_path)
            reply_markup.row(*goto_buttons)
            reply = cls.reply_user_card(
                response_to,
                bot_data=bot_data,
            )

            response_relations = None
            if user_from_id and user_from_id != response_to['user_id']:
                payload_relation = dict(
                    user_id_from=response_from['uuid'],
                    user_id_to=response_to['uuid'],
                )
                status, response = await cls.api_request(
                    path='/api/user/relations/',
                    method='get',
                    params=payload_relation,
                )
                logging.debug('get users relations, status: %s' % status)
                logging.debug('get users relations: %s' % response)
                if status == 200:
                    reply += cls.reply_relations(response)
                    response_relations = response

            if user_from_id != response_to['user_id'] and bot_data.id != message.from_user.id:
                dict_reply = dict(
                    keyboard_type=KeyboardType.TRUST_THANK_VER_2,
                    sep=KeyboardType.SEP,
                    user_to_uuid_stripped=cls.uuid_strip(response_to['uuid']),
                    message_to_forward_id=message_to_forward_id,
                    group_id=group_id,
                )
                callback_data_template = OperationType.CALLBACK_DATA_TEMPLATE
                show_inline_btn_nullify_trust = True
                if group_id or \
                   (response_relations and response_relations['from_to']['is_trust'] is None):
                    show_inline_btn_nullify_trust = False

                title_thank = 'Доверие'
                if response_relations:
                    if response_relations['from_to']['is_trust'] and response_relations['from_to']['thanks_count']:
                        title_thank = 'Благодарить'
                dict_reply.update(operation=OperationType.TRUST_AND_THANK)
                inline_btn_trust = InlineKeyboardButton(
                    title_thank,
                    callback_data=callback_data_template % dict_reply,
                )
                dict_reply.update(operation=OperationType.MISTRUST)
                inline_btn_mistrust = InlineKeyboardButton(
                    'Недоверие',
                    callback_data=callback_data_template % dict_reply,
                )
                dict_reply.update(operation=OperationType.NULLIFY_TRUST)
                inline_btn_nullify_trust = InlineKeyboardButton(
                    'Забыть',
                    callback_data=callback_data_template % dict_reply,
                )
                if show_inline_btn_nullify_trust:
                    reply_markup.row(
                        inline_btn_trust,
                        inline_btn_mistrust,
                        inline_btn_nullify_trust
                    )
                else:
                    reply_markup.row(
                        inline_btn_trust,
                        inline_btn_mistrust,
                    )

            callback_data_template = cls.CALLBACK_DATA_UUID_TEMPLATE
            if is_own_account or is_owned_account:
                # Карточка самому пользователю или его родственнику
                #
                inline_btn_other = InlineKeyboardButton(
                    'Пол и даты' if is_owned_account else 'Пол и дата рождения',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.OTHER,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                ))
                inline_btn_location = InlineKeyboardButton(
                    'Место',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.LOCATION,
                    uuid=response_to['uuid'] if is_owned_account else '',
                    sep=KeyboardType.SEP,
                ))
                inline_btn_photo = InlineKeyboardButton(
                    'Фото',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.PHOTO,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                ))

                inline_btn_iof = InlineKeyboardButton(
                    'ФИО',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.IOF,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                ))
                reply_markup.row(
                    inline_btn_iof,
                    inline_btn_other,
                    inline_btn_photo,
                    inline_btn_location
                )

                dict_papa_mama = dict(
                    keyboard_type=KeyboardType.FATHER,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                )
                inline_btn_papa = InlineKeyboardButton(
                    'Папа',
                    callback_data=callback_data_template % dict_papa_mama,
                )
                dict_papa_mama.update(keyboard_type=KeyboardType.MOTHER)
                inline_btn_mama = InlineKeyboardButton(
                    'Мама',
                    callback_data=callback_data_template % dict_papa_mama,
                )
                dict_child = dict(
                    keyboard_type=KeyboardType.CHILD,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                )
                inline_btn_child = InlineKeyboardButton(
                    'Ребёнок',
                    callback_data=callback_data_template % dict_child,
                )
                args_papa_mama_owner = [inline_btn_papa, inline_btn_mama, inline_btn_child, ]
                if is_owned_account:
                    dict_change_owner = dict(
                        keyboard_type=KeyboardType.CHANGE_OWNER,
                        uuid=response_to['uuid'],
                        sep=KeyboardType.SEP,
                    )
                    inline_btn_change_owner = InlineKeyboardButton(
                        'Владелец',
                        callback_data=callback_data_template % dict_change_owner,
                    )
                    args_papa_mama_owner.append(inline_btn_change_owner)
                reply_markup.row(*args_papa_mama_owner)

                dict_abwishkey = dict(
                    keyboard_type=KeyboardType.ABILITY,
                    uuid=response_to['uuid'] if is_owned_account else '',
                    sep=KeyboardType.SEP,
                )
                inline_btn_ability = InlineKeyboardButton(
                    'Возможности',
                    callback_data=callback_data_template % dict_abwishkey,
                )
                dict_abwishkey.update(keyboard_type=KeyboardType.WISH)
                inline_btn_wish = InlineKeyboardButton(
                    'Потребности',
                    callback_data=callback_data_template % dict_abwishkey,
                )
                dict_abwishkey.update(keyboard_type=KeyboardType.KEYS, uuid=response_to['uuid'])
                inline_btn_keys = InlineKeyboardButton(
                    'Контакты',
                    callback_data=callback_data_template % dict_abwishkey,
                )
                reply_markup.row(inline_btn_ability, inline_btn_wish, inline_btn_keys)

            if not group_id:
                dict_message = dict(
                    keyboard_type=KeyboardType.SEND_MESSAGE,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                )
                inline_btn_send_message = InlineKeyboardButton(
                    'Написать',
                    callback_data=callback_data_template % dict_message,
                )
                dict_message.update(
                    keyboard_type=KeyboardType.SHOW_MESSAGES,
                )
                inline_btn_show_messages = InlineKeyboardButton(
                    'Архив',
                    callback_data=callback_data_template % dict_message,
                )
                reply_markup.row(inline_btn_send_message, inline_btn_show_messages)

            if user_from_id:
                # в бот
                #
                send_text_message = True
                if response_to.get('photo') and response_from and response_from.get('tg_data'):
                    try:
                        photo = InputFile.from_url(response_to['photo'], filename='1.png')
                        await bot.send_photo(
                            chat_id=message.from_user.id,
                            photo=photo,
                            disable_notification=True,
                            caption=reply,
                            reply_markup=reply_markup,
                        )
                        send_text_message = False
                    except BadRequest as excpt:
                        if excpt.args[0] == 'Media_caption_too_long':
                            try:
                                await bot.send_photo(
                                    chat_id=message.from_user.id,
                                    photo=photo,
                                    disable_notification=True,
                                )
                            except:
                                pass
                    except:
                        pass
                if send_text_message:
                    await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)
            else:
                # в группу
                await message.answer(reply, reply_markup=reply_markup, disable_web_page_preview=True)


    @classmethod
    def get_lifetime_str(cls, response):
        lifetime = ''
        if response.get('dob'):
            lifetime += response['dob']
        elif response.get('dod'):
            lifetime += '...'
        if response.get('dod'):
            lifetime += " – %s" % response['dod']
        return lifetime


    @classmethod
    def get_lifetime_years_str(cls, response):
        lifetime = ''
        if response.get('dob'):
            lifetime += response['dob'][-4:]
        elif response.get('dod'):
            lifetime += '...'
        if response.get('dod'):
            lifetime += " – %s" % response['dod'][-4:]
        return lifetime


    @classmethod
    def his_her(cls, profile):
        his_her = 'его (её)'
        if profile.get('gender'):
            if profile['gender'] == 'm':
                his_her = 'его'
            else:
                his_her = 'её'
        return his_her


    @classmethod
    async def state_finish(cls, state):
        if state:
            await state.finish()
            async with state.proxy() as data:
                for key in ('uuid', ):
                    if data.get(key):
                        data[key] = ''


    @classmethod
    def inline_button_cancel(cls):
        """
        Inline кнопка с 'Отмена'
        """
        callback_data = '%(keyboard_type)s%(sep)s' % dict(
            keyboard_type=KeyboardType.CANCEL_ANY,
            sep=KeyboardType.SEP,
        )
        return InlineKeyboardButton(
            'Отмена',
            callback_data=callback_data,
        )


    @classmethod
    def strip_text(cls, s):
        """
        Убрать из текста лишние пробелы
        """
        s = s.strip().strip("'").strip()
        s = re.sub(r'\s{2,}', ' ', s)
        s = re.sub(r'\s', ' ', s)
        return s


    @classmethod
    def reply_markup_cancel_row(cls):
        """
        Ряд с одна inline кнопкой с 'Отмена'
        """
        inline_btn_cancel = cls.inline_button_cancel()
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_cancel)
        return reply_markup


    @classmethod
    def show_other_data(cls, data):
        """
        Показать текущие другие данные

        data: может быть ответ о пользователе из апи, или данные, сохраняемые в состоянии бота
        """
        is_owned = bool(data.get('is_owned') or data.get('owner_id'))
        gender = 'не задан'
        if 'is_male' in data:
            gender = 'муж.' if data['is_male'] else 'жен.'
        elif 'gender' in data:
            if data['gender'] == 'm':
                gender = 'муж.'
            elif data['gender'] == 'f':
                gender = 'жен.'
        dob='Дата рождения: %s' % (data.get('dob') or 'не указана')
        dod = ''
        if is_owned:
            dod='\nДата смерти: %s' % (data.get('dod') or 'не указана')
        d = dict(
            name=data.get('name', '') or data.get('first_name', '') or 'Без имени',
            gender=gender,
            dob=dob,
            dod=dod,
        )
        s = (
            '<b>%(name)s</b>\n'
            '<u>Текущие сведения:</u>\n'
            'Пол: %(gender)s\n'
            '%(dob)s'
            '%(dod)s'
        ) % d + '\n'
        return s


    @classmethod
    async def put_user_properties(cls, **kwargs):
        status, response = None, None
        logging.debug('put tg_user_data...')
        payload = dict(tg_token=settings.TOKEN,)
        payload.update(**kwargs)
        logging.debug('put user_data, payload: %s' % payload)
        status, response = await Misc.api_request(
            path='/api/profile',
            method='put',
            data=payload,
        )
        logging.debug('put user_data, status: %s' % status)
        logging.debug('put user_data, response: %s' % response)
        return status, response

    @classmethod
    def text_search_phrase(
            cls,
            phrase,
            morph_analyzer,
            # Исключаемые граммемы
            # https://pymorphy2.readthedocs.io/en/latest/user/grammemes.html#grammeme-docs
            functors_pos={'INTJ', 'PRCL', 'CONJ', 'PREP'},
            # or, and or nothing
            operation='and',
        ):
        """
        Возвращает фразу для полнотекстового поиска
        """
        def what_pos(word):
            "Return a likely part of speech for the *word*."""
            return morph_analyzer.parse(word)[0].tag.POS

        result = []
        words = re.split(r'\s+', phrase)
        for word in words:
            if len(word) < settings.MIN_LEN_SEARCHED_TEXT:
                continue
            if what_pos(word) not in functors_pos:
                word = re.sub(r'[\?\!\&\|\,\.\:\;\'\)\(\{\}\*\"\<\>\`\~]', '', word)
                if len(word) >= settings.MIN_LEN_SEARCHED_TEXT:
                    result.append(word)
        if result:
            sep = ' '
            if operation == 'and':
                sep = ' & '
            elif operation == 'or':
                sep = ' | '
            result = sep.join(result)
        else:
            result = ''
        return result

    @classmethod
    def uuid_from_text(cls, text, unstrip=False):
        user_uuid_to = None
        if unstrip:
            text = '%s-%s-%s-%s-%s'% (text[0:8], text[8:12], text[12:16], text[16:20], text[20:])
        m = re.search(cls.UUID_PATTERN, text)
        if m:
            s = m.group(0)
            try:
                UUID(s)
                user_uuid_to = s
            except (TypeError, ValueError,):
                pass
        return user_uuid_to


    @classmethod
    def uuid_strip(cls, uuid):
        """
        Убрать - в uuid

        Экономим место для callback_data в inline кнопках
        """
        return uuid.replace('-', '')

    @classmethod
    async def search_users(cls, what, search_phrase, *args, **kwargs):
        """
        Поиск пользователей

        what:           query, query_ability, query_person...
        query:          строка поиска
        select_related: возможен вариант 'profile__ability'.
                        Если что-то еще, то строка с ними через запятую
        """
        status, a_found = None, None
        if search_phrase:
            payload_query = { what: search_phrase, }
            payload_query.update(**kwargs)
            logging.debug('get users by %s, payload: %s' % (what, payload_query,))
            status, a_found = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=payload_query,
            )
            logging.debug('get users by %s, status: %s' % (what, status, ))
            logging.debug('get users by %s, a_found: %s' % (what, a_found, ))
        return status, a_found

class TgGroup(object):
    """
    Список групп, где бот: внесение, удаление
    """

    @classmethod
    async def get(cls, chat_id):
        payload = dict(chat_id=chat_id)
        logging.debug('get group info, payload: %s' % payload)
        status, response = await Misc.api_request(
            path='/api/bot/group',
            method='GET',
            params=payload,
        )
        logging.debug('get group info, status: %s' % status)
        logging.debug('get group info, response: %s' % response)
        return status, response

    @classmethod
    async def post(cls, chat_id, title, type_):
        payload = {'tg_token': settings.TOKEN, 'chat_id': chat_id, 'title': title, 'type': type_,}
        logging.debug('post group id, payload: %s' % payload)
        status, response = await Misc.api_request(
            path='/api/bot/group',
            method='post',
            json=payload,
        )
        logging.debug('post group id, status: %s' % status)
        logging.debug('post group id, response: %s' % response)
        return status, response

    @classmethod
    async def delete(cls, chat_id):
        payload = {'tg_token': settings.TOKEN, 'chat_id': chat_id,}
        logging.debug('delete group id, payload: %s' % payload)
        status, response = await Misc.api_request(
            path='/api/bot/group',
            method='delete',
            json=payload,
        )
        logging.debug('delete group id, status: %s' % status)
        logging.debug('delete group id, response: %s' % response)
        return status, response

class TgGroupMember(object):
    """
    Список групп, где бот: внесение, удаление
    """

    @classmethod
    def payload(cls, group_chat_id, group_title, group_type, user_tg_uid):
        return {
            'tg_token': settings.TOKEN,
            'group': {
                'chat_id': group_chat_id,
                # могут быть не заданы. Если так, то апи не меняет это, если группа (канал) существуют
                #
                'title': group_title,
                'type': group_type,
            },
            'user': {
                'tg_uid': user_tg_uid,
            }
        }

    @classmethod
    async def add(cls, group_chat_id, group_title, group_type, user_tg_uid):
        payload = cls.payload(group_chat_id, group_title, group_type, user_tg_uid)
        logging.debug('post group member, payload: %s' % payload)
        status, response = await Misc.api_request(
            path='/api/bot/groupmember',
            method='post',
            json=payload,
        )
        logging.debug('post group member, status: %s' % status)
        logging.debug('post group member, response: %s' % response)
        return status, response

    @classmethod
    async def remove(cls, group_chat_id, group_title, group_type, user_tg_uid):
        payload = cls.payload(group_chat_id, group_title, group_type, user_tg_uid)
        logging.debug('delete group member, payload: %s' % payload)
        status, response = await Misc.api_request(
            path='/api/bot/groupmember',
            method='delete',
            json=payload,
        )
        logging.debug('delete group member, status: %s' % status)
        logging.debug('delete group member, response: %s' % response)
        return status, response

