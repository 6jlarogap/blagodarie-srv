import base64, re, hashlib, redis, time, tempfile
from io import BytesIO
from urllib.parse import urlparse

import settings
from settings import logging
from utils import Misc, Attitude, OperationType, KeyboardType, TgGroup, TgGroupMember

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import ChatTypeFilter, Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_polling, start_webhook
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import ChatNotFound, CantInitiateConversation, CantTalkWithBots, \
    BadRequest, MessageNotModified, MessageCantBeDeleted, MessageToEditNotFound
from aiogram.types.message_entity import MessageEntityType
from aiogram.bot.api import TelegramAPIServer

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from youtube_upload import upload_video

import pymorphy2
MorphAnalyzer = pymorphy2.MorphAnalyzer()

storage = MemoryStorage()

class FSMability(StatesGroup):
    ask = State()

class FSMwish(StatesGroup):
    ask = State()

class FSMnewIOF(StatesGroup):
    ask = State()
    ask_gender = State()

class FSMnewOrg(StatesGroup):
    ask = State()

class FSMcomment(StatesGroup):
    ask = State()

class FSMexistingIOF(StatesGroup):
    ask = State()

class FSMgender(StatesGroup):
    ask = State()

class FSMdates(StatesGroup):
    dob = State()
    dod = State()

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

class FSMbroSis(StatesGroup):
    ask = State()
    new = State()

class FSMsendMessage(StatesGroup):
    ask = State()

class FSMsendMessageToOffer(StatesGroup):
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

class FSMinviteConfirm(StatesGroup):
    # приглашение с объединением собственного
    ask = State()

kwargs_bot_start = dict(
    token=settings.TOKEN,
    parse_mode=types.ParseMode.HTML,
)
if settings.LOCAL_SERVER:
    local_server = TelegramAPIServer.from_base(settings.LOCAL_SERVER)
    kwargs_bot_start.update(server=local_server)
bot = Bot(**kwargs_bot_start)

dp = Dispatcher(bot, storage=storage)

async def on_startup(dp):
    if settings.START_MODE == 'webhook':
        await bot.set_webhook(settings.WEBHOOK_URL)


async def on_shutdown(dp):
    logging.warning('Shutting down..')
    if settings.START_MODE == 'webhook':
        await bot.delete_webhook()

# --- commands ----

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('map', 'карта'),
    state=None,
)
async def process_command_map(message: types.Message, state: FSMContext):
    await bot.send_message(
        message.from_user.id,
        text=Misc.get_html_a(href=settings.MAP_HOST, text='Карта участников'),
        disable_web_page_preview=True,
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('setvozm', 'возможности', ),
    state=None,
)
async def process_command_ability(message: types.Message, state: FSMContext):
    await do_process_ability(message)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('poll',),
    state=None,
)
async def process_command_poll(message: types.Message, state: FSMContext):
    err_mes = ''
    options = []
    for i, l in enumerate(message.text.split('\n')):
        line = l.strip()
        if not line:
            continue
        if i == 0:
            m = re.search(r'^\/poll\s+(.*)$', line)
            if not m or not m.group(1):
                err_mes = 'Не указан вопрос опроса'
                break
            question = m.group(1)
        else:
            for o in options:
                if line == o:
                    err_mes = 'Обнаружен повтор вопроса'
                    break
            if err_mes:
                break
            options.append(line)
    if not err_mes:
        if not options:
            err_mes = 'Не указаны ответы'
        elif len(options) > 10:
            err_mes = 'Вопросов может быть не больше 10'
    if err_mes:
        await message.reply(
            text='%s\n\n%s' % (
                err_mes,
                'Поручить боту создать неанонимный опрос:\n'
                '/poll Вопрос\n'
                'Ответ 1\n'
                'Ответ 2\n'
                ' и т.д. не больше 10 ответов'
            ))
        return
    poll_message = await bot.send_poll(
        chat_id=message.chat.id,
        question=question,
        options=options,
        is_anonymous=False
    )
    poll_message_dict = dict(poll_message)
    poll_message_dict.update(tg_token=settings.TOKEN)
    logging.debug('create poll in api, payload: %s' % Misc.secret(poll_message_dict))
    status, response = await Misc.api_request(
        path='/api/bot/poll',
        method='post',
        json=poll_message_dict,
    )
    logging.debug('create poll in api, status: %s' % status)
    logging.debug('create poll in api, response: %s' % response)
    if status == 200:
        await message.reply(
            'Опрос успешно сохранен. Ниже ссылка об опросе. Можете ею поделиться:',
            disable_web_page_preview=True,
        )
        bot_data = await bot.get_me()
        await bot.send_message(
            message.from_user.id,
            text='Опрос:\n' + Misc.get_html_a(
                href='t.me/%s?start=poll-%s' % (bot_data['username'], poll_message_dict['poll']['id'],),
                text=poll_message_dict['poll']['question']
            ),
            disable_web_page_preview=True,
        )
    else:
        await message.reply('Ошибка сохранения опроса', disable_web_page_preview=True,)


@dp.message_handler(
    ChatTypeFilter(chat_type=(types.ChatType.PRIVATE,)),
    commands=('offer', 'offer_multi'),
    state=None,
)
async def process_command_offer(message: types.Message, state: FSMContext):
    """
    Создание опроса- предложения из сообщения- команды

    offer:          опрос c выбором лишь одного ответа
    offer_multi:    опрос с возможным выбором нескольких ответов
    """
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        answers = []
        err_mes = ''
        for i, l in enumerate(message.text.split('\n')):
            line = l.strip()
            if not line:
                continue
            if i == 0:
                m = re.search(r'^\/(offer|offer_multi)\s+(.*)$', line, flags=re.I)
                if not m or not m.group(2):
                    err_mes = 'Не указан вопрос опроса'
                    break
                question = m.group(2)
                is_multi = m.group(1).lower() == 'offer_multi'
            else:
                for a in answers:
                    if line == a:
                        err_mes = 'Обнаружен повтор ответа'
                        break
                if err_mes:
                    break
                answers.append(line)
        if not err_mes:
            if not answers:
                err_mes = 'Не указаны ответы'
            elif len(answers) == 1:
                err_mes = 'Опрос из одного ответа? Так нельзя'
            elif len(answers) > settings.OFFER_MAX_NUM_ANSWERS:
                err_mes = 'Превышен максимум числа ответов (до %s)' % settings.OFFER_MAX_NUM_ANSWERS
        if err_mes:
            help_mes = (
                '%(err_mes)s\n\n'
                'Поручить боту создать опрос-предложение:\n'
                '\n'
                '/offer Вопрос\n'
                '<i>или</i>\n'
                '/offer_multi Вопрос\n'
                'Ответ 1\n'
                'Ответ 2\n'
                ' и т.д. не больше %(offer_max_num_answers)s ответов\n'
                '\n'
                '/offer: опрос c выбором лишь одного ответа\n'
                '/offer_multi: опрос с возможным выбором нескольких ответов\n'
            )
            await message.reply(help_mes % dict(
                err_mes=err_mes,
                offer_max_num_answers=settings.OFFER_MAX_NUM_ANSWERS
            ))
            return

        create_offer_dict = dict(
            tg_token=settings.TOKEN,
            user_uuid=response_sender['uuid'],
            question=question,
            answers=answers,
            is_multi=is_multi,
        )
        logging.debug('create offer in api, payload: %s' % Misc.secret(create_offer_dict))
        status, response = await Misc.api_request(
            path='/api/offer',
            method='post',
            json=create_offer_dict,
        )
        logging.debug('create offer in api, status: %s' % status)
        logging.debug('create offer in api, response: %s' % response)
        if status == 400 and response.get('message'):
            err_mes = response['message']
        elif status != 200:
            err_mes = 'Ошибка сохранения опроса-предложения'
        if err_mes:
            await message.reply(err_mes, disable_web_page_preview=True,)
            return
        await message.reply('Создан опрос:', disable_web_page_preview=True,)
        bot_data = await bot.get_me()
        await show_offer(response_sender, response, message, bot_data)

        if response_sender.get('created'):
            await Misc.update_user_photo(bot, message.from_user, response_sender)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('setpotr', 'потребности',),
    state=None,
)
async def process_command_wish(message: types.Message, state: FSMContext):
    await do_process_wish(message)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('new', 'new_person',),
    state=None,
)
async def process_command_new_person(message: types.Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        if not Misc.editable(response_sender):
            return
        await FSMnewIOF.ask.set()
        state = dp.current_state()
        await message.reply(Misc.PROMPT_NEW_IOF, reply_markup=Misc.reply_markup_cancel_row())
        if response_sender.get('created'):
            await Misc.update_user_photo(bot, message.from_user, response_sender)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('new_org',),
    state=None,
)
async def process_command_new_org(message: types.Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        if not Misc.editable(response_sender):
            return
        await FSMnewOrg.ask.set()
        state = dp.current_state()
        await message.reply(Misc.PROMPT_NEW_ORG, reply_markup=Misc.reply_markup_cancel_row())
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
        if not Misc.editable(response_sender):
            return
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
    commands=('setplace', 'место',),
    state=None,
)
async def geo_command_handler(message: types.Message, state: FSMContext):
    await geo(message, state_to_set=FSMgeo.geo)


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


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('getowned', 'listown',),
    state=None,
)
async def echo_getowned_to_bot(message: types.Message, state: FSMContext):
    tg_user_sender = message.from_user
    status, response_from = await Misc.post_tg_user(tg_user_sender)
    if status == 200:
        if not Misc.editable(response_from):
            return
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
    commands=('graph',),
    state=None,
)
async def echo_graph_to_bot(message: types.Message, state: FSMContext):
    bot_data = await bot.get_me()
    reply_markup = InlineKeyboardMarkup()
    inline_btn_all_users = InlineKeyboardButton(
        'Отношения участников',
        login_url=Misc.make_login_url(
            redirect_path=settings.GRAPH_HOST + '/?rod=on&dover=on&withalone=on',
            bot_username=bot_data["username"],
            keep_user_data='on'
    ))
    inline_btn_recent = InlineKeyboardButton(
        'Недавно добавленные',
        login_url=Misc.make_login_url(
            redirect_path=settings.GRAPH_HOST + '/?f=0&q=50',
            bot_username=bot_data["username"],
            keep_user_data='on'
    ))
    reply_markup.row(inline_btn_all_users)
    reply_markup.row(inline_btn_recent)
    await message.reply(
        'Выберите тип графика',
        disable_web_page_preview=True,
        reply_markup=reply_markup
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('help',),
    state=None,
)
async def echo_help_to_bot(message: types.Message, state: FSMContext):
    await message.reply(await Misc.help_text(), disable_web_page_preview=True)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('meet', 'trust', 'thank',),
    state=None,
)
async def echo_meet(message: types.Message, state: FSMContext):
    command = message.text.strip('/').strip().lower()
    status, profile = await Misc.post_tg_user(message.from_user)
    command_to_data = dict(
        meet= dict(prefix='m',  caption='Знакомьтесь: %(link)s'),
        trust=dict(prefix='t',  caption='Доверяю %(link)s'),
        thank=dict(prefix='th', caption='Благодарить %(link)s'),
    )
    if status == 200:
        bot_data = await bot.get_me()
        url = (
            f'https://t.me/{bot_data["username"]}'
            f'?start={command_to_data[command]["prefix"]}-{profile["username"]}'
        )
        link = f'<a href="{url}">{profile["first_name"]}</a>'
        caption = command_to_data[command]["caption"] % dict(link=link)
        bytes_io = await Misc.get_qrcode(profile, url)
        await bot.send_photo(
            chat_id=message.from_user.id,
            photo=bytes_io,
            caption=caption,
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('quit',),
    state=None,
)
async def anonymize(message: types.Message, state: FSMContext):
    status, profile = await Misc.post_tg_user(message.from_user)
    if status == 200:
        if not profile['is_active']:
            await message.reply('Вы уже обезличены', disable_web_page_preview=True, disable_notification=True)
            return
        owner = profile
        await do_confirm_delete_profile(message, profile, owner)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('stat',),
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
            f'Пользователи: {response["active"]}\n'
            f'Стартовали бот: {response["did_bot_start"]}\n'
            f'Указали местоположение: {response["with_geodata"]}\n'
            f'Cозданные профили: {response["owned"]}\n'
            f'Всего профилей: {response["active"] + response["owned"]}\n'
            f'Родственных связей: {response["relations"]}\n'
            f'Доверий: {response["trusts"]}\n'
            f'Недоверий: {response["mistrusts"]}\n'
            f'Знакомств: {response["acqs"]}\n'
        )
    else:
        reply = 'Произошла ошибка'
    await message.answer(reply)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('feedback',),
    state=None,
)
async def echo_feedback(message: types.Message, state: FSMContext):
    await message.reply(
        Misc.get_html_a(settings.BOT_CHAT['href'], settings.BOT_CHAT['caption']),
        disable_web_page_preview=True,
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    commands=('feedback_admins',),
    state=None,
)
async def echo_feedback_admins(message: types.Message, state: FSMContext):
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
    ChatTypeFilter(chat_type=(types.ChatType.GROUP, types.ChatType.SUPERGROUP)),
    commands=('service_get_group_id',),
    state=None,
)
async def service_get_group_id(message: types.Message, state: FSMContext):
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

