import logging

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
    await message.reply("Текст помощи в разработке!")

@dp.message_handler(content_types=ContentType.all())
async def echo_send(message: types.Message):

    msg_api_error = 'Произошла ошибка при обращении к апи\n'

    reply_from = ''
    reply_markup = None
    user_sender = message.from_user

    logging.info('get user_sender...')
    payload_sender = dict(
        tg_token=settings.TOKEN,
        tg_uid=message.from_user.id,
        last_name=user_sender.last_name or '',
        first_name=user_sender.first_name or '',
        username=user_sender.username or '',
    )
    status, response = await api_request(
        path='/api/profile',
        method='post',
        data=payload_sender,
    )
    logging.info('get user_sender, status: %s' % status)
    logging.debug('get user_sender, response: %s' % response)

    user_from_id = None
    user_from_uuid = None
    user_from_created = False

    user_to_id = None
    user_to_uuid = None
    user_to_created = False
    if status == 200:
        user_from_id = response.get('user_id')
        user_from_uuid = response.get('uuid')
        user_from_created = response['created']
        if user_from_id:
            reply_from += (
                    '<b>%(first_name)s %(last_name)s</b>\n'
                    'Доверий: %(trust_count)s\n'
                    'Благодарностей: %(sum_thanks_count)s\n'
                    'Недоверий: %(trust_count)s\n'
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
            reply_from += ('Возможности: %s' % abilities_text) + '\n\n'

            wishes_text = '\n'.join(
                wish['text'] for wish in response['wishes']
            ) if response.get('wishes') else 'не задано'
            reply_from += ('Потребности: %s' % wishes_text) + '\n\n'

            map_text = (
                '<a href="%(frontend_host)s/profile/?id=%(user_from_uuid)s&q=1&map_visible=true">тут</a>'
            ) % dict(
                frontend_host=settings.FRONTEND_HOST,
                user_from_uuid=user_from_uuid,
            ) if response.get('latitude') is not None and response.get('longitude') is not None \
              else  'не задано'
            reply_from += ('Местоположение: %s' % map_text) + '\n\n'

            keys = []
            if user_sender.username:
                keys.append("@%s" % user_sender.username)
            keys += [key['text'] for key in response['keys']]
            keys_text = '\n' + '\n'.join(
                key for key in keys
            ) if keys else 'не задано'

            reply_from += ('Контакты: %s' % keys_text) + '\n\n'
            inline_kb_full = InlineKeyboardMarkup()
            inline_btn_go = InlineKeyboardButton(
                'Перейти',
                url="%(frontend_host)s/profile/?id=%(user_from_uuid)s" % dict(
                    frontend_host=settings.FRONTEND_HOST,
                    user_from_uuid=user_from_uuid,
            ))
            inline_kb_full.row(inline_btn_go)
            reply_markup = inline_kb_full

    else:
        reply_from += msg_api_error + '\n'

    reply = ''
    if message.is_forward():
        user_forwarded = message.forward_from
        if not user_forwarded:
            reply += (
                'Автор исходного сообщения '
                '<a href="https://telegram.org/blog/unsend-privacy-emoji#anonymous-forwarding">запретил</a> '
                'идентифицировать себя в пересылаемых сообщениях\n'
            )
        elif user_forwarded.is_bot:
            reply += 'Автор исходного сообщения: бот\n'
        elif user_forwarded.id == user_sender.id:
            reply += (
                'Было переслано сообщение от себя самого\n'
            )
        else:
            logging.info('get user_forwarded...')
            payload_forwarded = dict(
                tg_token=settings.TOKEN,
                tg_uid=message.forward_from.id,
                last_name=user_forwarded.last_name or '',
                first_name=user_forwarded.first_name or '',
                username=user_forwarded.username or '',
            )
            status, response = await api_request(
                path='/api/profile',
                method='post',
                data=payload_forwarded,
            )
            logging.info('get user_forwarded, status: %s' % status)
            logging.debug('get user_forwarded, response: %s' % response)
            if status == 200 and user_from_id:
                user_to_id = response.get('user_id')
                user_to_uuid = response.get('uuid')
                user_to_created = response['created']
            else:
                reply += msg_api_error
    else:
        # Not forwarded message
        # Ищем @username в теле сообщения
        # Потом запрос в апи, есть ли такой @username у нас в базе
        pass

    if user_to_id:
        dict_reply = dict(
            sep=KeyboardType.SEP,
            frontend_host=settings.FRONTEND_HOST,
            user_from_id=user_from_id,
            user_to_id=user_to_id,
            user_to_uuid=user_to_uuid,
            frontend_host_title=settings.FRONTEND_HOST_TITLE,
            full_name=user_forwarded.full_name,
            keyboard_type=KeyboardType.TRUST_THANK,
        )
        reply += (
            'Автор исходного сообщения: '
            'пользователь %(frontend_host_title)s'
            ' '
            '<a href="%(frontend_host)s/profile/?id=%(user_to_uuid)s"><b>%(full_name)s</b></a>\n'
        ) % dict_reply
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
        inline_kb_full.row(
            inline_btn_thank,
            inline_btn_mistrust,
            inline_btn_nullify_trust
        )

    if user_from_id:
        await message.reply(reply_from + reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if user_from_uuid and user_from_created:
        sender_photo = await get_user_photo(bot, user_sender)
        logging.info('put user_sender photo...')
        if sender_photo:
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=sender_photo,
                uuid=user_from_uuid,
            )
            status, response = await api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.info('put user_sender photo, status: %s' % status)
            logging.debug('put user_sender photo, response: %s' % response)

    if user_to_uuid and user_to_created:
        user_forwarded_photo = await get_user_photo(bot, user_forwarded)
        if user_forwarded_photo:
            logging.info('put user_forwarded photo...')
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=user_forwarded_photo,
                uuid=user_to_uuid,
            )
            status, response = await api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.info('put user_forwarded photo, status: %s' % status)
            logging.debug('put user_forwarded photo, response: %s' % response)

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
