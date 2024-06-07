import asyncio
from aiogram import Bot, Dispatcher, enums
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

import settings, me
from settings import logging

storage = MemoryStorage()

async def main_():
    bot = Bot(
        token=settings.TOKEN,
        default=DefaultBotProperties(
            parse_mode=enums.ParseMode.HTML,
    ))
    dp = Dispatcher(storage=storage)
    me.bot = bot
    me.dp = dp
    me.bot_data = await bot.get_me()

    from handler_bot import router as router_bot
    from handler_group import router as router_group
    from handler_callbacks import router as router_callbacks
    dp.include_routers(router_bot, router_group, router_callbacks)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        polling_timeout=20,
    )

asyncio.run(main_())
