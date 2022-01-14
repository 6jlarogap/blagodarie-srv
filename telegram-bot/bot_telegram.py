import logging

import settings
from utils import get_user_photo, api_request

from aiogram import Bot, types
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

@dp.message_handler()
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
    logging.info(status)
    logging.info(response)

    if status == 200:
        reply += (
                'Вы - <b>%(msg_is_created)s</b> '
                '<a href="%(frontend_host)s?id=%(uuid)s">пользователь %(frontend_host_title)s</a>\n'
            ) % dict(
            msg_is_created=msg_is_created(response['created']),
            frontend_host=settings.FRONTEND_HOST,
            uuid=response['uuid'],
            frontend_host_title=settings.FRONTEND_HOST_TITLE,
        )
    else:
        reply += msg_api_error

    if message.is_forward():
        reply += '\nСообщение было переслано.\n'
        user_forwarded = message.forward_from
        if not user_forwarded:
            logging.info('but the forwarded message user restricts forwarding')
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
            logging.info(status)
            logging.info(response)
            if status == 200:
                reply += (
                    'Автор исходного сообщения: - <b>%(msg_is_created)s</b> '
                    '<a href="%(frontend_host)s?id=%(uuid)s">пользователь %(frontend_host_title)s</a>\n'
                ) % dict(
                    msg_is_created=msg_is_created(response['created']),
                    frontend_host=settings.FRONTEND_HOST,
                    uuid=response['uuid'],
                    frontend_host_title=settings.FRONTEND_HOST_TITLE,
                )
            else:
                reply += msg_api_error

    try:
        await message.reply(reply)
    except (ChatNotFound, CantInitiateConversation):
        pass

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
