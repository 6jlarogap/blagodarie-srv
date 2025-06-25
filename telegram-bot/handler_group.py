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
                if message.chat.type == ChatType.SUPERGROUP:
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
                        try:
                            await bot.send_message(
                                tg_user_sender.id,
                                'Ошибка скачивания видео из сообщения. Не слишком ли большой файл?'
                            )
                        except (TelegramBadRequest, TelegramForbiddenError,):
                            pass
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
                            try:
                                await bot.send_message(
                                    tg_user_sender.id,
                                    f'Ошибка загрузки видео:\n{error}'
                                )
                            except (TelegramBadRequest, TelegramForbiddenError,):
                                pass
                        else:
                            href = f'https://www.youtube.com/watch?v={response["id"]}'
                            try:
                                await message.answer((
                                    f'Видео {Misc.get_html_a(href, message.caption)} загружено.\n'
                                    f'Автор: {Misc.get_deeplink_with_name(response_from, plus_trusts=True)}'
                                    ),
                                    link_preview_options=LinkPreviewOptions(is_disabled=False),
                                )
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


@router.my_chat_member(F.chat.type.in_((ChatType.CHANNEL,)))
async def echo_my_chat_member_for_bot(chat_member: ChatMemberUpdated):
    """
    Для формирования ссылки на доверия и карту среди участников канала

    Реакция на подключение к каналу бота
    """
    new_chat_member = chat_member.new_chat_member
    bot_ = new_chat_member.user
    tg_user_from = chat_member.from_user
    if tg_user_from and not tg_user_from.is_bot:
        status, user_from = await Misc.post_tg_user(tg_user_from, did_bot_start=False)
        if status == 200:
            await TgGroupMember.add(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type, tg_user_from.id)
        else:
            return
    else:
        status, response = await TgGroup.post(chat_member.chat.id, chat_member.chat.title, chat_member.chat.type)
        if status != 200:
            return
    if bot_.is_bot and new_chat_member.status == 'administrator':
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
    tg_subscriber = message.from_user
    tg_inviter = message.invite_link.creator if message.invite_link else None
    if tg_inviter:
        status_inviter, response_inviter = await Misc.post_tg_user(tg_inviter, did_bot_start=False)
        if status_inviter != 200:
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
    status, response_subscriber = await Misc.post_tg_user(tg_subscriber, did_bot_start=False)
    if status != 200:
        return
    try:
        await bot.approve_chat_join_request(
                chat.id,
                tg_subscriber.id
        )
    except TelegramBadRequest as excpt:
        in_chat = 'в канале' if is_channel else 'в группе'
        msg = f'Возможно, вы уже {in_chat}'
        if excpt.message == 'User_already_participant':
            msg = 'Вы уже {in_chat}'
        try:
            await bot.send_message(
                chat_id=tg_subscriber.id,
                text=msg,
            )
            return
        except (TelegramBadRequest, TelegramForbiddenError,):
            pass

    status, response_add_member = await TgGroupMember.add(
        group_chat_id=message.chat.id,
        group_title=message.chat.title,
        group_type=message.chat.type,
        user_tg_uid=tg_subscriber.id,
    )
    if status != 200:
        return

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
    try:
        await bot.send_message(chat_id=tg_subscriber.id, text=msg)
    except (TelegramBadRequest, TelegramForbiddenError,):
        pass
    if is_channel:
        reply = '%(dl_subscriber)s подключен(а)' % msg_dict
        await bot.send_message(
            message.chat.id,
            reply,
            disable_notification=True,
        )
