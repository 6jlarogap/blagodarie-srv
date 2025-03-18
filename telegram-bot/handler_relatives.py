# handler_offer.py
#
# Команды и сообщения для занесения родственников

import re

from aiogram import Router, F, html
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


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMpapaMama.ask))
async def put_papa_mama(message: Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    user_sid_to = Misc.sid_from_link(message.text)
    if not user_sid_to:
        if await is_it_command(message, state, excepts=('start',)):
            return
        data = await state.get_data()
        uuid = data.get('uuid')
        is_father = data.get('is_father')
        if uuid and is_father is not None:
            if is_father:
                prompt_new_parent = 'Новый'
            else:
                prompt_new_parent = 'Новая'
            msg_invalid_link_with_new = (
                f'Профиль не найден - попробуйте скопировать и отправить ссылку '
                f'на существующий профиль ещё раз или создайте '
                f'<u>{prompt_new_parent}</u>'
            )
            button_new_parent = InlineKeyboardButton(
                text=prompt_new_parent,
                callback_data= Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                    keyboard_type=KeyboardType.NEW_FATHER if is_father else KeyboardType.NEW_MOTHER,
                    uuid=uuid,
                    sep=KeyboardType.SEP,
            ))
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
                button_new_parent, Misc.inline_button_cancel()
            ]])
            await message.reply(
                msg_invalid_link_with_new,
                reply_markup=reply_markup
            )
        else:
            await message.reply(
                Misc.MSG_INVALID_LINK + '\nПовторите, пожалуйста' ,
                reply_markup=Misc.reply_markup_cancel_row()
            )
        return
    user_uuid_from = is_father = ''
    data = await state.get_data()
    if data.get('uuid'):
        user_uuid_from = data['uuid']
        is_father = data.get('is_father')
    if not user_uuid_from or not isinstance(is_father, bool):
        await state.clear()
        return
    response_sender = await Misc.check_owner_by_sid(owner_tg_user=message.from_user, sid=user_sid_to)
    if not response_sender:
        await state.clear()
        return

    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=OperationType.SET_FATHER if is_father else OperationType.SET_MOTHER,
        user_id_from=user_uuid_from,
        user_id_to=response_sender['response_uuid']['uuid']
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
                'Ошибка!\n%s\n\nНазначайте родителя по новой' % response['message']
            )
        else:
            await message.reply(Misc.MSG_ERROR_API)
    else:
        if response and response.get('profile_from') and response.get('profile_to'):
            if not response['profile_to'].get('gender'):
                await Misc.put_user_properties(
                    uuid=response['profile_to']['uuid'],
                    gender='m' if is_father else 'f',
                )
            await bot.send_message(
                message.from_user.id,
                Misc.PROMPT_PAPA_MAMA_SET % dict(
                    iof_from = Misc.get_deeplink_with_name(response['profile_from'], plus_trusts=True),
                    iof_to = Misc.get_deeplink_with_name(response['profile_to'], plus_trusts=True),
                    papa_or_mama='папа' if is_father else 'мама',
                    _a_='' if is_father else 'а',
                ))
        else:
            await message.reply('Родитель внесен в данные')
    await state.clear()

@router.callback_query(F.data.regexp(r'^(%s|%s)%s' % (
        KeyboardType.NEW_FATHER, KeyboardType.NEW_MOTHER,
        KeyboardType.SEP,
    )), StateFilter(FSMpapaMama.ask))
