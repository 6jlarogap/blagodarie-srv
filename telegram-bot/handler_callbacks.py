# handler_callbacks.py
#
# Сallback реакции

import re, base64

from aiogram import Router, F, html
from aiogram.filters import Command, StateFilter
from aiogram.filters.logic import or_f
from aiogram.types import Message, CallbackQuery, ContentType, \
                          InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from handler_bot import is_it_command

import settings, me
from settings import logging

from common import Misc, OperationType, KeyboardType, Rcache
from common import FSMnewPerson, FSMdelete, FSMaskMoney

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class FSMgender(StatesGroup):
    ask = State()

class FSMmeet(StatesGroup):
    ask_gender = State()
    ask_dob = State()
    ask_geo = State()
    ask_bank = State()
    ask_tgdesc = State()

class FSMexistingIOF(StatesGroup):
    ask = State()

class FSMphoto(StatesGroup):
    ask = State()
    remove = State()

class FSMdates(StatesGroup):
    dob = State()
    dod = State()

class FSMcomment(StatesGroup):
    ask = State()

class FSMundelete(StatesGroup):
    ask = State()

class FSMsendMessage(StatesGroup):
    ask = State()

class FSMpersonDesc(StatesGroup):
    ask = State()

class FSMbanking(StatesGroup):
    ask = State()

@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
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


