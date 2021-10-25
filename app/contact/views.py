import os, datetime, time, json, re
import urllib.request, urllib.error
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.db import transaction, IntegrityError, connection
from django.db.models import F, Sum
from django.db.models.query_utils import Q
from django.views.generic.base import View
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

from app.utils import ServiceException, FrontendMixin, SQL_Mixin, get_moon_day
from app.models import UnclearDate

from contact.models import KeyType, Key, \
                           Symptom, UserSymptom, SymptomChecksumManage, \
                           Journal, CurrentState, OperationType, Wish, \
                           AnyText, Ability
from users.models import CreateUserMixin, IncognitoUser, Profile, TempToken, Oauth, UuidMixin

MSG_NO_PARM = 'Не задан или не верен какой-то из параметров в связке номер %s (начиная с 0)'

class SendMessageMixin(FrontendMixin):

    def profile_link(self, profile):
        url_profile = self.get_frontend_url('profile') + '?id=%s' % profile.uuid
        full_name = profile.full_name(last_name_first=False) or 'Без имени'
        link = '<a href="%(url_profile)s">%(full_name)s</a>' % dict(
            url_profile=url_profile,
            full_name=full_name,
        )
        return link

    def send_to_telegram(self, message, user=None, telegram_uid=None):
        """
        Сообщение в телеграм или пользователю user, или по telegram uid
        """
        uid = None
        if user:
            try:
                uid = Oauth.objects.filter(user=user, provider=Oauth.PROVIDER_TELEGRAM)[0].uid
            except IndexError:
                # У пользователя нет аккаунта в телеграме
                pass
        elif telegram_uid:
            uid = telegram_uid

        if uid:
            url = 'https://api.telegram.org/bot%s/sendMessage?' % settings.TELEGRAM_BOT_TOKEN
            parms = dict(
                chat_id=uid,
                parse_mode='html',
                text=message
            )
            url += urlencode(parms)
            try:
                req = urllib.request.Request(url)
                urllib.request.urlopen(req, timeout=20)
            except (urllib.error.URLError, ):
                pass

