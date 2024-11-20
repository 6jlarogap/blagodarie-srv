# handler_group.py
#
# Команды и сообщения в группы и каналы

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from common import TgGroup, TgGroupMember
import settings, me
from settings import logging


router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

@router.message(F.text, F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP)), Command("group"))
async def cmd_start(message: Message):
    await message.answer(
        f'Группы!',
    )