@router.callback_query(F.data.regexp(r'^(%s|%s)%s$' % (
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


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.GENDER,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_gender(callback: CallbackQuery, state: FSMContext):
    if not (uuid := Misc.get_uuid_from_callback(callback)):
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


@router.callback_query(F.data.regexp(r'^(%s|%s)%s$' % (
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


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
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


async def meet_quest_bank(state):
    data = await state.get_data()
    await bot.send_message(
        chat_id=data['tg_user_sender_id'],
        text=Misc.PROMPT_BANK,
        reply_markup=Misc.reply_markup_cancel_row(),
    )


async def meet_quest_tgdesc(state):
    data = await state.get_data()
    await bot.send_message(
        chat_id=data['tg_user_sender_id'],
        text=Misc.PROMPT_USER_DESC,
        reply_markup=Misc.reply_markup_cancel_row(),
    )


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMmeet.ask_tgdesc))
async def process_message_meet_tgdesc(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    status_from, profile_from = await Misc.post_tg_user(message.from_user)
    if status_from != 200 or profile_from['uuid'] != data['uuid']:
        await state.clear()
        return
    status, response, is_first = await do_get_user_desc(message, state)
    if status == 200:
        data.update(tgdesc_first=is_first)
    await state.clear()
    await meet_do_or_revoke(data)


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
    await state.update_data(latitude=latitude, longitude=longitude)
    if not data['has_bank']:
        await state.set_state(FSMmeet.ask_bank)
        await meet_quest_bank(state)
    elif not data['has_tgdesc']:
        await state.set_state(FSMmeet.ask_tgdesc)
        await meet_quest_tgdesc(state)
    else:
        await state.clear()
        data.update(latitude=latitude, longitude=longitude)
        await meet_do_or_revoke(data)


@router.message(F.text, F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMmeet.ask_bank))
async def process_message_meet_bank(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    status_from, profile_from = await Misc.post_tg_user(message.from_user)
    if status_from != 200 or profile_from['uuid'] != data['uuid']:
        await state.clear()
        return
    bank = message.text.strip()
    await state.update_data(bank=bank)
    if not data['has_tgdesc']:
        await state.set_state(FSMmeet.ask_tgdesc)
        await meet_quest_tgdesc(state)
    else:
        await state.clear()
        data.update(bank=bank)
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
        if data['latitude'] is None or data['longitude'] is None:
            await state.set_state(FSMmeet.ask_geo)
            await meet_quest_geo(state)
        elif not data['has_bank']:
            await state.set_state(FSMmeet.ask_bank)
            await meet_quest_bank(state)
        elif not data['has_tgdesc']:
            await state.set_state(FSMmeet.ask_tgdesc)
            await meet_quest_tgdesc(state)
        else:
            await state.clear()
            data.update(dob=dob)
            await meet_do_or_revoke(data)
    else:
        await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
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
        text_scram = 'Вы уже участвуете в игре знакомств. Выход из игры: посредством команды /meet'
    elif not profile_from['did_meet'] and what == KeyboardType.MEET_REVOKE:
        text_scram = 'Вы и так не участвуете в игре знакомств. Для участия: команда /meet'
    if text_scram:
        await callback.message.reply(text=text_scram)
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
        has_bank=profile_from['has_bank'],
        bank='',
        has_tgdesc=profile_from['has_tgdesc'],
        tg_user_sender_id=callback.from_user.id,
        message_id=callback.message.message_id,
    )
    await callback.answer()
    if what == KeyboardType.MEET_DO:
        next_proc = None
        if not profile_from['gender']:
            await state.set_state(FSMmeet.ask_gender)
            next_proc = meet_quest_gender
        elif not profile_from['dob']:
            await state.set_state(FSMmeet.ask_dob)
            next_proc = meet_quest_dob
        elif not (profile_from['latitude'] and profile_from['longitude']):
            await state.set_state(FSMmeet.ask_geo)
            next_proc = meet_quest_geo
        elif not profile_from['has_bank']:
            await state.set_state(FSMmeet.ask_bank)
            next_proc = meet_quest_bank
        elif not profile_from['has_tgdesc']:
            await state.set_state(FSMmeet.ask_tgdesc)
            next_proc = meet_quest_tgdesc
        if next_proc:
            await state.update_data(**data)
            await next_proc(state)
            return
    await meet_do_or_revoke(data)


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        f'{KeyboardType.MEET_GENDER_FEMALE}|{KeyboardType.MEET_GENDER_MALE}',
        KeyboardType.SEP,
    )), StateFilter(FSMmeet.ask_gender))

async def cbq_meet_ask_gender(callback: CallbackQuery, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(callback.from_user)
    if status_sender != 200 and data.get('uuid') != response_sender['uuid']:
        await state.clear()
        return
    code = callback.data.split(KeyboardType.SEP)
    gender = 'm' if int(code[0]) == KeyboardType.MEET_GENDER_MALE else 'f'
    await state.update_data(gender=gender)
    data = await state.get_data()
    next_proc = None
    if not response_sender['dob']:
        await state.set_state(FSMmeet.ask_dob)
        next_proc = meet_quest_dob
    elif response_sender['latitude'] is None or response_sender['longitude'] is None:
        await state.set_state(FSMmeet.ask_geo)
        next_proc = meet_quest_geo
    elif not data['has_bank']:
        await state.set_state(FSMmeet.ask_bank)
        next_proc = meet_quest_bank
    elif not data['has_tgdesc']:
        await state.set_state(FSMmeet.ask_tgdesc)
        next_proc = meet_quest_tgdesc
    await callback.answer()
    if next_proc:
        await next_proc(state)
    else:
        await state.clear()
        data.update(gender=gender)
        await meet_do_or_revoke(data)


async def meet_do_or_revoke(data):
    did_meet = '1' if data['what'] == KeyboardType.MEET_DO else ''
    if not did_meet or ('tgdesc_first' not in data) or data['tgdesc_first']:
        if did_meet:
            count_meet_invited_ = await Misc.count_meet_invited(data.get('uuid'))
            count_meet_invited_.update(already='', vy=Misc.get_html_a(Misc.get_deeplink(data), 'Вы'))
            text_to_sender = Misc.PROMT_MEET_DOING % count_meet_invited_
        else:
            text_to_sender = ('Вы вышли из игры знакомств. Нам вас будет не хватать')
        parms = dict(did_meet=did_meet)
        if data['what'] == KeyboardType.MEET_DO:
            fields = ['uuid', 'username_inviter', 'gender', 'dob', 'latitude', 'longitude',]
            if data.get('bank'):
                fields.append('bank')
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
                        redirect_path=settings.MEET_HOST,
                        keep_user_data='on'
                ))
                buttons.append([inline_btn_map])
                reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot.send_message(
                data['tg_user_sender_id'],
                text=text_to_sender,
                reply_markup=reply_markup,
            )
        elif status == 400 and response.get('message'):
            await bot.send_message(
                data['tg_user_sender_id'],
                text=f'Ошибка ввода данных: {response["message"]}'
            )


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
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


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.TRUST_THANK,
        KeyboardType.SEP,
    )),
    StateFilter(None)
)
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
        <card_type>                         # 4,
                    '1':    отправлено из карточки после благодарности
                    '2':    отправлено из карточки вместе с описанием
        <KeyboardType.SEP>
    """
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
            card_type = code[4]
            is_thank_card = code[4] == '1'
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

    if profile_sender['uuid'] == profile_to['uuid']:
        text_same = 'Операция на себя не позволяется'
        if group_member:
            if operation_type_id == OperationType.TRUST:
                text_same ='Доверие самому себе не предусмотрено'
            try:
                await bot.answer_callback_query(
                        callback.id,
                        text=text_same,
                        show_alert=True,
                     )
            except TelegramBadRequest:
                pass
        else:
            await message.reply(text_same,)
        await callback.answer()
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
        state=state,
    )
    if group_member:
        group_member.update(user_tg_uid=tg_user_sender.id)
    await Misc.put_attitude(data)
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
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
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.IOF,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_existing_iof(callback: CallbackQuery, state: FSMContext):
    """
    Заменить имя, фамилию, отчество или название организации
    """
    if not (uuid := Misc.get_uuid_from_callback(callback)):
        return
    if not (response_sender := await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid)):
        return
    response_uuid = response_sender['response_uuid']
    await state.set_state(FSMexistingIOF.ask)
    await state.update_data(uuid=uuid, is_org=response_uuid['is_org'])
    await bot.send_message(
        callback.from_user.id,
        (Misc.PROMPT_EXISTING_ORG if response_uuid['is_org'] else Misc.PROMPT_EXISTING_IOF) % dict(
            name=response_uuid['first_name'],
        ),
        reply_markup=Misc.reply_markup_cancel_row(),
    )
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMexistingIOF.ask))
async def process_existing_iof(message: Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(Misc.MSG_ERROR_TEXT_ONLY, reply_markup=Misc.reply_markup_cancel_row())
        return
    if await is_it_command(message, state):
        return
    first_name = Misc.strip_text(message.text)
    data = await state.get_data()
    if not first_name or re.search(Misc.RE_UUID, first_name) or len(first_name) < 5:
        await message.reply(
            Misc.PROMPT_ORG_INCORRECT if data.get('is_org') else Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    if uuid := data.get('uuid'):
        response_sender = await Misc.check_owner_by_uuid(
            owner_tg_user=message.from_user,
            uuid=uuid
        )
        if response_sender:
            status, response = await Misc.put_user_properties(
                uuid=uuid,
                first_name=first_name,
            )
            if status == 200:
                await message.reply('Изменено')
                await Misc.show_card(
                    profile=response,
                    profile_sender=response_sender,
                    tg_user_sender=message.from_user,
                )
    await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.PHOTO,       # 0
        KeyboardType.SEP,
        # uuid, кому              # 1
        # KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_photo(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        inline_button_cancel = Misc.inline_button_cancel()
        await state.set_state(FSMphoto.ask)
        await state.update_data(uuid=uuid)
        prompt_photo = Misc.PROMPT_PHOTO
        status, response = await Misc.get_user_by_uuid(uuid)
        if status == 200 and Misc.is_photo_downloaded(response):
            prompt_photo += '\n' + Misc.PROMPT_PHOTO_REMOVE
            callback_data_remove = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                keyboard_type=KeyboardType.PHOTO_REMOVE,
                sep=KeyboardType.SEP,
                uuid=uuid,
            )
            inline_btn_remove = InlineKeyboardButton(
                text='Удалить',
                callback_data=callback_data_remove,
            )
            buttons = [[inline_button_cancel, inline_btn_remove]]
        else:
            buttons = [[inline_button_cancel]]
        await callback.message.reply(prompt_photo, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMphoto.ask))
async def process_photo(message: Message, state: FSMContext):
    if message.content_type != ContentType.PHOTO or \
       message.photo[-1].file_size > settings.DOWNLOAD_PHOTO_MAX_SIZE * 1024 * 1024:
        await message.reply(
            Misc.MSG_ERROR_PHOTO_ONLY,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    data = await state.get_data()
    if response_check := await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=data.get('uuid')):
        image = await Misc.get_file_bytes(message.photo[-1])
        image = base64.b64encode(image).decode('UTF-8')
        status_put, response_put = await Misc.put_user_properties(
            uuid=data['uuid'],
            photo=image,
        )
        msg_error = '<b>Ошибка</b>. Фото не внесено.\n'
        if status_put == 200:
            await message.reply(f'{Misc.get_deeplink_with_name(response_put)} : фото внесено')
            await Misc.show_card(response_put, response_check, message.from_user)
        elif status_put == 400:
            if response_put.get('message'):
                await message.reply(msg_error + response_put['message'])
            else:
                await message.reply(msg_error + Misc.MSG_ERROR_API)
        else:
            await message.reply(msg_error + Misc.MSG_ERROR_API)
    else:
        await message.reply(msg_error + Misc.MSG_ERROR_API)
    await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.PHOTO_REMOVE,      # 0
        KeyboardType.SEP,
        # uuid, кому                    # 1
        # KeyboardType.SEP,
    )), StateFilter(FSMphoto.ask))
async def process_callback_photo_remove(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        inline_btn_remove = InlineKeyboardButton(
            text='Да, удалить',
            callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                keyboard_type=KeyboardType.PHOTO_REMOVE_CONFIRMED,
                sep=KeyboardType.SEP,
                uuid=uuid,
        ))
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[Misc.inline_button_cancel(), inline_btn_remove]]
        )
        prompt_photo_confirm = (
            'Подтвердите <b>удаление фото</b> у:\n'
            f'<b>{response_check["response_uuid"]["first_name"]}</b>\n'
        )
        await state.set_state(FSMphoto.remove)
        await callback.message.reply(prompt_photo_confirm, reply_markup=reply_markup)
    else:
        await state.clear()
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.PHOTO_REMOVE_CONFIRMED,      # 0
        KeyboardType.SEP,
        # uuid, кому                    # 1
        # KeyboardType.SEP,
    )), StateFilter(FSMphoto.remove))
async def cbq_photo_remove_confirmed(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        logging.debug('put (remove) photo: post tg_user data')
        status_put, response_put = await Misc.put_user_properties(
            photo='',
            uuid=uuid,
        )
        if status_put == 200:
            await callback.message.reply(f'{Misc.get_deeplink_with_name(response_put)} : фото удалено')
            await Misc.show_card(response_put, response_check, callback.from_user)
        elif status_put == 400:
            if response_put.get('message'):
                await message.reply(msg_error + response_put['message'])
            else:
                await message.reply(msg_error + Misc.MSG_ERROR_API)
        else:
            await message.reply(msg_error + Misc.MSG_ERROR_API)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.DATES,
        KeyboardType.SEP,
        # uuid, кому                    # 1
        # KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_dates(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        response_uuid = response_check['response_uuid']
        his_her = Misc.his_her(response_uuid) if response_uuid['owner'] else 'Ваш'
        title_dob_unknown = 'Не знаю'
        prompt_dob = (
            f'<b>{response_uuid["first_name"]}</b>\n\n'
            f'Укажите {his_her} день рождения '
        ) + Misc.PROMPT_DATE_FORMAT
        if not response_uuid['owner']:
            prompt_dob += (
                f'\n\nЕсли хотите скрыть дату своего рождения '
                f'или в самом деле не знаете, когда Ваш день рождения, нажмите <u>{title_dob_unknown}</u>'
            )
        inline_button_dob_unknown = InlineKeyboardButton(
            text=title_dob_unknown, callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.DATES_DOB_UNKNOWN,
            sep=KeyboardType.SEP,
            uuid=uuid,
        ))
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[inline_button_dob_unknown, Misc.inline_button_cancel()]]
        )
        await state.set_state(FSMdates.dob)
        await state.update_data(uuid=uuid)
        await callback.message.reply(
            prompt_dob,
            reply_markup=reply_markup,
        )
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.DATES_DOB_UNKNOWN,
        KeyboardType.SEP,
    )), StateFilter(FSMdates.dob))
async def cbq_dates_dob_unknown(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        await state.update_data(dob=None)
        if (profile := response_check['response_uuid'])['owner']:
            await draw_dod(profile, callback.message, state)
        else:
            await put_dates(callback.message, state, callback.from_user)
    await callback.answer()


async def draw_dod(profile, message, state):
    if profile['gender']:
        is_male = profile['gender'] == 'm'
        s_alive = 'Жив' if is_male else 'Жива'
        s_alive_or_dont_know = s_alive + ' или не знаю'
        s_dead = 'Умер' if is_male else 'Умерла'
        s_dead_none_title = s_dead + ', дату не знаю'
        his_her = 'его' if is_male else 'её'
        he_she = 'он' if is_male else 'она'
        prompt_dod = (
            f'<b>{profile["first_name"]}</b>\n\n'
            f'Нажмите <u>{s_alive_or_dont_know}</u>, если {s_alive.lower()} или Вы не знаете, {s_dead.lower()} {he_she} или нет\n\n'
            f'Или нажмите <u>{s_dead_none_title}</u>, если {s_dead.lower()}, но Вы не знаете, когда {he_she} {s_dead.lower()}\n\n'
            f'Или укажите дату {his_her} смерти {Misc.PROMPT_DATE_FORMAT}, если она Вам известна'
        )
    else:
        s_alive = 'Жив(а)'
        s_alive_or_dont_know = 'Жив(а) или не знаю'
        s_dead = 'Умер(ла)'
        s_dead_none_title = s_dead + ', дату не знаю'
        prompt_dod = (
            f'<b>{profile["first_name"]}</b>\n\n'
            f'Нажмите <u>{s_alive_or_dont_know}</u>, если {s_alive.lower()} или Вы не знаете, {s_dead.lower()} или нет\n\n'
            f'Или нажмите <u>{s_dead_none_title}</u>, если {s_dead.lower()}, но Вы не знаете дату смерти\n\n'
            f'Или укажите дату смерти {Misc.PROMPT_DATE_FORMAT}'
        )
    callback_data_template = Misc.CALLBACK_DATA_UUID_TEMPLATE
    dict_callback = dict(
        keyboard_type=KeyboardType.DATES_DOD_NONE,
        sep=KeyboardType.SEP,
        uuid=profile['uuid'],
    )
    inline_button_alive = InlineKeyboardButton(
        text=s_alive_or_dont_know,
        callback_data=callback_data_template % dict_callback
    )
    dict_callback.update(keyboard_type=KeyboardType.DATES_DOD_DEAD)
    inline_button_dead = InlineKeyboardButton(
        text=s_dead_none_title,
        callback_data=callback_data_template % dict_callback
    )
    reply_markup = InlineKeyboardMarkup(
        inline_keyboard=[[inline_button_alive, inline_button_dead, Misc.inline_button_cancel()]]
    )
    await state.set_state(FSMdates.dod)
    await message.reply(
        prompt_dod,
        reply_markup=reply_markup,
    )


async def put_dates(message, state, tg_user_sender):
    data = await state.get_data()
    if data.get('uuid') and \
       (response_check := await Misc.check_owner_by_uuid(tg_user_sender, data['uuid'])):
        dob = data.get('dob') or ''
        dod = data.get('dod') or ''
        is_dead = data.get('is_dead') or dod or ''
        status_put, response_put = await Misc.put_user_properties(
            uuid=data['uuid'],
            dob=dob,
            dod=dod,
            is_dead = '1' if is_dead else '',
        )
        if status_put == 200:
            await Misc.show_card(response_put, response_check, tg_user_sender)
        elif status_put == 400 and response_put.get('message'):
            dates = 'даты' if response_check['response_uuid']['owner'] else 'дату рождения'
            await message.reply(f'Ошибка!\n{response_put["message"]}\n\nНазначайте {dates} по новой')
        else:
            await message.reply(Misc.MSG_ERROR_API)
    await state.clear()


@router.callback_query(F.data.regexp(r'^(%s|%s)%s' % (
        KeyboardType.DATES_DOD_NONE, KeyboardType.DATES_DOD_DEAD,
        KeyboardType.SEP,
    )), StateFilter(FSMdates.dod))
async def cbq_dates_dod_done_or_dead(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        code = callback.data.split(KeyboardType.SEP)
        await state.update_data(
            dod=None,
            is_dead=code[0] == str(KeyboardType.DATES_DOD_DEAD)
        )
        await put_dates(callback.message, state, callback.from_user)
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMdates.dob))
async def process_dob(message: Message, state: FSMContext):
    if (message.content_type != ContentType.TEXT) or \
       not (message_text := Misc.strip_text(message.text)):
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    if (uuid := data.get('uuid')) and \
       (response_check := await Misc.check_owner_by_uuid(message.from_user, uuid)):
        await state.update_data(dob=message_text)
        if (profile := response_check['response_uuid'])['owner']:
            await draw_dod(profile, message, state)
        else:
            await put_dates(message, state, message.from_user)


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMdates.dod))
async def process_dod(message: Message, state: FSMContext):
    if (message.content_type != ContentType.TEXT) or \
       not (message_text := Misc.strip_text(message.text)):
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    if (uuid := data.get('uuid')) and \
       (response_check := await Misc.check_owner_by_uuid(message.from_user, uuid)):
        await state.update_data(dod=message_text)
        await put_dates(message, state, message.from_user)


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.COMMENT,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_comment(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        await state.set_state(FSMcomment.ask)
        await state.update_data(uuid=uuid)
    await callback.message.reply(
        f'Введите комментарий для:\n{response_check["response_uuid"]["first_name"]}',
        reply_markup=Misc.reply_markup_cancel_row(),
    )
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMcomment.ask))
async def process_comment(message: Message, state: FSMContext):
    if (message.content_type != ContentType.TEXT) or \
       not (message_text := message.text.strip()):
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    if (uuid := data.get('uuid')) and \
       (response_check := await Misc.check_owner_by_uuid(message.from_user, uuid)):
        status_put, response_put = await Misc.put_user_properties(
            uuid=uuid,
            comment=message_text,
        )
        if status_put == 200:
            await message.reply(
                f'{"Изменен" if response_check["response_uuid"]["comment"] else "Добавлен"} комментарий'
            )
            await Misc.show_card(response_put, response_check, message.from_user)
    await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.DELETE_USER,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_delete_user(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        profile = response_check['response_uuid']
        owner = response_check
        if profile['is_active'] or profile['owner']:
            prompt, reply_markup = Misc.message_delete_user(profile, owner)
            await state.set_state(FSMdelete.ask)
            await state.update_data(uuid=uuid, owner_id=owner['user_id'])
            await callback.message.reply(prompt, reply_markup=reply_markup)
        else:
            await callback.message.reply('Профиль уже обезличен')
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.DELETE_USER_CONFIRMED,
        KeyboardType.SEP,
    )), StateFilter(FSMdelete.ask))
async def cbq_delete_user_confirmed(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # Удаление! Доп. проверки!
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)) and \
       data.get('uuid') and data.get('owner_id') and \
       response_check['user_id'] == data['owner_id'] and \
       response_check['response_uuid']['uuid'] == data['uuid'] and \
       uuid == data['uuid']:

        profile = response_check['response_uuid']; 
        profile_sympa = None
        if profile['r_sympa_username']:
            status_r_sympa, profile_sympa = await Misc.get_user_by_sid(profile['r_sympa_username'])
            if status_r_sympa != 200:
                profile_sympa = None
        if profile['owner']:
            msg_debug = 'delete owned user, '
            msg_deleted = f'Профиль <u>{response_check["response_uuid"]["first_name"]}</u> удалён'
        else:
            msg_debug = 'depersonalize user, '
            msg_deleted = 'Теперь Вы обезличены'

        payload = dict(tg_token=settings.TOKEN, uuid=uuid, owner_id=data['owner_id'])
        logging.debug(msg_debug + 'payload: %s' % Misc.secret(payload))
        status_delete, response_delete = await Misc.api_request(
            path='/api/profile',
            method='delete',
            data=payload,
        )
        logging.debug(msg_debug + 'status: %s' % status_delete)
        logging.debug(msg_debug + 'response: %s' % response_delete)
        if status_delete == 400:
            await callback.message.reply('Ошибка: %s' % response['message'])
        elif status_delete != 200:
            await callback.message.reply('Неизвестная ошибка')
        else:
            await callback.message.reply(msg_deleted)
            if not profile['owner']:
                await Misc.show_card(response_delete, response_check, callback.from_user)
                if profile_sympa:
                    for tgd in profile_sympa['tg_data']:
                        try:
                            await bot.send_message(
                                tgd['tg_uid'],
                                text=(
                                    f'Симпатия к Вам отменена. Приглашайте новых игроков '
                                    f'и ставьте больше интересов на '
                                    f'<a href="{settings.MEET_HOST}">карте</a> - '
                                    f'чтобы скорее найти совпадения!'
                            ))
                        except (TelegramBadRequest, TelegramForbiddenError):
                            pass
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.UNDELETE_USER,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_undelete_user(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        profile = response_check['response_uuid']
        owner = response_check
        if profile['uuid'] == owner['uuid']:
            if profile['is_active']:
                await callback.message.reply('Вы уже восстановлены')
            else:
                prompt = (
                    f'<b>{profile["first_name"]}</b>\n'
                    '\n'
                    'Вы собираетесь <u>восстановить</u> себя и свои данные в системе.\n'
                    '\n'
                    'Если подтверждаете, то нажмите <u>Продолжить</u>. Иначе <u>Отмена</u>\n'
                )
                inline_btn_go = InlineKeyboardButton(
                    text='Продолжить',
                    callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                        keyboard_type=KeyboardType.UNDELETE_USER_CONFIRMED,
                        uuid=profile['uuid'],
                        sep=KeyboardType.SEP,
                ))
                reply_markup = InlineKeyboardMarkup(inline_keyboard=[[inline_btn_go, Misc.inline_button_cancel()]])
                await state.set_state(FSMundelete.ask)
                await callback.message.reply(prompt, reply_markup=reply_markup)
    await callback.answer()

@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.UNDELETE_USER_CONFIRMED,
        KeyboardType.SEP,
    )), StateFilter(FSMundelete.ask))
async def cbq_udelete_user_confirmed(callback: CallbackQuery, state: FSMContext):
    if (uuid := Misc.get_uuid_from_callback(callback)) and \
       (response_check := await Misc.check_owner_by_uuid(callback.from_user, uuid)):
        profile = response_check['response_uuid']
        owner = response_check
        if profile['uuid'] == owner['uuid'] and not profile['is_active']:
            logging.debug('un-depersonalize user')
            status, response = await Misc.post_tg_user(callback.from_user, activate=True)
            if status == 400:
                await callback.message.reply('Ошибка: %s' % response['message'])
            elif status != 200:
                await callback.message.reply('Неизвестная ошибка')
            else:
                await callback.message.reply(
                    "Ваш профиль восстановлен."
                )
                status_photo, response_photo = await Misc.update_user_photo(callback.from_user, response)
                if status_photo == 200:
                    response = response_photo
                await Misc.show_card(response, response, callback.from_user)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SEND_MESSAGE,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_send_message(callback: CallbackQuery, state: FSMContext):
    if uuid := Misc.get_uuid_from_callback(callback):
        status_to, profile_to = await Misc.get_user_by_uuid(uuid)
        if status_to == 200:
            await state.set_state(FSMsendMessage.ask)
            await state.update_data(uuid=uuid)
            iof_link = Misc.get_deeplink_with_name(profile_to)
            await callback.message.reply(
                f'Напишите или перешлите мне сообщение для отправки <b>{iof_link}</b>',
                reply_markup=Misc.reply_markup_cancel_row(),
            )
    await callback.answer()

@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMsendMessage.ask))
async def process_message_to_send(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    msg_saved = 'Сообщение сохранено'
    data = await state.get_data()
    if data.get('uuid'):
        status_to, profile_to = await Misc.get_user_by_uuid(data['uuid'], with_owner_tg_data=True)
        if status_to == 200:
            status_from, profile_from = await Misc.post_tg_user(message.from_user)
            if status_from == 200:
                # первое сообщение в коллаже или единственное
                is_first = True
                if message.media_group_id:
                    key = (
                        f'{Rcache.SEND_MESSAGE_PREFIX}{Rcache.KEY_SEP}'
                        f'{message.from_user.id}{Rcache.KEY_SEP}{message.media_group_id}'
                    )
                    is_first = Misc.redis_is_key_first_up(key, ex=300)

                # Возможны варианты с получателем:
                #   - самому себе                               нет смысла отправлять
                #   - своему овнеду                             нет смысла отправлять
                #   - чужому овнеду с владельцем с телеграмом
                #   - чужому овнеду с владельцем без телеграма  нет смысла отправлять
                #   - юзеру с телеграмом
                #   - юзеру без телеграма                       нет смысла отправлять

                # Есть ли смысл отправлять и если есть то кому?
                #
                tg_user_to_tg_data = []
                user_to_delivered_uuid = None
                if profile_from['uuid'] == profile_to['uuid']:
                    # самому себе
                    user_to_delivered_uuid = profile_to['uuid']
                elif profile_to['owner'] and profile_to['owner']['uuid'] == profile_from['uuid']:
                    # своему овнеду
                    pass
                elif profile_to['owner'] and profile_to['owner']['uuid'] != profile_from['uuid']:
                    # чужому овнеду: телеграм у него есть?
                    if profile_to['owner'].get('tg_data'):
                        tg_user_to_tg_data = profile_to['owner']['tg_data']
                        user_to_delivered_uuid = profile_to['owner']['uuid']
                elif profile_to.get('tg_data'):
                    tg_user_to_tg_data = profile_to['tg_data']
                    user_to_delivered_uuid = profile_to['uuid']
                if tg_user_to_tg_data:
                    success = False
                    for tgd in tg_user_to_tg_data:
                        try:
                            if is_first:
                                await bot.send_message(
                                    tgd['tg_uid'],
                                    text=Misc.MSG_YOU_GOT_MESSAGE % Misc.get_deeplink_with_name(profile_from),
                                )
                            await bot.copy_message(
                                tgd['tg_uid'],
                                from_chat_id=message.chat.id,
                                message_id=message.message_id,
                            )
                            success = True
                        except (TelegramBadRequest, TelegramForbiddenError):
                            pass
                    if success:
                        msg_delivered = 'Сообщение доставлено'
                    else:
                        msg_delivered = msg_saved
                        user_to_delivered_uuid = None
                    if is_first:
                        await message.reply(msg_delivered)
                else:
                    if is_first:
                        await message.reply(msg_saved)
            payload_log_message = dict(
                tg_token=settings.TOKEN,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                user_from_uuid=profile_from['uuid'],
                user_to_uuid=profile_to['uuid'],
                user_to_delivered_uuid=user_to_delivered_uuid,
            )
            try:
                status_log, response_log = await Misc.api_request(
                    path='/api/tg_message',
                    method='post',
                    json=payload_log_message,
                )
            except:
                pass
    await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SHOW_MESSAGES,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_show_messages(callback: CallbackQuery, state: FSMContext):
    if user_to_uuid := Misc.get_uuid_from_callback(callback):
        tg_user_sender = callback.from_user
        status_from, profile_from = await Misc.post_tg_user(callback.from_user)
        if status_from == 200:
            payload = dict(
                tg_token=settings.TOKEN,
                user_from_uuid=profile_from['uuid'],
                user_to_uuid=user_to_uuid,
            )
            logging.debug('get_user_messages, payload: %s' % Misc.secret(payload))
            status, response = await Misc.api_request(
                path='/api/tg_message/list',
                method='post',
                json=payload,
            )
            logging.debug('get_user_messages, status: %s' % status)
            logging.debug('get_user_messages, response: %s' % response)
            if status == 200:
                if response:
                    await bot.send_message(
                        tg_user_sender.id,
                        text='Ниже последние сообщения к %s ...' % \
                            Misc.get_deeplink_with_name(response[0]['user_to']),
                    )
                    n = 0
                    for i in range(len(response)-1, -1, -1):
                        m = response[i]
                        n += 1
                        msg = (
                            '(%(n)s) %(datetime_string)s\n'
                            'От %(user_from)s к %(user_to)s\n'
                        )
                        if m['operation_type_id']:
                            if m['operation_type_id'] == OperationType.NULLIFY_ATTITUDE:
                                msg += 'в связи с тем что не знаком(а)\n'
                            elif m['operation_type_id'] == OperationType.ACQ:
                                msg += 'в связи с установкой знакомства\n'
                            elif m['operation_type_id'] == OperationType.MISTRUST:
                                msg += 'в связи с утратой доверия\n'
                            elif m['operation_type_id'] == OperationType.TRUST:
                                msg += 'в связи с тем что доверяет\n'
                            elif m['operation_type_id'] == OperationType.THANK:
                                msg += 'с благодарностью\n'
                        user_to_delivered = None
                        if m['user_to_delivered']:
                            msg += 'Доставлено'
                            if m['user_to_delivered']['id'] != m['user_to']['id']:
                                msg += ' к %(user_to_delivered)s !!!'
                                user_to_delivered = Misc.get_deeplink_with_name(m['user_to_delivered'])
                        else:
                            msg += 'Не доставлено, лишь сохранено'
                        msg += '\nНиже само сообщение:'
                        msg %= dict(
                            n=n,
                            datetime_string=Misc.datetime_string(m['timestamp']),
                            user_from=Misc.get_deeplink_with_name(m['user_from']),
                            user_to=Misc.get_deeplink_with_name(m['user_to']),
                            user_to_delivered=user_to_delivered,
                        )
                        await bot.send_message(tg_user_sender.id, text=msg)
                        await bot.forward_message(
                            tg_user_sender.id,
                            from_chat_id=m['from_chat_id'],
                            message_id=m['message_id'],
                        )
                else:
                    status_to, profile_to = await Misc.get_user_by_uuid(user_to_uuid)
                    if status_to == 200:
                        msg = '%(full_name)s не получал%(a)s от Вас сообщений' % dict(
                            full_name=Misc.get_deeplink_with_name(profile_to),
                            a='а' if profile_to.get('gender') == 'f' else '' if profile_to.get('gender') == 'm' else '(а)',
                        )
                    else:
                        msg = 'Сообщения не найдены'
                    await bot.send_message(tg_user_sender.id, text=msg)
    await callback.answer()

@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.USER_DESC,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_get_user_desc(callback: CallbackQuery, state: FSMContext):
    if uuid := Misc.get_uuid_from_callback(callback):
        status, profile = await Misc.get_user_by_uuid(uuid)
        if status == 200:
            await state.set_state(FSMpersonDesc.ask)
            await state.update_data(uuid=uuid)
            await callback.message.reply(
                Misc.PROMPT_USER_DESC,
                reply_markup=Misc.reply_markup_cancel_row(),
            )
    await callback.answer()


async def do_get_user_desc(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    if not data.get('uuid'):
        return
    status, profile = await Misc.post_tg_user(message.from_user)
    if status != 200 or profile['uuid'] != data['uuid']:
        return
    # первое сообщение в коллаже или единственное
    is_first = True
    media_group_id = str(message.media_group_id or '')
    if media_group_id:
        key = (
            f'{Rcache.USER_DESC_PREFIX}{Rcache.KEY_SEP}'
            f'{message.from_user.id}{Rcache.KEY_SEP}{media_group_id}'
        )
        is_first = Misc.redis_is_key_first_up(key, ex=300)
    is_first = '1' if is_first else ''
    tgdesc  = '~'.join((str(message.message_id), str(message.chat.id), is_first, media_group_id,))
    status, response = await Misc.put_user_properties(uuid=data['uuid'], tgdesc=tgdesc)
    return status, response, is_first


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMpersonDesc.ask))
async def process_get_user_desc(message: Message, state: FSMContext):
    status, response, is_first = await do_get_user_desc(message, state)
    if status == 200 and is_first:
        await message.reply('Описание сохранено')
    await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.BANKING,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_get_banking(callback: CallbackQuery, state: FSMContext):
    if uuid := Misc.get_uuid_from_callback(callback):
        status_sender, response_sender = await Misc.post_tg_user(callback.from_user)
        if status_sender != 200 or response_sender['uuid'] != uuid:
            return
        text = Misc.PROMPT_BANK
        if bank_details := await Misc.get_bank_details(uuid):
            text += (
                '.\n\n'
                '<b>Ваши текущие реквизиты:</b>\n\n'
                f'{html.quote(bank_details)}\n\n'
                '<b>будут заменены</b>'
            )
        await state.set_state(FSMbanking.ask)
        await state.update_data(uuid=uuid)
        await callback.message.reply(text, reply_markup=Misc.reply_markup_cancel_row())
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMbanking.ask))
async def process_message_banking(message: Message, state: FSMContext):
    if (message.content_type != ContentType.TEXT) or \
       not (message_text := message.text.strip()):
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    if (uuid := data.get('uuid')) and \
       (response_check := await Misc.check_owner_by_uuid(message.from_user, uuid, check_own_only=True)):
        status, response = await Misc.api_request(
            path='/api/addkey',
            method='post',
            json=dict(
                tg_token=settings.TOKEN,
                keytype_id=Misc.BANKING_DETAILS_ID,
                owner_uuid=response_check['uuid'],
                user_uuid=response_check['uuid'],
                keys=[message_text],
        ))
        if status == 200:
            await message.reply('Реквизиты записаны')
    await state.clear()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMaskMoney.ask))
async def process_message_thank_ask_money(message: Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    data = await state.get_data()
    if not (profile_to := data.get('profile_to')) or not (journal_id := data.get('journal_id')):
        await state.clear(); return
    status_from, profile_from = await Misc.post_tg_user(message.from_user)
    if status_from != 200 or profile_from['uuid'] != data.get('profile_from', {}).get('uuid', ''):
        await state.clear(); return

    is_first = True
    media_group_id = str(message.media_group_id or '')
    if media_group_id:
        key = (
            f'{Rcache.ASK_MONEY_PREFIX}{Rcache.KEY_SEP}'
            f'{message.from_user.id}{Rcache.KEY_SEP}'
            f'{media_group_id}{Rcache.KEY_SEP}'
            f'{journal_id}'
        )
        is_first = Misc.redis_is_key_first_up(key, ex=300)
    tgdesc_payload  = dict(
        tg_token=settings.TOKEN,
        journal_id=journal_id,
        message_id=message.message_id,
        chat_id=message.chat.id,
        media_group_id=media_group_id,
        is_first=is_first,
    )
    logging.debug('post thank_bank, payload: %s' % Misc.secret(tgdesc_payload))
    status, response = await Misc.api_request(
        '/api/thank_bank',
        method='POST',
        json = tgdesc_payload
    )
    logging.debug('post thank_bank, status: %s' % status)
    logging.debug('post thank_bank, response: %s' % response)
    if status == 200:
        if is_first:
            await message.reply('Сообщение передано получателю благодарности')
        for tgd in profile_to['tg_data']:
            try:
                await bot.forward_message(
                    tgd['tg_uid'],
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            if is_first and not data.get('profile_to_has_bank_details'):
                try:
                    await bot.send_message(
                        tgd['tg_uid'], (
                        'Укажите Ваши Реквизиты для пожертвований в профиле - и '
                        'они будут предложены всем кто Вас будет благодарить!'
                    ))
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass
    await state.clear()