class ApiAddOperationMixin(object):

    def add_operation(self,
        user_from,
        profile_to,
        operationtype_id,
        comment,
        insert_timestamp,
    ):
        try:
            operationtype = OperationType.objects.get(pk=operationtype_id)
        except (ValueError, OperationType.DoesNotExist,):
            raise ServiceException('Неизвестный operation_type_id = %s' % operationtype_id)

        data = dict()
        update_timestamp = int(time.time())
        user_to = profile_to.user

        if operationtype_id == OperationType.THANK:
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    thanks_count=1,
            ))
            if not created_:
                currentstate.update_timestamp = update_timestamp
                if currentstate.is_reverse:
                    # то же что created
                    currentstate.insert_timestamp = insert_timestamp
                    currentstate.is_reverse = False
                    currentstate.thanks_count = 1
                    currentstate.is_trust = None
                else:
                    currentstate.thanks_count += 1
                currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    is_trust=currentstate.is_trust,
                    thanks_count=currentstate.thanks_count,
            ))
            if not reverse_created and reverse_cs.is_reverse:
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.thanks_count = currentstate.thanks_count
                reverse_cs.save()

            profile_to.sum_thanks_count += 1
            profile_to.save()

        elif operationtype_id == OperationType.MISTRUST:
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    is_trust=False,
            ))
            if not created_:
                currentstate.update_timestamp = update_timestamp
                if currentstate.is_reverse:
                    # то же что created
                    currentstate.insert_timestamp = insert_timestamp
                    currentstate.is_reverse = False
                    currentstate.is_trust = False
                    currentstate.thanks_count = 0
                    currentstate.save()
                else:
                    if currentstate.is_trust == False:
                        raise ServiceException('Вы уже не доверяете пользователю')
                    else:
                        # True or None
                        currentstate.is_trust = False
                        currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    is_trust=False,
                    thanks_count=currentstate.thanks_count,
            ))
            if not reverse_created and reverse_cs.is_reverse and not (reverse_cs.is_trust == False):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_trust = False
                reverse_cs.save()

            profile_to.recount_trust_fame()

        elif operationtype_id == OperationType.TRUST:
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    is_trust=True,
            ))
            if not created_:
                currentstate.update_timestamp = update_timestamp
                if currentstate.is_reverse:
                    # то же что created
                    currentstate.insert_timestamp = insert_timestamp
                    currentstate.is_reverse = False
                    currentstate.is_trust = True
                    currentstate.thanks_count = 0
                    currentstate.save()
                else:
                    if currentstate.is_trust == True:
                        raise ServiceException('Вы уже доверяете пользователю')
                    else:
                        # False or None
                        currentstate.is_trust = True
                        currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    is_trust=True,
                    thanks_count=currentstate.thanks_count,
            ))
            if not reverse_created and reverse_cs.is_reverse and not (reverse_cs.is_trust == True):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_trust = True
                reverse_cs.save()

            profile_to.recount_trust_fame()

        elif operationtype_id == OperationType.TRUST_AND_THANK:
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    is_trust=True,
                    thanks_count=1,
            ))
            if not created_:
                currentstate.update_timestamp = update_timestamp
                if currentstate.is_reverse:
                    # то же что created
                    currentstate.insert_timestamp = insert_timestamp
                    currentstate.is_reverse = False
                    currentstate.is_trust = True
                    currentstate.thanks_count = 1
                    currentstate.save()
                else:
                    currentstate.is_trust = True
                    currentstate.thanks_count += 1
                    currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    is_trust=True,
                    thanks_count=currentstate.thanks_count,
            ))
            if not reverse_created and reverse_cs.is_reverse:
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_trust = True
                reverse_cs.thanks_count = currentstate.thanks_count
                reverse_cs.save()

            profile_to.sum_thanks_count += 1
            profile_to.save()
            profile_to.recount_trust_fame()

        elif operationtype_id == OperationType.NULLIFY_TRUST:
            err_message = 'У вас не было ни доверия, ни недоверия к пользователю'
            try:
                currentstate = CurrentState.objects.select_for_update().get(
                    user_from=user_from,
                    user_to=user_to,
                )
            except CurrentState.DoesNotExist:
                raise ServiceException(err_message)

            if currentstate.is_reverse:
                # то же что created
                raise ServiceException(err_message)
            else:
                if currentstate.is_trust == None:
                    raise ServiceException(err_message)
                else:
                    # False or True
                    currentstate.update_timestamp = update_timestamp
                    currentstate.is_trust = None
                    currentstate.save()

            CurrentState.objects.filter(
                user_to=user_from,
                user_from=user_to,
                is_reverse=True,
                is_trust__isnull=False,
            ).update(is_trust=None, update_timestamp=update_timestamp)

            profile_to.recount_trust_fame()

        elif operationtype_id == OperationType.PARENT:
            try:
                CurrentState.objects.get(
                    user_from=user_to,
                    user_to=user_from,
                    is_parent=True,
                )
                raise ServiceException('Два человека не могут быть оба родителями по отношению друг к другу')
            except CurrentState.DoesNotExist:
                pass

            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    is_parent=True,
                    is_child=False,
            ))
            if not created_:
                if currentstate.is_parent == True:
                    raise ServiceException('Такой родитель уже задан')
                else:
                    currentstate.is_parent = True
                    currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    is_child=True,
                    is_parent=False,
                    thanks_count=currentstate.thanks_count,
                    is_trust=currentstate.is_trust,
            ))
            if not reverse_created:
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_child = True
                reverse_cs.is_parent = False
                reverse_cs.save()

        elif operationtype_id == OperationType.NOT_PARENT:
            try:
                currentstate = CurrentState.objects.select_for_update().get(
                    user_from=user_from,
                    user_to=user_to,
                    is_parent=True
                )
            except CurrentState.DoesNotExist:
                raise ServiceException('Вы и так не связаны отношением потомок - родитель')

            currentstate.update_timestamp = update_timestamp
            currentstate.is_parent = False
            currentstate.is_child = False
            currentstate.save()

            CurrentState.objects.filter(
                user_to=user_from,
                user_from=user_to,
            ).update(is_parent=False, is_child=False, update_timestamp=update_timestamp)

        else:
            raise ServiceException('Неизвестный operation_type_id')

        Journal.objects.create(
            user_from=user_from,
            user_to=user_to,
            operationtype=operationtype,
            insert_timestamp=insert_timestamp,
            comment=comment,
        )

        return data

