# handler_callbacks.py
#
# Сallback реакции

import re, base64, time, redis

from aiogram import Router, F, html
from aiogram.filters import Command, StateFilter
from aiogram.filters.logic import or_f
from aiogram.types import Message, CallbackQuery, ContentType, \
                          InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import settings, me
from settings import logging

from common import Misc, OperationType, KeyboardType, Rcache

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class FSMdonateSympa(StatesGroup):
    ask = State()

class Common(object):
    
    CALLBACK_DATA_TEMPLATE = (
        '%(keyboard_type)s%(sep)s'
        '%(user_from_sid)s%(sep)s'
        '%(user_to_sid)s%(sep)s'
        '%(journal_id)s%(sep)s'
    )
    YES = 'Да'
    NO = 'Нет'


    @classmethod
    async def check_common_callback(cls, callback):
        profile_from = profile_to = journal_id = None
        profile_from, profile_to = await Misc.check_sids_from_callback(callback)
        if profile_from and profile_to:
            if not (journal_id := cls.check_journal_id(callback)):
                profile_from = profile_to = journal_id = None
        return profile_from, profile_to, journal_id


    @classmethod
    def _callback_dict(cls, profile_from, profile_to, journal_id):
        return dict(
            user_from_sid=profile_from['username'],
            user_to_sid=profile_to['username'],
            journal_id=journal_id,
            sep=KeyboardType.SEP,
        )

    @classmethod
    def make_sympa_revoke(cls, profile_from, profile_to, journal_id, message_pre=''):
        text = message_pre
        reply_markup = None
        if text:
            callback_dict = cls._callback_dict(profile_from, profile_to, journal_id)
            callback_dict.update(keyboard_type=KeyboardType.SYMPA_REVOKE)
            button_yes = InlineKeyboardButton(
                text='Отменить',
                callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
            )
            reply_markup = InlineKeyboardMarkup(inline_keyboard=[ [button_yes] ])
        return text, reply_markup


    @classmethod
    async def make1_donate(cls, profile_from, profile_to, journal_id, message_pre=''):
        text = message_pre + '\n\n' if message_pre else ''
        status, response = await cls.get_donate_to(journal_id)
        if status == 200 and response.get('donate', {}).get('profile'):
            user_f_name = response['user_f']['first_name']
            text += (
                f'Поздравляем! У Вас взаимная симпатия - ваши профили скрыты от других участников игры.\n'
                f'Перед запросом контактов {user_f_name}, предлагаем добровольно поблагодарить '
                f'{response["donate"]["profile"]["first_name"]}. '
                f'Ваша благодарность будет передана {user_f_name}, '
                f'но не обязательна для её решения о передаче контактов.'
            )
        else:
            text += (
                f'Поздравляем! Взаимная симпатия!'
                f'Нажмите "Донатить" для отправки доната'
            )

        callback_dict = cls._callback_dict(profile_from, profile_to, journal_id)
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_DONATE)
        button_donate = InlineKeyboardButton(
            text='Добровольный дар',
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_DONATE_REFUSE)
        button_refuse_donate = InlineKeyboardButton(
            text='Без благодарности',
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_REVOKE)
        button_cancel_sympa = InlineKeyboardButton(
            text='Отменить симпатию',
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [button_donate],
                [button_refuse_donate],
                [button_cancel_sympa]
            ]
        )
        return text, reply_markup


    @classmethod
    async def get_donate_to(cls, journal_id):
        status, response = None, None
        donate_to_payload  = dict(
            tg_token=settings.TOKEN,
            journal_id=journal_id,
        )
        logging.debug('find_donate_to, payload: %s' % Misc.secret(donate_to_payload))
        status, response = await Misc.api_request(
            '/api/get_donate_to',
            method='POST',
            json = donate_to_payload
        )
        logging.debug('find_donate_to, status: %s' % status)
        logging.debug('find_donate_to, response: %s' % response)
        return status, response


    @classmethod
    async def make2_donate(cls, profile_from, profile_to, journal_id, message_pre=''):
        text = message_pre + '\n\n' if message_pre else ''
        text += 'Пожалуйста, пришлите мне снимок экрана с подтверждением перевода по указанным ниже реквизитам:\n\n'
        status, response = await cls.get_donate_to(journal_id)
        if status != 200 or not response.get('donate', {}).get('bank'):
            return None, None
        text += f'{response["donate"]["bank"]}\n'

        callback_dict = cls._callback_dict(profile_from, profile_to, journal_id)
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_DONATE_REFUSE)
        button_refuse_donate = InlineKeyboardButton(
            text='Продолжить без доната',
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_REVOKE)
        button_cancel_sympa = InlineKeyboardButton(
            text='Отменить симпатию',
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[ [button_refuse_donate, button_cancel_sympa] ]
        )
        return text, reply_markup, response


    @classmethod
    def inform_her_about_reciprocal(cls, profile_from, profile_to, journal_id, message_pre=''):
        text = message_pre + '\n\n' if message_pre else ''
        text += (
                f'Поздравляем! Взаимная симпатия! '
                f'{html.quote(profile_to["first_name"])} предложено задонатить'
        )
        callback_dict = cls._callback_dict(profile_from, profile_to, journal_id)
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_REVOKE)
        button_cancel_sympa = InlineKeyboardButton(
            text='Отменить симпатию',
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[ [button_cancel_sympa] ])
        return text, reply_markup


    @classmethod
    def make_sympa_do(cls, profile_from, profile_to, journal_id, message_pre=''):
        text = message_pre + '\n\n' if message_pre else ''
        text += f'Установить симпатию к {html.quote(profile_to["first_name"])}'
        callback_dict = cls._callback_dict(profile_from, profile_to, journal_id)
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_SET)
        button_yes = InlineKeyboardButton(
            text=cls.YES,
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        callback_dict.update(keyboard_type=KeyboardType.SYMPA_SET_CANCEL)
        button_no = InlineKeyboardButton(
            text=cls.NO,
            callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[ [button_yes, button_no] ])
        return text, reply_markup

    @classmethod
    def after_donate_or_not_donate(cls, profile_from, profile_to, journal_id, message_pre=''):
        text = message_pre
        if text:
            buttons = []
            callback_dict = cls._callback_dict(profile_from, profile_to, journal_id)
            if profile_from['gender'] == 'f':
                callback_dict.update(keyboard_type=KeyboardType.SYMPA_SEND_PROFILE)
                button_send_profile = InlineKeyboardButton(
                    text='Отправить профиль',
                    callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
                )
                buttons.append(button_send_profile)
            callback_dict.update(keyboard_type=KeyboardType.SYMPA_REVOKE)
            button_cancel_sympa = InlineKeyboardButton(
                text='Отменить симпатию',
                callback_data=cls.CALLBACK_DATA_TEMPLATE % callback_dict
            )
            buttons.append(button_cancel_sympa)
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[ buttons ]
            )
        return text, reply_markup

    @classmethod
    def check_journal_id(cls, callback):
        journal_id = 0
        try:
            if not (journal_id := int((callback.data.split(KeyboardType.SEP))[3])):
                raise ValueError
        except (IndexError, ValueError, TypeError):
            pass
        return journal_id

