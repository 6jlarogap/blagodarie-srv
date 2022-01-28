import logging, re

import settings
from utils import get_user_photo, api_request, OperationType, KeyboardType

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
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
    lambda c: c.data and c.data.startswith('%s%s' % (
        KeyboardType.TRUST_THANK,
        KeyboardType.SEP,
)))
async def process_callback_tn(callback_query: types.CallbackQuery):
    """
    Действия по (не)доверию, благодарностям

    На входе строка:
        <KeyboardType.TRUST_THANK>
        <KeyboardType.SEP>
        <operation_type_id>
        <KeyboardType.SEP>
        <user_from_id>
        <KeyboardType.SEP>
        <user_to_id>,
        например: 1~2~326~387
    """
    code = callback_query.data.split(KeyboardType.SEP)
    try:
        p = dict(
            tg_token=settings.TOKEN,
            operation_type_id=int(code[1]),
            user_id_from=int(code[2]),
            user_id_to=int(code[3]),
        )
    except (ValueError, IndexError,):
        return
    logging.info('post operation, payload: %s' % p)
    status, response = await api_request(
        path='/api/addoperation',
        method='post',
        data=p,
    )
    logging.info('post operation, status: %s' % status)
    logging.info('post operation, response: %s' % response)
    text = None
    if status == 200:
        if p['operation_type_id'] == OperationType.TRUST:
            text = 'Доверие установлено'
        elif p['operation_type_id'] == OperationType.MISTRUST:
            text = 'Установлено недоверие'
        elif p['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Установлено, что не знакомы'
        elif p['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            text = 'Отправлена благодарность'
    elif status == 400 and response.get('code', '') == 'already':
        if p['operation_type_id'] == OperationType.TRUST:
            text = 'Уже было установлено доверие'
        elif p['operation_type_id'] == OperationType.MISTRUST:
            text = 'Уже было установлено недоверие'
        elif p['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Вы и так не знакомы'

    if not text:
        if status == 200:
            text = 'Операция выполнена'
        elif status == 400:
            text = 'Простите, произошла ошибка'
            if response.get('message'):
                text += ': %s' % response['message']
        else:
            text = 'Простите, произошла ошибка'

    await bot.answer_callback_query(
            callback_query.id,
            text=text,
            show_alert=True,
        )
    try:
        await bot.send_message(
            callback_query.message.chat.id,
            text=text,
        )
    except (ChatNotFound, CantInitiateConversation):
        pass
    #await callback_query.message.delete_reply_markup()

@dp.message_handler(commands=["help",])
async def cmd_start_help(message: types.Message):
    await message.reply("Текст в разработке")

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

    def make_reply(response, username):
        """
        Карточка пользователя, каким он на сайте
        
        response: ответ от сервера
        username: @username в телеграме, если задано
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
            '<a href="%(frontend_host)s/profile/?id=%(user_from_uuid)s&q=1&map_visible=true">тут</a>'
        ) % dict(
            frontend_host=settings.FRONTEND_HOST,
            user_from_uuid=response['uuid'],
        ) if response.get('latitude') is not None and response.get('longitude') is not None \
            else  'не задано'
        reply += ('Местоположение: %s' % map_text) + '\n\n'

        keys = []
        if username:
            keys.append("@%s" % username)
        keys += [key['text'] for key in response['keys']]
        keys_text = '\n' + '\n'.join(
            key for key in keys
        ) if keys else 'не задано'

        reply += ('Контакты: %s' % keys_text) + '\n\n'

        return reply

# ------ starting ------

    reply = ''
    reply_markup = None

    tg_user_sender = message.from_user

    # Кто будет благодарить... или чей профиль показывать, когда некого благодарить...
    # Это из апи, user_id & profile_dict:
    #
    user_from_id = None
    response_from = dict()

    tg_user_forwarded = None

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
                    logging.info('username "@%s" found\n' % username_in_text) 
                    payload_username = dict(
                        tg_token=settings.TOKEN,
                        tg_username=username_in_text,
                    )
                    status, response = await api_request(
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
            status, response_from = await api_request(
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
            status, response_to = await api_request(
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
        inline_btn_go = InlineKeyboardButton(
            'Перейти',
            url="%(frontend_host)s/profile/?id=%(uuid)s" % dict(
                frontend_host=settings.FRONTEND_HOST,
                uuid=response_to['uuid'] if user_to_id else response_from['uuid'],
        ))
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
        reply = make_reply(response, username)

    if user_from_id and user_to_id:
        payload_relation = dict(
            user_id_from=response_from['uuid'],
            user_id_to=response_to['uuid'],
        )
        status, response = await api_request(
            path='/api/user/relations/',
            method='get',
            params=payload_relation,
        )
        logging.info('get users relations, status: %s' % status)
        logging.debug('get users relations: %s' % response)
        if status == 200:
            reply += '\n'.join((
                'От Вас: %s' % OperationType.relation_text(response['to_from']['is_trust']),
                'К Вам: %s' % OperationType.relation_text(response['from_to']['is_trust']),
                '\n',
            ))

        dict_reply = dict(
            sep=KeyboardType.SEP,
            user_from_id=user_from_id,
            user_to_id=user_to_id,
            user_to_uuid=response_to['uuid'],
            frontend_host_title=settings.FRONTEND_HOST_TITLE,
            keyboard_type=KeyboardType.TRUST_THANK,
        )
        callback_data_template = (
                '%(keyboard_type)s%(sep)s'
                '%(operation)s%(sep)s'
                '%(user_from_id)s%(sep)s'
                '%(user_to_id)s'
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
        dict_reply.update(operation=OperationType.NULLIFY_TRUST)
        inline_btn_nullify_trust = InlineKeyboardButton(
            'Не знакомы',
            callback_data=callback_data_template % dict_reply,
        )
        reply_markup.row(
            inline_btn_thank,
            inline_btn_mistrust,
            inline_btn_nullify_trust
        )

    if reply:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if user_from_id and response_from.get('created'):
        tg_user_sender_photo = await get_user_photo(bot, tg_user_sender)
        logging.info('put tg_user_sender_photo...')
        if tg_user_sender_photo:
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=tg_user_sender_photo,
                uuid=response_from['uuid'],
            )
            status, response = await api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.info('put tg_user_sender_photo, status: %s' % status)
            logging.debug('put tg_user_sender_photo, response: %s' % response)

    if user_to_id and response_to.get('created'):
        tg_user_forwarded_photo = await get_user_photo(bot, tg_user_forwarded)
        if tg_user_forwarded_photo:
            logging.info('put tg_user_forwarded_photo...')
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=tg_user_forwarded_photo,
                uuid=response_to['uuid'],
            )
            status, response = await api_request(
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
