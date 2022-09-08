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

class FSMchild(StatesGroup):
    parent_gender = State()
    ask = State()
    new = State()

class FSMother(StatesGroup):
    gender = State()
    dob = State()
    dod = State()

class FSMsendMessage(StatesGroup):
    ask = State()

class FSMchangeOwner(StatesGroup):
    ask = State()
    confirm = State()

class FSMkey(StatesGroup):
    ask = State()

class FSMquery(StatesGroup):
    ask = State()

class FSMgeo(StatesGroup):
    geo = State()

class FSMtrip(StatesGroup):
    geo = State()

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
    owner = await Misc.check_owner(owner_tg_user=message.from_user, uuid=user_uuid_from)
    if not owner or not owner.get('user_id'):
        await Misc.state_finish(state)
        return
    owner_id = owner['user_id']

    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=OperationType.SET_FATHER if is_father else OperationType.SET_MOTHER,
        user_uuid_from=user_uuid_from,
        user_uuid_to=user_uuid_to,
        owner_id=owner_id,
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
            bot_data = await bot.get_me()
            await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                    iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data),
                    iof_to = Misc.get_deeplink_with_name(response['profile_to'], bot_data),
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
    owner_id = owner['user_id']

    post_data = dict(
        tg_token=settings.TOKEN,
        first_name = first_name_to,
        link_relation='new_is_father' if is_father else 'new_is_mother',
        link_uuid=user_uuid_from,
        owner_id=owner_id,
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
            bot_data = await bot.get_me()
            await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                    iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data),
                    iof_to = Misc.get_deeplink_with_name(response, bot_data),
                    papa_or_mama='папа' if is_father else 'мама',
                    _a_='' if is_father else 'а',
                    disable_web_page_preview=True,
            ))
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
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            return
        is_father = code[0] == str(KeyboardType.NEW_FATHER)
        response_uuid = response_sender['response_uuid']
        prompt_new_papa_mama = Misc.PROMPT_NEW_PAPA_MAMA % dict(
            name=response_uuid['first_name'],
            papoy_or_mamoy='папой' if is_father else 'мамой',
            fio_pama_mama='Иван Иванович Иванов'if is_father else 'Марья Ивановна Иванова',
            on_a='Он' if is_father else 'Она',
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
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['is_father'] = is_father
        his_her = Misc.his_her(response_uuid)
        prompt_papa_mama = Misc.PROMPT_PAPA_MAMA % dict(
            bot_data_username=bot_data['username'],
            name=response_uuid['first_name'],
            his_her=his_her,
            papy_or_mamy='папы' if is_father else 'мамы',
            novy_novaya='Новый' if is_father else 'Новая',
            papoy_or_mamoy='папой' if is_father else 'мамой',
        )
        callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.NEW_FATHER if is_father else KeyboardType.NEW_MOTHER,
            uuid=uuid,
            sep=KeyboardType.SEP,
        )
        inline_btn_new_papa_mama = InlineKeyboardButton(
            'Новый' if is_father else 'Новая',
            callback_data=callback_data,
        )
        inline_button_cancel = Misc.inline_button_cancel()
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_new_papa_mama, inline_button_cancel)
        await FSMpapaMama.ask.set()
        await callback_query.message.reply(
            prompt_papa_mama,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )

