import logging, re

import settings
from utils import Misc, OperationType, KeyboardType

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.types.login_url import LoginUrl
from aiogram.dispatcher import Dispatcher
from aiogram.utils.executor import start_polling, start_webhook

from aiogram.utils.exceptions import ChatNotFound, CantInitiateConversation

bot = Bot(
    token=settings.TOKEN,
    parse_mode=types.ParseMode.HTML,
)
dp = Dispatcher(bot)

logging.basicConfig(level=settings.LOG_LEVEL)

async def on_startup(dp):
    logging.info('Starting...')
    if settings.START_MODE == 'webhook':
        await bot.set_webhook(settings.WEBHOOK_URL)

async def on_shutdown(dp):
    logging.warning('Shutting down..')
    if settings.START_MODE == 'webhook':
        await bot.delete_webhook()

@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.TRUST_THANK_VER_1,
        KeyboardType.TRUST_THANK_VER_2,
        KeyboardType.SEP,
    ), c.data
    ))
async def process_callback_tn(callback_query: types.CallbackQuery):
    """
    Действия по (не)доверию, благодарностям

    На входе строка:
        <KeyboardType.TRUST_THANK>      # 0
        <KeyboardType.SEP>
        <operation_type_id>             # 1
        <KeyboardType.SEP>
        <user_to_id>                    # 2
        <KeyboardType.SEP>
        <message_to_forward_id>         # 3
        <KeyboardType.SEP>
        ''                              # 4
        например: 1~2~326~387~
    """
    code = callback_query.data.split(KeyboardType.SEP)
    try:
        #TODO это должно устареть (14.02.22)
        if int(code[0]) == KeyboardType.TRUST_THANK_VER_1:
            post = dict(
                tg_token=settings.TOKEN,
                operation_type_id=int(code[1]),
                user_id_from=int(code[2]),
                user_id_to=int(code[3]),
            )
            try:
                message_to_forward_id = int(code[4])
            except (ValueError, IndexError,):
                message_to_forward_id = None
        else:
            post = dict(
                tg_token=settings.TOKEN,
                operation_type_id=int(code[1]),
                tg_user_id_from=str(callback_query.from_user.id),
                user_id_to=int(code[2]),
            )
            try:
                message_to_forward_id = int(code[3])
            except (ValueError, IndexError,):
                message_to_forward_id = None
    except (ValueError, IndexError,):
        return

    logging.debug('post operation, payload: %s' % post)
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post,
    )
    logging.info('post operation, status: %s' % status)
    logging.debug('post operation, response: %s' % response)
    text = text_link = None
    operation_done = False
    if status == 200:
        if post['operation_type_id'] == OperationType.TRUST:
            text = 'Установлено доверие с %(full_name_to)s'
            text_link = 'Установлено доверие с %(full_name_to_link)s'
            operation_done = True
        elif post['operation_type_id'] == OperationType.MISTRUST:
            text = 'Установлено недоверие с %(full_name_to)s'
            text_link = 'Установлено недоверие с %(full_name_to_link)s'
            operation_done = True
        elif post['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Установлено, что не знакомы с %(full_name_to)s'
            text_link = 'Установлено, что не знакомы с %(full_name_to_link)s'
            operation_done = True
        elif post['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            text = 'Отправлена благодарность к %(full_name_to)s'
            text_link = 'Отправлена благодарность к %(full_name_to_link)s'
            operation_done = True
    elif status == 400 and response.get('code', '') == 'already':
        if post['operation_type_id'] == OperationType.TRUST:
            text = 'Уже было установлено доверие'
        elif post['operation_type_id'] == OperationType.MISTRUST:
            text = 'Уже было установлено недоверие'
        elif post['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Вы и так не знакомы'

    if operation_done:
        profile_to = response['profile_to']
        try:
            tg_user_to_uid = profile_to['tg_data']['uid']
        except KeyError:
            tg_user_to_uid = None
        try:
            tg_user_to_username = profile_to['tg_data']['username']
        except KeyError:
            tg_user_to_username = ''
        full_name_to = Misc.make_full_name(profile_to)
        full_name_to_link = (
                '<a href="%(frontend_host)s/profile/?id=%(uuid)s">%(full_name)s</a>'
            ) % dict(
            frontend_host=settings.FRONTEND_HOST,
            uuid=profile_to['uuid'],
            full_name=full_name_to,
        )
        d = dict(
            full_name_to=full_name_to,
            full_name_to_link=full_name_to_link,
        )
        text = text % d
        text_link = text_link % d
        if tg_user_to_username:
            text_link += ' ( @%s )' % tg_user_to_username

    if not text:
        if status == 200:
            text = 'Операция выполнена'
        elif status == 400:
            text = 'Простите, произошла ошибка'
            if response.get('message'):
                text += ': %s' % response['message']
        else:
            text = 'Простите, произошла ошибка'

    if not text_link:
        text_link = text

    # Это отправителю благодарности и т.п.
    #
    await bot.answer_callback_query(
            callback_query.id,
            text=text,
            show_alert=True,
        )
    try:
        await bot.send_message(
            callback_query.from_user.id,
            text=text_link,
            disable_web_page_preview=True,
        )
    except (ChatNotFound, CantInitiateConversation):
        pass

    # Это получателю благодарности и т.п.
    #
    if operation_done and tg_user_to_uid:
        profile_from = response.get('profile_from')

        if post['operation_type_id'] == OperationType.TRUST:
            text_link = 'Установлено доверие с'
        elif post['operation_type_id'] == OperationType.MISTRUST:
            text_link = 'Установлено недоверие с'
        elif post['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text_link = 'Установлено, что не знакомы с'
        elif post['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            text_link = 'Получена благодарность от'

        try:
            tg_user_from_username = profile_from['tg_data']['username']
        except KeyError:
            tg_user_from_username = None
        if tg_user_from_username:
            text_link += ' @%s :' % tg_user_from_username
        else:
            text_link += ':'

        reply = text_link + '\n\n'
        reply += Misc.reply_user_card(
            response=profile_from,
            username=profile_from.get('tg_username_to') or ''
        )
        payload_relation = dict(
            user_id_from=profile_to['uuid'],
            user_id_to=profile_from['uuid'],
        )
        status, response = await Misc.api_request(
            path='/api/user/relations/',
            method='get',
            params=payload_relation,
        )
        logging.info('get users relations, status: %s' % status)
        logging.debug('get users relations: %s' % response)
        if status == 200:
            reply += Misc.reply_relations(response)
            response_relations = response
        else:
            response_relations = None

        reply_markup = InlineKeyboardMarkup()

        path = '/profile/?id=%(uuid)s' % dict(
            frontend_host=settings.FRONTEND_HOST,
            uuid=profile_from['uuid'],
        )
        url = settings.FRONTEND_HOST + path
        login_url = Misc.make_login_url(path)

        inline_btn_go = InlineKeyboardButton(
            'Перейти',
            url=url,
            # login_url=login_url,
        )
        reply_markup.row(inline_btn_go)

        dict_reply = dict(
            keyboard_type=KeyboardType.TRUST_THANK_VER_2,
            sep=KeyboardType.SEP,
            user_to_id=profile_from['user_id'],
            message_to_forward_id='',
        )
        callback_data_template = (
                '%(keyboard_type)s%(sep)s'
                '%(operation)s%(sep)s'
                '%(user_to_id)s%(sep)s'
                '%(message_to_forward_id)s%(sep)s'
            )
        dict_reply.update(operation=OperationType.TRUST_AND_THANK)
        inline_btn_thank = InlineKeyboardButton(
            'Благодарность',
            callback_data=callback_data_template % dict_reply,
        )
        dict_reply.update(operation=OperationType.MISTRUST)
        inline_btn_mistrust = InlineKeyboardButton(
            'Не доверяю',
            callback_data=callback_data_template % dict_reply,
        )
        inline_btn_nullify_trust = None
        if response_relations and response_relations['from_to']['is_trust'] is not None:
            dict_reply.update(operation=OperationType.NULLIFY_TRUST)
            inline_btn_nullify_trust = InlineKeyboardButton(
                'Не знакомы',
                callback_data=callback_data_template % dict_reply,
            )
        if inline_btn_nullify_trust:
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

        if message_to_forward_id:
            try:
                await bot.forward_message(
                    chat_id=tg_user_to_uid,
                    from_chat_id=callback_query.from_user.id,
                    message_id=message_to_forward_id,
                )
            except:
                pass
        try:
            await bot.send_message(
                tg_user_to_uid,
                text=reply,
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        except (ChatNotFound, CantInitiateConversation):
            pass


@dp.message_handler(commands=["help",])
async def cmd_start_help(message: types.Message):
    await message.reply("Перешлите мне сообщение или напишите @имя пользователя чтобы увидеть возможные действия.")

@dp.message_handler(content_types=ContentType.all())
async def echo_send(message: types.Message):
    """
    Обработка остальных сообщений в бот
    
    кнопка /start 
        возвращаем карточку юзера с данными обратившегося пользователя
        и кнопкой перейти и без других кнопок.

    просто сообщение в бот
        смотрим текст если там @username - проверяем -
        если он у нас зарегистрирован - выводим карточку этого @username
        - если не зарегистрирован - или нет в тексте @username
        - отвечаем "Профиль не найден"
        Если передал свой @username в сообщении, показать свою карточку

    пересланное сообщение от самого себя
        показываем карточку профиля автора пересланного сообщения - себя
        - с кнопкой перейти и без других кнопок

    пересланное сообщение от бота
        "Сообщения от ботов пока не обрабатываются"

    пересланное сообщение от того, кто не дает себя аутентифицировать
        "пользователь скрыл..."

    пересланное сообщение от того, кто дал себя аутентифицировать
        карточку профиля Автора пересланного сообщения - со всеми кнопками

    Карточка профиля:
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

        От Вас: доверие
        К Вам: не знакомы

    Кнопки:
        Перейти
        Благодарность   Недоверие   Не знакомы
    """

    if not message.is_forward() and message.content_type != ContentType.TEXT:
        await message.reply(
            'Сюда можно слать только текст или пересылать сообщения любого типа'
        )
        return

    reply = ''
    reply_markup = None

    tg_user_sender = message.from_user

    # Кто будет благодарить... или чей профиль показывать, когда некого благодарить...
    # Это из апи, user_id & profile_dict:
    #
    user_from_id = None
    response_from = dict()

    tg_user_forwarded = None
    message_to_forward_id = None

    # Кого будут благодарить...
    # Это из апи, user_id & profile_dict:
    #
    user_to_id = None
    response_to = dict()

    username_in_text = ''
    state = ''

    if tg_user_sender.is_bot:
        reply = 'Сообщения от ботов пока не обрабатываются'
    else:
        if message.is_forward():
            tg_user_forwarded = message.forward_from
            if not tg_user_forwarded:
                reply = (
                    'Автор исходного сообщения '
                    '<a href="https://telegram.org/blog/unsend-privacy-emoji#anonymous-forwarding">запретил</a> '
                    'идентифицировать себя в пересылаемых сообщениях\n'
                )
            elif tg_user_forwarded.is_bot:
                reply = 'Сообщения, пересланные от ботов, пока не обрабатываются'
            elif tg_user_forwarded.id == tg_user_sender.id:
                state = 'forwarded_from_me'
            else:
                state = 'forwarded_from_other'
        else:
            if message.text == '/start':
                state = 'start'
            else:
                m = re.search(r'\@(\w+)', message.text)
                if m:
                    username_in_text = m.group(1)
                    logging.info('username "@%s" found in message text\n' % username_in_text) 
                    payload_username = dict(
                        tg_token=settings.TOKEN,
                        tg_username=username_in_text,
                    )
                    status, response = await Misc.api_request(
                        path='/api/profile',
                        method='post',
                        data=payload_username,
                    )
                    logging.info('get by username, status: %s' % status)
                    logging.debug('get by username, response: %s' % response_to)
                    if status == 200 and response:
                        if int(response['tg_uid']) == int(tg_user_sender.id):
                            response_from = response
                            user_from_id = response['user_id']
                            state = 'username_from_me'
                        else:
                            response_to = response
                            user_to_id = response['user_id']
                            state = 'username_from_other'
    if state:
        logging.debug('State is: %s' % state)
    if not state and not reply:
        reply = 'Профиль не найден'

    # Сейчас возможные остояния (state)
    #   '': готов ответ. Ничего дальше делать не надо
    #   start
    #   forwarded_from_me
    #   forwarded_from_other
    #   username_from_me:       готовы user_from_id, response_from
    #   username_from_other:    готовы user_to_id, response_to

    if state in ('start', 'forwarded_from_me', 'forwarded_from_other', 'username_from_other'):
        logging.info('get_or_create tg_user_sender data in api...')
        payload_from = dict(
            tg_token=settings.TOKEN,
            tg_uid=tg_user_sender.id,
            last_name=tg_user_sender.last_name or '',
            first_name=tg_user_sender.first_name or '',
            username=tg_user_sender.username or '',
            activate=True,
        )
        try:
            status, response_from = await Misc.api_request(
                path='/api/profile',
                method='post',
                data=payload_from,
            )
            logging.info('get_or_create tg_user_sender data in api, status: %s' % status)
            logging.debug('get_or_create tg_user_sender data in api, response_from: %s' % response_from)
            user_from_id = response_from.get('user_id')
        except:
            pass

    if user_from_id and state == 'forwarded_from_other':
        logging.info('get_or_create tg_user_forwarded data in api...')
        payload_to = dict(
            tg_token=settings.TOKEN,
            tg_uid=tg_user_forwarded.id,
            last_name=tg_user_forwarded.last_name or '',
            first_name=tg_user_forwarded.first_name or '',
            username=tg_user_forwarded.username or '',
            activate=False,
        )
        try:
            status, response_to = await Misc.api_request(
                path='/api/profile',
                method='post',
                data=payload_to,
            )
            logging.info('get_or_create tg_user_forwarded data in api, status: %s' % status)
            logging.debug('get_or_create get tg_user_forwarded data in api, response_to: %s' % response_to)
            user_to_id = response_to.get('user_id')
        except:
            pass

    if user_from_id:
        reply_markup = InlineKeyboardMarkup()
        path = "/profile/?id=%(uuid)s" % dict(
            uuid=response_to['uuid'] if user_to_id else response_from['uuid'],
        )
        url = settings.FRONTEND_HOST + path
        login_url = Misc.make_login_url(path)
        login_url = LoginUrl(url=login_url)
        inline_btn_go = InlineKeyboardButton(
            'Перейти',
            url=url,
            # login_url=login_url,
        )
        reply_markup.row(inline_btn_go)
        username = username_in_text
        if user_to_id:
            response = response_to
            if not username:
                username = tg_user_forwarded and tg_user_forwarded.username
        else:
            response = response_from
            if not username:
                username = tg_user_sender and tg_user_sender.username
        reply = Misc.reply_user_card(response, username)

    if user_from_id and user_to_id:
        payload_relation = dict(
            user_id_from=response_from['uuid'],
            user_id_to=response_to['uuid'],
        )
        status, response = await Misc.api_request(
            path='/api/user/relations/',
            method='get',
            params=payload_relation,
        )
        logging.info('get users relations, status: %s' % status)
        logging.debug('get users relations: %s' % response)
        if status == 200:
            reply += Misc.reply_relations(response)
            response_relations = response
        else:
            response_relations = None

        dict_reply = dict(
            keyboard_type=KeyboardType.TRUST_THANK_VER_2,
            sep=KeyboardType.SEP,
            user_to_id=user_to_id,
            message_to_forward_id=state == 'forwarded_from_other' and message.message_id or ''
        )
        callback_data_template = (
                '%(keyboard_type)s%(sep)s'
                '%(operation)s%(sep)s'
                '%(user_to_id)s%(sep)s'
                '%(message_to_forward_id)s%(sep)s'
            )
        dict_reply.update(operation=OperationType.TRUST_AND_THANK)
        inline_btn_thank = InlineKeyboardButton(
            'Благодарность',
            callback_data=callback_data_template % dict_reply,
        )
        dict_reply.update(operation=OperationType.MISTRUST)
        inline_btn_mistrust = InlineKeyboardButton(
            'Не доверяю',
            callback_data=callback_data_template % dict_reply,
        )
        inline_btn_nullify_trust = None
        if response_relations and response_relations['from_to']['is_trust'] is not None:
            dict_reply.update(operation=OperationType.NULLIFY_TRUST)
            inline_btn_nullify_trust = InlineKeyboardButton(
                'Не знакомы',
                callback_data=callback_data_template % dict_reply,
            )
        if inline_btn_nullify_trust:
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

    if reply:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if user_from_id and response_from.get('created'):
        tg_user_sender_photo = await Misc.get_user_photo(bot, tg_user_sender)
        logging.info('put tg_user_sender_photo...')
        if tg_user_sender_photo:
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=tg_user_sender_photo,
                uuid=response_from['uuid'],
            )
            status, response = await Misc.api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.info('put tg_user_sender_photo, status: %s' % status)
            logging.debug('put tg_user_sender_photo, response: %s' % response)

    if user_to_id and response_to.get('created'):
        tg_user_forwarded_photo = await Misc.get_user_photo(bot, tg_user_forwarded)
        if tg_user_forwarded_photo:
            logging.info('put tg_user_forwarded_photo...')
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=tg_user_forwarded_photo,
                uuid=response_to['uuid'],
            )
            status, response = await Misc.api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.info('put tg_user_forwarded_photo, status: %s' % status)
            logging.debug('put tg_user_forwarded_photo, response: %s' % response)

if __name__ == '__main__':
    if settings.START_MODE == 'poll':
        start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
        )

    elif settings.START_MODE == 'webhook':
        start_webhook(
            dispatcher=dp,
            webhook_path=settings.WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host=settings.WEBAPP_HOST,
            port=settings.WEBAPP_PORT,
    )
    else:
        raise Exception('Unknown START_MODE in settings')