# --- end of class Common ---

@router.callback_query(F.data.regexp(r'^%s%s' % (
        KeyboardType.SYMPA_SET_CANCEL,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_sympa_set_cancel(callback: CallbackQuery, state: FSMContext):

    # Из апи приходит:
    #   f'{KeyboardType.что-то}{KeyboardType.SEP}'
    #   f'{user_from.username}{KeyboardType.SEP}'
    #   f'{user_to.username}{KeyboardType.SEP}'

    profile_from, profile_to, journal_id = await Common.check_common_callback(callback)
    if not profile_to:
        return
    what = int((callback.data.split(KeyboardType.SEP))[0])
    message = f'Вы отказались от установки симпатии к {html.quote(profile_to["first_name"])}'
    await bot.answer_callback_query(
        callback.id,
        text=message,
        show_alert=True,
    )
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_SET, KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_sympa_set(callback: CallbackQuery, state: FSMContext):

    # Из апи приходит:
    #   f'{KeyboardType.что-то}{KeyboardType.SEP}'
    #   f'{user_from.username}{KeyboardType.SEP}'
    #   f'{user_to.username}{KeyboardType.SEP}'
    #   f'{journal_id}{KeyboardType.SEP}'

    profile_from, profile_to, journal_id = await Common.check_common_callback(callback)
    if not profile_to:
        return

    r_key = (
        Rcache.SET_NEXT_SYMPA_WAIT_PREFIX + \
        profile_from['username'] + Rcache.KEY_SEP + \
        profile_to['username']
    )
    if r := redis.Redis(**settings.REDIS_CONNECT):
        r_rec = r.get(r_key)
        r.close()
        if r_rec:
            time_current = int(time.time())
            tm_diff = int(r_rec) - time_current
            if tm_diff > 0:
                await bot.answer_callback_query(
                    callback.id,
                    text=(
                        f'Вы можете снова установить симпатию к '
                        f'{html.quote(profile_to["first_name"])} '
                        f'только через {Misc.d_h_m_s(tm_diff)}'
                    ),
                    show_alert=True,
                )
                await callback.answer()
                return

    if profile_from['r_sympa_username'] or profile_to['r_sympa_username']:
        if profile_from['r_sympa_username']:
            message = 'У Вас уже есть взаимная симпатия'
        else:
            message = f'У {profile_to["first_name"]} уже есть взаимная симпатия'
        await bot.answer_callback_query(
            callback.id,
            text=message,
            show_alert=True,
        )
        await callback.answer()
        return

    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=str(OperationType.SET_SYMPA),
        tg_user_id_from=str(callback.from_user.id),
        user_id_to=profile_to['uuid'],
        is_confirmed='1',
    )
    logging.debug('post operation, set sympa, payload: %s' % Misc.secret(post_op))
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post_op,
    )
    logging.debug('post operation, set sympa, status: %s' % status)
    logging.debug('post operation, set sympa, response: %s' % response)
    message_pre = ''
    text_from = reply_markup_from = None
    text_to = reply_markup_to = None
    if status == 400 and response.get('message'):
        await bot.answer_callback_query(
            callback.id,
            text=f'Симпатия не установлена:\n{response["message"]}',
            show_alert=True,
        )
    elif status == 200:
        journal_id = response['journal_id']
        if response.get('previousstate'):
            if response['previousstate']['is_sympa_confirmed']:
                message_pre = f'Симпатия к {html.quote(profile_to["first_name"])} уже установлена'
                text_from, reply_markup_from = Common.make_sympa_revoke(
                    profile_from, profile_to, journal_id, message_pre
                )
            else:
                if response.get('is_reciprocal'):
                    if profile_to['gender'] == 'f':
                        # М (from) поставил симпатию, которая стала взаимной.
                        # М (from) донатить  с кнопкой отмены симпатии.
                        # Ж (to) уведомление с кнопкой отмены симпатии
                        #
                        text_from, reply_markup_from = await Common.make1_donate(
                            profile_from, profile_to, journal_id, message_pre=''
                        )
                        text_to, reply_markup_to = Common.inform_her_about_reciprocal(
                            profile_to, profile_from, journal_id, message_pre=''
                        )
                    else:
                        # Ж (from) поставила симпатию, которая стала взаимной.
                        # Ж (from) уведомление с кнопкой отмены симпатии.
                        # М(to) донатить с кнопкой отмены симпатии.
                        text_from, reply_markup_from = Common.inform_her_about_reciprocal(
                            profile_from, profile_to, journal_id, message_pre=''
                        )
                        text_to, reply_markup_to = await Common.make1_donate(
                            profile_to, profile_from, journal_id, message_pre=''
                        )

                else:
                    message_pre = f'Симпатия к {html.quote(profile_to["first_name"])} установлена'
                    text_from, reply_markup_from = Common.make_sympa_revoke(
                        profile_from, profile_to, journal_id, message_pre
                    )

                    text_to = (
                        'Вам установлена симпатия! '
                        'Отмечайте интересы на карте и ставьте симпатии чтобы найти взаимные'
                    )
                    inline_btn_map = InlineKeyboardButton(
                        text='Карта участников игры',
                        login_url=Misc.make_login_url(
                            redirect_path=settings.MEET_HOST,
                            keep_user_data='on'
                    ))
                    reply_markup_to = InlineKeyboardMarkup(inline_keyboard=[ [inline_btn_map] ])
                if r := redis.Redis(**settings.REDIS_CONNECT):
                    time_current = int(time.time())
                    r.set(
                        r_key,
                        str(time_current + Rcache.SET_NEXT_SYMPA_WAIT),
                        ex=Rcache.SET_NEXT_SYMPA_WAIT,
                    )
                    r.close()

    if text_from:
        await Misc.remove_n_send_message(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text_from,
            reply_markup=reply_markup_from,
        )

    if text_to:
        for tgd in profile_to['tg_data']:
            try:
                await bot.send_message(
                    tgd['tg_uid'],
                    text=text_to,
                    reply_markup=reply_markup_to,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
    await callback.answer()

@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_REVOKE, KeyboardType.SEP,
    )), StateFilter(None))
