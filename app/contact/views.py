import os, datetime, time, json, re

from django.shortcuts import redirect
from django.db import transaction, IntegrityError, connection
from django.db.models import F, Sum
from django.db.models.query_utils import Q
from django.views.generic.base import View
from django.views.decorators.cache import cache_page
from django.http import Http404
from django.core.exceptions import ValidationError

from django.conf import settings
from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.exceptions import NotAuthenticated

from app.utils import ServiceException, FrontendMixin, SQL_Mixin, get_moon_day

from app.models import UnclearDate, PhotoModel

from contact.models import KeyType, Key, \
                           Symptom, UserSymptom, SymptomChecksumManage, \
                           Journal, CurrentState, OperationType, Wish, \
                           AnyText, Ability, TgJournal, TgMessageJournal, \
                           ApiAddOperationMixin
from users.models import CreateUserMixin, IncognitoUser, Profile, TempToken, Oauth, UuidMixin, TgGroup, TelegramApiMixin

MSG_NO_PARM = 'Не задан или не верен какой-то из параметров в связке номер %s (начиная с 0)'


class ApiAddOperationView(ApiAddOperationMixin, TelegramApiMixin, FrontendMixin, APIView):
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    @transaction.atomic
    def post(self, request):
        """
        Добавление операции

        На входе json или form data

        Обязательно:
            тип операции, operation_type_id, см. таблицу OperationType

        Если запрос приходит из телеграм бота:
            tg_token
                токен бота, должен соответствовать тому, что в api local_settings

            ИЛИ
                user_id_from
                    (не uuid!) пользователя от кого
                        NB! при передаче данных по кнопке есть ограничение, строка не больше 64 символов, uuid не подходит
            или
                tg_user_id_from
                    Ид телеграм прользователя
            или
                user_uuid_from
                    Это uuid, от кого

            ИЛИ
                user_id_to
                    (не uuid!) пользователя к кому
                        NB! при передаче данных по кнопке есть ограничение, строка не больше 64 символов, uuid не подходит
            или
                user_uuid_to
                    Это uuid, к кому

            tg_from_chat_id (необязательно):
                id пользователя (1) телеграма, который составил сообщение, что перенаправил другой пользователь (2).
                Пользователь (2) отправил благодарность к (1) или выполнил другое действие
            tg_message_id (необязательно):
                Ид того сообщения
            тип операции может быть любой, кроме назначения/снятия родственников

        Иначе требует авторизации
        - если user_id_from == user_id_to, то вернуть ошибку (нельзя добавить операцию себе);
        - иначе:
            - если тип операции THANK:
                - записать данные в таблицу tbl_journal;
                - инкрементировать значение столбца sum_thanks_count для пользователя user_id_to;
                - если не существует записи в tbl_current_state для заданных user_id_from и user_id_to, то создать ее;
                - инкрементировать значение столбца thanks_count в таблице tbl_current_state для user_id_from и user_id_to;
            - если тип операции MISTRUST:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to;
                    - если значение IS_TRUST == FALSE, вернуть ошибку /message/
                      (нельзя утратить доверие, если его и так нет),
                      при этом кроме message, еще передается code='already';
                - иначе:
                    - создать запись в таблице tbl_current_state;
                - записать данные в таблицу tbl_journal;
                - если текущее IS_TRUST == NULL, то инкрементировать FAME и MISTRUST_COUNT для пользователя user_id_to;
                - если текущее IS_TRUST == TRUE, то
                  декрементировать TRUST_COUNT и инкрементировать FAME и MISTRUST_COUNT для пользователя user_id_to;
                - в таблице tbl_current_state установить IS_TRUST = FALSE;
            - если тип операции TRUST:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to;
                    - если значение IS_TRUST == TRUE, вернуть ошибку /message/
                    (нельзя установить доверие, если уже доверяешь);
                      при этом кроме message, еще передается code='already';
                - иначе:
                    - создать запись в таблице tbl_current_state;
                - записать данные в таблицу tbl_journal;
                - если текущее IS_TRUST == NULL, то инкрементировать FAME и TRUST_COUNT для пользователя user_id_to;
                - если текущее IS_TRUST == FALSE, то
                  декрементировать MISTRUST_COUNT и инкрементировать FAME и TRUST_COUNT для пользователя user_id_to;
                - в таблице tbl_current_state установить IS_TRUST = TRUE;
            - если тип операции NULLIFY_TRUST:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to;
                    - если значение IS_TRUST == NULL, вернуть ошибку /message/
                      (нельзя обнулить доверие, если оно пустое);
                      при этом кроме message, еще передается code='already';
                    - иначе:
                        - если текущее IS_TRUST == TRUE, то декрементировать TRUST_COUNT;
                        - если текущее IS_TRUST == FALSE, то декрементировать MISTRUST_COUNT;
                        - декрементировать FAME для user_id_to;
                        - установить IS_TRUST = NULL;
                        - записать данные в таблицу tbl_journal;
                    - иначе вернуть ошибку /message/ (нельзя обнулить доверие, если связи нет)
                      при этом кроме message, еще передается code='already';

            - По операциям Father, Mother not_Parent NB
            !!! может быть задан еще и user_from_id,
            !!! из user_from, user_to хотя бы один должен быть
                или авторизованным пользователем или его родственником

            - если тип операции Father или Mother:
                - проверить, есть ли запись с user_from == user_to и
                  user_to == user_from и и (is_mother == True или is_father == True).
                  Если есть, то ошибка:
                  в одной паре людей не могут быть первй родителем второго одновременно
                  с тем, что второй - родитель первого
                - проверить, есть ли уже у user_from папа (при операции FATHER)
                  или мама (при операции MOTHER), но не user_to.
                  Если есть, то ошибка: двух пап или двух мам у человека быть не должно.
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to:
                    - если текущее значение is_father  == True (при операции FATHER)
                      или текущее значение is_mother  == True (при операции MOTHER),
                      вернуть ошибку, нельзя несколько раз подряд становиться мамой или папой
                    - иначе устанавливаются is_father, is_mother
                      в соответствии с полученным типом операции
                - иначе создать запись в таблице tbl_current_state c
                  для заданных user_id_from и user_id_to c is_father, is_mother
                      в соответствии с полученным типом операции
                - если нет ошибок, то записать данные в таблицу tbl_journal

            - если тип операции NOT_PARENT:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to:
                    - если текущие значения is_father == is_mother == False,
                      вернуть ошибку, нельзя не становиться  родителем, если и раньше им не был
                    - если одно из is_father, is_mother == True,
                      установить is_mother = is_father = False
                - иначе вернуть ошибку, не был родителем, нечего еще раз говорить, что не родитель,
                  при этом кроме message, еще передается code='already'
                - если нет ошибок, то записать данные в таблицу tbl_journal

        Пример исходных данных:
        {
            "user_id_to": "825b031e-95a2-4fdd-a70b-b446a52c4498",
            "operation_type_id": 1,
            "timestamp": 1593527855
        }
        """
        try:
            try:
                operationtype_id = int(request.data.get("operation_type_id"))
            except (TypeError, ValueError):
                raise ServiceException('Не задан или неверный operation_type_id')

            got_tg_token = False
            tg_from_chat_id = tg_message_id = None
            if request.data.get('tg_token'):
                if request.data.get('tg_token') != settings.TELEGRAM_BOT_TOKEN:
                    raise ServiceException('Неверный токен телеграм бота')

                if not request.data.get('user_uuid_from') and not request.data.get('tg_user_id_from'):
                    raise ServiceException('Не заданы ни user_id_from, ни tg_user_id_from')
                if request.data.get('user_uuid_from') and request.data.get('tg_user_id_from'):
                    raise ServiceException('Заданы и user_uuid_from, и tg_user_id_from')

                user_uuid_from = request.data.get('user_uuid_from')
                if user_uuid_from:
                    try:
                        profile_from = Profile.objects.select_related('user').get(uuid=user_uuid_from)
                        user_from = profile_from.user
                    except ValidationError:
                        raise ServiceException('Неверный user_uuid_from = "%s"' % user_uuid_from)
                    except Profile.DoesNotExist:
                        raise ServiceException('Не найден пользователь, user_uuid_from = "%s"' % user_uuid_from)

                tg_user_id_from = request.data.get('tg_user_id_from')
                if tg_user_id_from:
                    try:
                        user_from = Oauth.objects.get(
                            provider=Oauth.PROVIDER_TELEGRAM,
                            uid= str(tg_user_id_from),
                        ).user
                        profile_from = user_from.profile
                    except Oauth.DoesNotExist:
                        raise ServiceException('Не найден пользователь с этим ид телеграма')

                if not request.data.get('user_uuid_to') and not request.data.get('user_id_to'):
                    raise ServiceException('Не заданы ни user_uuid_to, ни user_id_to')
                if request.data.get('user_uuid_to') and request.data.get('user_id_to'):
                    raise ServiceException('Заданы и user_uuid_to, и user_id_to')

                user_id_to = request.data.get('user_id_to')
                if user_id_to:
                    try:
                        profile_to = Profile.objects.select_for_update().select_related('user').get(user__pk=user_id_to)
                        user_to = profile_to.user
                    except (Profile.DoesNotExist, ValueError,):
                        raise ServiceException('Не задан или не найден user_id_to')

                user_uuid_to = request.data.get('user_uuid_to')
                if user_uuid_to:
                    try:
                        profile_to = Profile.objects.select_for_update().select_related('user').get(uuid=user_uuid_to)
                        user_to = profile_to.user
                    except ValidationError:
                        raise ServiceException('Неверный uuid = "%s"' % user_uuid_to)
                    except Profile.DoesNotExist:
                        raise ServiceException('Не найдено ничего с uuid = "%s"' % user_uuid_to)

                tg_from_chat_id = request.data.get('tg_from_chat_id')
                tg_message_id = request.data.get('tg_message_id')
                got_tg_token = True

            elif not request.user.is_authenticated:
                raise NotAuthenticated

            if not got_tg_token:
                user_from = request.user
                profile_from = user_from.profile
                user_from_uuid = profile_from.uuid

                user_to_uuid = request.data.get("user_id_to")
                if not user_to_uuid:
                    raise ServiceException('Не задан user_id_to')
                try:
                    profile_to = Profile.objects.select_for_update().select_related('user').get(uuid=user_to_uuid)
                    user_to = profile_to.user
                except ValidationError:
                    raise ServiceException('Неверный user_id_to = "%s"' % user_to_uuid)
                except Profile.DoesNotExist:
                    raise ServiceException('Не найден пользователь, user_id_to = "%s"' % user_to_uuid)

                if operationtype_id in (OperationType.FATHER, OperationType.MOTHER, OperationType.NOT_PARENT,):
                    user_from_uuid = request.data.get("user_id_from")
                    if user_from_uuid:
                        try:
                            profile_from = Profile.objects.select_related('user').get(uuid=user_from_uuid)
                            user_from = profile_from.user
                        except ValidationError:
                            raise ServiceException('Неверный user_id_from = "%s"' % user_from_uuid)
                        except Profile.DoesNotExist:
                            raise ServiceException('Не найден пользователь, user_id_from = "%s"' % user_from_uuid)
            if user_to == user_from:
                raise ServiceException('Операция на самого себя не предусмотрена')

            if not got_tg_token:
                if operationtype_id in (
                    OperationType.SET_FATHER, OperationType.SET_MOTHER,
                    OperationType.FATHER, OperationType.MOTHER,
                    OperationType.NOT_PARENT,
                ):
                    if not (
                        user_from == request.user or profile_from.owner == request.user
                    ):
                            raise ServiceException('У Вас нет прав задавать такого родителя')

            comment = request.data.get("comment", None)
            insert_timestamp = request.data.get('timestamp', int(time.time()))

            data = self.add_operation(
                user_from,
                profile_to,
                operationtype_id,
                comment,
                insert_timestamp,
                tg_from_chat_id,
                tg_message_id,
            )

            if got_tg_token:
                profile_from_data=profile_from.data_dict(request)
                profile_from_data.update(profile_from.data_WAK())
                profile_from_data.update(tg_data=profile_from.tg_data(), user_id=user_from.pk)

                profile_to_data=profile_to.data_dict(request)
                profile_to_data.update(profile_to.data_WAK())
                profile_to_data.update(tg_data=profile_to.tg_data(), user_id=user_to.pk)
                data.update(
                    profile_from=profile_from_data,
                    profile_to=profile_to_data,
                )

            if not got_tg_token and profile_to.is_notified:
                message = None
                if operationtype_id in (OperationType.THANK, OperationType.TRUST_AND_THANK, ):
                    message = 'Получена благодарность от '
                    message += self.profile_link(request, user_from.profile)
                elif operationtype_id == OperationType.MISTRUST:
                    message = 'Получена утрата доверия от '
                    message += self.profile_link(request, user_from.profile)
                elif operationtype_id == OperationType.TRUST:
                    message = 'Получено доверие от '
                    message += self.profile_link(request, user_from.profile)
                elif operationtype_id == OperationType.NULLIFY_TRUST:
                    message = 'Доверие от ' + self.profile_link(request, user_from.profile) + ' обнулено'
                if message:
                    self.send_to_telegram(message, user=user_to)

            status_code = status.HTTP_200_OK

        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            try:
                code=excpt.args[1]
            except IndexError:
                code=''
            data.update(code=code)
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_operation = ApiAddOperationView.as_view()

