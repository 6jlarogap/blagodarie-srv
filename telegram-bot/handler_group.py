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

import logging
import settings
import me
dp, bot, bot_data = me.dp, me.bot, me.bot_data

router = Router()

@router.message(F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP)), StateFilter(None))
async def process_group_message(message: Message, state: FSMContext):
    """
    Обработка сообщений в группу
    """
    logging.debug("TEST: process_group_message handler called")

    dedup_key = f"msg_dedup:{message.chat.id}:{message.message_id}"
    
    if r := redis.Redis(**settings.REDIS_CONNECT):
        try:
            # Пытаемся установить ключ с временем жизни 5 минут
            # Если ключ уже существует (возвращает 0) - сообщение уже обрабатывалось
            if not r.set(dedup_key, "1", ex=300, nx=True):
                logging.debug(f"Message {message.message_id} already processed, skipping")
                return
            logging.debug(f"Message {message.message_id} added to Redis")
        except Exception as e:
            logging.error(f"Redis dedup error: {str(e)}")
            # В случае ошибки Redis продолжаем обработку
        finally:
            r.close()

    tg_user_sender = message.from_user

    # tg_user_sender.id == 777000:
    #   Если к группе привязан канал, то сообщения идут от этого пользователя
    #
    if tg_user_sender.id == 777000:
        logging.debug("TEST: filtered tg_user_sender.id == 777000")
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
        logging.debug("TEST: filtered content type {message.content_type}")
        return

    #
    # Это отработано.
    # Пересылается офер в группу, и бот формирует офер с кнопками
    # if await Offer.offer_forwarded_in_group_or_channel(message, state):
    #     return

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
            logging.debug("TEST: return from message.migrate_to_chat_id")
            return
    except (TypeError, AttributeError,):
        logging.debug("ERROR: try message.migrate_to_chat_id")
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
                logging.debug("TEST: migrate TgGroup.put {status}")                   