async def ask_child(message, state, data):
    bot_data = await bot.get_me()
    prompt_child = Misc.PROMPT_CHILD % dict(
        bot_data_username=bot_data['username'],
        name=data['name'],
        his_her='его' if data['parent_gender'] == 'm' else 'её'
    )
    callback_data = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
        keyboard_type=KeyboardType.NEW_CHILD,
        uuid=data['uuid'],
        sep=KeyboardType.SEP,
    )
    inline_btn_new_child = InlineKeyboardButton(
        'Новый ребёнок',
        callback_data=callback_data,
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_btn_new_child, Misc.inline_button_cancel())
    await FSMchild.ask.set()
    await message.reply(
        prompt_child,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )

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
            response_sender = await Misc.check_owner(owner_tg_user=message.from_user, uuid=data['uuid'])
            if response_sender:
                if not response_sender['response_uuid']['gender']:
                    await Misc.put_user_properties(
                      uuid=data['uuid'],
                      gender=data['parent_gender'],
                    )
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
                        bot_data = await bot.get_me()
                        await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                                iof_from = Misc.get_deeplink_with_name(response['profile_from'], bot_data),
                                iof_to = Misc.get_deeplink_with_name(response['profile_to'], bot_data),
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
                first_name = Misc.strip_text(message.text)
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
                        bot_data = await bot.get_me()
                        is_father = data['parent_gender'] == 'm'
                        await message.reply(Misc.PROMPT_PAPA_MAMA_SET % dict(
                                iof_from = Misc.get_deeplink_with_name(response_child, bot_data),
                                iof_to = Misc.get_deeplink_with_name(response_parent, bot_data),
                                papa_or_mama='папа' if is_father else 'мама',
                                _a_='' if is_father else 'а',
                                disable_web_page_preview=True,
                        ))
                    else:
                        await message.reply('Ребёнок внесен в данные')
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.CHILD,
        KeyboardType.SEP,
        # uuid родителя           # 1
        # KeyboardType.SEP,
    ), c.data),
    state = None,
    )