@dp.message_handler(
    ChatTypeFilter(chat_type=(types.ChatType.GROUP, types.ChatType.SUPERGROUP, types.ChatType.CHANNEL)),
    commands=('service_add_user_to_chat',),
    state=None,
)
async def service_add_user_to_chat(message: types.Message, state: FSMContext):
    if not message.from_user.is_bot:
        chat = message.chat
        try:
            await message.delete()
        except:
            pass
        status_sender, response_sender = await Misc.post_tg_user(message.from_user)
        if status_sender != 200:
            return
        m = re.search(r'\/\w+\s+(\S+)', message.text)
        if m:
            user_uuid = Misc.uuid_from_text(m.group(0))
        msg_invalid_input = (
            'Неверный запрос в команду /service_add_user_to_chat в группе/канале '
            f'{chat.title}.\n'
            'Ожидалось /service_add_user_to_chat <i>user_uuid</i>'
        )
        if not m or not user_uuid:
            try:
                await bot.send_message(message.from_user.id, msg_invalid_input)
            except (ChatNotFound, CantInitiateConversation):
                pass
            return
        status_user, response_user = await Misc.get_user_by_uuid(uuid=user_uuid)
        tg_uid = response_user['tg_data'] and response_user['tg_data'][0]['tg_uid'] or None
        if status_user != 200 or not tg_uid:
            try:
                await bot.send_message(message.from_user.id,
                    (
                    'Неверный запрос в команду /service_add_user_to_chat в группе '
                    f'{chat.title}.\n\n'
                    'Пользователь не найден или не в телеграме'
                ))
            except (ChatNotFound, CantInitiateConversation):
                pass
            return
        status, response_add_member = await TgGroupMember.add(
            group_chat_id=chat.id,
            group_title='',
            group_type='',
            user_tg_uid=tg_uid,
        )
        if status_user != 200:
            try:
                await bot.send_message(message.from_user.id,
                    (
                    f'Не удалось добавить {response_user["first_name"]} '
                    f'в группу/канал {chat.title} в апи'
                ))
            except (ChatNotFound, CantInitiateConversation):
                pass
            return

        try:
            await bot.approve_chat_join_request(
                    chat.id,
                    tg_uid
            )
        except BadRequest as excpt:
            already = False
            try:
                if excpt.args[0] == 'User_already_participant':
                    already = True
            except:
                pass
            try:
                await bot.send_message(message.from_user.id,
                    f'Пользователь уже в телеграм группе/канале {chat.title}' if already \
                    else f'Не удалось подтвердить завку на подключение в группу/канал',
                )
            except (ChatNotFound, CantInitiateConversation):
                pass
            return

        post_op = dict(
            tg_token=settings.TOKEN,
            operation_type_id=OperationType.TRUST,
            tg_user_id_from=tg_uid,
            user_id_to=response_sender['uuid'],
        )
        logging.debug('post operation (chat subscriber thanks inviter), payload: %s' % Misc.secret(post_op))
        status_op, response_op = await Misc.api_request(
            path='/api/addoperation',
            method='post',
            data=post_op,
        )
        logging.debug('post operation (chat subscriber thanks inviter), status: %s' % status_op)
        logging.debug('post operation (chat subscriber thanks inviter), response: %s' % response_op)
        try:
            await bot.send_message(message.from_user.id,
                f'{response_user["first_name"]} подключен к телеграм группе/каналу {chat.title}'
            )
        except (ChatNotFound, CantInitiateConversation):
            pass
        return


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=None,
)
async def echo_send_to_bot(message: types.Message, state: FSMContext):
    """
    Обработка сообщений в бот при state==None, включая команду /start
    """

    # В пересылаемых и других сообщениях могут быть много сообщений.
    # Чтоб ответ по ним не плодил дубли
    #
    show_response = True
    if getattr(message, 'media_group_id', None):
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

    tg_user_sender = message.from_user
    reply = ''
    if tg_user_sender.is_bot:
        reply = 'Сообщения от ботов пока не обрабатываются'
    elif message.content_type == ContentType.PINNED_MESSAGE:
        return
    elif not message.is_forward() and message.content_type != ContentType.TEXT:
        reply = 'Сюда можно слать текст для поиска, включая @username, или пересылать сообщения любого типа'
    if reply and show_response:
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

    # Чью карточку будут показывать?
    profile_card = {}

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

        elif m := re.search(
                r'^\/start\s+setplace$',
                message_text,
                flags=re.I,
          ):
            state_ = 'start_setplace'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=setplace'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            state_ = 'start_setplace'

        elif m := re.search(
                r'^\/start\s+(t|m|th)\-([0-9a-z]{10})$',
                message_text,
                flags=re.I,
          ):
            d_trust = dict(
                operation_type_id=OperationType.start_prefix_to_op(m.group(1).lower()),
                sid=m.group(2)
            )
            state_ = 'start_trust'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=(t|m|th)\-([0-9a-z]{10})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            d_trust = dict(
                operation_type_id=OperationType.start_prefix_to_op(m.group(1).lower()),
                sid=m.group(2)
            )
            state_ = 'start_trust'

        elif m := re.search(
                r'^\/start\s+offer\-([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$',
                message_text,
                flags=re.I,
          ):
            offer_to_search = m.group(1).lower()
            state_ = 'start_offer'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=offer\-'
                    '([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            offer_to_search = m.group(1).lower()
            state_ = 'start_offer'

        elif m := re.search(
                r'^\/start\s+invite\-([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$',
                message_text,
                flags=re.I,
          ):
            token_invite = m.group(1).lower()
            state_ = 'start_invite'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=invite\-'
                    '([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            token_invite = m.group(1).lower()
            state_ = 'start_invite'

        elif m := re.search(
                r'^\/start\s+([0-9a-z]{10})$',
                message_text,
                flags=re.I,
          ):
            sid_to_search = m.group(1)
            state_ = 'start_sid'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=([0-9a-z]{10})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            sid_to_search = m.group(1)
            state_ = 'start_sid'

        elif m := re.search(
                r'^\/start\s+([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$',
                message_text,
                flags=re.I,
          ):
            uuid_to_search = m.group(1).lower()
            state_ = 'start_uuid'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\='
                    '([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            uuid_to_search = m.group(1).lower()
            state_ = 'start_uuid'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=poll\-'
                    '(\d{3,})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            # https://t.me/doverabot?start=poll
            poll_to_search = m.group(1)
            state_ = 'start_poll'
        elif m := re.search(
                r'^\/start\s+poll\-(\d{3,})$',
                message_text,
                flags=re.I,
          ):
            # /start poll:
            poll_to_search = m.group(1)
            state_ = 'start_poll'

        elif m := re.search(
                (
                    r'^(?:https?\:\/\/)?t\.me\/%s\?start\=auth_redirect\-'
                    '([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$'
                ) % re.escape(bot_data['username']),
                message_text,
                flags=re.I,
          ):
            # /start auth_redirect-<token, в котором зашит url для авторизации>
            redirect_token = m.group(1)
            state_ = 'start_auth_redirect'
        elif m := re.search(
                (
                r'^\/start\s+auth_redirect\-'
                    '([0-9a-f]{8}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{4}\-[0-9a-f]{12})$'
                ),
                message_text,
                flags=re.I,
          ):
            # /start auth_redirect-<token, в котором зашит url для авторизации>
            redirect_token = m.group(1)
            state_ = 'start_auth_redirect'

        elif m := Misc.get_youtube_id(message_text):
            youtube_id, youtube_link = m
            state_ = 'youtube_link'

        elif len(message_text) < settings.MIN_LEN_SEARCHED_TEXT:
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
               state_ in (
                    'start_uuid', 'start_sid', 'start_setplace', 'start_poll',
                    'start_offer', 'start_auth_redirect',
               ) and response_from.get('created'):
                profile_card = response_from

    if user_from_id and state_ == 'start_sid':
        logging.debug('get tg_user_by_start_sid data in api...')
        try:
            status, response_uuid = await Misc.get_user_by_sid(sid=sid_to_search)
            if status == 200:
                profile_card = response_uuid
            else:
                reply = Misc.MSG_USER_NOT_FOUND
        except:
            pass

    if user_from_id and state_ == 'start_uuid':
        logging.debug('get tg_user_by_start_uuid data in api...')
        try:
            status, response_uuid = await Misc.get_user_by_uuid(uuid=uuid_to_search)
            if status == 200:
                profile_card = response_uuid
            else:
                reply = Misc.MSG_USER_NOT_FOUND
        except:
            pass

    if user_from_id and state_ == 'forwarded_from_other':
        status, response_to = await Misc.post_tg_user(tg_user_forwarded)
        if status == 200:
            response_to.update(tg_username=tg_user_forwarded.username)
            if show_response:
                profile_card = response_to

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


    if state_ and state_ not in (
        'not_found', 'invalid_message_text',
        'start_setplace', 'start_poll',
        'start_offer', 'start_trust', 'start_auth_redirect',
        'youtube_link', 'start_invite'
       ) and user_from_id and profile_card:
        if state_ == 'start':
            await message.reply(await Misc.help_text(), disable_web_page_preview=True)
            if not profile_card.get('photo'):
                status_photo, response_photo = await Misc.update_user_photo(bot, tg_user_sender, response_from)
                if response_photo:
                    response_from = response_photo
                    profile_card = response_photo
        message_to_forward_id = state_ == 'forwarded_from_other' and message.message_id or ''
        if show_response:
            await Misc.show_card(
                profile_card,
                bot,
                response_from=response_from,
                tg_user_from=message.from_user,
                message_to_forward_id=message_to_forward_id,
            )

    elif reply and show_response:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True)

    if state_ not in (
        'start_setplace', 'start_poll', 'start_offer', 'start_auth_redirect', 'start_trust', 'youtube_link',
       ):
        await Misc.show_deeplinks(a_found, message, bot_data)

    if user_from_id:
        if response_from.get('created') and state_ != 'start':
            await Misc.update_user_photo(bot, tg_user_sender, response_from)
            # Будем показывать карточку нового юзера в таких случаях?
            #if profile_card and state_ in ('start_setplace', 'start_poll', 'start_offer', ):
                #await Misc.show_card(
                    #profile_card,
                    #bot,
                    #response_from=response_from,
                    #tg_user_from=message.from_user,
                #)
        if state_ == 'start_setplace':
            await geo(message, state_to_set=FSMgeo.geo)
        elif state_ == 'start_auth_redirect':
            status_token, response_token = await Misc.api_request(
                path='/api/token/url/',
                params=dict(token=redirect_token)
            )
            if status_token == 200:
                redirect_path = response_token['url']
                reply_markup = InlineKeyboardMarkup()
                inline_btn_redirect = InlineKeyboardButton(
                    'Продолжить',
                    login_url=Misc.make_login_url(
                        redirect_path=redirect_path,
                        bot_sername=bot_data['username'],
                        keep_user_data='on'
                    ),
                )
                reply_markup.row(inline_btn_redirect)
                if redirect_path.lower().startswith(settings.VOTE_URL):
                    if m := re.search(r'\#(\S+)$', redirect_path):
                        if m := Misc.get_youtube_id(m.group(1)):
                            youtube_id, youtube_link = m
                            await answer_youtube_message(message, youtube_id, youtube_link)
                            return
                auth_url_parse = urlparse(redirect_path)
                auth_text = ''
                if auth_url_parse.hostname:
                    for auth_domain in settings.AUTH_PROMPT_FOR_DOMAIN:
                        if re.search(re.escape(auth_domain) + '$', auth_url_parse.hostname):
                            auth_text = settings.AUTH_PROMPT_FOR_DOMAIN[auth_domain]
                            break
                redirect_path_new = redirect_path
                if not auth_text:
                    # Чтобы телеграм не предлагал ссылку, берется после последнего http(s)://,
                    # впереди ставится троеточие
                    #
                    if m:=re.search(r'(?:https?\:\/\/)?([^\:\#]+)$', redirect_path):
                        redirect_path_new = '...' + m.group(1)
                    auth_text = f'Нажмите <u>Продолжить</u> для доступа к:\n{redirect_path_new}'
                await message.reply(
                    auth_text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            else:
                await message.reply('Ссылка устарела или не найдена. Получите новую.')
        elif state_ == 'start_poll':
            params = dict(tg_token=settings.TOKEN, tg_poll_id=poll_to_search)
            logging.debug('get_poll, params: %s' % params)
            status_poll, response_poll = await Misc.api_request(
                path='/api/bot/poll/results',
                method='post',
                json=params,
            )
            logging.debug('get_poll, params, status: %s' % status_poll)
            logging.debug('get_poll, params, response: %s' % response_poll)
            if status_poll == 200:
                try:
                    await bot.forward_message(
                        tg_user_sender.id,
                        from_chat_id=response_poll['chat_id'],
                        message_id=response_poll['message_id'],
                    )
                except:
                    await message.reply('Не удалось отобразить опрос. Уже не действует?')
            else:
                await message.reply('Опрос не найден')
        elif state_ == 'start_offer':
            status_offer, response_offer = await post_offer_answer(offer_to_search, response_from, [-1])
            if status_offer == 200:
                await show_offer(response_from, response_offer, message, bot_data)
            else:
                await message.reply('Опрос-предложение не найдено')
        elif state_ == 'youtube_link':
            await answer_youtube_message(message, youtube_id, youtube_link)
        elif state_ == 'forwarded_from_other' and profile_card and profile_card.get('created'):
            await Misc.update_user_photo(bot, tg_user_forwarded, response_to)
        elif state_ == 'start_invite':
            await show_invite(response_from, token_invite, message, bot_data)
        elif state_ == 'start_trust':
            status_to, profile_to = await Misc.get_user_by_sid(d_trust['sid'])
            if status_to != 200:
                return
            data = dict(
                profile_from = response_from,
                profile_to = profile_to,
                operation_type_id = d_trust['operation_type_id'],
                tg_user_sender_id = tg_user_sender.id,
                message_to_forward_id = None,
                group_member=None,
                message_after_meet=bool(
                    d_trust['operation_type_id'] == OperationType.ACQ
            ))
            await put_thank_etc(tg_user_sender, data, state=state)
            return

# --- command list ----

commands_dict = {
    'map': process_command_map,
    'карта': process_command_map, 
    'setvozm': process_command_ability,
    'возможности': process_command_ability,
    'setpotr': process_command_wish,
    'потребности': process_command_wish,
    'findpotr': process_commands_query,
    'findvozm': process_commands_query,
    'findperson': process_commands_query,
    'setplace': geo_command_handler,
    'место': geo_command_handler,
    'poll': process_command_poll,
    'offer': process_command_offer,
    'poll': process_command_offer,
    'new': process_command_new_person,
    'new_person': process_command_new_person,
    'new_org': process_command_new_org,
    'trip': trip_geo_command_handler,
    'тур': trip_geo_command_handler,
    'getowned': echo_getowned_to_bot,
    'listown': echo_getowned_to_bot,
    'graph': echo_graph_to_bot,
    'help': echo_help_to_bot,
    'meet': echo_meet,
    'stat': echo_stat_to_bot,
    'feedback': echo_feedback,
    'feedback_admins': echo_feedback_admins,
    'quit': anonymize,
    'start': echo_send_to_bot,
    'ya': echo_send_to_bot,
}

async def is_it_command(message: types.Message, state: FSMContext, excepts=[]):
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
                    await state.finish()
                await message.reply('%s\n%s /%s' % (
                     Misc.MSG_YOU_CANCELLED_INPUT,
                     'Выполняю команду',
                     command
                ))
                result = True
                await commands_dict[command](message, state)
    return result


# --- end of commands ----

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
            if uuid and not await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid):
                return
        except IndexError:
            uuid = None
        await geo(callback_query.message, state_to_set=FSMgeo.geo, uuid=uuid)


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
    user_sid_to = Misc.sid_from_link(message.text)
    if not user_sid_to:
        if await is_it_command(message, state, excepts=('start',)):
            return
        async with state.proxy() as data:
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
                    prompt_new_parent,
                    callback_data= Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
                        keyboard_type=KeyboardType.NEW_FATHER if is_father else KeyboardType.NEW_MOTHER,
                        uuid=uuid,
                        sep=KeyboardType.SEP,
                ))
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(button_new_parent, Misc.inline_button_cancel())
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
    async with state.proxy() as data:
        if data.get('uuid'):
            user_uuid_from = data['uuid']
            is_father = data.get('is_father')
        data['uuid'] = data['is_father'] = ''
    if not user_uuid_from or not isinstance(is_father, bool):
        await Misc.state_finish(state)
        return
    response_sender = await Misc.check_owner_by_sid(owner_tg_user=message.from_user, sid=user_sid_to)
    if not response_sender:
        await Misc.state_finish(state)
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
    if await is_it_command(message, state):
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
    owner = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=user_uuid_from)
    if not owner or not owner.get('user_id'):
        await Misc.state_finish(state)
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
            await Misc.show_card(
                response,
                bot,
                response_from=owner,
                tg_user_from=message.from_user,
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
        response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid)
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
        code = callback_query.data.split(KeyboardType.SEP)
        uuid = None
        try:
            uuid = code[1]
        except IndexError:
            pass
        if not uuid:
            return
        tg_user_sender = callback_query.from_user
        response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid)
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    message = callback_query.message
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
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
        bot_data_username=bot_data['username'],
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
        'Новый сын',
        callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % data_new_child,
    )
    data_new_child.update(keyboard_type=KeyboardType.NEW_DAUGHTER)
    inline_btn_new_daughter = InlineKeyboardButton(
        'Новая дочь',
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
    if not (parent_uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    message = callback_query.message
    tg_user_sender = callback_query.from_user
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=parent_uuid)
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    message = callback_query.message
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
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


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMchild.choose,
)
async def choose_child_to_clear_link(message: types.Message, state: FSMContext):
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
    async with state.proxy() as data:
        if data.get('uuid') and data.get('parent_gender'):
            parent_uuid = data['uuid']
            response_sender = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=parent_uuid)
            if not response_sender:
                await Misc.state_finish(state)
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
async def put_child_by_sid(message: types.Message, state: FSMContext):
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
        async with state.proxy() as data:
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
                reply_markup = InlineKeyboardMarkup()
                reply_markup.row(inline_btn_new_son, inline_btn_new_daughter, Misc.inline_button_cancel())
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
    async with state.proxy() as data:
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
            else:
                # Не имеет права
                await message.reply((
                    'Нельзя назначать ребенка, если это активный пользователь или профиль, '
                    'которым владеете не Вы.\n\n'
                    'Назначайте ребёнка по новой'
                ))
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMchild.new,
)
async def put_new_child(message: types.Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    async with state.proxy() as data:
        if data.get('uuid') and data.get('parent_gender') and data.get('new_child_gender'):
            if message.content_type != ContentType.TEXT:
                await message.reply(
                    Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
                    reply_markup=Misc.reply_markup_cancel_row()
                )
                return
            first_name = Misc.strip_text(message.text)
            if not first_name or re.search(Misc.RE_UUID, first_name):
                await message.reply(
                    Misc.PROMPT_IOF_INCORRECT,
                    reply_markup=Misc.reply_markup_cancel_row(),
                )
                return
            response_sender = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=data['uuid'])
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
                    link_id=data['uuid'],
                    link_relation='link_is_father' if data['parent_gender'] == 'm' else 'link_is_mother',
                    owner_id=response_sender['user_id'],
                    gender=data['new_child_gender']
                )
                logging.debug('post new child, payload: %s' % Misc.secret(post_new_link))
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
                            'Ошибка!\n%s\n\nНазначайте ребёнка по новой' % response_child['message']
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
                        await Misc.show_card(
                            response_child,
                            bot,
                            response_from=response_sender,
                            tg_user_from=message.from_user,
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
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
        response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid)
        if not response_sender:
            await Misc.state_finish(state)
            return
        async with state.proxy() as data:
            data['uuid'] = uuid
            data['name'] = response_sender['response_uuid']['first_name']
            data['parent_gender'] = 'm' if code[0] == str(KeyboardType.FATHER_OF_CHILD) else 'f'
            await ask_child(callback_query.message, state, data, children=response_sender['response_uuid']['children'])


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.NEW_SON, KeyboardType.NEW_DAUGHTER,
        KeyboardType.SEP,
    ), c.data),
    state = FSMchild.ask,
    )
