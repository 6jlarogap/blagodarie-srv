import base64, re
from io import BytesIO

import settings
from settings import logging
from utils import Misc, OperationType, KeyboardType

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.types.login_url import LoginUrl
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import ChatTypeFilter, Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_polling, start_webhook
from aiogram.utils.parts import safe_split_text
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from aiogram.utils.exceptions import ChatNotFound, CantInitiateConversation

storage = MemoryStorage()

class FSMability(StatesGroup):
    ask = State()

class FSMwish(StatesGroup):
    ask = State()

class FSMnewIOF(StatesGroup):
    ask = State()

class FSMphoto(StatesGroup):
    ask = State()
    remove = State()

last_user_in_group = None

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
    ))
async def process_callback_ability(callback_query: types.CallbackQuery):
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
    ))
async def process_callback_wish(callback_query: types.CallbackQuery):
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
async def put_ability(message, state):
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
async def put_wish(message, state):
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
async def put_photo(message, state):
    if message.content_type != ContentType.PHOTO:
        reply_markup = Misc.reply_markup_cancel_row()
        await message.reply(
            Misc.MSG_ERROR_PHOTO_ONLY + '\n\n' + \
            Misc.PROMPT_PHOTO,
            reply_markup=reply_markup,
        )
        return

    bot_data = await bot.get_me()
    logging.debug('put_photo: post tg_user data')
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
            await message.photo[-1].download(destination_file=image)
            image = base64.b64encode(image.read()).decode('UTF-8')

            logging.debug('put tg_user_by_uuid photo...')
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo=image,
                uuid=user_uuid,
            )
            status_photo, response_photo = await Misc.api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.debug('put tg_user_by_uuid photo, status: %s' % status_photo)
            logging.debug('put tg_user_by_uuid photo, response: %s' % response_photo)
            if status_photo == 200:
                await message.reply('Фото внесено')
                try:
                    status, response = await Misc.get_user_by_uuid(user_uuid)
                    if status == 200:
                        await Misc.show_cards(
                            [response],
                            message,
                            bot_data,
                            response_from=response_sender,
                        )
                except:
                    pass
            elif status_photo == 400:
                if response_photo.get('message'):
                    await message.reply(response_photo['message'])
                else:
                    await message.reply(Misc.MSG_ERROR_API)
            else:
                await message.reply(Misc.MSG_ERROR_API)
        else:
            await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.PHOTO,       # 0
        KeyboardType.SEP,
        # uuid, кому              # 1
        # KeyboardType.SEP,
    ), c.data
    ))
