import base64, re
from urllib.parse import urlencode

from aiogram.types.login_url import LoginUrl
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

    # Возможности
    #
    CANCEL_ABILITY = 6

    # Потребности
    #
    CANCEL_WISH = 7

    # Разделитель данных в call back data
    #
    SEP = '~'

class Misc(object):
    """
    Различные функции, сообщения, константы
    """

    MSG_ERROR_API = 'Ошибка доступа к данным'
    MSG_ERROR_TEXT_ONLY = 'Принимается только текст'
    PROMPT_ABILITY = 'Отправьте мне текст с Вашими <b>возможностями</b>'
    PROMPT_WISH = 'Отправьте мне текст с Вашими <b>потребностями</b>'
    
    @classmethod
    def help_text(cls):
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
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.request(
                method.upper(),
                "%s%s" % (settings.API_HOST, path,),
                data=data,
                json=json,
                params=params,
            ) as resp:
                status = resp.status
                if response_type == 'json':
                    response = await resp.json()
                elif response_type == 'text':
                    response = await resp.text('UTF-8')
                return status, response

    @classmethod
    def get_deeplink(cls, response, bot_data):
        """
        Получить ссылку типа http://t.me/BotNameBot?start=:uuid
        """
        return "https://t.me/%(bot_data_username)s?start=%(resonse_uuid)s" % dict(
            bot_data_username=bot_data['username'],
            resonse_uuid=response['uuid']
        )


    @classmethod
    def reply_user_card(cls, response, bot_data, username=None):
        """
        Карточка пользователя, каким он на сайте

        На входе:
        response: ответ от сервера
        username: от телеграма. Если не задано, ищется в response.get('tg_username')

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
        iof = cls.get_iof(response, put_middle_name=bool(response.get('owner_id')))
        lifetime_str = cls.get_lifetime_str(response)
        if lifetime_str:
            lifetime_str += '\n'
        reply = (
                '<b>%(iof)s</b>\n'
                '%(lifetime_str)s'
                'Доверий: %(trust_count)s\n'
                'Благодарностей: %(sum_thanks_count)s\n'
                'Недоверий: %(mistrust_count)s\n'
                '\n'
            ) % dict(
            iof=iof,
            lifetime_str=lifetime_str,
            last_name=response['last_name'],
            trust_count=response['trust_count'],
            sum_thanks_count=response['sum_thanks_count'],
            mistrust_count=response['mistrust_count'],
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
            '<a href="%(frontend_host)s/profile/?id=%(user_from_uuid)s&q=0&map_visible=true">тут</a>'
        ) % dict(
            frontend_host=settings.FRONTEND_HOST,
            user_from_uuid=response['uuid'],
        ) if response.get('latitude') is not None and response.get('longitude') is not None \
            else  'не задано'
        reply += ('Местоположение: %s' % map_text) + '\n\n'

        keys = []
        if not username:
            username = response.get('tg_username')
        if username:
            keys.append("@%s" % username)
        keys += [key['value'] for key in response['keys']]
        keys.append(cls.get_deeplink(response, bot_data))
        keys_text = '\n' + '\n'.join(
            key for key in keys
        ) if keys else 'не задано'

        reply += ('Контакты: %s' % keys_text) + '\n\n'

        return reply

    @classmethod
    def reply_relations(cls, response):
        return '\n'.join((
                'От Вас: %s' % OperationType.relation_text(response['from_to']['is_trust']),
                'К Вам: %s' % OperationType.relation_text(response['to_from']['is_trust']),
                '\n',
            ))

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
            activate=activate,
        )
        try:
            status_sender, response_sender = await cls.api_request(
                path='/api/profile',
                method='post',
                data=payload_sender,
            )
        except:
            status_sender = response_sender = None
        return status_sender, response_sender


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
    async def show_cards(cls,
        a_response_to,
        message,
        bot_data,
        exclude_tg_uids=[],
        response_from={},
        message_to_forward_id='',
    ):
        """
        Показать карточки пользователей
        """
        tg_uids = set(exclude_tg_uids)
        user_from_id = response_from.get('user_id')
        for response_to in a_response_to:
            if response_to.get('tg_uid'):
                if str(response_to['tg_uid']) in tg_uids:
                    continue
                else:
                    tg_uids.add(str(response_to['tg_uid']))
            reply_markup = InlineKeyboardMarkup()
            path = "/profile/?id=%s" % response_to['uuid']
            url = settings.FRONTEND_HOST + path
            login_url = cls.make_login_url(path)
            login_url = LoginUrl(url=login_url)
            inline_btn_go = InlineKeyboardButton(
                'Перейти',
                url=url,
                # login_url=login_url,
            )
            reply_markup.row(inline_btn_go)
            reply = cls.reply_user_card(response_to, bot_data=bot_data)

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
                logging.info('get users relations, status: %s' % status)
                logging.debug('get users relations: %s' % response)
                if status == 200:
                    reply += cls.reply_relations(response)
                    response_relations = response

            if (not user_from_id or user_from_id != response_to['user_id']) and \
               (not response_to.get('tg_uid') or str(bot_data.id) != str(response_to['tg_uid'])):
                dict_reply = dict(
                    keyboard_type=KeyboardType.TRUST_THANK_VER_2,
                    sep=KeyboardType.SEP,
                    user_to_id=response_to['user_id'],
                    message_to_forward_id=message_to_forward_id,
                    group_id='',
                )
                callback_data_template = (
                        '%(keyboard_type)s%(sep)s'
                        '%(operation)s%(sep)s'
                        '%(user_to_id)s%(sep)s'
                        '%(message_to_forward_id)s%(sep)s'
                        '%(group_id)s%(sep)s'
                    )
                dict_reply.update(operation=OperationType.TRUST_AND_THANK)
                inline_btn_thank = InlineKeyboardButton(
                    'Благодарю',
                    callback_data=callback_data_template % dict_reply,
                )
                dict_reply.update(operation=OperationType.MISTRUST)
                inline_btn_mistrust = InlineKeyboardButton(
                    'Не доверяю',
                    callback_data=callback_data_template % dict_reply,
                )
                show_inline_btn_nullify_trust = True
                dict_reply.update(operation=OperationType.NULLIFY_TRUST)
                inline_btn_nullify_trust = InlineKeyboardButton(
                    'Не знакомы',
                    callback_data=callback_data_template % dict_reply,
                )
                if response_relations and response_relations['from_to']['is_trust'] is None:
                    show_inline_btn_nullify_trust = False
                if show_inline_btn_nullify_trust:
                    reply_markup.row(
                        inline_btn_thank,
                        inline_btn_mistrust,
                        inline_btn_nullify_trust
                    )
                else:
                    reply_markup.row(
                        inline_btn_thank,
                        inline_btn_mistrust,
                    )
            if user_from_id and user_from_id == response_to['user_id']:
                # Карточка самому пользователю
                #
                dict_location = dict(
                    keyboard_type=KeyboardType.LOCATION,
                    sep=KeyboardType.SEP,
                )
                callback_data_template = (
                        '%(keyboard_type)s%(sep)s'
                    )
                inline_btn_location = InlineKeyboardButton(
                    'Местоположение',
                    callback_data=callback_data_template % dict_location,
                )
                reply_markup.row(inline_btn_location)

                dict_abwish = dict(
                    keyboard_type=KeyboardType.ABILITY,
                    sep=KeyboardType.SEP,
                )
                callback_data_template = (
                        '%(keyboard_type)s%(sep)s'
                    )
                inline_btn_ability = InlineKeyboardButton(
                    'Возможности',
                    callback_data=callback_data_template % dict_abwish,
                )
                dict_abwish.update(keyboard_type=KeyboardType.WISH)
                inline_btn_wish = InlineKeyboardButton(
                    'Потребности',
                    callback_data=callback_data_template % dict_abwish,
                )
                reply_markup.row(inline_btn_ability, inline_btn_wish)

            if user_from_id:
                # в бот
                await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)
            else:
                # в группу
                await message.answer(reply, reply_markup=reply_markup, disable_web_page_preview=True)

        return bool(tg_uids)


    @classmethod
    def get_iof(cls, response, put_middle_name=True):
        result = '%s %s %s' % (
            response.get('first_name') or '',
            put_middle_name and response.get('middle_name') or '',
            response.get('last_name') or '',
        )
        result = re.sub(r'\s{2,}', ' ', result)
        return result.strip()


    @classmethod
    def get_lifetime_str(cls, response):
        lifetime = ''
        if response.get('owner_id'):
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
        if response.get('owner_id'):
            if response.get('dob'):
                lifetime += response['dob'][-4:]
            elif response.get('dod'):
                lifetime += '...'
            if response.get('dod'):
                lifetime += " – %s" % response['dod'][-4:]
        return lifetime
