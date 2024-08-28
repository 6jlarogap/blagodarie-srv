import base64, re, datetime, copy
from urllib.parse import urlencode
from uuid import UUID
import qrcode
from PIL import Image
from io import BytesIO

from aiogram import types
from aiogram.types.login_url import LoginUrl
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types.input_file import InputFile
from aiogram.utils.parts import safe_split_text
from aiogram.utils.exceptions import BadRequest
import aiohttp

import settings

from settings import logging

TIMEOUT = aiohttp.ClientTimeout(total=settings.HTTP_TIMEOUT)


class Attitude(object):

    ACQ = 'a'
    TRUST = 't'
    MISTRUST = 'mt'

    @classmethod
    def text(cls, attitude):
        result = 'не знакомы'
        if attitude == Attitude.TRUST:
            result = 'доверие'
        elif attitude == Attitude.MISTRUST:
            result = 'недоверие'
        elif attitude == Attitude.ACQ:
            result = 'знакомы'
        return result


class OperationType(object):
    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_ATTITUDE = 4
    FATHER = 6
    NOT_PARENT = 7
    MOTHER = 8
    SET_FATHER = 9
    SET_MOTHER = 10
    # Acquainted
    ACQ = 11

    CALLBACK_DATA_TEMPLATE = (
        '%(keyboard_type)s%(sep)s'
        '%(operation)s%(sep)s'
        '%(user_to_uuid_stripped)s%(sep)s'
        '%(message_to_forward_id)s%(sep)s'
    )


    # Операции, которые возможны для запуска ссылкой
    # для телеграма типа:
    # https://t.me/<bot_username>?start=<start_prefix>-<uuid>
    # Пока только t: trust and thank, которое устанавливает
    # доверие от авторизованного юзера, если до этого не было
    # установлено доверие, или делает благодарность,
    # если уже установлено доверие

    @classmethod
    def start_prefix_to_op(cls, prefix):
        """
        Префикс команды /start <prefix>-<uuid> --> операция
        """
        return dict(
            t=cls.TRUST,
            m=cls.ACQ,
            th=cls.THANK,
        ).get(prefix)


class KeyboardType(object):
    """
    Варианты клавиатур и служебный символ для call back data из кнопок клавиатур
    """
    # Багодарность, доверие, недоверие...
    #
    TRUST_THANK = 2

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

    # Замена пола
    #
    GENDER = 16
    GENDER_MALE = 17
    GENDER_FEMALE = 18

    # Даты рождения/смерти
    #
    DATES = 19
    # не знаю, когда его, ее, мой д.р.
    DATES_DOB_UNKNOWN = 54
    # На вопрос о дате смерти: жив или не знаю
    DATES_DOD_NONE = 20
    # На вопрос о дате смерти: точно знаю, что умер, не знаю когда
    DATES_DOD_DEAD = 53

    # Внести ребёнка
    #
    CHILD = 21

    CANCEL_THANK = 22

    NEW_SON = 45
    NEW_DAUGHTER = 46


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

    DELETE_USER = 34
    DELETE_USER_CONFIRMED = 35

    UNDELETE_USER = 36
    UNDELETE_USER_CONFIRMED = 37

    # Обнулить папу, маму
    #
    CLEAR_PARENT = 38
    CLEAR_PARENT_CONFIRM = 39

    # Очистка связи родитель -> ребенок
    #
    CLEAR_CHILD = 40
    CLEAR_CHILD_CONFIRM = 41

    # Письмо администраторам
    #
    FEEDBACK = 42

    # Отменили комментарии к благодарностям
    #
    # TRUST_THANK_WO_COMMENT = 43

    OFFER_ANSWER = 44

    # заняты: 45, 46

    # Новый собственный, его/её пол
    #
    NEW_IOF_GENDER_MALE = 47
    NEW_IOF_GENDER_FEMALE = 48

    # Брат/сестра
    #
    BRO_SIS = 49
    NEW_BRO = 50
    NEW_SIS = 51

    COMMENT = 52

    # заняты: 53, 54

    # В карточке пользователя при кнопке "Пригласить"
    INVITE = 55
    # В вопросе, не желает ли принять приглашение
    INVITE_CONFIRM = 56

    # Участие и отказ от участия в игре знакомств
    #
    MEET_DO = 57
    MEET_REVOKE = 58

    MEET_GENDER_MALE = 59
    MEET_GENDER_FEMALE = 60


    # Разделитель данных в call back data
    #
    SEP = '~'

