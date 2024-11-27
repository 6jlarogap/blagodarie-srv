# handler_calls.py
#
# Сallback реакции

import re

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, ContentType, \
                          InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest

from handler_bot import is_it_command

import settings, me
from settings import logging

from common import Misc, OperationType, KeyboardType
from common import FSMnewPerson


router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class FSMgender(StatesGroup):
    ask = State()

class FSMmeet(StatesGroup):
    ask_gender = State()
    ask_dob = State()
    ask_geo = State()

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
    your = '' if response_uuid['owner'] else 'Ваш '
    prompt_gender = (
        f'<b>{response_uuid["first_name"]}</b>.\n\n'
        f'Уточните {your}пол:'
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


async def meet_quest_gender(state):
    data = await state.get_data()
    callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
    callback_data_male = callback_data_template % dict(
        keyboard_type=KeyboardType.MEET_GENDER_MALE,
        sep=KeyboardType.SEP,
    )
    inline_btn_male = InlineKeyboardButton(text='Муж', callback_data=callback_data_male)
    callback_data_female = callback_data_template % dict(
        keyboard_type=KeyboardType.MEET_GENDER_FEMALE,
        sep=KeyboardType.SEP,
    )
    inline_btn_female = InlineKeyboardButton(text='Жен', callback_data=callback_data_female)
    await bot.send_message(
        chat_id=data['tg_user_sender_id'],
        text='Укажите Ваш пол',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_btn_male, inline_btn_female, Misc.inline_button_cancel()]]),
        reply_to_message_id=data['message_id'],
    )


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMmeet.ask_gender))
async def meet_got_gender_text(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    await message.reply(
        Misc.PROMPT_MESSAGE_INSTEAD_OF_GENDER,
        reply_markup=Misc.reply_markup_cancel_row(),
    )


async def meet_quest_dob(state, error_message=None):
    data = await state.get_data()
    text = f'Напишите мне Вашу дату рождения, ' + Misc.PROMPT_DATE_FORMAT
    if error_message:
        text = f'{error_message}\n\n{text}'
    await bot.send_message(
        chat_id=data['tg_user_sender_id'],
        text=text,
        reply_markup=Misc.reply_markup_cancel_row(),
    )


async def meet_quest_geo(state, error_message=None):
    text = Misc.MSG_LOCATION_MANDAT
    if error_message:
        text = f'{error_message}\n\n{text}'
    data = await state.get_data()
    await bot.send_message(
        chat_id=data['tg_user_sender_id'],
        text=text,
        reply_markup=Misc.reply_markup_cancel_row(),
    )


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMmeet.ask_geo))
async def process_message_meet_geo(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    status_from, profile_from = await Misc.post_tg_user(message.from_user)
    if status_from != 200 or profile_from['uuid'] != data['uuid']:
        await state.clear()
        return
    latitude, longitude = Misc.check_location_str(message.text)
    if latitude is None or longitude is None:
        await meet_quest_geo(state, error_message=Misc.MSG_ERR_GEO)
        return
    data.update(latitude=latitude, longitude=longitude)
    await state.clear()
    await meet_do_or_revoke(data)


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMmeet.ask_dob))
async def process_message_meet_dob(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    status_from, profile_from = await Misc.post_tg_user(message.from_user)
    if status_from != 200 or profile_from['uuid'] != data['uuid']:
        await state.clear()
        return
    dob = message.text.strip()
    status, response = await Misc.api_request(
        path='/api/check/date',
        method='get',
        params=dict(date=dob, min_age='10', max_age='100')
    )
    if status == 400:
        await meet_quest_dob(state, error_message=response['message'])
    elif status == 200:
        await state.update_data(dob=dob)
        if data['latitude'] is not None and data['longitude'] is not None:
            await state.clear()
            await meet_do_or_revoke(data)
        else:
            await state.set_state(FSMmeet.ask_geo)
            await meet_quest_geo(state, data)
    else:
        await state.clear()



@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        f'{KeyboardType.MEET_DO}|{KeyboardType.MEET_REVOKE}',
        KeyboardType.SEP,
        # sid_from         # 1
        # KeyboardType.SEP,
        # sid_to           # 2
    )), StateFilter(None))