async def cbq_new_papa_mama(callback: CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы
    """
    tg_user_sender = callback.from_user
    code = callback.data.split(KeyboardType.SEP)
    uuid = None
    try:
        uuid = code[1]
    except IndexError:
        pass
    if not uuid:
        await state.clear(); await callback.answer()
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid)
    if not response_sender:
        await state.clear(); await callback.answer()
        return
    is_father = code[0] == str(KeyboardType.NEW_FATHER)
    response_uuid = response_sender['response_uuid']
    prompt_new_papa_mama = (
        'Укажите Имя Фамилию и Отчество для %(papy_or_mamy)s, '
        'пример %(fio_pama_mama)s'
    ) % dict(
        papy_or_mamy='папы' if is_father else 'мамы',
        name=Misc.get_deeplink_with_name(response_uuid, plus_trusts=True),
        fio_pama_mama='Иван Иванович Иванов'if is_father else 'Марья Ивановна Иванова',
    )
    await state.set_state(FSMpapaMama.new)
    await state.update_data(uuid=uuid, is_father=is_father)
    await callback.message.reply(
        prompt_new_papa_mama,
        reply_markup=Misc.reply_markup_cancel_row(),
    )
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMpapaMama.new))
async def put_new_papa_mama(message: Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    first_name_to = Misc.strip_text(message.text)
    user_uuid_from = is_father = ''
    data = await state.get_data()
    if data.get('uuid'):
        user_uuid_from = data['uuid']
        is_father = data.get('is_father')
    if not user_uuid_from or not isinstance(is_father, bool):
        await state.clear()
        return
    owner = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=user_uuid_from)
    if not owner or not owner.get('user_id'):
        await state.clear()
        return

    post_data = dict(
        tg_token=settings.TOKEN,
        first_name = first_name_to,
        link_relation='new_is_father' if is_father else 'new_is_mother',
        link_id=user_uuid_from,
        owner_id=owner['user_id'],
    )
    logging.debug('post new owned user with link_id, payload: %s' % Misc.secret(post_data))
    status, response = await Misc.api_request(
        path='/api/profile',
        method='post',
        data=post_data,
    )
    logging.debug('post new owned user with link_id, status: %s' % status)
    logging.debug('post new owned user with link_id, response: %s' % response)
    if status != 200:
        if status == 400  and response.get('message'):
            await message.reply(
                'Ошибка!\n%s\n\nНазначайте родителя по новой' % response['message']
            )
        else:
            await message.reply(Misc.MSG_ERROR_API)
    else:
        if response and response.get('profile_from'):
            await Misc.put_user_properties(
                uuid=response['uuid'],
                gender='m' if is_father else 'f',
            )
            await bot.send_message(
                message.from_user.id,
                Misc.PROMPT_PAPA_MAMA_SET % dict(
                iof_from = Misc.get_deeplink_with_name(response['profile_from'], plus_trusts=True),
                iof_to = Misc.get_deeplink_with_name(response, plus_trusts=True),
                papa_or_mama='папа' if is_father else 'мама',
                _a_='' if is_father else 'а',
                ))
            await Misc.show_card(
                profile=response,
                profile_sender=owner,
                tg_user_sender=message.from_user,
            )
        else:
            await message.reply('Родитель внесен в данные')
    await state.clear()

@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CHILD,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_callback_child(callback: CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы для ребенка
    """
    if True:
        await bot.answer_callback_query(
                callback.id,
                text='Пока не реализовано',
                show_alert=True,
        )
        await callback.answer()
        return
    if not (uuid := Misc.get_uuid_from_callback(callback)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid)
    if not response_sender:
        return
    response_uuid = response_sender['response_uuid']
    reply_markup = None
    await state.update_data(uuid=uuid, name=response_uuid['first_name'])
    if response_uuid['gender']:
        await state.update_data(parent_gender=response_uuid['gender'])
        await ask_child(callback.message, state, children=response_sender['response_uuid']['children'])
    else:
        await state.update_data(parent_gender=None)
        callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.FATHER_OF_CHILD,
            uuid=uuid,
            sep=KeyboardType.SEP,
        )
        inline_btn_papa_of_child = InlineKeyboardButton(
            text='Муж',
            callback_data=callback_data,
        )
        callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.MOTHER_OF_CHILD,
            uuid=uuid,
            sep=KeyboardType.SEP,
        )
        inline_btn_mama_of_child = InlineKeyboardButton(
            text='Жен',
            callback_data=callback_data,
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            inline_btn_papa_of_child, inline_btn_mama_of_child, Misc.inline_button_cancel()
        ]])
        prompt_papa_mama_of_child = Misc.PROMPT_PAPA_MAMA_OF_CHILD % dict(
            name=response_uuid['first_name'],
        )
        await FSMchild.parent_gender.set()
        await callback.message.reply(
            prompt_papa_mama_of_child,
            reply_markup=reply_markup,
        )
    await callback.answer()