async def process_callback_photo(callback_query: types.CallbackQuery):
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        uuid = code[1]
        if uuid and not await Misc.check_owner(owner_tg_user=tg_user_sender, uuid=uuid):
            return
    except IndexError:
        uuid = None
    if uuid:
        callback_data_cancel = '%(keyboard_type)s%(sep)s' % dict(
            keyboard_type=KeyboardType.CANCEL_ANY,
            sep=KeyboardType.SEP,
        )
        inline_btn_cancel = InlineKeyboardButton(
            'Отмена',
            callback_data=callback_data_cancel,
        )
        reply_markup = InlineKeyboardMarkup()
        await FSMphoto.ask.set()
        state = dp.current_state()
        async with state.proxy() as data:
            data['uuid'] = uuid
        prompt_photo = Misc.PROMPT_PHOTO
        status, response = await Misc.get_user_by_uuid(uuid)
        if status == 200 and response and Misc.is_photo_downloaded(response):
            prompt_photo += '\n' + Misc.PROMPT_PHOTO_REMOVE
            callback_data_remove = '%(keyboard_type)s%(sep)s%(uuid)s%(sep)s' % dict(
                keyboard_type=KeyboardType.PHOTO_REMOVE,
                sep=KeyboardType.SEP,
                uuid=uuid,
            )
            inline_btn_remove = InlineKeyboardButton(
                'Удалить',
                callback_data=callback_data_remove,
            )
            reply_markup.row(inline_btn_cancel, inline_btn_remove)
        else:
            reply_markup.row(inline_btn_cancel)
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
            callback_data_cancel = '%(keyboard_type)s%(sep)s' % dict(
                keyboard_type=KeyboardType.CANCEL_ANY,
                sep=KeyboardType.SEP,
            )
            inline_btn_cancel = InlineKeyboardButton(
                'Отмена',
                callback_data=callback_data_cancel,
            )
            callback_data_remove = '%(keyboard_type)s%(sep)s%(uuid)s%(sep)s' % dict(
                keyboard_type=KeyboardType.PHOTO_REMOVE_CONFIRMED,
                sep=KeyboardType.SEP,
                uuid=uuid,
            )
            inline_btn_remove = InlineKeyboardButton(
                'Да, удалить',
                callback_data=callback_data_remove,
            )
            reply_markup = InlineKeyboardMarkup()
            reply_markup.row(inline_btn_cancel, inline_btn_remove)
            full_name = Misc.get_iof(response)
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
        tg_user_sender = callback_query.message.from_user
        status_sender, response_sender = await Misc.post_tg_user(tg_user_sender)
        if status_sender == 200 and response_sender:
            payload_photo = dict(
                tg_token=settings.TOKEN,
                photo='',
                uuid=uuid,
            )
            status_photo, response_photo = await Misc.api_request(
                path='/api/profile',
                method='put',
                data=payload_photo,
            )
            logging.debug('put (remove) user_photo, status: %s' % status_photo)
            logging.debug('put (remove) user_photo, response: %s' % response_photo)
            if status_photo == 200:
                await callback_query.message.reply('Фото удалено')
                try:
                    status, response = await Misc.get_user_by_uuid(uuid)
                    if status == 200:
                        await Misc.show_cards(
                            [response],
                            callback_query.message,
                            bot_data,
                            response_from=response_sender,
                        )
                except:
                    pass
            elif status_photo == 400:
                if response_photo.get('message'):
                    await message.reply(response_photo['message'])
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
async def put_new_iof(message, state):
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
        message_text = message.text.strip()
        message_text = re.sub(r'\s{2,}', ' ', message_text)
        payload_iof = dict(
            tg_token=settings.TOKEN,
            owner_id=response_sender['user_id'],
            first_name=message_text,
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
async def process_command_new(message):
    reply_markup = Misc.reply_markup_cancel_row()
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    await FSMnewIOF.ask.set()
    state = dp.current_state()
    await message.reply(Misc.PROMPT_NEW_IOF, reply_markup=reply_markup)
    if status_sender and response_sender.get('created'):
        photo = await Misc.get_user_photo(bot, message.from_user)
        if photo:
            await Misc.put_tg_user_photo(photo, response_sender)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.TRUST_THANK_VER_2,
        KeyboardType.SEP,
    ), c.data
    ))
