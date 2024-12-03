# handler_offer.py
#
# Команды и сообщения для offer: наши опросы/предложения

import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ContentType, InlineKeyboardMarkup, InlineKeyboardButton 
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
from aiogram.enums.message_entity_type import MessageEntityType
from aiogram.exceptions import TelegramBadRequest

import settings, me
from settings import logging

from common import Misc, TgGroup, TgGroupMember

router = Router()
dp, bot, bot_data = me.dp, me.bot, me.bot_data

class Offer(object):

    @classmethod
    async def offer_forwarded_in_group_or_channel(cls, message, state):
        result = False
        if message.forward_origin and message.content_type == ContentType.TEXT:
            num_links = 0
            for entity in message.entities:
                m = None
                if entity.type == MessageEntityType.TEXT_LINK:
                    m = re.search(
                        r'(?:start\=offer\-|offer_uuid\=|offer_id\=)([\da-f]{8}-([\da-f]{4}-){3}[\da-f]{12})',
                        entity.url,
                        flags=re.I
                    )
                if m:
                    num_links += 1
                    offer_uuid = m.group(1)
                if num_links >= 2:
                    status_offer, response_offer = await cls.post_offer_answer(offer_uuid, None, [-1])
                    if status_offer == 200:
                        await cls.show_offer(None, response_offer, message)
                        result = True
                        try:
                            await message.delete()
                        except TelegramBadRequest:
                            pass
                        break
        return result


    @classmethod
    async def show_offer(cls, user_from, offer, message, bot_data):
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
        try:
            await bot.send_message(
                message.chat.id,
                text=cls.text_offer(user_from, offer, message),
                reply_markup=cls.markup_offer(user_from, offer, message),
            )
        except TelegramBadRequest:
            await message.reply('Опрос-предложение предъявить не удалось')

    @classmethod
    def text_offer(cls, user_from, offer, message, bot_data):
        """
        Текст опроса-предложения

        На примере опроса 'Как дела?' с ответами Отлично (3 голоса), Хорошо (2), Плохо (0)

        Как дела?

        Голоса на <датавремя>
        Отлично - 3
        Хорошо - 2
        Плохо - 0

        Схема <graph.meetgame.us.to/?offer_uuid=offerUUID>
        Карта map.meetgame.us.to/?offer_id=offerUUID
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
            href='t.me/%s?start=offer-%s' % (bot_data.username, offer['uuid'],),
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
            href=Misc.get_deeplink(offer['owner'], https=True),
            text='Автор опроса: ' + offer['owner']['first_name']
        ) + '\n'
        return result


    @classmethod
    def markup_offer(cls, user_from, offer, message):
        buttons = []
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
                    buttons.append([inline_btn_answer])

            if have_i_voted or message.chat.type != types.ChatType.PRIVATE:
                callback_data_dict.update(number=0)
                inline_btn_answer = InlineKeyboardButton(
                    'Отозвать мой выбор',
                    callback_data=callback_data_template % callback_data_dict
                )
                buttons.append([inline_btn_answer])

        callback_data_dict.update(number=-1)
        inline_btn_answer = InlineKeyboardButton(
            'Обновить результаты',
            callback_data=callback_data_template % callback_data_dict
        )
        buttons.append([inline_btn_answer])

        if message.chat.type == types.ChatType.PRIVATE and user_from['uuid'] == offer['owner']['uuid']:
            callback_data_dict.update(number=-2)
            inline_btn_answer = InlineKeyboardButton(
                'Сообщение участникам',
                callback_data=callback_data_template % callback_data_dict
            )
            buttons.append([inline_btn_answer])

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
            buttons.append([inline_btn_answer])

            callback_data_dict.update(number=-5)
            inline_btn_answer = InlineKeyboardButton(
                'Задать координаты',
                callback_data=callback_data_template % callback_data_dict
            )
            buttons.append([inline_btn_answer])
        return InlineKeyboardMarkup(inline_keyboard=buttons)