class ApiAddOperationView(ApiAddOperationMixin, SendMessageMixin, APIView):
    permission_classes = (IsAuthenticated, )
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    @transaction.atomic
    def post(self, request):
        """
        Добавление операции

        - если user_id_from == user_id_to, то вернуть ошибку (нельзя добавить операцию себе);
        - иначе:
            - если тип операции THANK:
                - записать данные в таблицу tbl_journal;
                - инкрементировать значение столбца sum_thanks_count для пользователя user_id_to;
                - если не существует записи в tbl_current_state для заданных user_id_from и user_id_to, то создать ее;
                - инкрементировать значение столбца thanks_count в таблице tbl_current_state для user_id_from и user_id_to;
            - если тип операции MISTRUST:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to;
                    - если значение IS_TRUST == FALSE, вернуть ошибку (нельзя утратить доверие, если его и так нет);
                - иначе:
                    - создать запись в таблице tbl_current_state;
                - записать данные в таблицу tbl_journal;
                - если текущее IS_TRUST == NULL, то инкрементировать FAME и MISTRUST_COUNT для пользователя user_id_to;
                - если текущее IS_TRUST == TRUE, то
                  декрементировать TRUST_COUNT и инкрементировать FAME и MISTRUST_COUNT для пользователя user_id_to;
                - в таблице tbl_current_state установить IS_TRUST = FALSE;
            - если тип операции TRUST:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to;
                    - если значение IS_TRUST == TRUE, вернуть ошибку (нельзя установить доверие, если уже доверяешь);
                - иначе:
                    - создать запись в таблице tbl_current_state;
                - записать данные в таблицу tbl_journal;
                - если текущее IS_TRUST == NULL, то инкрементировать FAME и TRUST_COUNT для пользователя user_id_to;
                - если текущее IS_TRUST == FALSE, то
                  декрементировать MISTRUST_COUNT и инкрементировать FAME и TRUST_COUNT для пользователя user_id_to;
                - в таблице tbl_current_state установить IS_TRUST = TRUE;
            - если тип операции NULLIFY_TRUST:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to;
                    - если значение IS_TRUST == NULL, вернуть ошибку (нельзя обнулить доверие, если оно пустое);
                    - иначе:
                        - если текущее IS_TRUST == TRUE, то декрементировать TRUST_COUNT;
                        - если текущее IS_TRUST == FALSE, то декрементировать MISTRUST_COUNT;
                        - декрементировать FAME для user_id_to;
                        - установить IS_TRUST = NULL;
                        - записать данные в таблицу tbl_journal;
                - иначе вернуть ошибку (нельзя обнулить доверие, если связи нет);

            - По операциям Parent, noParent NB::
            !!! может быть задан еще и user_from_id,
            !!! из user_from, user_to хотя бы один должен быть
                или авторизованным пользователем или его родственником

            - если тип операции Parent:
                - проверить, есть ли запись с user_from == user_to и
                  user_to == user_from и is_parent == True. Если есть, то ошибка:
                  в одной паре людей не могут быть первй родителем второго одновременно
                  с тем, что второй - родитель первого
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to:
                    - если текущее значение is_parent == True, вернуть ошибку,
                      нельзя несколько раз подряд становиться родителем
                    - если текущее значение is_parent == False, установить is_parent == True,
                - иначе создать запись в таблице tbl_current_state
                  для заданных user_id_from и user_id_to c is_parent == True
                - если нет ошибок, то записать данные в таблицу tbl_journal

            - если тип операции not Parent:
                - если есть запись в таблице tbl_current_state для заданных user_id_from и user_id_to:
                    - если текущее значение is_parent == False,
                      вернуть ошибку, нельзя не становиться  родителем, если и раньше им не был
                    - если текущее значение is_parent == True, установить is_parent == False
                - иначе вернуть ошибку, не был родителем, нечего еще раз говорить, что не родитель
                - если нет ошибок, то записать данные в таблицу tbl_journal

        Пример исходных данных:
        {
            "user_id_to": "825b031e-95a2-4fdd-a70b-b446a52c4498",
            "operation_type_id": 1,
            "timestamp": 1593527855
        }
        """

        try:
            user_from = request.user
            profile_from = user_from.profile
            user_from_uuid = profile_from.uuid

            user_to_uuid = request.data.get("user_id_to")
            if not user_to_uuid:
                raise ServiceException('Не задан user_id_to')

            try:
                operationtype_id = int(request.data.get("operation_type_id"))
            except (TypeError, ValueError):
                raise ServiceException('Не задан или неверный operation_type_id')

            comment = request.data.get("comment", None)
            insert_timestamp = request.data.get('timestamp', int(time.time()))

            try:
                profile_to = Profile.objects.select_for_update().select_related('user').get(uuid=user_to_uuid)
                user_to = profile_to.user
            except ValidationError:
                raise ServiceException('Неверный user_id_to = "%s"' % user_to_uuid)
            except Profile.DoesNotExist:
                raise ServiceException('Не найден пользователь, user_id_to = "%s"' % user_to_uuid)
            if operationtype_id in (OperationType.PARENT, OperationType.NOT_PARENT,):
                user_from_uuid = request.data.get("user_id_from")
                if user_from_uuid:
                    try:
                        profile_from = Profile.objects.select_for_update().select_related('user').get(uuid=user_from_uuid)
                        user_from = profile_from.user
                    except ValidationError:
                        raise ServiceException('Неверный user_id_from = "%s"' % user_from_uuid)
                    except Profile.DoesNotExist:
                        raise ServiceException('Не найден пользователь, user_id_from = "%s"' % user_from_uuid)
            if user_to == user_from:
                raise ServiceException('Операция на самого себя не предусмотрена')
            if operationtype_id in (OperationType.PARENT, OperationType.NOT_PARENT,):
                if not (
                    user_from == request.user or profile_from.owner == request.user
                   ):
                        raise ServiceException('У Вас нет прав задавать такого родителя')

            data = self.add_operation(
                user_from,
                profile_to,
                operationtype_id,
                comment,
                insert_timestamp,
            )

            if user_to.profile.is_notified:
                message = None
                if operationtype_id in (OperationType.THANK, OperationType.TRUST_AND_THANK, ):
                    message = 'Получена благодарность от '
                    message += self.profile_link(user_from.profile)
                elif operationtype_id == OperationType.MISTRUST:
                    message = 'Получена утрата доверия от '
                    message += self.profile_link(user_from.profile)
                elif operationtype_id == OperationType.TRUST:
                    message = 'Получено доверие от '
                    message += self.profile_link(user_from.profile)
                elif operationtype_id == OperationType.NULLIFY_TRUST:
                    message = 'Доверие от ' + self.profile_link(user_from.profile) + ' обнулено'
                if message:
                    self.send_to_telegram(message, user=user_to)

            status_code = status.HTTP_200_OK

        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
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
                    uuid, photo, photo_url
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
                        photo = Profile.choose_photo_of(request, rec['photo'], rec['photo_url']),
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

