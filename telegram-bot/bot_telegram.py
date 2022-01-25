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
        <user_id_from>
        <KeyboardType.SEP>
        <user_id_to>,
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

@dp.message_handler(commands=["start", "help",])
async def cmd_start_help(message: types.Message):
    await message.reply("Приветствуем Вас!")

@dp.message_handler(content_types=ContentType.all())
async def echo_send(message: types.Message):

    # NB: \n instead of <br /> !
    reply = 'От Вас получено сообщение.\n'

    msg_is_created = lambda created: 'новый' if created else 'существующий'
    msg_api_error = 'Произошла ошибка при обращении к апи\n'

    user_sender = message.from_user
    sender_photo = await get_user_photo(bot, user_sender)

    payload_sender = dict(
        tg_token=settings.TOKEN,
        tg_uid=message.from_user.id,
        last_name=user_sender.last_name or '',
        first_name=user_sender.first_name or '',
        username=user_sender.username or '',
        photo=sender_photo or '',
    )
    status, response = await api_request(
        path='/api/profile',
        method='post',
        data=payload_sender,
    )
    logging.info('get user_sender, status: %s' % status)
    logging.info('get user_sender, response: %s' % response)

    user_id_from = None
    user_id_to = None
    if status == 200:
        user_id_from = response.get('user_id')
        user_uuid_from = response.get('uuid')
        if user_id_from:
            reply += (
                    'Вы - <u>%(msg_is_created)s</u> пользователь %(frontend_host_title)s'
                    ' '
                    '<a href="%(frontend_host)s/profile/?id=%(user_uuid_from)s"><b>%(full_name)s</b></a>\n'
                ) % dict(
                msg_is_created=msg_is_created(response['created']),
                frontend_host=settings.FRONTEND_HOST,
                user_id_from=user_id_from,
                user_uuid_from=user_uuid_from,
                frontend_host_title=settings.FRONTEND_HOST_TITLE,
                full_name=user_sender.full_name,
            )
    else:
        reply += msg_api_error

    reply_markup = None
    if message.is_forward():
        reply += '\nСообщение было переслано.\n'
        user_forwarded = message.forward_from
        if not user_forwarded:
            reply += (
                'Автор исходного сообщения '
                '<a href="https://telegram.org/blog/unsend-privacy-emoji#anonymous-forwarding">запретил</a> '
                'идентифицировать себя в пересылаемых сообщениях\n'
            )
        elif user_forwarded.is_bot:
            reply += 'Автор исходного сообщения: бот\n'
        else:
            forwarded_photo = await get_user_photo(bot, user_forwarded)
            payload_forwarded = dict(
                tg_token=settings.TOKEN,
                tg_uid=message.forward_from.id,
                last_name=user_forwarded.last_name or '',
                first_name=user_forwarded.first_name or '',
                username=user_forwarded.username or '',
                photo=forwarded_photo or '',
            )
            status, response = await api_request(
                path='/api/profile',
                method='post',
                data=payload_forwarded,
            )
            logging.info('get user_forwarded, status: %s' % status)
            logging.info('get user_forwarded, response: %s' % response)
            if status == 200 and user_id_from:
                user_id_to = response.get('user_id')
                user_uuid_to = response.get('uuid')
                if user_id_to:
                    dict_reply = dict(
                        sep=KeyboardType.SEP,
                        msg_is_created=msg_is_created(response['created']),
                        frontend_host=settings.FRONTEND_HOST,
                        user_id_from=user_id_from,
                        user_id_to=user_id_to,
                        user_uuid_to=user_uuid_to,
                        frontend_host_title=settings.FRONTEND_HOST_TITLE,
                        full_name=user_forwarded.full_name,
                        keyboard_type=KeyboardType.TRUST_THANK,
                    )
                    reply += (
                        'Автор исходного сообщения: <u>%(msg_is_created)s</u> '
                        'пользователь %(frontend_host_title)s'
                        ' '
                        '<a href="%(frontend_host)s/profile/?id=%(user_uuid_to)s"><b>%(full_name)s</b></a>\n'
                    ) % dict_reply
                    if user_id_to != user_id_from:
                        inline_kb_full = InlineKeyboardMarkup()
                        callback_data_template = (
                                '%(keyboard_type)s%(sep)s'
                                '%(operation)s%(sep)s'
                                '%(user_id_from)s%(sep)s'
                                '%(user_id_to)s'
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
                        reply_markup = inline_kb_full
            else:
                reply += msg_api_error

    if user_id_from:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

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