class Misc(object):
    """
    Различные функции, сообщения, константы
    """

    MSG_YOU_GOT_MESSAGE = 'Вам сообщение от <b>%s</b>'
    MSG_YOU_CANCELLED_INPUT = 'Вы отказались от ввода данных'
    MSG_USER_NOT_FOUND = 'Пользователь не найден'

    MSG_LOCATION = (
        'Пожалуйста, отправьте мне координаты вида \'74.188586, 95.790195\' '
        '(широта,долгота - удобно скопировать из приложения карт Яндекса/Гугла) '
        'или нажмите Отмена. ВНИМАНИЕ! Отправленные координаты будут опубликованы!\n'
        '\n'
        'Отправленное местоположение будет использовано для отображение профиля '
        'на картах участников голосований, опросов и на общей карте участников проекта '
        '- точное местоположение не требуется - '
        'можно выбрать ближнюю/дальнюю остановку транспорта, рынок или парк.'
    )

    MSG_LOCATION_MANDAT = (
        'Пожалуйста, отправьте мне координаты вида \'74.188586, 95.790195\' '
        '(широта,долгота - удобно скопировать из приложения карт Яндекса/Гугла) '
        'ВНИМАНИЕ! Отправленные координаты будут опубликованы!\n'
        '\n'
        '- точное местоположение не требуется - '
        'можно выбрать ближнюю/дальнюю остановку транспорта, рынок или парк.'
    )

    PROMPT_SEARCH_TEXT_TOO_SHORT = 'Минимальное число символов в тексте для поиска: %s\n' % settings.MIN_LEN_SEARCHED_TEXT
    PROMPT_SEARCH_PHRASE_TOO_SHORT = 'Недостаточно для поиска: короткие слова или текст вообще без слов и т.п.'
    PROMPT_NOTHING_FOUND = 'Никто не найден - попробуйте другие слова'

    MSG_ERROR_API = 'Ошибка доступа к данным'
    MSG_ERROR_TEXT_ONLY = 'Принимается только текст'
    MSG_REPEATE_PLEASE = 'Повторите, пожалуйста!'

    PROMPT_ABILITY = 'Отправьте мне <u>текст</u> с <b>возможностями</b>'
    PROMPT_WISH = 'Отправьте мне <u>текст</u> с <b>потребностями</b>'

    PROMPT_PHOTO = 'Отправьте мне <b>фото</b>, не более %s Мб размером.' % settings.DOWNLOAD_PHOTO_MAX_SIZE
    PROMPT_PHOTO_REMOVE = "Нажмите 'Удалить' для удаления имеющегося фото."

    PROMPT_NEW_IOF = "Укажите имя отчество и фамилию - в одной строке, например: 'Иван Иванович Иванов'"
    PROMPT_NEW_ORG = 'Введите название новой организации'
    PROMPT_EXISTING_IOF = "Укажите для\n\n%(name)s\n\nдругие имя отчество и фамилию - в одной строке, например: 'Иван Иванович Иванов'"

    PROMPT_DATE_FORMAT = 'в формате ДД.ММ.ГГГГ или ММ.ГГГГ или ГГГГ'
    PROMPT_MESSAGE_INSTEAD_OF_GENDER = 'Ожидается выбор пола, нажатием одной из кнопок, в сообщении выше'

    PROMPT_PAPA_MAMA_OF_CHILD = (
        'Укажите пол %(name)s'
    )

    PROMPT_PAPA_MAMA_SET = (
                '%(iof_to)s\n'
                'отмечен%(_a_)s как %(papa_or_mama)s для:\n'
                '%(iof_from)s\n'
    )

    PROMPT_PAPA_MAMA_CLEARED = (
                'Родственная связь:\n'
                '%(iof_to)s - %(papa_or_mama)s для: %(iof_from)s\n'
                'разорвана\n'
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
        '%(iof_to)s %(already)s установлен владельцем для профиля %(iof_from)s'
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

    RE_UUID = re.compile(r'[\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12}', re.IGNORECASE)
    RE_SID = re.compile(r'^[0-9a-z]{10}$', re.IGNORECASE)

    # Никакого re.compile! :
    RE_KEY_SEP = r'^%s%s'

    CALLBACK_DATA_SID_TEMPLATE = '%(keyboard_type)s%(sep)s%(sid)s%(sep)s'
    CALLBACK_DATA_UUID_TEMPLATE = '%(keyboard_type)s%(sep)s%(uuid)s%(sep)s'
    CALLBACK_DATA_ID__TEMPLATE = '%(keyboard_type)s%(sep)s%(id_)s%(sep)s'
    CALLBACK_DATA_KEY_TEMPLATE = '%(keyboard_type)s%(sep)s'

    MSG_ERROR_UUID_NOT_VALID = (
        'Профиль не найден - попробуйте скопировать и '
        'отправить ссылку на существующий профиль ещё раз'
    )

    MSG_INVALID_LINK = 'Неверная ссылка'

    FORMAT_DATE = '%d.%m.%Y'
    FORMAT_TIME = '%H:%M:%S'

    PROMPT_CANCEL_LOCATION = 'Отмена'
    PROMPT_LOCATION = 'Отправить местоположение'

    PROMPT_IOF_INCORRECT = 'Некорректные ФИО - напишите ещё раз имя отчество и фамилию или Отмена'
    PROMPT_ORG_INCORRECT = (
        'Некорректное или слишком короткое, меньше 5 символов, '
        'название организации - напишите ещё раз название организации или '
        'нажмите Отмена'
    )


    @classmethod
    def secret(cls, payload):
        """
        Скрыть в payload, который отправляем в журнал, секретные параметры 
        """
        result = copy.deepcopy(payload)
        if 'tg_token' in payload:
            result.update(tg_token='SECRET')
        return result


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
    async def get_template(cls, template):
        status = response = None
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            try:
                async with session.request(
                    'GET',
                    "%s/res/telegram-bot/%s.txt" % (settings.FRONTEND_HOST, template),
                ) as resp:
                    status = resp.status
                    response = await resp.text('UTF-8')
            except:
                pass
        return status, response


    @classmethod
    async def help_text(cls):
        status, response = await cls.get_template('help')
        return response if status == 200 and response else cls.MSG_ERROR_API

    @classmethod
    async def chat_pin_message_text(cls):
        status, response = await cls.get_template('chat_pin_message')
        return response if status == 200 and response else None


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

        file_ = None
        first = True
        for o in photos_output:
            if o[0] == 'photos':
                for p in o[1]:
                    for f in p:
                        if first:
                            file_ = f
                            first = False
                        elif f.get('width') and f.get('height') and f['width'] * f['height'] <= settings.PHOTO_MAX_SIZE:
                            file_ = f
                    break
        if file_:
            image = await Misc.get_file_bytes(file_, bot)
            result = base64.b64encode(image).decode('UTF-8')
        return result


    @classmethod
    async def get_file_bytes(cls, f, bot):
        """
        Получить байты из телеграм- файла

        f:
            может быть message.photo[-1] при ContentType.PHOTO или фото тг юзера.
            У него обязан быть атрибут file_id или ключ file_id
        """
        file_id = getattr(f, 'file_id', None)
        if not file_id:
            file_id = f['file_id']
        tg_file = await bot.get_file(file_id)
        if settings.LOCAL_SERVER:
            fd = open(tg_file.file_path, 'rb')
            image = fd.read()
        else:
            fd = BytesIO()
            await bot.download_file(tg_file.file_path, fd)
            image = fd.read()
        fd.close()
        return image


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
        Получить ссылку типа http://t.me/BotNameBot?start=:username

        Если в response нет username, смотрим, есть ли uuid
        """
        if response.get('username'):
            response_id = response['username']
        elif response.get('uuid'):
            response_id = response['uuid']
        else:
            response_id = '-'
        deeplink = f't.me/{bot_data["username"]}?start={response_id}'
        if https:
            deeplink = 'https://' + deeplink
        return deeplink


    @classmethod
    def get_deeplink_with_name(cls, response, bot_data, with_lifetime_years=False, plus_trusts=False):
        """
        Получить ссылку типа https://t.me/BotNameBot?start=:uuid с именем

        и возможно, с годами жизни (with_lifetime_years=True)
        и числом доверий (plus_trusts=True), в скобках,
        или с числом доверий и не доверий, жирно, типа (+2 -1)
        """
        href = cls.get_deeplink(response, bot_data, https=True)
        iof = response['first_name']
        if with_lifetime_years:
            lifetime_years_str = cls.get_lifetime_years_str(response)
            if lifetime_years_str:
                iof += ', ' + lifetime_years_str
        result = cls.get_html_a(href, iof)
        if plus_trusts:
            trust_count = response['trust_count'] if response.get('trust_count') else 0
            mistrust_count = response['mistrust_count'] if response.get('mistrust_count') else 0
            result += f' (<b>+{trust_count}, -{mistrust_count}</b>)'
            plus_trusts = False
        return result


    @classmethod
    def reply_user_card(cls, response, editable, bot_data):
        """
        Карточка пользователя, каким он на сайте

        На входе:
        response: ответ от сервера
        bot_data

        На выходе:
        Имя Фамилия
        д/р - ...
        д/с - ....
        Доверий:
        Благодарностей:
        Знакомств:

        Возможности: водитель Камаз шашлык виноград курага изюм

        Потребности: не задано

        Контакты:
        @username
        +3752975422568
        https://username.com
        """
        if not response:
            return ''
        reply = f'<b>{response["first_name"]}</b>\n'
        if editable and (comment := response.get('comment', '').strip()) and comment:
            reply += f'{comment}\n'
        if not response.get('is_org'):
            reply += cls.get_lifetime_str(response)
        reply += (
            '\n'
            f'Доверий: {response["trust_count"]}\n'
            f'Благодарностей: {response["sum_thanks_count"]}\n'
            f'Знакомств: {response["acq_count"]}\n'
            '\n'
        )
        keys = []

        if editable and (response['is_active'] or response.get('owner')):
            abilities_text = '\n'.join(
                ability['text'] for ability in response['abilities']
            ) if response.get('abilities') else 'не заданы'
            reply += ('Возможности: %s' % abilities_text) + '\n\n'

            wishes_text = '\n'.join(
                wish['text'] for wish in response['wishes']
            ) if response.get('wishes') else 'не заданы'
            reply += ('Потребности: %s' % wishes_text) + '\n\n'

            if not response.get('is_org'):
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

        keys += ['@%s' % tgd['tg_username'] for tgd in response.get('tg_data', []) if tgd['tg_username']]
        keys += [key['value'] for key in response.get('keys', [])]
        keys.append(cls.get_deeplink(response, bot_data))

        if response.get('username'):
            keys.append(settings.SHORT_ID_LINK % response['username'])

        keys_text = '\n' + '\n'.join(
            key for key in keys
        ) if keys else 'не задано'
        reply += (('Контакты:' if len(keys) > 1 else 'Контакт:') + ' %s' % keys_text) + '\n\n'

        return reply

    @classmethod
    def editable(cls, profile, sender=None):
        """
        Можно ли sender'у править в карточке profile

        Если sender не задан, полагается, что profile есть профиль sender'а
        """
        if not sender:
            sender = profile
        return      profile.get('owner') and \
                        profile['owner'].get('editable') and profile['owner']['uuid'] == sender['uuid'] \
               or \
                    not profile.get('owner') and \
                    profile.get('editable') and profile['uuid'] == sender['uuid']


    @classmethod
    def reply_relations(cls, response, response_to):
        result = ''
        arr = ['От Вас: %s' % Attitude.text(response['from_to']['attitude']),]
        # Организация может доверять только, если у нее не собственный аккаунт
        if not response_to.get('is_org') and not response_to.get('owner'):
            arr.append('К Вам: %s' % Attitude.text(response['to_from']['attitude']))
        arr.append('\n')
        result = '\n'.join(arr)
        return result

    @classmethod
    def make_login_url(cls, redirect_path, bot_username, **kwargs):
        """
        Сформировать ссылку, которая будет открываться авторизованным пользователем

        Пример результата:
        https://blagoroda.org/auth/telegram/?redirect_path=https%3A%2F%2Fblagoroda.org%2F%3Ff%3D0%26q%3D25

        где:
            https://blagoroda.org/ (в начале)
                прописан /setdomain в боте
            redirect_path
                куда после авторизации уходим. В этом примере, после расшифровки,
                это https://blagoroda.org/f=0&q=50

        kwargs:
            дополнительные параметры, которые могут быть добавлены в результат
        """
        parms = dict(redirect_path=redirect_path)
        parms.update(**kwargs)
        parms = urlencode(parms)
        frontend_auth_path = settings.FRONTEND_AUTH_PATH.strip('/')
        return LoginUrl(
            url='%(frontend_host)s/%(frontend_auth_path)s/?%(parms)s' % dict(
                frontend_host=settings.FRONTEND_HOST,
                frontend_auth_path=frontend_auth_path,
                parms=parms,
            ),
            bot_username=bot_username,
        )


    @classmethod
    async def post_tg_user(cls, tg_user_sender, activate=False, did_bot_start=True):
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
            did_bot_start='1' if did_bot_start else '',
        )
        logging.debug('get_or_create tg_user by tg_uid in api, payload: %s' % cls.secret(payload_sender))
        status_sender, response_sender = await cls.api_request(
            path='/api/profile',
            method='post',
            data=payload_sender,
        )
        logging.debug('get_or_create tg_user by tg_uid in api, status: %s' % status_sender)
        logging.debug('get_or_create tg_user by tg_uid in api, response: %s' % response_sender)
        return status_sender, response_sender


    @classmethod
    async def get_user_by_uuid(cls, uuid, with_owner_tg_data=False):
        """
        Получить данные пользователя по uuid

        Если не найден, будет status == 400
        """
        params = dict(uuid=uuid)
        if with_owner_tg_data:
            params.update(with_owner_tg_data='1')
        logging.debug('get_user_profile by uuid, params: %s' % params)
        status, response = await cls.api_request(
            path='/api/profile',
            method='get',
            params=params,
        )
        logging.debug('get_user_profile by uuid, status: %s' % status)
        logging.debug('get_user_profile by uuid, response: %s' % response)
        return status, response


    @classmethod
    async def get_user_by_sid(cls, sid, with_owner_tg_data=False):
        """
        Получить данные пользователя по sid, short_id. Это username в апи

        Если не найден, будет status == 400
        """
        params = dict(username=sid)
        if with_owner_tg_data:
            params.update(with_owner_tg_data='1')
        logging.debug('get_user_profile by sid, params: %s' % params)
        status, response = await cls.api_request(
            path='/api/profile',
            method='get',
            params=params,
        )
        logging.debug('get_user_profile by sid, status: %s' % status)
        logging.debug('get_user_profile by sid, response: %s' % response)
        return status, response


    @classmethod
    async def get_admins(cls,):
        """
        Получить данные администраторов (они же разработчики)
        """
        params = dict(tg_uids=','.join(map(str, settings.BOT_ADMINS)))
        logging.debug('get_admins, params: %s' % params)
        status, response = await cls.api_request(
            path='/api/profile',
            method='get',
            params=params,
        )
        logging.debug('get_admins, status: %s' % status)
        logging.debug('get_admins, response: %s' % response)
        return status, response


    @classmethod
    async def get_user_by_tg_uid(cls, tg_uid):
        """
        Получить данные пользователя по тедеграм ид
        """
        params = dict(tg_uid=str(tg_uid))
        status, response = await cls.api_request(
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
    async def check_owner_by_uuid(cls, owner_tg_user, uuid, check_owned_only=False):
        """
        Проверить, принадлежит ли uuid к owner_tg_user или им является

        При check_onwed_only проверяет исключительно, принадлежит ли.
        Если принадлежит и им является, то возвращает данные из апи по owner_tg_user,
        а внутри словарь response_uuid, данные из апи по uuid:
        """
        result = False
        status_sender, response_sender = await cls.post_tg_user(owner_tg_user)
        if status_sender == 200 and response_sender.get('user_id'):
            status_uuid, response_uuid = await cls.get_user_by_uuid(uuid)
            if status_uuid == 200 and response_uuid:
                if response_uuid.get('owner'):
                    result = response_uuid['owner']['user_id'] == response_sender['user_id']
                elif not check_owned_only:
                    result = response_uuid['user_id'] == response_sender['user_id']
                if result:
                    result = response_sender
                    result.update(response_uuid=response_uuid)
        return result


    @classmethod
    async def check_owner_by_sid(cls, owner_tg_user, sid, check_owned_only=False):
        """
        Проверить, принадлежит ли user c sid к owner_tg_user или им является

        При check_onwed_only проверяет исключительно, принадлежит ли.
        Если принадлежит и им является, то возвращает данные из апи по owner_tg_user,
        а внутри словарь response_uuid, данные из апи по sid:
        """
        result = False
        status_sender, response_sender = await cls.post_tg_user(owner_tg_user)
        if status_sender == 200 and response_sender.get('user_id'):
            status_uuid, response_uuid = await cls.get_user_by_sid(sid)
            if status_uuid == 200 and response_uuid:
                if response_uuid.get('owner'):
                    result = response_uuid['owner']['user_id'] == response_sender['user_id']
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
                reply += cls.get_deeplink_with_name(response, bot_data, with_lifetime_years=True) +'\n'
        if reply:
            parts = safe_split_text(reply, split_separator='\n')
            for part in parts:
                await message.reply(part, disable_web_page_preview=True)


    @classmethod
    async def call_response_relations(cls, response_from, response_to):
        payload = dict(
            user_id_from=response_from.get('uuid'),
            user_id_to=response_to.get('uuid'),
        )
        status, response = await cls.api_request(
            path='/api/user/relations/',
            method='get',
            params=payload,
        )
        logging.debug('get users relations, payload: %s' % payload)
        logging.debug('get users relations, status: %s' % status)
        logging.debug('get users relations: %s' % response)
        if status != 200 or not response:
            status, response = None, {}
        return status, response


    @classmethod
    async def show_card(cls,
        # Данные пользователя
        #
        response_to,

        bot,

        # профиль пользователя-отправителя из апи, который будет читать карточку
        #
        response_from,

        # телеграм- пользователь, который будет читать карточку.
        #
        tg_user_from,

        # Ид сообщения, которое включить в кнопки, чтобы его потом перенаправить
        #
        message_to_forward_id='',

        # Сообщение с карточкой, которое надо подправить, а не слать новую карточку
        #
        card_message=None,
    ):
        """
        Показать карточки пользователей
        """
        if not response_to:
            return
        bot_data = await bot.get_me()
        user_from_id = response_from['user_id']
        tg_user_from_id = tg_user_from.id

        is_own_account = user_from_id == response_to['user_id']
        is_owned_account = response_to.get('owner') and response_to['owner']['user_id'] == user_from_id
        is_org = response_to.get('is_org')
        editable = cls.editable(profile=response_to, sender=response_from)

        reply = cls.reply_user_card(
            response_to,
            editable,
            bot_data=bot_data,
        )
        response_relations = {}
        if user_from_id != response_to['user_id']:
            status_relations, response_relations = await cls.call_response_relations(response_from, response_to)
            if response_relations:
                reply += cls.reply_relations(response_relations, response_to)
        if response_to['owner']:
            reply += f'Владелец: {cls.get_deeplink_with_name(response_to["owner"], bot_data)}\n'

        reply_markup = InlineKeyboardMarkup()

        if user_from_id != response_to['user_id'] and bot_data.id != tg_user_from_id:
            dict_reply = dict(
                keyboard_type=KeyboardType.TRUST_THANK,
                sep=KeyboardType.SEP,
                user_to_uuid_stripped=cls.uuid_strip(response_to['uuid']),
                message_to_forward_id=message_to_forward_id,
            )
            callback_data_template = OperationType.CALLBACK_DATA_TEMPLATE
            trust_buttons = []

            dict_reply.update(operation=OperationType.ACQ)
            inline_btn_acq = InlineKeyboardButton(
                'Знакомы',
                callback_data=callback_data_template % dict_reply,
            )

            dict_reply.update(operation=OperationType.TRUST)
            inline_btn_trust = InlineKeyboardButton(
                'Доверяю',
                callback_data=callback_data_template % dict_reply,
            )

            dict_reply.update(operation=OperationType.MISTRUST)
            inline_btn_mistrust = InlineKeyboardButton(
                'Не доверяю',
                callback_data=callback_data_template % dict_reply,
            )

            dict_reply.update(operation=OperationType.NULLIFY_ATTITUDE)
            inline_btn_nullify_attitude = InlineKeyboardButton(
                'Не знакомы',
                callback_data=callback_data_template % dict_reply,
            )
            if response_relations:
                attitude = response_relations['from_to']['attitude']
                if attitude == None:
                    trust_buttons = (inline_btn_acq, inline_btn_trust, inline_btn_mistrust, )
                elif attitude == Attitude.ACQ:
                    trust_buttons = (inline_btn_nullify_attitude, inline_btn_trust, inline_btn_mistrust, )
                elif attitude == Attitude.TRUST:
                    trust_buttons = (inline_btn_acq, inline_btn_nullify_attitude, inline_btn_mistrust, )
                elif attitude == Attitude.MISTRUST:
                    trust_buttons = (inline_btn_acq, inline_btn_trust, inline_btn_nullify_attitude, )
                reply_markup.row(*trust_buttons)

            dict_reply.update(operation=OperationType.THANK)
            inline_btn_thank = InlineKeyboardButton(
                'Благодарить',
                callback_data=callback_data_template % dict_reply,
            )
            reply_markup.row(inline_btn_thank)

        inline_btn_trusts = InlineKeyboardButton(
            'Сеть доверия',
            login_url=cls.make_login_url(
                redirect_path=f'{settings.GRAPH_HOST}/?user_trusts={response_to["username"]}' % dict(
                        graph_host=settings.GRAPH_HOST,
                        user_uuid=response_to['uuid'],
                    ),
                bot_username=bot_data["username"],
                keep_user_data='on',
            ))
        login_url_buttons = [inline_btn_trusts, ]

        if editable and not is_org:
            inline_btn_genesis = InlineKeyboardButton(
                'Род',
                login_url=cls.make_login_url(
                    redirect_path=((
                            f'{settings.GRAPH_HOST}/?user_genesis_tree={response_to["username"]}'
                            f'&up=on&down=on&depth=2'
                        )),
                    bot_username=bot_data["username"],
                    keep_user_data='on',
                ))
            login_url_buttons.append(inline_btn_genesis)

        if response_to.get('latitude') is not None and response_to.get('longitude') is not None:
            inline_btn_map = InlineKeyboardButton(
                'Карта',
                login_url=cls.make_login_url(
                    redirect_path='%(map_host)s/?uuid_trustees=%(user_uuid)s' % dict(
                        map_host=settings.MAP_HOST,
                        user_uuid=response_to['uuid'],
                    ),
                bot_username=bot_data["username"],
                keep_user_data='on',
            ))
            login_url_buttons.append(inline_btn_map)
        reply_markup.row(*login_url_buttons)

        callback_data_template = cls.CALLBACK_DATA_UUID_TEMPLATE
        if response_to['is_active'] or response_to['owner']:
            if is_own_account or is_owned_account:
                # Карточка самому пользователю или его родственнику
                #
                inline_btn_iof = InlineKeyboardButton(
                    'Название' if is_org else 'ФИО',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.IOF,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                ))
                inline_btn_photo = InlineKeyboardButton(
                    'Фото',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.PHOTO,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                ))
                edit_buttons_1 = []
                if editable:
                    edit_buttons_1 += [inline_btn_iof, inline_btn_photo,]
                if not is_org:
                    inline_btn_gender = InlineKeyboardButton(
                        'Пол',
                        callback_data=callback_data_template % dict(
                        keyboard_type=KeyboardType.GENDER,
                        uuid=response_to['uuid'],
                        sep=KeyboardType.SEP,
                    ))
                    inline_btn_dates = InlineKeyboardButton(
                        'Д.р.' if is_own_account else 'Даты',
                        callback_data=callback_data_template % dict(
                        keyboard_type=KeyboardType.DATES,
                        uuid=response_to['uuid'],
                        sep=KeyboardType.SEP,
                    ))
                    edit_buttons_1 += [inline_btn_gender, inline_btn_dates,]
                reply_markup.row(*edit_buttons_1)

                inline_btn_location = InlineKeyboardButton(
                    'Место',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.LOCATION,
                    uuid=response_to['uuid'] if is_owned_account else '',
                    sep=KeyboardType.SEP,
                ))
                inline_btn_comment = InlineKeyboardButton(
                    'О себе' if is_own_account else 'Коммент',
                    callback_data=callback_data_template % dict(
                    keyboard_type=KeyboardType.COMMENT,
                    uuid=response_to['uuid'],
                    sep=KeyboardType.SEP,
                ))
                edit_buttons_2 = []
                if editable:
                    edit_buttons_2 += [inline_btn_location, inline_btn_comment]
                else:
                    edit_buttons_1 += [inline_btn_location]
                if editable and is_owned_account:
                    dict_change_owner = dict(
                        keyboard_type=KeyboardType.CHANGE_OWNER,
                        uuid=response_to['uuid'],
                        sep=KeyboardType.SEP,
                    )
                    inline_btn_change_owner = InlineKeyboardButton(
                        'Владелец',
                        callback_data=callback_data_template % dict_change_owner,
                    )
                    edit_buttons_2.append(inline_btn_change_owner)
                    if not response_to['is_dead'] and not is_org:
                        dict_invite = dict(
                            keyboard_type=KeyboardType.INVITE,
                            uuid=response_to['uuid'],
                            sep=KeyboardType.SEP,
                        )
                        inline_btn_invite = InlineKeyboardButton(
                            'Пригласить',
                            callback_data=callback_data_template % dict_invite,
                        )
                        edit_buttons_2.append(inline_btn_invite)
                if edit_buttons_2:
                    reply_markup.row(*edit_buttons_2)

                if editable and not is_org:
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
                    args_relatives = [inline_btn_papa, inline_btn_mama, inline_btn_child, ]
                    if response_to.get('father') or response_to.get('mother'):
                        dict_bro_sis = dict(
                            keyboard_type=KeyboardType.BRO_SIS,
                            uuid=response_to['uuid'],
                            sep=KeyboardType.SEP,
                        )
                        inline_btn_bro_sis = InlineKeyboardButton(
                            'Брат/сестра',
                            callback_data=callback_data_template % dict_bro_sis,
                        )
                        args_relatives.append(inline_btn_bro_sis)
                    reply_markup.row(*args_relatives)

                if editable:
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

        if editable:
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

        if is_own_account and response_to['is_active'] or is_owned_account:
            title_delete = 'Удалить' if is_owned_account else 'Обезличить'
            callback_data_template = cls.CALLBACK_DATA_UUID_TEMPLATE + '%(owner_id)s%(sep)s'
            dict_delete = dict(
                keyboard_type=KeyboardType.DELETE_USER,
                uuid=response_to['uuid'],
                owner_id=user_from_id,
                sep=KeyboardType.SEP,
            )
            inline_btn_delete = InlineKeyboardButton(
                title_delete,
                callback_data=callback_data_template % dict_delete,
            )
            reply_markup.row(inline_btn_delete)

        if is_own_account and not response_to['is_active']:
            callback_data_template = cls.CALLBACK_DATA_UUID_TEMPLATE + '%(owner_id)s%(sep)s'
            dict_undelete = dict(
                keyboard_type=KeyboardType.UNDELETE_USER,
                uuid=response_to['uuid'],
                owner_id=user_from_id,
                sep=KeyboardType.SEP,
            )
            inline_btn_undelete = InlineKeyboardButton(
                'Восстановить',
                callback_data=callback_data_template % dict_undelete,
            )
            reply_markup.row(inline_btn_undelete)

        if reply:
            await cls.send_or_edit_card(bot, reply, reply_markup, response_to, tg_user_from_id, card_message)


    @classmethod
    async def send_or_edit_card(cls, bot, reply, reply_markup, response_to, tg_user_from_id, card_message=None,):
        send_text_message = True
        if response_to.get('photo') and (response_to['is_active'] or response_to['owner']):
            try:
                photo = InputFile.from_url(response_to['photo'], filename='1.png')
                if card_message:
                    await bot.edit_message_caption(
                        chat_id=tg_user_from_id,
                        message_id=card_message.message_id,
                        caption=reply,
                        reply_markup=reply_markup,
                    )
                else:
                    await bot.send_photo(
                        chat_id=tg_user_from_id,
                        photo=photo,
                        disable_notification=True,
                        caption=reply,
                        reply_markup=reply_markup,
                    )
                send_text_message = False
            except BadRequest as excpt:
                if excpt.args[0] == 'Media_caption_too_long' and not card_message:
                    try:
                        await bot.send_photo(
                            chat_id=tg_user_from_id,
                            photo=photo,
                            disable_notification=True,
                        )
                    except:
                        pass
            except:
                raise
        if send_text_message:
            if card_message:
                try:
                    await bot.edit_message_text(
                        chat_id=tg_user_from_id,
                        message_id=card_message.message_id,
                        text=reply,
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                    )
                except:
                    pass
            else:
                parts = safe_split_text(reply, split_separator='\n')
                for part in parts:
                    await bot.send_message(tg_user_from_id, part, reply_markup=reply_markup, disable_web_page_preview=True)


    @classmethod
    def url_photo_to_thumbnail(cls, photo, width, height=None, fill_color='white', frame_width=0):
        """
        Преобразовать url фото в thumbnail url

        Например, из:
            http://api.blagoroda.bsuir.by/media/profile-photo/2024/04/11/326/photo.jpg
        сделать:
            http://api.blagoroda.bsuir.by/thumb/profile-photo/2024/04/11/326/photo.jpg/100x100~crop-white-frame-2~12.jpg
        """
        if not height:
            height = width
        result = photo.lower()
        if width and photo:
            result = result.replace('/media/', '/thumb/', 1)
            result += f'/{width}x{height}~crop-{fill_color}-frame-{frame_width}~12.jpg'
        return result


    @classmethod
    async def get_qrcode(cls, profile, url):
        """
        Получить qrcode профиля profile (байты картинки), где зашит url.

        Возвращает BytesIO qrcod'a, установленный на нулевую позицию
        """

        PHOTO_WIDTH = 100
        PHOTO_FRAME_WIDTH = 2
        PHOTO_FILL_COLOR = 'white'

        qr_code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
        qr_code.add_data(url)
        image = qr_code.make_image(fill_color='black', back_color='white').convert('RGB')
        bytes_io = BytesIO()
        bytes_io.name = f'{profile["username"]}.jpg'

        if profile.get('photo'):
            thumbnail = cls.url_photo_to_thumbnail(
                profile['photo'],
                width=PHOTO_WIDTH,
                fill_color=PHOTO_FILL_COLOR,
                frame_width=PHOTO_FRAME_WIDTH,
            )
            status = photo = None
            async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                try:
                    async with session.request('GET', thumbnail,) as response:
                        status = response.status
                        photo = Image.open(BytesIO(await response.read()))
                except:
                    pass
                if status == 200 and photo:
                    photo_width = PHOTO_WIDTH + PHOTO_FRAME_WIDTH * 2
                    wpercent = photo_width / float(photo.size[0])
                    photo_height = int((float(photo.size[1]) * float(wpercent)))
                    if photo.size[0] != photo_width or photo.size[1] != photo_height:
                        photo = photo.resize((photo_width, photo_height), Image.LANCZOS)
                    pos = (
                        (image.size[0] - photo.size[0]) // 2,
                        (image.size[1] - photo.size[1]) // 2,
                    )
                    image.paste(photo, pos)

        image.save(bytes_io, format='JPEG')
        bytes_io.seek(0)
        return bytes_io


    @classmethod
    def get_lifetime_str(cls, response):
        lifetime = 'д/р - %s\n' % (response['dob'] if response.get('dob') else 'не задано')
        if response.get('dod'):
            lifetime += 'д/с - %s\n' % response['dod']
        elif response.get('is_dead'):
            s_dead = 'умер(ла)'
            gender = response.get('gender')
            if gender:
                s_dead = 'умерла' if gender == 'f' else 'умер'
            lifetime += f'д/с - неизвестна. Известно, что {s_dead}\n'
        return lifetime


    @classmethod
    def get_lifetime_years_str(cls, response):
        lifetime = ''
        if response.get('dob'):
            lifetime += response['dob'][-4:]
        elif response.get('dod') or response.get('is_dead'):
            lifetime += '...'
        if response.get('dod'):
            lifetime += " — %s" % response['dod'][-4:]
        elif response.get('is_dead'):
            lifetime += " — ?"
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
    async def put_user_properties(cls, **kwargs):
        status, response = None, None
        logging.debug('put tg_user_data...')
        payload = dict(tg_token=settings.TOKEN,)
        payload.update(**kwargs)
        logging.debug('put user_data, payload: %s' % cls.secret(payload))
        status, response = await cls.api_request(
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
        result = ' '.join(result) if result else ''
        return result

    @classmethod
    def uuid_from_text(cls, text, unstrip=False):
        user_uuid_to = None
        if unstrip:
            text = '%s-%s-%s-%s-%s'% (text[0:8], text[8:12], text[12:16], text[16:20], text[20:])
        m = re.search(cls.RE_UUID, text)
        if m:
            s = m.group(0)
            try:
                UUID(s)
                user_uuid_to = s
            except (TypeError, ValueError,):
                pass
        return user_uuid_to


    @classmethod
    def sid_from_link(cls, link):
        """
        Короткий ид из ссылки типа t.me/?start=(короткий_ид) или .../t/(короткий_ид)
        """
        if m:= re.search(r'([0-9A-Za-z]{10})$', link):
            return m.group(1)
        return None


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
            status, a_found = await cls.api_request(
                path='/api/profile',
                method='get',
                params=payload_query,
            )
            logging.debug('get users by %s, status: %s' % (what, status, ))
            logging.debug('get users by %s, a_found: %s' % (what, a_found, ))
        return status, a_found

    @classmethod
    def get_youtube_id(cls, link):
        """
        Получить  youtube id из ссылки

        Например,
        link = youtube.com/watch?v=J0dGoFsO_j4
        результат: J0dGoFsO_j4

        Если это не youtube ссылка, то возвращает пустоту
        """
        rr = (
                r'^(?:http[s]?\:\/\/)?(?:www\.)?youtube\.com/watch\/?\?v=(\w{11,11})',
                r'^(?:http[s]?\:\/\/)?youtu\.be/(\w{11,11})',
        )
        for r in rr:
            if m := re.search(r, link, flags=re.I):
                return m.group(1), m.group(0)
        return None

    @classmethod
    async def make_pin_group_message(cls, chat, bot, bot_data):
        """
        Сделать сообщение для последующего закрепления с группе/канале

        Обычно такое сообщение формируется, когда администратор группы/канала
        добавляет бота к числу участников

        Возвращает текст и разметку сообщения
        """
        text = await cls.chat_pin_message_text()
        if text:
            text = text.replace('$BOT_USERNAME$', bot_data['username'])
            if chat.username:
                chat_link = f'<a href="https://t.me/{chat.username}">{chat.title}</a>'
            else:
                chat_link = f'<u>{chat.title}</u>'
            text = text.replace('$CHAT_LINK', chat_link)
        else:
            text = '@' + bot_data['username']
        inline_btn_map = InlineKeyboardButton(
            'Карта',
            login_url=cls.make_login_url(
                redirect_path='%(map_host)s/?chat_id=%(chat_id)s' % dict(
                    map_host=settings.MAP_HOST,
                    chat_id=chat.id,
                ),
                bot_username=bot_data['username'],
                keep_user_data='on',
            ))
        inline_btn_trusts = InlineKeyboardButton(
            'Схема',
            login_url=cls.make_login_url(
                redirect_path='%(graph_host)s/?tgr=%(chat_id)s' % dict(
                    graph_host=settings.GRAPH_HOST,
                    chat_id=chat.id,
                ),
                bot_username=bot_data['username'],
                keep_user_data='on',
            ))
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_map, inline_btn_trusts,)
        return text, reply_markup

    @classmethod
    async def send_pin_group_message(cls, chat, bot, bot_data):
        """
        Отправить сообщение для последующего закрепления с группе/канале

        Обычно такое сообщение формируется, когда администратор группы/канала
        добавляет бота к числу участников

        Ид группы изменяется, когда просто группа становится супергруппой,
        а в закрепленном сообщении будет висеть ид просто группы.
        Посему ид сообщения запоминаем в апи, чтоб когда поймаем
        изменение группа -> супергруппа, изменить ранее закрепленное
        сообщение по его ид функцией bot.edit_message_text
        Возможно ли переход супергруппа -> группа? Не изестно, но учитываем
        возможность. Для канала изменение ид не замечено.
        """
        text, reply_markup = await cls.make_pin_group_message(chat, bot, bot_data)
        try:
            messsage_for_pin = await bot.send_message(
                chat_id=chat.id,
                text=text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except:
            messsage_for_pin = None
        if messsage_for_pin and \
           chat.type in (types.ChatType.GROUP, types.ChatType.SUPERGROUP,) :
            payload = {
                'old_chat_id': chat.id,
                'chat_id': chat.id, 'title': chat.title, 'type': chat.type,
                'pin_message_id' : messsage_for_pin.message_id,
            }
            await TgGroup.put(
                old_chat_id=chat.id, chat_id=chat.id, title=chat.title, type_=chat.type,
                pin_message_id=messsage_for_pin.message_id,
            )
        return messsage_for_pin


    @classmethod
    def get_uuid_from_callback(cls, callback_query):
        """
        Получить uuid из самых распространенных callback_query
        """
        result = None
        if getattr(callback_query, 'message', None) and getattr(callback_query, 'data', None):
            code = (callback_query.data or '').split(KeyboardType.SEP)
            try:
                result = code[1]
                UUID(result)
            except (IndexError, ValueError,):
                pass
        return result

    @classmethod
    def get_sid_from_callback(cls, callback_query):
        """
        Получить username из самых распространенных callback_query
        """
        result = None
        if getattr(callback_query, 'message', None) and getattr(callback_query, 'data', None):
            code = (callback_query.data or '').split(KeyboardType.SEP)
            try:
                result = code[1]
                if not re.search(cls.RE_SID, result):
                    result = None
            except IndexError:
                pass
        return result

    @classmethod
    def check_location_str(cls, message_text):
        latitude, longitude = None, None
        m = re.search(r'([\-\+]?\d+(?:\.\d*)?)\s*\,\s*([\-\+]?\d+(?:\.\d*)?)', message_text)
        if m:
            try:
                latitude_ = float(m.group(1))
                longitude_ = float(m.group(2))
                if -90 <= latitude_ <= 90 and -180 <= longitude_ <= 180:
                    latitude = latitude_
                    longitude = longitude_
                else:
                    raise ValueError
            except ValueError:
                pass
        return latitude, longitude


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
        logging.debug('post group id, payload: %s' % Misc.secret(payload))
        status, response = await Misc.api_request(
            path='/api/bot/group',
            method='post',
            json=payload,
        )
        logging.debug('post group id, status: %s' % status)
        logging.debug('post group id, response: %s' % response)
        return status, response

    @classmethod
    async def put(cls, old_chat_id, chat_id, title, type_, pin_message_id=None):
        payload = {
            'tg_token': settings.TOKEN,
            'old_chat_id': old_chat_id,
            'chat_id': chat_id, 'title': title, 'type': type_,
            'pin_message_id' : pin_message_id,
        }
        logging.debug('modify group, payload: %s' % Misc.secret(payload))
        status, response = await Misc.api_request(
            path='/api/bot/group',
            method='put',
            json=payload,
        )
        logging.debug('modify group, status: %s' % status)
        logging.debug('modify group, response: %s' % response)
        return status, response

    @classmethod
    async def delete(cls, chat_id):
        payload = {'tg_token': settings.TOKEN, 'chat_id': chat_id,}
        logging.debug('delete group id, payload: %s' % Misc.secret(payload))
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
        logging.debug('post group member, payload: %s' % Misc.secret(payload))
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
        logging.debug('delete group member, payload: %s' % Misc.secret(payload))
        status, response = await Misc.api_request(
            path='/api/bot/groupmember',
            method='delete',
            json=payload,
        )
        logging.debug('delete group member, status: %s' % status)
        logging.debug('delete group member, response: %s' % response)
        return status, response
