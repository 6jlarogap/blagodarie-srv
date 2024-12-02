# handler_offer.py
#
# Команды и сообщения для offer: наши опросы/предложения

import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ContentType
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.enums.message_entity_type import MessageEntityType
from aiogram.exceptions import TelegramBadRequest

import settings, me
from settings import logging

from common import TgGroup, TgGroupMember

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class Offer(object):

    @classmethod
    async def offer_forwarded_in_group_or_channel(cls, message: Message, state: FSMContext):
        result = False
        if message.is_forward() and message.content_type == ContentType.TEXT:
            num_links = 0
            for entity in message.entities:
                m = None
                if entity.type == MessageEntityType.TEXT_LINK:
                    m = re.search(r'(?:start\=offer\-|offer_uuid\=|offer_id\=)([\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12})', entity.url, flags=re.I)
                if m:
                    num_links += 1
                    offer_uuid = m.group(1)
                if num_links >= 2:
                    status_offer, response_offer = await cls.post_offer_answer(offer_uuid, None, [-1])
                    if status_offer == 200:
                        await Misc.show_offer(None, response_offer, message)
                        result = True
                        try:
                            await message.delete()
                        except TelegramBadRequest:
                            pass
                        break
        return result

