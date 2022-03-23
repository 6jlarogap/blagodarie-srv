import base64
from urllib.parse import urlencode

import aiohttp

import settings

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

    # Разделитель данных в call back data
    #
    SEP = '~'

class Misc(object):
    """
    Различные функции, сообщения, константы
    """

    MSG_ERROR_API = 'Ошибка доступа к данным'
    MSG_ERROR_TEXT_ONLY = 'Принимается только текст'
    PROMPT_ABILITY = 'Отправьте мне текст с Вашими <b>возможностями</b>. Введите <i>Отмена</i>, чтоб отказаться'
    PROMPT_WISH = 'Отправьте мне текст с Вашими <b>потребностями</b>. Введите <i>Отмена</i>, чтоб отказаться'
    
    @classmethod
    def help_text(cls):
        return (
            ('Поиск участников %s по:\n' % settings.FRONTEND_HOST_TITLE) + \
            '\n'
            '- @имени участника в телеграме,\n'
            '- фамилии, имени, возможностям, потребностям,\n'
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
    def reply_user_card(cls, response, username=None):
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
        reply = (
                '<b>%(first_name)s %(last_name)s</b>\n'
                'Доверий: %(trust_count)s\n'
                'Благодарностей: %(sum_thanks_count)s\n'
                'Недоверий: %(mistrust_count)s\n'
                '\n'
            ) % dict(
            first_name=response['first_name'],
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
    def make_full_name(cls, profile):
        return (
            '%s %s' % (
                profile.get('first_name', ''),
                profile.get('last_name', ''),
        )).strip()

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
