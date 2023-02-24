import base64, re, hashlib
from io import BytesIO

import settings
from settings import logging
from utils import Misc, OperationType, KeyboardType, TgGroup, TgGroupMember

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.types.login_url import LoginUrl
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import ChatTypeFilter, Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_polling, start_webhook
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import ChatNotFound, CantInitiateConversation, CantTalkWithBots, \
    BadRequest
from aiogram.utils.parts import safe_split_text

import pymorphy2
MorphAnalyzer = pymorphy2.MorphAnalyzer()

storage = MemoryStorage()

class FSMability(StatesGroup):
    ask = State()

class FSMwish(StatesGroup):
    ask = State()

class FSMnewIOF(StatesGroup):
    ask = State()

class FSMexistingIOF(StatesGroup):
    ask = State()

class FSMphoto(StatesGroup):
    ask = State()
    remove = State()

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

class FSMother(StatesGroup):
    gender = State()
    dob = State()
    dod = State()

class FSMsendMessage(StatesGroup):
    ask = State()

class FSMfeedback(StatesGroup):
    ask = State()

class FSMchangeOwner(StatesGroup):
    ask = State()
    confirm = State()

class FSMkey(StatesGroup):
    ask = State()

class FSMquery(StatesGroup):
    ask = State()

class FSMdelete(StatesGroup):
    ask = State()

class FSMundelete(StatesGroup):
    ask = State()

class FSMgeo(StatesGroup):
    geo = State()

class FSMtrip(StatesGroup):
    ask_geo = State()
    geo = State()

class FSMtrustThank(StatesGroup):
    # благодарности, недоверия, не-знакомы
    ask = State()

# Отслеживаем по каждой группе (ключ этого словаря),
# кто был автором последнего сообщения в группу.
# Если юзер отправит два сообщения подряд, то
# реакция бота будет только по первому сообщению.
# Несколько сообщений подряд от одного и того же юзера
# могут быть и в сообщении, включающем множество картинок.
#
last_user_in_group = dict()

bot = Bot(
    token=settings.TOKEN,
    parse_mode=types.ParseMode.HTML,
)
dp = Dispatcher(bot, storage=storage)

async def on_startup(dp):
    if settings.START_MODE == 'webhook':
        await bot.set_webhook(settings.WEBHOOK_URL)


async def on_shutdown(dp):
    logging.warning('Shutting down..')
    if settings.START_MODE == 'webhook':
        await bot.delete_webhook()


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMpapaMama.ask,
)
async def put_papa_mama(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    user_uuid_to = Misc.uuid_from_text(message.text)
    if not user_uuid_to:
        await message.reply(
            Misc.MSG_ERROR_UUID_NOT_VALID + '\nПовторите, пожалуйста' ,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return

    user_uuid_from = is_father = ''
    async with state.proxy() as data:
        if data.get('uuid'):
            user_uuid_from = data['uuid']
            is_father = data.get('is_father')
        data['uuid'] = data['is_father'] = ''
    if not user_uuid_from or not isinstance(is_father, bool):
        await Misc.state_finish(state)
        return
    if not await Misc.check_owner(owner_tg_user=message.from_user, uuid=user_uuid_to):
        await Misc.state_finish(state)
        return

    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=OperationType.SET_FATHER if is_father else OperationType.SET_MOTHER,
        user_uuid_from=user_uuid_from,
        user_uuid_to=user_uuid_to,
    )
    logging.debug('post operation, payload: %s' % post_op)
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
            bot_data = await bot.get_me()
            await bot.send_message(
                message.from_user.id,
                Misc.PROMPT_PAPA_MAMA_SET % dict(
                    iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data, plus_trusts=True),
                    iof_to = Misc.get_deeplink_with_name(response['profile_to'], bot_data, plus_trusts=True),
                    papa_or_mama='папа' if is_father else 'мама',
                    _a_='' if is_father else 'а',
                ),
                disable_web_page_preview=True,
            )
        else:
            await message.reply('Родитель внесен в данные')
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMpapaMama.new,
)
async def put_new_papa_mama(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    first_name_to = Misc.strip_text(message.text)
    if re.search(Misc.RE_UUID, first_name_to):
        await message.reply(
            Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    user_uuid_from = is_father = ''
    async with state.proxy() as data:
        if data.get('uuid'):
            user_uuid_from = data['uuid']
            is_father = data.get('is_father')
        data['uuid'] = data['is_father'] = ''
    if not user_uuid_from or not isinstance(is_father, bool):
        await Misc.state_finish(state)
        return
    owner = await Misc.check_owner(owner_tg_user=message.from_user, uuid=user_uuid_from)
    if not owner or not owner.get('user_id'):
        await Misc.state_finish(state)
        return

    post_data = dict(
        tg_token=settings.TOKEN,
        first_name = first_name_to,
        link_relation='new_is_father' if is_father else 'new_is_mother',
        link_uuid=user_uuid_from,
        owner_id=owner['user_id'],
    )
    logging.debug('post new owned user with link_uuid, payload: %s' % post_data)
    status, response = await Misc.api_request(
        path='/api/profile',
        method='post',
        data=post_data,
    )
    logging.debug('post new owned user with link_uuid, status: %s' % status)
    logging.debug('post new owned user with link_uuid, response: %s' % response)
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
            bot_data = await bot.get_me()
            await bot.send_message(
                message.from_user.id,
                Misc.PROMPT_PAPA_MAMA_SET % dict(
                iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data, plus_trusts=True),
                iof_to = Misc.get_deeplink_with_name(response, bot_data, plus_trusts=True),
                papa_or_mama='папа' if is_father else 'мама',
                _a_='' if is_father else 'а',
                ),
                disable_web_page_preview=True,
            )
            await Misc.show_cards(
                [response],
                message,
                bot,
                response_from=owner,
            )
        else:
            await message.reply('Родитель внесен в данные')
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.NEW_FATHER, KeyboardType.NEW_MOTHER,
        KeyboardType.SEP,
        # uuid пользователя, включая owned, кому назначается новый папа/мама     # 1
        # KeyboardType.SEP,
    ), c.data),
    state = FSMpapaMama.ask,
    )
async def process_callback_new_papa_mama(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            await Misc.state_finish(state)
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            await Misc.state_finish(state)
            return
        bot_data = await bot.get_me()
        is_father = code[0] == str(KeyboardType.NEW_FATHER)
        response_uuid = response_sender['response_uuid']
        prompt_new_papa_mama = (
            'Укажите Имя Фамилию и Отчество для %(papy_or_mamy)s, '
            'пример %(fio_pama_mama)s'
        ) % dict(
            papy_or_mamy='папы' if is_father else 'мамы',
            name=Misc.get_deeplink_with_name(response_uuid, bot_data, plus_trusts=True),
            fio_pama_mama='Иван Иванович Иванов'if is_father else 'Марья Ивановна Иванова',
        )
        await FSMpapaMama.next()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['is_father'] = is_father
        await callback_query.message.reply(
            prompt_new_papa_mama,
            reply_markup=Misc.reply_markup_cancel_row(),
        )


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.FATHER, KeyboardType.MOTHER,
        KeyboardType.SEP,
        # uuid потомка папы или мамы           # 1
        # KeyboardType.SEP,
    ), c.data),
    state = None,
    )
async def process_callback_papa_mama(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            return
        response_uuid = response_sender['response_uuid']
        is_father = code[0] == str(KeyboardType.FATHER)
        bot_data = await bot.get_me()
        state = dp.current_state()
        existing_parent = None
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['is_father'] = is_father
            if is_father and response_sender['response_uuid'].get('father'):
                existing_parent = response_sender['response_uuid']['father']
            elif not is_father and response_sender['response_uuid'].get('mother'):
                existing_parent = response_sender['response_uuid']['mother']
            data['existing_parent_uuid'] = existing_parent['uuid'] if existing_parent else None,
            data['existing_parent_name'] = existing_parent['first_name'] if existing_parent else None

        callback_data_new_parent = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.NEW_FATHER if is_father else KeyboardType.NEW_MOTHER,
            uuid=uuid,
            sep=KeyboardType.SEP,
        )
        novy_novaya = 'Новый' if is_father else 'Новая'
        inline_btn_new_papa_mama = InlineKeyboardButton(
            novy_novaya,
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
                'Очистить',
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
            bot_data_username=bot_data['username'],
            response_uuid_name=response_sender['response_uuid']['first_name'],
            existing_parent_name=existing_parent['first_name'] if existing_parent else '',
            novy_novaya=novy_novaya,
        )
        reply_markup = InlineKeyboardMarkup()
        buttons.append(Misc.inline_button_cancel())
        reply_markup.row(*buttons)
        await FSMpapaMama.ask.set()
        await callback_query.message.reply(
            prompt_papa_mama,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_PARENT,
        KeyboardType.SEP,
    ), c.data),
    state = FSMpapaMama.ask,
    )
async def process_callback_clear_parent(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по обнулению папы, мамы
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            await Misc.state_finish(state)
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            await Misc.state_finish(state)
            return
        async with state.proxy() as data:
            if not data or \
               not data.get('existing_parent_uuid') or \
               ('is_father' not in data) or \
               not data.get('existing_parent_name') or \
               data.get('uuid') != uuid \
               :
                await Misc.state_finish(state)
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
            'Очистить',
            callback_data=callback_data_clear_parent_confirm,
        )
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_clear_parent_confirm, Misc.inline_button_cancel())
        await FSMpapaMama.confirm_clear.set()
        await callback_query.message.reply(
            prompt,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    else:
        await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_PARENT_CONFIRM,
        KeyboardType.SEP,
    ), c.data),
    state = FSMpapaMama.confirm_clear,
    )
async def process_callback_clear_parent_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по обнулению папы, мамы
    """
    message = callback_query.message
    if message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            await Misc.state_finish(state)
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            await Misc.state_finish(state)
            return
        async with state.proxy() as data:
            if not data or \
               not data.get('existing_parent_uuid') or \
               ('is_father' not in data) or \
               not data.get('existing_parent_name') or \
               data.get('uuid') != uuid \
               :
                await Misc.state_finish(state)
                return
            existing_parent_uuid = data['existing_parent_uuid']
            is_father = data['is_father']
        post_op = dict(
            tg_token=settings.TOKEN,
            operation_type_id=OperationType.NOT_PARENT,
            user_uuid_from=response_sender['response_uuid']['uuid'],
            user_uuid_to=existing_parent_uuid,
        )
        logging.debug('post operation, payload: %s' % post_op)
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
                bot_data = await bot.get_me()
                await bot.send_message(
                    callback_query.from_user.id,
                    Misc.PROMPT_PAPA_MAMA_CLEARED % dict(
                        iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data, plus_trusts=True),
                        iof_to = Misc.get_deeplink_with_name(response['profile_to'], bot_data, plus_trusts=True),
                        papa_or_mama='папа' if is_father else 'мама',
                    ),
                    disable_web_page_preview=True,
                )
            else:
                await message.reply('Связь Ребенок - Родитель очищена')
    await Misc.state_finish(state)


async def ask_child(message, state, data, children):
    bot_data = await bot.get_me()
    prompt_child = (
        '<b>%(name)s</b>.\n'
        'Отправьте мне <u><b>ссылку на профиль %(his_her)s сына (дочери)</b></u> '
        'вида t.me/%(bot_data_username)s?start=...\n'
        '\n'
        'Или нажмите <b><u>Новый ребёнок</u></b> для ввода нового родственника, '
        'который станет %(his_her)s сыном (дочерью)\n'
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
        bot_data_username=bot_data['username'],
        name=data['name'],
        his_her='его' if data['parent_gender'] == 'm' else 'её',
        name_of_single_child=children[0]['first_name'] if children else '',
    )
    callback_data_new_child = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
        keyboard_type=KeyboardType.NEW_CHILD,
        uuid=data['uuid'],
        sep=KeyboardType.SEP,
    )
    inline_btn_new_child = InlineKeyboardButton(
        'Новый ребёнок',
        callback_data=callback_data_new_child,
    )
    buttons = [inline_btn_new_child, ]
    if children:
        callback_data_clear_child = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.CLEAR_CHILD,
            uuid=data['uuid'],
            sep=KeyboardType.SEP,
        )
        inline_btn_clear_child = InlineKeyboardButton(
            'Очистить',
            callback_data=callback_data_clear_child,
        )
        buttons.append(inline_btn_clear_child)
    buttons.append(Misc.inline_button_cancel())
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(*buttons)
    await FSMchild.ask.set()
    await message.reply(
        prompt_child,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def clear_child_confirm(child_profile, parent_profile, message, state):
    """
    Подтвердить очистить связь родитель -> ребенок
    """
    async with state.proxy() as data:
        if not data or not data.get('parent_gender') or not data.get('uuid'):
            await Misc.state_finish(state)
            return
        prompt = (
            'Вы уверены, что хотите очистить родственную связь: '
            '<b>%(parent_name)s</b> - %(papa_or_mama)s для <b>%(child_name)s</b>?\n\n'
            'Если уверены, нажмите <b><u>Очистить</u></b>'
            ) % dict(
            papa_or_mama='папа' if data['parent_gender'] == 'm' else 'мама',
            parent_name=parent_profile['first_name'],
            child_name=child_profile['first_name'],
        )
        callback_data_clear_child_confirm = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.CLEAR_CHILD_CONFIRM,
            uuid=parent_profile['uuid'],
            sep=KeyboardType.SEP,
        )
        inline_btn_clear_child_confirm = InlineKeyboardButton(
            'Очистить',
            callback_data=callback_data_clear_child_confirm,
        )
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_clear_child_confirm, Misc.inline_button_cancel())
        data['child_uuid'] = child_profile['uuid']
        await FSMchild.confirm_clear.set()
        await message.reply(
            prompt,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_CHILD_CONFIRM,
        KeyboardType.SEP,
    ), c.data),
    state = FSMchild.confirm_clear,
    )
async def process_callback_clear_child_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по вопросу об обнулении ребенка
    """
    message = callback_query.message
    if message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        parent_uuid = None
        try:
            parent_uuid = code[1]
        except IndexError:
            pass
        if not parent_uuid:
            await Misc.state_finish(state)
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=parent_uuid)
        if not response_sender or \
           not response_sender.get('response_uuid') or \
           not response_sender['response_uuid'].get('children'):
            await Misc.state_finish(state)
            return
        async with state.proxy() as data:
            if not data or \
               not data.get('parent_gender') or \
               data.get('uuid') != parent_uuid or \
               not data.get('child_uuid'):
                await Misc.state_finish(state)
                return
            is_father = data['parent_gender'] == 'm'
            post_op = dict(
                tg_token=settings.TOKEN,
                operation_type_id=OperationType.NOT_PARENT,
                user_uuid_from=data['child_uuid'],
                user_uuid_to=parent_uuid,
            )
            logging.debug('post operation, payload: %s' % post_op)
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
                    bot_data = await bot.get_me()
                    await bot.send_message(
                        tg_user_sender.id,
                        Misc.PROMPT_PAPA_MAMA_CLEARED % dict(
                            iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data, plus_trusts=True),
                            iof_to = Misc.get_deeplink_with_name(response['profile_to'], bot_data, plus_trusts=True),
                            papa_or_mama='папа' if is_father else 'мама',
                        ),
                        disable_web_page_preview=True,
                    )
                else:
                    await message.reply('Связь Родитель - Ребенок очищена')
    await Misc.state_finish(state)        


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CLEAR_CHILD,
        KeyboardType.SEP,
    ), c.data),
    state = FSMchild.ask,
    )
