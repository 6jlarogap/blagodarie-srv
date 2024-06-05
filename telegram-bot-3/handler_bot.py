# handler_bot.py
#
# Команды и сообщения в бот

import re, redis

from aiogram import Router, F
from aiogram.types import Message, ContentType,  \
                            MessageOriginUser, MessageOriginHiddenUser, \
                            InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter, CommandStart, CommandObject

import settings, me

from common import Misc

router = Router()

@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('graph'))
async def cmd_graph(message: Message, state: FSMContext):
    inline_btn_all_users = InlineKeyboardButton(
        text='Отношения участников',
        login_url=Misc.make_login_url(
            redirect_path=settings.GRAPH_HOST + '/?rod=on&dover=on&withalone=on',
            keep_user_data='on'
    ))
    inline_btn_recent = InlineKeyboardButton(
        text='Недавно добавленные',
        login_url=Misc.make_login_url(
            redirect_path=settings.GRAPH_HOST + '/?f=0&q=50',
            keep_user_data='on'
    ))
    await message.reply(
        text='Выберите тип графика',
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_btn_all_users],[inline_btn_recent]])

    )


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('ya'))
async def cmd_ya(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    await Misc.show_card(
        profile=response_sender,
        profile_sender=response_sender,
        tg_user_sender=message.from_user,
    )


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('help'))
async def cmd_help(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    await message.reply(await Misc.help_text(), disable_web_page_preview=True)



@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, command: CommandObject, state: FSMContext):
    arg = command.args if type(command.args) == str else args[0]
    print('With arg')
    await message.answer(f'With arg: {arg}')


# Просто /start без аргументов. Должно идти после cmd_start_deeplink
#
@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('start'))
async def cmd_start_empty(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    await message.reply(await Misc.help_text(), disable_web_page_preview=True)
    await Misc.show_card(
        profile=response_sender,
        profile_sender=response_sender,
        tg_user_sender=message.from_user,
    )

# Команды в бот закончились.
# Просто сообщение в бот. Должно здесь идти после всех команд в бот

@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None))
async def cmd_message_to_bot(message: Message, state: FSMContext):
    show_response = True
    if message.media_group_id:
        if r := redis.Redis(**settings.REDIS_CONNECT):
            check_str = (
                f'{settings.REDIS_MEDIA_GROUP_PREFIX}'
                f'{message.media_group_id}'
            )
            if r.get(check_str):
                show_response = False
            else:
                r.set(
                    name=check_str,
                    value='1',
                    ex=settings.REDIS_MEDIA_GROUP_TTL,
                )
            r.close()
    if not show_response:
        return

    tg_user_sender = message.from_user
    reply = ''
    is_forward = is_forward_from_other = is_forward_from_me = False
    if tg_user_sender.is_bot:
        reply = 'Сообщения от ботов пока не обрабатываются'
    elif message.content_type == ContentType.PINNED_MESSAGE:
        return
    if message.forward_origin:
        if type(message.forward_origin) == MessageOriginUser:
            if message.forward_origin.sender_user.is_bot:
                reply = 'Сообщения, пересланные от ботов, пока не обрабатываются'
            else:
                is_forward = True
                is_forward_from_me = message.forward_origin.sender_user.id == tg_user_sender.id
                is_forward_from_other = not is_forward_from_me
        elif type(message.forward_origin) == MessageOriginHiddenUser:
            reply = (
                'Автор исходного сообщения '
                '<a href="https://telegram.org/blog/unsend-privacy-emoji#anonymous-forwarding">запретил</a> '
                'идентифицировать себя в пересылаемых сообщениях'
            )
        else:
            # Возможны еще: MessageOriginChannel, MessageOriginChat как АВТОРЫ пересланных сообщений
            reply = 'Пересланное сообщение, автор: группа или канал. Пока такие не обрабатываются'
    else:
        if message.content_type != ContentType.TEXT:
            reply = 'Сюда можно слать текст для поиска, включая @username, или пересылать сообщения любого типа'

    if reply:
        await message.reply(reply)
        return

    message_text = getattr(message, 'text', '') and message.text.strip() or ''
    if not is_forward and message_text.startswith('/'):
        await message.reply('Не известная команда')
        return

    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if m := Misc.get_youtube_id(message_text):
        youtube_id, youtube_link = m
        await Misc.answer_youtube_message(message, youtube_id, youtube_link)
        return


async def is_it_command():
    return ':yes_it_is'
