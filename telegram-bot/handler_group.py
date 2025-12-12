# handler_group.py
#
# Команды и сообщения в группы и каналы

import base64, re, hashlib, redis, time, tempfile, os

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ContentType, InlineKeyboardMarkup, InlineKeyboardButton, \
                          ChatJoinRequest, CallbackQuery, ChatMemberUpdated, LinkPreviewOptions
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.enums.message_entity_type import MessageEntityType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from youtube_upload import upload_video

from common import Misc, KeyboardType, OperationType, TgGroup, TgGroupMember, Rcache
from handler_offer import Offer

import settings, me
from settings import logging


router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

@router.chat_member(F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL)))
async def handle_chat_member_update(chat_member: ChatMemberUpdated):
    """
    Обработка событий обновления статуса участников чата
    Включает в себя вступление/выход пользователей и добавление/удаление бота
    """
    try:
        old_status = chat_member.old_chat_member.status
        new_status = chat_member.new_chat_member.status
        
        chat = chat_member.chat
        user = chat_member.new_chat_member.user
        
        logging.info(
            f"ChatMemberUpdated: chat_id={chat.id}, title={chat.title}, type={chat.type}, "
            f"user_id={user.id}, username={user.username or 'no_username'}, "
            f"old_status={old_status}, new_status={new_status}"
        )
        
        # Обработка добавления/удаления нашего бота в группу/канал
        if user.id == bot_data.id:
            if new_status in ("administrator", "member"):
                # Бота добавили в группу/канал
                status, response = await TgGroup.post(chat.id, chat.title, chat.type)
                if status == 200:
                    logging.info(f"Бот добавлен в {chat.type}: {chat.title} (ID: {chat.id})")
                    # Отправляем приветственное сообщение
                    await Misc.send_pin_group_message(chat)
                    
                    # Добавляем пользователя, который добавил бота, в базу и в группу
                    if chat_member.from_user and not chat_member.from_user.is_bot:
                        try:
                            status_user, user_data = await Misc.post_tg_user(chat_member.from_user, did_bot_start=False)
                            if status_user == 200:
                                await TgGroupMember.add(
                                    group_chat_id=chat.id,
                                    group_title=chat.title,
                                    group_type=chat.type,
                                    user_tg_uid=chat_member.from_user.id
                                )
                                logging.info(f"Пользователь {chat_member.from_user.id} добавлен в группу при добавлении бота")
                        except Exception as user_err:
                            logging.error(f"Ошибка при добавлении пользователя: {user_err}")
                else:
                    logging.error(f"Ошибка при сохранении группы в базе: {response}")
            elif new_status in ("left", "kicked"):
                # Бота удалили из группы/канала
                logging.info(f"Бот удален из {chat.type}: {chat.title} (ID: {chat.id})")
            return
        
        # Обработка вступления/выхода пользователей (только для групп)
        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            # Пользователь присоединился к группе
            if old_status in ("left", "kicked", "restricted") and new_status in ("member", "administrator"):
                if not user.is_bot:
                    try:
                        # Создаем пользователя в базе если его нет
                        status, user_data = await Misc.post_tg_user(user, did_bot_start=False)
                        if status == 200:
                            # Добавляем пользователя в члены группы
                            await TgGroupMember.add(
                                group_chat_id=chat.id,
                                group_title=chat.title,
                                group_type=chat.type,
                                user_tg_uid=user.id
                            )
                            logging.info(f"Пользователь {user.username or user.id} добавлен в группу {chat.title}")
                        
                        # Записываем в Redis последнего пользователя для топиков
                        try:
                            if r := redis.Redis(**settings.REDIS_CONNECT):
                                last_user_in_group_rec = (
                                    Rcache.LAST_USER_IN_GROUP_PREFIX + 
                                    str(chat.id)
                                )
                                r.setex(last_user_in_group_rec, 3600, user.id)  # TTL 1 час
                                r.close()
                        except Exception as redis_err:
                            logging.error(f"Ошибка Redis при записи пользователя: {redis_err}")
                    except Exception as e:
                        logging.error(f"Ошибка при добавлении пользователя в группу: {e}")
            
            # Пользователь покинул группу
            elif old_status in ("member", "administrator") and new_status in ("left", "kicked"):
                if not user.is_bot:
                    try:
                        # Удаляем пользователя из членов группы
                        await TgGroupMember.remove(
                            group_chat_id=chat.id,
                            group_title=chat.title,
                            group_type=chat.type,
                            user_tg_uid=user.id
                        )
                        logging.info(f"Пользователь {user.username or user.id} удален из группы {chat.title}")
                    except Exception as e:
                        logging.error(f"Ошибка при удалении пользователя из группы: {e}")
    
    except Exception as e:
        logging.error(f"Ошибка в обработчике ChatMemberUpdated: {e}", exc_info=True)