async def process_callback_tn(callback_query: types.CallbackQuery):
    """
    Действия по (не)доверию, благодарностям

    На входе строка:
        <KeyboardType.TRUST_THANK_VER_2>    # 0
        <KeyboardType.SEP>
        <operation_type_id>                 # 1
        <KeyboardType.SEP>
        <user_to_id>                        # 2
        <KeyboardType.SEP>
        <message_to_forward_id>             # 3
        <KeyboardType.SEP>
        <group_id>                          # 4
        <KeyboardType.SEP>
        ''                                  # 5
        например: 2~2~326~387~62525~-52626~
    """
    code = callback_query.data.split(KeyboardType.SEP)
    tg_user_sender = callback_query.from_user
    try:
        post_op = dict(
            tg_token=settings.TOKEN,
            operation_type_id=int(code[1]),
            tg_user_id_from=str(tg_user_sender.id),
            user_id_to=int(code[2]),
        )
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
    payload_sender = dict(
        tg_token=settings.TOKEN,
        tg_uid=tg_user_sender.id,
        last_name=tg_user_sender.last_name or '',
        first_name=tg_user_sender.first_name or '',
        username=tg_user_sender.username or '',
        activate='1',
    )
    try:
        status_sender, response_sender = await Misc.api_request(
            path='/api/profile',
            method='post',
            data=payload_sender,
        )
        logging.debug('get_or_create tg_user_sender data in api, status_sender: %s' % status_sender)
        logging.debug('get_or_create tg_user_sender data in api, response_sender: %s' % response_sender)
        user_from_id = response_sender.get('user_id')
    except:
        return

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
        if post_op['operation_type_id'] == OperationType.TRUST:
            text = 'Установлено доверие с %(full_name_to)s'
            text_link = 'Установлено доверие с %(full_name_to_link)s'
            operation_done = True
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            text = 'Установлено недоверие с %(full_name_to)s'
            text_link = 'Установлено недоверие с %(full_name_to_link)s'
            operation_done = True
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            text = 'Установлено, что не знакомы с %(full_name_to)s'
            text_link = 'Установлено, что не знакомы с %(full_name_to_link)s'
            operation_done = True
        elif post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            text = 'Отправлена благодарность к %(full_name_to)s'
            text_link = 'Отправлена благодарность к %(full_name_to_link)s'
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
            tg_user_to_uid = profile_to['tg_data']['uid']
        except KeyError:
            tg_user_to_uid = None
        try:
            tg_user_to_username = profile_to['tg_data']['username']
        except KeyError:
            tg_user_to_username = ''
        try:
            tg_user_from_username = profile_from['tg_data']['username']
        except KeyError:
            tg_user_from_username = None
        full_name_to = Misc.get_iof(profile_to)
        full_name_to_link = (
                '<a href="%(frontend_host)s/profile/?id=%(uuid)s">%(full_name)s</a>'
            ) % dict(
            frontend_host=settings.FRONTEND_HOST,
            uuid=profile_to['uuid'],
            full_name=full_name_to,
        )
        d = dict(
            full_name_to=full_name_to,
            full_name_to_link=full_name_to_link,
        )
        text = text % d
        text_link = text_link % d
        if tg_user_to_username:
            text_link += ' ( @%s )' % tg_user_to_username

    if not text:
        if status == 200:
            text = 'Операция выполнена'
        elif status == 400 and response.get('message'):
            text = response['message']
        else:
            text = 'Простите, произошла ошибка'

    if not text_link:
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
    if operation_done and not group_id:
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
        if post_op['operation_type_id'] == OperationType.TRUST:
            reply = '%(deeplink_sender)s доверяет %(deeplink_receiver)s'
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            reply = '%(deeplink_sender)s не доверяет %(deeplink_receiver)s'
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            reply = '%(deeplink_sender)s заявляет, что не знаком(а) с %(deeplink_receiver)s'
        elif post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            reply = '%(deeplink_sender)s поблагодарил(а) %(deeplink_receiver)s'
        if reply:
            deeplink_template = '<a href="%(deeplink)s">%(full_name)s</a>'
            deeplink_sender = deeplink_template % dict(
                deeplink=Misc.get_deeplink(profile_from, bot_data),
                full_name=tg_user_sender.full_name,
            )
            deeplink_receiver = deeplink_template % dict(
                deeplink=Misc.get_deeplink(profile_to, bot_data),
                full_name=Misc.get_iof(profile_to)
            )
            reply %= dict(deeplink_sender=deeplink_sender, deeplink_receiver=deeplink_receiver)
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
            reply = 'Установлено доверие с'
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            reply = 'Установлено недоверие с'
        elif post_op['operation_type_id'] == OperationType.NULLIFY_TRUST:
            reply = 'Установлено, что не знакомы с'
        elif post_op['operation_type_id'] in (OperationType.TRUST_AND_THANK, OperationType.THANK):
            reply = 'Получена благодарность от'

        if reply:
            reply += ' <a href="%(deeplink_sender)s">%(full_name_sender)s</a>' % dict(
                deeplink_sender=Misc.get_deeplink(response_sender, bot_data),
                full_name_sender=tg_user_sender.full_name,
            )

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
                payload_did_bot_start = dict(
                    tg_token=settings.TOKEN,
                    uuid=profile_to['uuid'],
                    did_bot_start='1',
                )
                status, response = await Misc.api_request(
                    path='/api/profile',
                    method='put',
                    data=payload_did_bot_start,
                )
                logging.debug('put tg_user_sender_payload_did_bot_start, status: %s' % status)
                logging.debug('put tg_user_sender_payload_did_bot_start, response: %s' % response)
                # --------------------------------------------------------------------
            except (ChatNotFound, CantInitiateConversation):
                pass

    if response_sender.get('created'):
        tg_user_sender_photo = await Misc.get_user_photo(bot, tg_user_sender)
        if tg_user_sender_photo:
            await Misc.put_tg_user_photo(tg_user_sender_photo, response_sender)