async def process_callback_clear_child(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по вопросу об обнулении ребенка
    """
    message = callback_query.message
    if message:
        # Если у него/неё одни ребенок, сразу вопрос
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            await Misc.state_finish(state)
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender or \
           not response_sender.get('response_uuid') or \
           not response_sender['response_uuid'].get('children'):
            await Misc.state_finish(state)
            return
        async with state.proxy() as data:
            if not data or \
               not data.get('parent_gender') or \
               data.get('uuid') != uuid:
                await Misc.state_finish(state)
                return
        parent = response_sender['response_uuid']
        children = parent['children']
        if len(children) == 1:
            await clear_child_confirm(children[0], parent, callback_query.message, state)
        else:
            bot_data = await bot.get_me()
            prompt = (
                'У <b>%(parent_name)s</b> несколько детей. Нажмите на ссылку того, '
                'с кем собираетесь разорвать %(his_her)s родственную связь\n\n'
            )
            prompt = prompt % dict(
                parent_name=parent['first_name'],
                his_her='его' if data['parent_gender'] == 'm' else 'её',
            )
            for child in children:
                prompt += Misc.get_deeplink_with_name(child, bot_data, plus_trusts=True) + '\n'
            prompt += "\nПосле надо будет нажать внизу 'Запустить' ('Start')\n"
            reply_markup = InlineKeyboardMarkup()
            reply_markup.row(Misc.inline_button_cancel())
            await FSMchild.choose.set()
            await callback_query.message.reply(
                prompt,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
    else:
        await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMchild.choose,
)
async def choose_child_to_lear_link(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_INVALID_LINK + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    child_uuid = Misc.uuid_from_text(message.text)
    if not child_uuid:
        await message.reply(
            Misc.MSG_INVALID_LINK + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    async with state.proxy() as data:
        if data.get('uuid') and data.get('parent_gender'):
            parent_uuid = data['uuid']
            response_sender = await Misc.check_owner(owner_tg_user=message.from_user, uuid=parent_uuid)
            if not response_sender:
                await Misc.state_finish(state)
                return
            parent_profile = response_sender['response_uuid']
            children = parent_profile.get('children', [])
            child_profile = None
            for child in children:
                if child['uuid'] == child_uuid:
                    child_profile = child
                    break
            if not child_profile:
                await message.reply(
                    'Это ссылка на кого-то другого, а не на одного из детей <b>%s</b>\n\n%s' % (
                        parent_profile['first_name'],
                        Misc.MSG_REPEATE_PLEASE,
                    ),
                    reply_markup=Misc.reply_markup_cancel_row()
                )
                return
            await clear_child_confirm(child_profile, parent_profile, message, state)
        else:
            await Misc.state_finish(state)

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMchild.ask,
)
async def put_child_by_uuid(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    user_uuid_from = Misc.uuid_from_text(message.text)
    if not user_uuid_from:
        await message.reply(
            Misc.MSG_ERROR_UUID_NOT_VALID + '\nПовторите, пожалуйста' ,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    async with state.proxy() as data:
        if data.get('uuid') and data.get('parent_gender'):
            response_sender = await Misc.check_owner(owner_tg_user=message.from_user, uuid=user_uuid_from)
            if response_sender:
                is_father = data['parent_gender'] == 'm'
                post_op = dict(
                    tg_token=settings.TOKEN,
                    operation_type_id=OperationType.SET_FATHER if is_father else OperationType.SET_MOTHER,
                    user_uuid_from=user_uuid_from,
                    user_uuid_to=data['uuid'],
                    owner_id=response_sender['user_id'],
                )
                logging.debug('post operation, payload: %s' % post_op)
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
                        bot_data = await bot.get_me()
                        await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                                iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data, plus_trusts=True),
                                iof_to = Misc.get_deeplink_with_name(response['profile_to'], bot_data, plus_trusts=True),
                                papa_or_mama='папа' if is_father else 'мама',
                                _a_='' if is_father else 'а',
                                disable_web_page_preview=True,
                        ))
                    else:
                        await message.reply('Родитель внесен в данные')
        await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMchild.new,
)
async def put_new_child(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    first_name = Misc.strip_text(message.text)
    if re.search(Misc.RE_UUID, first_name):
        await message.reply(
            Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    async with state.proxy() as data:
        if data.get('uuid') and data.get('parent_gender'):
            response_sender = await Misc.check_owner(owner_tg_user=message.from_user, uuid=data['uuid'])
            if response_sender:
                response_parent = response_sender['response_uuid']
                if not response_parent['gender']:
                    await Misc.put_user_properties(
                      uuid=data['uuid'],
                      gender=data['parent_gender'],
                    )
                post_new_link = dict(
                    tg_token=settings.TOKEN,
                    first_name=first_name,
                    link_uuid=data['uuid'],
                    link_relation='link_is_father' if data['parent_gender'] == 'm' else 'link_is_mother',
                    owner_id=response_sender['user_id'],
                )
                logging.debug('post new child, payload: %s' % post_new_link)
                status_child, response_child = await Misc.api_request(
                    path='/api/profile',
                    method='post',
                    data=post_new_link,
                )
                logging.debug('post new child, status: %s' % status_child)
                logging.debug('post new child, response: %s' % response_child)
                if status_child != 200:
                    if status_child == 400  and response_child.get('message'):
                        await message.reply(
                            'Ошибка!\n%s\n\nНазначайте ребёнка по новой' % response['message']
                        )
                    else:
                        await message.reply(Misc.MSG_ERROR_API)
                else:
                    if response_child:
                        is_father = data['parent_gender'] == 'm'
                        bot_data = await bot.get_me()
                        await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                                iof_from = Misc.get_deeplink_with_name(response_child, bot_data, plus_trusts=True),
                                iof_to = Misc.get_deeplink_with_name(response_parent, bot_data, plus_trusts=True),
                                papa_or_mama='папа' if is_father else 'мама',
                                _a_='' if is_father else 'а',
                                disable_web_page_preview=True,
                        ))
                        await Misc.show_cards(
                            [response_child],
                            message,
                            bot,
                            response_from=response_sender,
                        )
                    else:
                        await message.reply('Ребёнок внесен в данные')
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CHILD,
        KeyboardType.SEP,
        # uuid родителя           # 1
        # KeyboardType.SEP,
    ), c.data),
    state = None,
    )
async def process_callback_child(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы для ребенка
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            return
        response_uuid = response_sender['response_uuid']
        state = dp.current_state()
        reply_markup = None
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['name'] = response_uuid['first_name']
            if response_uuid['gender']:
                data['parent_gender'] = response_uuid['gender']
                await ask_child(callback_query.message, state, data, children=response_sender['response_uuid']['children'])
            else:
                data['parent_gender'] = None
                callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                    keyboard_type=KeyboardType.FATHER_OF_CHILD,
                    uuid=uuid,
                    sep=KeyboardType.SEP,
                )
                inline_btn_papa_of_child = InlineKeyboardButton(
                    'Муж',
                    callback_data=callback_data,
                )
                callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                    keyboard_type=KeyboardType.MOTHER_OF_CHILD,
                    uuid=uuid,
                    sep=KeyboardType.SEP,
                )
                inline_btn_mama_of_child = InlineKeyboardButton(
                    'Жен',
                    callback_data=callback_data,
                )
                inline_button_cancel = Misc.inline_button_cancel()
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(inline_btn_papa_of_child, inline_btn_mama_of_child, inline_button_cancel)
                prompt_papa_mama_of_child = Misc.PROMPT_PAPA_MAMA_OF_CHILD % dict(
                    name=response_uuid['first_name'],
                )
                await FSMchild.parent_gender.set()
                await callback_query.message.reply(
                    prompt_papa_mama_of_child,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.FATHER_OF_CHILD, KeyboardType.MOTHER_OF_CHILD,
        KeyboardType.SEP,
        # uuid родителя           # 1
        # KeyboardType.SEP,
    ), c.data),
    state = FSMchild.parent_gender,
    )
async def process_callback_child_unknown_parent_gender(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по заданию папы, мамы
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            await Misc.state_finish(state)
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            await Misc.state_finish(state)
            return
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['name'] = response_sender['response_uuid']['first_name']
            data['parent_gender'] = 'm' if code[0] == str(KeyboardType.FATHER_OF_CHILD) else 'f'
            await ask_child(callback_query.message, state, data, children=response_sender['response_uuid']['children'])


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.NEW_CHILD,
        KeyboardType.SEP,
        # uuid потомка папы или мамы           # 1
        # KeyboardType.SEP,
    ), c.data),
    state = FSMchild.ask,
    )
async def process_callback_new_child(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            return
        await FSMchild.next()
        await callback_query.message.reply(
            Misc.PROMPT_NEW_CHILD % dict(name=response_sender['response_uuid']['first_name']),
            reply_markup=Misc.reply_markup_cancel_row(),
        )


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.KEYS,
        KeyboardType.SEP,
        # uuid себя или родственника           # 1
        # KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_keys(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Заменить контакты

    (В апи контакты - это keys)
    """
    if callback_query.message:
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(
            owner_tg_user=callback_query.from_user,
            uuid=uuid,
            check_owned_only=False
        )
        if not response_sender:
            return
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        response_uuid = response_sender['response_uuid']
        await FSMkey.ask.set()
        await callback_query.message.reply(
            Misc.PROMPT_KEYS % dict(
                name=response_uuid['first_name'],
                his_her= 'Ваши' if response_uuid['uuid'] == response_sender['uuid'] else Misc.his_her(response_uuid),
            ),
            reply_markup=Misc.reply_markup_cancel_row(),
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMkey.ask,
)
async def get_keys(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(Misc.MSG_ERROR_TEXT_ONLY, reply_markup=Misc.reply_markup_cancel_row())
        return
    if re.search(Misc.RE_UUID, message.text):
        await message.reply(
            'Не похоже, что это контакты. Напишите ещё раз или Отмена',
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    async with state.proxy() as data:
        uuid = data.get('uuid')
        if uuid:
            response_sender = await Misc.check_owner(
                owner_tg_user=message.from_user,
                uuid=uuid
            )
            if response_sender:
                strs = re.split('\n+', message.text)
                keys = []
                for s in strs:
                    s = s.strip()
                    if s and s not in keys:
                        keys.append(s)
                if keys:
                    try:
                        status, response = await Misc.api_request(
                            path='/api/addkey',
                            method='post',
                            json=dict(
                                tg_token=settings.TOKEN,
                                owner_uuid=response_sender['uuid'],
                                user_uuid=response_sender['response_uuid']['uuid'],
                                keys=keys,
                        ))
                        if status == 400 and response.get('profile'):
                            # 'Контакт "%s" есть уже у другого пользователя' % value
                            bot_data = await bot.get_me()
                            await message.reply(
                                response['message'] + \
                                ': ' + Misc.get_deeplink_with_name(response['profile'], bot_data) + '\n\n' + \
                                ('Контакты у %s не изменены' % \
                                 Misc.get_deeplink_with_name(response_sender['response_uuid'], bot_data
                                )),
                                disable_web_page_preview=True,
                             )
                        elif status == 400 and response.get('message'):
                            await message.reply(response['message'])
                        elif status == 200:
                            await message.reply('Контакты зафиксированы')
                            await Misc.show_cards(
                                [response],
                                message,
                                bot,
                                response_from=response_sender,
                            )
                    except:
                        pass
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CHANGE_OWNER,
        KeyboardType.SEP,
        # uuid родственника           # 1
        # KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_change_owner(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Заменить владельца
    """
    if callback_query.message:
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(
            owner_tg_user=callback_query.from_user,
            uuid=uuid,
            check_owned_only=True
        )
        if not response_sender:
            return
        bot_data = await bot.get_me()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        await FSMchangeOwner.ask.set()
        await callback_query.message.reply(
            Misc.PROMPT_CHANGE_OWNER % dict(
                iof=response_sender['response_uuid']['first_name'],
                bot_data_username=bot_data['username'],
                his_her=Misc.his_her(response_sender['response_uuid']),
            ),
            reply_markup=Misc.reply_markup_cancel_row(),
            disable_web_page_preview=True,
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMchangeOwner.ask,
)
async def get_new_owner(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(Misc.MSG_ERROR_TEXT_ONLY, reply_markup=Misc.reply_markup_cancel_row())
        return
    async with state.proxy() as data:
        uuid = data.get('uuid')
        if uuid:
            response_sender = await Misc.check_owner(
                owner_tg_user=message.from_user,
                uuid=uuid,
                check_owned_only=True
            )
            if response_sender:
                user_uuid_to = Misc.uuid_from_text(message.text)
                if not user_uuid_to:
                    await message.reply(
                        Misc.MSG_ERROR_UUID_NOT_VALID + '\nПовторите, пожалуйста' ,
                        reply_markup=Misc.reply_markup_cancel_row()
                    )
                    return
                response_from = response_sender['response_uuid']
                status_to, response_to = await Misc.get_user_by_uuid(user_uuid_to)
                if status_to == 400:
                    if response_to.get('message'):
                        reply = response_to['message']
                    else:
                        reply = Misc.MSG_USER_NOT_FOUND
                    await message.reply(reply)
                elif status_to == 200 and response_to:
                    bot_data = await bot.get_me()
                    iof_from = Misc.get_deeplink_with_name(response_from, bot_data)
                    iof_to = Misc.get_deeplink_with_name(response_to, bot_data)
                    if response_from['owner_id'] == response_to['user_id']:
                        # Сам себя назначил
                        await message.reply(
                            Misc.PROMPT_CHANGE_OWNER_SUCCESS % dict(
                                iof_from=iof_from, iof_to=iof_to
                        ))
                        # state_finish, return
                    elif response_to['owner_id']:
                        await message.reply('Нельзя назначить владельцем - неактивного пользователя')
                        # state_finish, return
                    else:
                        data['uuid_owner'] = response_to['uuid']
                        callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                            keyboard_type=KeyboardType.CHANGE_OWNER_CONFIRM,
                            uuid=uuid,
                            sep=KeyboardType.SEP,
                        )
                        inline_btn_change_owner_confirm = InlineKeyboardButton(
                            'Согласна' if response_sender.get('gender') == 'f' else 'Согласен',
                            callback_data=callback_data,
                        )
                        reply_markup = InlineKeyboardMarkup()
                        reply_markup.row(inline_btn_change_owner_confirm, Misc.inline_button_cancel())
                        await FSMchangeOwner.confirm.set()
                        await message.reply(
                            Misc.PROMPT_CHANGE_OWNER_CONFIRM % dict(
                                iof_from=iof_from, iof_to=iof_to
                            ), reply_markup=reply_markup,
                        )
                        return
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CHANGE_OWNER_CONFIRM,
        KeyboardType.SEP,
        # uuid родственника           # 1
        # KeyboardType.SEP,
    ), c.data,
    ), state=FSMchangeOwner.confirm,
    )
async def process_callback_change_owner_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Заменить имя, фамилию, отчество
    """
    if callback_query.message:
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(
            owner_tg_user=callback_query.from_user,
            uuid=uuid,
            check_owned_only=True
        )
        if not response_sender:
            await callback_query.message.reply('Пока Вы здесь думали, Вы же изменили владение с другого устройства')
        else:
            bot_data = await bot.get_me()
            state = dp.current_state()
            async with state.proxy() as data:
                if data.get('uuid') != response_sender['response_uuid']['uuid'] or \
                   not data.get('uuid_owner'):
                    # fool proof
                    pass
                else:
                    status_to, response_to = await Misc.get_user_by_uuid(data['uuid_owner'])
                    if status_to == 400:
                        if response_to.get('message'):
                            reply = response_to['message']
                        else:
                            reply = Misc.MSG_ERROR_API
                    elif status_to != 200 or not response_to:
                        reply = Misc.MSG_ERROR_API
                    else:
                        status, response = await Misc.put_user_properties(
                            uuid=uuid,
                            owner_uuid=data['uuid_owner'],
                        )
                        if status == 200:
                            bot_data = await bot.get_me()
                            iof_from = Misc.get_deeplink_with_name(response_sender['response_uuid'], bot_data)
                            iof_to = Misc.get_deeplink_with_name(response_to, bot_data)
                            reply = Misc.PROMPT_CHANGE_OWNER_SUCCESS % dict(
                                    iof_from=iof_from, iof_to=iof_to
                            )
                            if response_to.get('tg_data', []):
                                iof_sender = Misc.get_deeplink_with_name(response_sender, bot_data)
                                for tgd in response_to['tg_data']:
                                    try:
                                        await bot.send_message(
                                            tgd['tg_uid'],
                                            Misc.PROMPT_MESSAGE_TO_CHANGED_OWNER % dict(
                                                iof_from=iof_from, iof_sender=iof_sender,
                                            ))
                                    except (ChatNotFound, CantInitiateConversation):
                                        pass

                        elif status == 400 and response.get('message'):
                            reply = response['message']
                        else:
                            reply = Misc.MSG_ERROR_API
                    await callback_query.message.reply(reply)
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.IOF,
        KeyboardType.SEP,
        # uuid своё или родственника           # 1
        # KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_iof(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Заменить имя, фамилию, отчество
    """
    if callback_query.message:
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(
            owner_tg_user=callback_query.from_user,
            uuid=uuid
        )
        if not response_sender:
            return
        response_uuid = response_sender['response_uuid']
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        prompt_iof = Misc.PROMPT_EXISTING_IOF % dict(
            name=response_uuid['first_name'],
        )
        await FSMexistingIOF.ask.set()
        await bot.send_message(
            callback_query.from_user.id,
            prompt_iof,
            reply_markup=Misc.reply_markup_cancel_row(),
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMexistingIOF.ask,
)
async def put_change_existing_iof(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(Misc.MSG_ERROR_TEXT_ONLY, reply_markup=Misc.reply_markup_cancel_row())
        return
    first_name = Misc.strip_text(message.text)
    if re.search(Misc.RE_UUID, first_name):
        await message.reply(
            Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
                     
    async with state.proxy() as data:
        uuid = data.get('uuid')
    if uuid:
        response_sender = await Misc.check_owner(
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
                await Misc.show_cards(
                    [response],
                    message,
                    bot,
                    response_from=response_sender,
                )
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.OTHER,
        KeyboardType.SEP,
        # uuid своё ил родственника           # 1
        # KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_other(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Ввести другие данные человека: пол, дата рождения, дата смерти, если это родственник
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            return
        response_uuid = response_sender['response_uuid']
        dict_gender = dict(
            keyboard_type=KeyboardType.OTHER_MALE,
            sep=KeyboardType.SEP,
        )
        callback_data_template = '%(keyboard_type)s%(sep)s'
        inline_button_male = InlineKeyboardButton('Муж', callback_data=callback_data_template % dict_gender)
        dict_gender.update(keyboard_type=KeyboardType.OTHER_FEMALE)
        inline_button_female = InlineKeyboardButton('Жен', callback_data=callback_data_template % dict_gender)
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_button_male, inline_button_female, Misc.inline_button_cancel())
        await FSMother.gender.set()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['is_owned'] = bool(response_uuid['owner_id'])
            data['name'] = response_uuid['first_name']
        his_her = 'Ваш' if response_sender['uuid'] == response_uuid['uuid'] else 'его (её)'
        await callback_query.message.reply(
            Misc.show_other_data(response_uuid) + '\n' + \
            Misc.PROMPT_GENDER % dict(his_her=his_her),
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMother.gender,
)
async def got_gender_text(message: types.Message, state: FSMContext):
    await message.reply(
        'Ожидается выбор пола, нажатием одной из кнопок, в сообщении выше',
        reply_markup=Misc.reply_markup_cancel_row(),
    )


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.OTHER_MALE, KeyboardType.OTHER_FEMALE,
        KeyboardType.SEP,
    ), c.data,
    ), state=FSMother.gender,
    )
async def process_callback_other_gender(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Ввести другие данные человека: пол, дата рождения, дата смерти, если это родственник
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        async with state.proxy() as data:
            if data.get('uuid'):
                uuid = data['uuid']
            if uuid:
                response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
                if not response_sender:
                    await Misc.state_finish(state)
                    return
                data['is_male'] = code[0] == str(KeyboardType.OTHER_MALE)
                response_uuid = response_sender['response_uuid']
                dict_dob_unknown = dict(
                    keyboard_type=KeyboardType.OTHER_DOB_UNKNOWN,
                    sep=KeyboardType.SEP,
                )
                callback_data_template = '%(keyboard_type)s%(sep)s'
                inline_button_dob_unknown = InlineKeyboardButton(
                    'Не знаю', callback_data=callback_data_template % dict_dob_unknown
                )
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(inline_button_dob_unknown, Misc.inline_button_cancel())
                await FSMother.next()
                if not data.get('is_owned'):
                    his_her = 'Ваш'
                elif data['is_male']:
                    his_her = 'его'
                else:
                    his_her = 'её'
                await callback_query.message.reply(
                    Misc.PROMPT_DOB % dict(name=data['name'], his_her=his_her),
                    reply_markup=reply_markup,
                )
            else:
                await Misc.state_finish(state)
    else:
        await Misc.state_finish(state)

async def put_other_data(message, tg_user_sender, state, data):
    if data.get('uuid') and isinstance(data.get('is_male'), bool):
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=data['uuid'])
        if response_sender:
            dob = data.get('dob', '')
            dod = data.get('dod', '')
            is_male = data['is_male']
            # TODO Пока не отработано меню для умер, но не известна дата
            status, response = await Misc.put_user_properties(
                uuid=data['uuid'],
                gender='m' if is_male else 'f',
                dob=dob,
                dod=dod,
                is_dead = '1' if dod else '',
            )
            if status == 200 and response:
                await message.reply('Данные внесены:\n' + Misc.show_other_data(response), disable_web_page_preview=True,)
                await Misc.show_cards(
                    [response],
                    message,
                    bot,
                    response_from=response_sender,
                    tg_user_from=tg_user_sender,
                )
            elif status == 400 and response and response.get('message'):
                await message.reply('Ошибка!\n%s\n\nНазначайте сведения по новой' % response['message'])
            else:
                await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


async def draw_dod(message, state, data):
    dict_dod = dict(
        keyboard_type=KeyboardType.OTHER_DOD_UNKNOWN,
        sep=KeyboardType.SEP,
    )
    callback_data_template = '%(keyboard_type)s%(sep)s'
    inline_button_dod_unknown = InlineKeyboardButton(
        '%s или не знаю' % ('Жив' if data['is_male'] else 'Жива'),
        callback_data=callback_data_template % dict_dod
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_button_dod_unknown, Misc.inline_button_cancel())
    if data['is_male']:
        his_her = 'его'
    else:
        his_her = 'её'
    await FSMother.next()
    await message.reply(
        Misc.PROMPT_DOD % dict(name=data.get('name', ''), his_her=his_her),
        reply_markup=reply_markup,
    )

@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.OTHER_DOB_UNKNOWN,
        KeyboardType.SEP,
    ), c.data,
    ), state=FSMother.dob,
    )
async def process_callback_other_dob_unknown(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Ввести пустую дату рождения
    """
    if callback_query.message:
        async with state.proxy() as data:
            if data.get('uuid') and isinstance(data.get('is_male'), bool) and isinstance(data.get('is_owned'), bool):
                data['dob'] = ''
                if data.get('is_owned'):
                    await draw_dod(callback_query.message, state, data)
                else:
                    await put_other_data(callback_query.message, callback_query.from_user, state, data)
            else:
                await Misc.state_finish(state)
    else:
        await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.OTHER_DOD_UNKNOWN,
        KeyboardType.SEP,
    ), c.data,
    ), state=FSMother.dod,
    )
