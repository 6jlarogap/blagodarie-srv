# handler_group.py
#
# Команды и сообщения в группы и каналы

import base64, re, hashlib, redis, time, tempfile

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ContentType, InlineKeyboardMarkup, InlineKeyboardButton 
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.enums.message_entity_type import MessageEntityType
from aiogram.exceptions import TelegramBadRequest

from youtube_upload import upload_video

from common import TgGroup, TgGroupMember
from handler_offer import Offer

import settings, me
from settings import logging


router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

@router.message(F.chat.type.in_((ChatType.GROUP, ChatType.SUPERGROUP)), StateFilter(None))
async def process_group_message(message: Message, state: FSMContext):
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

    if await Offer.offer_forwarded_in_group_or_channel(message, state):
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
                    text, reply_markup = Misc.make_pin_group_message(message.chat)
                    try:
                        await bot.edit_message_text(
                            chat_id=message.migrate_from_chat_id,
                            message_id=response['pin_message_id'],
                            text=text,
                            reply_markup=reply_markup,
                        )
                    except TelegramBadRequest:
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
            await Misc.send_pin_group_message(message.chat)
            continue

        if not is_previous_his:
            reply_markup = InlineKeyboardMarkup()
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
                'Доверяю',
                callback_data=callback_data_template % dict_reply,
            )
            reply_markup.row(inline_btn_thank)
            logging.debug('minicard in group text: '+ repr(reply))
            answer = await message.answer(
                reply,
                reply_markup=reply_markup,
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
            if message.content_type == ContentType.VIDEO:
                if message.caption:
                    fname = None
                    if settings.LOCAL_SERVER:
                        try:
                            tg_file = await bot.get_file(message.video.file_id)
                            fname = tg_file.file_path
                        except:
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
                        except:
                            os.unlink(fname)
                            fname = None
                    if not fname:
                        await bot.send_message(
                            tg_user_sender.id,
                            'Ошибка скачивания видео из сообщения. Не слишком ли большой файл?'
                        )
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
                                title=message.caption,
                                description=description,
                        ))
                        if error:
                            await bot.send_message(
                                tg_user_sender.id,
                                f'Ошибка загрузки видео:\n{error}'
                            )
                        else:
                            href = f'https://www.youtube.com/watch?v={response["id"]}'
                            try:
                                await message.answer((
                                    f'Видео {Misc.get_html_a(href, message.caption)} загружено.\n'
                                    f'Автор: {Misc.get_deeplink_with_name(response_from, plus_trusts=True)}'
                                ))
                            except:
                                pass
                            try:
                                await message.delete()
                            except:
                                pass
                    if not settings.LOCAL_SERVER and fname:
                        os.unlink(fname)
                else:
                    await message.reply(
                        'Здесь допускаются <b>видео</b>, <u>обязательно <b>с заголовком</b></u>, '
                        'для отправки в Youtube'
                    )
