# handler_calls.py
#
# Сallback реакции

import re

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, ContentType, \
                          InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ChatType

from handler_bot import is_it_command

import settings, me
from settings import logging

from common import Misc, KeyboardType
from common import FSMnewPerson


router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class FSMgender(StatesGroup):
    ask = State()

@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CANCEL_ANY,
        KeyboardType.SEP,
        )))
async def cbq_cancel_any(callback: CallbackQuery, state: FSMContext):
    if state:
        await callback.message.answer(Misc.MSG_YOU_CANCELLED_INPUT)
        await state.clear()
        await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMnewPerson.ask))
async def enter_new_person_name(message: Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_NEW_IOF,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    if await is_it_command(message, state):
        return
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        await state.update_data(first_name=message.text.strip())
        await state.set_state(FSMnewPerson.ask_gender)
        await new_iof_ask_gender(message, state)
    else:
        await state.clear()
        await message.reply(Misc.MSG_ERROR_API)


async def new_iof_ask_gender(message: Message, state: FSMContext):
    data = await state.get_data()
    callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
    callback_data_male = callback_data_template % dict(
        keyboard_type=KeyboardType.NEW_IOF_GENDER_MALE,
        sep=KeyboardType.SEP,
    )
    inline_btn_male = InlineKeyboardButton(text='Муж', callback_data=callback_data_male)
    callback_data_female = callback_data_template % dict(
        keyboard_type=KeyboardType.NEW_IOF_GENDER_FEMALE,
        sep=KeyboardType.SEP,
    )
    inline_btn_female = InlineKeyboardButton(text='Жен', callback_data=callback_data_female)
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        inline_btn_male, inline_btn_female, Misc.inline_button_cancel()
    ]])
    await message.reply(
        '<u>' + data['first_name'] + '</u>:\n\n' + 'Укажите пол', reply_markup=reply_markup,)


@dp.callback_query(F.data.regexp(r'^(%s|%s)%s$' % (
        KeyboardType.NEW_IOF_GENDER_MALE, KeyboardType.NEW_IOF_GENDER_FEMALE,
        KeyboardType.SEP,
    )), StateFilter(FSMnewPerson.ask_gender))
async def cbq_gender_new_person(callback: CallbackQuery, state: FSMContext):
    gender = 'm' if callback.data.split(KeyboardType.SEP)[0] == str(KeyboardType.NEW_IOF_GENDER_MALE) else 'f'
    status_sender, response_sender = await Misc.post_tg_user(callback.from_user)
    data = await state.get_data()
    if status_sender == 200 and \
       response_sender['uuid'] == data.get('uuid') and \
       data.get('first_name'):
        payload_iof = dict(
            tg_token=settings.TOKEN,
            owner_id=response_sender['user_id'],
            first_name=data['first_name'],
            gender=gender,
        )
        logging.debug('post iof, payload: %s' % Misc.secret(payload_iof))
        status, response = await Misc.api_request(
            path='/api/profile',
            method='post',
            data=payload_iof,
        )
        logging.debug('post iof, status: %s' % status)
        logging.debug('post iof, response: %s' % response)
        if status == 200:
            await callback.message.reply('Добавлен' if gender == 'm' else 'Добавлена')
            await Misc.show_card(
                profile=response,
                profile_sender=response_sender,
                tg_user_sender=callback.from_user,
            )
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.GENDER,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_gender(callback: CallbackQuery, state: FSMContext):
    if not (uuid := Misc.getuuid_from_callback(callback)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid)
    if not response_sender:
        return
    response_uuid = response_sender['response_uuid']
    dict_gender = dict(
        keyboard_type=KeyboardType.GENDER_MALE,
        sep=KeyboardType.SEP,
    )
    callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
    inline_button_male = InlineKeyboardButton(text='Муж', callback_data=callback_data_template % dict_gender)
    dict_gender.update(keyboard_type=KeyboardType.GENDER_FEMALE)
    inline_button_female = InlineKeyboardButton(text='Жен', callback_data=callback_data_template % dict_gender)
    await state.set_state(FSMgender.ask)
    await state.update_data(uuid=uuid)
    his_her = Misc.his_her(response_uuid) if response_uuid['owner'] else 'Ваш'
    prompt_gender = (
        f'<b>{response_uuid["first_name"]}</b>.\n\n'
        f'Уточните {his_her} пол:'
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        inline_button_male, inline_button_female, Misc.inline_button_cancel()
    ]])
    await callback.message.reply(
        prompt_gender,
        reply_markup=reply_markup,
    )
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMgender.ask))
async def got_gender_text(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    await message.reply(
        (
            'Ожидается выбор пола, нажатием одной из кнопок, в сообщении выше.\n\n'
            'Или отмените выбор пола, нажав сейчас <u>Отмена</u>'
        ),
        reply_markup=Misc.reply_markup_cancel_row(),
    )


@dp.callback_query(F.data.regexp(r'^(%s|%s)%s$' % (
        KeyboardType.GENDER_MALE, KeyboardType.GENDER_FEMALE,
        KeyboardType.SEP,
    )), StateFilter(FSMgender.ask))
async def cbq_gender(callback: CallbackQuery, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(callback.from_user)
    if status_sender == 200:
        data = await state.get_data()
        if data.get('uuid'):
            response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=data['uuid'])
            if response_sender:
                gender = 'm' if callback.data.split(KeyboardType.SEP)[0] == str(KeyboardType.GENDER_MALE) else 'f'
                status, response = await Misc.put_user_properties(
                    uuid=data['uuid'],
                    gender=gender,
                )
                if status == 200 and response:
                    s_gender = 'мужской' if gender == 'm' else 'женский'
                    deeplink = Misc.get_deeplink_with_name(response)
                    await callback.message.reply(
                        text= f'{deeplink}\nУстановлен пол: {s_gender}',
                    )
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.LOCATION,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_location(callback: CallbackQuery, state: FSMContext):
    """
    Действия по местоположению

    На входе строка:
        <KeyboardType.LOCATION>             # 0
        <KeyboardType.SEP>
        uuid                                # 1
        <KeyboardType.SEP>
    """
    tg_user_sender = callback.from_user
    code = callback.data.split(KeyboardType.SEP)
    try:
        uuid = code[1]
        if uuid and not await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid):
            return
    except IndexError:
        uuid = None
    await callback.answer()
    if uuid:
        await Misc.prompt_location(callback.message, state, uuid=uuid)