async def cbq_meet_do_or_revoke(callback: CallbackQuery, state: FSMContext):
    if not (username_from := Misc.get_sid_from_callback(callback)):
        return
    code = callback.data.split(KeyboardType.SEP)
    what = int(code[0])
    status_from, profile_from = await Misc.post_tg_user(callback.from_user)
    if status_from != 200 or profile_from['username'] != username_from:
        return
    text_scram = ''
    if profile_from['did_meet'] and what == KeyboardType.MEET_DO:
        text_scram = 'Вы уже участвуете в игре знакомств'
    elif not profile_from['did_meet'] and what == KeyboardType.MEET_REVOKE:
        text_scram = 'Вы и так не участвуете в игре знакомств'
    if text_scram:
        await callback_query.message.reply(text=text_scram)
        return
    username_inviter = ''
    try:
        username_inviter = code[2]
    except IndexError:
        pass
    data = dict(
        what=what,
        uuid=profile_from['uuid'],
        username_from=profile_from['username'],
        username=profile_from['username'],
        username_inviter=username_inviter,
        gender=profile_from['gender'],
        dob=profile_from['dob'],
        latitude=profile_from['latitude'],
        longitude=profile_from['longitude'],
        tg_user_sender_id=callback.from_user.id,
        message_id=callback.message.message_id,
    )
    await callback.answer()
    if what == KeyboardType.MEET_DO:
        if profile_from['gender'] and profile_from['dob'] and \
           profile_from['latitude'] is not None and profile_from['longitude'] is not None:
            await meet_do_or_revoke(data)
        else:
            if not profile_from['gender']:
                await state.set_state(FSMmeet.ask_gender)
                next_proc = meet_quest_gender
            elif not profile_from['dob']:
                await state.set_state(FSMmeet.ask_dob)
                next_proc = meet_quest_dob
            elif not (profile_from['latitude'] and profile_from['longitude']):
                await state.set_state(FSMmeet.ask_geo)
                next_proc = meet_quest_geo
            await state.update_data(**data)
            await next_proc(state)
    else:
        await meet_do_or_revoke(data)


@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        f'{KeyboardType.MEET_GENDER_FEMALE}|{KeyboardType.MEET_GENDER_MALE}',
        KeyboardType.SEP,
    )), StateFilter(FSMmeet.ask_gender))

async def cbq_meet_ask_gender(callback: CallbackQuery, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(callback.from_user)
    if status_sender != 200 and data.get('uuid') != response_sender['uuid']:
        await state.clear()
        return
    code = callback.data.split(KeyboardType.SEP)
    await state.update_data(gender='m' if int(code[0]) == KeyboardType.MEET_GENDER_MALE else 'f')
    data = await state.get_data()
    next_proc = None
    if not response_sender['dob']:
        await state.set_state(FSMmeet.ask_dob)
        next_proc = meet_quest_dob
    elif response_sender['latitude'] is None or response_sender['longitude'] is None:
        await state.set_state(FSMmeet.ask_geo)
        next_proc = meet_quest_geo
    await callback.answer()
    if next_proc:
        await next_proc(state)
    else:
        await state.clear()
        await meet_do_or_revoke(data)


async def meet_do_or_revoke(data):
    if data['what'] == KeyboardType.MEET_DO:
        count_meet_invited_ = await Misc.count_meet_invited(data.get('uuid'))
        count_meet_invited_.update(already='', vy=Misc.get_html_a(Misc.get_deeplink(data), 'Вы'))
        text_to_sender = Misc.PROMT_MEET_DOING % count_meet_invited_
        did_meet = '1'
    else:
        text_to_sender = (
            'Вы вышли из игры знакомств. Нам вас будет не хватать.\n\n'
            'Для участия в игре знакомств: команда /meet'
        )
        did_meet = ''
    parms = dict(did_meet=did_meet)
    if data['what'] == KeyboardType.MEET_DO:
        fields = ('uuid', 'username_inviter', 'gender', 'dob', 'latitude', 'longitude',)
    else:
        fields = ('uuid', 'username_inviter',)
    for k in fields:
        if k in data:
            parms[k] = data[k]
    status, response = await Misc.put_user_properties(**parms)
    if status == 200:
        reply_markup = None
        if did_meet:
            callback_data_template = Misc.CALLBACK_DATA_SID_TEMPLATE + '%(sid2)s%(sep)s'
            inline_btn_quit = InlineKeyboardButton(
                text='Выйти',
                callback_data=callback_data_template % dict(
                keyboard_type=KeyboardType.MEET_REVOKE,
                sid=data['username_from'],
                sid2=data['username_inviter'],
                sep=KeyboardType.SEP,
            ))
            inline_btn_invite = InlineKeyboardButton(
                text='Пригласить в игру',
                callback_data=Misc.CALLBACK_DATA_KEY_TEMPLATE % dict(
                keyboard_type=KeyboardType.MEET_INVITE,
                sep=KeyboardType.SEP,
            ))
            buttons = [[inline_btn_invite, inline_btn_quit]]
            bot_data = await bot.get_me()
            inline_btn_map = InlineKeyboardButton(
                text='Карта участников игры',
                login_url=Misc.make_login_url(
                    redirect_path=settings.MAP_HOST + '/?meet=on',
                    keep_user_data='on'
            ))
            buttons.append([inline_btn_map])
            reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await bot.send_message(
            data['tg_user_sender_id'],
            text=text_to_sender,
            reply_markup=reply_markup,
        )


@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.MEET_INVITE,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_meet_invite(callback: CallbackQuery, state: FSMContext):
    status, profile = await Misc.post_tg_user(callback.from_user)
    await callback.answer()
    if status == 200:
        url = f'https://t.me/{bot_data.username}?start=m-{profile["username"]}'
        link = Misc.get_html_a(url, 'Вход...')
        caption = f'Перешлите одиноким — приглашение в игру знакомств! {link}'
        bytes_io = await Misc.get_qrcode(profile, url)
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=BufferedInputFile(bytes_io.getvalue(), filename=bytes_io.name),
            caption=caption,
        )