async def process_callback_other_dod_unknown(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Ввести пустую дату смерти
    """
    if callback_query.message:
        async with state.proxy() as data:
            if data.get('uuid') and isinstance(data.get('is_male'), bool) and isinstance(data.get('is_owned'), bool):
                data['dod'] = ''
                await put_other_data(callback_query.message, callback_query.from_user, state, data)
            else:
                await Misc.state_finish(state)
    else:
        await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMother.dob,
)
async def get_dob(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    async with state.proxy() as data:
        if data.get('uuid') and isinstance(data.get('is_male'), bool) and isinstance(data.get('is_owned'), bool):
            message_text = Misc.strip_text(message.text)
            dob = ''
            try:
                dob = message_text.split()[0]
            except IndexError:
                pass
            data['dob'] = dob
            if data.get('is_owned'):
                await draw_dod(message, state, data)
            else:
                await put_other_data(message, message.from_user, state, data)
        else:
            await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMother.dod,
)
async def get_dod(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    async with state.proxy() as data:
        if data.get('uuid') and isinstance(data.get('is_male'), bool) and isinstance(data.get('is_owned'), bool):
            message_text = Misc.strip_text(message.text)
            dod = ''
            try:
                dod = message_text.split()[0]
            except IndexError:
                pass
            data['dod'] = dod
            await put_other_data(message, message.from_user, state, data)
        else:
            await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.SEND_MESSAGE,
        KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_send_message(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Отправка сообщения
    """
    if callback_query.message:
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        status_to, profile_to = await Misc.get_user_by_uuid(uuid)
        if not (status_to == 200 and profile_to):
            return

        await FSMsendMessage.ask.set()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        bot_data = await bot.get_me()
        iof_link = Misc.get_deeplink_with_name(profile_to, bot_data)
        await callback_query.message.reply(
            'Напишите или перешлите мне сообщение для отправки <b>%s</b>' % iof_link,
            reply_markup=Misc.reply_markup_cancel_row(),
            disable_web_page_preview=True,
        )

@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.SHOW_MESSAGES,
        KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_show_messages(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Показ сообщений
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        status, response = await Misc.api_request(
            path='/api/tg_message',
            method='get',
            params=dict(uuid=uuid),
        )
        logging.debug('get_user_messages, uuid=%s, status: %s' % (uuid, status))
        logging.debug('get_user_messages, uuid=%s, response: %s' % (uuid, response))
        if status != 200:
            return
        bot_data = await bot.get_me()
        if response:
            await bot.send_message(
                tg_user_sender.id,
                text='Ниже последние сообщения к %s ...' % \
                    Misc.get_deeplink_with_name(response[0]['user_to'], bot_data),
                disable_web_page_preview=True,
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
                    if m['operation_type_id'] == OperationType.NULLIFY_TRUST:
                        msg += 'в связи с тем что забыл(а)\n'
                    elif m['operation_type_id'] == OperationType.MISTRUST:
                        msg += 'в связи с утратой доверия\n'
                    elif m['operation_type_id'] == OperationType.TRUST:
                        msg += 'в связи с тем что доверяет\n'
                    elif m['operation_type_id'] in (OperationType.THANK, OperationType.TRUST_AND_THANK,):
                        msg += 'с благодарностью\n'
                user_to_delivered = None
                if m['user_to_delivered']:
                    msg += 'Доставлено'
                    if m['user_to_delivered']['id'] != m['user_to']['id']:
                        msg += ' к %(user_to_delivered)s !!!'
                        user_to_delivered = Misc.get_deeplink_with_name(m['user_to_delivered'], bot_data)
                else:
                    msg += 'Не доставлено, лишь сохранено'
                msg += '\nНиже само сообщение:'
                msg %= dict(
                    n=n,
                    datetime_string=Misc.datetime_string(m['timestamp']),
                    user_from=Misc.get_deeplink_with_name(m['user_from'], bot_data),
                    user_to=Misc.get_deeplink_with_name(m['user_to'], bot_data),
                    user_to_delivered=user_to_delivered,
                )
                await bot.send_message(tg_user_sender.id, text=msg, disable_web_page_preview=True,)
                try:
                    await bot.forward_message(
                        tg_user_sender.id,
                        from_chat_id=m['from_chat_id'],
                        message_id=m['message_id'],
                    )
                except:
                    await bot.send_message(
                        tg_user_sender.id,
                        text='Не удалось отобразить сообщение!',
                        disable_web_page_preview=True,
                    )
        else:
            status_to, profile_to = await Misc.get_user_by_uuid(uuid)
            if status_to == 200 and profile_to:
                msg = '%(full_name)s не получал%(a)s сообщений' % dict(
                    full_name=Misc.get_deeplink_with_name(profile_to, bot_data),
                    a='а' if profile_to.get('gender') == 'f' else '' if profile_to.get('gender') == 'm' else '(а)',
                )
            else:
                msg = 'Сообщения не найдены'
            await bot.send_message(tg_user_sender.id, text=msg, disable_web_page_preview=True,)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMsendMessage.ask,
)
async def got_message_to_send(message: types.Message, state: FSMContext):
    msg_saved = 'Сообщение сохранено'
    async with state.proxy() as data:
        if data.get('uuid'):
            status_to, profile_to = await Misc.get_user_by_uuid(data['uuid'], with_owner=True)
            if status_to == 200 and profile_to:
                status_from, profile_from = await Misc.post_tg_user(message.from_user)
                if status_from == 200 and profile_from:

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
                        bot_data = await bot.get_me()
                        for tgd in tg_user_to_tg_data:
                            try:
                                try:
                                    await bot.send_message(
                                        tgd['tg_uid'],
                                        text=Misc.MSG_YOU_GOT_MESSAGE % Misc.get_deeplink_with_name(profile_from, bot_data),
                                        disable_web_page_preview=True,
                                    )
                                    await bot.forward_message(
                                        tgd['tg_uid'],
                                        from_chat_id=message.chat.id,
                                        message_id=message.message_id,
                                    )
                                    await message.reply('Сообщение доставлено')
                                except CantTalkWithBots:
                                    await message.reply('Сообщения к боту запрещены')
                            except (ChatNotFound, CantInitiateConversation):
                                user_to_delivered_uuid = None
                                await message.reply(msg_saved)
                    else:
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

    await Misc.state_finish(state)


async def do_process_ability(message: types.Message, uuid=None):
    reply_markup = Misc.reply_markup_cancel_row()
    await FSMability.ask.set()
    state = dp.current_state()
    if uuid:
        async with state.proxy() as data:
            data['uuid'] = uuid
    await message.reply(Misc.PROMPT_ABILITY, reply_markup=reply_markup)


async def do_process_wish(message: types.Message, uuid=None):
    reply_markup = Misc.reply_markup_cancel_row()
    await FSMwish.ask.set()
    state = dp.current_state()
    if uuid:
        async with state.proxy() as data:
            data['uuid'] = uuid
    await message.reply(Misc.PROMPT_WISH, reply_markup=reply_markup)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('map', 'карта'),
    state=None,
)
async def process_command_map(message):
    await bot.send_message(
        message.from_user.id,
        text=Misc.get_html_a(href=settings.MAP_HOST, text='Карта участников'),
        disable_web_page_preview=True,
    )

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('setvozm', 'возможности'),
    state=None,
)
async def process_command_ability(message):
    await do_process_ability(message)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.ABILITY,       # 0
        KeyboardType.SEP,
        # uuid, кому                # 1
        # KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_ability(callback_query: types.CallbackQuery, state: FSMContext):
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        uuid = code[1]
        if uuid and not await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid):
            return
    except IndexError:
        uuid = None
    await do_process_ability(callback_query.message, uuid=uuid)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('setpotr', 'потребности'),
    state=None,
)
async def process_command_wish(message):
    await do_process_wish(message)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.WISH,       # 0
        KeyboardType.SEP,
        # uuid, кому                # 1
        # KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_wish(callback_query: types.CallbackQuery, state: FSMContext):
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        uuid = code[1]
        if uuid and not await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid):
            return
    except IndexError:
        uuid = None
    await do_process_wish(callback_query.message, uuid=uuid)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CANCEL_ANY,
        KeyboardType.SEP,
        ), c.data
    ),
    state='*',
    )