async def geo(message: types.Message, uuid=None):
    keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
    button_geo = types.KeyboardButton(text="Отправить местоположение", request_location=True)
    keyboard.add(button_geo)
    state = dp.current_state()
    if uuid:
        async with state.proxy() as data:
            data['uuid'] = uuid
    await bot.send_message(message.chat.id, 'Пожалуйста, нажмите на кнопку "Отправить местоположение" снизу', reply_markup=keyboard)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=["setplace", "место"]
)
async def geo_command_handler(message: types.Message):
    await geo(message)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s)%s' % (
        KeyboardType.LOCATION,
        KeyboardType.SEP,
        # uuid, кому                # 1
        # KeyboardType.SEP,
    ), c.data
    ))
async def process_callback_location(callback_query: types.CallbackQuery):
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
        await geo(callback_query.message, uuid)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=["location",],
)
async def location(message: types.Message, state: FSMContext):
    """
    Записать местоположение пользователя телеграма или uuid в состоянии
    """
    state = dp.current_state()
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
                if user_uuid:
                    status_this, response_this = await Misc.get_user_by_uuid(user_uuid)
                else:
                    status_this, response_this = status_sender, response_sender
                    user_uuid = response_this.get('uuid')
            if user_uuid:
                payload_location = dict(
                    tg_token=settings.TOKEN,
                    uuid=user_uuid,
                    latitude = latitude,
                    longitude = longitude,
                )
                status, response = await Misc.api_request(
                    path='/api/profile',
                    method='put',
                    data=payload_location,
                )
                logging.debug('put tg_user_sender_location, status: %s' % status)
                logging.debug('put tg_user_sender_location, response: %s' % response)
                if status == 200:
                    response_this.update(
                        latitude=latitude,
                        longitude=longitude,
                    )
                    await Misc.show_cards(
                        [response_this],
                        message,
                        bot_data,
                        response_from=response_sender,
                    )
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['getowned', 'listown'],
)
async def echo_getowned_to_bot(message: types.Message):
    tg_user_sender = message.from_user
    payload_from = dict(
        tg_token=settings.TOKEN,
        tg_uid=tg_user_sender.id,
        last_name=tg_user_sender.last_name or '',
        first_name=tg_user_sender.first_name or '',
        username=tg_user_sender.username or '',
        activate='1',
    )
    try:
        status, response_from = await Misc.api_request(
            path='/api/profile',
            method='post',
            data=payload_from,
        )
        logging.debug('get_or_create tg_user_sender data in api, status: %s' % status)
        logging.debug('get_or_create tg_user_sender data in api, response_from: %s' % response_from)
        user_from_uuid = response_from['uuid']
    except:
        return

    try:
        status, a_response_to = await Misc.api_request(
            path='/api/profile',
            method='get',
            params=dict(uuid_owner=user_from_uuid),
        )
        logging.debug('get_tg_user_sender_owned data in api, status: %s' % status)
        logging.debug('get_tg_user_sender_owned data in api, response: %s' % a_response_to)
    except:
        return

    if not a_response_to:
        await message.reply('У вас нет запрошенных данных')
        return

    bot_data = await bot.get_me()
    reply = ''
    for response in a_response_to:
        deeplink=Misc.get_deeplink(response, bot_data)
        iof = Misc.get_iof(response)
        lifetime_years_str = Misc.get_lifetime_years_str(response)
        if lifetime_years_str:
            lifetime_years_str = ', ' + lifetime_years_str
        reply += '<a href="%(deeplink)s">%(iof)s%(lifetime_years_str)s</a>\n'
        reply %= dict(deeplink=deeplink, iof=iof, lifetime_years_str=lifetime_years_str)
    parts = safe_split_text(reply, split_separator='\n')
    for part in parts:
        await message.reply(part, disable_web_page_preview=True)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['help',],
)
async def echo_help_to_bot(message: types.Message):
    await message.reply(Misc.help_text())


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=['stat',],
)
async def echo_stat_to_bot(message: types.Message):
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
)
async def echo_send_to_bot(message: types.Message):
    """
    Обработка остальных сообщений в бот
    
    кнопка /start 
        возвращаем карточку юзера с данными обратившегося пользователя
        и кнопкой перейти и без других кнопок.

    просто сообщение в бот
        смотрим текст если там @username - проверяем -
        если он у нас зарегистрирован - выводим карточку этого @username
        - если не зарегистрирован - или нет в тексте @username
        - отвечаем "Профиль не найден"
        Если передал свой @username в сообщении, показать свою карточку

    пересланное сообщение от самого себя
        показываем карточку профиля автора пересланного сообщения - себя
        - с кнопкой перейти и без других кнопок

    пересланное сообщение от бота
        "Сообщения от ботов пока не обрабатываются"

    пересланное сообщение от того, кто не дает себя аутентифицировать
        "пользователь скрыл..."

    пересланное сообщение от того, кто дал себя аутентифицировать
        карточку профиля Автора пересланного сообщения - со всеми кнопками

    Карточка профиля:
        Имя Фамилия
        Доверий:
        Благодарностей:
        Недоверий:

        Возможности: водитель Камаз шашлык виноград курага изюм

        Потребности: не задано

        Местоположение: не задано/ссылка на карту

        Контакты:
        @username
        +3752975422568
        https://username.com

        От Вас: доверие
        К Вам: не знакомы

    Кнопки:
        Перейти
        Благодарность   Недоверие   Не знакомы
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

    state = ''

    # Кого будут благодарить
    # или свой профиль в массиве
    # или массив найденных профилей
    #
    a_response_to = []

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
                state = 'forwarded_from_me'
            else:
                state = 'forwarded_from_other'
        else:
            if message_text in ('/start', '/ya', '/я'):
                state = 'start'
            else:
                m = re.search(
                    r'^\/start\s+([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$',
                    message_text,
                    flags=re.I,
                )
                if m:
                    # /start 293d987f-4ee8-407c-a614-7110cad3552f
                    # state = 'start_uuid'
                    uuid_to_search = m.group(1).lower()
                    state = 'start_uuid'
                else:
                    if len(message_text) < settings.MIN_LEN_SEARCHED_TEXT:
                        state = 'invalid_message_text'
                        reply = Misc.help_text()
                    else:
                        usernames, text_stripped = Misc.get_text_usernames(message_text)
                        if usernames:
                            logging.debug('@usernames found in message text\n') 
                            payload_username = dict(
                                tg_username=','.join(usernames),
                            )
                            status, response = await Misc.api_request(
                                path='/api/profile',
                                method='get',
                                params=payload_username,
                            )
                            logging.debug('get by username, status: %s' % status)
                            logging.debug('get by username, response: %s' % response)
                            if status == 200 and response:
                                a_response_to += response
                                state = 'found_username'
                            else:
                                state = 'not_found'

                        if text_stripped and len(text_stripped) >= settings.MIN_LEN_SEARCHED_TEXT:
                            payload_query = dict(
                                query=text_stripped,
                            )
                            status, response = await Misc.api_request(
                                path='/api/profile',
                                method='get',
                                params=payload_query
                            )
                            logging.debug('get by query, status: %s' % status)
                            logging.debug('get by query, response: %s' % response)
                            if status == 200 and response:
                                a_response_to += response
                                state = 'found_in_search'
                            elif state != 'found_username':
                                state = 'not_found'

    if state == 'not_found':
        reply = 'Профиль не найден'

    if state:
        logging.debug('get_or_create tg_user_sender data in api...')
        payload_from = dict(
            tg_token=settings.TOKEN,
            tg_uid=tg_user_sender.id,
            last_name=tg_user_sender.last_name or '',
            first_name=tg_user_sender.first_name or '',
            username=tg_user_sender.username or '',
            activate='1',
            did_bot_start='1',
        )
        try:
            status, response_from = await Misc.api_request(
                path='/api/profile',
                method='post',
                data=payload_from,
            )
            logging.debug('get_or_create tg_user_sender data in api, status: %s' % status)
            logging.debug('get_or_create tg_user_sender data in api, response_from: %s' % response_from)
            if status == 200:
                response_from.update(tg_username=tg_user_sender.username)
                user_from_id = response_from.get('user_id')
                if state in ('start', 'forwarded_from_me', ) or \
                   state == 'start_uuid' and response_from.get('created'):
                    a_response_to += [response_from, ]
        except:
            pass

    if user_from_id and state == 'start_uuid':
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

    if user_from_id and state == 'forwarded_from_other':
        logging.debug('get_or_create tg_user_forwarded data in api...')
        payload_to = dict(
            tg_token=settings.TOKEN,
            tg_uid=tg_user_forwarded.id,
            last_name=tg_user_forwarded.last_name or '',
            first_name=tg_user_forwarded.first_name or '',
            username=tg_user_forwarded.username or '',
            activate='',
        )
        try:
            status, response_to = await Misc.api_request(
                path='/api/profile',
                method='post',
                data=payload_to,
            )
            logging.debug('get_or_create tg_user_forwarded data in api, status: %s' % status)
            logging.debug('get_or_create get tg_user_forwarded data in api, response_to: %s' % response_to)
            if status == 200:
                response_to.update(tg_username=tg_user_forwarded.username)
                a_response_to = [response_to, ]
        except:
            pass

    if user_from_id and state in ('forwarded_from_other', 'forwarded_from_me'):
        usernames, text_stripped = Misc.get_text_usernames(message_text)
        if usernames:
            logging.debug('@usernames found in message text\n')
            payload_username = dict(
                tg_username=','.join(usernames),
            )
            status, response = await Misc.api_request(
                path='/api/profile',
                method='get',
                params=payload_username,
            )
            logging.debug('get by username, status: %s' % status)
            logging.debug('get by username, response: %s' % response)
            if status == 200 and response:
                a_response_to += response


    if state and state not in ('not_found', 'invalid_message_text',) and user_from_id and a_response_to:
        message_to_forward_id = state == 'forwarded_from_other' and message.message_id or ''

        await Misc.show_cards(
            a_response_to,
            message,
            bot_data,
            exclude_tg_uids=[],
            response_from=response_from,
            message_to_forward_id=message_to_forward_id,
        )

    elif reply:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if user_from_id and response_from.get('created'):
        tg_user_sender_photo = await Misc.get_user_photo(bot, tg_user_sender)
        if tg_user_sender_photo:
            await Misc.put_tg_user_photo(tg_user_sender_photo, response_from)

    if state == 'forwarded_from_other' and a_response_to and a_response_to[0].get('created'):
        tg_user_forwarded_photo = await Misc.get_user_photo(bot, tg_user_forwarded)
        if tg_user_forwarded_photo:
            await Misc.put_tg_user_photo(tg_user_forwarded_photo, response_to)


@dp.message_handler(
    ChatTypeFilter(chat_type=(types.ChatType.GROUP, types.ChatType.SUPERGROUP)),
    content_types=ContentType.all(),
)
async def echo_send_to_group(message: types.Message):
    """
    Обработка сообщений в группу

    При добавлении пользователя в группу:
        Карточка профиля:
            Имя Фамилия
            Доверий:
            Благодарностей:
            Недоверий:

            Возможности: водитель Камаз шашлык виноград курага изюм

            Потребности: не задано

            Местоположение: не задано/ссылка на карту

            Контакты:
            @username
            +3752975422568
            https://username.com

            От Вас: доверие
            К Вам: не знакомы
    Иначе:
        Имя Фамилия /ссылка/ (@username)

    Кнопки:
        Перейти
        Благодарность   Недоверие   Не знакомы
    """
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

    tg_user_sender = message.from_user
    a_users_in = [ message.from_user ]
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

    bot_data = await bot.get_me()
    if tg_user_left or tg_users_new:
        exclude_tg_uids = []
        is_previous_his = False
        last_user_in_group = None
    else:
        exclude_tg_uids = [str(tg_user_sender.id)]
        # Было ли предыдущее сообщение в группу отправлено этом пользователем?
        # Полезно, т.к. в сообщении из 10 фоток, а это 10 сообщений в бот,
        # надо бы только одну реакцию
        # Если сообщение о новом, убывшем пользователе, то любое следующее
        # сообщение будет как бы от нового пользователя
        #
        previous_user_in_group = last_user_in_group
        is_previous_his = True
        if previous_user_in_group != message.from_user.id:
            last_user_in_group = message.from_user.id
            is_previous_his = False

    for user_in in a_users_in:
        reply_markup = None
        payload_from = dict(
            tg_token=settings.TOKEN,
            tg_uid=user_in.id,
            last_name=user_in.last_name or '',
            first_name=user_in.first_name or '',
            username=user_in.username or '',
            activate='1',
        )
        try:
            status, response_from = await Misc.api_request(
                path='/api/profile',
                method='post',
                data=payload_from,
            )
            logging.debug('get_or_create tg_user_sender data in api, status: %s' % status)
            logging.debug('get_or_create tg_user_sender data in api, response_from: %s' % response_from)
            if status != 200:
                a_users_out.append({})
                continue
            a_users_out.append(response_from)
        except:
            a_users_out.append({})
            continue

        if tg_users_new and response_from.get('tg_uid') and str(tg_user_sender.id) != str(response_from['tg_uid']):
            # Сразу доверие добавляемому пользователю
            post_op = dict(
                tg_token=settings.TOKEN,
                operation_type_id=OperationType.TRUST,
                tg_user_id_from=tg_user_sender.id,
                user_id_to=response_from['user_id'],
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
            try:
                status, response_from = await Misc.api_request(
                    path='/api/profile',
                    method='post',
                    data=payload_from,
                )
                logging.debug('get_or_create tg_user_to data in api, status: %s' % status)
                logging.debug('get_or_create tg_user_to data in api, response_from: %s' % response_from)
                if status != 200:
                    continue
            except:
                continue

        if tg_user_left or tg_users_new:
            reply = Misc.reply_user_card(response_from, bot_data=bot_data)
        else:
            reply_template = '<b>%(full_name)s</b>'
            username = response_from.get('tg_username', '')
            if username:
                reply_template += ' ( @%(username)s )'
            reply = reply_template % dict(
                full_name=tg_user_sender.full_name,
                username=username,
            )

        if not is_previous_his:
            reply_markup = InlineKeyboardMarkup()
            path = "/profile/?id=%(uuid)s" % dict(uuid=response_from['uuid'],)

            url = settings.FRONTEND_HOST + path
            login_url = Misc.make_login_url(path)
            login_url = LoginUrl(url=login_url)
            inline_btn_go = InlineKeyboardButton(
                'Перейти',
                url=url,
                # login_url=login_url,
            )
            reply_markup.row(inline_btn_go)

            if response_from.get('tg_uid') and str(bot_data.id) != str(response_from['tg_uid']):
                dict_reply = dict(
                    keyboard_type=KeyboardType.TRUST_THANK_VER_2,
                    sep=KeyboardType.SEP,
                    user_to_id=response_from['user_id'],
                    message_to_forward_id='',
                    group_id=message.chat.id,
                )
                callback_data_template = (
                        '%(keyboard_type)s%(sep)s'
                        '%(operation)s%(sep)s'
                        '%(user_to_id)s%(sep)s'
                        '%(message_to_forward_id)s%(sep)s'
                        '%(group_id)s%(sep)s'
                    )
                dict_reply.update(operation=OperationType.TRUST_AND_THANK)
                inline_btn_thank = InlineKeyboardButton(
                    'Благодарю',
                    callback_data=callback_data_template % dict_reply,
                )
                dict_reply.update(operation=OperationType.MISTRUST)
                inline_btn_mistrust = InlineKeyboardButton(
                    'Не доверяю',
                    callback_data=callback_data_template % dict_reply,
                )
                reply_markup.row(
                    inline_btn_thank,
                    inline_btn_mistrust,
                )

            await message.answer(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if not (tg_user_left or tg_users_new):
        # Найдем @usernames в сообщении
        #
        message_text = getattr(message, 'text', '') and message.text.strip() or ''
        if message_text:
            usernames, text_stripped = Misc.get_text_usernames(message.text)
            if usernames:
                logging.debug('@usernames found in message text\n')
                payload_username = dict(
                    tg_username=','.join(usernames),
                )
                status, a_response_to = await Misc.api_request(
                    path='/api/profile',
                    method='get',
                    params=payload_username,
                )
                logging.debug('get by username, status: %s' % status)
                logging.debug('get by username, response: %s' % a_response_to)
                if status == 200 and a_response_to:
                    await Misc.show_cards(
                        a_response_to,
                        message,
                        bot_data,
                        exclude_tg_uids=exclude_tg_uids,
                        response_from={},
                        message_to_forward_id='',
                        group_id=message.chat.id,
                    )

    for i, response_from in enumerate(a_users_out):
        if response_from.get('created'):
            tg_user = a_users_in[i]
            tg_user_photo = await Misc.get_user_photo(bot, tg_user)
            if tg_user_photo:
                await Misc.put_tg_user_photo(tg_user_photo, response_from)

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