class ApiAddTextOperationView(APIView):
    permission_classes = (IsAuthenticated, )

    def anytext_recount(self, anytext):
        anytext.trust_count = CurrentState.objects.filter(
            anytext=anytext,
            is_trust=True,
        ).distinct().count()
        anytext.mistrust_count = CurrentState.objects.filter(
            anytext=anytext,
            is_trust=False,
        ).distinct().count()
        anytext.fame = anytext.trust_count + anytext.mistrust_count
        anytext.save()

    @transaction.atomic
    def post(self, request):
        """
        Добавление операции для текста

        - если тип операции THANK:
            - записать данные в таблицу tbl_journal;
            - инкрементировать значение столбца sum_thanks_count для текста text_id_to;
            - если не существует записи в tbl_current_state для заданных user_id_from и text_id_to, то создать ее;
            - инкрементировать значение столбца thanks_count в таблице tbl_current_state для user_id_from и text_id_to;
        - если тип операции MISTRUST:
            - если есть запись в таблице tbl_current_state для заданных user_id_from и text_id_to;
                - если значение IS_TRUST == FALSE, вернуть ошибку (нельзя утратить доверие, если его и так нет);
            - иначе:
                - создать запись в таблице tbl_current_state;
            - записать данные в таблицу tbl_journal;
            - если текущее IS_TRUST == NULL, то инкрементировать FAME и MISTRUST_COUNT для текста text_id_to;
            - если текущее IS_TRUST == TRUE, то
              декрементировать TRUST_COUNT и инкрементировать FAME и MISTRUST_COUNT для текста text_id_to;
            - в таблице tbl_current_state установить IS_TRUST = FALSE;
        - если тип операции TRUST:
            - если есть запись в таблице tbl_current_state для заданных user_id_from и text_id_to;
                - если значение IS_TRUST == TRUE, вернуть ошибку (нельзя установить доверие, если уже доверяешь);
            - иначе:
                - создать запись в таблице tbl_current_state;
            - записать данные в таблицу tbl_journal;
            - если текущее IS_TRUST == NULL, то инкрементировать FAME и TRUST_COUNT для текста text_id_to;
            - если текущее IS_TRUST == FALSE, то
              декрементировать MISTRUST_COUNT и инкрементировать FAME и TRUST_COUNT для текста text_id_to;
            - в таблице tbl_current_state установить IS_TRUST = TRUE;
        - если тип операции NULLIFY_TRUST:
            - если есть запись в таблице tbl_current_state для заданных user_id_from и text_id_to;
                - если значение IS_TRUST == NULL, вернуть ошибку (нельзя обнулить доверие, если оно пустое);
                    - иначе:
                        - если текущее IS_TRUST == TRUE, то декрементировать TRUST_COUNT;
                        - если текущее IS_TRUST == FALSE, то декрементировать MISTRUST_COUNT;
                        - декрементировать FAME для text_id_to;
                        - установить IS_TRUST = NULL;
                        - записать данные в таблицу tbl_journal;
            - иначе вернуть ошибку (нельзя обнулить доверие, если связи нет);

        Пример исходных данных:
        {
            "text_id_to": "31f6a5b2-94a2-4993-9b13-f289318891e6",
            "text": "Любой текст",
            // передается что-то одно из двух предыдущих
            "operation_type_id": 1,
            "timestamp": 1593527855,
            "comment": "Спасибо за помощь"
        }
        Возвращает:
        {
            "text_id_to": "......"
            // имеет смысл такой возврат, если был передан текст.
            // Если переданного текста не было в базе, создается,
            если был, то возвращается существующий uuid
        }
        """

        try:
            user_from = request.user
            text_to_uuid = request.data.get("text_id_to")
            text = request.data.get("text")
            if text_to_uuid and text:
                raise ServiceException('Заданы и text_id_to и text')
            if not text_to_uuid and not text:
                raise ServiceException('Не заданы ни text_id_to, ни text')
            operationtype_id = request.data.get("operation_type_id")
            try:
                operationtype_id = int(operationtype_id)
                operationtype = OperationType.objects.get(pk=operationtype_id)
            except (ValueError, OperationType.DoesNotExist,):
                raise ServiceException('Неизвестный operation_type_id = %s' % operationtype_id)

            if text_to_uuid:
                # задан только text_id_to
                try:
                    anytext = AnyText.objects.select_for_update().get(uuid=text_to_uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = "%s"' % text_to_uuid)
                except AnyText.DoesNotExist:
                    raise ServiceException('Не найден текст, text_id_to = "%s"' % text_to_uuid)
            else:
                # задан только text
                if operationtype_id == OperationType.NULLIFY_TRUST:
                    try:
                        anytext = AnyText.objects.select_for_update().get(text=text)
                    except AnyText.DoesNotExist:
                        raise ServiceException('Не найден текст, к которому хотите снять доверие или недоверие')
                else:
                    anytext, created_ = AnyText.objects.select_for_update().get_or_create(text=text)

            update_timestamp = int(time.time())
            insert_timestamp = request.data.get('timestamp', update_timestamp)

            if operationtype_id == OperationType.THANK:
                currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                    user_from=user_from,
                    anytext=anytext,
                    defaults=dict(
                        thanks_count=1,
                ))
                if not created_:
                    currentstate.thanks_count = F('thanks_count') + 1
                    currentstate.update_timestamp = update_timestamp
                    currentstate.save(update_fields=('thanks_count', 'update_timestamp'))
                anytext.sum_thanks_count += 1
                anytext.save(update_fields=('sum_thanks_count',))

            elif operationtype_id == OperationType.MISTRUST:
                currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                    user_from=user_from,
                    anytext=anytext,
                    defaults=dict(
                        is_trust=False,
                ))
                if not created_:
                    if currentstate.is_trust == False:
                        raise ServiceException('Вы уже не доверяете тексту')
                    currentstate.is_trust = False
                    currentstate.update_timestamp = update_timestamp
                    currentstate.save(update_fields=('is_trust', 'update_timestamp'))
                self.anytext_recount(anytext)

            elif operationtype_id == OperationType.TRUST:
                currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                    user_from=user_from,
                    anytext=anytext,
                    defaults=dict(
                        is_trust=True,
                ))
                if not created_:
                    if currentstate.is_trust == True:
                        raise ServiceException('Вы уже доверяете тексту')
                    currentstate.is_trust = True
                    currentstate.update_timestamp = update_timestamp
                    currentstate.save(update_fields=('is_trust', 'update_timestamp'))
                self.anytext_recount(anytext)

            elif operationtype_id == OperationType.NULLIFY_TRUST:
                err_message = 'У вас не было ни доверия, ни недоверия к тексту'
                try:
                    currentstate = CurrentState.objects.select_for_update().get(
                        user_from=user_from,
                        anytext=anytext,
                    )
                except CurrentState.DoesNotExist:
                    raise ServiceException(err_message)
                if currentstate.is_trust == None:
                    raise ServiceException(err_message)
                currentstate.is_trust = None
                currentstate.update_timestamp = update_timestamp
                currentstate.save(update_fields=('is_trust', 'update_timestamp'))
                self.anytext_recount(anytext)

            comment = request.data.get("comment", None)
            Journal.objects.create(
                user_from=user_from,
                anytext=anytext,
                operationtype=operationtype,
                insert_timestamp=insert_timestamp,
                comment=comment,
            )
            data = dict(text_id_to=anytext.uuid)
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_text_operation = ApiAddTextOperationView.as_view()

class ApiGetTextInfo(SQL_Mixin, APIView):

    def get(self, request):
        """
        Получение информации о тексте

        Возвращает информацию о тексте, если такой текст существует в поле text
        таблицы AnyText: идентификатор, известность, общее количество благодарностей,
        количество утрат доверия. Если такого текста не существует,
        то вернуть все поля null.

        Если в запросе присутствует токен авторизации, то нужно вернуть
        и текущее состояние между пользователем, который запрашивает информацию,
        и текстом, о котором он запрашивает информацию.
        То есть информацию из таблицы CurrentState, где user_from =
        id_пользователя_из_токена, а text_id = id_текста_из_запроса.
        Если в CurrentState нет записи по заданным пользователям,
        то "thanks_count" = null и "is_trust" = null.
        Также нужно возвратить массив пользователей (их фото и UUID),
        которые благодарили текст, о котором запрашивается информация.
        Массив пользователей должен быть отсортирован по убыванию известности пользователей.
        Пример вызова:
        /api/gettextinfo?text=ЛЮБОЙ_ТЕКСТ ИЛИ http://ссылка.ком

        Пример возвращаемых данных:
        {
            "uuid": "3d20c185-388a-4e38-9fe1-6df8a31c7c31",
            "sum_thanks_count": 300,
            "fame": 3,
            "mistrust_count": 1,
            "trust_count": 2,
            "thanks_count": 12, // только при авторизованном запросе
            "is_trust": true,   // только при авторизованном запросе
            "thanks_users": [
                {
                "photo": "photo/url",
                "user_uuid": "6e14d54b-9371-431f-8bf0-6688f2cf2451"
                },
                {
                "photo": "photo/url",
                "user_uuid": "5548a8ba-ac47-400e-96f3-f3c9caa75383"
                },
                {
                "photo": "photo/url",
                "user_uuid": "7ced71b2-3b55-45bf-a622-57311dbc6c9f"
                }
            ]
        }

        """

        try:
            text = request.GET.get('text')
            if not text:
                raise ServiceException("Не задан text")
            try:
                anytext = AnyText.objects.get(text=text)
            except AnyText.DoesNotExist:
                raise ServiceException("Не найден text: %s" % text)
            data = dict(
                uuid=anytext.uuid,
                sum_thanks_count=anytext.sum_thanks_count,
                fame=anytext.fame,
                mistrust_count=anytext.mistrust_count,
                trust_count=anytext.trust_count,
            )
            user_from = request.user
            if user_from.is_authenticated:
                thanks_count = is_trust = None
                try:
                    currentstate = CurrentState.objects.get(
                        user_from=user_from,
                        anytext=anytext,
                    )
                    thanks_count = currentstate.thanks_count
                    is_trust = currentstate.is_trust
                except CurrentState.DoesNotExist:
                    pass
                data.update(
                    thanks_count=thanks_count,
                    is_trust=is_trust,
                )
            thanks_users = []
            req_str = """
                SELECT
                    uuid, photo
                FROM
                    users_profile
                WHERE
                    user_id IN (
                        SELECT
                            DISTINCT user_from_id AS id_
                        FROM
                            contact_journal
                        WHERE
                            anytext_id = %(anytext_id)s AND
                            operationtype_id = %(thank_id)s
                    )
                ORDER BY fame DESC
            """ % dict(
                anytext_id=anytext.pk,
                thank_id=OperationType.THANK,
            )
            with connection.cursor() as cursor:
                cursor.execute(req_str)
                recs = self.dictfetchall(cursor)
                for rec in recs:
                    thanks_users.append(dict(
                        photo = Profile.choose_photo_of(request, rec['photo']),
                        user_uuid=str(rec['uuid'])
                    ))
            data.update(
                thanks_users=thanks_users
            )
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_get_textinfo = ApiGetTextInfo.as_view()

class ApiGetTextOperationsView(APIView):

    def post(self, request):
        """
        Получение журнала операций по тексту

        Вернуть список из таблицы Journal, где anytext_id = “uuid”
        из запроса.
        Записи должны быть отсортированы по полю inseert_timestamp в
        убывающем порядке (т. е. сначала последние).
        И необходимо вернуть только count записей с "from"
        (постраничная загрузка).
        Запрос:
            {
                "uuid": "c01ee6a8-b6a1-4718-a6ef-de44a6dc54e9",
                "from": 0,
                "count": 20
            }
            from нет или null: сначала
            count нет или null: до конца
        Возвращает:
        {
            "operations":
            [
                {
                "user_id_from": "31f6a5b2-94a2-4993-9b13-f289318891e6",
                "photo": "/url",
                "first_name": "Видомина",
                "last_name": "Павлова-Аксёнова",
                "operation_type_id": 1,
                "timestamp": 384230840234,
                "comment": "Хороший человек"
                },
                …
            ]
        }
        """

        try:
            anytext_uuid = request.data.get("uuid")
            if not anytext_uuid:
                raise ServiceException('Не задан uuid')
            try:
                anytext = AnyText.objects.get(uuid=anytext_uuid)
            except ValidationError:
                raise ServiceException('Неверный uuid = %s' % anytext_uuid)
            except AnyText.DoesNotExist:
                raise ServiceException('Не найден текст, uuid = %s' % anytext_uuid)
            from_ = request.data.get("from")
            if not from_:
                from_ = 0
            count = request.data.get("count")
            qs = Journal.objects.filter(anytext=anytext). \
                    order_by('-insert_timestamp'). \
                    select_related('user_from__profile')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            data = [
                dict(
                    user_id_from=j.user_from.profile.uuid,
                    first_name=j.user_from.first_name,
                    last_name=j.user_from.last_name,
                    photo=j.user_from.profile.choose_photo(request),
                    operation_type_id=j.operationtype.pk,
                    timestamp=j.insert_timestamp,
                    comment=j.comment,
                ) for j in qs
            ]
            status_code = status.HTTP_200_OK
            data = dict(operations=data)
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_text_operations = ApiGetTextOperationsView.as_view()

class ApiGetUserOperationsView(APIView):

    #TODO
    # Смотри комментарии к модели Journal.
    # Пока этот метод не используется, можно подождать.

    def post(self, request):
        """
        Получение журнала операций по пользователю

        Вернуть список из таблицы Journal, где user_id_to = "uuid".
        Записи должны быть отсортированы по полю insert_timestamp
        в убывающем порядке (т. е. сначала последние).
        И необходимо вернуть только count записей с "from"
        (постраничная загрузка).
        Запрос:
            {
                "uuid": "c01ee6a8-b6a1-4718-a6ef-de44a6dc54e9",
                "from": 0,
                "count": 20
            }
            from нет или null: сначала
            count нет или null: до конца
        Возвращает:
        {
            "operations":
            [
                {
                "user_id_from": "31f6a5b2-94a2-4993-9b13-f289318891e6",
                "photo": "/url",
                "first_name": "Видомина",
                "last_name": "Павлова-Аксёнова",
                "operation_type_id": 1,
                "timestamp": 384230840234,
                "comment": "Хороший человек",
                "is_active": true,
                },
                …
            ]
        }
        """

        try:
            user_to_uuid = request.data.get("uuid")
            if not user_to_uuid:
                raise ServiceException('Не задан uuid')
            try:
                profile_to = Profile.objects.get(uuid=user_to_uuid)
                user_to = profile_to.user
            except ValidationError:
                raise ServiceException('Неверный uuid = %s' % user_to_uuid)
            except Profile.DoesNotExist:
                raise ServiceException('Не найден пользователь, uuid = %s' % user_to_uuid)
            from_ = request.data.get("from")
            if not from_:
                from_ = 0
            count = request.data.get("count")
            qs = Journal.objects.filter(user_to=user_to). \
                    order_by('-insert_timestamp'). \
                    select_related('user_from__profile')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            data = [
                dict(
                    user_id_from=j.user_from.profile.uuid,
                    first_name=j.user_from.first_name,
                    last_name=j.user_from.last_name,
                    is_active=j.user_from.is_active,
                    photo=j.user_from.profile.choose_photo(request),
                    operation_type_id=j.operationtype.pk,
                    timestamp=j.insert_timestamp,
                    comment=j.comment,
                ) for j in qs
            ]
            status_code = status.HTTP_200_OK
            data = dict(operations=data)
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_user_operations = ApiGetUserOperationsView.as_view()