async def process_callback_new_child_gender(callback_query: types.CallbackQuery, state: FSMContext):
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    async with state.proxy() as data:
        for key in ('name', 'uuid', 'parent_gender',):
            if not data.get(key) or key == 'uuid' and data[key] != uuid:
                await Misc.state_finish(state)
                return
        data['new_child_gender'] = 'm' \
            if callback_query.data.split(KeyboardType.SEP)[0] == str(KeyboardType.NEW_SON) \
            else 'f'
        await FSMchild.new.set()
        await callback_query.message.reply(
            (
                f'Укажите ФИО {"СЫНА" if data["new_child_gender"] == "m" else "ДОЧЕРИ"} для:\n'
                f'{data["name"]}\nНапример, "Иван Иванович Иванов"'
            ),
            reply_markup=Misc.reply_markup_cancel_row(),
        )


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.BRO_SIS,
        KeyboardType.SEP,
        # uuid человека из карточки          # 1
        # KeyboardType.SEP,
    ), c.data),
    state = None,
    )
async def process_callback_bro_sis(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Действия по заданию брата или сестры
    """
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
    if not response_sender:
        return
    response_uuid = response_sender['response_uuid']
    if not (response_uuid.get('father') or response_uuid.get('mother')):
        return
    state = dp.current_state()
    reply_markup = None
    async with state.proxy() as data:
        data['uuid'] = uuid
        bot_data = await bot.get_me()
        prompt_bro_sis = (
            '<b>%(name)s</b>.\n'
            'Отправьте мне <u><b>ссылку на профиль %(his_her)s брата или сестры</b></u> '
            'вида t.me/%(bot_data_username)s?start=...\n'
            '\n'
            'Или нажмите <b><u>Новый брат</u></b> или <b><u>Новая сестра</u></b> для ввода нового родственника, '
            'который станет %(his_her)s братом или сестрой; родители брата (сестры):\n'
        )
        prompt_bro_sis = prompt_bro_sis % dict(
            bot_data_username=bot_data['username'],
            name=response_uuid['first_name'],
            his_her=Misc.his_her(response_uuid),
        )
        if response_uuid.get('father'):
            prompt_bro_sis += f'папа: {response_uuid["father"]["first_name"]}\n'
        if response_uuid.get('mother'):
            prompt_bro_sis += f'мама: {response_uuid["mother"]["first_name"]}\n'

        new_bro_sis_dict = dict(
            keyboard_type=KeyboardType.NEW_BRO,
            uuid=data['uuid'],
            sep=KeyboardType.SEP,
        )
        inline_btn_new_bro = InlineKeyboardButton(
            'Новый брат',
            callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % new_bro_sis_dict,
        )
        new_bro_sis_dict.update(keyboard_type=KeyboardType.NEW_SIS)
        inline_btn_new_sis = InlineKeyboardButton(
            'Новая сестра',
            callback_data=Misc.CALLBACK_DATA_UUID_TEMPLATE % new_bro_sis_dict,
        )
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_new_bro, inline_btn_new_sis, Misc.inline_button_cancel())
        await FSMbroSis.ask.set()
        await callback_query.message.reply(
            prompt_bro_sis,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMbroSis.ask,
)
async def put_bro_sys_by_uuid(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    sid_bro_sis = Misc.sid_from_link(message.text)
    if not sid_bro_sis:
        if await is_it_command(message, state, excepts=('start',)):
            return
        async with state.proxy() as data:
            await message.reply(
                Misc.MSG_INVALID_LINK + '\nПовторите, пожалуйста' ,
                reply_markup=Misc.reply_markup_cancel_row()
            )
        return
    async with state.proxy() as data:
        if data.get('uuid'):
            uuid_whose = data['uuid']
            response_whose = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=uuid_whose)
            response_bro_sis = await Misc.check_owner_by_sid(owner_tg_user=message.from_user, sid=sid_bro_sis)
            if response_whose and response_bro_sis:
                data_whose = response_whose['response_uuid']
                data_bro_sis = response_bro_sis['response_uuid']
                bot_data = await bot.get_me()
                dl_whose = Misc.get_deeplink_with_name(data_whose, bot_data)
                dl_bro_sis = Misc.get_deeplink_with_name(data_bro_sis, bot_data)
                if data_whose['uuid'] == data_bro_sis['uuid']:
                    await message.reply((
                        'Нельзя назначать брата или сестру между '
                        'одним и тем человеком.\n\n'
                        'Назначайте брата или сестру по новой'
                    ))
                elif not data_whose.get('father') and not data_whose.get('mother'):
                    await message.reply((
                        f'Назначить брата/сестру для {dl_whose} - это задать для {dl_bro_sis} родителей {dl_whose}. '
                        f'Но у {dl_whose} не заданы родители!\n\n'
                        f'Назначайте брата или сестру по новой'
                    ))
                elif data_bro_sis.get('father') or data_bro_sis.get('mother'):
                    await message.reply((
                        f'Назначить брата/сестру для {dl_whose} - это задать для {dl_bro_sis} родителей {dl_whose}. '
                        f'Но у {dl_bro_sis} уже задан папа и/или мама!\n\n'
                        f'Не исключено, что Вы ошиблись.\n'
                        f'Назначайте брата или сестру по новой или задавайте папу/маму для {dl_bro_sis}'
                    ))
                else:
                    is_father_set = is_mother_set = False
                    if data_whose.get('father'):
                        post_op = dict(
                            tg_token=settings.TOKEN,
                            operation_type_id=OperationType.SET_FATHER,
                            user_id_from=data_bro_sis['uuid'],
                            user_id_to=data_whose['father']['uuid'],
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
                                await message.reply((
                                    f'Ошибка назначения папы для {dl_bro_sis}!\n'
                                    f'{response["message"]}\n\n'
                                    f'Назначайте брата/сестру по новой'
                                ))
                            else:
                                await message.reply(Misc.MSG_ERROR_API + '\nНазначайте брата/сестру по новой')
                        else:
                            is_father_set = True
                    if (data_whose.get('father') and is_father_set or not data_whose.get('father')) and \
                       data_whose.get('mother'):
                        post_op = dict(
                            tg_token=settings.TOKEN,
                            operation_type_id=OperationType.SET_MOTHER,
                            user_id_from=data_bro_sis['uuid'],
                            user_id_to=data_whose['mother']['uuid'],
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
                                    f'Ошибка назначения мамы для {dl_bro_sis}!\n' + \
                                    f'{response["message"]}\n\n' + \
                                    '' if is_father_set else 'Назначайте брата/сестру по новой' 
                                )
                            else:
                                await message.reply(
                                    Misc.MSG_ERROR_API + \
                                    '\nпри назначении мамы для ' + dl_bro_sis + \
                                    '' if is_father_set else '\nНазначайте брата/сестру по новой'
                                )
                        else:
                            is_mother_set = True
                    if is_father_set or data_whose.get('mother') and is_mother_set:
                        status, response = await Misc.get_user_by_uuid(uuid=data_bro_sis['uuid'])
                        if status == 200:
                            await message.reply(f'{dl_bro_sis} имеет тех же родителей, что и {dl_whose}')
                            await Misc.show_card(
                                response,
                                bot,
                                response_from=response_whose,
                                tg_user_from=message.from_user,
                            )
            else:
                await message.reply((
                    'Можно назначать брата или сестру только между Вами '
                    'или профилями, которыми Вы владеете.\n\n'
                    'Назначайте брата или сестру по новой'
                ))
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.NEW_BRO, KeyboardType.NEW_SIS,
        KeyboardType.SEP,
        # uuid потомка папы или мамы           # 1
        # KeyboardType.SEP,
    ), c.data),
    state = FSMbroSis.ask,
    )
async def process_callback_new_bro_sis_gender(callback_query: types.CallbackQuery, state: FSMContext):
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    async with state.proxy() as data:
        if not data.get('uuid') or data['uuid'] != uuid:
            await Misc.state_finish(state)
            return
        data['gender'] = 'm' \
            if callback_query.data.split(KeyboardType.SEP)[0] == str(KeyboardType.NEW_BRO) \
            else 'f'
        brata_sestru = "брата" if data["gender"] == "m" else "сестру"
        response = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
        if not response:
            await callback_query.message.reply((
                f'Можно назначить {brata_sestru} только Вам '
                f'или профилю, которым Вы владеете.\n\n'
                f'Назначайте {brata_sestru} по новой'
            ))
            await Misc.state_finish(state)
            return
        data_whose = response['response_uuid']
        if not data_whose.get('father') and not data_whose.get('mother'):
            await message.reply((
                f'Назначить {brata_sestru} для <b>{data_whose["first_name"]}</b> - '
                f'это внести профиль с теми же родителям. '
                f'Но у <b>{data_whose["first_name"]}</b> не заданы родители!\n\n'
                f'Назначайте {brata_sestru} по новой'
            ))
            await Misc.state_finish(state)
            return
        await FSMbroSis.new.set()
        await callback_query.message.reply((
                f'Укажите ФИО {"БРАТА" if data["gender"] == "m" else "СЕСТРЫ"} для:\n'
                f'{data_whose["first_name"]}\n'
                f'Например, {"Иван Иванович Иванов" if data["gender"] == "m" else "Мария Ивановна Иванова"} '
            ),
            reply_markup=Misc.reply_markup_cancel_row())

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMbroSis.new,
)
async def put_new_bro_sis(message: types.Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    async with state.proxy() as data:
        if data.get('uuid') and data.get('gender'):
            if message.content_type != ContentType.TEXT:
                await message.reply(
                    Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + Misc.MSG_REPEATE_PLEASE,
                    reply_markup=Misc.reply_markup_cancel_row()
                )
                return
            first_name = Misc.strip_text(message.text)
            if not first_name or re.search(Misc.RE_UUID, first_name):
                await message.reply(
                    Misc.PROMPT_IOF_INCORRECT,
                    reply_markup=Misc.reply_markup_cancel_row(),
                )
                return
            brata_sestru = "брата" if data["gender"] == "m" else "сестру"
            response_whose = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=data['uuid'])
            if response_whose:
                data_whose = response_whose['response_uuid']
                bot_data = await bot.get_me()
                dl_whose = Misc.get_deeplink_with_name(data_whose, bot_data)
                if not data_whose.get('father') and not data_whose.get('mother'):
                    await message.reply((
                        f'Назначить {brata_sestru} - это задать для <u>{first_name}</u> родителей {dl_whose}. '
                        f'Но у {dl_whose} не заданы родители!\n\n'
                        f'Назначайте {brata_sestru} по новой'
                    ))
                else:
                    is_father_set = is_mother_set = False
                    data_bro_sis = None
                    payload_post = dict(
                        tg_token=settings.TOKEN,
                        first_name=first_name,
                        gender=data['gender'],
                        owner_id=response_whose['user_id'],
                    )
                    if data_whose.get('father'):
                        payload_post.update(
                            link_id=data_whose['father']['uuid'],
                            link_relation='link_is_father',
                        )
                        logging.debug('post new brother or sister & set father payload: %s' % Misc.secret(payload_post))
                        status, data_bro_sis = await Misc.api_request(
                            path='/api/profile',
                            method='post',
                            data=payload_post,
                        )
                        logging.debug('post new brother or sister & set father, status: %s' % status)
                        logging.debug('post new brother or sister & set father, response: %s' % data_bro_sis)
                        if status == 200:
                            is_father_set = True
                            dl_bro_sis = Misc.get_deeplink_with_name(data_bro_sis, bot_data)
                        else:
                            if status == 400  and data_bro_sis.get('message'):
                                await message.reply(
                                    f'Ошибка!\n{data_bro_sis["message"]}\n\nНазначайте {brata_sestru} по новой'
                                )
                            else:
                                await message.reply(Misc.MSG_ERROR_API)
                    if (data_whose.get('father') and is_father_set or not data_whose.get('father')) and \
                       data_whose.get('mother'):
                        if is_father_set:
                            # когда связывали с папой, уже появился профиль в системе: data_bro_sis
                            payload_op = dict(
                                tg_token=settings.TOKEN,
                                operation_type_id=OperationType.SET_MOTHER,
                                user_id_from=data_bro_sis['uuid'],
                                user_id_to=data_whose['mother']['uuid'],
                            )
                            logging.debug('post operation, payload: %s' % Misc.secret(payload_op))
                            status, response = await Misc.api_request(
                                path='/api/addoperation',
                                method='post',
                                data=payload_op,
                            )
                            logging.debug('post operation, status: %s' % status)
                            logging.debug('post operation, response: %s' % response)
                            if not (status == 200 or \
                               status == 400 and response.get('code') == 'already'):
                                repr_bro_sis = dl_bro_sis if is_father_set else first_name
                                if status == 400  and response.get('message'):
                                    await message.reply(
                                        f'Ошибка назначения мамы для {repr_bro_sis}!\n' + \
                                        f'{response["message"]}\n\n' + \
                                        '' if is_father_set else 'Назначайте {brata_sestru} по новой' 
                                    )
                                else:
                                    await message.reply(
                                        Misc.MSG_ERROR_API + \
                                        '\nпри назначении мамы для ' + repr_bro_sis + \
                                        '' if is_father_set else '\nНазначайте {brata_sestru} по новой'
                                    )
                            if status == 200:
                                is_mother_set = True
                        else:
                            payload_post.update(
                                link_id=data_whose['mother']['uuid'],
                                link_relation='link_is_mother',
                            )
                            logging.debug('post new brother or sister & set mother payload: %s' % Misc.secret(payload_post))
                            status, data_bro_sis = await Misc.api_request(
                                path='/api/profile',
                                method='post',
                                data=payload_post,
                            )
                            logging.debug('post new brother or sister & set mother, status: %s' % status)
                            logging.debug('post new brother or sister & set father, response: %s' % data_bro_sis)
                            if status == 200:
                                is_mother_set = True
                                dl_bro_sis = Misc.get_deeplink_with_name(data_bro_sis, bot_data)
                            else:
                                if status == 400  and data_bro_sis.get('message'):
                                    await message.reply(
                                        f'Ошибка!\n{data_bro_sis["message"]}\n\nНазначайте {brata_sestru} по новой'
                                    )
                                else:
                                    await message.reply(Misc.MSG_ERROR_API)
                    if is_father_set or data_whose.get('mother') and is_mother_set:
                        status, response = await Misc.get_user_by_uuid(uuid=data_bro_sis['uuid'])
                        if status == 200:
                            await message.reply(f'{dl_bro_sis} имеет тех же родителей, что и {dl_whose}')
                            await Misc.show_card(
                                response,
                                bot,
                                response_from=response_whose,
                                tg_user_from=message.from_user,
                            )
            else:
                await message.reply((
                    f'Можно назначить {brata_sestru} только Вам '
                    f'или профилю, которым Вы владеете.\n\n'
                    f'Назначайте {brata_sestru} по новой'
                ))
    await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.KEYS,
        KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_keys(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Заменить контакты

    (В апи контакты - это keys)
    """
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(
        owner_tg_user=callback_query.from_user,
        uuid=uuid,
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
    if await is_it_command(message, state):
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
            response_sender = await Misc.check_owner_by_uuid(
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
                            await Misc.show_card(
                                response,
                                bot,
                                response_from=response_sender,
                                tg_user_from=message.from_user,
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
        response_sender = await Misc.check_owner_by_uuid(
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
    if await is_it_command(message, state, excepts=('start',)):
        return
    async with state.proxy() as data:
        uuid = data.get('uuid')
        if uuid:
            response_sender = await Misc.check_owner_by_uuid(
                owner_tg_user=message.from_user,
                uuid=uuid,
                check_owned_only=True
            )
            if response_sender:
                user_sid_to = Misc.sid_from_link(message.text)
                if not user_sid_to:
                    await message.reply(
                        Misc.MSG_ERROR_UUID_NOT_VALID,
                        reply_markup=Misc.reply_markup_cancel_row()
                    )
                    return
                response_from = response_sender['response_uuid']
                status_to, response_to = await Misc.get_user_by_sid(user_sid_to)
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
                    if response_from['owner']['user_id'] == response_to['user_id']:
                        # Сам себя назначил
                        await message.reply(
                            Misc.PROMPT_CHANGE_OWNER_SUCCESS % dict(
                                iof_from=iof_from, iof_to=iof_to, already='уже',
                        ))
                        # state_finish, return
                    elif response_to['owner']:
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
    Заменить владельца. Подтверждение получено
    """
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    response_sender = await Misc.check_owner_by_uuid(
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
                                iof_from=iof_from, iof_to=iof_to, already='',
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
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
    if await is_it_command(message, state):
        return
    first_name = Misc.strip_text(message.text)
    if not first_name or re.search(Misc.RE_UUID, first_name):
        await message.reply(
            Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
                     
    async with state.proxy() as data:
        uuid = data.get('uuid')
    if uuid:
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
                    response,
                    bot,
                    response_from=response_sender,
                    tg_user_from=message.from_user,
                )
    await Misc.state_finish(state)

# ------------------------------------------------------------------------------
#   Пол
# ------------------------------------------------------------------------------

@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.GENDER,
        KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_gender(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Задать пол
    """
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
    if not response_sender:
        return
    response_uuid = response_sender['response_uuid']
    dict_gender = dict(
        keyboard_type=KeyboardType.GENDER_MALE,
        sep=KeyboardType.SEP,
    )
    callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
    inline_button_male = InlineKeyboardButton('Муж', callback_data=callback_data_template % dict_gender)
    dict_gender.update(keyboard_type=KeyboardType.GENDER_FEMALE)
    inline_button_female = InlineKeyboardButton('Жен', callback_data=callback_data_template % dict_gender)
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_button_male, inline_button_female, Misc.inline_button_cancel())
    await FSMgender.ask.set()
    state = dp.current_state()
    async with state.proxy() as data:
        data['uuid'] = uuid
    his_her = Misc.his_her(response_uuid) if response_uuid['owner'] else 'Ваш'
    prompt_gender = (
        f'<b>{response_uuid["first_name"]}</b>.\n\n'
        f'Уточните {his_her} пол:'
    )
    await callback_query.message.reply(
        prompt_gender,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMgender.ask,
)
async def got_gender_text(message: types.Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    await message.reply(
        'Ожидается выбор пола, нажатием одной из кнопок, в сообщении выше',
        reply_markup=Misc.reply_markup_cancel_row(),
    )

@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s' % (
        KeyboardType.GENDER_MALE, KeyboardType.GENDER_FEMALE,
        KeyboardType.SEP,
    ), c.data,
    ), state=FSMgender.ask,
    )
async def process_callback_gender_got(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Ввести пол человека
    """
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        uuid = None
        async with state.proxy() as data:
            if data.get('uuid'):
                uuid = data['uuid']
        if uuid:
            response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
            if response_sender:
                code = callback_query.data.split(KeyboardType.SEP)
                gender = 'm' if code[0] == str(KeyboardType.GENDER_MALE) else 'f'
                status, response = await Misc.put_user_properties(
                    uuid=data['uuid'],
                    gender=gender,
                )
                if status == 200 and response:
                    gender = response.get('gender')
                    s_gender = 'не известный'
                    if gender:
                        s_gender = 'мужской' if gender == 'm' else 'женский'
                    bot_data = await bot.get_me()
                    deeplink = Misc.get_deeplink_with_name(response, bot_data)
                    await callback_query.message.reply(
                        text= f'{deeplink}\nУстановлен пол: {s_gender}',
                        disable_web_page_preview=True,
                    )
    await Misc.state_finish(state)

# ------------------------------------------------------------------------------
#   Даты
# ------------------------------------------------------------------------------

@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.DATES,
        KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_dates(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Задать пол
    """
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
    if not response_sender:
        return
    response_uuid = response_sender['response_uuid']
    his_her = Misc.his_her(response_uuid) if response_uuid['owner'] else 'Ваш'
    title_dob = 'Не знаю'
    prompt_dob = (
        f'<b>{response_uuid["first_name"]}</b>\n\n'
        f'Укажите {his_her} день рождения '
    ) + Misc.PROMPT_DATE_FORMAT
    if not response_uuid['owner']:
        prompt_dob += (
            f'\n\nЕсли хотите скрыть дату своего рождения '
            f'или в самом деле не знаете, когда Ваш день рождения, нажмите <u>{title_dob}</u>'
        )
    callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
    dict_dob_unknown = dict(
        keyboard_type=KeyboardType.DATES_DOB_UNKNOWN,
        sep=KeyboardType.SEP,
    )
    inline_button_dob_unknown = InlineKeyboardButton(
        title_dob, callback_data=Misc.CALLBACK_DATA_KEY_TEMPLATE % dict_dob_unknown
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_button_dob_unknown, Misc.inline_button_cancel())
    await FSMdates.dob.set()
    state = dp.current_state()
    async with state.proxy() as data:
        data['uuid'] = uuid
    await callback_query.message.reply(
        prompt_dob,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.DATES_DOB_UNKNOWN,
        KeyboardType.SEP,
    ), c.data,
    ), state=FSMdates.dob,
    )
async def process_callback_other_dob_unknown(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Ввести пустую дату рождения
    """
    finish_it = True
    if callback_query.message:
        async with state.proxy() as data:
            if uuid := data.get('uuid'):
                response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
                if response_sender:
                    finish_it = False
                    response_uuid = response_sender['response_uuid']
                    data['dob'] = ''
                    if response_uuid['owner']:
                        await draw_dod(callback_query.message, response_uuid)
                    else:
                        await put_dates(callback_query.message, callback_query.from_user, state, data)
    if finish_it:
        await Misc.state_finish(state)


async def draw_dod(message, profile):
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

    callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
    dict_callback = dict(
        keyboard_type=KeyboardType.DATES_DOD_NONE,
        sep=KeyboardType.SEP,
    )
    inline_button_alive = InlineKeyboardButton(
        s_alive_or_dont_know,
        callback_data=callback_data_template % dict_callback
    )
    dict_callback.update(keyboard_type=KeyboardType.DATES_DOD_DEAD)
    inline_button_dead = InlineKeyboardButton(
        s_dead_none_title,
        callback_data=callback_data_template % dict_callback
    )
    reply_markup = InlineKeyboardMarkup()
    reply_markup.row(inline_button_alive, inline_button_dead, Misc.inline_button_cancel())
    await FSMdates.dod.set()
    await message.reply(
        prompt_dod,
        reply_markup=reply_markup,
    )


async def put_dates(message, tg_user_sender, state, data):
    if data.get('uuid'):
        response_sender = await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=data['uuid'])
        if response_sender:
            dob = data.get('dob', '')
            dod = data.get('dod', '')
            is_dead = data.get('is_dead', '')
            status, response = await Misc.put_user_properties(
                uuid=data['uuid'],
                dob=dob,
                dod=dod,
                is_dead = '1' if is_dead or dod else '',
            )
            if status == 200 and response:
                await Misc.show_card(
                    response,
                    bot,
                    response_from=response_sender,
                    tg_user_from=tg_user_sender,
                )
            elif status == 400 and response and response.get('message'):
                dates = 'даты' if response_sender['response_uuid']['owner'] else 'дату рождения'
                await message.reply(f'Ошибка!\n{response["message"]}\n\nНазначайте {dates} по новой')
            else:
                await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMdates.dob,
)
async def get_dob(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    finish_it = True
    if message_text := Misc.strip_text(message.text):
        async with state.proxy() as data:
            if data.get('uuid'):
                if response_sender := await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=data['uuid']):
                    finish_it = False
                    data['dob'] = message_text
                    response_uuid = response_sender['response_uuid']
                    if response_uuid['owner']:
                        await draw_dod(message, response_uuid)
                    else:
                        await put_dates(message, message.from_user, state, data)
    if finish_it:
        await Misc.state_finish(state)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s$' % (
        KeyboardType.DATES_DOD_NONE, KeyboardType.DATES_DOD_DEAD,
        KeyboardType.SEP,
    ), c.data,
    ), state=FSMdates.dod,
    )
async def process_callback_dates_DOD_NONE_or_DEAD(callback_query: types.CallbackQuery, state: FSMContext):
    finish_it = True
    if callback_query.message:
        async with state.proxy() as data:
            if uuid := data.get('uuid'):
                if response_sender := await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid):
                    finish_it = False
                    code = callback_query.data.split(KeyboardType.SEP)
                    data['dod'] = ''
                    data['is_dead'] = code[0] == str(KeyboardType.DATES_DOD_DEAD)
                    await put_dates(callback_query.message, callback_query.from_user, state, data)
    if finish_it:
        await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMdates.dod,
)
async def get_dod(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY,
            reply_markup=Misc.reply_markup_cancel_row()
        )
        return
    if await is_it_command(message, state):
        return
    finish_it = True
    if message_text := Misc.strip_text(message.text):
        async with state.proxy() as data:
            if data.get('uuid'):
                if response_sender := await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=data['uuid']):
                    finish_it = False
                    data['is_dead'] = True
                    data['dod'] = message_text
                    await put_dates(message, message.from_user, state, data)
    if finish_it:
        await Misc.state_finish(state)

# ------------------------------------------------------------------------------
#   Комментарий
# ------------------------------------------------------------------------------

@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.COMMENT,
        KeyboardType.SEP,
        # uuid своё или родственника           # 1
        # KeyboardType.SEP,
    ), c.data,
    ), state=None,
    )
async def process_callback_comment(callback_query: types.CallbackQuery, state: FSMContext):
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    response_sender = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
    if not response_sender:
        return
    response_uuid = response_sender['response_uuid']
    state = dp.current_state()
    async with state.proxy() as data:
        data['uuid'] = uuid
    await FSMcomment.ask.set()
    await bot.send_message(
        callback_query.from_user.id,
        f'Введите комментарий для:\n{response_sender["response_uuid"]["first_name"]}',
        reply_markup=Misc.reply_markup_cancel_row(),
    )


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMcomment.ask,
)
async def put_comment(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(Misc.MSG_ERROR_TEXT_ONLY, reply_markup=Misc.reply_markup_cancel_row())
        return
    if await is_it_command(message, state):
        return
    if not (comment := Misc.strip_text(message.text)):
        return
    async with state.proxy() as data:
        uuid = data.get('uuid')
    if uuid:
        response_sender = await Misc.check_owner_by_uuid(owner_tg_user=message.from_user, uuid=uuid)
        if response_sender:
            status, response = await Misc.put_user_properties(
                uuid=uuid,
                comment=comment,
            )
            if status == 200:
                await message.reply(
                    f'{"Изменен" if response_sender["response_uuid"]["comment"] else "Добавлен"} комментарий')
                await Misc.show_card(
                    response,
                    bot,
                    response_from=response_sender,
                    tg_user_from=message.from_user,
                )
    await Misc.state_finish(state)


# ------------------------------------------------------------------------------
#   Отправить сообщение
# ------------------------------------------------------------------------------

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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    status_to, profile_to = await Misc.get_user_by_uuid(uuid)
    if status_to != 200:
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

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMsendMessage.ask,
)
async def got_message_to_send(message: types.Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    msg_saved = 'Сообщение сохранено'
    async with state.proxy() as data:
        if data.get('uuid'):
            status_to, profile_to = await Misc.get_user_by_uuid(data['uuid'], with_owner_tg_data=True)
            if status_to == 200:
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


# ------------------------------------------------------------------------------
#   Архив (показать сообщения)
# ------------------------------------------------------------------------------

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
    if not (user_to_uuid := Misc.getuuid_from_callback(callback_query)):
        return
    tg_user_sender = callback_query.from_user
    status_from, profile_from = await Misc.post_tg_user(callback_query.from_user)
    if status_from != 200:
        return
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
                if m['operation_type_id'] == OperationType.NULLIFY_ATTITUDE:
                    msg += 'в связи с тем что не знаком(а) с\n'
                if m['operation_type_id'] == OperationType.NULLIFY_ACQ:
                    msg += 'в связи с установкой знакомства с\n'
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
        if status_to == 200:
            msg = '%(full_name)s не получал%(a)s сообщений' % dict(
                full_name=Misc.get_deeplink_with_name(profile_to, bot_data),
                a='а' if profile_to.get('gender') == 'f' else '' if profile_to.get('gender') == 'm' else '(а)',
            )
        else:
            msg = 'Сообщения не найдены'
        await bot.send_message(tg_user_sender.id, text=msg, disable_web_page_preview=True,)

# ------------------------------------------------------------------------------

async def do_process_ability(message: types.Message, uuid=None):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        if not Misc.editable(response_sender):
            return
        reply_markup = Misc.reply_markup_cancel_row()
        await FSMability.ask.set()
        state = dp.current_state()
        if uuid:
            async with state.proxy() as data:
                data['uuid'] = uuid
        await message.reply(Misc.PROMPT_ABILITY, reply_markup=reply_markup)
        if response_sender.get('created'):
            await Misc.update_user_photo(bot, message.from_user, response_sender)


async def do_process_wish(message: types.Message, uuid=None):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        if not Misc.editable(response_sender):
            return
        reply_markup = Misc.reply_markup_cancel_row()
        await FSMwish.ask.set()
        state = dp.current_state()
        if uuid:
            async with state.proxy() as data:
                data['uuid'] = uuid
        await message.reply(Misc.PROMPT_WISH, reply_markup=reply_markup)
        if response_sender.get('created'):
            await Misc.update_user_photo(bot, message.from_user, response_sender)


@dp.poll_answer_handler()
async def our_poll_answer_handler(poll_answer: types.PollAnswer):
    status_sender, response_sender = await Misc.post_tg_user(poll_answer.user, did_bot_start=False)
    if status_sender == 200:
        poll_answer_dict=dict(poll_answer)
        poll_answer_dict.update(tg_token=settings.TOKEN)
        logging.debug('poll answer to api, payload: %s' % Misc.secret(poll_answer_dict))
        status, response = await Misc.api_request(
            path='/api/bot/poll/answer',
            method='post',
            json=poll_answer_dict,
        )
        logging.debug('poll answer to api, status: %s' % status)
        logging.debug('poll answer to api, response: %s' % response)
        if response_sender.get('created'):
            await Misc.update_user_photo(bot, poll_answer.user, response_sender)


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
        if uuid and not await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid):
            return
    except IndexError:
        uuid = None
    await do_process_ability(callback_query.message, uuid=uuid)


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
        if uuid and not await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid):
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
        await callback_query.message.reply(Misc.MSG_YOU_CANCELLED_INPUT)


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
                await Misc.show_card(
                    response,
                    bot,
                    response_from=response_sender,
                    tg_user_from=message.from_user,
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
                await Misc.show_card(
                    response,
                    bot,
                    response_from=response_sender,
                    tg_user_from=message.from_user,
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
                await Misc.show_card(
                    response,
                    bot,
                    response_from=response_sender,
                    tg_user_from=message.from_user,
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
        if uuid and not await Misc.check_owner_by_uuid(owner_tg_user=tg_user_sender, uuid=uuid):
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
        if status == 200 and Misc.is_photo_downloaded(response):
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
    status, response = await Misc.get_user_by_uuid(uuid)
    if status == 200:
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
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        await Misc.state_finish(state)
        return
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
            await Misc.show_card(
                response,
                bot,
                response_from=response_sender,
                tg_user_from=callback_query.from_user,
            )
        elif status == 400:
            if response.get('message'):
                await callback_query.message.reply(response['message'])
            else:
                await callback_query.message.reply(Misc.MSG_ERROR_API)
        else:
            await callback_query.message.reply(Misc.MSG_ERROR_API)
    else:
        await message.reply(Misc.MSG_ERROR_API)
    await Misc.state_finish(state)


async def new_iof_ask_gender(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if data.get('first_name'):
            callback_data_template = Misc.CALLBACK_DATA_KEY_TEMPLATE
            callback_data_male = callback_data_template % dict(
                keyboard_type=KeyboardType.NEW_IOF_GENDER_MALE,
                sep=KeyboardType.SEP,
            )
            inline_btn_male = InlineKeyboardButton('Муж', callback_data=callback_data_male)
            callback_data_female = callback_data_template % dict(
                keyboard_type=KeyboardType.NEW_IOF_GENDER_FEMALE,
                sep=KeyboardType.SEP,
            )
            inline_btn_female = InlineKeyboardButton('Жен', callback_data=callback_data_female)
            reply_markup = InlineKeyboardMarkup()
            reply_markup.row(inline_btn_male, inline_btn_female, Misc.inline_button_cancel())
            await message.reply(
                '<u>' + data['first_name'] + '</u>:\n\n' + 'Укажите пол',
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        else:
            await Misc.state_finish(state)

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMnewIOF.ask_gender,
)
async def new_iof_ask_gender_if_message(message: types.Message, state: FSMContext):
    '''
    Если после запроса пола нового приходит сообщение

    Снова надо попросить пол
    '''
    if await is_it_command(message, state):
        return
    async with state.proxy() as data:
        await new_iof_ask_gender(message, state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMnewOrg.ask,
)
async def new_iof_ask_org(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_NEW_ORG,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    if await is_it_command(message, state):
        return
    first_name = Misc.strip_text(message.text)
    if not first_name or len(first_name) < 5:
        await message.reply(
            Misc.PROMPT_ORG_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        payload_org = dict(
            tg_token=settings.TOKEN,
            owner_id=response_sender['user_id'],
            first_name=first_name,
            is_org='1',
        )
        logging.debug('post new org, payload: %s' % Misc.secret(payload_org))
        status, response = await Misc.api_request(
            path='/api/profile',
            method='post',
            data=payload_org,
        )
        logging.debug('post new org, status: %s' % status)
        logging.debug('post new org, response: %s' % response)
        if status == 200:
            await message.reply('Добавлена организация')
            try:
                status, response = await Misc.get_user_by_uuid(response['uuid'])
                if status == 200:
                    await Misc.show_card(
                        response,
                        bot,
                        response_from=response_sender,
                        tg_user_from=message.from_user,
                    )
            except:
                pass
    await Misc.state_finish(state)

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMnewIOF.ask,
)
async def new_iof_ask_fio(message: types.Message, state: FSMContext):
    if message.content_type != ContentType.TEXT:
        await message.reply(
            Misc.MSG_ERROR_TEXT_ONLY + '\n\n' + \
            Misc.PROMPT_NEW_IOF,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    if await is_it_command(message, state):
        return
    first_name = Misc.strip_text(message.text)
    if not first_name:
        await message.reply(
            Misc.PROMPT_IOF_INCORRECT,
            reply_markup=Misc.reply_markup_cancel_row(),
        )
        return
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    if status_sender == 200:
        state = dp.current_state()
        async with state.proxy() as data:
            await FSMnewIOF.ask_gender.set()
            data['uuid'] = response_sender['uuid']
            data['first_name'] = first_name
        await new_iof_ask_gender(message, state)
    else:
         await Misc.state_finish(state)
         await message.reply(Misc.MSG_ERROR_API)


@dp.callback_query_handler(
    lambda c: c.data and re.search(r'^(%s|%s)%s$' % (
        KeyboardType.NEW_IOF_GENDER_MALE, KeyboardType.NEW_IOF_GENDER_FEMALE,
        KeyboardType.SEP,
    ), c.data),
    state = FSMnewIOF.ask_gender,
    )
async def process_callback_new_iof_gender(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.message:
        gender = 'm' if callback_query.data.split(KeyboardType.SEP)[0] == str(KeyboardType.NEW_IOF_GENDER_MALE) else 'f'
        status_sender, response_sender = await Misc.post_tg_user(callback_query.from_user)
        async with state.proxy() as data:
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
                    await callback_query.message.reply('Добавлен' if gender == 'm' else 'Добавлена')
                    status, response = await Misc.get_user_by_uuid(response['uuid'])
                    if status == 200:
                        await Misc.show_card(
                            response,
                            bot,
                            response_from=response_sender,
                            tg_user_from=callback_query.from_user,
                        )
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMquery.ask,
)
async def process_make_query(message: types.Message, state: FSMContext):
    status_sender, response_sender = await Misc.post_tg_user(message.from_user)
    state = dp.current_state()
    if await is_it_command(message, state):
        return
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


def parse_code_tn(callback_query):
    '''
    Получить необходимое из callback_query.data при (не)доверии, не знакомы

    ValueError, если что-то там неверно
    '''
    code = callback_query.data.split(KeyboardType.SEP)
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
    message_ = callback_query.message
    group_member = \
        message_.chat.type in (types.ChatType.GROUP, types.ChatType.SUPERGROUP) and \
        dict(
                group_chat_id=message_.chat.id,
                group_title=message_.chat.title,
                group_type=message_.chat.type,
        ) \
        or None
    return operation_type_id, uuid, message_to_forward_id, group_member, is_thank_card


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.TRUST_THANK,
        KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_tn(callback_query: types.CallbackQuery, state: FSMContext):
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
    try:
        operation_type_id, uuid, message_to_forward_id, group_member, is_thank_card = parse_code_tn(callback_query)
    except ValueError:
        return

    tg_user_sender = callback_query.from_user
    message = callback_query.message
    status_sender, profile_sender = await Misc.post_tg_user(
        tg_user_sender,
        did_bot_start=message.chat.type == types.ChatType.PRIVATE,
    )
    if status_sender != 200 or not profile_sender:
        return
    if not operation_type_id or operation_type_id not in (
            OperationType.TRUST,
            OperationType.MISTRUST, OperationType.NULLIFY_ATTITUDE,
            OperationType.ACQ, OperationType.THANK,
        ):
        return
    status_to, profile_to = await Misc.get_user_by_uuid(uuid)
    if status_to != 200:
        return
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
            except (ChatNotFound, CantInitiateConversation):
                pass
            return
        else:
            await message.reply(text_same, disable_web_page_preview=True,)
            return

    data_ = dict(
        profile_from = profile_sender,
        profile_to = profile_to,
        operation_type_id = operation_type_id,
        tg_user_sender_id = tg_user_sender.id,
        message_to_forward_id = message_to_forward_id,
        callback_query=callback_query,
        group_member=group_member,
        is_thank_card=is_thank_card,
    )
    if group_member:
        group_member.update(user_tg_uid=tg_user_sender.id)
    await put_thank_etc(tg_user_sender, data=data_, state=None)


async def put_thank_etc(tg_user_sender, data, state=None):
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
        user_id_to=profile_to['uuid'],
    )
    if data.get('message_to_forward_id'):
        post_op.update(
            tg_from_chat_id=tg_user_sender.id,
            tg_message_id=data['message_to_forward_id'],
        )
    logging.debug('post operation, payload: %s' % Misc.secret(post_op))
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post_op,
    )
    logging.debug('post operation, status: %s' % status)
    logging.debug('post operation, response: %s' % response)
    text = text_popup = None
    operation_done = operation_already = do_thank = False
    bot_data = await bot.get_me()
    if status == 200:
        operation_done = True
        trusts_or_thanks = ''
        thanks_count_str = ''
        thanks_count = response.get('currentstate') and response['currentstate'].get('thanks_count') or None
        if thanks_count is not None:
            thanks_count_str = ' (%s)' % thanks_count
        if post_op['operation_type_id'] == OperationType.THANK:
            text = '%(full_name_from_link)s благодарит%(thanks_count_str)s %(full_name_to_link)s'
            do_thank = True
        if post_op['operation_type_id'] == OperationType.ACQ:
            text = '%(full_name_from_link)s знаком(а) с %(full_name_to_link)s'
        if post_op['operation_type_id'] == OperationType.MISTRUST:
            text = '%(full_name_from_link)s не доверяет %(full_name_to_link)s'
        elif post_op['operation_type_id'] == OperationType.NULLIFY_ATTITUDE:
            text = '%(full_name_from_link)s не знаком(а) с %(full_name_to_link)s'
        elif post_op['operation_type_id'] == OperationType.TRUST:
            text = '%(full_name_from_link)s доверяет %(full_name_to_link)s'
        profile_from = response['profile_from']
        profile_to = response['profile_to']

    elif status == 400 and response.get('code', '') == 'already':
        operation_already = True
        full_name_to_link = Misc.get_deeplink_with_name(profile_to, bot_data, plus_trusts=True)
        if post_op['operation_type_id'] == OperationType.TRUST:
            text = f'Вы уже доверяете {full_name_to_link}'
        elif post_op['operation_type_id'] == OperationType.MISTRUST:
            text = f'Вы уже установили недоверие к {full_name_to_link}'
        elif post_op['operation_type_id'] == OperationType.NULLIFY_ATTITUDE:
            text = f'Вы и так не знакомы с {full_name_to_link}'
        elif post_op['operation_type_id'] == OperationType.ACQ:
            text = f'Вы уже знакомы с {full_name_to_link}'

    if operation_done and text:
        full_name_from_link = Misc.get_deeplink_with_name(profile_from, bot_data, plus_trusts=True)
        full_name_to_link = Misc.get_deeplink_with_name(profile_to, bot_data, plus_trusts=True)
        text = text % dict(
            full_name_from_link=full_name_from_link,
            full_name_to_link=full_name_to_link,
            trusts_or_thanks=trusts_or_thanks,
            thanks_count_str=thanks_count_str,
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
        reply_markup = None
        text_to_sender = text
        if do_thank:
            if response.get('journal_id'):
                reply_markup = InlineKeyboardMarkup()
                inline_btn_cancel_thank = InlineKeyboardButton('Отменить благодарность',
                    callback_data=Misc.CALLBACK_DATA_ID__TEMPLATE % dict(
                        keyboard_type=KeyboardType.CANCEL_THANK,
                        id_=response['journal_id'],
                        sep=KeyboardType.SEP,
                ))
                reply_markup.row(inline_btn_cancel_thank)

        if operation_done and data.get('message_after_meet'):
            status_template, message_after_meet = await Misc.get_template('message_after_meet')
            if status_template != 200 or not message_after_meet:
                message_after_meet = 'Добро пожаловать!'
            text_to_sender += f'\n\n{message_after_meet}'

        if not group_member and (operation_done or operation_already):
            if reply_markup is None:
                reply_markup = InlineKeyboardMarkup()
            link_profile = profile_to
            if post_op['operation_type_id'] == OperationType.ACQ:
                link_profile = profile_from
            inline_btn_trusts = InlineKeyboardButton(
                'Сеть доверия',
                login_url=Misc.make_login_url(
                    redirect_path='%(graph_host)s/?user_uuid_trusts=%(user_uuid)s' % dict(
                        graph_host=settings.GRAPH_HOST,
                        user_uuid=link_profile['uuid'],
                    ),
                    bot_username=bot_data['username'],
                    keep_user_data='on',
                ))
            login_url_buttons = [inline_btn_trusts, ]

            inline_btn_map = InlineKeyboardButton(
                'Карта',
                login_url=Misc.make_login_url(
                    redirect_path='%(map_host)s/?uuid_trustees=%(user_uuid)s' % dict(
                        map_host=settings.MAP_HOST,
                        user_uuid=link_profile['uuid'],
                    ),
                    bot_username=bot_data['username'],
                    keep_user_data='on',
                ))
            reply_markup.row(inline_btn_trusts, inline_btn_map)

        if not group_member:
            try:
                await bot.send_message(
                    tg_user_sender.id,
                    text=text_to_sender,
                    disable_web_page_preview=True,
                    disable_notification=True,
                    reply_markup=reply_markup,
                )
            except (ChatNotFound, CantInitiateConversation):
                pass

        if not group_member and data.get('callback_query') and \
           (operation_done  or operation_already):
            if data.get('is_thank_card'):
                await quest_after_thank_if_no_attitude(
                    f'Установите отношение к {full_name_to_link}:',
                    profile_from, profile_to, tg_user_sender,
                    card_message=data['callback_query'].message,
                )
            else:
                await Misc.show_card(
                    profile_to,
                    bot=bot,
                    response_from=profile_from,
                    tg_user_from=tg_user_sender,
                    card_message=data['callback_query'].message,
                )

        if do_thank and response.get('currentstate') and response['currentstate'].get('attitude', '') == None:
            # Благодарность незнакомому. Нужен вопрос, как он к этому незнакомому
            await quest_after_thank_if_no_attitude(
                f'Установите отношение к {full_name_to_link}:',
                profile_from, profile_to, tg_user_sender, card_message=None,
            )

    # Это в группу
    #
    if group_member and data.get('callback_query') and \
       (operation_done  or operation_already):
        try:
            await data['callback_query'].message.edit_text(
            text=await group_minicard_text (response['profile_to'], data['callback_query'].message.chat, bot_data),
            reply_markup=data['callback_query'].message.reply_markup,
            disable_web_page_preview=True,
            )
        except:
            pass
        if post_op['operation_type_id'] == OperationType.TRUST:
            if operation_done:
                popup_message = 'Доверие установлено'
            else:
                popup_message = 'Доверие уже было установлено'
            await bot.answer_callback_query(
                data['callback_query'].id,
                text=popup_message,
                show_alert=True,
            )

    # Это получателю благодарности и т.п. или владельцу получателя, если получатель собственный
    #
    if text:
        text_to_recipient = text
        if operation_done and data.get('message_to_forward_id'):
            text_to_recipient += ' в связи с сообщением, см. ниже...'
        tg_user_to_notify_tg_data = []
        if profile_to.get('owner'):
            if profile_to['owner']['uuid'] != profile_from['uuid']:
                tg_user_to_notify_tg_data = profile_to['owner'].get('tg_data', [])
        else:
            tg_user_to_notify_tg_data = profile_to.get('tg_data', [])
        for tgd in tg_user_to_notify_tg_data:
            if operation_done:
                try:
                    await bot.send_message(
                        tgd['tg_uid'],
                        text=text_to_recipient,
                        disable_web_page_preview=True,
                        disable_notification=True,
                    )
                except (ChatNotFound, CantInitiateConversation):
                    pass
            if operation_done and not profile_to.get('owner') and data.get('message_to_forward_id'):
                try:
                    await bot.forward_message(
                        chat_id=tgd['tg_uid'],
                        from_chat_id=tg_user_sender.id,
                        message_id=data['message_to_forward_id'],
                        disable_notification=True,
                    )
                except (ChatNotFound, CantInitiateConversation):
                    pass


async def quest_after_thank_if_no_attitude(text, profile_from, profile_to, tg_user_from, card_message=None,):
    """
    Карточка юзера в бот, когда того благодарят, но благодаривший с ним не знаком

    -   text:           текст в карточке
    -   profile_to:     кого благодарят
    -   tg_user_from:   кто благодарит
    -   card_message:   сообщение с карточкой, которое надо подправить, а не слать новую карточку
    """

    reply_markup = InlineKeyboardMarkup()
    attitude = None
    status_relations, response_relations = await Misc.call_response_relations(profile_from, profile_to)
    if status_relations == 200:
        attitude = response_relations['from_to']['attitude']

    dict_reply = dict(
        keyboard_type=KeyboardType.TRUST_THANK,
        sep=KeyboardType.SEP,
        user_to_uuid_stripped=Misc.uuid_strip(profile_to['uuid']),
        message_to_forward_id='',
        is_thank_card='1',
    )
    callback_data_template = OperationType.CALLBACK_DATA_TEMPLATE + '%(is_thank_card)s%(sep)s'
    asterisk = ' (*)'

    dict_reply.update(operation=OperationType.ACQ)
    inline_btn_acq = InlineKeyboardButton(
        'Знакомы' + (asterisk if attitude == Attitude.ACQ else ''),
        callback_data=callback_data_template % dict_reply,
    )

    dict_reply.update(operation=OperationType.TRUST)
    inline_btn_trust = InlineKeyboardButton(
        'Доверяю' + (asterisk if attitude == Attitude.TRUST else ''),
        callback_data=callback_data_template % dict_reply,
    )

    dict_reply.update(operation=OperationType.MISTRUST)
    inline_btn_mistrust = InlineKeyboardButton(
        'Не доверяю' + (asterisk if attitude == Attitude.MISTRUST else ''),
        callback_data=callback_data_template % dict_reply,
    )

    dict_reply.update(operation=OperationType.NULLIFY_ATTITUDE)
    inline_btn_nullify_attitude = InlineKeyboardButton(
        'Не знакомы' + (asterisk if not attitude else ''),
        callback_data=callback_data_template % dict_reply,
    )
    reply_markup.row(inline_btn_acq, inline_btn_trust)
    reply_markup.row(inline_btn_nullify_attitude, inline_btn_mistrust)
    await Misc.send_or_edit_card(bot, text, reply_markup, profile_to, tg_user_from.id, card_message)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.CANCEL_THANK,
        KeyboardType.SEP,
        # id благодарности в журнале    # 1
        # KeyboardType.SEP,
    ), c.data),
    state = None,
    )
async def process_callback_cancel_thank(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        journal_id = int(callback_query.data.split(KeyboardType.SEP)[1])
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
    reply_markup = callback_query.message.reply_markup
    if status == 200:
        text = 'Благодарность отменена'
        reply_markup = None
    elif status == 400:
        text = callback_query.message.text + '\n\n' + response['message']
    else:
        text = Misc.MSG_ERROR_API
    try:
        await callback_query.message.edit_text(text=text, reply_markup=reply_markup,)
    except:
        pass


async def geo(message, state_to_set, uuid=None):
    await state_to_set.set()
    state = dp.current_state()
    if uuid:
        async with state.proxy() as data:
            data['uuid'] = uuid
    msg_location = (
        'Пожалуйста, отправьте мне координаты вида \'74.188586, 95.790195\' '
        '(широта,долгота - удобно скопировать из приложения карт Яндекса/Гугла) '
        'или нажмите Отмена. ВНИМАНИЕ! Отправленные координаты будут опубликованы!\n'
        '\n'
        'Отправленное местоположение будет использовано для отображение профиля '
        'на картах участников голосований, опросов и на общей карте участников проекта '
        '- точное местоположение не требуется - '
        'можно выбрать ближнюю/дальнюю остановку транспорта, рынок или парк.'
    )
    await bot.send_message(
        message.chat.id,
        msg_location,
        reply_markup=Misc.reply_markup_cancel_row(),
    )

async def geo_with_location(message, state_to_set, uuid=None):

    # Старая функция geo(), в которой заточено получение координат
    # от мобильного устройства

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
            'Пожалуйста, отправьте мне координаты вида \'74.188586, 95.790195\' '
            '(широта,долгота - удобно скопировать из приложения карт Яндекса/Гугла) '
            'или нажмите Отмена. ВНИМАНИЕ! Отправленные координаты будут опубликованы!\n'
            '\n'
            'Отправленное местоположение будет использовано для отображение профиля '
            'на картах участников голосований, опросов и на общей карте участников проекта '
            '- точное местоположение не требуется - '
            'можно выбрать ближнюю/дальнюю остановку транспорта, рынок или парк.'

            #'Пожалуйста, отправьте мне координаты вида \'74.188586, 95.790195\' '
            #'(<i>широта</i>,<i>долгота</i>, '
            #'удобно скопировать из приложения карт).\n'
            #'\n'
            #'Или нажмите на кнопку "%(prompt_location)s" внизу '
            #'(на некоторых устройствах кнопка может отсутствовать).\n'
            #'\n'
            #'Чтобы отказаться - нажмите на кнопку "%(prompt_cancel_location)s" внизу '
            #'(если есть кнопка) или наберите <u>%(prompt_cancel_location)s</u>'
        ) % dict(
            prompt_location=Misc.PROMPT_LOCATION,
            prompt_cancel_location=Misc.PROMPT_CANCEL_LOCATION,
        ),
        reply_markup=keyboard
    )


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
                    await Misc.show_card(
                        response,
                        bot,
                        response_from=response_sender,
                        tg_user_from=message.from_user,
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
    content_types=('location', ContentType.TEXT,),
    state=FSMtrip.geo,
)
async def location_trip(message: types.Message, state: FSMContext):
    """
    Записать местоположение пользователя в процессе сбора данных для тура
    """
    if message.content_type == ContentType.TEXT and await is_it_command(message, state):
        return
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
    if message.content_type == ContentType.TEXT and await is_it_command(message, state):
        return
    await put_location(message, state, show_card=True)
    await state.finish()


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
            if status_from == 200:
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

async def answer_youtube_message(message, youtube_id, youtube_link):
    """
    На запрос авторизации на сайт голосования или в ответ на youtube ссылку в бот
    """
    reply = 'Коллективный разум:\n' + youtube_link
    redirect_path = settings.VOTE_URL + '#' + youtube_link
    reply_markup = InlineKeyboardMarkup()
    bot_data = await bot.get_me()
    inline_btn_redirect = InlineKeyboardButton(
        'Продолжить',
        login_url=Misc.make_login_url(
            redirect_path=redirect_path,
            bot_username=bot_data["username"],
            keep_user_data='on'
    ))
    reply_markup.row(inline_btn_redirect)
    inline_btn_scheme = InlineKeyboardButton(
        'Схема',
        login_url=Misc.make_login_url(
            redirect_path='%(graph_host)s/?videoid=%(youtube_id)s&source=yt' % dict(
                graph_host=settings.GRAPH_HOST,
                youtube_id=youtube_id,
            ),
            bot_username=bot_data['username'],
            keep_user_data='on',
        ))
    inline_btn_map = InlineKeyboardButton(
        'Карта',
        login_url=Misc.make_login_url(
            redirect_path='%(map_host)s/?videoid=%(youtube_id)s&source=yt' % dict(
                map_host=settings.MAP_HOST,
                youtube_id=youtube_id,
            ),
            bot_username=bot_data['username'],
            keep_user_data='on',
        ))
    reply_markup.row(inline_btn_scheme, inline_btn_map)
    await message.reply(reply, reply_markup=reply_markup,)

async def post_offer_answer(offer_uuid, user_from, answers):
    payload = dict(
        tg_token=settings.TOKEN,
        offer_uuid=offer_uuid,
        answers=answers,
        user_uuid=user_from and user_from['uuid'] or None,
    )
    logging.debug('post_offer, payload: %s' % Misc.secret(payload))
    status, response = await Misc.api_request(
        path='/api/offer/answer',
        method='post',
        json=payload,
    )
    logging.debug('post_offer_answer, status: %s' % status)
    logging.debug('get_offer_answer, response: %s' % response)
    return status, response


def text_offer(user_from, offer, message, bot_data):
    """
    Текст опроса-предложения

    На примере опроса 'Как дела?' с ответами Отлично (3 голоса), Хорошо (2), Плохо (0)

    Как дела?

    Голоса на <датавремя>
    Отлично - 3
    Хорошо - 2
    Плохо - 0

    Схема <graph.blagoroda.org/?offer_uuid=offerUUID>
    Карта map.blagoroda.org/?offer_id=offerUUID
    Ссылка на опрос <t.me/bot_username?start=offer-offerUUID>

    Это всё сообщение - под ним - 5 кнопок:
    Отлично
    Хорошо
    Плохо
    Отмена
    Обновить результаты
    """

    result = (
        '%(question)s\n'
        '%(multi_text)s%(closed_text)s'
        '\n'
        'Голоса на %(datetime_string)s\n'
    ) % dict(
        question=offer['question'],
        datetime_string=Misc.datetime_string(offer['timestamp'], with_timezone=True),
        multi_text='(возможны несколько ответов)\n' if offer['is_multi'] else '',
        closed_text='(опрос остановлен)\n' if offer['closed_timestamp'] else '',
    )
    for answer in offer['answers']:
        if answer['number'] > 0:
            result += '%s - %s\n' % (answer['answer'], len(answer['users']),)
    result += '\n'
    result += Misc.get_html_a(
        href='t.me/%s?start=offer-%s' % (bot_data['username'], offer['uuid'],),
        text='Ссылка на опрос'
    ) + '\n'
    result += Misc.get_html_a(
        href='%s/?offer_uuid=%s' % (settings.GRAPH_HOST, offer['uuid']),
        text='Схема'
    ) + '\n'
    result += Misc.get_html_a(
        href='%s/?offer_id=%s' % (settings.MAP_HOST, offer['uuid']),
        text='Карта'
    ) + '\n'
    result += Misc.get_html_a(
        href=Misc.get_deeplink(offer['owner'], bot_data, https=True),
        text='Автор опроса: ' + offer['owner']['first_name']
    ) + '\n'
    return result


def markup_offer(user_from, offer, message):
    reply_markup = InlineKeyboardMarkup()
    callback_data_template = '%(keyboard_type)s%(sep)s%(uuid)s%(sep)s%(number)s%(sep)s'
    callback_data_dict = dict(
        keyboard_type=KeyboardType.OFFER_ANSWER,
        uuid=offer['uuid'],
        sep=KeyboardType.SEP,
    )
    if not offer['closed_timestamp']:
        have_i_voted = False
        for answer in offer['answers']:
            if answer['number'] > 0:
                callback_data_dict.update(number=answer['number'])
                answer_text = answer['answer']
                if user_from and user_from['user_id'] in answer['users']:
                    have_i_voted = True
                    if message.chat.type == types.ChatType.PRIVATE:
                        answer_text = '(*) ' + answer_text
                inline_btn_answer = InlineKeyboardButton(
                    answer_text,
                    callback_data=callback_data_template % callback_data_dict
                )
                reply_markup.row(inline_btn_answer)

        if have_i_voted or message.chat.type != types.ChatType.PRIVATE:
            callback_data_dict.update(number=0)
            inline_btn_answer = InlineKeyboardButton(
                'Отозвать мой выбор',
                callback_data=callback_data_template % callback_data_dict
            )
            reply_markup.row(inline_btn_answer)

    callback_data_dict.update(number=-1)
    inline_btn_answer = InlineKeyboardButton(
        'Обновить результаты',
        callback_data=callback_data_template % callback_data_dict
    )
    reply_markup.row(inline_btn_answer)

    if message.chat.type == types.ChatType.PRIVATE and user_from['uuid'] == offer['owner']['uuid']:
        callback_data_dict.update(number=-2)
        inline_btn_answer = InlineKeyboardButton(
            'Сообщение участникам',
            callback_data=callback_data_template % callback_data_dict
        )
        reply_markup.row(inline_btn_answer)

        if offer['closed_timestamp']:
            callback_data_dict.update(number=-4)
            inline_btn_answer = InlineKeyboardButton(
                'Возбновить опрос',
                callback_data=callback_data_template % callback_data_dict
            )
        else:
            callback_data_dict.update(number=-3)
            inline_btn_answer = InlineKeyboardButton(
                'Остановить опрос',
                callback_data=callback_data_template % callback_data_dict
            )
        reply_markup.row(inline_btn_answer)

    return reply_markup

@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMsendMessageToOffer.ask,
)
async def got_message_to_send_to_offer(message: types.Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    state_finished = False
    async with state.proxy() as data:
        if data.get('uuid') and data.get('offer_uuid'):
            status_sender, response_sender = await Misc.post_tg_user(message.from_user)
            if status_sender == 200 and response_sender.get('uuid') == data['uuid']:
                payload = dict(
                    tg_token=settings.TOKEN,
                    user_uuid=data['uuid'],
                    offer_uuid=data['offer_uuid']
                )
                logging.debug('/api/offer/voted/tg_users %s' % Misc.secret(payload ))
                status, response = await Misc.api_request(
                    path='/api/offer/voted/tg_users',
                    method='post',
                    json=payload,
                )
                logging.debug('/api/offer/voted/tg_users, status: %s' % status)
                logging.debug('/api/offer/voted/tg_users: %s' % response)
                if status == 200:
                    n_delivered = 0
                    if response['users']:
                        bot_data = await bot.get_me()
                        msg_to = 'Сообщение участникам опроса:\n %(offer_deeplink)s\n от %(sender_deeplink)s' % dict(
                            offer_deeplink=Misc.get_html_a(
                                href='t.me/%s?start=offer-%s' % (bot_data['username'], data['offer_uuid'],),
                                text=response['question'],
                            ),
                            sender_deeplink=Misc.get_deeplink_with_name(response_sender, bot_data)
                        )
                        await Misc.state_finish(state)
                        state_finished = True
                        for user in response['users']:
                            delivered_to_user = False
                            for tg_account in user['tg_data']:
                                tg_uid = tg_account['tg_uid']
                                try:
                                    await bot.send_message(
                                        tg_uid,
                                        text=msg_to,
                                        disable_web_page_preview=True,
                                    )
                                    await bot.forward_message(
                                        tg_uid,
                                        from_chat_id=message.chat.id,
                                        message_id=message.message_id,
                                    )
                                    delivered_to_user = True
                                except (ChatNotFound, CantInitiateConversation, CantTalkWithBots,):
                                    pass
                            if delivered_to_user:
                                n_delivered += 1
                    if n_delivered == 0:
                        msg = 'Сообщение никому не отправлено'
                    else:
                        msg = 'Сообщение отправлено %s %s' % (
                            n_delivered,
                            'адресату' if n_delivered == 1 else 'адресатам',
                        )
                    await message.reply(msg)
                else:
                    await message.reply('Опрос не найден или вы не его ваделец')
    if not state_finished:
        await Misc.state_finish(state)


async def show_offer(user_from, offer, message, bot_data):
    """
    Показать опрос-предложение

    Текст получаем из text_offer(), формируем сообщение с этим текстом и с кнопками:
    Ответ 1
    Ответ 2
    ...
    Ответ N
    Отмена
    Обновить
    Кнопки будут иметь свой keyboard_type, uuid опроса, а также номер ответа:
        - для ответов 1 ... N номер будет: 1 ... N
        - для Отмена: 0
        - для Обновить: -1

    Структура offer на входе имееет вид:
    {
        'uuid': '6caf0f7f-d9f4-4c4f-a04b-4a9169f7461c',
        'owner': {'first_name': 'Евгений Супрун', 'uuid': '8f686101-c5a2-46d0-a5ee-c74386ffffff', 'id': 326},
        'question': 'How are you',
        'timestamp': 1683197002,
        'closed_timestamp': None,
        'is_multi': True,
        'answers': [
            {
                'number': 0,        // ответ с фиктивным номером 0: тот кто видел опрос, возможно голосовал
                'answer': '',       // и отменил голос
                'users': [
                    { 'id': 326, 'uuid': '8f686101-c5a2-46d0-a5ee-c74386ffffff', 'first_name': 'X Y'}
                ]
            },
            { 'number': 1, 'answer': 'Excellent', 'users': [] },
            { 'number': 2, 'answer': 'Good', 'users': [] },
            { 'number': 3, 'answer': 'Bad', 'users': []  }
        ],
        'user_answered': {'326': {'answers': [0]}} // создатель опроса его видел
    }
    """
    text = text_offer(user_from, offer, message, bot_data)
    reply_markup = markup_offer(user_from, offer, message)
    try:
        await bot.send_message(
            message.chat.id,
            text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except:
        await message.reply('Опрос-предложение предъявить не удалось')


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.OFFER_ANSWER,
        KeyboardType.SEP,
        # uuid опроса           # 1
        # KeyboardType.SEP,
        # номер ответа          # 2
        #   >= 1:   подать голос
        #      0:   отозвать голос
        #     -1:   обновить результаты
        #     -2:   сообщение, пока доступно только владельцу опроса
        #     -3:   остановить опрос
        #     -4:   возобновить опрос
        # KeyboardType.SEP,
    ), c.data),
    state = None,
    )
async def process_callback_offer_answer(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.message:
        tg_user_sender = callback_query.from_user
        code = callback_query.data.split(KeyboardType.SEP)
        try:
            offer_uuid = code[1]
            number = int(code[2])
        except (IndexError, ValueError,):
            return
        status_from, profile_from = await Misc.post_tg_user(tg_user_sender)
        if status_from != 200 or not profile_from:
            return
        if number == -2:
            # Сообщение
            await FSMsendMessageToOffer.ask.set()
            state = dp.current_state()
            async with state.proxy() as data:
                data['uuid'] = profile_from['uuid']
                data['offer_uuid'] = offer_uuid
            await callback_query.message.reply(
                (
                    'Отправьте или перешлите мне сообщение для отправки '
                    'всем проголосовавшим участникам, кроме недоверенных. '
                    'Чтобы не получить недоверия - пишите только по делу!'
                ),
                reply_markup=Misc.reply_markup_cancel_row(),
                disable_web_page_preview=True,
            )
            return

        status_answer, response_answer = await post_offer_answer(offer_uuid, profile_from, [number])
        if status_answer == 200:
            bot_data = await bot.get_me()
            text = text_offer(profile_from, response_answer, callback_query.message, bot_data)
            reply_markup = markup_offer(profile_from, response_answer, callback_query.message)
            try:
                await callback_query.message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
            except MessageNotModified:
                pass
            success_message = ''
            if number > 0:
                if response_answer['closed_timestamp']:
                    success_message = 'Владелец остановил голосование'
                else:
                    if response_answer['is_multi']:
                        num_answers = response_answer['user_answered'][str(profile_from['user_id'])]['answers']
                        success_message = 'Вы выбрали вариант%s:\n' % ('ы' if len(num_answers) > 1 else '')
                        answers_text = '\n'.join([' ' + response_answer['answers'][n]['answer'] for n in num_answers])
                        success_message += answers_text
                    else:
                        success_message = 'Вы выбрали вариант: %s' % response_answer['answers'][number]['answer']
            elif number == 0:
                if response_answer['closed_timestamp']:
                    success_message = 'Владелец остановил голосование'
                else:
                    success_message = 'Вы отозвали свой выбор'
            elif number == -3 and callback_query.message.chat.type == types.ChatType.PRIVATE:
                success_message = 'Опрос остановлен'
            elif number == -4 and callback_query.message.chat.type == types.ChatType.PRIVATE:
                success_message = 'Опрос возобновлен'
            if success_message:
                await callback_query.answer(success_message, show_alert=True,)
        elif callback_query.message.chat.type == types.ChatType.PRIVATE:
            if number > 0:
                err_mes = 'Не далось подать голос'
            elif number == 0:
                err_mes = 'Не удалось отозвать голос'
            elif number == -1:
                err_mes = 'Не удалось обновить'
            elif number == -3:
                err_mes = 'Не удалось приостановить опрос'
            elif number == -4:
                err_mes = 'Не удалось возобновить опрос'
            else:
                err_mes = 'Ошибка выполнения запроса'
            await callback_query.message.reply(err_mes)
    if profile_from.get('created'):
        await Misc.update_user_photo(bot, tg_user_sender, profile_from)


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
            try:
                await bot.send_message(
                    chat_id=tg_subscriber.id,
                    text=msg,
                    disable_web_page_preview=True
                )
            except CantInitiateConversation:
                pass
        return

    status, response_add_member = await TgGroupMember.add(
        group_chat_id=chat_id,
        group_title='',
        group_type='',
        user_tg_uid=tg_subscriber_id,
    )
    if status != 200:
        return

    data_group = response_add_member['group']
    is_channel = data_group['type'] == types.ChatType.CHANNEL
    to_to_chat = 'в канал' if is_channel else 'в группу'

    bot_data = await bot.get_me()
    dl_subscriber = Misc.get_deeplink_with_name(response_subscriber, bot_data, plus_trusts=True)
    dl_inviter = Misc.get_deeplink_with_name(response_inviter, bot_data, plus_trusts=True) if tg_inviter_id else ''
    msg_dict = dict(
        dl_subscriber=dl_subscriber,
        dl_inviter=dl_inviter,
        to_to_chat=to_to_chat,
        map_link = Misc.get_html_a(href=settings.MAP_HOST, text='карте участников'),
        group_title=data_group['title'],
    )
    msg = (
            'Ваша заявка на вступление %(to_to_chat)s %(group_title)s одобрена.\n'
            'Нажмите /setplace чтобы указать Ваше местоположение на %(map_link)s.'
    ) %  msg_dict
    if callback_query:
        await callback_query.message.reply(msg, disable_web_page_preview=True,)
    else:
        try:
            await bot.send_message(
                chat_id=tg_subscriber.id,
                text=msg,
                disable_web_page_preview=True
            )
        except CantInitiateConversation:
            pass
    if is_channel:
        reply = '%(dl_subscriber)s подключен(а)' % msg_dict
        await bot.send_message(
            chat_id,
            reply,
            disable_notification=True,
            disable_web_page_preview=True,
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
    Для формирования ссылки на доверия и карту среди участников канала

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
    if bot_.is_bot and new_chat_member.status == 'administrator':
        bot_data = await bot.get_me()
        await Misc.send_pin_group_message(chat_member.chat, bot, bot_data)

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
            ContentType.FORUM_TOPIC_CREATED,
            ContentType.FORUM_TOPIC_CLOSED,
            ContentType.FORUM_TOPIC_REOPENED,
            ContentType.FORUM_TOPIC_EDITED,
            ContentType.GENERAL_FORUM_TOPIC_HIDDEN,
            ContentType.GENERAL_FORUM_TOPIC_UNHIDDEN,
       ):
        return

    if await offer_forwarded_in_group_or_channel(message, state):
        return

    # При преобразовании группы в супергруппу сообщения:
    #   Это если юзер сделал из частной группы публичную:
    # {
    #     "update_id":178689763,
    #     \n"message":{
    #         "message_id":15251,
    #         "from":{
    #             "id":1109405488,"is_bot":false,"first_name":"...","last_name":"...",
    #             "username":"...","language_code":"ru"
    #         },
    #         "chat":{
    #             "id":-989004337,"title":"SevGroupTest","type":"group","all_members_are_administrators":false
    #         },
    #         "date":1691488438,
    #         "migrate_to_chat_id":-1001962534553
    #     }
    # },
    #   Это вслед за тем как юзер сделал из частной группы публичную,
    #   Надеюсь, что и при других случаях, когда телеграм сам преобразует
    #   группу в публичную, будет то же самое
    # {
    #     "update_id":178689764,
    #     \n"message":{
    #         "message_id":1,
    #         "from":{
    #             "id":1087968824,"is_bot":true,"first_name":"Group","username":"GroupAnonymousBot"
    #         },
    #         "sender_chat":{
    #             "id":-1001962534553,"title":"SevGroupTest","type":"supergroup"
    #         },
    #         "chat":{
    #             "id":-1001962534553,"title":"SevGroupTest","type":"supergroup"
    #         },
    #         "date":1691488438,
    #         "migrate_from_chat_id":-989004337
    #     }
    # }
    try:
        if message.migrate_to_chat_id:
            # Это сообщение может быть обработано позже чем
            # сообщение с migrate_from_chat_id и еще со старым chat_id,
            # и будет воссоздана старая группа в апи
            return
    except (TypeError, AttributeError,):
        pass
    try:
        if message.migrate_from_chat_id:
            status, response = await TgGroup.put(
                old_chat_id=message.migrate_from_chat_id,
                chat_id=message.chat.id,
                title=message.chat.title,
                type_=message.chat.type,
            )
            if status == 200:
                if message.chat.type == types.ChatType.SUPERGROUP:
                    msg_failover = 'Ура! Группа стала супергруппой'
                else:
                    # Если что-то случится при понижении статуса, то зачем об этом говорить?
                    msg_failover = ''
                if response['pin_message_id']:
                    bot_data = await bot.get_me()
                    text, reply_markup = Misc.make_pin_group_message(message.chat, bot, bot_data)
                    try:
                        await bot.edit_message_text(
                            chat_id=message.migrate_from_chat_id,
                            message_id=response['pin_message_id'],
                            text=text,
                            reply_markup=reply_markup,
                        )
                    except MessageToEditNotFound:
                        if msg_failover:
                            await bot.send_message(message.chat.id, msg_failover)
                elif msg_failover:
                    await bot.send_message(message.chat.id, msg_failover)
            return
    except (TypeError, AttributeError,):
        pass

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
    except (TypeError, AttributeError,):
        tg_user_left = None
    if tg_user_left:
        a_users_in = [ tg_user_left ]
    try:
        tg_users_new = message.new_chat_members
    except (TypeError, AttributeError,):
        tg_users_new = []
    if tg_users_new:
        a_users_in += tg_users_new

    if not tg_users_new and not tg_user_left and tg_user_sender.is_bot:
        # tg_user_sender.is_bot:
        #   анонимное послание в группу или от имени канала
        # Но делаем исключение, когда анонимный владелей
        return

    bot_data = await bot.get_me()

    logging.debug(
        f'message in group: chat_title: {message.chat.title}, '
        f'chat_id: {message.chat.id}, '
        f'message_thread_id: {message.message_thread_id}, '
        f'user_from: {message.from_user.first_name} {message.from_user.last_name}, '
        f'message text: {repr(message.text)}, '
        f'message caption: {repr(message.caption)}, '
    )

    # Предыдущее сообщение в группу было от текущего юзера:
    #   Выводим миникаточку, если
    #       -   для группы включена выдача мини карточек,
    #           message.chat.id в settings.GROUPS_WITH_CARDS
    #       -   для группы включена выдача мини карточек,
    #       -   сообщение не из топика General
    #           сообщение удовлетворяет одному из условий:
    #           *   в списке settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids']
    #               есть message.message_thread_id
    #           *   в списке settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids']
    #               есть слово 'topic_messages'
    #       -   если предыдущее сообщение было от него
    #
    is_previous_his = True
    keep_hours = None
    message.is_topic_message
    if message.chat.id in settings.GROUPS_WITH_CARDS and \
       not tg_user_left and not tg_users_new and message.from_user.id != bot_data.id and \
       message.is_topic_message and message.message_thread_id and \
       (
        message.message_thread_id in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids'] or
        'topic_messages' in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids']
       ):
        if r := redis.Redis(**settings.REDIS_CONNECT):
            last_user_in_grop_rec = (
                settings.REDIS_LAST_USERIN_GROUP_PREFIX + \
                str(message.chat.id) + \
                settings.REDIS_KEY_SEP + \
                str(message.message_thread_id)
            )
            previous_user_in_group = r.get(last_user_in_grop_rec)
            if str(previous_user_in_group) != str(message.from_user.id):
                r.set(last_user_in_grop_rec, message.from_user.id)
                is_previous_his = False
                keep_hours = settings.GROUPS_WITH_CARDS[message.chat.id].get('keep_hours')
            r.close()

    for user_in in a_users_in:
        reply_markup = None
        response_from = {}
        if user_in.is_bot:
            a_users_out.append({})
        else:
            status, response_from = await Misc.post_tg_user(user_in, did_bot_start=False)
            if status != 200:
                a_users_out.append({})
                continue
            a_users_out.append(response_from)
            if tg_user_left:
                await TgGroupMember.remove(
                    group_chat_id=message.chat.id,
                    group_title=message.chat.title,
                    group_type=message.chat.type,
                    user_tg_uid=user_in.id
                )
            else:
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
                    operation_type_id=OperationType.TRUST,
                    tg_user_id_from=tg_user_sender.id,
                    user_id_to=response_from['uuid'],
                )
                logging.debug('post operation, payload: %s' % Misc.secret(post_op))
                status, response = await Misc.api_request(
                    path='/api/addoperation',
                    method='post',
                    data=post_op,
                )
                logging.debug('post operation, status: %s' % status)
                logging.debug('post operation, response: %s' % response)

        if not tg_user_left and bot_data.id == user_in.id:
            # ЭТОТ бот подключился.
            await Misc.send_pin_group_message(message.chat, bot, bot_data)
            continue

        if not is_previous_his:
            reply_markup = InlineKeyboardMarkup()
            reply = await group_minicard_text (response_from, message.chat, bot_data)
            dict_reply = dict(
                keyboard_type=KeyboardType.TRUST_THANK,
                operation=OperationType.TRUST,
                sep=KeyboardType.SEP,
                user_to_uuid_stripped=Misc.uuid_strip(response_from['uuid']),
                message_to_forward_id='',
                group_id=message.chat.id,
            )
            callback_data_template = (
                    '%(keyboard_type)s%(sep)s'
                    '%(operation)s%(sep)s'
                    '%(user_to_uuid_stripped)s%(sep)s'
                    '%(message_to_forward_id)s%(sep)s'
                    '%(group_id)s%(sep)s'
                )
            inline_btn_thank = InlineKeyboardButton(
                'Доверяю',
                callback_data=callback_data_template % dict_reply,
            )
            reply_markup.row(inline_btn_thank)
            logging.debug('minicard in group text: '+ repr(reply))
            answer = await message.answer(
                reply,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                disable_notification=True,
            )
            if answer and keep_hours:
                if r := redis.Redis(**settings.REDIS_CONNECT):
                    s = (
                        f'{settings.REDIS_CARD_IN_GROUP_PREFIX}{settings.REDIS_KEY_SEP}'
                        f'{int(time.time())}{settings.REDIS_KEY_SEP}'
                        f'{answer.chat.id}{settings.REDIS_KEY_SEP}'
                        f'{answer.message_id}'
                    )
                    r.set(name=s, value='1')
                    r.close()


        if message.is_topic_message and \
           message.chat.id in settings.GROUPS_WITH_YOUTUBE_UPLOAD and \
           message.message_thread_id and \
           message.message_thread_id == \
           settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]['message_thread_id']:
            if message.content_type == ContentType.VIDEO and message.caption:
                try:
                    f = tempfile.NamedTemporaryFile(
                        dir=settings.DIR_TMP, suffix='.video', delete=False,
                    )
                    fname = f.name
                    f.close()
                except OSError:
                    await message.reply(
                        'Не могу отправить видео. Проблема в обработчике бота. '
                        'Не могу создать временный файл'
                    )
                else:
                    try:
                        tg_file = await bot.get_file(message.video.file_id)
                        await bot.download_file(tg_file.file_path, fname)
                    except:
                        await message.reply('Ошибка скачивания видео. Не удалил ли его кто? Не слишком ли большой файл?')
                    else:
                        response, error = upload_video(
                            fname=fname,
                            auth_data=settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]['auth_data'],
                            snippet=dict(
                                title=message.caption,
                                description='Test Description'
                        ))
                    os.unlink(fname)
            else:
                await message.reply(
                    'Здесь допускаются только <b>видео</b>, <u>обязательно с заголовком</u>, '
                    'для отправки в Youtube'
                )

    for i, response_from in enumerate(a_users_out):
        if response_from.get('created'):
            await Misc.update_user_photo(bot, a_users_in[i], response_from)


async def group_minicard_text (profile, chat, bot_data):
    reply = Misc.get_deeplink_with_name(profile, bot_data, plus_trusts=True)
    status, chat_from_api = await TgGroup.get(chat.id)
    if status == 200 and chat_from_api.get('pin_message_id'):
        if chat.username:
            href = f'https://t.me/{chat.username}/{chat_from_api["pin_message_id"]}'
        else:
            chat_id_short = str(chat.id)
            if chat_id_short.startswith('-100'):
                chat_id_short = chat_id_short[4:]
            href = f'https://t.me/c/{chat_id_short}/{chat_from_api["pin_message_id"]}'
        reply += f'\n<a href="{href}">Подробнее...</a>'
    return reply


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
        owner = await Misc.check_owner_by_uuid(owner_tg_user=callback_query.from_user, uuid=uuid)
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
    profile, owner = await check_user_delete_undelete(callback_query)
    #   owner:  Кто удаляет (если собственного) или обезличивает (сам себя)
    #   user:   его удаляем или обезличиваем

    await do_confirm_delete_profile(callback_query.message, profile, owner)


async def do_confirm_delete_profile(message, profile, owner):
    if not profile or not (profile['is_active'] or profile['owner']):
        return
    if profile['user_id'] == owner['user_id']:
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
        p_udalen = 'удалён'
        if profile.get('is_org'):
            name = profile['first_name']
            p_udalen = 'удалена организация:'
        else:
            bot_data = await bot.get_me()
            name = Misc.get_deeplink_with_name(profile, bot_data, with_lifetime_years=True,)
            if profile.get('gender') == 'f':
                p_udalen = 'удалена'
        prompt = (
            f'Будет {p_udalen} {name}!\n\n'
            'Если подтверждаете удаление, нажмите <u>Продолжить</u>. Иначе <u>Отмена</u>\n'
        )
    callback_data = (Misc.CALLBACK_DATA_UUID_TEMPLATE + '%(owner_id)s%(sep)s') % dict(
        keyboard_type=KeyboardType.DELETE_USER_CONFIRMED,
        uuid=profile['uuid'],
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
    await message.reply(prompt, reply_markup=reply_markup, disable_web_page_preview=True,)


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

    if not user or not (user['is_active'] or user['owner']):
        await Misc.state_finish(state)
        return

    if user['user_id'] == owner['user_id']:
        msg_debug = 'depersonalize user, '
        msg_deleted = 'Теперь Вы обезличены'
    else:
        msg_debug = 'delete owned user, '
        msg_deleted = 'Профиль <u>%s</u> удалён' % user['first_name']

    payload = dict(tg_token=settings.TOKEN, uuid=user['uuid'], owner_id=owner['user_id'])
    logging.debug(msg_debug + 'payload: %s' % Misc.secret(payload))
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
            await Misc.show_card(
                response,
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
    if not user or user['user_id'] != owner['user_id'] or user['is_active'] or user['owner']:
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
    if not user or user['user_id'] != owner['user_id'] or user['is_active'] or user['owner']:
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
        await Misc.show_card(
            response,
            bot,
            response_from=owner,
            tg_user_from=callback_query.from_user
        )
    await Misc.state_finish(state)


async def offer_forwarded_in_group_or_channel(message: types.Message, state: FSMContext):
    result = False
    if message.is_forward() and message.content_type == ContentType.TEXT:
        num_links = 0
        for entity in message.entities:
            m = None
            if entity.type == MessageEntityType.TEXT_LINK:
                m = re.search(r'(?:start\=offer\-|offer_uuid\=|offer_id\=)([\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12})', entity.url, flags=re.I)
            if m:
                num_links += 1
                offer_uuid = m.group(1)
            if num_links >= 2:
                status_offer, response_offer = await post_offer_answer(offer_uuid, None, [-1])
                if status_offer == 200:
                    bot_data = await bot.get_me()
                    await show_offer(None, response_offer, message, bot_data)
                    result = True
                    try:
                        await message.delete()
                    except MessageCantBeDeleted:
                        pass
                    break
    return result


@dp.channel_post_handler(
    content_types= ContentType.all(),
    state=None,
)
async def channel_post_handler(message: types.Message, state: FSMContext):
    status, response = await TgGroup.post(message.chat.id, message.chat.title, message.chat.type)
    if status != 200:
        return
    await offer_forwarded_in_group_or_channel(message, state)


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


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.INVITE,
        KeyboardType.SEP,
    ), c.data
    ), state=None,
    )
async def process_callback_invite(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Нажата кнопка "Пригласить"

    Отправить запрос на получение токена приглашения.
    По токену сформировать ссылку, ответить нажавшему кнопку
    сообщением, которое можно будет переслать в личку кому-то,
    от которого мы хотим, чтоб он объединил себя с собственным
    профилем нажавшего кнопку
    """
    if not (uuid := Misc.getuuid_from_callback(callback_query)):
        return
    message = callback_query.message
    response_sender = await Misc.check_owner_by_uuid(
        owner_tg_user=callback_query.from_user, uuid=uuid, check_owned_only=True
    )
    if not response_sender:
        return
    post_invite_set = dict(
        tg_token=settings.TOKEN,
        operation='set',
        uuid_inviter=response_sender['uuid'],
        uuid_to_merge=uuid,
    )
    logging.debug('post invite (set token), payload: %s' % Misc.secret(post_invite_set))
    status, response = await Misc.api_request(
        path='/api/token/invite/',
        method='post',
        json=post_invite_set,
    )
    logging.debug('post invite (set token), status: %s' % status)
    logging.debug('post invite (set token): %s' % response)
    reply = ''
    if status == 200:
        bot_data = await bot.get_me()
        link = Misc.get_html_a(
            href=f't.me/{bot_data["username"]}?start=invite-{response["token"]}',
            text='ссылка'
        )
        reply = (
            f'Ссылка для приглашения <b>{response_sender["response_uuid"]["first_name"]}</b> '
            f'сформирована - перешлите её адресату: {link}'
        )
    elif status == 400 and response.get("message"):
        reply = f'Ошибка:\n\n{response["message"]}'
    if reply:
        await callback_query.message.reply(reply, disable_web_page_preview=True,)


async def show_invite(profile, token_invite, message, bot_data):
    """
    Действия приглашенного пользователя
    """
    post_invite_get = dict(
        tg_token=settings.TOKEN,
        operation='get',
        token=token_invite,
        uuid_invited=profile['uuid'],
    )
    logging.debug('post invite ( token), payload: %s' % Misc.secret(post_invite_get))
    status, response = await Misc.api_request(
        path='/api/token/invite/',
        method='post',
        json=post_invite_get,
    )
    logging.debug('post invite (get token), status: %s' % status)
    logging.debug('post invite (get token): %s' % response)
    reply_markup = reply = None
    if status == 200:
        reply = (
            f'Чтобы объединить свой профиль с профилем '
            f'<b>{response["profile"]["first_name"]}</b> нажмите Продолжить'
        )
        callback_data_invite_confirm = Misc.CALLBACK_DATA_UUID_TEMPLATE % dict(
            keyboard_type=KeyboardType.INVITE_CONFIRM,
            uuid=token_invite,
            sep=KeyboardType.SEP,
        )
        inline_btn_invite_confirm = InlineKeyboardButton(
            "Продолжить",
            callback_data=callback_data_invite_confirm,
        )
        reply_markup = InlineKeyboardMarkup()
        reply_markup.row(inline_btn_invite_confirm, Misc.inline_button_cancel())
        await FSMinviteConfirm.ask.set()
    elif status == 400 and response.get("message"):
        reply = f'Ошибка:\n\n{response["message"]}'
    else:
        reply = Misc.MSG_ERROR_API
    if reply:
        await message.reply(reply, reply_markup=reply_markup, disable_web_page_preview=True,)


@dp.callback_query_handler(
    lambda c: c.data and re.search(Misc.RE_KEY_SEP % (
        KeyboardType.INVITE_CONFIRM,
        KeyboardType.SEP,
    ), c.data
    ), state=FSMinviteConfirm.ask,
    )
async def process_callback_invite_confirm(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Пользователь подтверждает приглашение

    В токене есть всё необходимое
    """
    reply = None
    if token_invite := Misc.getuuid_from_callback(callback_query):
        status_sender, response_sender = await Misc.post_tg_user(callback_query.from_user)
        if status_sender == 200:
            post_invite_accept = dict(
                tg_token=settings.TOKEN,
                operation='accept',
                token=token_invite,
                uuid_invited=response_sender['uuid'],
            )
            logging.debug('post invite (accept token), payload: %s' % Misc.secret(post_invite_accept))
            status, response = await Misc.api_request(
                path='/api/token/invite/',
                method='post',
                json=post_invite_accept,
            )
            logging.debug('post invite (accept token), status: %s' % status)
            logging.debug('post invite (accept token): %s' % response)
            if status == 200:
                await callback_query.message.reply(
                    'Добро пожаловать в родственную сеть',
                    disable_web_page_preview=True,
                )
                await Misc.show_card(
                    response['profile'],
                    bot,
                    response_from=response_sender,
                    tg_user_from=callback_query.from_user
                )
            elif status == 400 and response.get("message"):
                reply = f'Ошибка:\n\n{response["message"]}'
            else:
                reply = 'Ошибка:\n\nОбратитесь в поддежку: /feedback'
        else:
            reply = Misc.MSG_ERROR_API
    if reply:
        await callback_query.message.reply(reply, disable_web_page_preview=True,)
    await Misc.state_finish(state)


@dp.message_handler(
    ChatTypeFilter(chat_type=types.ChatType.PRIVATE),
    content_types=ContentType.all(),
    state=FSMinviteConfirm.ask,
)
async def process_invite_confirm_message(message: types.Message, state: FSMContext):
    if await is_it_command(message, state):
        return
    await message.reply('Ожидается ответ на вопрос о приглашении', disable_web_page_preview=True,)


async def cron_remove_cards_in_group():
    if not settings.GROUPS_WITH_CARDS:
        return
    from datetime import datetime
    if r := redis.Redis(**settings.REDIS_CONNECT):
        time_current = int(time.time())
        for key in r.scan_iter(settings.REDIS_CARD_IN_GROUP_PREFIX + '*'):
            try:
                (prefix, tm, chat_id, message_id) = key.split(settings.REDIS_KEY_SEP)
                tm = int(tm); chat_id = int(chat_id); message_id = int(message_id)
                if chat_id in settings.GROUPS_WITH_CARDS and settings.GROUPS_WITH_CARDS[chat_id].get('keep_hours'):
                    try:
                        keep_secs = int(settings.GROUPS_WITH_CARDS[chat_id]['keep_hours']) * 3600
                        if tm + keep_secs < time_current:
                            try:
                                await bot.delete_message(chat_id=chat_id, message_id=message_id)
                            except:
                                pass
                            r.expire(key, 10)
                    except (ValueError, TypeError,):
                        r.expire(key, 10)
                else:
                    r.expire(key, 10)
            except ValueError:
                r.expire(key, 10)
        r.close()

# ---------------------------------

if __name__ == '__main__':

    scheduler = AsyncIOScheduler()
    scheduler.add_job(cron_remove_cards_in_group, 'cron', day_of_week='mon-sun', hour=0, minute=1,)
    scheduler.start()

    if settings.START_MODE == 'poll':
        start_polling(
            dp,
            timeout=20,
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