async def ask_child(message, state, children):
    data = await state.get_data()
    prompt_child = (
        '<b>%(name)s</b>.\n'
        'Отправьте мне <u><b>ссылку на профиль %(his_her)s сына (дочери)</b></u> '
        'вида t.me/%(bot_data_username)s?start=...\n'
        '\n'
        'Или нажмите <b><u>Новый сын</u></b> или <b><u>Новая дочь</u></b> для ввода нового родственника, '
        'который станет %(his_her)s сыном или дочерью\n'
    )
    if children:
        if len(children) == 1:
            prompt_child += (
                '\n'
                'Или нажмите <b><u>Очистить</u></b> для очистки %(his_her)s родственной связи '
                'с <b>%(name_of_single_child)s</b>\n'
            )
        else:
            prompt_child += (
                '\n'
                'Или нажмите <b><u>Очистить</u></b> для очистки родственной связи '
                'с кем-то из %(his_her)s детей\n'
            )
    prompt_child = prompt_child % dict(
        bot_data_username=bot_data.username,
        name=data['name'],
        his_her='его' if data['parent_gender'] == 'm' else 'её',
        name_of_single_child=children[0]['first_name'] if children else '',
    )
    data_new_child = dict(
        keyboard_type=KeyboardType.NEW_SON,
        uuid=data['uuid'],
        sep=KeyboardType.SEP,
    )
    inline_btn_new_son = InlineKeyboardButton(
        text='Новый сын',
        callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % data_new_child,
    )
    data_new_child.update(keyboard_type=KeyboardType.NEW_DAUGHTER)
    inline_btn_new_daughter = InlineKeyboardButton(
        text='Новая дочь',
        callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % data_new_child,
    )
    buttons = [inline_btn_new_son, inline_btn_new_daughter, ]
    if children:
        callback_data_clear_child = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.CLEAR_CHILD,
            uuid=data['uuid'],
            sep=KeyboardType.SEP,
        )
        inline_btn_clear_child = InlineKeyboardButton(
            text='Очистить',
            callback_data=callback_data_clear_child,
        )
        buttons.append(inline_btn_clear_child)
    buttons.append(Misc.inline_button_cancel())
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[ buttons ])
    await state.set_state(FSMchild.ask)
    await message.reply(
        prompt_child,
        reply_markup=reply_markup,
    )


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_CHILD,
        KeyboardType.SEP,
    )), StateFilter(FSMchild.ask))