class ApiTgGroupConnectionsMixin(object):
    """
    Получить данные о группе из запроса

    Возвращает:
        tg_group_id:
            None, если не было в запросе ничего о группе/канале
            0, если было в запросе о группе/канале
            id группы/канала, если группа/канал найден
        tggroup:
            запись о группе/канале или None
    """

    def get_tg_group_id(self, request):
        tg_group_id, tggroup = None, None
        tg_group_chat_id = request.GET.get('tg_group_chat_id')
        tggroup = None
        if tg_group_chat_id is not None:
            if tg_group_chat_id:
                try:
                    tg_group_chat_id = int(tg_group_chat_id)
                except ValueError:
                    tg_group_chat_id = 0
        if tg_group_chat_id is not None:
            tg_group_id = tg_group_chat_id
            if tg_group_id:
                try:
                    tggroup = TgGroup.objects.get(chat_id=tg_group_chat_id)
                    tg_group_id = tggroup.pk
                except TgGroup.DoesNotExist:
                    tg_group_id = 0
        return tg_group_id, tggroup


class ApiGetStats(SQL_Mixin, TelegramApiMixin, ApiTgGroupConnectionsMixin, APIView):

    # За сколько часов берем статистику
    #
    LAST_STAT_HOURS = 48

    def get(self, request, *args, **kwargs):
        """
        Получение статистики, диаграмм и проч.

        Что получать, определяется в словаре kwargs
        """
        return Response(data=self.get_stats(request, *args, **kwargs), status=status.HTTP_200_OK)

    def get_stats(self, request, *args, **kwargs):

        if kwargs.get('only') == 'user_connections_graph':

            # Возвращает:
            #  список пользователей, которые выполнили логин в систему
            #  (т.е. все, кроме родственников)
            #
            #   без параметров:
            #       список тех пользователей, и связи,
            #       где есть доверие (currentstate.is_trust == True).
            #   с параметром query:
            #       у которых в
            #               имени или
            #               фамилии или
            #               возможностях или
            #               ключах или
            #               желаниях
            #       есть query, и их связи,
            #       где есть доверие (currentstate.is_trust == True).
            #   В любом случае возвращаются в массиве users еще
            #   данные пользователя, если он авторизовался, а также
            #   связи с попавшими в выборку по query и/или в страницу from...
            #   number.
            #   Cписок выдается по страницам найденных (или всех) пользователей,
            #   в порядке убывания даты регистрации пользователя,
            #   начало страницы -- параметр from (нумерация с 0), по умолчанию 0
            #   сколько на странице -- параметр number, по умолчанию 50
            #   с параметром count:
            #       число пользователей, всех или найденных по фильтру query
            #
            #   При наличии непустого параметра tg_group_chat_id ищет
            #   только тех, кто в этой телеграм группе
            #
            #   Учитывается также get параметр fmt, особенно при tg_group_chat_id,
            #   если fmt == '3d-force-graph', то формат вывода связей и юзеров
            #   короткий

            fmt = request.GET.get('fmt', 'd3js')
            short = fmt == '3d-force-graph'
            q_users = Q(is_superuser=False)

            tg_group_id, tggroup = self.get_tg_group_id(request)
            if tg_group_id is not None:
                tg_group_id = tg_group_id or 0;
                q_users &= Q(
                    oauth__provider=Oauth.PROVIDER_TELEGRAM,
                    oauth__groups__pk=tg_group_id,
                )

            query = request.GET.get('query')
            if query:
                q_users &= \
                    Q(first_name__icontains=query) | \
                    Q(wish__text__icontains=query) | \
                    Q(ability__text__icontains=query) | \
                    Q(key__value__icontains=query)
            users_selected = User.objects.filter(q_users).distinct()

            count = request.GET.get('count')
            if count:
                return dict(count=users_selected.count())

            try:
                from_ = int(request.GET.get("from"))
                if from_ <= 0:
                    from_ = 0
            except (ValueError, TypeError, ):
                from_ = 0
            try:
                number_ = int(request.GET.get("number"))
            except (ValueError, TypeError, ):
                number_ = settings.PAGINATE_USERS_COUNT

            if fmt == '3d-force-graph':
                users_selected = users_selected.select_related('profile')
            else:
                users_selected = users_selected.select_related('profile', 'profile__ability').order_by('-date_joined')

            users = []
            user_pks = []
            if number_ > 0:
                users_selected = users_selected[from_:from_ + number_]
            else:
                users_selected = users_selected[from_:]
            for user in users_selected:
                profile = user.profile
                users.append(profile.data_dict(request, short=short, fmt=fmt))
                user_pks.append(user.pk)

            if request.user and request.user.is_authenticated:
                if request.user.pk not in user_pks:
                    user= request.user
                    profile = user.profile
                    users.append(profile.data_dict(request, short=short, fmt=fmt))
                    user_pks.append(user.pk)

            connections = []
            q_connections = Q(
                is_reverse=False,
                is_trust=True,
                user_to__isnull=False,
            )
            q_connections &= Q(user_to__pk__in=user_pks) & Q(user_from__pk__in=user_pks)
            for cs in CurrentState.objects.filter(q_connections).select_related(
                    'user_from__profile', 'user_to__profile',
                ).distinct():
                connections.append(cs.data_dict(show_trust=True, fmt=fmt))

            if fmt == '3d-force-graph':
                bot_username = self.get_bot_username()
                result = dict(bot_username=bot_username, nodes=users, links=connections)
                if tggroup:
                    result.update(tg_group=dict(type=tggroup.type, title=tggroup.title))
            else:
                result = dict(users=users, connections=connections)
            return result

        if kwargs.get('only') == 'users':
            # Вернуть число пользователей и симтомов
            #
            return dict(
                users=UserSymptom.objects.all().distinct('incognitouser').count(),
                symptoms=UserSymptom.objects.all().count(),
            )

        time_current = int(time.time())
        time_last = int(((time_current + 3599) / 3600)) * 3600
        time_1st = time_current - self.LAST_STAT_HOURS * 3600
        time_1st = int(time_1st / 3600) * 3600

        symptom_by_name = Symptom.objects.all().order_by('name')

        if kwargs.get('only') == 'symptoms_names':
            data = [
                {
                    'id': str(symptom.pk),
                    'name': symptom.name,
                }
                for symptom in symptom_by_name
            ]
            return data

        selected_ids_str = request.GET.get('selected_ids_str', '')
        m = re.search(r'\((\S*)\)', selected_ids_str)
        selected_ids_list = []
        selected_ids_where = ''
        if m:
            m_group = m.group(1)
            if m_group:
                for s in m_group.split(','):
                    try:
                        selected_ids_list.append(int(s))
                    except ValueError:
                        selected_ids_list = []
                        selected_ids_str = ''
                        break
        else:
            selected_ids_str = ''
        if len(selected_ids_list) == symptom_by_name.count():
            selected_ids_str = ''
        if selected_ids_str:
            selected_ids_where = ' AND symptom_id IN %s ' % selected_ids_str

        public_key = request.GET.get('public_key', '')
        incognitouser = None
        incognitouser_where = ''
        if public_key:
            try:
                incognitouser = IncognitoUser.objects.get(public_key=public_key)
                incognitouser_where = ' AND incognitouser_id = %s ' % incognitouser.pk
            except IncognitoUser.DoesNotExist:
                pass

        if kwargs.get('only') == 'symptoms':
            # Возвращает json:
            #   {
            #       "titles": [
            #           "симптом1 (всего, <за LAST_STAT_HOURS>, <за 24 HOURS>)",
            #           ...
            #           "симптомN (всего, <за LAST_STAT_HOURS>, <за 24 HOURS>)",
            #       ],
            #       "counts_all": [
            #           "<всего симптомов1>",
            #           ...
            #           "<всего симптомовN>"
            #       ],
            #       "counts_48h": [
            #           "<за LAST_STAT_HOURS симптомов1>",
            #           ...
            #           "<за LAST_STAT_HOURS симптомовN>"
            #       ],
            #       "counts_24h": [
            #           "<за 24 HOURS симптомов1>",
            #           ...
            #           "<за 24 HOURS симптомовN>"
            #       ],
            #   }
            #

            time_24h = time_current - 24 * 3600
            time_24h = int(time_24h / 3600) * 3600

            data = dict(
                titles=[],
                counts_all=[],
                counts_48h=[],
                counts_24h=[]
            )

            s_dict = dict()
            if selected_ids_str != '()':
                req_str = """
                    SELECT
                        contact_symptom.name AS name,
                        count(contact_usersymptom.id) as count
                    FROM
                        contact_usersymptom
                    LEFT JOIN
                        contact_symptom
                    ON
                        symptom_id=contact_symptom.id
                    WHERE
                        insert_timestamp < %(time_last)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        name
                    ORDER BY
                        count
                """ % dict(
                    time_last=time_last,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    symptoms = self.dictfetchall(cursor)
                for symptom in symptoms:
                    s_dict[symptom['name']] = dict(
                        count_all=symptom['count'],
                    )

            if selected_ids_str != '()':
                req_str = """
                    SELECT
                        contact_symptom.name AS name,
                        count(contact_usersymptom.id) as count
                    FROM
                        contact_usersymptom
                    LEFT JOIN
                        contact_symptom
                    ON
                        symptom_id=contact_symptom.id
                    WHERE
                        insert_timestamp < %(time_last)s AND
                        insert_timestamp >= %(time_1st)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        name
                    ORDER BY
                        count
                """ % dict(
                    time_last=time_last,
                    time_1st=time_1st,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    symptoms = self.dictfetchall(cursor)
                for symptom in symptoms:
                    s_dict[symptom['name']]['count_48h'] = symptom['count']
                for name in s_dict:
                    if not s_dict[name].get('count_48h'):
                        s_dict[name]['count_48h'] = 0

                req_str = """
                    SELECT
                        contact_symptom.name AS name,
                        count(contact_usersymptom.id) as count
                    FROM
                        contact_usersymptom
                    LEFT JOIN
                        contact_symptom
                    ON
                        symptom_id=contact_symptom.id
                    WHERE
                        insert_timestamp < %(time_last)s AND
                        insert_timestamp >= %(time_24h)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        name
                    ORDER BY
                        count
                """ % dict(
                    time_last=time_last,
                    time_24h=time_24h,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    symptoms = self.dictfetchall(cursor)
                for symptom in symptoms:
                    s_dict[symptom['name']]['count_24h'] = symptom['count']
                for name in s_dict:
                    if not s_dict[name].get('count_24h'):
                        s_dict[name]['count_24h'] = 0

            s_list = []
            for name in s_dict:
                title = '%s (%s, %s, %s)' % (
                    name,
                    s_dict[name]['count_all'],
                    s_dict[name]['count_48h'],
                    s_dict[name]['count_24h'],
                )
                s_list.append(dict(
                    title=title,
                    count_all=s_dict[name]['count_all'],
                    count_48h=s_dict[name]['count_48h'],
                    count_24h=s_dict[name]['count_24h'],
                ))
            s_list.sort(key = lambda d: d['count_all'])

            for s in s_list:
                data['titles'].append(s['title'])
                data['counts_all'].append(s['count_all'])
                data['counts_48h'].append(s['count_48h'])
                data['counts_24h'].append(s['count_24h'])
            return data


        if kwargs.get('only') == 'symptoms_hist_data':

            # Возвращает json, данные для гистогораммы
            # за последние 48 часов, для отрисовки
            # средстванми plotly на front end

            symptom_ids = dict()
            symptom_names = dict()
            n = 0
            for symptom in Symptom.objects.all().order_by('pk'):
                symptom_ids[symptom.pk] = n
                symptom_names[n] = symptom.name
                n += 1
            times = [[] for i in symptom_ids]
            q = Q(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                )
            if selected_ids_str:
                q &= Q(symptom__pk__in=selected_ids_list)
            if incognitouser:
                q &= Q(incognitouser=incognitouser)
            for usersymptom in UserSymptom.objects.filter(q).select_related('symptom'):
                times[symptom_ids[usersymptom.symptom.pk]].append(usersymptom.insert_timestamp)

            return dict(
                time_1st=time_1st,
                time_last=time_last,
                times=times,
                symptom_names=symptom_names,
            )

        if kwargs.get('only') == 'symptoms_moon_data':

            # Возвращает json, данные для графиков
            # симптомов по лунным дням за все время
            # наюлюдений для отрисовки
            # средстванми plotly на front end

            symptom_ids = dict()
            symptom_names = dict()
            n = 0
            for symptom in Symptom.objects.all().order_by('pk'):
                symptom_ids[symptom.pk] = n
                symptom_names[n] = symptom.name
                n += 1
            moon_bars = []
            if selected_ids_str != '()':
                moon_bars = [[0 for j in range(30)] for i in range(len(symptom_ids))]
                where = selected_ids_where + incognitouser_where
                if where:
                    where = re.sub(r'^\s*AND', '', where, flags=re.I)
                    where = 'WHERE ' + where
                req_str = """
                    SELECT
                        moon_day,
                        symptom_id,
                        Count(symptom_id) as count
                    FROM
                        contact_usersymptom
                    %(where)s
                    GROUP BY
                        moon_day,
                        symptom_id
                """ % dict(
                    where=where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = self.dictfetchall(cursor)
                for r in m:
                    moon_bars[symptom_ids[ r['symptom_id']] ] [r['moon_day']] = r['count']
                for i, symptom_bar in enumerate(moon_bars):
                    if not any(symptom_bar):
                        moon_bars[i] = []
                if not any(moon_bars):
                    moon_bars = []

            moon_hour = []
            max_count_in_hour = 0
            if moon_bars:

                # Получить примерно следующее по каждому симптому
                # из массива симптомов, которые идут в порядке
                # массива symptom_names. Итак, элемент для симптома
                # из массива moon_hour:
                #   [
                #       {2: {'count': 2, 'pos': 7.389655172413794}},
                #       {5: {'count': 8, 'pos': 4.5}},
                #       {5: {'count': 1, 'pos': 5.466666666666666}},
                #       {6: {'count': 2, 'pos': 22.380555555555556}},
                #       ...
                #   ]
                # Здесь:
                #   2, 5, 5, 6 -    лунные дни (ось x)
                #   2, 8, 1, 2 -    сколько раз появлялся симптом в позиции
                #                   pos (ось y). Например 7.38... - соответствует
                #                   7-му часу. В 7-м часе 2-го дня есть еще
                #                   симптомы, они будут располагаться
                #                   кружками размером count с некоторым сдвигом
                #                   по вертикали
                #                   А в 4-м часу 5-го дня, наверное, один
                #                   симптом, он будет располагаться посреди
                #                   "квадратика" для 4-го часа 5-го дня.
                #
                req_str = """
                    SELECT
                        moon_day,
                        ((insert_timestamp + timezone * 3600/100 + (timezone %% 100) * 60)/3600) %% 24 as hour,
                        symptom_id,
                        Count(DISTINCT id) as count
                    FROM
                        contact_usersymptom
                    %(where)s
                    GROUP BY
                        moon_day,
                        hour,
                        symptom_id
                    ORDER BY
                        count
                    DESC
                """ % dict(
                    where=where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = self.dictfetchall(cursor)
                s_d_h = [ [ [{'count': 0, 'pos': 0.5} for i in range(24)] for j in range(30) ] for k in range(len(symptom_ids)) ]
                d_h_s = [ [[] for i in range(24)] for j in range(30) ]
                for r in m:
                    if r['count']:
                        s_d_h[symptom_ids[ r['symptom_id']]] [r['moon_day']] [r['hour']] ['count'] = r['count']
                        d_h_s[r['moon_day']] [r['hour']].append({
                            symptom_ids[r['symptom_id']]: r['count']
                        })
                for s in range(len(symptom_ids)):
                    for d in range(30):
                        for h in range(24):
                            len_slist = len(d_h_s[d][h])
                            if len_slist <= 1:
                                continue
                            step = 0.5 / len_slist
                            y_current = 0.70
                            for ss in d_h_s[d][h]:
                                for k in ss.keys():
                                    s_d_h[k][d][h]['pos'] = y_current
                                    break
                                y_current -= step

                for s in range(len(symptom_ids)):
                    items = []
                    for d in range(30):
                        for h in range(24):
                            if s_d_h[s][d][h]['count']:
                                max_count_in_hour = max(max_count_in_hour, s_d_h[s][d][h]['count'])
                                items.append({
                                    d: {
                                        'count': s_d_h[s][d][h]['count'],
                                        'pos': h + s_d_h[s][d][h]['pos']
                                    }
                                })
                    moon_hour.append(items)

            return dict(
                current_moon_day = get_moon_day(time_current),
                moon_bars=moon_bars,
                moon_hour=moon_hour,
                symptom_names=symptom_names,
                max_count_in_hour=max_count_in_hour,
            )

        return dict()
api_get_stats = ApiGetStats.as_view()

class ApiAddUserSymptom(APIView):

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Добавление симптома пользователя (новая версия)

        Вставить переданные user_symptoms.
        Для этого метода есть url с обязательной авторизацией и без нее.
        Пример исходных данных:
        {
            "incognito_id": "2b0cdb0a-544d-406a-b832-6821c63f5d45"
            // Это временно. Из разряда "нет ничего более постоянного, чем временное" :)
            // В коде apk таки применяется incognito_id
            //
            // или
            "private_key": "2b0cdb0a-544d-406a-b832-6821c63fffff"
            "user_symptoms": [
                {
                    "symptom_id": 10,
                    "timestamp": 2341234134,
                    "timezone": "+0300",
                    "latitude": 22.4321,
                    "longitude": 32.2212
                },
                {
                    "symptom_id": 12,
                    "timestamp": 2341234195,
                    "timezone": "+0300",
                    "latitude": 22.4321,
                    "longitude": 32.2212
                }
            ]
        }
        Возвращает: {}
        """
        try:
            auth_only = kwargs.get('auth')
            if auth_only and not request.user.is_authenticated:
                raise AuthenticationFailed

            incognito_id = request.data.get("incognito_id")
            private_key = request.data.get("private_key")
            if not incognito_id and not private_key:
                raise ServiceException("Не задано ни incognito_id, ни private_key")
            if incognito_id and private_key:
                raise ServiceException("Заданы и incognito_id, и private_key")
            if private_key:
                private_key = private_key.lower()
                try:
                    incognitouser = IncognitoUser.objects.get(
                        private_key=private_key
                    )
                except IncognitoUser.DoesNotExist:
                    raise ServiceException("Не найден private_key среди incognito пользователей")
            else:
                # got incognito_id
                incognito_id = incognito_id.lower()
                incognitouser, created_ = IncognitoUser.objects.get_or_create(
                    private_key=incognito_id
                )

            user_symptoms = request.data.get("user_symptoms")
            if not isinstance(user_symptoms, list):
                raise ServiceException("Не заданы user_symptoms")
            n_key = 0
            for user_symptom in user_symptoms:
                try:
                    symptom_id = user_symptom['symptom_id']
                except KeyError:
                    raise ServiceException(MSG_NO_PARM % n_key)
                try:
                    symptom = Symptom.objects.get(pk=symptom_id)
                except Symptom.DoesNotExist:
                    raise ServiceException(
                        "Не найден symptom_id, элемент списка %s (начиная с нуля)" % n_key
                    )
                insert_timestamp = user_symptom.get('timestamp')
                latitude = user_symptom.get('latitude')
                longitude = user_symptom.get('longitude')
                timezone = user_symptom.get(
                    'timezone',
                    UserSymptom._meta.get_field('timezone').default
                )
                try:
                    timezone = int(timezone)
                except ValueError:
                    raise ServiceException(
                        "Неверная timezone, элемент списка %s (начиная с нуля)" % n_key
                    )
                usersymptom = UserSymptom.objects.create(
                    incognitouser=incognitouser,
                    symptom=symptom,
                    insert_timestamp=insert_timestamp,
                    latitude=latitude,
                    longitude=longitude,
                    timezone=timezone,
                )
                n_key += 1

            data = dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_user_symptom = ApiAddUserSymptom.as_view()

class ApiGetSymptoms(APIView):

    def post(self, request):
        """
        Получить группы симптомов, симптомы, их контрольную сумму

        Сравнивает контрольную сумму справочника симптомов
        с переданной контрольной суммой.
        Если они различаются, то возвращает все данные из таблиц
        Symptom и SymptomGroup
        """

        try:
            if 'checksum' not in request.data:
                raise ServiceException('Не задана checksum')
            checksum_got = request.data.get("checksum")
            checksum_here = SymptomChecksumManage.get_symptoms_checksum().value
            changed = checksum_got != checksum_here
            data = dict(changed=changed)
            if changed:
                data.update(checksum=checksum_here)
                data.update(SymptomChecksumManage.get_symptoms_dict())
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_getsymptoms = ApiGetSymptoms.as_view()

class ApiAddOrUpdateWish(UuidMixin, APIView):

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Создать либо обновить желание

        - задан параметр tg_token, совпадающий с токеном бота телеграма:
            - user_uuid, обязательно
            - update_main, true или false, необязательно, править первое желание, если оно имеется
            - uuid: uuid желания:  если задано, то update_main не учитывается.
                    Если желания с таким uuid не существует, то создать.
            - text: обязательно, текст желания
            - last_edit: необязательно, время добавления/правки
        - не задан параметр tg_token. Авторизация обязательна
            - user_uuid, не обязательно, если не задан, то правим или добавляем свое желание
            - update_main, true или false, необязательно, править первое желание, если оно имеется
            - uuid: uuid желания:  если задано, то update_main не учитывается.
                    Если желания с таким uuid не существует, то создать.
            - text: обязательно, текст желания
            - last_edit: необязательно, время добавления/правки

        Пример исходных данных:
        * Создать желание (uuid не задан)
            {
                "text": "Хочу, хочу, хочу...",
                "last_edit": 154230840234
            }
        * Обновить или обновить желание (uuid задан)
            {
                "uuid": "e17a34d0-c6c4-4755-a67b-7e7d13e4bd4b",
                "text": "Хочу, хочу, хочу...",
                "last_edit": 154230840234
            }
        Возвращает: {}
        """
        try:
            text = request.data.get('text', '').strip()
            if not text:
                raise ServiceException('Текст обязателен')
            update_timestamp = request.data.get('last_edit', int(time.time()))
            tg_token = request.data.get('tg_token')
            if tg_token and tg_token != settings.TELEGRAM_BOT_TOKEN:
                raise ServiceException('Неверный токен телеграм бота')
            user_uuid = request.data.get('user_uuid')
            if tg_token and not user_uuid:
                raise ServiceException('Не задан user_uuid')
            if not tg_token and not request.user.is_authenticated:
                raise NotAuthenticated
            if tg_token:
                owner, profile = self.check_user_uuid(user_uuid)
            else:
                owner, profile = self.check_user_or_owned_uuid(request, uuid_field='user_uuid')
            uuid = None
            update_main = request.data.get('update_main')
            if update_main:
                try:
                    uuid = Wish.objects.filter(owner=owner).order_by('insert_timestamp')[0].uuid
                except IndexError:
                    pass
            if not uuid:
                uuid = request.data.get('uuid')
            if uuid:
                do_create = False
                try:
                    wish = Wish.objects.get(uuid=uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Wish.DoesNotExist:
                    do_create = True
                    wish = Wish.objects.create(
                        uuid=uuid,
                        owner=owner,
                        text=text,
                        update_timestamp=update_timestamp,
                    )
                if not do_create:
                    if not tg_token and wish.owner != request.user and wish.owner.profile.owner != request.user:
                        raise ServiceException('Желание с uuid = %s не принадлежит ни Вам, ни Вашему родственнику' % uuid)
                    wish.text = text
                    wish.update_timestamp = update_timestamp
                    wish.save()
            else:
                do_create = True
                wish = Wish.objects.create(
                    owner=owner,
                    text=text,
                    update_timestamp=update_timestamp,
                )
            data = wish.data_dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_or_update_wish = ApiAddOrUpdateWish.as_view()

class ApiDeleteWish(APIView):
    permission_classes = (IsAuthenticated, )

    def get(self, request, *args, **kwargs,):
        """
        Удалить желание uuid

        Проверить, принадлежит ли желание пользователю, пославшему запрос,
        или его родственнику, и
        если принадлежит, то удалить его, иначе вернуть сообщение об ошибке.
        Пример исходных данных:
        /api/deletewish?uuid=4d02e22c-b6eb-4307-a440-ccafdeedd9b8
        Возвращает: {}
        """
        try:
            uuid = request.GET.get('uuid')
            if uuid:
                try:
                    wish = Wish.objects.get(uuid=uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Wish.DoesNotExist:
                    raise ServiceException(
                        'Желание с uuid = %s не найдено' % uuid
                    )
                if wish.owner != request.user and wish.owner.profile.owner != request.user:
                    raise ServiceException('Желание с uuid = %s не принадлежит ни Вам, ни Вашему родственнику' % uuid)
                wish.delete()
            else:
                raise ServiceException('Не задан uuid желания')
            data = dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_wish = ApiDeleteWish.as_view()

class ApiGetWishInfo(APIView):

    def get(self, request, *args, **kwargs):
        """
        Возвращает информацию о желании

        Пример исходных данных:
        /api/getwishinfo?uuid=4d02e22c-b6eb-4307-a440-ccafdeedd9b8
        Возвращает:
        {
            "owner_id":"e17a34d0-c6c4-4755-a67b-7e7d13e4bd4b",
            "text":"Хочу хочу хочу...",
            "last_edit":384230840234
        }

        """
        try:
            uuid = request.GET.get('uuid')
            if uuid:
                try:
                    wish = Wish.objects.get(uuid=uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Wish.DoesNotExist:
                    raise ServiceException('Не найдено желание с uuid = %s' % uuid)
                data = dict(
                    owner_id=wish.owner.profile.uuid,
                    text=wish.text,
                    last_edit=wish.update_timestamp,
                )
                status_code = status.HTTP_200_OK
            else:
                raise ServiceException('Не задан uuid желания')
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_wish_info = ApiGetWishInfo.as_view()

class ApiGetUserWishes(UuidMixin, APIView):

    def get(self, request, *args, **kwargs):
        """
        Возвращает список желаний пользователя

        Пример исходных данных:
        /api/getuserwishes?uuid=172da3fe-dd30-4cb8-8df3-46f69785d30a
        Возвращает:
        {
            "wishes": [
                {
                    "uuid": "e17a34d0-c6c4-4755-a67b-7e7d13e4bd4b",
                    "text": "Хочу, хочу, хочу...",
                    "last_edit": 184230840234
                },
                ...
            ]
        }

        """
        try:
            uuid = request.GET.get('uuid')
            user, profile = self.check_user_uuid(uuid)
            qs = Wish.objects.filter(owner=user).order_by('update_timestamp')
            try:
                from_ = request.GET.get("from", 0)
                from_ = int(from_) if from_ else 0
                count = request.GET.get("count", 0)
                count = int(count) if count else 0
            except ValueError:
                raise ServiceException('Неверный from или count')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            data = dict(
                wishes = [wish.data_dict() for wish in qs]
            )
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_user_wishes = ApiGetUserWishes.as_view()

class MergeSymptomsView(View):

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        try:
            src = Symptom.objects.get(pk=request.POST['symptom_src_pk'])
            dst = Symptom.objects.get(pk=request.POST['symptom_dst_pk'])
        except (Symptom.DoesNotExist, KeyError, IndexError,):
            raise Http404
        UserSymptom.objects.filter(symptom=src).update(symptom=dst)
        src.delete()
        return redirect('/admin/contact/symptom/')

merge_symptoms = MergeSymptomsView.as_view()

class ApiGetUserKeys(UuidMixin, APIView):

    def get(self, request, *args, **kwargs):
        """
        Возвращает список ключей пользователя

        Пример исходных данных:
        /api/getuserkeys?uuid=172da3fe-dd30-4cb8-8df3-46f69785d30a
        Возвращает:
        {
            "keys": [
                {
                "id": 234,
                "value": "6354654651",
                "type_id": 1
                },
                {
                "id": 4234,
                "value": "asdf@fdsa.com",
                "type_id": 2
                },
            ...
            ]
        }
        """
        try:
            uuid = request.GET.get('uuid')
            user, profile = self.check_user_uuid(uuid)
            qs = Key.objects.filter(owner=user).order_by('pk')
            try:
                from_ = request.GET.get("from", 0)
                from_ = int(from_) if from_ else 0
                count = request.GET.get("count", 0)
                count = int(count) if count else 0
            except ValueError:
                raise ServiceException('Неверный from или count')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            data = dict(
                keys = [ key.data_dict() for key in qs ]
            )
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_user_keys = ApiGetUserKeys.as_view()

class ApiAddKeyView(UuidMixin, APIView):

    @transaction.atomic
    def post(self, request):
        """
        Добавление ключа (ключей)

        Если запрос идет от телеграм бота:
            Исходные данные:
                {
                    "owner_uuid": ".....",
                    "user_uuid": "....",
                    keys: [
                        "ключ 1",
                        "ключ 2"
                        ...
                    ]
                }
            owner_uuid и user_uuid не совпадают, когда производится замена
            ключей родственника user_uuid, владельцем которого является
            owner_uuid.
            Все прежние ключи пользователя user_uuid с типом KeyType.OTHER_ID удаляются.
            Все переданные ключи записываются с типом KeyType.OTHER_ID

        Если запрос идет не от телеграм бота:
            Добавить ключ в таблицу Key, свой ключ или родственника.
            Если такой ключ уже существует (пара значение-тип ключа),
            то вернуть ошибку.

            Пример исходных данных:
            {
                "user_uuid": "...."
                // свой или родственника. Если отсутствует user_uuid, значит свой ключ
                "value": "56648",
                "type_id": 1
            }
        """
        try:
            if request.data.get('tg_token'):
                if request.data['tg_token'] != settings.TELEGRAM_BOT_TOKEN:
                    raise ServiceException('Неверный токен телеграм бота')
                if not (request.data.get('owner_uuid') and request.data.get('user_uuid') and request.data.get('keys')):
                    raise ServiceException('Не задан(ы) owner_uuid и/или user_uuid и/или keys')
                owner, owner_profile = self.check_user_uuid(request.data['owner_uuid'], related=('owner', ))
                if request.data['owner_uuid'] == request.data['user_uuid']:
                    if owner_profile.owner:
                        raise ServiceException('Пользователь (owner_uuid == user_uuid): им кто-то владеет')
                    user, user_profile = owner, owner_profile
                else:
                    user, user_profile = self.check_user_uuid(request.data['user_uuid'], related=('owner', ))
                    if owner != user_profile.owner:
                        raise ServiceException('Профиль user_uuid не подлежит правке пользователем owner_uuid')
                Key.objects.filter(type__pk=KeyType.OTHER_ID, owner=user).delete()
                for value in request.data['keys']:
                    key, created_ = Key.objects.get_or_create(
                        type_id=KeyType.OTHER_ID,
                        value=value,
                        defaults=dict(
                            owner=user,
                    ))
                    if not created_:
                        raise ServiceException('Контакт "%s" есть уже у другого человека' % value,
                            '%s' % key.owner.pk,
                        )
                data = user_profile.data_dict(request)
                data.update(user_profile.parents_dict(request))
                data.update(user_profile.data_WAK())
                data.update(
                    user_id=user.pk,
                    owner_id=user_profile.owner and user_profile.owner.pk or None,
                )
            else:
                if not request.user.is_authenticated:
                    raise NotAuthenticated
                owner, profile = self.check_user_or_owned_uuid(request, uuid_field='user_uuid',)
                value = request.data.get("value")
                type_id = request.data.get("type_id")
                if not value or not type_id:
                    raise ServiceException('Не задан(ы) value и/или type_id')
                try:
                    keytype = KeyType.objects.get(pk=int(type_id))
                except KeyType.DoesNotExist:
                    raise ServiceException('Не найден тип ключа type_id = %s' % type_id)
                key, created_ = Key.objects.get_or_create(
                    type=keytype,
                    value=value,
                    defaults=dict(
                        owner=owner,
                ))
                if not created_:
                    raise ServiceException('Такой контакт уже существует')
                data = key.data_dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            try:
                pk=excpt.args[1]
                profile = Profile.objects.select_related('user').get(user__pk=pk)
                data.update(profile=profile.data_dict(request))
            except IndexError:
                pass
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_key = ApiAddKeyView.as_view()

class ApiUpdateKeyView(APIView):
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        """
        Обновление ключа

        Обновить ключ в таблице tbl_key,  свой ключ или родственника.
        Если такого ключа не существует или если пользователь пытается обновить ключ,
        который не принадлежит ему или его родственнику,
        то вернуть ошибку.

        Пример исходных данных:
        {
            "id": 4654645,
            "value": "56648",
            "type_id": 1
        }
        """
        try:
            id_ = request.data.get("id")
            value = request.data.get("value")
            type_id = request.data.get("type_id")
            if not value or not type_id or not id_:
                raise ServiceException('Не задан(ы) id и/или value и/или type_id')
            try:
                keytype = KeyType.objects.get(pk=int(type_id))
            except KeyType.DoesNotExist:
                raise ServiceException('Не найден тип ключа type_id = %s' % type_id)
            try:
                key = Key.objects.get(pk=id_)
            except (ValueError, Key.DoesNotExist):
                raise ServiceException('Не найден ключ id = %s' % id_)
            if key.owner != request.user and key.owner.profile.owner != request.user:
                raise ServiceException('Ключ id = %s не принадлежит ни Вам, ни вашему родственнику' % id_)
            try:
                key.type = keytype
                key.value = value
                key.save()
            except IntegrityError:
                raise ServiceException('Попытка замены ключа на уже существующий')
            data = key.data_dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_update_key = ApiUpdateKeyView.as_view()

class ApiDeleteKeyView(APIView):
    permission_classes = (IsAuthenticated, )

    def get(self, request):
        """
        Удаление ключа

        Удалить ключ в таблице tbl_key. Если такого ключа не существует или
        если пользователь пытается обновить ключ, который не принадлежит
        ему или его родственнику, то вернуть ошибку

        Пример исходных данных:
        /api/deletekey?id=324342
        """
        try:
            id_ = request.GET.get("id")
            if not id_:
                raise ServiceException('Не задан id ключа')
            try:
                key = Key.objects.get(pk=id_)
            except (ValueError, Key.DoesNotExist):
                raise ServiceException('Не найден ключ id = %s' % id_)
            if key.owner != request.user and key.owner.profile.owner != request.user:
                raise ServiceException('Ключ id = %s не принадлежит ни Вам, ни вашему родственнику' % id_)
            key.delete()
            data = dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_key = ApiDeleteKeyView.as_view()


class ApiProfileGraph(UuidMixin, SQL_Mixin, ApiTgGroupConnectionsMixin, TelegramApiMixin, APIView):

    def get(self, request, *args, **kwargs):
        """
        Возвращает связи пользователя
        Если параметр fmt != '3d-force-graph', то еще его желания и ключи

        Параметры:
        uuid
            Опрашиваемый пользователь

        Если fmt == '3d-force-graph', то вывод:
        {
            "bot_username": "DevBlagoBot",
            "nodes": [
            {
                "id": 1228,
                "uuid": "6f9a0e44-9a58-47ce-9e8d-55fac1cbc685",
                "first_name": "Просковья Александровна Иванова",
                "photo": ""
            },
            ...
            ],
            "links": [
            {
                "is_trust": true,
                "source": 1228,
                "target": 436
            },
            ...
            ]
        }

        Остальные параметры, если fmt != '3d-force-graph'
        count=1
            Возвращать лишь число пользователей -  ближайших связей опрашиваемого
        from
            Начало выборки, по умолчанию 0
        number
            Сколько ближайших связей выдавать среди всех (без параметра query)
            или среди найденных (с параметром query)
        query
            Поиск среди ближайших связей по
                имени или
                фамилии или
                возможностях или
                ключах или
                желаниях

        С параметром count возвращает лишь число ближайших связей запрашиваемого
        среди всех или найденных по query

        Иначе возвращает ближайшие связи пользователя, его желания и ключи.
        Также возвращает связи между этими ближайшими связями

        Ближайшие связи возвращаются постранично,
        в порядке убывания даты регистрации пользователя
        из ближайшего окружения опрашиваемого

        Если пользователь, выполняющий запрос, авторизован,
        то он будет обязательно в выводе метода, возможно,
        со связями пользователей, попавших в выборку

        Пример вызова:
        /api/profile_graph?uuid=91c49fe2-3f74-49a8-906e-f4f711f8e3a1
        Возвращает:
        С параметром count: { "count": 444 }
        Без параметра count:
        {
            "users": [
                    {
                        "uuid": "8d2db918-9a81-4537-ab69-1c3d2d19a00d",
                        "first_name": "Олег",
                        "last_name": ".",
                        "photo": "https://...jpg",
                        "is_active": true,
                        "latitude": 54.32,
                        "longitude": 32.54,
                        "ability": “Всё могу”,
                    },
                    ...
            ],
            "connections": [
                    {
                        "source": "8d2db918-9a81-4537-ab69-1c3d2d19a00d",
                        "target": "1085113f-d4d8-4de6-8d80-916e85576fc6",
                        "thanks_count": 1,
                        "is_trust": true
                    },
                    ...
            ],
            "wishes":[
                {
                    "uuid":1,
                    "text": "хочу то…"
                },
            ],
            "keys":[
                {
                    "id":1,
                    "value": "asdf@fdas.com"
                    "type_id": 2
                },
            ]
            "abilities":[
                {
                    "uuid":"1085113f-d4d8-4de6-8d80-916bbbbbbbb",
                    "text": "могу то…"
            ]
            ...
        }
        """
        try:
            data = dict()
            status_code = status.HTTP_200_OK
            fmt = request.GET.get('fmt')
            uuid = request.GET.get('uuid')
            user_q, profile_q = self.check_user_uuid(uuid)
            req_union = """
                SELECT
                    DISTINCT user_to_id as id
                FROM
                    contact_currentstate
                WHERE
                    is_reverse = false AND
                    is_trust = true AND
                    user_to_id IS NOT NULL AND
                    user_from_id = %(user_q_pk)s
                UNION
                SELECT
                    DISTINCT user_from_id as id
                FROM
                    contact_currentstate
                WHERE
                    is_reverse = false AND
                    is_trust is not null AND
                    user_to_id = %(user_q_pk)s
            """ % dict(
                user_q_pk=user_q.pk
            )

            tg_group_id, tggroup = self.get_tg_group_id(request)
            if tg_group_id is not None:
                inner_joins = """
                    INNER JOIN
                        users_oauth ON (auth_user.id = users_oauth.user_id)
                    INNER JOIN
                        users_oauth_groups ON (users_oauth.id = users_oauth_groups.oauth_id)
                """
                and_tg_group_id = ' AND users_oauth_groups.tggroup_id = %s ' % tg_group_id
            else:
                inner_joins = ''
                and_tg_group_id = ''

            if fmt == '3d-force-graph':
                outer_joins = """
                    LEFT OUTER JOIN
                        users_profile ON (auth_user.id = users_profile.user_id)
                """
                req = """
                    SELECT
                        distinct auth_user.id as id,
                        auth_user.is_active,
                        auth_user.first_name,
                        users_profile.uuid,
                        users_profile.photo
                    FROM
                        auth_user
                    %(outer_joins)s
                    %(inner_joins)s
                    WHERE
                        auth_user.id IN (%(req_union)s) %(and_tg_group_id)s
                """ % dict(
                    req_union=req_union,
                    outer_joins=outer_joins,
                    inner_joins=inner_joins,
                    and_tg_group_id=and_tg_group_id,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req)
                    recs = self.dictfetchall(cursor)
                nodes = []
                user_pks = []
                bot_username = self.get_bot_username()
                nodes.append(dict(
                    id=user_q.pk,
                    uuid=user_q.profile.uuid,
                    first_name=user_q.first_name,
                    photo=Profile.image_thumb(
                        request, user_q.profile.photo,
                        method='crop-green-frame-3',
                        put_default_avatar=True,
                    ),
                ))
                user_pks.append(user_q.pk)
                for rec in recs:
                    if rec['id'] not in user_pks:
                        nodes.append(dict(
                            id=rec['id'],
                            uuid=rec['uuid'],
                            first_name=rec['first_name'],
                            photo=Profile.image_thumb(request, rec['photo']),
                        ))
                        user_pks.append(rec['id'])
                links = []
                if user_q.pk not in user_pks:
                    user_pks.append(user_q.pk)
                q = Q(user_from__in=user_pks) & Q(user_to__in=user_pks)
                q &= Q(user_to__isnull=False) & Q(is_reverse=False) & Q(is_trust__isnull=False)
                for cs in CurrentState.objects.filter(q).select_related(
                    'user_to__profile', 'user_from__profile',
                    ).distinct():
                    links.append(cs.data_dict(fmt=fmt, show_trust=True))
                data.update(bot_username=bot_username, nodes=nodes, links=links, user_q_name=user_q.first_name)
                if tggroup:
                    data.update(tg_group=dict(type=tggroup.type, title=tggroup.title))

            else:
                # fmt != '3d-force-graph, "old 3d style"
                outer_joins = """
                    LEFT OUTER JOIN
                        contact_wish ON (auth_user.id = contact_wish.owner_id)
                    LEFT OUTER JOIN
                        contact_ability ON (auth_user.id = contact_ability.owner_id)
                    LEFT OUTER JOIN
                        contact_key ON (auth_user.id = contact_key.owner_id)
                    LEFT OUTER JOIN
                        users_profile ON (auth_user.id = users_profile.user_id)
                    LEFT OUTER JOIN
                        contact_ability profile__ability ON (users_profile.ability_id = profile__ability.uuid)
                """
                query = request.GET.get('query', '')
                if query:
                    # '%QUERY%' :
                    like_value = "'%" + self.sql_like_value(query.upper()) + "%'"
                    query_where = """
                        UPPER(auth_user.first_name) LIKE %(like_value)s OR
                        UPPER(contact_wish.text) LIKE %(like_value)s OR
                        UPPER(contact_ability.text) LIKE %(like_value)s OR
                        UPPER(contact_key.value) LIKE %(like_value)s
                    """ % dict(like_value=like_value)

                if request.GET.get('count'):
                    if query:
                        req = """
                            SELECT
                                Count(distinct auth_user.id) as count
                            FROM
                                auth_user
                            %(outer_joins)s
                            %(inner_joins)s
                            WHERE
                                auth_user.id IN (%(req_union)s) AND
                                (%(query_where)s) %(and_tg_group_id)s
                        """ % dict(
                            outer_joins=outer_joins,
                            query_where=query_where,
                            req_union=req_union,
                            inner_joins=inner_joins,
                            and_tg_group_id=and_tg_group_id,
                        )
                    else:
                        if tg_group_id is not None:
                            req = """
                                SELECT
                                    Count(distinct auth_user.id) as count
                                FROM
                                    auth_user
                                %(inner_joins)s
                                WHERE
                                    auth_user.id IN (%(req_union)s) %(and_tg_group_id)s
                            """ % dict(
                                outer_joins=outer_joins,
                                req_union=req_union,
                                inner_joins=inner_joins,
                                and_tg_group_id=and_tg_group_id,
                            )
                        else:
                            req = """
                                SELECT
                                    Count(distinct id) as count
                                FROM
                                    (%(req_union)s) as foo
                            """ % dict(
                                req_union=req_union
                            )

                    with connection.cursor() as cursor:
                        cursor.execute(req)
                        recs = self.dictfetchall(cursor)
                    return Response(data=dict(count=recs[0]['count']), status=status_code)

                try:
                    from_ = abs(int(request.GET.get('from')))
                except (ValueError, TypeError, ):
                    from_ = 0
                try:
                    number_ = abs(int(request.GET.get('number')))
                except (ValueError, TypeError, ):
                    number_ = settings.PAGINATE_USERS_COUNT

                req = """
                    SELECT
                        distinct auth_user.id,
                        auth_user.is_active,
                        auth_user.first_name,
                        auth_user.last_name,
                        auth_user.date_joined,

                        users_profile.middle_name,
                        users_profile.gender,
                        users_profile.latitude,
                        users_profile.longitude,
                        users_profile.photo,
                        users_profile.uuid,

                        users_profile.dob,
                        users_profile.dob_no_day,
                        users_profile.dob_no_month,

                        users_profile.is_dead,
                        users_profile.dod,
                        users_profile.dod_no_day,
                        users_profile.dod_no_month,

                        profile__ability.text,
                        users_profile.comment
                    FROM
                        auth_user
                    %(outer_joins)s
                    %(inner_joins)s
                    WHERE
                        auth_user.id IN (%(req_union)s) %(and_tg_group_id)s
                """ % dict(
                    outer_joins=outer_joins,
                    req_union=req_union,
                    inner_joins=inner_joins,
                    and_tg_group_id=and_tg_group_id,
                )
                if query:
                    req += "AND (%(query_where)s)" % dict(query_where=query_where)
                req += """
                    ORDER BY
                        date_joined
                    DESC
                    OFFSET %(from_)s
                    LIMIT %(number_)s
                """ % dict(
                    from_=from_,
                    number_=number_,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req)
                    recs = self.dictfetchall(cursor)
                users = []
                users.append(profile_q.data_dict(request))
                user_pks = []
                for rec in recs:
                    dod=UnclearDate.str_safe_from_rec(rec, 'dod')
                    users.append(dict(
                        uuid=rec['uuid'],
                        first_name=rec['first_name'],
                        last_name=rec['last_name'],
                        middle_name=rec['middle_name'],
                        photo=Profile.choose_photo_of(request, rec['photo']),
                        is_active=rec['is_active'],
                        latitude=rec['latitude'],
                        longitude=rec['longitude'],
                        ability=rec['text'],
                        gender=rec['gender'],
                        dob=UnclearDate.str_safe_from_rec(rec, 'dob'),
                        is_dead=rec['is_dead'] or bool(dod),
                        dod=dod,
                        comment=rec['comment'] or '',
                    ))
                    user_pks.append(rec['id'])
                connections = []

                if user_q.pk not in user_pks:
                    user_pks.append(user_q.pk)
                user_a = request.user
                if user_a.is_authenticated and user_a.pk not in user_pks:
                    users.append(user_a.profile.data_dict(request))
                    user_pks.append(user_a.pk)
                q = Q(user_from__in=user_pks) & Q(user_to__in=user_pks)
                q &= Q(user_to__isnull=False) & Q(is_reverse=False) & Q(is_trust__isnull=False)
                for cs in CurrentState.objects.filter(q).select_related(
                    'user_to__profile', 'user_from__profile',
                    ).distinct():
                    connections.append(cs.data_dict(show_trust=True))

                keys = [
                    {
                        'id': key.pk,
                        'type_id': key.type.pk,
                        'value': key.value,
                    } \
                    for key in Key.objects.filter(owner=user_q).select_related('type')
                ]
                for oauth in Oauth.objects.filter(user=user_q, provider=Oauth.PROVIDER_TELEGRAM, username__gt=''):
                    keys.append({
                        'id': None,
                        'type_id': KeyType.LINK_ID,
                        'value': 'https://t.me/%s' % oauth.username,
                    })
                wishes = [
                    {
                        'uuid': wish.uuid,
                        'text': wish.text,
                    } \
                    for wish in Wish.objects.filter(owner=user_q)
                ]
                abilities = [
                    {
                        'uuid': ability.uuid,
                        'text': ability.text,
                    } \
                    for ability in Ability.objects.filter(owner=user_q)
                ]
                data.update(
                    users=users,
                    connections=connections,
                    keys=keys,
                    wishes=wishes,
                    abilities=abilities,
                )
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_404_NOT_FOUND
        return Response(data=data, status=status_code)

api_profile_graph = ApiProfileGraph.as_view()

class ApiGetIncognitoMessages(APIView):

    def post(self, request):
        """
        Постраничное получение списка сообщений

        Вернуть список сообщений пользователя,
        заданного типа, с записи from количеством count.
        Записи должны быть отсортированы по убыванию timestamp
        Запрос:
            {
                "incognito_id":”a20928d3-76f6-4874-8af7-7bacb0fc1853”,
                "message_type_id": 2,
                "from": 0,
                "count": 20
            }
            from нет или null: сначала
            count нет или null: до конца
        Возвращает:
        {
        "user_messages": [
            {"timestamp": 142342342342},
            ...
        }
        """

        try:
            incognito_id = request.data.get("incognito_id")
            message_type_id = request.data.get("message_type_id")
            if not (incognito_id and message_type_id):
                raise ServiceException('Не задан(ы) incognito_id и/или message_type_id')
            from_ = request.data.get("from")
            if not from_:
                from_ = 0
            count = request.data.get("count")
            qs = UserSymptom.objects.filter(
                incognitouser__public_key=incognito_id,
                symptom__pk=message_type_id,
            )
            qs = qs.distinct().order_by('-insert_timestamp')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            data = [ dict(timestamp=s.insert_timestamp,) for s in qs ]
            status_code = status.HTTP_200_OK
            data = dict(user_messages=data)
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_getincognitomessages = ApiGetIncognitoMessages.as_view()

class ApiGetThanksUsersForAnytext(APIView):

    def get(self, request, *args, **kwargs):
        """
        Постраничное получение списка поблагодаривших и поблагодаренных

        Возвратить массив пользователей (их фото и UUID),
        которые благодарили текст.
        Массив пользователей должен быть отсортирован по
        убыванию известности пользователей.
        Нужно получить count записей начиная с записи from.

        Пример вызова:
        /api/getthanksusersforanytext?text=ТЕКСТ,ЛА,ЛА,ЛА...&from=...&count=..
        Возвращает:
        {
        "thanks_users": [
                {
                    "photo": "photo/url",
                    "user_uuid": "6e14d54b-9371-431f-8bf0-6688f2cf2451"
                },
            ...
            ]
        }

        """
        try:
            text = request.GET.get('text')
            if not text:
                raise ServiceException('Не задан текст')
            qs = CurrentState.objects.select_related(
                    'user_from__profile',
                ).filter(
                    anytext__text=text,
                )
            try:
                from_ = request.GET.get("from", 0)
                from_ = int(from_) if from_ else 0
                count = request.GET.get("count", 0)
                count = int(count) if count else 0
            except ValueError:
                raise ServiceException('Неверный from или count')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            thanks_users = []
            for currentstate in qs:
                profile = currentstate.user_from.profile
                thanks_users.append(dict(
                    photo = profile.choose_photo(request),
                    user_uuid=str(profile.uuid)
                ))
            data = dict(
                thanks_users=thanks_users
            )
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_get_thanks_users_for_anytext = ApiGetThanksUsersForAnytext.as_view()

class ApiAddOrUpdateAbility(UuidMixin, APIView):

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Создать либо обновить возможность uuid

        - задан параметр tg_token, совпадающий с токеном бота телеграма:
            - user_uuid, обязательно
            - update_main, true или false, необязательно, править первую возможность, если она имеется
            - uuid: uuid возможности:  если задано, то update_main не учитывается.
                    Если возможности с таким uuid не существует, то создать.
            - text: обязательно, текст возможности
            - last_edit: необязательно, время добавления/правки
        - не задан параметр tg_token. Авторизация обязательна
            - user_uuid, не обязательно, если не задан, то правим или добавляем свою возможность
            - update_main, true или false, необязательно, править первую возможность, если она имеется
            - uuid: uuid возможности:  если задано, то update_main не учитывается.
                    Если возможности с таким uuid не существует, то создать.
            - text: обязательно, текст возможности
            - last_edit: необязательно, время добавления/правки

        Пример исходных данных:
        * Создать возможность (uuid не задан)
            {
                "user_uuid": "....",
                    // у кого создаем возможность.
                    // Если не задан, то у себя

                "text": "Могу, Могу, Могу...",
                "last_edit": 154230840234
            }
        * Обновить или обновить возможность (uuid задан)
            {
                "user_uuid": "....",
                    // у кого создаем возможность.
                    // Если не задан, то у себя
                "uuid": "e17a34d0-c6c4-4755-a67b-7e7d13e4bd4b",
                "text": "Могу, Могу, Могу...",
                "last_edit": 154230840234
            }
        Возвращает: {}
        """
        try:
            text = request.data.get('text', '').strip()
            if not text:
                raise ServiceException('Текст обязателен')
            update_timestamp = request.data.get('last_edit', int(time.time()))
            tg_token = request.data.get('tg_token')
            if tg_token and tg_token != settings.TELEGRAM_BOT_TOKEN:
                raise ServiceException('Неверный токен телеграм бота')
            user_uuid = request.data.get('user_uuid')
            if tg_token and not user_uuid:
                raise ServiceException('Не задан user_uuid')
            if not tg_token and not request.user.is_authenticated:
                raise NotAuthenticated
            if tg_token:
                owner, profile = self.check_user_uuid(user_uuid)
            else:
                owner, profile = self.check_user_or_owned_uuid(request, uuid_field='user_uuid')
            uuid = None
            update_main = request.data.get('update_main')
            if update_main:
                try:
                    uuid = Ability.objects.filter(owner=owner).order_by('insert_timestamp')[0].uuid
                except IndexError:
                    pass
            if not uuid:
                uuid = request.data.get('uuid')
            if uuid:
                do_create = False
                try:
                    ability = Ability.objects.get(uuid=uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Ability.DoesNotExist:
                    do_create = True
                    ability = Ability.objects.create(
                        uuid=uuid,
                        owner=owner,
                        text=text,
                        update_timestamp=update_timestamp,
                    )
                if not do_create:
                    if not tg_token and ability.owner != request.user and ability.owner.profile.owner != request.user:
                        raise ServiceException('Возможность с uuid = %s не принадлежит ни Вам, ни Вашему родственнику' % uuid)
                    ability.text = text
                    ability.update_timestamp = update_timestamp
                    ability.save()
            else:
                do_create = True
                ability = Ability.objects.create(
                    owner=owner,
                    text=text,
                    update_timestamp=update_timestamp,
                )
            if do_create:
                if not profile.ability:
                    profile.ability = ability
                    profile.save(update_fields=('ability',))
            data = ability.data_dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_or_update_ability = ApiAddOrUpdateAbility.as_view()

class ApiGetUserAbilities(UuidMixin, APIView):

    def get(self, request, *args, **kwargs):
        """
        Возвращает список возможностей пользователя

        Пример исходных данных:
        /api/getuserabilities?uuid=172da3fe-dd30-4cb8-8df3-46f69785d30a
        Возвращает:
        {
            "abilities": [
                {
                    "uuid": "e17a34d0-c6c4-4755-a67b-7e7d13e4bd4b",
                    "text": "Хочу, хочу, хочу...",
                    "last_edit": 184230840234
                },
                ...
            ]
        }

        """
        try:
            uuid = request.GET.get('uuid')
            user, profile = self.check_user_uuid(uuid)
            qs = Ability.objects.filter(owner=user).order_by('insert_timestamp')
            try:
                from_ = request.GET.get("from", 0)
                from_ = int(from_) if from_ else 0
                count = request.GET.get("count", 0)
                count = int(count) if count else 0
            except ValueError:
                raise ServiceException('Неверный from или count')
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            data = dict(
                abilities = [ ability.data_dict() for ability in qs ]
            )
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_user_abilities = ApiGetUserAbilities.as_view()

class ApiDeleteAbility(APIView):
    permission_classes = (IsAuthenticated, )

    @transaction.atomic
    def get(self, request, *args, **kwargs,):
        """
        Удалить возможности uuid

        Проверить, принадлежит ли возможность пользователю, пославшему запрос,
        или его родственнику, и если принадлежит, то удалить ее,
        иначе вернуть сообщение об ошибке.
        Пример исходных данных:
        /api/deleteability?uuid=4d02e22c-b6eb-4307-a440-ccafdeedd9b8
        Возвращает: {}
        """
        try:
            uuid = request.GET.get('uuid')
            if uuid:
                try:
                    ability = Ability.objects.get(uuid=uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Ability.DoesNotExist:
                    raise ServiceException('Возможность с uuid = %s не найдена' % uuid)
                profile = ability.owner.profile
                if ability.owner != request.user and profile.owner != request.user:
                    raise ServiceException('Возможность с uuid = %s не принадлежит ни Вам, ни Вашему родственнику' % uuid)
                if profile.ability == ability:
                    profile.ability = None
                    profile.save(update_fields=('ability',))
                ability.delete()
                if not profile.ability:
                    try:
                        profile.ability = profile.user.ability_set.all().order_by('insert_timestamp')[0]
                        profile.save(update_fields=('ability',))
                    except IndexError:
                        pass
            else:
                raise ServiceException('Не задан uuid возможности')
            data = dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_ability = ApiDeleteAbility.as_view()

class ApiInviteUseToken(ApiAddOperationMixin, TelegramApiMixin, FrontendMixin, APIView):
    permission_classes = (IsAuthenticated, )

    @transaction.atomic
    def post(self, request):
        try:
            token = None
            token_s = request.data.get('token')
            if not token_s:
                raise ServiceException('Не задан token')
            try:
                token = TempToken.objects.get(type=TempToken.TYPE_INVITE, token=token_s)
            except TempToken.DoesNotExist:
                raise ServiceException('Не найден token приглашения')
            try:
                user_from = User.objects.get(pk=token.obj_id)
            except User.DoesNotExist:
                raise ServiceException('Пригласивший пользователь уже не существует')
            if token.insert_timestamp + token.ttl < time.time():
                raise ServiceException('Время действия токена истекло')
            profile_to = Profile.objects.select_for_update().select_related('user').get(user=request.user)
            self.add_operation(
                user_from,
                profile_to,
                operationtype_id=OperationType.TRUST_AND_THANK,
                comment=None,
                insert_timestamp=int(time.time()),
            )
            if profile_to.is_notified:
                message = self.profile_link(request, profile_to) + ' принял Вашу благодарность'
                self.send_to_telegram(message, user=user_from)
            token.delete()
            data = dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_invite_use_token = ApiInviteUseToken.as_view()

class GetTrustGenesisMixin(object):
    def get(self, request):
        try:
            chat_id = request.GET.get('chat_id')
            fmt = request.GET.get('fmt', 'd3js')
            try:
                recursion_depth = int(request.GET.get('depth', 0) or 0)
            except (TypeError, ValueError,):
                recursion_depth = 0
            max_recursion_depth = settings.MAX_RECURSION_DEPTH_IN_GROUP if chat_id else settings.MAX_RECURSION_DEPTH
            if recursion_depth <= 0 or recursion_depth > max_recursion_depth:
                recursion_depth = max_recursion_depth

            uuid = request.GET.get('uuid', '').strip(' ,')
            if chat_id:
                data = self.get_chat_mesh(request, chat_id, recursion_depth)
            elif uuid:
                uuids = re.split(r'[, ]+', uuid)
                len_uuids = len(uuids)
                if len_uuids == 1:
                    data = self.get_tree(request, uuids[0], recursion_depth, fmt)
                elif len_uuids == 2:
                    data = self.get_shortest_path(request, uuids, recursion_depth, fmt)
                else:
                    raise ServiceException("Допускается  uuid (дерево) или 2 uuid's (найти путь между)")
            else:
                raise ServiceException('Не заданы параметры uuid или chat_id')
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)


class ApiProfileGenesisAll(TelegramApiMixin, APIView):
    """
    Отдать все профили и все связи

    Возможны форматы выдачи (?fmt= get параметр):
        - d3js
        - 3d-force-graph
    Возможные выборки (get параметры):
        - dover :   показать доверия
        - rod   :   показать родственные связи
        - withalone: показать и тех, у кого нет связей родственных и/или доверия
        * from
        * number    параметры страницы. Выборка пользователей числом number,
                    начиная с from, в порядке убывания дат их присоединения
                    к сообществу.
                    Если заданы from и/или number, по полагается withalone=on

    """
    def get(self, request):
        fmt = request.GET.get('fmt', 'd3js')
        withalone = request.GET.get('withalone')
        dover = request.GET.get('dover')
        rod = request.GET.get('rod')
        from_ = number_ = None
        try:
            from_ = int(request.GET.get('from'))
            if from_ < 0:
                from_ = 0
        except (ValueError, TypeError,):
            pass
        try:
            number_ = int(request.GET.get('number'))
        except (ValueError, TypeError,):
            pass
        if number_ and from_ is None:
            from_ = 0
        if from_ is not None and not number_:
            number_ = settings.PAGINATE_USERS_COUNT
        if number_ and from_ is not None:
            withalone = 'on'

        connections = []
        q_connections = Q(pk=0)
        if rod:
            q_connections = Q(is_child=True)
        if dover:
            q_connections |= Q(is_trust=True, user_to__isnull=False, is_reverse=False)
        if withalone:
            if from_ is None:
                users = [
                    profile.data_dict(request=request, short=True, fmt=fmt) \
                    for profile in Profile.objects.select_related('user').filter(user__is_superuser=False).distinct()
                ]
                if rod or dover:
                    connections = [
                        cs.data_dict(
                            show_child=rod and fmt=='3d-force-graph',
                            show_parent=fmt=='d3js',
                            show_trust=bool(dover),
                            fmt=fmt
                        ) \
                        for cs in CurrentState.objects.filter(q_connections).select_related(
                                'user_from__profile', 'user_to__profile',
                            ).distinct()
                    ]
            else:
                users = []
                connections = []
                user_pks = []
                if rod or dover:
                    for profile in Profile.objects.select_related('user').filter(
                            user__is_superuser=False,
                        ).order_by(
                            '-user__date_joined'
                        ).distinct()[from_: from_ + number_]:
                        users.append(profile.data_dict(request=request, short=True, fmt=fmt))
                        user_pks.append(profile.user.pk)
                    connections = [
                        cs.data_dict(
                            show_child=rod and fmt=='3d-force-graph',
                            show_parent=fmt=='d3js',
                            show_trust=bool(dover),
                            fmt=fmt
                        ) \
                        for cs in CurrentState.objects.filter(q_connections).select_related(
                                'user_from__profile', 'user_to__profile',
                            ).filter(
                                user_from__in=user_pks,
                                user_to__in=user_pks,
                            ).distinct()
                    ]
        else:
            users = []
            if rod or dover:
                users_pks = set()
                for cs in CurrentState.objects.filter(q_connections).select_related(
                            'user_from__profile', 'user_to__profile',).distinct():
                    connections.append(cs.data_dict(
                        show_child=rod and fmt=='3d-force-graph',
                        show_parent=fmt=='d3js',
                        show_trust=bool(dover),
                        fmt=fmt
                    ))
                    if cs.user_from.pk not in users_pks:
                        users_pks.add(cs.user_from.pk)
                        users.append(cs.user_from.profile.data_dict(request=request, short=True, fmt=fmt))
                    if cs.user_to.pk not in users_pks:
                        users_pks.add(cs.user_to.pk)
                        users.append(cs.user_to.profile.data_dict(request=request, short=True, fmt=fmt))

        if fmt == '3d-force-graph':
            bot_username = self.get_bot_username()
            data = dict(bot_username=bot_username, nodes=users, links=connections)
        else:
            data = dict(users=users, connections=connections, trust_connections=[])
        return Response(data=data, status=status.HTTP_200_OK)

api_profile_genesis_all = cache_page(30)(ApiProfileGenesisAll.as_view())


class ApiProfileGenesis(GetTrustGenesisMixin, UuidMixin, SQL_Mixin, TelegramApiMixin, APIView):
    """
    Дерево родни в чате телеграма, или просто среди пользователей.

    Если задан параметр chat_id, то показ родственных связей между участниками
    телеграм группы/канала, возможно опосредованный через иных пользователей

    Если задан параметр uuid
        Если указан один uuid:
            Возвращает информацию о пользователе, а также его родственных связях (дерево рода).

        Если указаны 2 uuid через запятую:
            Возвращает кратчайший путь (пути) между двумя родственниками
    В любом случае возвращаются данные авторизованного пользователя и
    его доверия (недоверия) к пользователям в цепочках связей.

    Параметры
    Если задан параметр uuid:
        uuid:
            uuid пользователя
        depth:
            0 или отсутствие параметра или он неверен:
                показать без ограничения глубины рекурсии
                (в этом случае она таки ограничена, но немыслимо большИм для глубины рекурсии числом: 100)
            1 или более:
                показать в рекурсии связи не дальше указанной глубины рекурсии
        up:
            (если указан один uuid)
            =что-то: true; отсутствует или пусто: false
            показать прямых предков от пользователя с uuid
        down:
            (если указан один uuid)
            =что-то: true; отсутствует или пусто: false
            показать прямых потомков от пользователя с uuid
        Если указан один uuid и отсутствуют или пустые оба параметра up и down,
        будет показана вся сеть родни от пользователя с uuid, включая двоюродных и т.д.

    Если задан параметр chat_id:
        chat_id:
            id телеграм группы или канала
        depth:
            по умолчанию settings.MAX_RECURSION_DEPTH_IN_GROUP и не больше этого числа:
        from:
            откуда начинать страницу показа результатов для участников группы,
            по умолчанию 0
        count:
            сколько показывать участников группы в очередной странице,
            по умолчанию settings.MAX_RECURSION_COUNT_IN_GROUP
    """

    def get_chat_mesh(self, request, chat_id, recursion_depth):
        users = []
        connections = []
        trust_connections = []
        try:
            tggroup = TgGroup.objects.get(chat_id=chat_id)
        except (ValueError, TgGroup.DoesNotExist,):
            raise ServiceException('Группа/канал не существует')
        chat_user_pks = []
        for oauth in Oauth.objects.select_related(
                    'user',
                ).filter(
                    groups__pk=tggroup.pk
                ).order_by(
                    '-user__date_joined',
                ):
            if oauth.user_id not in chat_user_pks:
                # Один юзер может иметь несколь телеграм аккаунтов
                chat_user_pks.append(oauth.user_id)
        if chat_user_pks:
            try:
                from_ = int(request.GET.get('from', 0))
                if from_ <= 0:
                    from_ = 0
                count = int(request.GET.get('count', settings.MAX_RECURSION_COUNT_IN_GROUP))
                if count <= 1 or count > settings.MAX_RECURSION_COUNT_IN_GROUP:
                    count = settings.MAX_RECURSION_COUNT_IN_GROUP
            except (TypeError, ValueError,):
                raise ServiceException('Неверный параметр: from и/или count')
            user_page_pks = chat_user_pks[from_: from_ + count]
            if len(user_page_pks) == 0:
                # return nothing
                pass
            elif len(user_page_pks) == 1:
                # Один пользователь не может иметь связей сам с собой
                users = [
                    p.data_dict(request) for p in Profile.objects.select_related(
                        'user'
                    ).filter(user__pk=user_page_pks[0])
                ]
            else:
                user_page_pks_string = ','.join([str(pk) for pk in user_page_pks])

                # select path from find_group_genesis_tree(array[1167,1162,1089,484,429,426,395,331], 9)
                # where path[array_length(path, 1)] = any(array[1167,1162,1089,484,429,426,395,331])
                # and path[1] != path[array_length(path, 1)]
                #
                sql = (
                    'select path from find_group_genesis_tree('
                        'array[%(user_page_pks_string)s], %(recursion_depth)s'
                    ') '
                    'where '
                        'path[array_length(path, 1)] = any(array[%(user_page_pks_string)s]) '
                        'and path[1] != path[array_length(path, 1)] '
                ) % dict(user_page_pks_string=user_page_pks_string, recursion_depth=recursion_depth)

                user_pks = set(user_page_pks)
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    for rec in cursor.fetchall():
                        path = rec[0]
                        for user_pk in path[1:len(path)-1]:
                            user_pks.add(user_pk)

                q_connections = Q(is_child=True)
                q_connections &= Q(user_to__pk__in=user_pks) & Q(user_from__pk__in=user_pks)
                for cs in CurrentState.objects.filter(q_connections).select_related(
                        'user_from__profile', 'user_to__profile',
                    ).distinct():
                    connections.append(cs.data_dict(show_parent=True))

                if request.user.is_authenticated:
                    user = request.user
                    user_pks.add(int(request.user.pk))

                participants_on_page = 0
                for p in Profile.objects.filter(user__pk__in=user_pks).select_related('user', 'ability'):
                    d = p.data_dict(request)
                    d.update(
                        is_in_page = p.user.pk in user_page_pks,
                        is_in_group = p.user.pk in chat_user_pks,
                    )
                    if d['is_in_page']:
                        participants_on_page += 1
                    users.append(d)

                q_connections = Q(
                    is_reverse=False,
                    user_to__isnull=False,
                    is_trust=True,
                )
                q_connections &= Q(user_to__pk__in=user_pks) & Q(user_from__pk__in=user_pks)
                for cs in CurrentState.objects.filter(q_connections).select_related(
                        'user_from__profile', 'user_to__profile',
                    ).distinct():
                    trust_connections.append(cs.data_dict(show_trust=True))

        return dict(users=users, connections=connections, trust_connections=trust_connections, participants_on_page=participants_on_page)

    def get_shortest_path(self, request, uuids, recursion_depth, fmt='d3js'):
        """
        Кратчайший путь родства от uuids[0] к uuids[1]
        """
        user_pks = []
        try:
            user_pks = [int(profile.user.pk) for profile in Profile.objects.filter(uuid__in=uuids)]
        except ValidationError:
            pass
        if len(user_pks) != 2:
            raise ServiceException('Один или несколько uuid неверны или есть повтор среди заданных uuid')

        # Строка запроса типа:
        # select path from find_genesis_path_shortest(416, 455, 10)
        # where path @> array [416, 455];
        #
        sql = 'select path from find_genesis_path_shortest ' \
              '(%(user_from_id)s, %(user_to_id)s, %(recursion_depth)s) ' \
              'where path @> array [%(user_from_id)s, %(user_to_id)s]' % dict(
            user_from_id=user_pks[0],
            user_to_id=user_pks[1],
            recursion_depth=recursion_depth,
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            paths = [rec[0] for rec in cursor.fetchall()]
        user_pks = set(user_pks)
        for path in paths:
            for user_id in path:
                user_pks.add(user_id)

        connections = []
        q_connections = Q(is_child=True)
        q_connections &= Q(user_to__pk__in=user_pks) & Q(user_from__pk__in=user_pks)
        for cs in CurrentState.objects.filter(q_connections).select_related(
                'user_from__profile', 'user_to__profile',
            ).distinct():
            if fmt == '3d-force-graph':
                connections.append(cs.data_dict(show_child=True, fmt=fmt))
            else:
                connections.append(cs.data_dict(show_parent=True, fmt=fmt))

        users = [
            p.data_dict(request, short=fmt=='3d-force-graph', fmt=fmt) for p in \
            Profile.objects.filter(user__pk__in=user_pks).select_related('user', 'ability')
        ]
        if fmt == '3d-force-graph':
            bot_username = self.get_bot_username()
            return dict(bot_username=bot_username, nodes=users, links=connections)
        else:
            return dict(users=users, connections=connections, trust_connections=[])

    def get_tree(self, request, uuid, recursion_depth, fmt='d3js'):
        """
        Дерево родственных связей от пользователя
        """
        related = ('user', 'owner', 'ability',)
        user_q, profile_q = self.check_user_uuid(uuid, related=related)

        v_up = bool(request.GET.get('up'))
        v_down = bool(request.GET.get('down'))
        v_all = not v_up and not v_down
        v_is_child = 'True' if v_down else 'False'
        sql_req_dict = dict(
                user_id=user_q.pk,
                recursion_depth=recursion_depth,
                v_all='True' if v_all else 'False',
                v_is_child=v_is_child,
        )
        sql_req_str = (

            # Вызов postgresql функции. 
            # Родственные связи, начиная с пользователя user_id
            #  recursion_depth:
            #      максимальное число итераций при проходе по дереву связей
            #  v_all:
            #      показывать ли все связи, то есть проходим и по потомкам,
            #      и по предкам, получаем в т.ч. тетей, двоюродных и т.д.
            #      Если True, то v_is_child роли не играет
            #  v_is_child:
            #      При v_all == False:
            #          v_is_child == True:     проходим только по детям.
            #          v_is_child == False:    проходим только по предкам.

            'select * from find_genesis_tree('
                '%(user_id)s,'
                '%(recursion_depth)s,'
                '%(v_all)s,'
                '%(v_is_child)s'
            ')'
        )

        recs = []
        with connection.cursor() as cursor:
            cursor.execute(sql_req_str % sql_req_dict)
            recs += self.dictfetchall(cursor)

        if not v_all and v_up and v_down:
            # v_is_child сейчас 'True'. Потомков нашли. Ищем предков
            sql_req_dict.update(v_is_child='False',)
            with connection.cursor() as cursor:
                cursor.execute(sql_req_str % sql_req_dict)
                recs += self.dictfetchall(cursor)

        connections = []
        user_pks = set()
        pairs = []
        for rec in recs:
            user_pks.add(rec['user_from_id'])
            user_pks.add(rec['user_to_id'])

        user_pks.add(user_q.pk)
        users = []
        for p in Profile.objects.filter(user__pk__in=user_pks).select_related('user', 'ability'):
            if p == profile_q and fmt=='3d-force-graph':
                users.append(dict(
                    id=user_q.pk,
                    uuid=profile_q.uuid,
                    first_name=user_q.first_name,
                    photo=Profile.image_thumb(
                        request, profile_q.photo,
                        method='crop-green-frame-3',
                        put_default_avatar=True,
                )))
            else:
                users.append(p.data_dict(request, short=fmt=='3d-force-graph', fmt=fmt))

        connections = []
        q_connections = Q(is_child=True)
        q_connections &= Q(user_to__pk__in=user_pks) & Q(user_from__pk__in=user_pks)
        for cs in CurrentState.objects.filter(q_connections).select_related(
                'user_from__profile', 'user_to__profile',
            ).distinct():
            if fmt == '3d-force-graph':
                connections.append(cs.data_dict(show_child=True, fmt=fmt))
            else:
                connections.append(cs.data_dict(show_parent=True, fmt=fmt))

        if fmt == '3d-force-graph':
            bot_username = self.get_bot_username()
            return dict(bot_username=bot_username, nodes=users, links=connections, user_q_name=user_q.first_name)
        else:
            return dict(users=users, connections=connections, trust_connections=[])

api_profile_genesis = ApiProfileGenesis.as_view()

class ApiProfileTrust(GetTrustGenesisMixin, UuidMixin, SQL_Mixin, TelegramApiMixin, APIView):
    """
    Дерево доверия пользователя или путь доверий между пользователями

    Если задан параметр chat_id, то показ связей доверия между участниками
    телеграм группы/канала, возможно опосредованный через иных пользователей
    ПОКА НЕ РЕАЛИЗОВАНО, точнее не востребовано

    Если задан параметр uuid
        если задан 1 uuid, или кратчайший путь (пути) по доверию между 2 пользователями

        Если указан один uuid:
            Возвращает информацию о пользователе, а также его довериям в дереве доверий

        Если указаны 2 uuid через запятую:
            Возвращает кратчайший путь (пути) доверия между двумя пользователями
            При этом анализ параметра fmt, или для показа в 3djs фронте,
            или для показа в 3d-force-graph фронте

    Параметры
    Если задан параметр uuid:
        uuid:
            uuid пользователя
        depth:
            0 или отсутствие параметра или он неверен:
                показать без ограничения глубины рекурсии
                (в этом случае она таки ограничена, но немыслимо большИм для глубины рекурсии числом: 100)
            1 или более:
                показать в рекурсии связи не дальше указанной глубины рекурсии
    """

    def get_chat_mesh(self, request, chat_id, recursion_depth):
        raise ServiceException('Не реализовано, ибо не востребовано')
        #return dict(users=[], connections=[], trust_connections=[])

    def get_shortest_path(self, request, uuids, recursion_depth, fmt='d3js'):
        """
        Кратчайший путь доверий между двумя пользователями

        Реализована для двух форматов на фронте
        """
        try:
            user_from_id = Profile.objects.get(uuid=uuids[0]).user_id
            user_to_id = Profile.objects.get(uuid=uuids[1]).user_id
        except (ValidationError, Profile.DoesNotExist, IndexError,):
            raise ServiceException('Один или несколько uuid неверны или не существуют')
        if user_from_id == user_to_id:
            raise ServiceException('Есть повтор среди заданных uuid')

        # Строка запроса типа:
        # select path from find_trust_path_shortest(416, 455, 10)
        # where path @> array [416, 455];
        #
        sql = 'select path from find_trust_path_shortest ' \
              '(%(user_from_id)s, %(user_to_id)s, %(recursion_depth)s) ' \
              'where path @> array [%(user_from_id)s, %(user_to_id)s]' % dict(
            user_from_id=user_from_id,
            user_to_id=user_to_id,
            recursion_depth=recursion_depth,
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            paths = [rec[0] for rec in cursor.fetchall()]
        user_pks = set()
        for path in paths:
            for user_id in path:
                user_pks.add(user_id)

        connections = []
        q_connections = Q(
            is_trust=True,
            is_reverse=False,
            user_to__isnull=False,
            user_to__pk__in=user_pks,
            user_from__pk__in=user_pks,
        )
        for cs in CurrentState.objects.filter(q_connections).select_related(
                'user_from__profile', 'user_to__profile',
            ).distinct():
            d = cs.data_dict(show_trust=True, fmt=fmt)
            if fmt == 'd3js':
                d.update(
                    # Это ради фронта, который заточен для обработки родственных
                    # деревьев
                    is_father=True,
                )
            connections.append(d)

        user_pks.add(user_from_id)
        user_pks.add(user_to_id)
        users = []
        for profile in Profile.objects.filter(user__pk__in=user_pks).select_related('user', 'ability'):
            users.append(profile.data_dict(request, short=fmt=='3d-force-graph', fmt=fmt))

        if fmt == '3d-force-graph':
            bot_username = self.get_bot_username()
            return dict(bot_username=bot_username, nodes=users, links=connections)
        else:
            return dict(users=users, connections=connections, trust_connections=[])

    def get_tree(self, request, uuid, recursion_depth, fmt='d3js'):
        """
        Дерево доверий

        Пока нигде не используется на фронте
        """

        user_q, profile_q = self.check_user_uuid(uuid, related=[])

        sql_req_dict = dict(
                user_id=user_q.pk,
                recursion_depth=recursion_depth,
        )
        recs = []
        with connection.cursor() as cursor:
            cursor.execute(
                'select * from find_trust_tree(%(user_id)s,%(recursion_depth)s)' % dict(
                    user_id=user_q.pk,
                    recursion_depth=recursion_depth,
            ))
            recs += self.dictfetchall(cursor)
        connections = []
        user_pks = set()
        pairs = set()
        for rec in recs:
            user_pks.add(rec['user_from_id'])
            user_pks.add(rec['user_to_id'])
            pairs.add('%s/%s' % (rec['user_from_id'], rec['user_to_id']))

        for cs in CurrentState.objects.filter(
                user_from__in=user_pks,
                user_to__in=user_pks,
                is_trust=True,
                is_reverse=False,
            ).select_related(
                'user_from', 'user_from__profile', 'user_from__profile__ability',
                'user_to', 'user_to__profile', 'user_to__profile__ability',
            ).distinct():
            # Здесь дерево.
            # Отбросим связи МЕЖДУ узлами 2-го и последующих уровней,
            # которые (связи) получились между разными лучами в итерациях
            # процедуры find_trust_tree
            pair = '%s/%s' % (cs.user_from_id, cs.user_to_id)
            pair_reverse = '%s/%s' % (cs.user_to_id, cs.user_from_id)
            if pair in pairs or pair_reverse in pairs:
                d = cs.data_dict(show_trust=True)
                d.update(
                    # Это ради фронта, который заточен для обработки родственных
                    # деревьев
                    is_father=True,
                )
                connections.append(d)

        users = []
        user_pks.add(user_q.pk)
        for profile in Profile.objects.filter(user__pk__in=user_pks).select_related('user', 'ability'):
            users.append(profile.data_dict(request))

        return dict(users=users, connections=connections, trust_connections=[])

api_profile_trust = ApiProfileTrust.as_view()

class ApiTgMessage(UuidMixin, APIView):

    MESSAGE_COUNT = 10

    def get(self, request):
        """
        Получить self.MESSAGE_COUNT последниех сообщений к uuid
        """
        try:
            user_to, p = self.check_user_uuid(request.GET.get('uuid'), related=[], comment='uuid: ')
            data = [
                tm.data_dict() for tm in TgMessageJournal.objects.filter(
                    user_to__pk=user_to.pk,
                    ).select_related(
                        'user_from', 'user_to', 'user_to_delivered',
                        'user_from__profile', 'user_to__profile', 'user_to_delivered__profile',
                        'operationtype',
                    ).order_by('-insert_timestamp')[:self.MESSAGE_COUNT]
            ]

            data += [
                tm.data_dict() for tm in TgJournal.objects.filter(
                    journal__user_to__pk=user_to.pk,
                    ).select_related(
                        'journal__user_from', 'journal__user_to',
                        'journal__user_from__profile', 'journal__user_to__profile',
                        'journal__operationtype',
                    ).distinct(
                        'journal__insert_timestamp',
                        'message_id', 'from_chat_id',
                    ).order_by(
                        '-journal__insert_timestamp',
                        'message_id', 'from_chat_id',
                    )[:self.MESSAGE_COUNT]
            ]

            data = sorted(data, key=lambda item: item['timestamp'], reverse=True)[:self.MESSAGE_COUNT]
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

    def post(self, request):
        """
        Записать в журнал данные об отправленном пользователем телеграма сообщения другому пользователю
        """
        try:
            data = request.data
            if data.get('tg_token'):
                if data.get('tg_token') != settings.TELEGRAM_BOT_TOKEN:
                    raise ServiceException('Неверный токен телеграм бота')
            else:
                raise NotAuthenticated
            user_from, p = self.check_user_uuid(data.get('user_from_uuid'), related=[], comment='user_from_uuid: ')
            user_to, p = self.check_user_uuid(data.get('user_to_uuid'), related=[], comment='user_to_uuid: ')
            if data.get('user_to_delivered_uuid'):
                user_to_delivered, p = self.check_user_uuid(data.get('user_to_delivered_uuid'), related=[], comment='user_to_delivered_uuid: ')
            else:
                user_to_delivered = None
            try:
                from_chat_id = int(data.get('from_chat_id'))
            except (TypeError, ValueError,):
                raise ServiceException('Не задан или не число: from_chat_id')
            try:
                message_id = int(data.get('message_id'))
            except (TypeError, ValueError,):
                raise ServiceException('Не задан или не число: message_id')
            operationtype = None
            if data.get('operation_type_id'):
                try:
                    operationtype = OperationType.objects.get(pk = int(data['operation_type_id']))
                except (OperationType.DoesNotExist, ValueError, TypeError,):
                    pass
            TgMessageJournal.objects.create(
                from_chat_id=from_chat_id,
                message_id=message_id,
                user_from=user_from,
                user_to=user_to,
                user_to_delivered=user_to_delivered,
                operationtype=operationtype,
            )
            status_code = status.HTTP_200_OK
            data = {}
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_tg_message = ApiTgMessage.as_view()