@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.TRUST_THANK,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_attitude(callback: CallbackQuery, state: FSMContext):
    """
    Действия по нажатию кнопок доверия, недоверия, не знакомы

    На входе строка:
        <KeyboardType.TRUST_THANK>          # 0
        <KeyboardType.SEP>
        <operation_type_id>                 # 1
        <KeyboardType.SEP>
        <user_uuid_to (без знаков -)>       # 2
        <KeyboardType.SEP>
        <message_to_forward_id>             # 3
        <KeyboardType.SEP>
        <thank_card>                        # 4, отправлено из карточки после благодарности
        <KeyboardType.SEP>
    """
    callback.answer()
    try:
        code = callback.data.split(KeyboardType.SEP)
        try:
            operation_type_id=int(code[1])
        except (ValueError, IndexError,):
            raise ValueError
        uuid = Misc.uuid_from_text(code[2], unstrip=True)
        if not uuid:
            raise ValueError
        try:
            message_to_forward_id = int(code[3])
        except (ValueError, IndexError,):
            message_to_forward_id = None
        try:
            is_thank_card = bool(code[4])
        except (IndexError,):
            is_thank_card = False
        message = callback.message
        group_member = \
            message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and \
            dict(
                    group_chat_id=message.chat.id,
                    group_title=message.chat.title,
                    group_type=message.chat.type,
            ) \
            or None
        tg_user_sender = callback.from_user
        status_sender, profile_sender = await Misc.post_tg_user(
            tg_user_sender,
            did_bot_start=message.chat.type == ChatType.PRIVATE,
        )
        if status_sender != 200:
            raise ValueError
        if not operation_type_id or operation_type_id not in (
                OperationType.TRUST,
                OperationType.MISTRUST, OperationType.NULLIFY_ATTITUDE,
                OperationType.ACQ, OperationType.THANK,
            ):
            raise ValueError
        status_to, profile_to = await Misc.get_user_by_uuid(uuid)
        if status_to != 200:
            raise ValueError
    except ValueError:
        return

    await callback.answer()

    if profile_sender['uuid'] == profile_to['uuid']:
        text_same = 'Операция на себя не позволяется'
        if group_member:
            if operation_type_id == OperationType.TRUST:
                text_same ='Доверие самому себе не предусмотрено'
            try:
                await bot.answer_callback_query(
                        callback_query.id,
                        text=text_same,
                        show_alert=True,
                    )
            except TelegramBadRequest:
                pass
            return
        else:
            await message.reply(text_same, disable_web_page_preview=True,)
            return

    data = dict(
        tg_user_sender=tg_user_sender,
        profile_from = profile_sender,
        profile_to = profile_to,
        operation_type_id = operation_type_id,
        callback=callback,
        message_to_forward_id = message_to_forward_id,
        group_member=group_member,
        is_thank_card=is_thank_card,
        state=None,
    )
    if group_member:
        group_member.update(user_tg_uid=tg_user_sender.id)
    await Misc.put_attitude(data)


@dp.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CANCEL_THANK,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_cancel_thank(callback: CallbackQuery, state: FSMContext):
    try:
        journal_id = int(callback.data.split(KeyboardType.SEP)[1])
    except (TypeError, ValueError, IndexError,):
        return
    payload = dict(tg_token=settings.TOKEN, journal_id=journal_id)
    logging.debug('cancel thank in api, payload: %s' % Misc.secret(payload))
    status, response = await Misc.api_request(
        path='/api/cancel_thank',
        method='delete',
        json=payload
    )
    logging.debug('cancel thank in api, status: %s' % status)
    logging.debug('cancel thank in api, response: %s' % response)
    reply_markup = callback.message.reply_markup
    if status == 200:
        text = 'Благодарность отменена'
        reply_markup = None
    elif status == 400:
        text = callback.message.text + '\n\n' + response['message']
    else:
        text = callback.message.text + '\n\n' + Misc.MSG_ERROR_API
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup,)
    except TelegramBadRequest:
        pass
