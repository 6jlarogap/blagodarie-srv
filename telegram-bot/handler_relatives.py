# handler_offer.py
#
# Команды и сообщения для занесения родственников

import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ContentType, \
                          InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.enums.message_entity_type import MessageEntityType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.state import StatesGroup, State

from handler_bot import is_it_command

import settings, me
from settings import logging

from common import Misc, KeyboardType, OperationType, TgGroup, TgGroupMember

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class FSMpapaMama(StatesGroup):
    ask = State()
    new = State()
    confirm_clear = State()

class FSMchild(StatesGroup):
    parent_gender = State()
    ask = State()
    new = State()
    choose = State()
    confirm_clear = State()

class FSMbroSis(StatesGroup):
    ask = State()
    new = State()


@router.callback_query(F.data.regexp(r'^(%s|%s)%s' % (
        KeyboardType.FATHER, KeyboardType.MOTHER,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_papa_mama(callback: CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы
    """
    code = callback.data.split(KeyboardType.SEP)
    uuid = None
    try:
        uuid = code[1]
    except IndexError:
        pass
    if not uuid:
        await callback.answer()
        return
    tg_user_sender = callback.from_user
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid)
    if not response_sender:
        await callback.answer()
        return
    response_uuid = response_sender['response_uuid']
    is_father = code[0] == str(KeyboardType.FATHER)

    existing_parent = None
    if is_father and response_sender['response_uuid'].get('father'):
        existing_parent = response_sender['response_uuid']['father']
    elif not is_father and response_sender['response_uuid'].get('mother'):
        existing_parent = response_sender['response_uuid']['mother']

    await state.update_data(
        uuid = uuid,
        is_father = is_father,
        existing_parent_uuid = existing_parent['uuid'] if existing_parent else None,
        existing_parent_name = existing_parent['first_name'] if existing_parent else None
    )
    callback_data_new_parent = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
        keyboard_type=KeyboardType.NEW_FATHER if is_father else KeyboardType.NEW_MOTHER,
        uuid=uuid,
        sep=KeyboardType.SEP,
    )
    novy_novaya = 'Новый' if is_father else 'Новая'
    inline_btn_new_papa_mama = InlineKeyboardButton(
        text=novy_novaya,
        callback_data=callback_data_new_parent,
    )
    buttons = [inline_btn_new_papa_mama, ]
    if existing_parent:
        callback_data_clear_parent = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.CLEAR_PARENT,
            uuid=uuid,
            sep=KeyboardType.SEP,
        )
        inline_btn_clear_parent = InlineKeyboardButton(
            text='Очистить',
            callback_data=callback_data_clear_parent,
        )
        buttons.append(inline_btn_clear_parent)
    prompt_papa_mama = (
        'Отправьте мне <u><b>ссылку на профиль %(papy_or_mamy)s</b></u> для '
        '%(response_uuid_name)s '
        'вида t.me/%(bot_data_username)s?start=...\n'
        '\n'
        'Или нажмите <b><u>%(novy_novaya)s</u></b> - для нового профиля %(papy_or_mamy)s\n'
    )
    if existing_parent:
        prompt_papa_mama += (
            '\n'
            'Или нажмите <b><u>Очистить</u></b> - для очистки имеющейся родственной связи: '
            '<b>%(existing_parent_name)s</b> - %(papa_or_mama)s для <b>%(response_uuid_name)s</b>'
        )
    prompt_papa_mama = prompt_papa_mama % dict(
        papa_or_mama='папа' if is_father else 'мама',
        papy_or_mamy='папы' if is_father else 'мамы',
        bot_data_username=bot_data.username,
        response_uuid_name=response_sender['response_uuid']['first_name'],
        existing_parent_name=existing_parent['first_name'] if existing_parent else '',
        novy_novaya=novy_novaya,
    )
    buttons.append(Misc.inline_button_cancel())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[ buttons ])
    await state.set_state(FSMpapaMama.ask)
    await callback.message.reply(
        prompt_papa_mama,
        reply_markup=reply_markup,
    )
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_PARENT,
        KeyboardType.SEP,
    )), StateFilter(FSMpapaMama.ask))
async def cbq_callback_clear_parent(callback: CallbackQuery, state: FSMContext):
    """
    Действия по обнулению папы, мамы
    """
    if not (uuid := Misc.get_uuid_from_callback(callback)):
        await state.clear(); await callback.answer()
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid)
    if not response_sender:
        await state.clear(); await callback.answer()
        return
    data = await state.get_data()
    if not data.get('existing_parent_uuid') or \
        ('is_father' not in data) or \
        not data.get('existing_parent_name') or \
        data.get('uuid') != uuid:
        await state.clear(); await callback.answer()
        return
    existing_parent_name = data['existing_parent_name']
    is_father = data['is_father']
    prompt = (
        'Вы уверены, что хотите очистить родственную связь: '
        '<b>%(existing_parent_name)s</b> - %(papa_or_mama)s для <b>%(response_uuid_name)s</b>?\n\n'
        'Если уверены, нажмите <b><u>Очистить</u></b>'
        ) % dict(
        papa_or_mama='папа' if is_father else 'мама',
        response_uuid_name=response_sender['response_uuid']['first_name'],
        existing_parent_name=existing_parent_name,
    )
    callback_data_clear_parent_confirm = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
        keyboard_type=KeyboardType.CLEAR_PARENT_CONFIRM,
        uuid=uuid,
        sep=KeyboardType.SEP,
    )
    inline_btn_clear_parent_confirm = InlineKeyboardButton(
        text='Очистить',
        callback_data=callback_data_clear_parent_confirm,
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        inline_btn_clear_parent_confirm, Misc.inline_button_cancel()
    ]])
    await state.set_state(FSMpapaMama.confirm_clear)
    await callback.message.reply(
        prompt,
        reply_markup=reply_markup,
    )
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_PARENT_CONFIRM,
        KeyboardType.SEP,
    )), StateFilter(FSMpapaMama.confirm_clear))
async def cbq_callback_clear_parent_confirmed(callback: CallbackQuery, state: FSMContext):
    """
    Действия по обнулению папы, мамы
    """
    if not (uuid := Misc.get_uuid_from_callback(callback)):
        await state.clear(); await callback.answer()
        return
    message = callback.message
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid)
    if not response_sender:
        await state.clear(); await callback.answer()
        return
    data = await state.get_data()
    if not data.get('existing_parent_uuid') or \
       ('is_father' not in data) or \
       not data.get('existing_parent_name') or \
       data.get('uuid') != uuid:
        await state.clear(); await callback.answer()
        return
    existing_parent_uuid = data['existing_parent_uuid']
    is_father = data['is_father']
    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=OperationType.NOT_PARENT,
        user_id_from=response_sender['response_uuid']['uuid'],
        user_id_to=existing_parent_uuid,
    )
    logging.debug('post operation, payload: %s' % Misc.secret(post_op))
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post_op,
    )
    logging.debug('post operation, status: %s' % status)
    logging.debug('post operation, response: %s' % response)
    if not (status == 200 or \
       status == 400 and response.get('code') == 'already'):
        if status == 400  and response.get('message'):
            await message.reply(
                'Ошибка!\n%s\n\nОчищайте родителя по новой' % response['message']
            )
        else:
            await message.reply(Misc.MSG_ERROR_API)
    else:
        if response and response.get('profile_from') and response.get('profile_to'):
            await bot.send_message(
                callback.from_user.id,
                Misc.PROMPT_PAPA_MAMA_CLEARED % dict(
                    iof_from = Misc.get_deeplink_with_name(response['profile_from'], plus_trusts=True),
                    iof_to = Misc.get_deeplink_with_name(response['profile_to'], plus_trusts=True),
                    papa_or_mama='папа' if is_father else 'мама',
            ))
        else:
            await message.reply('Связь Ребенок - Родитель очищена')
    await state.clear()
    await callback.answer()