# Также добавляем обработчик my_chat_member для получения событий о самом боте
@router.my_chat_member(F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL)))
async def handle_my_chat_member_update(chat_member: ChatMemberUpdated):
    """
    Обработка событий обновления статуса самого бота
    (дублирует handle_chat_member_update для my_chat_member)
    """
    await handle_chat_member_update(chat_member)

@router.message(F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP)), StateFilter(None))
async def process_group_message(message: Message, state: FSMContext):
    """
    Обработка обычных сообщений в группе и логика миграции группы в супергруппу
    """
    logging.debug(f'process_group_message called: chat_id={message.chat.id}, chat_title={message.chat.title}')
    
    # Enhanced logging for join scenarios
    if message.new_chat_members:
        for user in message.new_chat_members:
            logging.info(f'NEW_MEMBER_DETECTED: User {user.id} ({user.first_name} {user.last_name}) joined group {message.chat.id} ({message.chat.title}) via invite link')
            if user.username:
                logging.debug(f'User {user.id} username: @{user.username}')
    
    tg_user_sender = message.from_user

        # Игнорируем системные сообщения от Telegram
        if tg_user_sender.id == 777000:
            return

        # Игнорируем служебные обновления чата
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

        # Обработка оферов (если нужно)
        # if await Offer.offer_forwarded_in_group_or_channel(message, state):
        #     return

        # Обработка миграции группы в супергруппу
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
                if status == 200 and response.get('pin_message_id'):
                    text, reply_markup = Misc.make_pin_group_message(message.chat)
                    try:
                        await bot.edit_message_text(
                            chat_id=message.migrate_from_chat_id,
                            message_id=response['pin_message_id'],
                            text=text,
                            reply_markup=reply_markup,
                        )
                    except TelegramBadRequest as e:
                        logging.debug(f'TelegramBadRequest while editing pin message: {e}')
            return
    except (TypeError, AttributeError,) as e:
        logging.debug(f'Error accessing migrate_from_chat_id: {e}')
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
        logging.debug(f'Accessed left_chat_member: {tg_user_left}')
    except Exception as e:
        logging.debug(f'Exception accessing left_chat_member: {type(e).__name__}: {e}')
        tg_user_left = None
    if tg_user_left:
        a_users_in = [ tg_user_left ]
        logging.debug(f'Processing user who left group: {tg_user_left.id} ({tg_user_left.first_name})')
    try:
        tg_users_new = message.new_chat_members
        logging.debug(f'Accessed new_chat_members: {tg_users_new}')
    except (TypeError, AttributeError,) as e:
        logging.debug(f'Exception accessing new_chat_members: {type(e).__name__}: {e}')
        tg_users_new = []
    if tg_users_new:
        a_users_in += tg_users_new
    
    # Deduplicate users to avoid duplicate API calls
    seen_user_ids = set()
    unique_users = []
    for user in a_users_in:
        if user.id not in seen_user_ids:
            seen_user_ids.add(user.id)
            unique_users.append(user)
    if len(a_users_in) != len(unique_users):
        logging.debug(f'Deduplicated {len(a_users_in)} users to {len(unique_users)} unique users')
    a_users_in = unique_users

    if not tg_users_new and not tg_user_left and tg_user_sender.is_bot:
        # tg_user_sender.is_bot:
        #   анонимное послание в группу или от имени канала
        # Но делаем исключение, когда анонимный владелей
        logging.debug('Skipping anonymous/channel message')
        return

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
    if message.chat.id in settings.GROUPS_WITH_CARDS and \
       not tg_user_left and not tg_users_new and message.from_user.id != bot_data.id and \
       message.is_topic_message and message.message_thread_id and \
       (
        message.message_thread_id in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids'] or
        'topic_messages' in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids']
       ):
        if r := redis.Redis(**settings.REDIS_CONNECT):
            last_user_in_grop_rec = (
                Rcache.LAST_USER_IN_GROUP_PREFIX + \
                str(message.chat.id) + \
                Rcache.KEY_SEP + \
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
            logging.debug(f'Skipping bot user {user_in.id} ({user_in.first_name})')
            a_users_out.append({})
        else:
            logging.debug(f'Processing user {user_in.id} ({user_in.first_name}) - is_new_member: {user_in in tg_users_new}, is_left_user: {tg_user_left and user_in.id == tg_user_left.id}')
            status, response_from = await Misc.post_tg_user(user_in, did_bot_start=False)
            if status != 200:
                logging.error(f'CRITICAL: Failed to create/update user {user_in.id} ({user_in.first_name}), status: {status}, response: {response_from}')
                a_users_out.append({})
                continue
            else:
                logging.debug(f'SUCCESS: User {user_in.id} ({user_in.first_name}) created/updated successfully')
            a_users_out.append(response_from)
            if tg_user_left:
                logging.debug(f'Removing user {user_in.id} from group (left user: {tg_user_left.id} {tg_user_left.first_name})')
                await TgGroupMember.remove(
                    group_chat_id=message.chat.id,
                    group_title=message.chat.title,
                    group_type=message.chat.type,
                    user_tg_uid=user_in.id
                )
                if status_remove != 200:
                    logging.error(f'CRITICAL: Failed to remove user {user_in.id} from group {message.chat.id}, status: {status_remove}, response: {response_remove}')
                else:
                    logging.debug(f'SUCCESS: User {user_in.id} removed from group {message.chat.id}')
            else:
                logging.debug(f'No user left detected, skipping removal logic')
                
                # Only add user to database if they are actually in the group
                # This prevents adding users when invite links are expired
                if tg_users_new and user_in in tg_users_new:
                    try:
                        # Check if user is actually a member of the group
                        chat_member = await bot.get_chat_member(message.chat.id, user_in.id)
                        if chat_member.status in ('member', 'administrator', 'creator'):
                            logging.debug(f'User {user_in.id} is confirmed as group member, adding to database')
                            await TgGroupMember.add(
                                group_chat_id=message.chat.id,
                                group_title=message.chat.title,
                                group_type=message.chat.type,
                                user_tg_uid=user_in.id
                            )
                        else:
                            logging.debug(f'User {user_in.id} is not a group member (status: {chat_member.status}), skipping database addition')
                    except (TelegramBadRequest, TelegramForbiddenError) as e:
                        logging.debug(f'Failed to verify user {user_in.id} membership status: {e}, skipping database addition')
                else:
                    # Regular message processing (not a new member)
                    logging.debug(f'Processing regular message from user {user_in.id}')
            if tg_users_new and \
               tg_user_sender.id != user_in.id:
                # Сразу доверие c благодарностью добавляемому пользователю
                logging.debug(f'Adding trust operation from {tg_user_sender.id} to {user_in.id}')
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
            logging.debug('Bot connected to group, sending pin message')
            await Misc.send_pin_group_message(message.chat)
            continue

        if not is_previous_his:
            logging.debug(f'Sending minicard for user {user_in.id}')
            reply = await Misc.group_minicard_text (response_from, message.chat)
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
                text='Доверяю',
                callback_data=callback_data_template % dict_reply,
            )
            logging.debug('minicard in group text: '+ repr(reply))
            answer = await message.answer(
                reply,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_btn_thank]]),
                disable_notification=True,
            )
            if answer and keep_hours:
                if r := redis.Redis(**settings.REDIS_CONNECT):
                    s = (
                        f'{Rcache.CARD_IN_GROUP_PREFIX}{Rcache.KEY_SEP}'
                        f'{int(time.time())}{Rcache.KEY_SEP}'
                        f'{answer.chat.id}{Rcache.KEY_SEP}'
                        f'{answer.message_id}'
                    )
                    r.set(name=s, value='1')
                    r.close()
            except Exception as redis_err:
                logging.error(f"Ошибка Redis при работе с карточками: {redis_err}")

        # Обработка загрузки видео на YouTube для специальных топиков
        if (message.is_topic_message and
            message.chat.id in settings.GROUPS_WITH_YOUTUBE_UPLOAD and
            message.message_thread_id and
            message.message_thread_id == 
            settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]['message_thread_id']):
            
            if message.content_type == ContentType.VIDEO:
                # Получаем данные пользователя
                status, user_data = await Misc.post_tg_user(message.from_user, did_bot_start=False)
                
                # Генерируем заголовок на основе даты и времени, если его нет
                title = message.caption if message.caption else f"Видео от {message.date.strftime('%d.%m.%Y %H:%M UTC')}"
                
                fname = None
                if settings.LOCAL_SERVER:
                    try:
                        tg_file = await bot.get_file(message.video.file_id)
                        fname = tg_file.file_path
                    except Exception as e:
                        logging.error(f"Ошибка получения файла: {e}")
                else:
                    f = tempfile.NamedTemporaryFile(
                        dir=settings.DIR_TMP, suffix='.video', delete=False,
                    )
                    fname = f.name
                    f.close()
                    try:
                        tg_file = await bot.get_file(message.video.file_id)
                        await bot.download_file(tg_file.file_path, fname)
                    except Exception as e:
                        logging.error(f"Ошибка скачивания файла: {e}")
                        os.unlink(fname)
                        fname = None
                
                if not fname:
                    try:
                        await bot.send_message(
                            message.from_user.id,
                            'Ошибка скачивания видео из сообщения. Не слишком ли большой файл?'
                        )
                    except (TelegramBadRequest, TelegramForbiddenError):
                        pass
                else:
                    description = (
                        f'Профиль автора: {user_data["first_name"]}, '
                        f'{Misc.get_deeplink(user_data, https=True)}\n'
                        f'Группа телеграм: '
                        f'{settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]["url_group"]}'
                    )
                    
                    try:
                        response, error = upload_video(
                            fname=fname,
                            auth_data=settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]['auth_data'],
                            snippet=dict(
                                title=title,
                                description=description,
                            ))
                        
                        if error:
                            try:
                                await bot.send_message(
                                    message.from_user.id,
                                    f'Ошибка загрузки видео:\n{error}'
                                )
                            except (TelegramBadRequest, TelegramForbiddenError):
                                pass
                        else:
                            href = f'https://www.youtube.com/watch?v={response["id"]}'
                            try:
                                await bot.send_message(
                                    message.from_user.id, (
                                        f'Видео {Misc.get_html_a(href, title)} загружено.\n'
                                        f'Автор: {Misc.get_deeplink_with_name(user_data, plus_trusts=True)}'
                                    ),
                                    link_preview_options=LinkPreviewOptions(is_disabled=False),
                                )
                            except Exception as e:
                                logging.error(f"Ошибка отправки сообщения о загрузке видео: {e}")
                    except Exception as upload_err:
                        logging.error(f"Ошибка загрузки видео на YouTube: {upload_err}")
                        try:
                            await bot.send_message(
                                tg_user_sender.id, (
                                    f'Видео {Misc.get_html_a(href, title)} загружено.\n'  # Используем title вместо message.caption
                                    f'Автор: {Misc.get_deeplink_with_name(response_from, plus_trusts=True)}'
                                ),
                                link_preview_options=LinkPreviewOptions(is_disabled=False),
                            )
                        except Exception as e:
                            logging.debug(f'Failed to send success message: {e}')
                            pass
                if not settings.LOCAL_SERVER and fname:
                    logging.debug(f'Cleaning up temporary file: {fname}')
                    os.unlink(fname)