async def cbq_clear_child(callback: CallbackQuery, state: FSMContext):
    """
    Действия по вопросу об обнулении ребенка
    """
    if not (uuid := Misc.get_uuid_from_callback(callback)):
        await state.clear()
        return
    message = callback.message
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback.from_user, uuid=uuid)
    if not response_sender or \
       not response_sender.get('response_uuid') or \
       not response_sender['response_uuid'].get('children'):
        await state.clear()
        return
    data = await state.get_data()
    if not data or \
       not data.get('parent_gender') or \
       data.get('uuid') != uuid:
        await state.clear()
        return
    parent = response_sender['response_uuid']
    children = parent['children']
    if len(children) == 1:
        await clear_child_confirm(children[0], parent, callback.message, state)
    else:
        prompt = (
            'У <b>%(parent_name)s</b> несколько детей. Нажмите на ссылку того, '
            'с кем собираетесь разорвать %(his_her)s родственную связь\n\n'
        )
        prompt = prompt % dict(
            parent_name=html.quote(parent['first_name']),
            his_her='его' if data['parent_gender'] == 'm' else 'её',
        )
        for child in children:
            prompt += Misc.get_deeplink_with_name(child, plus_trusts=True) + '\n'
        await state.set_state(FSMchild.choose)
        await callback.message.reply(
            prompt,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
    await callback.answer()


async def clear_child_confirm(child_profile, parent_profile, message, state):
    """
    Подтвердить очистить связь родитель -> ребенок
    """
    data = await state.get_data()
    if not data or not data.get('parent_gender') or not data.get('uuid'):
        await state.clear()
        return
    prompt = (
        'Вы уверены, что хотите очистить родственную связь: '
        '<b>%(parent_name)s</b> - %(papa_or_mama)s для <b>%(child_name)s</b>?\n\n'
        'Если уверены, нажмите <b><u>Очистить</u></b>'
        ) % dict(
        papa_or_mama='папа' if data['parent_gender'] == 'm' else 'мама',
        parent_name=html.quote(parent_profile['first_name']),
        child_name=html.quote(child_profile['first_name']),
    )
    callback_data_clear_child_confirm = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
        keyboard_type=KeyboardType.CLEAR_CHILD_CONFIRM,
        uuid=parent_profile['uuid'],
        sep=KeyboardType.SEP,
    )
    inline_btn_clear_child_confirm = InlineKeyboardButton(
        text='Очистить',
        callback_data=callback_data_clear_child_confirm,
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
        inline_btn_clear_child_confirm, Misc.inline_button_cancel()
    ]])
    await state.update_data(child_uuid = child_profile['uuid'])
    await state.set_state(FSMchild.confirm_clear)
    await message.reply(
        prompt,
        reply_markup=reply_markup,
    )


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMchild.choose))
async def choose_child_to_clear_link(message: Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_INVALID_LINK + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state, excepts=('start',)):
        return
    child_sid = Misc.sid_from_link(message.text)
    if not child_sid:
        await message.reply(
            Misc.MSG_INVALID_LINK + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    data = await state.get_data()
    if data.get('uuid') and data.get('parent_gender'):
        parent_uuid = data['uuid']
        response_sender = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=parent_uuid)
        if not response_sender:
            await state.clear()
            return
        parent_profile = response_sender['response_uuid']
        children = parent_profile.get('children', [])
        child_profile = None
        for child in children:
            if child['username'] == child_sid:
                child_profile = child
                break
        if not child_profile:
            await message.reply(
                'Это ссылка на кого-то другого, а не на одного из детей <b>%s</b>\n\n%s' % (
                    html.quote(parent_profile['first_name']),
                    Misc.MSG_REPEATE_PLEASE,
                ),
                reply_markup=Misc.reply_markup_cancel_row()
            )
            return
        await clear_child_confirm(child_profile, parent_profile, message, state)
    else:
        await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_CHILD_CONFIRM,
        KeyboardType.SEP,
    )), StateFilter(FSMchild.confirm_clear))
async def cbq_clear_child_confirmed(callback: CallbackQuery, state: FSMContext):
    """
    Действия по вопросу об обнулении ребенка
    """
    if not (parent_uuid := Misc.get_uuid_from_callback(callback)):
        await state.clear(); await callback.answer()
        return
    message = callback.message
    tg_user_sender = callback.from_user
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=parent_uuid)
    if not response_sender or \
       not response_sender.get('response_uuid') or \
       not response_sender['response_uuid'].get('children'):
        await state.clear(); await callback.answer()
        return
    data = await state.get_data()
    if not data or \
       not data.get('parent_gender') or \
       data.get('uuid') != parent_uuid or \
       not data.get('child_uuid'):
        await state.clear(); await callback.answer()
        return
    is_father = data['parent_gender'] == 'm'
    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=OperationType.NOT_PARENT,
        user_id_from=data['child_uuid'],
        user_id_to=parent_uuid,
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
                'Ошибка!\n%s\n\nОчищайте ребенка по новой' % response['message']
            )
        else:
            await message.reply(Misc.MSG_ERROR_API)
    else:
        if response and response.get('profile_from') and response.get('profile_to'):
            if not response['profile_to']['gender']:
                await Misc.put_user_properties(
                    uuid=response['profile_to']['uuid'],
                    gender='m' if is_father else 'f',
                )
            await bot.send_message(
                tg_user_sender.id,
                Misc.PROMPT_PAPA_MAMA_CLEARED % dict(
                    iof_from = Misc.get_deeplink_with_name(response['profile_from'], plus_trusts=True),
                    iof_to = Misc.get_deeplink_with_name(response['profile_to'], plus_trusts=True),
                    papa_or_mama='папа' if is_father else 'мама',
                ))
        else:
            await message.reply('Связь Родитель - Ребенок очищена')
    await state.clear()
    await callback.answer()