async def process_callback_child(callback_query: types.CallbackQuery, state: FSMContext):
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
        bot_data = await bot.get_me()
        state = dp.current_state()
        reply_markup = None
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['name'] = response_uuid['first_name']
            if response_uuid['gender']:
                data['parent_gender'] = response_uuid['gender']
                await ask_child(callback_query.message, state, data)
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
            return
        response_sender = await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            return
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['name'] = response_sender['response_uuid']['first_name']
            data['parent_gender'] = 'm' if code[0] == str(KeyboardType.FATHER_OF_CHILD) else 'f'
            await ask_child(callback_query.message, state, data)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
        bot_data = await bot.get_me()
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
                        bot_data = await bot.get_me()
                        if status == 400 and response.get('profile'):
                            # 'Контакт "%s" есть уже у другого пользователя' % value
                            await message.reply(
                                response['message'] + \
                                ': ' + Misc.get_deeplink_with_name(response['profile'], bot_data) + '\n\n' + \
                                ('Контакты у %s не изменены' % \
                                 Misc.get_deeplink_with_name(response_sender['response_uuid'], bot_data
                            )))
                        elif status == 400 and response.get('message'):
                            await message.reply(response['message'])
                        elif status == 200:
                            await message.reply('Контакты зафиксированы')
                            await Misc.show_cards(
                                [response],
                                message,
                                bot_data,
                                response_from=response_sender,
                            )
                    except:
                        pass
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
            reply_markup=Misc.reply_markup_cancel_row()
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
                        reply = 'Пользователь не найден'
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
                            if response_to.get('tg_uid'):
                                iof_sender = Misc.get_deeplink_with_name(response_sender, bot_data)
                                try:
                                    await bot.send_message(
                                        response_to['tg_uid'],
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
            uuid=uuid,
            check_owned_only=True
        )
        if not response_sender:
            return
        response_uuid = response_sender['response_uuid']
        bot_data = await bot.get_me()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        prompt_iof = Misc.PROMPT_EXISTING_IOF % dict(
            name=response_uuid['first_name'],
        )
        await FSMexistingIOF.ask.set()
        await callback_query.message.reply(prompt_iof, reply_markup=Misc.reply_markup_cancel_row())


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMexistingIOF.ask,
)
async def put_change_existing_iof(message: types.Message, state: FSMContext):
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
            status, response = await Misc.put_user_properties(
                uuid=uuid,
                first_name=Misc.strip_text(message.text),
            )
            if status == 200:
                await message.reply('Изменено')
                bot_data = await bot.get_me()
                await Misc.show_cards(
                    [response],
                    message,
                    bot_data,
                    response_from=response_sender,
                )
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
            status, response = await Misc.put_user_properties(
                uuid=data['uuid'],
                gender='m' if is_male else 'f',
                dob=dob,
                dod=dod,
            )
            if status == 200 and response:
                await message.reply('Данные внесены:\n' + Misc.show_other_data(response))
                bot_data = await bot.get_me()
                await Misc.show_cards(
                    [response],
                    message,
                    bot_data,
                    response_from=response_sender,
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
        tg_user_sender = callback_query.from_user
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
                    tg_uid_to = None
                    user_to_delivered_uuid = None
                    if profile_from['uuid'] == profile_to['uuid']:
                        # самому себе
                        user_to_delivered_uuid = profile_to['uuid']
                    elif profile_to['owner'] and profile_to['owner']['uuid'] == profile_from['uuid']:
                        # своему овнеду
                        pass
                    elif profile_to['owner'] and profile_to['owner']['uuid'] != profile_from['uuid']:
                        # чужому овнеду: телеграм у него есть?
                        if profile_to['owner'].get('tg_uid'):
                            tg_uid_to = profile_to['owner']['tg_uid']
                            user_to_delivered_uuid = profile_to['owner']['uuid']
                    elif profile_to.get('tg_uid'):
                        tg_uid_to = profile_to['tg_uid']
                        user_to_delivered_uuid = profile_to['uuid']
                    if tg_uid_to:
                        try:
                            bot_data = await bot.get_me()
                            try:
                                await bot.send_message(
                                    tg_uid_to,
                                    text='Вам сообщение от <b>%s</b>' % Misc.get_deeplink_with_name(profile_from, bot_data),
                                    disable_web_page_preview=True,
                                )
                                await bot.forward_message(
                                    tg_uid_to,
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
        text=Misc.get_html_a(href=settings.MAP_HOST,text='Карта участников')
    )

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('setvozm', 'возможности'),
    state=None,
)
async def process_command_ability(message):
    await do_process_ability(message)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
        reply_markup = Misc.reply_markup_cancel_row()
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_ABILITY,
            reply_markup=reply_markup
        )
        return

    bot_data = await bot.get_me()
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
                    bot_data,
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
            reply_markup=reply_markup,
        )
        return

    bot_data = await bot.get_me()
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
                    bot_data,
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

    bot_data = await bot.get_me()
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
                bot_data = await bot.get_me()
                await message.reply('%s : фото внесено' % Misc.get_deeplink_with_name(response, bot_data))
                await Misc.show_cards(
                    [response],
                    message,
                    bot_data,
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
        bot_data = await bot.get_me()
        logging.debug('put (remove) photo: post tg_user data')
        tg_user_sender = callback_query.from_user
        status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
        if status_sender == 200 and response_sender:
            status, response = await Misc.put_user_properties(
                photo='',
                uuid=uuid,
            )
            if status == 200:
                await callback_query.message.reply('Фото удалено')
                await Misc.show_cards(
                    [response],
                    callback_query.message,
                    bot_data,
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
        reply_markup = Misc.reply_markup_cancel_row()
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_NEW_IOF,
            reply_markup=reply_markup
        )
        return
    bot_data = await bot.get_me()
    logging.debug('put_new_iof: post tg_user data')
    tg_user_sender = message.from_user
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if status_sender == 200 and response_sender and response_sender.get('user_id'):
        payload_iof = dict(
            tg_token=settings.TOKEN,
            owner_id=response_sender['user_id'],
            first_name=Misc.strip_text(message.text),
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
                        bot_data,
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
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.TRUST_THANK_VER_2,
        KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_tn(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по (не)доверию, благодарностям

    На входе строка:
        <KeyboardType.TRUST_THANK_VER_2>    # 0
        <KeyboardType.SEP>
        <operation_type_id>                 # 1
        <KeyboardType.SEP>

        <user_to_uuid (без знаков -)>       # 2
            ИЛИ
        <user_uuid_to>
            :   так было раньше, но отказался,
                нечего использовать user_id в вызовах апи!

        <KeyboardType.SEP>
        <message_to_forward_id>             # 3
        <KeyboardType.SEP>
        <group_id>                          # 4
        <KeyboardType.SEP>
        ''                                  # 5
        например: 2~2~326~62525~-52626~
    """
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        post_op = dict(
            tg_token=settings.TOKEN,
            operation_type_id=int(code[1]),
            tg_user_id_from=str(tg_user_sender.id),
        )
        user_uuid_to = Misc.uuid_from_text(code[2], unstrip=True)
        if user_uuid_to:
            post_op.update(user_uuid_to=user_uuid_to)
        else:
            try:
                user_id_to=int(code[2])
                post_op.update(user_id_to=user_id_to)
            except ValueError:
                return
        try:
            message_to_forward_id = int(code[3])
        except (ValueError, IndexError,):
            message_to_forward_id = None
        if message_to_forward_id:
            post_op.update(
                tg_from_chat_id=tg_user_sender.id,
                tg_message_id=message_to_forward_id,
            )
        try:
            group_id = int(code[4])
        except (ValueError, IndexError,):
            group_id = None
    except (ValueError, IndexError,):
        return

    bot_data = await bot.get_me()
    status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
    if response_sender is None:
        return
    user_from_id = response_sender.get('user_id')

    chat = callback_query.message.chat
    is_this_bot = bot_data.id == tg_user_sender.id
    if callback_query.message.chat.type in ('group', 'supergroup',) and not is_this_bot:
        await TgGroupMember.add(
            group_chat_id=chat.id,
            group_title=chat.title,
            group_type=chat.type,
            user_tg_uid=tg_user_sender.id
        )

    logging.debug('post operation, payload: %s' % post_op)
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post_op,
    )
    logging.debug('post operation, status: %s' % status)
    logging.debug('post operation, response: %s' % response)
    text = text_link = None
    operation_done = False
    if status == 200:
        if post_op['operation_type_id'] == OperationType.MISTRUST:
            operation_done = True
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Доверие к %(full_name_to)s отозвано'
            text_link = 'Доверие к %(full_name_to_link)s отозвано'
            operation_done = True
        elif post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK, OperationType.TRUST):
            text = 'Вы доверяете %(full_name_to)s (%(trust_count)s)'
            text_link = 'Вы доверяете %(full_name_to_link)s (%(trust_count)s)'
            operation_done = True
    elif status == 400 and response.get('code', '') == 'already':
        if post_op['operation_type_id'] == OperationType.TRUST:
            text = 'Уже установлено доверие'
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            text = 'Уже установлено недоверие'
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Вы и так не знакомы'

    if operation_done:
        profile_to = response['profile_to']
        profile_from = response['profile_from']
        try:
            tg_user_to_uid = profile_to['tg_data']['tg_uid']
        except KeyError:
            tg_user_to_uid = None
        try:
            tg_user_to_username = profile_to['tg_data']['tg_username']
        except KeyError:
            tg_user_to_username = ''
        try:
            tg_user_from_username = profile_from['tg_data']['tg_username']
        except KeyError:
            tg_user_from_username = None
        if text and text_link:
            full_name_to = profile_to['first_name']
            full_name_to_link = Misc.get_deeplink_with_name(profile_to, bot_data)
            d = dict(
                full_name_to=full_name_to,
                full_name_to_link=full_name_to_link,
                trust_count=profile_to['trust_count'],
            )
            text = text % d
            text_link = text_link % d

    if not text and not operation_done:
        if status == 200:
            text = 'Операция выполнена'
        elif status == 400 and response.get('message'):
            text = response['message']
        else:
            text = 'Простите, произошла ошибка'

    if not text_link and text:
        text_link = text

    # Это отправителю благодарности и т.п.
    #
    try:
        await bot.answer_callback_query(
                callback_query.id,
                text=text,
                show_alert=True,
            )
    except (ChatNotFound, CantInitiateConversation):
        pass
    if operation_done and not group_id and text_link:
        # Не отправляем в личку, если сообщение в группу
        try:
            await bot.send_message(
                tg_user_sender.id,
                text=text_link,
                disable_web_page_preview=True,
            )
        except (ChatNotFound, CantInitiateConversation):
            pass

    # Это в группу
    #
    if group_id and operation_done:
        reply = ''
        if post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK, OperationType.TRUST):
            reply = '%(dl_sender)s (%(tc_sender)s) доверяет %(dl_receiver)s (%(tc_receiver)s)'
        if reply:
            reply %= dict(
                dl_sender=Misc.get_deeplink_with_name(profile_from, bot_data),
                dl_receiver=Misc.get_deeplink_with_name(profile_to, bot_data),
                tc_sender=profile_from['trust_count'],
                tc_receiver=profile_to['trust_count'],
            )
            try:
                await bot.send_message(
                    group_id,
                    text=reply,
                    disable_web_page_preview=True,
                )
            except (ChatNotFound, CantInitiateConversation):
                pass

    # Это получателю благодарности и т.п.
    #
    if operation_done and tg_user_to_uid:
        reply = ''
        if post_op['operation_type_id'] == OperationType.TRUST:
            reply = 'Получено доверие от'
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            pass
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            pass
        elif post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            reply = 'Получено доверие от'

        if reply:
            reply += ' ' + Misc.get_deeplink_with_name(response_sender, bot_data)

            if message_to_forward_id:
                try:
                    await bot.forward_message(
                        chat_id=tg_user_to_uid,
                        from_chat_id=tg_user_sender.id,
                        message_id=message_to_forward_id,
                    )
                except:
                    pass
            try:
                await bot.send_message(
                    tg_user_to_uid,
                    text=reply,
                    disable_web_page_preview=True,
                )
                # TODO здесь временно сделано, что юзер стартанул бот ----------------
                # Потом удалить
                #
                await Misc.put_user_properties(
                    uuid=profile_to['uuid'],
                    did_bot_start='1',
                )
                # --------------------------------------------------------------------
            except (ChatNotFound, CantInitiateConversation):
                pass

    if response_sender.get('created'):
        await Misc.update_user_photo(bot, tg_user_sender, response_sender)


async def geo(message, state, state_to_set, uuid=None):
    # Здесь вынужден отказаться от параметра , one_time_keyboard=True
    # Не убирает телеграм "нижнюю" клавиатуру в мобильных клиентах!
    # Убираю "вручную", сообщением с reply_markup=types.reply_keyboard.ReplyKeyboardRemove()
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
        message.chat.id,
        'Пожалуйста, нажмите на кнопку "%s" снизу' % Misc.PROMPT_LOCATION,
        reply_markup=keyboard
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=["setplace", "место"],
    state=None,
)
async def geo_command_handler(message: types.Message, state: FSMContext):
    await geo(message, state, FSMgeo.geo)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
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
        await geo(callback_query.message, state, FSMgeo.geo, uuid)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('trip',),
    state=None,
)
async def trip_geo_command_handler(message: types.Message, state: FSMContext):
    await geo(message, state, FSMtrip.geo)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=['location', ContentType.TEXT],
    state=FSMtrip.geo,
)
async def location_trip(message: types.Message, state: FSMContext):
    if message.location is not None:
        try:
            latitude = getattr(message.location, 'latitude')
            longitude = getattr(message.location, 'longitude')
        except AttributeError:
            pass
        if latitude and longitude:
            pass
    await message.reply(
        'Ok.\nПока по команде /trip ничего не делается, даже если Вы отправили боту локацию',
        reply_markup=types.reply_keyboard.ReplyKeyboardRemove()
    )
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
    if message.location is not None:
        user_uuid = None
        async with state.proxy() as data:
            user_uuid = data.get('uuid')
        latitude = longitude = None
        try:
            latitude = getattr(message.location, 'latitude')
            longitude = getattr(message.location, 'longitude')
        except AttributeError:
            pass
        if latitude and longitude:
            bot_data = await bot.get_me()
            tg_user_sender = message.from_user
            status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
            if status_sender == 200:
                if not user_uuid:
                    user_uuid = response_sender.get('uuid')
            if user_uuid:
                status, response = await Misc.put_user_properties(
                    uuid=user_uuid,
                    latitude = latitude,
                    longitude = longitude,
                )
                reply_markup = types.reply_keyboard.ReplyKeyboardRemove()
                if status == 200:
                    await Misc.show_cards(
                        [response],
                        message,
                        bot_data,
                        response_from=response_sender,
                    )
                    await message.reply('Координаты записаны', reply_markup=reply_markup)
                else:
                    await message.reply('Ошибка записи координат', reply_markup=reply_markup)
    else:
        # text message, отмена или ввел что-то
        reply = 'Выберите что-то из кнопок снизу'
        try:
            message_text = message.text
            if message_text != Misc.PROMPT_CANCEL_LOCATION:
                await message.reply(
                    'Надо что-то выбрать: <u>%s</u> или <u>%s</u>, из кнопок снизу' % (
                        Misc.PROMPT_LOCATION, Misc.PROMPT_CANCEL_LOCATION
                ))
                return
        except AttributeError:
            pass
        await message.reply(
            'Вы отказались задавать местоположение',
            reply_markup=types.reply_keyboard.ReplyKeyboardRemove()
        )
    await Misc.state_finish(state)


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
    commands=['help',],
    state=None,
)
async def echo_help_to_bot(message: types.Message, state: FSMContext):
    await message.reply(Misc.help_text(), disable_web_page_preview=True)


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
            'Всего пользователей: %(all)s\n'
            'Стартовали бот: %(did_bot_start)s\n'
            'Указали местоположение: %(with_geodata)s\n'
        ) % {
            'all': response['all'],
            'did_bot_start': response['did_bot_start'],
            'with_geodata': response['with_geodata'],
        }
    else:
        reply = 'Произошла ошибка'
    await message.reply(reply)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=None,
)
async def echo_send_to_bot(message: types.Message, state: FSMContext):
    """
    Обработка остальных сообщений в бот
    """

    if not message.is_forward() and message.content_type != ContentType.TEXT:
        await message.reply(
            'Сюда можно слать текст для поиска, включая @username, или пересылать сообщения любого типа'
        )
        return

    reply = ''
    reply_markup = None

    tg_user_sender = message.from_user

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
    if tg_user_sender.is_bot:
        reply = 'Сообщения от ботов пока не обрабатываются'
    else:
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
            elif message_text in ('/start', '/ya', '/я'):
                state_ = 'ya'
            else:
                m = re.search(
                    r'^\/start\s+([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$',
                    message_text,
                    flags=re.I,
                )
                if m:
                    # /start 293d987f-4ee8-407c-a614-7110cad3552f
                    # state_ = 'start_uuid'
                    uuid_to_search = m.group(1).lower()
                    state_ = 'start_uuid'
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
                            payload_username = dict(
                                tg_username=','.join(usernames),
                                verbose='',
                            )
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
                state_ == 'start_uuid' and response_from.get('created'):
                a_response_to += [response_from, ]

    if user_from_id and state_ == 'start_uuid':
        logging.debug('get tg_user_by_start_uuid data in api...')
        payload_uuid = dict(
            uuid=uuid_to_search,
        )
        try:
            status, response_uuid = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=payload_uuid,
            )
            logging.debug('get tg_user_by_start_uuid in api, response_to: %s' % response_uuid)
            if status == 200:
                a_response_to += [response_uuid, ]
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
            payload_username = dict(
                tg_username=','.join(usernames),
                verbose='',
            )
            status, response = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=payload_username,
            )
            logging.debug('get by username, status: %s' % status)
            logging.debug('get by username, response: %s' % response)
            if status == 200 and response:
                a_found += response


    if state_ and state_ not in ('not_found', 'invalid_message_text', ) and user_from_id and a_response_to:
        message_to_forward_id = state_ == 'forwarded_from_other' and message.message_id or ''
        await Misc.show_cards(
            a_response_to,
            message,
            bot_data,
            exclude_tg_uids=[],
            response_from=response_from,
            message_to_forward_id=message_to_forward_id,
        )
        if state_ == 'start':
             await message.reply(Misc.help_text(), disable_web_page_preview=True)

    elif reply:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    await Misc.show_deeplinks(a_found, message, bot_data)

    if user_from_id and (response_from.get('created') or state_ == 'start'):
        await Misc.update_user_photo(bot, tg_user_sender, response_from)
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

@dp.chat_join_request_handler()
async def echo_join_channel_request(message: types.Message):
    """
    Пользователь присоединяется к каналу по ссылке- приглашению

    Работает только ссылка, требующая одобрения.
    Бот, он всегда администратор канала, одобрит.
    Но до этого:
        Нового участника надо завести в базе, если его там нет
        В канал отправится мини- карточка нового участника
    """
    tg_subscriber = message.from_user
    tg_inviter = message.invite_link.creator
    status, response_inviter = await Misc.post_tg_user(tg_inviter)
    if status != 200:
        return

    # Владельца канала сразу в канал. Вдруг его там нет
    #
    await TgGroupMember.add(
        group_chat_id=message.chat.id,
        group_title=message.chat.title,
        group_type=message.chat.type,
        user_tg_uid=tg_inviter.id,
    )

    dict_callback = dict(
        keyboard_type=KeyboardType.CHANNEL_JOIN,
        tg_subscriber_id=tg_subscriber.id,
        tg_inviter_id=tg_inviter.id,
        channel_id=message.chat.id,
        sep=KeyboardType.SEP,
    )
    callback_data_template = (
        '%(keyboard_type)s%(sep)s'
        '%(tg_subscriber_id)s%(sep)s'
        '%(tg_inviter_id)s%(sep)s'
        '%(channel_id)s%(sep)s'
    )
    inline_btn_channel_join = InlineKeyboardButton(
        text='Согласие',
        callback_data=callback_data_template % dict_callback,
    )
    dict_callback.update(keyboard_type=KeyboardType.CHANNEL_REFUSE)
    inline_btn_channel_refuse = InlineKeyboardButton(
        text='Отказ',
        callback_data=callback_data_template % dict_callback,
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_btn_channel_join, inline_btn_channel_refuse)
    await bot.send_message(
        chat_id=tg_subscriber.id,
        text=Misc.help_text(),
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

    if response_inviter.get('created'):
        await Misc.update_user_photo(bot, tg_inviter, response_inviter)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.CHANNEL_JOIN,
        KeyboardType.SEP,
        # tg_subscriber_id          # 1
        # tg_inviter_id             # 2
        # channel_id                # 3
    ), c.data
    ), state=None,
    )
async def process_callback_channel_join(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.message:
        tg_subscriber = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        try:
            tg_subscriber_id = int(code[1])
            if not (tg_subscriber_id and tg_subscriber.id == tg_subscriber_id):
                return
            tg_inviter_id = int(code[2])
            channel_id = int(code[3])
        except (IndexError, ValueError, TypeError,):
            return
        status, response_subscriber = await Misc.post_tg_user(tg_subscriber)
        if status != 200:
            return
        status, response_inviter = await Misc.get_user_by_tg_uid(tg_inviter_id)
        if status != 200:
            return
        await TgGroupMember.add(
            group_chat_id=channel_id,
            group_title='',
            group_type='',
            user_tg_uid=tg_subscriber_id,
        )
        try:
            await bot.approve_chat_join_request(
                    channel_id,
                    tg_subscriber_id
            )
        except BadRequest as excpt:
            msg = 'Наверное, вы уже в канале'
            try:
                if excpt.args[0] == 'User_already_participant':
                    msg = 'Вы уже в канале'
            except:
                pass
            await callback_query.message.reply(msg, disable_web_page_preview=True,)
            return

        # Сразу доверие c благодарностью от входящего в канал к владельцу канала
        #
        post_op = dict(
            tg_token=settings.TOKEN,
            operation_type_id=OperationType.TRUST_AND_THANK,
            tg_user_id_from=tg_subscriber_id,
            user_uuid_to=response_inviter['uuid'],
        )
        logging.debug('post operation (channel subscriber thanks inviter), payload: %s' % post_op)
        status_op, response_op = await Misc.api_request(
            path='/api/addoperation',
            method='post',
            data=post_op,
        )
        logging.debug('post operation (channel subscriber thanks inviter), status: %s' % status_op)
        logging.debug('post operation (channel subscriber thanks inviter), response: %s' % response_op)

        bot_data = await bot.get_me()
        dl_subscriber = Misc.get_deeplink_with_name(response_subscriber, bot_data)

        dl_inviter = Misc.get_deeplink_with_name(response_inviter, bot_data)
        if status_op == 200:
            dl_inviter = Misc.get_deeplink_with_name(response_inviter, bot_data)
            reply = '%(dl_subscriber)s подключен(а) к каналу и увеличил(а)  до %(thanks_count)s доверия к владельцу канала' % dict(
                dl_subscriber=dl_subscriber,
                thanks_count=response_op['currentstate']['thanks_count'],
            )
        else:
            reply = '%(dl_subscriber)s подключен(а) к каналу' % dict(
                dl_subscriber=dl_subscriber,
            )
        await bot.send_message(
            channel_id,
            reply,
            disable_notification=True,
            disable_web_page_preview=True,
        )
        await callback_query.message.reply(
            'Добро пожаловать в канал',
            disable_web_page_preview=True,
        )
        await Misc.put_user_properties(
            uuid=response_subscriber['uuid'],
            did_bot_start='1',
        )
        if response_subscriber.get('created'):
            await Misc.update_user_photo(bot, tg_subscriber, response_subscriber)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.CHANNEL_REFUSE,
        KeyboardType.SEP,
        # tg_subscriber_id          # 1
        # tg_inviter_id             # 2
        # channel_id                # 3
    ), c.data
    ), state=None,
    )
async def process_callback_channel_join(callback_query: types.CallbackQuery, state: FSMContext):
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
    if bot_.is_bot and new_chat_member.status == 'administrator' and bot_.first_name:
        reply_markup = InlineKeyboardMarkup()
        #inline_btn_map = InlineKeyboardButton('Карта', url=settings.MAP_HOST)
        inline_btn_trusts = InlineKeyboardButton(
            'Доверие',
            url='%(group_host)s/?tg_group_chat_id=%(chat_id)s' % dict(
                group_host=settings.GROUP_HOST,
                chat_id=chat_member.chat.id,
        ))
        reply_markup.row(
            inline_btn_trusts,
            #inline_btn_map
        )
        await bot.send_message(
            chat_id=chat_member.chat.id,
            text=bot_.first_name,
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

        if tg_user_left:
            # Ушел пользователь, убираем его из группы
            await TgGroupMember.remove(
                group_chat_id=message.chat.id,
                group_title=message.chat.title,
                group_type=message.chat.type,
                user_tg_uid=response_from['tg_uid']
            )
        elif str(bot_data.id) != str(response_from['tg_uid']):
            # Добавить в группу в апи, если его там нет и если это не бот-обработчик
            await TgGroupMember.add(
                group_chat_id=message.chat.id,
                group_title=message.chat.title,
                group_type=message.chat.type,
                user_tg_uid=response_from['tg_uid']
            )

        if tg_users_new and \
           str(tg_user_sender.id) != str(response_from['tg_uid']):
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
            # Обновить, ибо уже на доверие больше у него может быть
            status, response_from = await Misc.post_tg_user(user_in)
            if status != 200:
                continue

        reply_template = '<b>%(deeplink_with_name)s</b>'
        is_this_bot = str(bot_data.id) == str(response_from['tg_uid'])
        trust_count = response_from.get('trust_count')
        if (trust_count is not None) and not (is_this_bot and tg_users_new):
            reply_template += ' (%(trust_count)s)'
        reply = reply_template % dict(
            deeplink_with_name=Misc.get_deeplink_with_name(response_from, bot_data),
            trust_count=trust_count,
        )

        if not is_previous_his:
            reply_markup = InlineKeyboardMarkup()
            path = "/profile/?id=%(uuid)s" % dict(uuid=response_from['uuid'],)

            url = settings.FRONTEND_HOST + path
            # login_url = Misc.make_login_url(path)
            # login_url = LoginUrl(url=login_url)
            inline_btn_go = InlineKeyboardButton(
                'Друзья',
                url=url,
                # login_url=login_url,
            )
            buttons = [inline_btn_go]

            if is_this_bot:
                if tg_user_left:
                    # ЭТОТ Бот ушел, не может послать ответ без аварии
                    reply = ''
                elif tg_users_new:
                    # ЭТОТ бот подключился. Достаточно его full name и ссылку на доверия в группе
                    #
                    inline_btn_trusts = InlineKeyboardButton(
                        'Доверие',
                        url='%(group_host)s/?tg_group_chat_id=%(chat_id)s' % dict(
                            group_host=settings.GROUP_HOST,
                            chat_id=message.chat.id,
                    ))
                    buttons = [inline_btn_trusts]
            else:
                # не делать кнопку Доверия для бота, глючит!
                dict_reply = dict(
                    operation=OperationType.TRUST_AND_THANK,
                    keyboard_type=KeyboardType.TRUST_THANK_VER_2,
                    sep=KeyboardType.SEP,
                    user_to_uuid_stripped=Misc.uuid_strip(response_from['uuid']),
                    message_to_forward_id='',
                    group_id=message.chat.id,
                )
                callback_data_template = OperationType.CALLBACK_DATA_TEMPLATE
                inline_btn_thank = InlineKeyboardButton(
                    '+Доверие',
                    callback_data=callback_data_template % dict_reply,
                )
                buttons.append(inline_btn_thank)
            reply_markup.row(*buttons)

            if reply:
                await message.answer(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    for i, response_from in enumerate(a_users_out):
        if response_from.get('created'):
            await Misc.update_user_photo(bot, a_users_in[i], response_from)


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
