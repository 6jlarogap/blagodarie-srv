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

logging.basicConfig(level=logging.INFO)

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
    print(status)
    print(response)

    message_is_forward = message.is_forward()
    user_forwarded = message.forward_from
    if message_is_forward:
        print('MESSAGE IS FORWARDED:')
        if user_forwarded:
            if user_forwarded.is_bot:
                print('Forwaded message user is a bot')
        else:
            print('but the forwarded message user restricts forwarding')
        
    # Не всегда можно получить message.forward_from, даже если пересылаем сообщение,
    # private policy: https://telegram.org/blog/unsend-privacy-emoji#anonymous-forwarding
    if user_forwarded and not user_forwarded.is_bot:
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
        print(status)
        print(response)

    try:
        await bot.send_message(message.from_user.id, message.text)
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