@router.my_chat_member(F.chat.type.in_((ChatType.CHANNEL,)))
async def echo_my_chat_member_for_bot(chat_member: ChatMemberUpdated):
    """
    Для формирования ссылки на доверия и карту среди участников канала

    Реакция на подключение к каналу бота
    """
    logging.debug(f'echo_my_chat_member_for_bot called: chat_id={chat_member.chat.id}, chat_title={chat_member.chat.title}')
    
    new_chat_member = chat_member.new_chat_member
    bot_ = new_chat_member.user
    tg_user_from = chat_member.from_user
    
    logging.debug(f'new_chat_member status: {new_chat_member.status}, bot: {bot_.is_bot}')
    logging.debug(f'tg_user_from: {tg_user_from}')
    
    if tg_user_from and not tg_user_from.is_bot:
        logging.debug(f'Processing regular user: {tg_user_from.id} ({tg_user_from.first_name})')
        status, user_from = await Misc.post_tg_user(tg_user_from, did_bot_start=False)
        if status == 200:
            logging.debug(f'User created/updated successfully, adding to group')
            await TgGroupMember.add(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type, tg_user_from.id)
        else:
            logging.debug(f'Failed to create/update user, status: {status}')
            return
    else:
        logging.debug(f'Processing bot/group event')
        status, response = await TgGroup.post(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type)
        if status != 200:
            logging.debug(f'Failed to create/update group, status: {status}')
            return
    if bot_.is_bot and new_chat_member.status == 'administrator':
        logging.debug(f'Bot is administrator, sending pin message')
        await Misc.send_pin_group_message(chat_member.chat)