#                if response['pin_message_id']:
                if response.get('pin_message_id'):
                    logging.debug("TEST: pin_message_id= {pin_message_id}")
                    text, reply_markup = Misc.make_pin_group_message(message.chat)
                    try:
                        await bot.edit_message_text(
                            chat_id=message.migrate_from_chat_id,
                            message_id=response['pin_message_id'],
                            text=text,
                            reply_markup=reply_markup,
                        )
                        logging.debug("TEST: migrate edit pin message")
                    except (TelegramBadRequest, TelegramForbiddenError) as e:
                        logging.error(f"Failed to edit pin message: {str(e)}")
            else:
                logging.debug("ERROR: TgGroup.put")

    except (TypeError, AttributeError,):
        pass

    try:
        status, response_from = await Misc.post_tg_user(tg_user_sender, did_bot_start=False)
        await TgGroupMember.add(
            group_chat_id=message.chat.id,
            group_title=message.chat.title,
            group_type=message.chat.type,
            user_tg_uid=tg_user_sender.id
        )
        logging.debug("TEST: TgGroupMember.add")
    except Exception as e:
        logging.debug("ERROR: TgGroupMember.add")
        return
    
    if tg_user_sender.is_bot:
        return

    logging.debug(
        f'message in group: chat_title: {message.chat.title}, '
        f'chat_id: {message.chat.id}, '
        f'message_thread_id: {message.message_thread_id}, '
        f'user_from: {message.from_user.first_name} {message.from_user.last_name}, '
        f'message text: {repr(message.text)}, '
        f'message caption: {repr(message.caption)}, '
        f'content_type: {message.content_type}, '  # Добавить тип контента
        f'media_group_id: {message.media_group_id if message.media_group_id else "None"}'
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
    logging.debug(
        "TEST: Before GROUPS_WITH_CARDS"
        f'message.chat.id: {message.chat.id if message.chat.id else "None"}'
        f'message.from_user.id: {message.from_user.id if message.from_user.id else "None"}'
        f'bot_data.id: {bot_data.id if bot_data.id else "None"}'
        f'message.is_topic_message: {message.is_topic_message if message.is_topic_message else "None"}'
        f'message.message_thread_id: {message.message_thread_id if message.message_thread_id else "None"}'
        f'message.chat.id: {message.chat.id if message.chat.id else "None"}'
    )

    is_previous_his = True
    keep_hours = None
    if message.chat.id in settings.GROUPS_WITH_CARDS and \
       message.from_user.id != bot_data.id and \
       message.is_topic_message and message.message_thread_id and \
       (
        message.message_thread_id in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids'] or
        'topic_messages' in settings.GROUPS_WITH_CARDS[message.chat.id]['message_thread_ids']
       ):
        logging.debug("TEST: GROUPS_WITH_CARDS")
       
        if r := redis.Redis(**settings.REDIS_CONNECT):
            try:
                last_user_in_grop_rec = (
                    Rcache.LAST_USER_IN_GROUP_PREFIX + \
                    str(message.chat.id) + \
                    Rcache.KEY_SEP + \
                    str(message.message_thread_id)
                )
                logging.debug("TEST: last_user_in_grop_rec")
                previous_user_in_group = r.get(last_user_in_grop_rec)
                if str(previous_user_in_group) != str(message.from_user.id):
                    r.set(last_user_in_grop_rec, message.from_user.id)
                    is_previous_his = False
                    keep_hours = settings.GROUPS_WITH_CARDS[message.chat.id].get('keep_hours')
                    logging.debug("TEST: is_previous_his = False")
            except Exception as e:
                logging.error(f"Redis operation failed: {str(e)}")
            finally:
                r.close()

        if not is_previous_his:
            logging.debug("TEST: not is_previous_his")
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
            try:
                answer = await message.answer(
                    reply,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_btn_thank]]),
                    disable_notification=True,
                )
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                logging.error(f"Failed to send minicard group message: {str(e)}")
                return
            if answer and keep_hours:
                if r := redis.Redis(**settings.REDIS_CONNECT):
                    try:
                        s = (
                            f'{Rcache.CARD_IN_GROUP_PREFIX}{Rcache.KEY_SEP}'
                            f'{int(time.time())}{Rcache.KEY_SEP}'
                            f'{answer.chat.id}{Rcache.KEY_SEP}'
                            f'{answer.message_id}'
                        )
                        r.set(name=s, value='1')
                    except Exception as e:
                        logging.error(f"Redis operation failed: {str(e)}")
                    finally:
                        r.close()

    if message.is_topic_message and \
    message.chat.id in settings.GROUPS_WITH_YOUTUBE_UPLOAD and \
    message.message_thread_id and \
    message.message_thread_id == \
    settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]['message_thread_id']:
        if message.content_type == ContentType.VIDEO:
            # Генерируем заголовок на основе даты и времени, если его нет
            title = message.caption if message.caption else f"Видео от {message.date.strftime('%d.%m.%Y %H:%M UTC')}"
            
            fname = None
            if settings.LOCAL_SERVER:
                try:
                    tg_file = await bot.get_file(message.video.file_id)
                    fname = tg_file.file_path
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logging.error(f"Failed to get ytvideo file: {str(e)}")
                    pass
            else:
                f = tempfile.NamedTemporaryFile(
                    dir=settings.DIR_TMP, suffix='.video', delete=False,
                )
                fname = f.name
                f.close()
                try:
                    tg_file = await bot.get_file(message.video.file_id)
                    await bot.download_file(tg_file.file_path, fname)
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logging.error(f"Failed to download video file: {str(e)}")
                    os.unlink(fname)
                    fname = None
            if not fname:
                try:
                    await bot.send_message(
                        tg_user_sender.id,
                        'Ошибка скачивания видео из сообщения. Не слишком ли большой файл?'
                    )
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logging.error(f"Failed to send error message: {str(e)}")
            else:
                description = (
                    f'Профиль автора: {response_from["first_name"]}, '
                    f'{Misc.get_deeplink(response_from, https=True)}\n'
                    f'Группа телеграм: '
                    f'{settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]["url_group"]}'
                )
                response, error = upload_video(
                    fname=fname,
                    auth_data=settings.GROUPS_WITH_YOUTUBE_UPLOAD[message.chat.id]['auth_data'],
                    snippet=dict(
                        title=title,  # Используем сгенерированный заголовок
                        description=description,
                ))
                if error:
                    try:
                        await bot.send_message(
                            tg_user_sender.id,
                            f'Ошибка загрузки видео:\n{error}'
                        )
                    except (TelegramBadRequest, TelegramForbiddenError) as e:
                        logging.error(f"Failed to send upload error message: {str(e)}")
                else:
                    href = f'https://www.youtube.com/watch?v={response["id"]}'
                    try:
                        await bot.send_message(
                            tg_user_sender.id, (
                                f'Видео {Misc.get_html_a(href, title)} загружено.\n'  # Используем title вместо message.caption
                                f'Автор: {Misc.get_deeplink_with_name(response_from, plus_trusts=True)}'
                            ),
                            link_preview_options=LinkPreviewOptions(is_disabled=False),
                        )
                    except (TelegramBadRequest, TelegramForbiddenError) as e:
                        logging.error(f"Failed to send upload success message: {str(e)}")
            if not settings.LOCAL_SERVER and fname:
                os.unlink(fname)