class ApiGetStats(SQL_Mixin, APIView):

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

        if kwargs.get('only') == 'user_connections':

            # Вернуть:
            #
            # {
            #   "users": [...],     # список пользователей с профилями (и uuid)
            #   "connections": [
            #       [3, 4],         # user_id=3 сделал thank user_id=4 или наоборот
            #       [5, 6],
            #       ...
            #   [
            # }

            users = dict()
            for user in User.objects.filter(is_superuser=False):
                initials = ''
                first_name = user.first_name.strip()
                if first_name:
                    initials += first_name[0]
                last_name = user.last_name.strip()
                if last_name:
                    initials += last_name[0]
                users[user.pk] = dict(initials=initials)
            connections = []
            for cs in CurrentState.objects.filter(
                        user_to__isnull=False,
                        thanks_count__gt=0,
                        is_reverse=False,
                    ).select_related('user_from', 'user_to'):
                connection_fvd = [cs.user_from.pk, cs.user_to.pk]
                connection_rev = [cs.user_to.pk, cs.user_from.pk]
                if not (connection_fvd in connections or connection_rev in connections):
                    connections.append(connection_fvd)

            return dict(users=users, connections=connections)

        if kwargs.get('only') == 'user_connections_graph':

            # Возвращает:
            #  список пользователей, которые выполнили логин в систему
            #  (т.е. все, кроме родственников)
            #
            #   без параметров:
            #       список тех пользователей, и связи,
            #       где не обнулено доверие (currenstate.is_trust is not null).
            #   с параметром query:
            #       у которых в
            #               имени или
            #               фамилии или
            #               возможностях или
            #               ключах или
            #               желаниях
            #       есть query, и их связи,
            #       где не обнулено доверие (currenstate.is_trust is not null).
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

            q_users = Q(is_superuser=False, profile__owner__isnull=True)
            query = request.GET.get('query')
            if query:
                q_users &= \
                    Q(last_name__icontains=query) | \
                    Q(first_name__icontains=query) | \
                    Q(profile__middle_name__icontains=query) | \
                    Q(wish__text__icontains=query) | \
                    Q(ability__text__icontains=query) | \
                    Q(key__value__icontains=query)
            users_selected = User.objects.filter(q_users).distinct()

            count = request.GET.get('count')
            if count:
                return dict(count=users_selected.count())

            users_selected = users_selected.select_related('profile', 'profile__ability')
            users = []
            user_pks = []
            try:
                from_ = abs(int(request.GET.get("from")))
            except (ValueError, TypeError, ):
                from_ = 0
            try:
                number_ = abs(int(request.GET.get("number")))
            except (ValueError, TypeError, ):
                number_ = settings.PAGINATE_USERS_COUNT

            users_selected = users_selected.order_by('-date_joined')[from_:from_ + number_]
            for user in users_selected:
                profile = user.profile
                users.append(profile.data_dict(request))
                user_pks.append(user.pk)

            if request.user and request.user.is_authenticated:
                if request.user.pk not in user_pks:
                    user= request.user
                    profile = user.profile
                    users.append(profile.data_dict(request))
                    user_pks.append(user.pk)

            connections = []
            q_connections = Q(
                is_reverse=False,
                is_trust__isnull=False,
                user_to__isnull=False,
            )
            q_connections &= Q(user_to__pk__in=user_pks) & Q(user_from__pk__in=user_pks)
            for cs in CurrentState.objects.filter(q_connections).select_related(
                    'user_from__profile', 'user_to__profile',
                ).distinct():
                connections.append({
                    'source': cs.user_from.profile.uuid,
                    'target': cs.user_to.profile.uuid,
                    'thanks_count': cs.thanks_count,
                    'is_trust': cs.is_trust,
                })

            return dict(users=users, connections=connections)

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

    # TODO
    # Удалить обработку incognito_id, когда пользователи обновят свои апк

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Добавление симптома пользователя (новая версия)

        Вставить переданные user_symptoms.
        Для этого метода есть url с обязательной авторизацией и без нее.
        Пример исходных данных:
        {
            "incognito_id": "2b0cdb0a-544d-406a-b832-6821c63f5d45"
            // Это временно
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
    permission_classes = (IsAuthenticated, )

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Создать либо обновить желание

        Если желание с заданным uuid существует,
        то проверить принадлежит ли оно пользователю,
        пославшему запрос, или его родственнику,
        и если принадлежит, то обновить его.
        Если же не принадлежит, то вернуть сообщение об ошибке.
        Если желания с таким uuid не существует, то создать.
        Может быть параметр user_uuid, чье желание изменять/добавлять.
        Если параметр user_uuid отсутствует, желание добавляется или
        изменяется у авторизованного пользователя

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
            text = request.data.get('text')
            if not text:
                raise ServiceException('Желание без текста')
            update_timestamp = request.data.get('last_edit', int(time.time()))
            uuid = request.data.get('uuid')
            owner, profile = self.check_user_or_owned_uuid(request, uuid_field='user_uuid')
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
                    if wish.owner == request.user or wish.owner.profile.owner == request.user:
                        wish.text = text
                        wish.update_timestamp = update_timestamp
                        wish.save()
                    else:
                        raise ServiceException('Желание с uuid = %s не принадлежит ни Вам, ни Вашему родственнику' % uuid)
            else:
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
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        """
        Добавление ключа

        Добавить ключ в таблицу Key, свой ключ или родственника.
        Если такой ключ уже существует (пара значение-тип ключа),
        то вернуть ошибку.

        Пример исходных данных:
        {
            "user_uuid": “....” :
            // свой или родственника. Если отсутствует user_uuid, значит свой ключ
            "value": "56648",
            "type_id": 1
        }
        """
        try:
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
                raise ServiceException('Такой ключ уже существует')
            data = key.data_dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
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

class ApiProfileGraph(UuidMixin, SQL_Mixin, APIView):

    def get(self, request, *args, **kwargs):
        """
        Возвращает связи пользователя, его желания и ключи

        Параметры:
        uuid
            Опрашиваемый пользователь
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
            uuid = request.GET.get('uuid')
            user_q, profile_q = self.check_user_uuid(uuid)
            status_code = status.HTTP_200_OK

            query = request.GET.get('query', '')

            req_union = """
                SELECT
                    DISTINCT user_to_id as id
                FROM
                    contact_currentstate
                WHERE
                    is_reverse = false AND
                    is_trust IS NOT NULL AND
                    user_to_id IS NOT NULL AND
                    user_from_id = %(user_q_pk)s
                UNION
                SELECT
                    DISTINCT user_from_id as id
                FROM
                    contact_currentstate
                WHERE
                    is_reverse = false AND
                    is_trust IS NOT NULL AND
                    user_to_id = %(user_q_pk)s
            """ % dict(
                user_q_pk=user_q.pk
            )

            sql_joins = """
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
            if query:
                # '%QUERY%' :
                like_value = "'%" + self.sql_like_value(query.upper()) + "%'"
                query_where = """
                    UPPER(auth_user.last_name) LIKE %(like_value)s OR
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
                        %(sql_joins)s
                        WHERE
                            auth_user.id IN (%(req_union)s) AND
                            (%(query_where)s)
                    """ % dict(
                        sql_joins=sql_joins,
                        query_where=query_where,
                        req_union=req_union,
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
                from_ = abs(int(request.GET.get("from")))
            except (ValueError, TypeError, ):
                from_ = 0
            try:
                number_ = abs(int(request.GET.get("number")))
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
                    users_profile.photo_url,

                    users_profile.dob,
                    users_profile.dob_no_day,
                    users_profile.dob_no_month,

                    users_profile.dod,
                    users_profile.dod_no_day,
                    users_profile.dod_no_month,

                    profile__ability.text
                FROM
                    auth_user
                %(sql_joins)s
                WHERE 
                    auth_user.id IN (%(req_union)s)
            """ % dict(
                sql_joins=sql_joins,
                req_union=req_union,
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
                users.append(dict(
                    uuid=rec['uuid'],
                    first_name=rec['first_name'],
                    last_name=rec['last_name'],
                    middle_name=rec['middle_name'],
                    photo=Profile.choose_photo_of(request, rec['photo'], rec['photo_url']),
                    is_active=rec['is_active'],
                    latitude=rec['latitude'],
                    longitude=rec['longitude'],
                    ability=rec['text'],
                    gender=rec['gender'],
                    dob=UnclearDate.str_safe_from_rec(rec, 'dob'),
                    dod=UnclearDate.str_safe_from_rec(rec, 'dod'),
                ))
                user_pks.append(rec['id'])
            connections = []

            user_pks.append(user_q.pk)
            q = Q(user_from__in=user_pks) & Q(user_to__in=user_pks)
            q &= Q(user_to__isnull=False) & Q(is_reverse=False) & Q(is_trust__isnull=False)
            for cs in CurrentState.objects.filter(q).select_related(
                'user_to__profile', 'user_from__profile',
                ).distinct():
                connections.append({
                    'source': cs.user_from.profile.uuid,
                    'target': cs.user_to.profile.uuid,
                    'thanks_count': cs.thanks_count,
                    'is_trust': cs.is_trust,
                    'is_parent': cs.is_parent,
                })

            keys = [
                {
                    'id': key.pk,
                    'type_id': key.type.pk,
                    'value': key.value,
                } \
                for key in Key.objects.filter(owner=user_q).select_related('type')
            ]
            try:
                tg_username = Oauth.objects.filter(
                    user=user_q, provider=Oauth.PROVIDER_TELEGRAM,
                )[0].username
            except IndexError:
                tg_username = ''
            if tg_username:
                keys.append({
                    'id': None,
                    'type_id': KeyType.LINK_ID,
                    'value': 'https://t.me/%s' % tg_username,
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
            data = dict(
                users=users,
                connections=connections,
                keys=keys,
                wishes=wishes,
                abilities=abilities,
            )
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
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
                    is_reverse=False,
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
    permission_classes = (IsAuthenticated, )

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Создать либо обновить возможность uuid

        Если возможность с заданным uuid существует, то проверить 
        принадлежит ли она пользователю, пославшему запрос,
        или его родственнику, и если принадлежит, то обновить ее.
        Если же не принадлежит, то вернуть сообщение об ошибке.
        Если возможности с таким uuid не существует, то создать.
        Может быть параметр user_uuid, чью возможность изменять
        или добавлять. Если параметр user_uuid отсутствует,
        возможность добавляется или изменяется у авторизованного пользователя.

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
            text = request.data.get('text')
            if not text:
                raise ServiceException('Возможность без текста')
            update_timestamp = request.data.get('last_edit', int(time.time()))
            uuid = request.data.get('uuid')
            owner, profile = self.check_user_or_owned_uuid(request, uuid_field='user_uuid')
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
                    if ability.owner == request.user or ability.owner.profile.owner == request.user:
                        ability.text = text
                        ability.update_timestamp = update_timestamp
                        ability.save()
                    else:
                        raise ServiceException('Возможность с uuid = %s не принадлежит ни Вам, ни Вашему родственнику' % uuid)
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
            qs = Ability.objects.filter(owner=user).order_by('update_timestamp')
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
        или его родственнику, иесли принадлежит, то удалить ее,
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
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_ability = ApiDeleteAbility.as_view()

class ApiInviteUseToken(ApiAddOperationMixin, SendMessageMixin, APIView):
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
                message = self.profile_link(profile_to) + ' принял Вашу благодарность'
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

class ApiProfileGenesis(UuidMixin, SQL_Mixin, APIView):

    def get(self, request, *args, **kwargs):
        """
        Строит рекурсивно дерево родни

        Пример вызова:
        /api/profile_genesis?uuid=4d02e22c-b6eb-4307-a440-ccafdeedd9b8
        Если задан uuid родственника, то выводится дерево родни
        владельца
        """
        try:
            related = ('user', 'owner', 'ability',)
            uuid = request.GET.get('uuid')
            user_q, profile_q = self.check_user_uuid(uuid, related=related)
            try:
                recursion_depth = int(request.GET.get('depth', 0) or 0)
            except (TypeError, ValueError,):
                recursion_depth = 0
            if recursion_depth <= 0 or recursion_depth > settings.MAX_RECURSION_DEPTH:
                recursion_depth = settings.MAX_RECURSION_DEPTH

            connections = []
            with connection.cursor() as cursor:
                cursor.execute(
                    'select * from find_rel_parent_child(%(user_id)s, %(recursion_depth)s)' % dict(
                        user_id=user_q.pk,
                        recursion_depth=recursion_depth,
                ))
                recs = self.dictfetchall(cursor)
            user_pks = set()
            pairs = []
            for rec in recs:
                if rec['is_parent']:
                    user_from_id = rec['user_from_id']
                    user_to_id = rec['user_to_id']
                else:
                    user_from_id = rec['user_to_id']
                    user_to_id = rec['user_from_id']
                pair = '%s/%s' % (user_from_id, user_to_id)
                if pair not in pairs:
                    pairs.append(pair)
                    user_pks.add(user_from_id)
                    user_pks.add(user_to_id)
                    connections.append(dict(
                        source=user_from_id,
                        target=user_to_id,
                        thanks_count=rec['thanks_count'],
                        is_trust=rec['is_trust'],
                    ))
            profiles_dict = dict()
            users = []
            for profile in Profile.objects.filter(user__pk__in=user_pks).select_related('user', 'ability'):
                profiles_dict[profile.user.pk] = dict(
                    uuid=profile.uuid,
                    gender=profile.gender,
                    last_name=profile.user.last_name,
                    first_name=profile.user.first_name,
                    middle_name=profile.middle_name,
                    user_pk=profile.user.pk,
                )
                users.append(profile.data_dict(request))

            if user_q.pk not in user_pks:
                user_pks.add(user_q.pk)
                users.append(profile_q.data_dict(request))

            for c in connections:

                # TODO: remove this debug:
                #
                c['source_fio'] = "%s %s %s" % (
                    profiles_dict[c['source']]['last_name'] or '-',
                    profiles_dict[c['source']]['first_name'] or '-',
                    profiles_dict[c['source']]['middle_name'] or '-',
                )
                c['target_fio'] = "%s %s %s" % (
                    profiles_dict[c['target']]['last_name'] or '-',
                    profiles_dict[c['target']]['first_name'] or '-',
                    profiles_dict[c['target']]['middle_name'] or '-',
                )
                # ------------------------

                c['child_gender'] = profiles_dict[c['source']]['gender']
                c['child_id'] = profiles_dict[c['source']]['user_pk']
                c['source'] = profiles_dict[c['source']]['uuid']
                c['parent_gender'] = profiles_dict[c['target']]['gender']
                c['parent_id'] = profiles_dict[c['target']]['user_pk']
                c['target'] = profiles_dict[c['target']]['uuid']

            data = dict(users=users, connections=connections)
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_profile_genesis = ApiProfileGenesis.as_view()
