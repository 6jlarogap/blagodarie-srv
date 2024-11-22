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
from aiogram.fsm.state import StatesGroup, State

import settings, me
from settings import logging

from common import Misc, FSMnewPerson, FSMgeo

import pymorphy3
MorphAnalyzer = pymorphy3.MorphAnalyzer()

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class FSMquery(StatesGroup):
    ask = State()

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


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('setplace'))
async def cmd_setplace(message: Message, state: FSMContext):
    await Misc.prompt_location(message, state)

@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command('start'))
async def cmd_start(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    arg = Misc.arg_deeplink(message.text)
    if not arg:
        # команда /start
        if m := re.search(r'^\s*\/start\s+(.+)', message.text, flags=re.I):
            arg = (m.group(1) or '').lower()
    if not arg:
        # Просто /start
        await message.reply(await Misc.help_text())
        await Misc.show_card(
            profile=response_sender,
            profile_sender=response_sender,
            tg_user_sender=message.from_user,
        )
    elif arg == 'setplace':
        await Misc.prompt_location(message, state)
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


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(None), Command(re.compile('findpotr|findvozm|findperson')))
async def cmd_find(message: Message, state: FSMContext):
    message_text = message.text.split()[0].lstrip('/')
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        if not Misc.editable(response_sender):
            return
        if message_text == 'findpotr':
            what = 'query_wish'
        elif message_text == 'findvozm':
            what = 'query_ability'
        elif message_text == 'findperson':
            what = 'query_person'
        else:
            return
        await state.set_state(FSMquery.ask)
        await state.update_data(what=what)
        await message.reply(Misc.PROMPT_QUERY[what], reply_markup=Misc.reply_markup_cancel_row())


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
    'setplace': cmd_setplace,
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


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMgeo.geo))
async def process_location_input(message: Message, state: FSMContext):
    """
    Записать местоположение пользователя телеграма или uuid в состоянии
    """
    if message.content_type == ContentType.TEXT:
        if await is_it_command(message, state):
            return
    else:
        await message.answer(Misc.MSG_ERR_GEO, reply_markup=Misc.reply_markup_cancel_row())
        return
    await put_location(message, state, show_card=True)


async def put_location(message, state, show_card=False):
    """
    Записать местоположение пользователя телеграма

    В случае успеха:
        Если show_card == True, то вернуть профиль карточки с новыми координатами
        Вернуть профиль пользователя
    Иначе вернуть пустой словарь
    """
    result = {}
    reply_markup = None
    user_uuid = None
    data = await state.get_data()
    user_uuid = data.get('uuid')
    latitude = longitude = None
    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender == 200:
        if not user_uuid:
            user_uuid = response_sender.get('uuid')
        latitude, longitude = Misc.check_location_str(message.text)
        if latitude is None or longitude is None:
            await message.answer(Misc.MSG_ERR_GEO, reply_markup=Misc.reply_markup_cancel_row())
            return
        else:
            status, response = await Misc.put_user_properties(
                uuid=user_uuid,
                latitude = latitude,
                longitude = longitude,
            )
            if status == 200:
                result = response
                if show_card:
                    await Misc.show_card(
                        profile=response_sender,
                        profile_sender=response,
                        tg_user_sender=tg_user_sender,
                    )
                    await message.reply('Координаты записаны', reply_markup=reply_markup)
            else:
                await message.reply('Ошибка записи координат', reply_markup=reply_markup)
    await state.clear()
    return result


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMquery.ask))
async def process_find_input(message: Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    data = await state.get_data()
    try:
        what = data['what']
    except KeyError:
        pass
    else:
        a_found = None
        if message.content_type != ContentType.TEXT:
            reply_markup = Misc.reply_markup_cancel_row()
            await message.reply(
                Misc.MSG_ERROR_TEXT_ONLY + '\n\n' +  Misc.PROMPT_QUERY[what],
                reply_markup=Misc.reply_markup_cancel_row(),
            )
            return
        if len(message.text.strip()) < settings.MIN_LEN_SEARCHED_TEXT:
            reply = Misc.PROMPT_SEARCH_TEXT_TOO_SHORT
        else:
            search_phrase = Misc.text_search_phrase(
                message.text,
                MorphAnalyzer,
            )
            print(search_phrase)
            if not search_phrase:
                reply = Misc.PROMPT_SEARCH_PHRASE_TOO_SHORT
            else:
                status, a_found = await Misc.search_users(what, search_phrase)
                if status != 200:
                    a_found = None
                elif not a_found:
                    reply = Misc.PROMPT_NOTHING_FOUND
        if a_found:
            await Misc.show_deeplinks(a_found, message)
        elif reply:
            await message.reply(reply)
    await state.clear()