@router.chat_join_request()
async def echo_join_chat_request(message: ChatJoinRequest):
    """
    Пользователь присоединяется к каналу/группе по ссылке- приглашению

    Работает только ссылка, требующая одобрения.
    Бот, он всегда администратор канала/группы, одобрит.
    Но до этого:
        Нового участника надо завести в базе, если его там нет
        В канал/группу отправится мини- карточка нового участника
    """
    logging.debug(f'echo_join_chat_request called: chat_id={message.chat.id}, chat_title={message.chat.title}')
    
    tg_subscriber = message.from_user
    tg_inviter = message.invite_link.creator if message.invite_link else None
    
    logging.info(f'JOIN_REQUEST: User {tg_subscriber.id} ({tg_subscriber.first_name} {tg_subscriber.last_name}) requesting to join group {message.chat.id} ({message.chat.title})')
    logging.debug(f'New subscriber: {tg_subscriber.id} ({tg_subscriber.first_name})')
    logging.debug(f'Invite creator: {tg_inviter.id if tg_inviter else None}')
    if message.invite_link:
        logging.debug(f'Invite link: {message.invite_link.invite_link}')
        logging.debug(f'Invite link name: {message.invite_link.name}')
    
    if tg_inviter:
        logging.debug(f'Processing invite creator')
        status_inviter, response_inviter = await Misc.post_tg_user(tg_inviter, did_bot_start=False)
        if status_inviter != 200:
            logging.debug(f'Failed to create/update inviter, status: {status_inviter}')
            return
        # Владельца канала/группы сразу в канал/группу. Вдруг его там нет
        #
        await TgGroupMember.add(
            group_chat_id=message.chat.id,
            group_title=message.chat.title,
            group_type=message.chat.type,
            user_tg_uid=tg_inviter.id,
        )

    is_channel = message.chat.type == ChatType.CHANNEL
    logging.debug(f'Chat type: {message.chat.type}, is_channel: {is_channel}')
    
    status, response_subscriber = await Misc.post_tg_user(tg_subscriber, did_bot_start=False)
    if status != 200:
        logging.error(f'CRITICAL: Failed to create/update subscriber {tg_subscriber.id}, status: {status}, response: {response_subscriber}')
        return
        
    logging.info(f'APPROVING_JOIN: Approving chat join request for user {tg_subscriber.id} ({tg_subscriber.first_name})')
    try:
        await bot.approve_chat_join_request(
                message.chat.id,
                tg_subscriber.id
        )
        logging.info(f'SUCCESS: Chat join request approved for user {tg_subscriber.id}')
    except TelegramBadRequest as excpt:
        logging.error(f'TELEGRAM_ERROR: BadRequest while approving join request for user {tg_subscriber.id}: {excpt.message}')
        in_chat = 'в канале' if is_channel else 'в группе'
        msg = f'Возможно, вы уже {in_chat}'
        if excpt.message == 'User_already_participant':
            msg = f'Вы уже {in_chat}'
            logging.warning(f'JOIN_REQUEST: User {tg_subscriber.id} already a participant')
        try:
            await bot.send_message(
                chat_id=tg_subscriber.id,
                text=msg,
            )
            logging.debug(f'Sent message to user {tg_subscriber.id} about existing membership')
            return
        except (TelegramBadRequest, TelegramForbiddenError,) as e:
            logging.error(f'FAILED_TO_NOTIFY: Failed to send message to subscriber {tg_subscriber.id}: {e}')
            pass
    except Exception as e:
        logging.error(f'UNEXPECTED_ERROR: Unexpected error while approving join request for user {tg_subscriber.id}: {type(e).__name__}: {e}')
        return

    logging.info(f'ADDING_TO_DB: Adding subscriber {tg_subscriber.id} ({tg_subscriber.first_name}) to group database')
    status, response_add_member = await TgGroupMember.add(
        group_chat_id=message.chat.id,
        group_title=message.chat.title,
        group_type=message.chat.type,
        user_tg_uid=tg_subscriber.id,
    )
    if status != 200:
        logging.error(f'CRITICAL: Failed to add subscriber {tg_subscriber.id} to group {message.chat.id}, status: {status}, response: {response_add_member}')
        return
    else:
        logging.info(f'SUCCESS: Subscriber {tg_subscriber.id} added to group {message.chat.id}')

    to_chat = 'в канал' if is_channel else 'в группу'
    dl_subscriber = Misc.get_deeplink_with_name(response_subscriber, plus_trusts=True)
    msg_dict = dict(
        dl_subscriber=dl_subscriber,
        to_chat=to_chat,
        map_link = Misc.get_html_a(href=settings.MAP_HOST, text='карте участников'),
        group_title=message.chat.title,
    )
    msg = (
            'Ваша заявка на вступление %(to_chat)s %(group_title)s одобрена.\n'
            'Нажмите /setplace чтобы указать Ваше местоположение на %(map_link)s.'
    ) %  msg_dict
    
    logging.debug(f'Sending welcome message to subscriber')
    try:
        await bot.send_message(chat_id=tg_subscriber.id, text=msg)
    except (TelegramBadRequest, TelegramForbiddenError,) as e:
        logging.debug(f'Failed to send welcome message: {e}')
        pass
        
    if is_channel:
        reply = '%(dl_subscriber)s подключен(а)' % msg_dict
        logging.debug(f'Sending announcement in channel')
        await bot.send_message(
            message.chat.id,
            reply,
            disable_notification=True,
        )