@router.my_chat_member(F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP)))
async def handle_bot_status_update(chat_member: ChatMemberUpdated):
    """
    Отслеживание подключения/отключения бота к группе
    """
    old_status = chat_member.old_chat_member.status
    new_status = chat_member.new_chat_member.status
    chat = chat_member.chat
    bot_user = chat_member.new_chat_member.user
    
    # Проверяем, что изменение касается нашего бота
    if bot_user.id != bot_data.id:
        return
    
    # Бот был добавлен в группу
    if old_status in ['left', 'kicked'] and new_status in ['member', 'administrator']:
        logging.info(f"Бот добавлен в группу: {chat.title} (ID: {chat.id})")
        
        # Сохраняем пользователя, который добавил бота
        if chat_member.from_user and not chat_member.from_user.is_bot:
            status, user_from = await Misc.post_tg_user(chat_member.from_user, did_bot_start=False)
            if status == 200:
                try:
                    await TgGroupMember.add(
                        group_chat_id=chat.id,
                        group_title=chat.title,
                        group_type=chat.type,
                        user_tg_uid=chat_member.from_user.id
                    )
                    logging.debug("TEST: AddBot TgGroupMember.add")
                    logging.info(f"Пользователь добавлен в группу: {chat.title} (ID: {chat.id}) (UID: {chat_member.from_user.id})")       
                except Exception as e:
                    logging.error(f"Group member add failed: {str(e)}")
        
        # Пробуем разные методы сохранения группы
        try:
            # Сначала пробуем создать/обновить через post (как в обработчике каналов)
            status, response = await TgGroup.post(chat.id, chat.title, chat.type)
            logging.debug(f"TgGroup.post result: {status}")
        except Exception as e:
            logging.error(f"TgGroup.post failed: {str(e)}")
            # Если post не сработал, пробуем put
            try:
                status, response = await TgGroup.put(
                    old_chat_id=chat.id,
                    chat_id=chat.id,
                    title=chat.title,
                    type_=chat.type,
                )
                logging.debug(f"TgGroup.put result: {status}")
            except Exception as e:
                logging.error(f"TgGroup.put also failed: {str(e)}")
        
        # Отправляем закреплённое сообщение
        try:
            await Misc.send_pin_group_message(chat)
            logging.info(f"Pin message sent to group {chat.title}")
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            logging.error(f"Failed to send pin message: {str(e)}")
        
    # Бот был удалён из группы
    elif new_status in ['left', 'kicked'] and old_status in ['member', 'administrator']:
        logging.info(f"Бот удалён из группы: {chat.title} (ID: {chat.id})")
        # Здесь можно добавить логику удаления группы из базы данных
        # или пометить её как неактивную

@router.my_chat_member(F.chat.type.in_((ChatType.CHANNEL,)))
async def echo_my_chat_member_for_bot(chat_member: ChatMemberUpdated):
    """
    Для формирования ссылки на доверия и карту среди участников канала

    Реакция на подключение к каналу бота
    """
    logging.debug("TEST: echo_my_chat_member_for_bot")
    new_chat_member = chat_member.new_chat_member
    bot_ = new_chat_member.user
    tg_user_from = chat_member.from_user
    if tg_user_from and not tg_user_from.is_bot:
        status, user_from = await Misc.post_tg_user(tg_user_from, did_bot_start=False)
        if status == 200:
            try:
                await TgGroupMember.add(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type, tg_user_from.id)
                logging.debug("TEST: Channel TgGroupMember.add")
            except Exception as e:
                logging.error(f"Channel member add failed: {str(e)}")
        else:
            return
    else:
        try:
            status, response = await TgGroup.post(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type)
            if status != 200:
                return
        except Exception as e:
            logging.error(f"TgGroup.post failed: {str(e)}")
    if bot_.is_bot and new_chat_member.status == 'administrator':
        try:
            await Misc.send_pin_group_message(chat_member.chat)
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            logging.error(f"Failed to send pin message: {str(e)}")