@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_REVOKE, KeyboardType.SEP,
    )), StateFilter(FSMdonateSympa))
async def cbq_sympa_revoke(callback: CallbackQuery, state: FSMContext):
    profile_from, profile_to, journal_id = await Common.check_common_callback(callback)
    if not profile_to:
        return
    post_op = dict(
        tg_token=settings.TOKEN,
        operation_type_id=str(OperationType.REVOKE_SYMPA_ONLY),
        tg_user_id_from=str(callback.from_user.id),
        user_id_to=profile_to['uuid'],
    )
    logging.debug('post operation, revoke sympa only, payload: %s' % Misc.secret(post_op))
    status, response = await Misc.api_request(
        path='/api/addoperation',
        method='post',
        data=post_op,
    )
    logging.debug('post operation, revoke sympa only, status: %s' % status)
    logging.debug('post operation, revoke sympa only, response: %s' % response)
    message_pre = ''
    text = reply_markup = None
    if status == 200:
        journal_id = response['journal_id']
        if response.get('previousstate'):
            if response['previousstate']['is_sympa_confirmed']:
                message_pre = f'Симпатия к {html.quote(profile_to["first_name"])} отменена'
                for tgd in profile_to['tg_data']:
                    try:
                        await bot.send_message(
                            tgd['tg_uid'],
                            text=(
                                f'Симпатия к Вам отменена. Приглашайте новых игроков '
                                f'и ставьте больше интересов на '
                                f'<a href="{settings.MEET_HOST}">карте</a> - '
                                f'чтобы скорее найти совпадения!'
                        ))
                    except (TelegramBadRequest, TelegramForbiddenError):
                        pass
            else:
                message_pre = f'Симпатия к {html.quote(profile_to["first_name"])} уже отменена'
            text, reply_markup = Common.make_sympa_do(
                profile_from, profile_to, journal_id, message_pre
            )
    if text:
        await Misc.remove_n_send_message(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=reply_markup,
        )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_DONATE,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_get_sympa_donate(callback: CallbackQuery, state: FSMContext):
    profile_from, profile_to, journal_id = await Common.check_common_callback(callback)
    if not profile_to:
        return
    if not profile_from['r_sympa_username'] or profile_from['r_sympa_username'] != profile_to['username']:
        await bot.answer_callback_query(
            callback.id,
            text=f'Этот донат уже не актуален. У вас нет взаимной симпатии к {html.quote(profile_to["first_name"])}',
            show_alert=True,
        )
        await callback.answer()
        return
    text, reply_markup, response_get_donate = await Common.make2_donate(
        profile_from, profile_to, journal_id, message_pre=''
    )
    if text:
        await state.set_state(FSMdonateSympa.ask)
        message = await Misc.remove_n_send_message(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text,
            reply_markup=reply_markup,
        )
        await state.update_data(
            journal_id=journal_id,
            response_get_donate=response_get_donate,
            # Это для того, если щелкнет Отказ от симпатии или Отказ от доната
            callback=callback,
            # Это для отравки доната
            message=message,
        )
    await callback.answer()

