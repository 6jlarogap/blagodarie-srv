import logging

import settings

from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils.executor import start_polling, start_webhook

from aiogram.utils.exceptions import ChatNotFound, CantInitiateConversation

bot = Bot(token=settings.TOKEN)
dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)

async def on_startup(dp):
    await bot.set_webhook(settings.WEBHOOK_URL)

async def on_shutdown(dp):
    logging.warning('Shutting down..')

@dp.message_handler()
async def echo_send(message: types.Message):
    #await message.answer(message.text)
    #await message.reply(message.text)
    
    try:
        await bot.send_message(message.from_user.id, message.text)
    except (ChatNotFound, CantInitiateConversation):
        pass

if __name__ == '__main__':
    if settings.START_MODE == 'poll':
        start_polling(dp, skip_updates=True)

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