@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMchild.ask))
async def put_child_by_sid(message: Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    user_sid_from = Misc.sid_from_link(message.text)
    if not user_sid_from:
        if await is_it_command(message, state, excepts=('start',)):
            return
        data = await state.get_data()
        if uuid := data.get('uuid'):
            data_new_child = dict(
                keyboard_type=KeyboardType.NEW_SON,
                uuid=uuid,
                sep=KeyboardType.SEP,
            )
            inline_btn_new_son = InlineKeyboardButton(
                'Новый сын',
                callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % data_new_child,
            )
            data_new_child.update(keyboard_type=KeyboardType.NEW_DAUGHTER)
            inline_btn_new_daughter = InlineKeyboardButton(
                'Новая дочь',
                callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % data_new_child,
            )
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
                inline_btn_new_son, inline_btn_new_daughter, Misc.inline_button_cancel()
            ]])
            await message.reply(
                'Профиль не найден - попробуйте скопировать и отправить ссылку '
                'на существующий профиль ещё раз или создайте <u>Новый сын</u> или <u>Новая дочь</u>',
                reply_markup=reply_markup
            )
        else:
            await message.reply(
                Misc.MSG_INVALID_LINK + '\nПовторите, пожалуйста' ,
                reply_markup=Misc.reply_markup_cancel_row()
            )
        return

    data = await state.get_data()
    if data.get('uuid') and data.get('parent_gender'):
        response_sender = await Misc.check_owner_by_sid(owner_tg_user=message.from_user, sid=user_sid_from)
        if response_sender:
            user_uuid_from = response_sender['response_uuid']['uuid']
            is_father = data['parent_gender'] == 'm'
            post_op = dict(
                tg_token=settings.TOKEN,
                operation_type_id=OperationType.SET_FATHER if is_father else OperationType.SET_MOTHER,
                user_id_from=user_uuid_from,
                user_id_to=data['uuid'],
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
                        'Ошибка!\n%s\n\nНазначайте ребёнка по новой' % response['message']
                    )
                else:
                    await message.reply(Misc.MSG_ERROR_API)
            else:
                if response and response.get('profile_from') and response.get('profile_to'):
                    if not response['profile_to'].get('gender'):
                        await Misc.put_user_properties(
                            uuid=response['profile_to']['uuid'],
                            gender='m' if is_father else 'f',
                        )
                    await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                            iof_from = Misc.get_deeplink_with_name(response['profile_from'], plus_trusts=True),
                            iof_to = Misc.get_deeplink_with_name(response['profile_to'], plus_trusts=True),
                            papa_or_mama='папа' if is_father else 'мама',
                            _a_='' if is_father else 'а',
                    ))
                else:
                    await message.reply('Родитель внесен в данные')
        else:
            # Не имеет права
            await message.reply((
                'Нельзя назначать ребенка, если это активный пользователь или профиль, '
                'которым владеете не Вы.\n\n'
                'Назначайте ребёнка по новой'
            ))
    await state.clear()


@router.callback_query(F.data.regexp(r'^(%s|%s)%s' % (
         KeyboardType.NEW_SON, KeyboardType.NEW_DAUGHTER,
        KeyboardType.SEP,
    )), StateFilter(FSMchild.ask))
async def cbq_new_child_ask_fio(callback: CallbackQuery, state: FSMContext):
    if not (uuid := Misc.get_uuid_from_callback(callback)):
        await state.clear(); await callback.answer()
        return
    data = await state.get_data()
    for key in ('name', 'uuid', 'parent_gender',):
        if not data.get(key) or key == 'uuid' and data[key] != uuid:
            await state.clear()
            return
    new_child_gender = 'm' \
        if callback.data.split(KeyboardType.SEP)[0] == str(KeyboardType.NEW_SON) \
        else 'f'
    fio_new_child = 'Иван Иванович Иванов' if new_child_gender == 'm' else 'Марья Ивановна Иванова'
    await state.update_data(new_child_gender=new_child_gender)
    await state.set_state(FSMchild.new)
    await callback.message.reply(
        (
            f'Укажите ФИО {"СЫНА" if new_child_gender == "m" else "ДОЧЕРИ"} для:\n'
            f'{data["name"]}\nНапример, {fio_new_child}'
        ),
        reply_markup=Misc.reply_markup_cancel_row(),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.BRO_SIS,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_callback_child(callback: CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(
            callback.id,
            text='Пока не реализовано',
            show_alert=True,
    )
