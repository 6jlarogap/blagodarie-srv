# handler_calls.py
#
# Сallback реакции

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from handler_bot import is_it_command

router = Router()