async def process_callback_cancel_any(callback_query: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await Misc.state_finish(state)
        await callback_query.message.reply('Вы отказались от ввода данных')


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMability.ask,
)
async def put_ability(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_ABILITY,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    if re.search(Misc.RE_UUID, message.text):
        await message.reply(
            'Не похоже, что это возможности. Напишите ещё раз или Отмена',
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return

    logging.debug('put_ability: post tg_user data')
    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender == 200:
        user_uuid = response_sender['uuid']
        async with state.proxy() as data:
            if data.get('uuid'):
                user_uuid = data['uuid']
            data['uuid'] = ''
        payload_add = dict(
            tg_token=settings.TOKEN,
            user_uuid=user_uuid,
            update_main=True,
            text=message.text.strip(),
        )
        try:
            status_add, response_add = await Misc.api_request(
                path='/api/addorupdateability',
                method='post',
                json=payload_add,
            )
        except:
            status_add = response_add = None
        if status_add == 200:
            await message.reply('Возможности учтены')
        try:
            status, response = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=dict(uuid=user_uuid),
            )
            logging.debug('get_user_profile after put ability, status: %s' % status)
            logging.debug('get_user_profile after put ability, response: %s' % response)
            if status_sender == 200:
                await Misc.show_cards(
                    [response],
                    message,
                    bot,
                    response_from=response_sender,
                )
            else:
                await message.reply(Misc.MSG_ERROR_API)
        except:
            pass
    else:
        await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMwish.ask,
)
async def put_wish(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        reply_markup = Misc.reply_markup_cancel_row()
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_WISH,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    if re.search(Misc.RE_UUID, message.text):
        await message.reply(
            'Не похоже, что это потребности. Напишите ещё раз или Отмена',
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return

    logging.debug('put_wish: post tg_user data')
    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender == 200:
        user_uuid = response_sender['uuid']
        async with state.proxy() as data:
            if data.get('uuid'):
                user_uuid = data['uuid']
            data['uuid'] = ''
        payload_add = dict(
            tg_token=settings.TOKEN,
            user_uuid=user_uuid,
            update_main=True,
            text=message.text.strip(),
        )
        try:
            status_add, response_add = await Misc.api_request(
                path='/api/addorupdatewish',
                method='post',
                json=payload_add,
            )
        except:
            status_add = response_add = None
        if status_add == 200:
            await message.reply('Потребности учтены')
        try:
            status, response = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=dict(uuid=user_uuid),
            )
            logging.debug('get_user_profile after put wish, status: %s' % status)
            logging.debug('get_user_profile after put wish, response: %s' % response)
            if status_sender == 200:
                await Misc.show_cards(
                    [response],
                    message,
                    bot,
                    response_from=response_sender,
                )
            else:
                await message.reply(Misc.MSG_ERROR_API)
        except:
            pass
    else:
        await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMphoto.ask,
)
async def put_photo(message: types.Message, state: FSMContext):
    if message.content_type not in (ContentType.PHOTO, ContentType.DOCUMENT):
        reply_markup = Misc.reply_markup_cancel_row()
        await message.reply(
            Misc.MSG_ERROR_PHOTO_ONLY + '\n\n' + \
            Misc.PROMPT_PHOTO,
            reply_markup=reply_markup,
        )
        return

    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender == 200:
        user_uuid = None
        async with state.proxy() as data:
            if data.get('uuid'):
                user_uuid = data['uuid']
            data['uuid'] = ''
        if user_uuid:
            image = BytesIO()
            if message.content_type == ContentType.PHOTO:
                await message.photo[-1].download(destination_file=image)
            else:
                # document
                await message.document.download(destination_file=image)
            image = base64.b64encode(image.read()).decode('UTF-8')
            status, response = await Misc.put_user_properties(
                uuid=user_uuid,
                photo=image,
            )
            msg_error = '<b>Ошибка</b>. Фото не внесено.\n'
            if status == 200:
                await message.reply('%s : фото внесено' % response['first_name'])
                await Misc.show_cards(
                    [response],
                    message,
                    bot,
                    response_from=response_sender,
                )
            elif status == 400:
                if response.get('message'):
                    await message.reply(msg_error + response['message'])
                else:
                    await message.reply(msg_error + Misc.MSG_ERROR_API)
            else:
                await message.reply(msg_error + Misc.MSG_ERROR_API)
        else:
            await message.reply(msg_error + Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.PHOTO,       # 0
        KeyboardType.SEP,
        # uuid, кому              # 1
        # KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_photo(callback_query: types.CallbackQuery, state: FSMContext):
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        uuid = code[1]
        if uuid and not await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid):
            return
    except IndexError:
        uuid = None
    if uuid:
        inline_button_cancel = Misc.inline_button_cancel()
        reply_markup = InlineKeyboardMarkup()
        await FSMphoto.ask.set()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        prompt_photo = Misc.PROMPT_PHOTO
        status, response = await Misc.get_user_by_uuid(uuid)
        if status == 200 and response and Misc.is_photo_downloaded(response):
            prompt_photo += '\n' + Misc.PROMPT_PHOTO_REMOVE
            callback_data_remove = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                keyboard_type=KeyboardType.PHOTO_REMOVE,
                sep=KeyboardType.SEP,
                uuid=uuid,
            )
            inline_btn_remove = InlineKeyboardButton(
                'Удалить',
                callback_data=callback_data_remove,
            )
            reply_markup.row(inline_button_cancel, inline_btn_remove)
        else:
            reply_markup.row(inline_button_cancel)
        await callback_query.message.reply(prompt_photo, reply_markup=reply_markup)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.PHOTO_REMOVE,      # 0
        KeyboardType.SEP,
        # uuid, кому                    # 1
        # KeyboardType.SEP,
    ), c.data
    ),
    state=FSMphoto.ask)
async def process_callback_photo_remove(callback_query: types.CallbackQuery, state: FSMContext):
    code = callback_query.data.split(KeyboardType.SEP)
    try:
        uuid = code[1]
    except IndexError:
        uuid = None
    if uuid:
        status, response = await Misc.get_user_by_uuid(uuid)
        if status == 200 and response:
            await FSMphoto.next()
            inline_button_cancel = Misc.inline_button_cancel()
            callback_data_remove = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                keyboard_type=KeyboardType.PHOTO_REMOVE_CONFIRMED,
                sep=KeyboardType.SEP,
                uuid=uuid,
            )
            inline_btn_remove = InlineKeyboardButton(
                'Да, удалить',
                callback_data=callback_data_remove,
            )
            reply_markup = InlineKeyboardMarkup()
            reply_markup.row(inline_button_cancel, inline_btn_remove)
            full_name = response['first_name']
            prompt_photo_confirm = (
                'Подтвердите <b>удаление фото</b> у:\n'
                '<b>%s</b>\n' % full_name
            )
            await callback_query.message.reply(prompt_photo_confirm, reply_markup=reply_markup)
        else:
            await Misc.state_finish(state)
    else:
        await Misc.state_finish(state)

@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.PHOTO_REMOVE_CONFIRMED,      # 0
        KeyboardType.SEP,
        # uuid, кому                    # 1
        # KeyboardType.SEP,
    ), c.data
    ),
    state=FSMphoto.remove)
