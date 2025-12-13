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
    try:
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
                    except TelegramBadRequest:
                        # Не удалось отредактировать старое сообщение - ничего страшного
                        pass
                logging.info(f"Группа мигрирована: {message.migrate_from_chat_id} -> {message.chat.id}")
                return
        except (TypeError, AttributeError,):
            pass

        # Игнорируем сообщения от ботов (кроме нашего)
        if tg_user_sender.is_bot and tg_user_sender.id != bot_data.id:
            return

        logging.debug(
            f'Сообщение в группе: chat_title: {message.chat.title}, '
            f'chat_id: {message.chat.id}, '
            f'message_thread_id: {message.message_thread_id}, '
            f'user_from: {message.from_user.first_name} {message.from_user.last_name}, '
            f'text: {repr(message.text)}, '
            f'caption: {repr(message.caption)}, '
        )

        # Обработка мини-карточек для пользователей в топиках
        if (message.chat.id in settings.GROUPS_WITH_CARDS and 
            message.from_user.id != bot_data.id and
            message.is_topic_message and message.message_thread_id and
            (message.message_thread_id in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids'] or
             'topic_messages' in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids'])):
            
            try:
                if r := redis.Redis(**settings.REDIS_CONNECT):
                    last_user_in_group_rec = (
                        Rcache.LAST_USER_IN_GROUP_PREFIX + 
                        str(message.chat.id) + 
                        Rcache.KEY_SEP + 
                        str(message.message_thread_id)
                    )
                    previous_user_in_group = r.get(last_user_in_group_rec)
                    
                    if str(previous_user_in_group) != str(message.from_user.id):
                        r.setex(last_user_in_group_rec, 3600, message.from_user.id)  # TTL 1 час
                        
                        # Получаем данные пользователя
                        status, user_data = await Misc.post_tg_user(message.from_user, did_bot_start=False)
                        
                        if status == 200:
                            reply = await Misc.group_minicard_text(user_data, message.chat)
                            dict_reply = dict(
                                keyboard_type=KeyboardType.TRUST_THANK,
                                operation=OperationType.TRUST,
                                sep=KeyboardType.SEP,
                                user_to_uuid_stripped=Misc.uuid_strip(user_data['uuid']),
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
                            
                            logging.debug('minicard in group text: ' + repr(reply))
                            await message.answer(
                                reply,
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_btn_thank]]),
                                disable_notification=True,
                            )
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
                                message.from_user.id,
                                f'Ошибка загрузки видео на YouTube'
                            )
                        except (TelegramBadRequest, TelegramForbiddenError):
                            pass
                    
                    # Удаляем временный файл
                    if not settings.LOCAL_SERVER and fname and os.path.exists(fname):
                        os.unlink(fname)
    
    except Exception as e:
        logging.error(f"Ошибка в process_group_message: {e}", exc_info=True)