@router.message(F.chat.type.in_((ChatType.PRIVATE,)), StateFilter(FSMdonateSympa.ask))
async def process_message_donate_after_sympa(message: Message, state: FSMContext):
    data = await state.get_data()
    status_from, profile_from = await Misc.post_tg_user(message.from_user)
    if status_from != 200 or \
       profile_from['uuid'] != data.get('response_get_donate', {}).get('user_m', {}).get('uuid') or \
       not data.get('journal_id'):
        await state.clear(); return
    is_first = True
    user_m = profile_from
    user_f = data['response_get_donate']['user_f']
    media_group_id = str(message.media_group_id or '')
    if media_group_id:
        key = (
            f'{Rcache.ASK_MONEY_PREFIX}{Rcache.KEY_SEP}'
            f'{message.from_user.id}{Rcache.KEY_SEP}'
            f'{media_group_id}{Rcache.KEY_SEP}'
            f'{data["journal_id"]}'
        )
        is_first = Misc.redis_is_key_first_up(key, ex=300)
    tgdesc_payload  = dict(
        tg_token=settings.TOKEN,
        journal_id=data['journal_id'],
        message_id=message.message_id,
        chat_id=message.chat.id,
        media_group_id=media_group_id,
        is_first=is_first,
    )
    logging.debug('post donate_reciprocal_sympathy, payload: %s' % Misc.secret(tgdesc_payload))
    status, response = await Misc.api_request(
        '/api/thank_bank',
        method='POST',
        json = tgdesc_payload
    )
    logging.debug('post donate_reciprocal_sympathy, status: %s' % status)
    logging.debug('post donate_reciprocal_sympathy, response: %s' % response)
    if status == 200:
        success = False
        if is_first:
            for tgd in data['response_get_donate']['donate']['tg_data']:
                try:
                    await bot.send_message(
                        tgd['tg_uid'],
                        text=(
                            f'Получена благодарность за приглашение '
                            f'{Misc.get_deeplink_with_name(user_f)} '
                            f'в игру знакомств'
                    ))
                    success = True
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass

        for tgd in data['response_get_donate']['donate']['tg_data']:
            try:
                await bot.forward_message(
                    tgd['tg_uid'],
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
                success = True
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
        for tgd in user_f['tg_data']:
            try:
                await bot.forward_message(
                    tgd['tg_uid'],
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

        if is_first and success:
            if data.get('message'):
                text, reply_markup = Common.after_donate_or_not_donate(
                    user_m, user_f, data['journal_id'],
                    message_pre=(
                        f'Донат отправлен. Ожидайте решения {html.quote(user_f["first_name"])} о передаче контактов'
                ))
                await Misc.remove_n_send_message(
                    chat_id=message.from_user.id,
                    message_id=data['message'].message_id,
                    text=text,
                    reply_markup=reply_markup,
                )

            text, reply_markup = Common.after_donate_or_not_donate(
                user_f, user_m, data['journal_id'],
                message_pre=(
                    f'Получен запрос от {html.quote(user_m["first_name"])} на Ваши контакты'
            ))
            for tgd in user_f['tg_data']:
                try:
                    await bot.send_message(
                        tgd['tg_uid'],
                        text=text,
                        reply_markup=reply_markup,
                    )
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass

    await state.clear()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_SEND_PROFILE,
        KeyboardType.SEP,
    )), StateFilter(None))