async def process_callback_photo_remove_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    code = callback_query.data.split(KeyboardType.SEP)
    try:
        uuid = code[1]
    except IndexError:
        uuid = None
    if uuid:
        logging.debug('put (remove) photo: post tg_user data')
        tg_user_sender = callback_query.from_user
        status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
        if status_sender == 200 and response_sender:
            status, response = await Misc.put_user_properties(
                photo='',
                uuid=uuid,
            )
            if status == 200:
                await callback_query.message.reply('%s: фото удалено' % response['first_name'])
                await Misc.show_cards(
                    [response],
                    callback_query.message,
                    bot,
                    response_from=response_sender,
                )
            elif status == 400:
                if response.get('message'):
                    await message.reply(response['message'])
                else:
                    await message.reply(Misc.MSG_ERROR_API)
            else:
                await message.reply(Misc.MSG_ERROR_API)
        else:
            await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMnewIOF.ask,
)
async def put_new_iof(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_NEW_IOF,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    first_name = Misc.strip_text(message.text)
    if re.search(Misc.RE_UUID, first_name):
        await message.reply(
            Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return

    logging.debug('put_new_iof: post tg_user data')
    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender == 200 and response_sender and response_sender.get('user_id'):
        payload_iof = dict(
            tg_token=settings.TOKEN,
            owner_id=response_sender['user_id'],
            first_name=first_name,
        )
        logging.debug('post iof, payload: %s' % payload_iof)
        status, response = await Misc.api_request(
            path='/api/profile',
            method='post',
            data=payload_iof,
        )
        logging.debug('post iof, status: %s' % status)
        logging.debug('post iof, response: %s' % response)
        if status == 200:
            await message.reply('Добавлен(а)')
            try:
                status, response = await Misc.get_user_by_uuid(response['uuid'])
                if status == 200:
                    await Misc.show_cards(
                        [response],
                        message,
                        bot,
                        response_from=response_sender,
                    )
            except:
                pass
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('new', ),
    state=None,
)
async def process_command_new(message: types.Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        await FSMnewIOF.ask.set()
        state = dp.current_state()
        await message.reply(Misc.PROMPT_NEW_IOF, reply_markup=Misc.reply_markup_cancel_row())
        if response_sender.get('created'):
            await Misc.update_user_photo(bot, message.from_user, response_sender)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('findpotr', 'findvozm', 'findperson',  ),
    state=None,
)
async def process_commands_query(message: types.Message, state: FSMContext):
    message_text = message.text.split()[0].lstrip('/')
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        await FSMquery.ask.set()
        state = dp.current_state()
        async with state.proxy() as data:
            if message_text == 'findpotr':
                query_what = 'query_wish'
            elif message_text == 'findvozm':
                query_what = 'query_ability'
            elif message_text == 'findperson':
                query_what = 'query_person'
            else:
                return
            data['what'] = query_what
        await message.reply(Misc.PROMPT_QUERY[query_what], reply_markup=Misc.reply_markup_cancel_row())
        if response_sender.get('created'):
            await Misc.update_user_photo(bot, message.from_user, response_sender)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMquery.ask,
)
async def process_make_query(message: types.Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    state = dp.current_state()
    async with state.proxy() as data:
        try:
            data['what']
            Misc.PROMPT_QUERY[data['what']]
            valid_data = True
        except KeyError:
            valid_data = False
        if valid_data:
            a_found = None
            if message.content_type != ContentType.TEXT:
                reply_markup = Misc.reply_markup_cancel_row()
                await message.reply(
                    Misc.MSG_ERROR_TEXT_ONLY + '\n\n' +  Misc.PROMPT_QUERY[data['what']],
                    reply_markup=Misc.reply_markup_cancel_row(),
                )
                return
            if len(message.text.strip()) < settings.MIN_LEN_SEARCHED_TEXT:
                reply = Misc.PROMPT_SEARCH_TEXT_TOO_SHORT
            else:
                if re.search(Misc.RE_UUID, message.text):
                    await message.reply(
                        'Не похоже, что это строка поиска. Напишите ещё раз или Отмена',
                        reply_markup=Misc.reply_markup_cancel_row(),
                    )
                    return
                search_phrase = Misc.text_search_phrase(
                    message.text,
                    MorphAnalyzer,
                )
                if not search_phrase:
                    reply = Misc.PROMPT_SEARCH_PHRASE_TOO_SHORT
                else:
                    status, a_found = await Misc.search_users(data['what'], search_phrase)
                    if status != 200:
                        a_found = None
                    elif not a_found:
                        reply = Misc.PROMPT_NOTHING_FOUND
            if a_found:
                bot_data = await bot.get_me()
                await Misc.show_deeplinks(a_found, message, bot_data)
            elif reply:
                await message.reply(reply)
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.TRUST_THANK,
        KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_tn(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по нажатию кнопок (не)доверия, забвения

    На входе строка:
        <KeyboardType.TRUST_THANK>          # 0
        <KeyboardType.SEP>
        <operation_type_id>                 # 1
        <KeyboardType.SEP>
        <user_uuid_to (без знаков -)>       # 2
        <KeyboardType.SEP>
        <message_to_forward_id>             # 3
        <KeyboardType.SEP>
    """
    tg_user_sender = callback_query.from_user
    status_sender, profile_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender != 200 or not profile_sender:
        return
    group_member = callback_query.message.chat.type in (types.ChatType.GROUP, types.ChatType.SUPERGROUP) \
        and dict(
                group_chat_id=callback_query.message.chat.id,
                group_title=callback_query.message.chat.title,
                group_type=callback_query.message.chat.type,
                user_tg_uid=tg_user_sender.id,
            ) \
        or None
    code = callback_query.data.split(KeyboardType.SEP)
    try:
        operation_type_id=int(code[1])
        if not operation_type_id or operation_type_id not in (
               OperationType.TRUST_AND_THANK, OperationType.TRUST,
               OperationType.MISTRUST, OperationType.NULLIFY_TRUST,
           ):
            return
        uuid = Misc.uuid_from_text(code[2], unstrip=True)
        if not uuid:
            return
        status_to, profile_to = await Misc.get_user_by_uuid(uuid)
        if status_to != 200 or not profile_to:
            return
        if profile_sender['uuid'] == profile_to['uuid']:
            if group_member:
                if operation_type_id in (OperationType.TRUST_AND_THANK, OperationType.TRUST):
                    try:
                        await bot.answer_callback_query(
                                callback_query.id,
                                text='Благодарности и доверия самому себе не предусмотрены',
                                show_alert=True,
                            )
                    except (ChatNotFound, CantInitiateConversation):
                        pass
                return
            else:
                return
        try:
            message_to_forward_id = int(code[3])
        except (ValueError, IndexError,):
            message_to_forward_id = None
    except (ValueError, IndexError,):
        return

    data_ = dict(
        profile_from = profile_sender,
        profile_to = profile_to,
        operation_type_id = operation_type_id,
        tg_user_sender_id = tg_user_sender.id,
        message_to_forward_id = message_to_forward_id,
        group_member= group_member,
    )
    if group_member:
        await put_thank_etc(tg_user_sender, data=data_, state=None, comment_message=None)
        return

    if operation_type_id == OperationType.TRUST:
        msg_what = 'к <b>доверию</b>'
    if operation_type_id == OperationType.TRUST_AND_THANK:
        status_relations, response_relations = await Misc.call_response_relations(profile_sender, profile_to)
        if response_relations and response_relations['from_to']['is_trust'] and response_relations['from_to']['thanks_count']:
            msg_what = 'к <b>благодарности</b>'
        else:
            msg_what = 'к <b>доверию</b> к'
    elif operation_type_id == OperationType.MISTRUST:
        msg_what = 'к <b>недоверию</b> для'
    else:
        # OperationType.NULLIFY_TRUST
        msg_what = 'к тому что хотите <b>забыть</b>'

    async with state.proxy() as data:
        data.update(data_)
    callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
        keyboard_type=KeyboardType.TRUST_THANK_WO_COMMENT,
        uuid=uuid,
        sep=KeyboardType.SEP,
    )
    inline_btn_wo_comment = InlineKeyboardButton(
        'Без комментария',
        callback_data=callback_data,
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_btn_wo_comment, Misc.inline_button_cancel())
    await FSMtrustThank.ask.set()
    await callback_query.message.reply(
        'Напишите комментарий %(msg_what)s <b>%(name)s</b>' % dict(
            msg_what=msg_what,
            name=profile_to['first_name'],
        ),
        reply_markup=reply_markup,
    )


async def put_thank_etc(tg_user_sender, data, state=None, comment_message=None):
    # Может прийти неколько картинок, .т.е сообщений, чтоб не было
    # много благодарностей и т.п. по нескольким сообщениям
    #
    if state:
        await Misc.state_finish(state)
    try:
        if not data or not data.get('profile_from', {}).get('uuid'):
            raise ValueError
        if not data.get('profile_to', {}).get('uuid'):
            raise ValueError
        if data.get('tg_user_sender_id') != tg_user_sender.id:
            raise ValueError
            await put_thank_etc(tg_user_sender, data, state, comment_message=message)
    except ValueError:
        return

    profile_from = data['profile_from']
    group_member = data.get('group_member')
    if group_member:
        await TgGroupMember.add(**group_member)

    profile_to = data['profile_to']
    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=data.get('operation_type_id'),
        tg_user_id_from=str(tg_user_sender.id),
        user_uuid_to=profile_to['uuid'],
    )
    if data.get('message_to_forward_id'):
        post_op.update(
            tg_from_chat_id=tg_user_sender.id,
            tg_message_id=data['message_to_forward_id'],
        )
    logging.debug('post operation, payload: %s' % post_op)
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post_op,
    )
    logging.debug('post operation, status: %s' % status)
    logging.debug('post operation, response: %s' % response)
    text = None
    operation_done = False
    tg_user_to_tg_data = profile_to.get('tg_data', [])
    if status == 200:
        if post_op['operation_type_id'] == OperationType.MISTRUST:
            text = '%(full_name_from_link)s не доверяет %(full_name_to_link)s'
            operation_done = True
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = '%(full_name_from_link)s забыл(а) %(full_name_to_link)s'
            operation_done = True
        elif post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.TRUST):
            text = '%(full_name_from_link)s %(trusts_or_thanks)s %(full_name_to_link)s'
            operation_done = True
    elif status == 400 and response.get('code', '') == 'already':
        if post_op['operation_type_id'] == OperationType.TRUST:
            text = 'Уже установлено доверие'
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            text = 'Уже установлено недоверие'
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Вы и так не знакомы'

    bot_data = await bot.get_me()
    if operation_done:
        profile_from = response['profile_from']
        profile_to = response['profile_to']
        if text:
            trusts_or_thanks = 'доверяет'
            if response.get('previousstate') and response['previousstate']['is_trust']:
                # точно доверял раньше
                trusts_or_thanks = 'благодарит'
            text = text % dict(
                full_name_from_link=Misc.get_deeplink_with_name(profile_from, bot_data, plus_trusts=True),
                full_name_to_link=Misc.get_deeplink_with_name(profile_to, bot_data, plus_trusts=True),
                trusts_or_thanks=trusts_or_thanks,
            )

    if not text and not operation_done:
        if status == 200:
            text = 'Операция выполнена'
        elif status == 400 and response.get('message'):
            text = response['message']
        else:
            text = 'Простите, произошла ошибка'

    # Это отправителю благодарности и т.п., даже если произошла ошибка
    #
    if text:
        try:
            await bot.send_message(
                tg_user_sender.id,
                text=text,
                disable_web_page_preview=True,
            )
        except (ChatNotFound, CantInitiateConversation):
            pass

    # Это получателю благодарности и т.п.
    #
    comment_delivered = False
    text_to_recipient = text
    if operation_done and data.get('message_to_forward_id') or comment_message:
        text_to_recipient += ' с комментарием:'
    for tgd in tg_user_to_tg_data:
        if operation_done:
            try:
                await bot.send_message(
                    tgd['tg_uid'],
                    text=text_to_recipient,
                    disable_web_page_preview=True,
                )
            except (ChatNotFound, CantInitiateConversation):
                pass
        if operation_done and data.get('message_to_forward_id'):
            try:
                await bot.forward_message(
                    chat_id=tgd['tg_uid'],
                    from_chat_id=tg_user_sender.id,
                    message_id=data['message_to_forward_id'],
                )
            except (ChatNotFound, CantInitiateConversation):
                pass
        if comment_message:
            try:
                await bot.forward_message(
                    tgd['tg_uid'],
                    from_chat_id=comment_message.chat.id,
                    message_id=comment_message.message_id,
                )
                comment_delivered = True
            except (ChatNotFound, CantInitiateConversation):
                pass
    if comment_delivered:
        try:
            await bot.send_message(
                tg_user_sender.id,
                text='Ваш комментарий доставлен к %s' % Misc.get_deeplink_with_name(profile_to, bot_data, plus_trusts=True),
            )
        except (ChatNotFound, CantInitiateConversation):
            pass

    # Тоже получателю благодарности и т.п., но это может быть и чей-то собственный
    #
    if comment_message:
        payload_log_message = dict(
            tg_token=settings.TOKEN,
            from_chat_id=comment_message.chat.id,
            message_id=comment_message.message_id,
            user_from_uuid=profile_from['uuid'],
            user_to_uuid=profile_to['uuid'],
            user_to_delivered_uuid=comment_delivered and profile_to['uuid'] or None,
            operation_type_id=post_op['operation_type_id'],
        )
        try:
            status_log, response_log = await Misc.api_request(
                path='/api/tg_message',
                method='post',
                json=payload_log_message,
            )
        except:
            pass


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMtrustThank.ask,
)
async def process_callback_thank_comment(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        await put_thank_etc(message.from_user, data, state, comment_message=message)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.TRUST_THANK_WO_COMMENT,
        KeyboardType.SEP,
    ), c.data
    ), state=FSMtrustThank.ask,
    )
async def process_callback_thank_wo_comment(callback_query: types.CallbackQuery, state: FSMContext):
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        try:
            uuid=code[1]
        except IndexError:
            raise ValueError
        async with state.proxy() as data:
            if not uuid or not data or data.get('profile_to', {}).get('uuid') != uuid:
                raise ValueError
            await put_thank_etc(tg_user_sender, data, state)
    except ValueError:
        await Misc.state_finish(state)


async def geo(message, state_to_set, uuid=None):
    # Здесь вынужден отказаться от параметра , one_time_keyboard=True
    # Не убирает телеграм "нижнюю" клавиатуру в мобильных клиентах!
    # Убираю "вручную", потом: собщением с reply_markup=types.reply_keyboard.ReplyKeyboardRemove()
    #
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=False)
    button_geo = types.KeyboardButton(text=Misc.PROMPT_LOCATION, request_location=True)
    button_cancel = types.KeyboardButton(text=Misc.PROMPT_CANCEL_LOCATION)
    keyboard.add(button_geo, button_cancel)
    await state_to_set.set()
    state = dp.current_state()
    if uuid:
        async with state.proxy() as data:
            data['uuid'] = uuid
    await bot.send_message(
        message.chat.id,(
            'Пожалуйста, нажмите на кнопку "%s" снизу '
            '(кнопки может и не быть в некоторых клиентах).\n\n'
            'Или введите координаты <i>широта, долгота</i>, '
            'где <i>широта</i> и <i>долгота</i> - числа, возможные для координат!\n\n'
            'Чтобы отказаться, нажмите на кнопку "%s" снизу '
            '(если есть кнопка) или наберите <u>%s</u>\n\n'
        ) % (Misc.PROMPT_LOCATION, Misc.PROMPT_CANCEL_LOCATION, Misc.PROMPT_CANCEL_LOCATION,),
        reply_markup=keyboard
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['setplace', 'место'],
    state=None,
)
async def geo_command_handler(message: types.Message, state: FSMContext):
    await geo(message, state_to_set=FSMgeo.geo)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.LOCATION,
        KeyboardType.SEP,
        # uuid, кому                # 1
        # KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_location(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по местоположению

    На входе строка:
        <KeyboardType.LOCATION>             # 0
        <KeyboardType.SEP>
        uuid                                # 1
        <KeyboardType.SEP>
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        try:
            uuid = code[1]
            if uuid and not await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid):
                return
        except IndexError:
            uuid = None
        await geo(callback_query.message, state_to_set=FSMgeo.geo, uuid=uuid)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('trip', 'тур'),
    state=None,
)
async def trip_geo_command_handler(message: types.Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if settings.TRIP_DATA and settings.TRIP_DATA.get('chat_id') and settings.TRIP_DATA.get('invite_link'):
        if status_sender == 200:
            if response_sender['latitude'] is not None and response_sender['longitude'] is not None:
                callback_data_dict = dict(
                    keyboard_type=KeyboardType.TRIP_NEW_LOCATION,
                    uuid=response_sender['uuid'],
                    sep=KeyboardType.SEP,
                )
                inline_btn_new_location = InlineKeyboardButton(
                    'Задать сейчас',
                    callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % callback_data_dict,
                )
                callback_data_dict.update(keyboard_type=KeyboardType.TRIP_OLD_LOCATION)
                inline_btn_use_old_location = InlineKeyboardButton(
                    'Использовать заданное',
                    callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % callback_data_dict,
                )
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(inline_btn_use_old_location, inline_btn_new_location, Misc.inline_button_cancel())
                address = response_sender.get('address') or '%s,%s' % (response_sender['latitude'], response_sender['longitude'])
                await FSMtrip.ask_geo.set()
                await message.reply(
                    (
                        'Собираю данные для поездки\n\n'
                        'У вас задано местоположение:\n\n%s\n\n'
                        '<u>Использовать заданное</u> местоположение? Или <u>задать сейчас</u> новое местоположение? '
                    ) % address,
                    reply_markup=reply_markup
                )
            else:
                await message.reply('Собираю данные для поездки\n\nУ вас НЕ задано местоположение!')
                await geo(message, state_to_set=FSMtrip.geo, uuid=response_sender['uuid'])
    else:
        await message.reply('В системе пока не предусмотрены туры')


async def prompt_trip_conditions(message, state, profile):
    text_invite = settings.TRIP_DATA['text_with_invite_link'] % settings.TRIP_DATA
    await message.reply(text_invite, reply_markup=types.reply_keyboard.ReplyKeyboardRemove())
    await state.finish()


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.TRIP_NEW_LOCATION, KeyboardType.TRIP_OLD_LOCATION,
        KeyboardType.SEP,
        # uuid задавшего  /trip # 1
        # KeyboardType.SEP,
    ), c.data),
    state = FSMtrip.ask_geo,
    )
async def process_callback_trip_new_location(callback_query: types.CallbackQuery, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(callback_query.from_user)
    if status_sender == 200:
        code = callback_query.data.split(KeyboardType.SEP)
        try:
            uuid = code[1]
            if response_sender.get('uuid') == uuid:
                if int(code[0]) == KeyboardType.TRIP_NEW_LOCATION:
                    await geo(callback_query.message, state_to_set=FSMtrip.geo, uuid=uuid)
                else:
                    # KeyboardType.TRIP_OLD_LOCATION
                    if response_sender['latitude'] is not None and response_sender['longitude'] is not None:
                        await prompt_trip_conditions(callback_query.message, state, response_sender)
                    else:
                        state.finish()
                        return
            else:
                state.finish()
                return
        except IndexError:
            state.finish()
            return
    else:
        state.finish()


async def put_location(message, state, show_card=False):
    """
    Записать местоположение пользователя телеграма или uuid в состоянии

    В случае успеха:
        Если show_card == True, то вернуть профиль карточки с новыми координатами
        Вернуть профиль пользователя
    Иначе вернуть пустой словарь
    """
    result = {}
    user_uuid = None
    async with state.proxy() as data:
        user_uuid = data.get('uuid')
    latitude = longitude = None
    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    reply_markup = types.reply_keyboard.ReplyKeyboardRemove()
    if status_sender == 200:
        if not user_uuid:
            user_uuid = response_sender.get('uuid')
    if user_uuid:
        if message.location is not None:
            try:
                latitude = getattr(message.location, 'latitude')
                longitude = getattr(message.location, 'longitude')
            except AttributeError:
                pass
        else:
            # text message, отмена или ввел что-то
            try:
                message_text = message.text
            except AttributeError:
                message_text = ''
            if message_text == Misc.PROMPT_CANCEL_LOCATION:
                await message.reply(
                    'Вы отказались задавать местоположение',
                    reply_markup=reply_markup,
                )
            else:
                message_text = message_text.strip()
                m = re.search(r'([\-\+]?\d+(?:\.\d*)?)\s*\,\s*([\-\+]?\d+(?:\.\d*)?)', message_text)
                if m:
                    try:
                        latitude_ = float(m.group(1))
                        longitude_ = float(m.group(2))
                        if -90 <= latitude_ <= 90 and -180 <= longitude_ <= 180:
                            latitude = latitude_
                            longitude = longitude_
                        else:
                            raise ValueError
                    except ValueError:
                        pass
                if latitude and longitude:
                    pass
                else:
                    await message.reply((
                            'Надо было:\n'
                            '- или что-то выбрать: <u>%s</u> или <u>%s</u>, из кнопок снизу.\n'
                            '- или вводить координаты <u><i>широта, долгота</i></u>, '
                            'где <i>широта</i> и <i>долгота</i> - числа, возможные для координат\n'
                            '<b>Повторите сначала!</b>'
                        )
                        % (Misc.PROMPT_LOCATION, Misc.PROMPT_CANCEL_LOCATION,),
                        reply_markup=reply_markup
                    )
        if latitude and longitude:
            status, response = await Misc.put_user_properties(
                uuid=user_uuid,
                latitude = latitude,
                longitude = longitude,
            )
            if status == 200:
                result = response
                if show_card:
                    await Misc.show_cards(
                        [response],
                        message,
                        bot,
                        response_from=response_sender,
                    )
                    await message.reply('Координаты записаны', reply_markup=reply_markup)
            else:
                await message.reply('Ошибка записи координат', reply_markup=reply_markup)
    else:
        # ошибка получения user_uuid
        await message.reply(
            Misc.MSG_ERROR_API,
            reply_markup=reply_markup
        )
    return result


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=['location', ContentType.TEXT],
    state=FSMtrip.geo,
)
async def location_trip(message: types.Message, state: FSMContext):
    """
    Записать местоположение пользователя в процессе сбора данных для тура
    """
    profile = await put_location(message, state, show_card=False)
    if profile:
        await prompt_trip_conditions(message, state, profile)
    else:
        await state.finish()


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=['location', ContentType.TEXT],
    state=FSMgeo.geo,
)
async def location(message: types.Message, state: FSMContext):
    """
    Записать местоположение пользователя телеграма или uuid в состоянии
    """
    await put_location(message, state, show_card=True)
    await state.finish()


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('getowned', 'listown',),
    state=None,
)
async def echo_getowned_to_bot(message: types.Message, state: FSMContext):
    tg_user_sender = message.from_user
    status, response_from = await Misc.post_tg_user(tg_user_sender)
    if status == 200:
        try:
            status, a_response_to = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=dict(uuid_owner=response_from['uuid']),
            )
            logging.debug('get_tg_user_sender_owned data in api, status: %s' % status)
            logging.debug('get_tg_user_sender_owned data in api, response: %s' % a_response_to)
        except:
            return

        if a_response_to:
            bot_data = await bot.get_me()
            await Misc.show_deeplinks(a_response_to, message, bot_data)
        else:
            await message.reply('У вас нет запрошенных данных')
        if response_from.get('created'):
            await Misc.update_user_photo(bot, tg_user_sender, response_from)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['graph',],
    state=None,
)
async def echo_graph_to_bot(message: types.Message, state: FSMContext):
    await message.reply(
        Misc.get_html_a(settings.GENESIS_HOST + '/?all=on', 'Все родственные связи'),
        disable_web_page_preview=True,
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['trusts',],
    state=None,
)
async def echo_trusts_to_bot(message: types.Message, state: FSMContext):
    await message.reply(
        Misc.get_html_a(settings.FRONTEND_HOST + '/?q=2500&f=0', 'Все связи доверий'),
        disable_web_page_preview=True,
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['rules',],
    state=None,
)
async def echo_rules_to_bot(message: types.Message, state: FSMContext):
    await message.reply(await Misc.rules_text(), disable_web_page_preview=True)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['help',],
    state=None,
)
async def echo_help_to_bot(message: types.Message, state: FSMContext):
    await message.reply(await Misc.help_text(), disable_web_page_preview=True)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['stat',],
    state=None,
)
async def echo_stat_to_bot(message: types.Message, state: FSMContext):
    status, response = await Misc.api_request(
        path='/api/bot/stat',
        method='get',
    )
    if status == 200 and response:
        reply = (
            '<b>Статистика</b>\n'
            '\n'
            'Пользователи: %(active)s\n'
            'Стартовали бот: %(did_bot_start)s\n'
            'Указали местоположение: %(with_geodata)s\n'
            'Cозданные профили: %(owned)s\n'
            'Всего профилей: %(all)s\n'
        ) % {
            'active': response['active'],
            'owned': response['owned'],
            'all': response['active'] + response['owned'],
            'did_bot_start': response['did_bot_start'],
            'with_geodata': response['with_geodata'],
        }
    else:
        reply = 'Произошла ошибка'
    await message.reply(reply)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['feedback',],
    state=None,
)
async def echo_feedback(message: types.Message, state: FSMContext):
    """
    Отправка сообщения администраторам (разработчикам)
    """

    if not settings.BOT_ADMINS:
        await message.reply('Не указаны администраторы системы',)
        return
    params_admins = dict(tg_uids=','.join(map(str, settings.BOT_ADMINS)))
    logging.debug('get_admins, params: %s' % params_admins)
    status_admins, response_admins = await Misc.get_admins()
    if not (status_admins == 200 and response_admins):
        await message.reply('Не найдены администраторы системы',)
        return
    status_sender, profile_sender = await Misc.post_tg_user(message.from_user)
    if not (status_sender == 200 and profile_sender):
        return

    await FSMfeedback.ask.set()
    state = dp.current_state()
    async with state.proxy() as data:
        data['uuid'] = profile_sender['uuid']
    await message.reply(
        'Напишите или перешлите сообщение для разработчиков',
        reply_markup=Misc.reply_markup_cancel_row(),
        disable_web_page_preview=True,
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMfeedback.ask,
)
async def got_message_to_send_to_admins(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        # Надо проверить, тот ли человек пишет админам
        if data.get('uuid'):
            status_from, profile_from = await Misc.get_user_by_uuid(data['uuid'])
            if status_from == 200 and profile_from:
                status_sender, profile_sender = await Misc.post_tg_user(message.from_user)
                if status_from == 200 and profile_from and profile_sender['uuid'] == profile_from['uuid']:
                    status_admins, response_admins = await Misc.get_admins()
                    if not (status_admins == 200 and response_admins):
                        # fool-proof
                        await Misc.state_finish(state)
                        await message.reply('Не найдены администраторы системы',)
                        return
                    bot_data = await bot.get_me()
                    profiles_delivered = []
                    for admin_profile in response_admins:
                        try:
                            await bot.send_message(
                                admin_profile['tg_data']['tg_uid'],
                                text='Вам, <b>разработчику</b>, <b>сообщение</b> от %s' % \
                                    Misc.get_deeplink_with_name(profile_from, bot_data),
                                disable_web_page_preview=True,
                            )
                            await bot.forward_message(
                                admin_profile['tg_data']['tg_uid'],
                                from_chat_id=message.chat.id,
                                message_id=message.message_id,
                            )
                            profiles_delivered.append(admin_profile)
                            payload_log_message = dict(
                                tg_token=settings.TOKEN,
                                from_chat_id=message.chat.id,
                                message_id=message.message_id,
                                user_from_uuid=profile_from['uuid'],
                                user_to_uuid=admin_profile['uuid'],
                                user_to_delivered_uuid=admin_profile['uuid'],
                            )
                            try:
                                status_log, response_log = await Misc.api_request(
                                    path='/api/tg_message',
                                    method='post',
                                    json=payload_log_message,
                                )
                            except:
                                pass
                        except (ChatNotFound, CantInitiateConversation):
                            pass
                    if profiles_delivered:
                        recipients = '\n'.join([Misc.get_deeplink_with_name(r, bot_data) for r in profiles_delivered])
                        await message.reply('Сообщение доставлено разработчикам:\n%s' % recipients)
                    else:
                        await message.reply('Извините, не удалось доставить')
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=None,
)
async def echo_send_to_bot(message: types.Message, state: FSMContext):
    """
    Обработка остальных сообщений в бот
    """

    tg_user_sender = message.from_user
    reply = ''
    if tg_user_sender.is_bot:
        reply = 'Сообщения от ботов пока не обрабатываются'
    elif not message.is_forward() and message.content_type != ContentType.TEXT:
        reply = 'Сюда можно слать текст для поиска, включая @username, или пересылать сообщения любого типа'
    if reply:
        await message.reply(reply)
        return

    reply = ''
    reply_markup = None

    # Кто будет благодарить... или чей профиль показывать, когда некого благодарить...
    #
    user_from_id = None
    response_from = dict()

    tg_user_forwarded = None

    state_ = ''

    # Кого будут благодарить
    # или свой профиль в массиве
    a_response_to = []

    # массив найденных профилей. По ним только deeplinks
    a_found = []

    message_text = getattr(message, 'text', '') and message.text.strip() or ''
    bot_data = await bot.get_me()
    if message.is_forward():
        tg_user_forwarded = message.forward_from
        if not tg_user_forwarded:
            reply = (
                'Автор исходного сообщения '
                '<a href="https://telegram.org/blog/unsend-privacy-emoji#anonymous-forwarding">запретил</a> '
                'идентифицировать себя в пересылаемых сообщениях\n'
            )
        elif tg_user_forwarded.is_bot:
            reply = 'Сообщения, пересланные от ботов, пока не обрабатываются'
        elif tg_user_forwarded.id == tg_user_sender.id:
            state_ = 'forwarded_from_me'
        else:
            state_ = 'forwarded_from_other'
    else:
        if message_text == '/start':
            state_ = 'start'
        elif message_text in ('/ya', '/я'):
            state_ = 'ya'
        else:
            m = re.search(
                r'^\/start\s+setplace$',
                message_text,
                flags=re.I,
            )
            if m:
                state_ = 'start_setplace'
            else:
                m = re.search(
                    r'^\/start\s+([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$',
                    message_text,
                    flags=re.I,
                )
                if m:
                    # /start 293d987f-4ee8-407c-a614-7110cad3552f
                    uuid_to_search = m.group(1).lower()
                    state_ = 'start_uuid'
                else:
                    # https://t.me/doverabot?start=70dce08c-087d-4ae0-8002-1de8dbc04ea5
                    m = re.search(
                        (
                            r'^(?:http[s]?\:\/\/)?t\.me\/%s\?start\='
                            '([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$'
                        ) % re.escape(bot_data['username']),
                        message_text,
                        flags=re.I,
                    )
                    if m:
                        # https://t.me/doverabot?start=70dce08c-087d-4ae0-8002-1de8dbc04ea5
                        uuid_to_search = m.group(1).lower()
                        state_ = 'start_uuid'
                    else:
                        m = re.search(
                            r'^\/start\s+(\w{5,})$',
                            message_text,
                            flags=re.I,
                        )
                        if m:
                            # /start username
                            username_to_search = m.group(1)
                            state_ = 'start_username'
                        else:
                            # https://t.me/doverabot?start=username
                            m = re.search(
                                (
                                    r'^(?:http[s]?\:\/\/)?t\.me\/%s\?start\='
                                    '(\w{5,})$'
                                ) % re.escape(bot_data['username']),
                                message_text,
                                flags=re.I,
                            )
                            if m:
                                # https://t.me/doverabot?start=username
                                username_to_search = m.group(1)
                                state_ = 'start_username'
                            else:
                                if len(message_text) < settings.MIN_LEN_SEARCHED_TEXT:
                                    state_ = 'invalid_message_text'
                                    reply = Misc.invalid_search_text()
                                else:
                                    search_phrase = ''
                                    usernames, text_stripped = Misc.get_text_usernames(message_text)
                                    if text_stripped:
                                        search_phrase = Misc.text_search_phrase(
                                            text_stripped,
                                            MorphAnalyzer,
                                        )
                                        if not search_phrase and not usernames:
                                            state_ = 'invalid_message_text'
                                            reply = Misc.PROMPT_SEARCH_PHRASE_TOO_SHORT

                                    if usernames:
                                        logging.debug('@usernames found in message text\n')
                                        payload_username = dict(tg_username=','.join(usernames),)
                                        status, response = await Misc.api_request(
                                            path='/api/profile',
                                            method='get',
                                            params=payload_username,
                                        )
                                        logging.debug('get by username, status: %s' % status)
                                        logging.debug('get by username, response: %s' % response)
                                        if status == 200 and response:
                                            a_found += response
                                            state_ = 'found_username'
                                        else:
                                            state_ = 'not_found'

                                    if search_phrase:
                                        status, response = await Misc.search_users('query', search_phrase)
                                        if status == 400 and response.get('code') and response['code'] == 'programming_error':
                                            if state_ != 'found_username':
                                                state_ = 'not_found'
                                                reply = 'Ошибка доступа к данных. Получили отказ по такой строке в поиске'
                                        elif status == 200:
                                            if response:
                                                a_found += response
                                                state_ = 'found_in_search'
                                            elif state_ != 'found_username':
                                                state_ = 'not_found'
                                        else:
                                            state_ = 'not_found'
                                            reply = Misc.MSG_ERROR_API

    if state_ == 'not_found' and not reply:
        reply = Misc.PROMPT_NOTHING_FOUND

    if state_:
        status, response_from = await Misc.post_tg_user(tg_user_sender)
        if status == 200:
            response_from.update(tg_username=tg_user_sender.username)
            user_from_id = response_from.get('user_id')
            if state_ in ('ya', 'forwarded_from_me', 'start', ) or \
                state_ in ('start_uuid', 'start_username',) and response_from.get('created'):
                a_response_to += [response_from, ]

    if user_from_id and state_ == 'start_uuid':
        logging.debug('get tg_user_by_start_uuid data in api...')
        try:
            status, response_uuid = await Misc.get_user_by_uuid(uuid=uuid_to_search)
            if status == 200:
                a_response_to += [response_uuid, ]
            else:
                reply = Misc.MSG_USER_NOT_FOUND
        except:
            pass

    if user_from_id and state_ == 'start_username':
        logging.debug('get tg_user_by_start_username data in api...')
        try:
            status, response_tg_username = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=dict(tg_username=username_to_search),
            )
            logging.debug('get_user_profile by username, status: %s' % status)
            logging.debug('get_user_profile by username, response: %s' % response_tg_username)
            if status == 200 and response_tg_username:
                a_response_to += response_tg_username
            else:
                reply = Misc.MSG_USER_NOT_FOUND
        except:
            pass

    if user_from_id and state_ == 'forwarded_from_other':
        status, response_to = await Misc.post_tg_user(tg_user_forwarded)
        if status == 200:
            response_to.update(tg_username=tg_user_forwarded.username)
            a_response_to = [response_to, ]

    if user_from_id and state_ in ('forwarded_from_other', 'forwarded_from_me'):
        usernames, text_stripped = Misc.get_text_usernames(message_text)
        if usernames:
            logging.debug('@usernames found in message text\n')
            payload_username = dict(tg_username=','.join(usernames),)
            status, response = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=payload_username,
            )
            logging.debug('get by username, status: %s' % status)
            logging.debug('get by username, response: %s' % response)
            if status == 200 and response:
                a_found += response


    if state_ and state_ not in ('not_found', 'invalid_message_text', 'start_setplace') and user_from_id and a_response_to:
        if state_ == 'start':
            await message.reply(await Misc.rules_text(), disable_web_page_preview=True)
            if a_response_to and not a_response_to[0].get('photo'):
                status_photo, response_photo = await Misc.update_user_photo(bot, tg_user_sender, response_from)
                if response_photo:
                    response_from = response_photo
                    a_response_to[0] = response_photo
        message_to_forward_id = state_ == 'forwarded_from_other' and message.message_id or ''
        await Misc.show_cards(
            a_response_to,
            message,
            bot,
            response_from=response_from,
            message_to_forward_id=message_to_forward_id,
        )

    elif reply:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if state_ != 'start_setplace':
        await Misc.show_deeplinks(a_found, message, bot_data)

    if user_from_id and response_from.get('created') and state_ != 'start':
        await Misc.update_user_photo(bot, tg_user_sender, response_from)
    if user_from_id and state_ == 'start_setplace':
        await geo(message, state_to_set=FSMgeo.geo)
    if state_ == 'forwarded_from_other' and a_response_to and a_response_to[0].get('created'):
        await Misc.update_user_photo(bot, tg_user_forwarded, response_to)


@dp.message_handler(
    ChatTypeFilter(chat_type=(types.ChatType.GROUP, types.ChatType.SUPERGROUP)),
    commands=('get_group_id',),
    state=None,
)
async def get_group_id(message: types.Message, state: FSMContext):
    if not message.from_user.is_bot:
        chat = message.chat
        status, response = await TgGroup.post(chat.id, chat.title, chat.type)
        try:
            await message.delete()
        except:
            pass
        reply =  (
            'Вы запросили ИД группы <b>%s</b>\n'
            'Отвечаю:\n\n'
            'ИД: %s\n'
            'Тип: %s\n'
        ) % (chat.title, chat.id, chat.type)
        try:
            if status == 200:
                await bot.send_message(
                    message.from_user.id, reply + (
                        'Группа только что создана Вами в данных\n' if response['created'] else 'Группа существовала в данных до Вашего запроса\n'
                ))
            else:
                await bot.send_message(
                    message.from_user.id, reply + 'ОШИБКА создания, если не существует, группы в данных\n'
                )
        except (ChatNotFound, CantInitiateConversation):
            pass


async def do_chat_join(
    callback_query,
    tg_inviter_id,
    tg_subscriber,
    chat_id,
):
    status, response_subscriber = await Misc.post_tg_user(tg_subscriber)
    if status != 200:
        return
    if tg_inviter_id:
        status, response_inviter = await Misc.get_user_by_tg_uid(tg_inviter_id)
        if status != 200:
            return
    tg_subscriber_id = tg_subscriber.id
    status, response = await TgGroupMember.add(
        group_chat_id=chat_id,
        group_title='',
        group_type='',
        user_tg_uid=tg_subscriber_id,
    )
    if status != 200:
        return
    status, response = await TgGroup.get(chat_id=chat_id)
    if status != 200:
        return
    is_channel = response['type'] == types.ChatType.CHANNEL
    in_chat = 'в канале' if is_channel else 'в группе'
    to_chat = 'к каналу' if is_channel else 'к группе'
    to_to_chat = 'в канал' if is_channel else 'в группу'
    of_chat = 'канала' if is_channel else 'группы'
    try:
        await bot.approve_chat_join_request(
                chat_id,
                tg_subscriber_id
        )
    except BadRequest as excpt:
        msg = 'Наверное, вы уже ' + in_chat
        try:
            if excpt.args[0] == 'User_already_participant':
                msg = 'Вы уже ' + in_chat
        except:
            pass
        if callback_query:
            await callback_query.message.reply(msg, disable_web_page_preview=True,)
        else:
            await bot.send_message(
                chat_id=tg_subscriber.id,
                text=msg,
                disable_web_page_preview=True
            )
        return

    tc_inviter = 0
    if tg_inviter_id:
        pass
        ## Сразу доверие c благодарностью от входящего в канал/группу к владельцу канала/группы
        ##
        #post_op = dict(
            #tg_token=settings.TOKEN,
            #operation_type_id=OperationType.TRUST_AND_THANK,
            #tg_user_id_from=tg_subscriber_id,
            #user_uuid_to=response_inviter['uuid'],
        #)
        #logging.debug('post operation (chat subscriber thanks inviter), payload: %s' % post_op)
        #status_op, response_op = await Misc.api_request(
            #path='/api/addoperation',
            #method='post',
            #data=post_op,
        #)
        #logging.debug('post operation (chat subscriber thanks inviter), status: %s' % status_op)
        #logging.debug('post operation (chat subscriber thanks inviter), response: %s' % response_op)
        #if status_op == 200:
            #tc_inviter = response_op['profile_to']['trust_count']

    bot_data = await bot.get_me()
    dl_subscriber = Misc.get_deeplink_with_name(response_subscriber, bot_data)
    dl_inviter = Misc.get_deeplink_with_name(response_inviter, bot_data) if tg_inviter_id else ''
    msg_dict = dict(
        dl_subscriber=dl_subscriber,
        dl_inviter=dl_inviter,
        to_chat=to_chat,
        of_chat=of_chat,
        tc_inviter=tc_inviter,
        tc_subscriber=response_subscriber['trust_count'],
    )
    if is_channel:
        #if tg_inviter_id and status_op == 200:
            #reply = (
                #'%(dl_subscriber)s (%(tc_subscriber)s) подключен(а) %(to_chat)s '
                #'и доверяет владельцу %(of_chat)s: %(dl_inviter)s (%(tc_inviter)s)'
            #) % msg_dict
        #else:
            #reply = '%(dl_subscriber)s (%(tc_subscriber)s) подключен(а) %(to_chat)s' % msg_dict
        reply = '%(dl_subscriber)s (%(tc_subscriber)s) подключен(а)' % msg_dict
        await bot.send_message(
            chat_id,
            reply,
            disable_notification=True,
            disable_web_page_preview=True,
        )
    msg = 'Добро пожаловать %s' % to_to_chat
    if callback_query:
        await callback_query.message.reply(msg, disable_web_page_preview=True,)
    else:
        await bot.send_message(
            chat_id=tg_subscriber.id,
            text=msg,
            disable_web_page_preview=True
        )
    await Misc.put_user_properties(
        uuid=response_subscriber['uuid'],
        did_bot_start='1',
    )
    if response_subscriber.get('created'):
        await Misc.update_user_photo(bot, tg_subscriber, response_subscriber)


@dp.chat_join_request_handler()
async def echo_join_chat_request(message: types.Message):
    """
    Пользователь присоединяется к каналу/группе по ссылке- приглашению

    Работает только ссылка, требующая одобрения.
    Бот, он всегда администратор канала/группы, одобрит.
    Но до этого:
        Нового участника надо завести в базе, если его там нет
        В канал/группу отправится мини- карточка нового участника
    """
    tg_subscriber = message.from_user
    tg_inviter = message.invite_link.creator if message.invite_link else None
    if tg_inviter:
        status, response_inviter = await Misc.post_tg_user(tg_inviter)
        if status != 200:
            return
        # Владельца канала/группы сразу в канал/группу. Вдруг его там нет
        #
        await TgGroupMember.add(
            group_chat_id=message.chat.id,
            group_title=message.chat.title,
            group_type=message.chat.type,
            user_tg_uid=tg_inviter.id,
        )
    if settings.TRIP_DATA and settings.TRIP_DATA.get('chat_id') == message.chat.id:
        text_agreement = settings.TRIP_DATA['text_agreement']

        dict_callback = dict(
            keyboard_type=KeyboardType.CHAT_JOIN_ACCEPT,
            tg_subscriber_id=tg_subscriber.id,
            tg_inviter_id=tg_inviter.id if tg_inviter else '',
            chat_id=message.chat.id,
            sep=KeyboardType.SEP,
        )
        callback_data_template = (
            '%(keyboard_type)s%(sep)s'
            '%(tg_subscriber_id)s%(sep)s'
            '%(tg_inviter_id)s%(sep)s'
            '%(chat_id)s%(sep)s'
        )
        inline_btn_chat_join = InlineKeyboardButton(
            text='Согласие',
            callback_data=callback_data_template % dict_callback,
        )
        dict_callback.update(keyboard_type=KeyboardType.CHAT_JOIN_REFUSE)
        inline_btn_chat_refuse = InlineKeyboardButton(
            text='Отказ',
            callback_data=callback_data_template % dict_callback,
        )
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_chat_join, inline_btn_chat_refuse)
        await bot.send_message(
            chat_id=tg_subscriber.id,
            text=text_agreement,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    else:
        await do_chat_join(
            callback_query=None,
            tg_inviter_id=tg_inviter and tg_inviter.id or None,
            tg_subscriber=tg_subscriber,
            chat_id=message.chat.id,
        )

    if tg_inviter and response_inviter.get('created'):
        await Misc.update_user_photo(bot, tg_inviter, response_inviter)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CHAT_JOIN_ACCEPT,
        KeyboardType.SEP,
        # tg_subscriber_id          # 1
        # tg_inviter_id             # 2, может быть ''
        # chat_id                   # 3
    ), c.data
    ), state=None,
    )
async def process_callback_chat_join(callback_query: types.CallbackQuery, state: FSMContext):
    # Это придет только в канал с chat_id = settings.TRIP_DATA['chat_id']
    if callback_query.message:
        tg_subscriber = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        try:
            tg_subscriber_id = int(code[1])
            if not (tg_subscriber_id and tg_subscriber.id == tg_subscriber_id):
                return
            try:
                tg_inviter_id = int(code[2])
            except (IndexError, ValueError, TypeError,):
                tg_inviter_id = None
            chat_id = int(code[3])
        except (IndexError, ValueError, TypeError,):
            return

        await do_chat_join(
            callback_query=callback_query,
            tg_inviter_id=tg_inviter_id,
            tg_subscriber=tg_subscriber,
            chat_id=chat_id,
        )


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CHAT_JOIN_REFUSE,
        KeyboardType.SEP,
        # tg_subscriber_id          # 1
        # tg_inviter_id             # 2
        # chat_id                # 3
    ), c.data
    ), state=None,
    )
async def process_callback_chat_join_refuse(callback_query: types.CallbackQuery, state: FSMContext):
    return


@dp.my_chat_member_handler(
    ChatTypeFilter(chat_type=(types.ChatType.CHANNEL,)),
)
async def echo_my_chat_member_for_bot(chat_member: types.ChatMemberUpdated):
    """
    Для формирования ссылки на доверия среди участников канала

    Реакция на подключение к каналу бота
    """
    new_chat_member = chat_member.new_chat_member
    bot_ = new_chat_member.user
    tg_user_from = chat_member.from_user
    if tg_user_from and not tg_user_from.is_bot:
        status, user_from = await Misc.post_tg_user(tg_user_from)
        if status == 200:
            await TgGroupMember.add(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type, tg_user_from.id)
        else:
            return
    else:
        status, response = await TgGroup.post(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type)
        if status != 200:
            return
    if bot_.is_bot and new_chat_member.status == 'administrator' and bot_.first_name:
        reply_markup = InlineKeyboardMarkup()
        inline_btn_trusts = InlineKeyboardButton(
            'Доверия',
            url='%(group_host)s/?tg_group_chat_id=%(chat_id)s' % dict(
                group_host=settings.GROUP_HOST,
                chat_id=chat_member.chat.id,
        ))
        reply_markup.row(
            inline_btn_trusts,
        )
        await bot.send_message(
            chat_id=chat_member.chat.id,
            text= \
                Misc.get_html_a(
                    href='%s/?chat_id=%s' % (settings.MAP_HOST, chat_member.chat.id),
                    text='Карта',
                ) + ' \n' + \
                Misc.get_html_a(
                    href='%s/?chat_id=%s&depth=10&q=50&f=0' % (
                        settings.GENESIS_HOST,
                        chat_member.chat.id,
                    ),
                    text='Род'
                ),
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=(types.ChatType.GROUP, types.ChatType.SUPERGROUP)),
    content_types=ContentType.all(),
    state=None,
)
async def echo_send_to_group(message: types.Message, state: FSMContext):
    """
    Обработка сообщений в группу
    """

    tg_user_sender = message.from_user

    # tg_user_sender.id == 777000:
    #   Если к группе привязан канал, то сообщения идут от этого пользователя
    #
    if tg_user_sender.id == 777000:
        return

    if message.content_type in(
            ContentType.NEW_CHAT_PHOTO,
            ContentType.NEW_CHAT_TITLE,
            ContentType.DELETE_CHAT_PHOTO,
            ContentType.PINNED_MESSAGE,
       ):
        return

    global last_user_in_group

    # Данные из телеграма пользователя /пользователей/, данные которых надо выводить при поступлении
    # сообщения в группу
    #
    a_users_in = []

    # Данные из базы пользователя /пользователей/, данные которых надо выводить при поступлении
    # сообщения в группу
    #
    a_users_out = []

    a_users_in = [ tg_user_sender ]
    try:
        tg_user_left = message.left_chat_member
    except  (TypeError, ):
        tg_user_left = None
    if tg_user_left:
        a_users_in = [ tg_user_left ]
    try:
        tg_users_new = message.new_chat_members
    except (TypeError, ):
        tg_users_new = []
    if tg_users_new:
        a_users_in = tg_users_new

    if not tg_users_new and not tg_user_left and tg_user_sender.is_bot:
        # tg_user_sender.is_bot:
        #   анонимное послание в группу или от имени канала
        # Но делаем исключение, когда анонимный владелей
        return

    bot_data = await bot.get_me()
    if tg_user_left or tg_users_new:
        # Если сообщение о новом, убывшем пользователе, то любое следующее
        # сообщение будет как бы от нового пользователя
        is_previous_his = False
        last_user_in_group[message.chat.id] = None
    else:
        previous_user_in_group = last_user_in_group.get(message.chat.id)
        is_previous_his = True
        if previous_user_in_group != message.from_user.id:
            last_user_in_group[message.chat.id] = message.from_user.id
            is_previous_his = False

    for user_in in a_users_in:
        reply_markup = None
        status, response_from = await Misc.post_tg_user(user_in)
        if status != 200:
            a_users_out.append({})
            continue
        a_users_out.append(response_from)

        is_this_bot = bot_data.id == user_in.id
        if tg_user_left:
            # Ушел пользователь, убираем его из группы
            await TgGroupMember.remove(
                group_chat_id=message.chat.id,
                group_title=message.chat.title,
                group_type=message.chat.type,
                user_tg_uid=user_in.id
            )
        elif not is_this_bot:
            # Добавить в группу в апи, если его там нет и если это не бот-обработчик
            await TgGroupMember.add(
                group_chat_id=message.chat.id,
                group_title=message.chat.title,
                group_type=message.chat.type,
                user_tg_uid=user_in.id
            )

        if tg_users_new and \
           tg_user_sender.id != user_in.id:
            # Сразу доверие c благодарностью добавляемому пользователю
            post_op = dict(
                tg_token=settings.TOKEN,
                operation_type_id=OperationType.TRUST_AND_THANK,
                tg_user_id_from=tg_user_sender.id,
                user_uuid_to=response_from['uuid'],
            )
            logging.debug('post operation, payload: %s' % post_op)
            status, response = await Misc.api_request(
                path='/api/addoperation',
                method='post',
                data=post_op,
            )
            logging.debug('post operation, status: %s' % status)
            logging.debug('post operation, response: %s' % response)
            if status == 200:
                # Обновить, ибо уже на доверие больше у него может быть
                response_from['trust_count'] = response['profile_to']['trust_count']
            #else:
                #   status == 400:
                #   response == {'message': 'Не найден пользователь с этим ид телеграма'}
                #       Возможно, что это не пользователь-администратор, а
                #       некий @GroupAnonymousBot добавляет юзера. Такое возможно
                #       с группами, подключенными к каналу


        buttons = []
        if not is_previous_his and not tg_user_left:
            if is_this_bot:
                # ЭТОТ бот подключился. Достаточно его full name и ссылку на доверия в группе
                #
                reply = Misc.get_html_a(
                    href='%s/?chat_id=%s' % (settings.MAP_HOST, message.chat.id),
                    text='Карта',
                ) + ' ...\n' + \
                Misc.get_html_a(
                    href='%s/?chat_id=%s&depth=10&q=20&f=0' % (
                        settings.GENESIS_HOST,
                        message.chat.id,
                    ),
                    text='Род',
                )
                inline_btn_trusts = InlineKeyboardButton(
                    'Доверия',
                    url='%(group_host)s/?tg_group_chat_id=%(chat_id)s' % dict(
                        group_host=settings.GROUP_HOST,
                        chat_id=message.chat.id,
                ))
                buttons = [inline_btn_trusts]
            else:
                reply = '<b>%(deeplink_with_name)s</b> (%(trust_count)s)' % dict(
                    deeplink_with_name=Misc.get_deeplink_with_name(response_from, bot_data),
                    trust_count=response_from['trust_count'],
                )
                inline_btn_thank = InlineKeyboardButton(
                    '+Доверие',
                    callback_data=OperationType.CALLBACK_DATA_TEMPLATE % dict(
                    operation=OperationType.TRUST_AND_THANK,
                    keyboard_type=KeyboardType.TRUST_THANK,
                    sep=KeyboardType.SEP,
                    user_to_uuid_stripped=Misc.uuid_strip(response_from['uuid']),
                    message_to_forward_id='',
               ))
                buttons = [inline_btn_thank]
            if buttons:
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(*buttons)
            await message.answer(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    for i, response_from in enumerate(a_users_out):
        if response_from.get('created'):
            await Misc.update_user_photo(bot, a_users_in[i], response_from)


async def check_user_delete_undelete(callback_query):
    """
    Проверить возможность удаления, обезличивания или восстановления после этого

    Делается два раза, линий раз не помешает
    Возвращает профили:
        owner: Кто удаляет (если собственного) или обезличивает (сам себя), или восстанавливает (себя)
        user: его удаляем или обезличиваем, или восстанавливаем
    """
    code = callback_query.data.split(KeyboardType.SEP)
    try:
        uuid = code[1]
        if not uuid:
            raise ValueError
        owner = await Misc.check_owner(owner_tg_user=callback_query.from_user, uuid=uuid)
        if not owner:
            raise ValueError
        owner_id = code[2]
        if owner_id != str(owner['user_id']):
            raise ValueError
        user = owner['response_uuid']
    except (IndexError, ValueError,):
        user, owner = None, None
    return user, owner


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.DELETE_USER,
        KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_delete_user(callback_query: types.CallbackQuery, state: FSMContext):
    user, owner = await check_user_delete_undelete(callback_query)
    #   owner:  Кто удаляет (если собственного) или обезличивает (сам себя)
    #   user:   его удаляем или обезличиваем
    if not user or not (user['is_active'] or user['owner_id']):
        return
    if user['user_id'] == owner['user_id']:
        # Себя обезличиваем
        prompt = (
            '<b>%(name)s</b>\n'
            '\n'
            'Вы собираетесь <u>обезличить</u> себя в системе.\n'
            'Будут удалены Ваши данные (ФИО, фото, место и т.д), а также связи с родственниками!\n'
            '\n'
            'Если подтверждаете, то нажмите <u>Продолжить</u>. Иначе <u>Отмена</u>\n'
        ) % dict(name = owner['first_name'])
    else:
        bot_data = await bot.get_me()
        prompt = (
            'Будет удалён %(name)s!\n'
            '\n'
            'Если подтверждаете удаление, нажмите <u>Продолжить</u>. Иначе <u>Отмена</u>\n'
        ) % dict(name = Misc.get_deeplink_with_name(user, bot_data, with_lifetime_years=True,))
    callback_data = (Misc.CALLBACK_DATA_UUID_TEMPLATE + '%(owner_id)s%(sep)s') % dict(
        keyboard_type=KeyboardType.DELETE_USER_CONFIRMED,
        uuid=user['uuid'],
        sep=KeyboardType.SEP,
        owner_id=owner['user_id']
    )
    inline_btn_go = InlineKeyboardButton(
        'Продолжить',
        callback_data=callback_data,
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_btn_go, Misc.inline_button_cancel())
    await FSMdelete.ask.set()
    await callback_query.message.reply(prompt, reply_markup=reply_markup)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.DELETE_USER_CONFIRMED,
        KeyboardType.SEP,
    ), c.data
    ), state=FSMdelete.ask,
    )
async def process_callback_delete_user_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    user, owner = await check_user_delete_undelete(callback_query)
    #   owner:  Кто удаляет (если собственного) или обезличивает (сам себя)
    #   user:   его удаляем или обезличиваем

    if not user or not (user['is_active'] or user['owner_id']):
        await Misc.state_finish(state)
        return

    if user['user_id'] == owner['user_id']:
        msg_debug = 'depersonalize user, '
        msg_deleted = 'Теперь Вы обезличены'
    else:
        msg_debug = 'delete owned user, '
        msg_deleted = 'Профиль <u>%s</u> удалён' % user['first_name']

    payload = dict(tg_token=settings.TOKEN, uuid=user['uuid'], owner_id=owner['user_id'])
    logging.debug(msg_debug + 'payload: %s' % payload)
    status, response = await Misc.api_request(
        path='/api/profile',
        method='delete',
        data=payload,
    )
    logging.debug(msg_debug + 'status: %s' % status)
    logging.debug(msg_debug + 'response: %s' % response)
    if status == 400:
        await callback_query.message.reply('Ошибка: %s' % response['message'])
    elif status != 200:
        await callback_query.message.reply('Неизвестная ошибка')
    else:
        await callback_query.message.reply(msg_deleted)
        if user['user_id'] == owner['user_id']:
            await Misc.show_cards(
                [response],
                callback_query.message,
                bot,
                response_from=owner,
                tg_user_from=callback_query.from_user
            )
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.UNDELETE_USER,
        KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_undelete_user(callback_query: types.CallbackQuery, state: FSMContext):
    user, owner = await check_user_delete_undelete(callback_query)
    if not user or user['user_id'] != owner['user_id'] or user['is_active'] or user['owner_id']:
        return
    prompt = (
        '<b>%(name)s</b>\n'
        '\n'
        'Вы собираетесь <u>восстановить</u> себя и свои данные в системе.\n'
        '\n'
        'Если подтверждаете, то нажмите <u>Продолжить</u>. Иначе <u>Отмена</u>\n'
    ) % dict(name = owner['first_name'])
    callback_data = (Misc.CALLBACK_DATA_UUID_TEMPLATE + '%(owner_id)s%(sep)s') % dict(
        keyboard_type=KeyboardType.UNDELETE_USER_CONFIRMED,
        uuid=user['uuid'],
        sep=KeyboardType.SEP,
        owner_id=owner['user_id']
    )
    inline_btn_go = InlineKeyboardButton(
        'Продолжить',
        callback_data=callback_data,
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_btn_go, Misc.inline_button_cancel())
    await FSMundelete.ask.set()
    await callback_query.message.reply(prompt, reply_markup=reply_markup)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.UNDELETE_USER_CONFIRMED,
        KeyboardType.SEP,
    ), c.data
    ), state=FSMundelete.ask,
    )
async def process_callback_undelete_user_confirmed(callback_query: types.CallbackQuery, state: FSMContext):
    user, owner = await check_user_delete_undelete(callback_query)
    #   owner:  Кто восстанавливает себя
    #   user:   Он же должен быть
    if not user or user['user_id'] != owner['user_id'] or user['is_active'] or user['owner_id']:
        await Misc.state_finish(state)
        return

    logging.debug('un-depersonalize user')
    status, response = await Misc.post_tg_user(callback_query.from_user, activate=True)
    payload = dict(tg_token=settings.TOKEN, uuid=user['uuid'], owner_id=owner['user_id'])
    if status == 400:
        await callback_query.message.reply('Ошибка: %s' % response['message'])
    elif status != 200:
        await callback_query.message.reply('Неизвестная ошибка')
    else:
        await callback_query.message.reply("Теперь Вы восстановлены в системе.\n\nГружу Ваше фото, если оно есть, из Telegram'а...")
        status_photo, response_photo = await Misc.update_user_photo(bot, callback_query.from_user, response)
        if status_photo == 200:
            response = response_photo
        await Misc.show_cards(
            [response],
            callback_query.message,
            bot,
            response_from=owner,
            tg_user_from=callback_query.from_user
        )
    await Misc.state_finish(state)


@dp.inline_handler()
async def inline_handler(query: types.InlineQuery):
    if query.query:
        search_phrase = Misc.text_search_phrase(query.query, MorphAnalyzer)
        if search_phrase:
            status, a_found = await Misc.search_users(
                'query', search_phrase,
                thumb_size=64,
                from_=0,
                number=50,
            )
            if status == 200 and a_found:
                articles = []
                bot_data = await bot.get_me()
                for profile in a_found:
                    thumb_url = profile['thumb_url']
                    # Ссылки от телеграма ведут на редирект и посему не показываются.
                    # Чтоб вместо них блы квадрат с первой буквы имени:
                    if thumb_url.lower().startswith('https://t.me/'):
                        thumb_url = ''
                    article = types.InlineQueryResultArticle(
                        id=hashlib.md5(profile['uuid'].encode()).hexdigest(),
                        title=profile['first_name'],
                        description=profile['ability'],
                        url = Misc.get_deeplink(profile, bot_data, https=True),
                        thumb_url=thumb_url,
                        hide_url=True,
                        input_message_content=types.InputTextMessageContent(
                            message_text=Misc.get_deeplink_with_name(profile, bot_data),
                            parse_mode='html',
                        ))
                    articles.append(article)
                await query.answer(
                    articles,
                    cache_time=1 if settings.DEBUG else 300,
                    is_personal=True,
                )


# ---------------------------------

if __name__ == '__main__':
    if settings.START_MODE == 'poll':
        start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
        )

    elif settings.START_MODE == 'webhook':
        start_webhook(
            dispatcher=dp,
            webhook_path=settings.WEBHOOK_PATH,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            skip_updates=True,
            host=settings.WEBAPP_HOST,
            port=settings.WEBAPP_PORT,
    )
    else:
        raise Exception('Unknown START_MODE in settings')
