import asyncio
import sys
from aiogram import Bot, Dispatcher, enums
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.session.aiohttp import AiohttpSession

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import settings, me
from common import AioHttpSessionManager
from settings import logging

storage = MemoryStorage()

async def main_():
    # DIAGNOSTIC: Add startup logging
    logging.info("=" * 50)
    logging.info("BOT STARTUP DIAGNOSTIC")
    logging.info("=" * 50)
    logging.info(f"Python version: {sys.version}")
    logging.info(f"Settings.DEBUG: {settings.DEBUG}")
    logging.info(f"Settings.TOKEN: {'SET' if settings.TOKEN else 'NOT SET'}")
    logging.info(f"Settings.LOCAL_SERVER: {settings.LOCAL_SERVER}")
    logging.info(f"Settings.HTTP_TIMEOUT: {settings.HTTP_TIMEOUT}")
    logging.info(f"Logging level: {logging.getLogger().level}")
    logging.info(f"Logging handlers: {len(logging.getLogger().handlers)}")
    logging.info("=" * 50)
    
    kwargs_bot = dict(
        token=settings.TOKEN,
        default=DefaultBotProperties(
            parse_mode=enums.ParseMode.HTML,
            link_preview_is_disabled=True,
    ))
    if settings.LOCAL_SERVER:
        kwargs_bot.update(
            session = AiohttpSession(
                api=TelegramAPIServer.from_base(settings.LOCAL_SERVER, is_local=True),
        ))
    bot = Bot(**kwargs_bot)
    dp = Dispatcher(storage=storage)

    me.bot = bot
    me.dp = dp
    me.bot_data = await bot.get_me()
    from handler_bot import router as router_bot
    from handler_callbacks import router as router_callbacks
    from handler_group import router as router_group
    from handler_offer import router as router_offer
    from handler_sympas import router as router_sympas
    from handler_relatives import router as router_relatives

    schedule_start = False
    if settings.SCHEDULE_CRON:
        scheduler = AsyncIOScheduler()
        from common import Schedule
        for task in settings.SCHEDULE_CRON:
            if proc := getattr(Schedule, task, None):
                try:
                    if scheduler.add_job(proc, 'cron', **settings.SCHEDULE_CRON[task]):
                        schedule_start = True
                except:
                    pass
    if schedule_start:
        scheduler.start()

    dp.include_routers(
        router_bot,
        router_callbacks,
        router_group,
        router_offer,
        router_sympas,
        router_relatives,
    )

    await bot.delete_webhook(drop_pending_updates=True)

    try:
        logging.info("Запуск бота...")
        logging.info("Проверка подключения к Telegram API...")
        
        # Test bot connection
        me.bot_data = await bot.get_me()
        logging.info(f"Бот подключен: {me.bot_data.username}")
        
        logging.info("Запуск polling...")
        await dp.start_polling(
            bot,
            polling_timeout=20,
            skip_updates=True
        )
        logging.info("Polling завершен")
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка в боте: {e}", exc_info=True)
        logging.error(f"Тип ошибки: {type(e).__name__}")
        logging.error(f"Аргументы ошибки: {e.args}")
    finally:
        logging.info("Закрытие сессий...")
        # Close application session first
        await AioHttpSessionManager.close()
        
        # Then close bot session
        if bot.session:
            try:
                await bot.session.close()
                logging.info("Сессия бота закрыта")
            except Exception as e:
                logging.error(f"Ошибка при закрытии сессии бота: {e}")
        
        logging.info("Бот завершил работу")

asyncio.run(main_())