async def cbq_get_sympa_send_profile(callback: CallbackQuery, state: FSMContext):
    profile_from, profile_to, journal_id = await Common.check_common_callback(callback)
    if not profile_to:
        return
    if not profile_from['r_sympa_username'] or profile_from['r_sympa_username'] != profile_to['username']:
        await bot.answer_callback_query(
            callback.id,
            text=f'Этот уже не актуально. У вас нет взаимной симпатии к {html.quote(profile_to["first_name"])}',
            show_alert=True,
        )
        await callback.answer()
        return
    success = False
    text_to = (
        f'{Misc.get_deeplink_with_name(profile_from)}\n'
        f'Контакты переданы. Вы покидаете игру знакомств - для личного общения! Удачи!'
    )
    inline_btn_invite = InlineKeyboardButton(
        text='Пригласить в игру',
        callback_data=Misc.CALLBACK_DATA_KEY_TEMPLATE % dict(
        keyboard_type=KeyboardType.MEET_INVITE,
        sep=KeyboardType.SEP,
    ))
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[ [ inline_btn_invite ] ])
    for tgd in profile_to['tg_data']:
        try:
            await bot.send_message(
                tgd['tg_uid'],
                text=text_to,
                reply_markup=reply_markup
            )
            success = True
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
    if success:
        text_from = (
            f'Контакты переданы. Вы покидаете игру знакомств - для личного общения! Удачи!'
        )
        await Misc.remove_n_send_message(
            chat_id=callback.from_user.id,
            message_id=callback.message.message_id,
            text=text_from,
            reply_markup=reply_markup,
        )
    else:
        await bot.answer_callback_query(
            callback.id,
            text='Не удалось передать контакты',
            show_alert=True,
        )
    await callback.answer()


