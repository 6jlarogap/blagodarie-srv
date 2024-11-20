# handler_bot.py
#
# Команды и сообщения в бот
#
# Все команды в бот должны быть здесь. После команд в бот идет обработка
# любого сообщения

import re, redis

from aiogram import Router, F, html
from aiogram.types import Message, ContentType,  \
                            MessageOriginUser, MessageOriginHiddenUser, \
                            InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter, CommandStart, CommandObject

import settings, me
from settings import logging

from common import Misc, FSMnewPerson

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('graph'))
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
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_btn_all_users],[inline_btn_recent]])

    )


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('ya'))
async def cmd_ya(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    await Misc.show_card(
        profile=response_sender,
        profile_sender=response_sender,
        tg_user_sender=message.from_user,
    )


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('help'))
async def cmd_help(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    await message.reply(await Misc.help_text())


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    arg = Misc.arg_deeplink(message.text)
    if not arg:
        # команда /start
        if m := re.search(r'^\s*\/start\s+(.+)', message.text, flags=re.I):
            arg = m.group(1)
    if not arg:
        # Просто /start
        await message.reply(await Misc.help_text())
        await Misc.show_card(
            profile=response_sender,
            profile_sender=response_sender,
            tg_user_sender=message.from_user,
        )
    # elif :
    #     await message.reply(f'arg: ~{arg}~')
    else:
        await message.reply(f'arg: ~{arg}~')

@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command(re.compile('new|new_person')))
async def cmd_new_person(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        if not Misc.editable(response_sender):
            return
        await state.set_state(FSMnewPerson.ask)
        await state.update_data(uuid=response_sender['uuid'])
        await message.reply(Misc.PROMPT_NEW_IOF, reply_markup=Misc.reply_markup_cancel_row())


# Команды в бот закончились.
# Просто сообщение в бот. Должно здесь идти после всех команд в бот

@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None))
async def message_to_bot(message: Message, state: FSMContext):
    # Deeplink. Если щелкнуть по нему, все ок. Если загнать в бот, то никакой реакции
    #
    if message.content_type == ContentType.TEXT and  Misc.arg_deeplink(message.text):
        await cmd_start(message, state)
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


commands_dict = {
    'graph': cmd_graph,
    'ya': cmd_ya,
    'help': cmd_help,
    'new': cmd_new_person,
    'new_person': cmd_new_person,
    'start': cmd_start,
}

async def is_it_command(message: Message, state: FSMContext, excepts=[]):
    """
    Проверка, не обнаружилась ли команда, когда от пользователя ждут данных

    Если обнаружилась, то состояние обнуляется,
    сообщение пользователю, вызов функции, выполняющей команду
    """
    result = False
    if message.content_type == ContentType.TEXT:
        message_text = Misc.strip_text(message.text).lower()
        m = re.search(r'^\/(\S+)', message_text)
        if m:
            command = m.group(1)
            if command in commands_dict and command not in excepts:
                if state:
                    await state.clear()
                await message.reply('%s\n%s /%s' % (
                     Misc.MSG_YOU_CANCELLED_INPUT,
                     'Выполняю команду',
                     command
                ))
                result = True
                await commands_dict[command](message, state)
    return result