@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_DONATE_REFUSE, KeyboardType.SEP,
    )), StateFilter(None))
@router.callback_query(F.data.regexp(Misc.RE_KEY_SEP % (
        KeyboardType.SYMPA_DONATE_REFUSE, KeyboardType.SEP,
    )), StateFilter(FSMdonateSympa))
async def cbq_sympa_donate_refuse(callback: CallbackQuery, state: FSMContext):
    user_m, user_f, journal_id = await Common.check_common_callback(callback)
    if not user_f or user_f['gender'] != 'f':
        return
    if not user_m['r_sympa_username'] or user_m['r_sympa_username'] != user_f['username']:
        await bot.answer_callback_query(
            callback.id,
            text=f'Этот уже не актуально. У вас нет взаимной симпатии к {html.quote(user_f["first_name"])}',
            show_alert=True,
        )
        await state.clear()
        await callback.answer()
        return

    text, reply_markup = Common.after_donate_or_not_donate(
        user_m, user_f, journal_id,
        message_pre=(
            f'Ожидайте решения {html.quote(user_f["first_name"])} о передаче контактов'
    ))
    await Misc.remove_n_send_message(
        chat_id=callback.from_user.id,
        message_id=callback.message.message_id,
        text=text,
        reply_markup=reply_markup,
    )
    text, reply_markup = Common.after_donate_or_not_donate(
        user_f, user_m, journal_id,
        message_pre=(
            f'Получен запрос от {html.quote(user_m["first_name"])} на Ваши контакты'
    ))
    for tgd in user_f['tg_data']:
        try:
            await bot.send_message(
                tgd['tg_uid'],
                text=text,
                reply_markup=reply_markup,
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
    await state.clear()
    await callback.answer()
