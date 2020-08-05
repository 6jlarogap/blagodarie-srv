import os, datetime, time

from django.shortcuts import redirect
from django.db import transaction, connection
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

from app.utils import ServiceException

from contact.models import KeyType, Key, UserKey, LikeKey, Like, LogLike, \
                           Symptom, UserSymptom, SymptomChecksumManage, \
                           Journal, CurrentState, OperationType, Wish
from users.models import CreateUserMixin, IncognitoUser, Profile

MSG_NO_PARM = 'Не задан или не верен какой-то из параметров в связке номер %s (начиная с 0)'

class ApiAddOperationView(APIView):
    permission_classes = (IsAuthenticated, )
    
    @transaction.atomic
    def post(self, request):
        """
        Добавление операции

        Добавляет запись в таблицу Journal. Если тип операции Thank,
        то инкрементировать значение столбца sum_thanks_count для пользователя user_id_to,
        и инкрементировать значение столбца thanks_count в таблице CurrentState
        для user_id_from и user_id_to, если в таблице CurrentState
        не существует записи с такими user_id_from и user_id_to,
        то добавить ее.
        Если тип операции Trustless то инкрементировать значение столбца trustless_count
        и установить значение is_trust в таблице CurrentState в значение False.
        Если тип операции Trustless cancel, то декрементировать значение столбца
        trustless_count и установить значение is_trust в таблице CurrentState в значение True

        Пример исходных данных:
        {
            "user_id_to": "825b031e-95a2-4fdd-a70b-b446a52c4498",
            "operation_type_id": 1,
            "timestamp": 1593527855
        }
        """

        try:
            data = dict()
            status_code = status.HTTP_200_OK
            user_from = request.user
            user_to_uuid = request.data.get("user_id_to")
            operationtype_id = request.data.get("operation_type_id")
            comment = request.data.get("comment", None)
            if not user_to_uuid or not operationtype_id:
                raise ServiceException('Не заданы user_id_to и/или operation_type_id')
            try:
                profile_to = Profile.objects.select_for_update().get(uuid=user_to_uuid)
                user_to = profile_to.user
            except ValidationError:
                raise ServiceException('Неверный uuid = "%s"' % user_to_uuid)
            except Profile.DoesNotExist:
                raise ServiceException('Не найден пользователь, uuid = "%s"' % user_to_uuid)
            try:
                operationtype_id = int(operationtype_id)
                operationtype = OperationType.objects.get(pk=operationtype_id)
            except (ValueError, OperationType.DoesNotExist,):
                raise ServiceException('Неизвестный operation_type_id = %s' % operationtype_id)
            insert_timestamp = request.data.get('timestamp', int(time.time()))

            Journal.objects.create(
                user_from=user_from,
                user_to=user_to,
                operationtype=operationtype,
                insert_timestamp=insert_timestamp,
                comment=comment,
            )

            if operationtype_id == OperationType.THANK:
                currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                    user_from=user_from,
                    user_to=user_to,
                    defaults=dict(
                        thanks_count=1,
                ))
                if not created_:
                    currentstate.thanks_count = F('thanks_count') + 1
                    currentstate.save(update_fields=('thanks_count',))
                fame = user_to.currentstate_user_to_set.filter(
                    Q(thanks_count__gt=0) | Q(is_trust=False)
                ).distinct().count()
                profile_to.sum_thanks_count += 1
                profile_to.fame = fame
                profile_to.save(update_fields=('fame', 'sum_thanks_count',))

            elif operationtype_id == OperationType.TRUSTLESS:
                currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                    user_from=user_from,
                    user_to=user_to,
                    defaults=dict(
                        is_trust=False,
                ))
                if created_ or currentstate.is_trust:
                    if not created_:
                        currentstate.is_trust = False
                        currentstate.save(update_fields=('is_trust',))
                    fame = user_to.currentstate_user_to_set.filter(
                        Q(thanks_count__gt=0) | Q(is_trust=False)
                    ).distinct().count()
                    profile_to.trustless_count += 1
                    profile_to.fame = fame
                    profile_to.save(update_fields=('fame', 'trustless_count',))

            elif operationtype_id == OperationType.TRUSTLESS_CANCEL:
                currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                    user_from=user_from,
                    user_to=user_to,
                    defaults=dict(
                        is_trust=True,
                ))
                if not created_ and not currentstate.is_trust:
                    currentstate.is_trust = True
                    currentstate.save(update_fields=('is_trust',))
                    fame = user_to.currentstate_user_to_set.filter(
                        Q(thanks_count__gt=0) | Q(is_trust=False)
                    ).distinct().count()
                    if profile_to.trustless_count:
                        profile_to.trustless_count -= 1
                    profile_to.fame = fame
                    profile_to.save(update_fields=('fame', 'trustless_count',))

        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_operation = ApiAddOperationView.as_view()

class ApiGetUserOperationsView(APIView):

    def post(self, request):
        """
        Получение журнала операций


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
                "operation_type_id": 1,
                "timestamp": 384230840234,
                "comment": "Хороший человек"
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
                raise ServiceException('Неверный uuid = "%s"' % user_to_uuid)
            except Profile.DoesNotExist:
                raise ServiceException('Не найден пользователь, uuid = "%s"' % user_to_uuid)
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

class ApiAddKeyView(APIView):
    
    @transaction.atomic
    def post(self, request):
        """
        Добавить ключ

        Пример исходных данных:
        {
            "keyz":
                [
                    {"id":1,"owner_id":2313,"value":"vasya@mail.ru","type_id": 2},
                    {"id":2,"owner_id":null,"value":"+375 33 846-48-54","type_id":1}
                ]
        }
        Надо проверить, существует ли в базе ключ с такими value и type_id:
        * Если не существует, то добавить запись в БД и вернуть его id.
        * Если существует, вернуть его id и проверить owner_id:
            - Если owner_id в базе не пустой,
              то если переданный owner_id не равен owner_id в базе,
              будет ошибка
            - Если owner_id в базе пустой, а в переданных данных он не пустой,
              то записать owner_id в запись БД
        Возвращает:
        {
            "keyz":[
                {"id":1,"server_id":2134},
                {"id":2,"server_id":2135}
            ]
        }
        """
        try:
            data = dict(keyz=[])
            status_code = status.HTTP_200_OK
            keyz = request.data.get("keyz")
            if not isinstance(keyz, list):
                raise ServiceException("Не заданы keyz")
            n_key = 0
            for key in keyz:
                try:
                    id_ = key['id']
                    owner_id = key.get('owner_id')
                    value = key['value']
                    type_id = key['type_id']
                except KeyError:
                    raise ServiceException(MSG_NO_PARM % n_key)
                if owner_id:
                    try:
                        owner = User.objects.get(pk=owner_id)
                    except User.DoesNotExist:
                        raise ServiceException("Не найден пользователь с owner_id = %s" % owner_id)
                else:
                    owner = None
                try:
                    type_ = KeyType.objects.get(pk=type_id)
                except KeyType.DoesNotExist:
                    raise ServiceException("Нет такого типа ключа: %s" % type_id)
                objects = Key.objects
                if owner is not None:
                    objects = objects.select_for_update()
                key_object, created_ = objects.get_or_create(
                    type=type_,
                    value=value,
                    defaults = dict(
                        owner=owner,
                ))
                if not created_:
                    if key_object.owner is None:
                        if owner is not None:
                            key_object.owner = owner
                            key_object.save(update_fields=('owner',))
                        #else:
                            # В базе owner is None, переданный в запросе owner is None. ОК
                            #pass
                    else:
                        if owner != key_object.owner:
                            if owner is None:
                                msg = "Нельзя лишать существующий ключ владельца" #"
                            else:
                                msg = "Нельзя менять владельца в существующем ключе"
                            msg += ", см. связку вх. параметров номер %s (начиная с 0)"
                            raise ServiceException(msg % n_key)
                        #else:
                            # Непустой owner в базе тот же, что и переданный в запросе. ОК
                            #pass
                data['keyz'].append({
                    'id': id_,
                    'server_id': key_object.pk,
                })
                n_key += 1
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_key = ApiAddKeyView.as_view()

class ApiGetOrCreateKey(APIView):
    
    @transaction.atomic
    def post(self, request):
        """
        Добавление ключа

        Надо проверить, существует ли в базе ключ с такими value и type_id:
            Если не существует, то добавить запись в БД и вернуть его id.
            Если существует, вернуть его id.
        Надо проверить проверить, существует ли в базе связь пользователь-ключ
            с такими user_id и keyz_id:
            Если не существует, то добавить запись в БД и вернуть его id.
            Если существует, вернуть его id

        Пример исходных данных:
        {
            "user_id":2,
            "keyz": [
                {"id":1,"value":"vasya@mail.ru","type_id":1},
                {"id":2,"value":"+375 33 846-48-54","type_id":2}
            ]
        }
        Возвращает:
        {
            "keyz":[
                {"id":1,"server_id":2134},
                {"id":2,"server_id":2135}
            ],
            "user_keyz":[
                {"keyz_id":1,"server_id":3566},
                {"keyz_id":2,"server_id":3567}
            ]
        }
        """
        try:
            data = dict(keyz=[], user_keyz=[])
            keyz = request.data.get('keyz')
            if not isinstance(keyz, list):
                raise ServiceException('Не заданы keyz')
            user_id = request.data.get('user_id')
            if not user_id:
                raise ServiceException('Не задан user_id')
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise ServiceException('Нет пользователя с user_id = %s' % user_id)
            n_key = 0
            for key in keyz:
                try:
                    id_ = key['id']
                    value = key['value']
                    type_id = key['type_id']
                except (KeyError, TypeError,):
                    raise ServiceException(
                        'Не задан или не верен какой-то из параметров'
                        'в ключе номер %s (начиная с 0)'
                        % n_key
                    )
                try:
                    type_ = KeyType.objects.get(pk=type_id)
                except KeyType.DoesNotExist:
                    raise ServiceException("Нет такого типа ключа: %s" % type_id)
                key_object, created_ = Key.objects.get_or_create(
                    type=type_,
                    value=value,
                    defaults = dict(
                        owner=None,
                ))
                data['keyz'].append({
                    'id': id_,
                    'server_id': key_object.pk,
                })
                userkey_object, created_ = UserKey.objects.get_or_create(
                    user=user,
                    key=key_object,
                )
                data['user_keyz'].append({
                    'keyz_id': id_,
                    'server_id': userkey_object.pk,
                })
                n_key += 1

            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

get_or_create_key = ApiGetOrCreateKey.as_view()

class ApiAddLIke(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Запрос добавляет вставляет лайк и его связь с ключом в БД
        и возвращает ID лайков и связей в БД

        Пример исходных данных:
        {
            "likes":[
                {"id":1,"owner_id":2313,"create_timestamp":1565599089},
                {"id":2,"owner_id":2313,"create_timestamp":1565599090}
            ],
            "likekeyz": [
                {"id":22,"like_id":1,"keyz_id":431},
                {"id":23,"like_id":1,"keyz_id":432},
                {"id":33,"like_id":2,"keyz_id":462}
            ]
        }
        Возвращает:
        {
            "likes":[
                {"id":1,"server_id":9586},
                {"id":2,"server_id":9587}
            ],
            "likekeyz":[
                {"id":22,"server_id":5454},
                {"id":23,"server_id":5455},
                {"id":33,"server_id":322}
            ]
        }
        """
        try:
            data = dict(likes=[], likekeyz=[])
            likes = request.data.get('likes')
            if not isinstance(likes, list):
                raise ServiceException('Не заданы likes')
            like_dict = dict()
            n_key = 0
            for like in likes:
                try:
                    id_ = like['id']
                    owner_id = like['owner_id']
                except KeyError:
                    raise ServiceException(
                        'Не задан или не верен какой-то из параметров'
                        'в likes номер %s (начиная с 0)'
                        % n_key
                    )
                insert_timestamp = like.get('create_timestamp', int(time.time()))
                try:
                    owner = User.objects.get(pk=owner_id)
                except User.DoesNotExist:
                    raise ServiceException("Нет пользователя с owner_id = %s" % owner_id)
                like_object = Like.objects.create(
                    owner=owner,
                    insert_timestamp=insert_timestamp,
                )
                data['likes'].append({
                    'id': id_,
                    'server_id': like_object.pk,
                })
                like_dict[id_] = like_object
                n_key += 1

            likekeyz = request.data.get('likekeyz')
            if not isinstance(likekeyz, list):
                raise ServiceException('Не заданы likekeyz')
            for likekey in likekeyz:
                try:
                    id_ = likekey['id']
                    like_id = likekey['like_id']
                    keyz_id = likekey['keyz_id']
                except KeyError:
                    raise ServiceException(
                        'Не задан или не верен какой-то из параметров'
                        'в likekeyz номер %s (начиная с 0)'
                        % n_key
                    )
                if like_dict.get(like_id, None) is None:
                    raise ServiceException(
                        'likekeyz номер %s (начиная с 0): '
                        'нет like_id = %s среди id в массиве likes'
                        % (n_key, like_id, )
                    )
                try:
                    key = Key.objects.get(pk=keyz_id)
                except Key.DoesNotExist:
                    raise ServiceException('Не найден ключ с keyz_id = %s' % keyz_id)
                likekey_object = LikeKey.objects.create(
                    like=like_dict[like_id],
                    key=key,
                )
                data['likekeyz'].append({
                    'id': id_,
                    'server_id': likekey_object.pk,
                })

            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_add_like = ApiAddLIke.as_view()

class ApiGetLikes(APIView):

    def get(self, request):
        """
        Получение лайков и связей лайк-ключ

        Возвращает все лайки, поставленные либо отмененные
        данным пользователем после заданного момента времени,
        а также связи лайк-ключ для всех переданных лайков
        со значениями и типами ключей.

        Пример исходных данных:
        .../getlikes?ownerid=2&synctimestamp=1569995335

        Возвращает:
        {
            "likes":[
                {"server_id":231,"timestamp":1570995335},
                {"server_id":232,"timestamp":1579995335},
                {"server_id":233,"timestamp":569995335,"cancel_timestamp":1569995335}
            ],
            "likekeyz":[
                {"server_id":3443,"like_id":231,"keyz_id":340,"value":"asdf@gmail.com","type_id":2},
                {"server_id":3444,"like_id":231,"keyz_id":344,"value":"375296685412","type_id":1},
                {"server_id":3445,"like_id":232,"keyz_id":874,"value":"375298849562","type_id":1},
                {"server_id":6456,"like_id":233,"keyz_id":874,"value":"375298849562","type_id":1}
            ]
        }
        """
        try:
            data = dict(
                likes=[],
                likekeyz=[],
            )
            ownerid = request.GET.get('ownerid')
            if not ownerid:
                raise ServiceException("Не задан параметр ownerid")
            synctimestamp = request.GET.get('synctimestamp')

            qs = Q(owner__pk=ownerid)
            if synctimestamp:
                qs &= Q(insert_timestamp__gte=synctimestamp) | Q(update_timestamp__gte=synctimestamp)
            for like in Like.objects.filter(qs).distinct():
                data['likes'].append(dict(
                    server_id=like.pk,
                    create_timestamp=like.insert_timestamp,
                    cancel_timestamp=like.cancel_timestamp,
                ))
                for likekey in LikeKey.objects.filter(like=like):
                    data['likekeyz'].append(dict(
                        server_id=likekey.pk,
                        like_id=likekey.like.pk,
                        keyz_id=likekey.key.pk,
                        value=likekey.key.value,
                        type_id=likekey.key.type.pk,
                    ))

            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_likes = ApiGetLikes.as_view()

class ApiGetAllLikes(APIView):

    def post(self, request, *args, **kwargs):
        """
        Получение всех лайков по ключам или по идентификаторам

        Запрос возвращает сгруппированные:
            по ключам: kwargs['by'] =='keys'
        или
            по идентификаторам: kwargs['by'] =='ids'
        вставленные либо обновленные после заданного момента времени
        (insert_timestamp > sync_timestamp OR update_timestamp > sync_timestamp).

        Примеры исходных данных.
            kwargs['by'] =='keys':
                {
                    "keyz": [
                        {
                        "value": "324234234",
                        "type_id": 1
                        },
                        {
                        "value": "asfe@gmail.com",
                        "type_id": 2
                        },
                        {
                        "value": "656346346",
                        "type_id": 1
                        }
                    ]
                }
            kwargs['by'] =='ids':
                {
                    "keyz_ids":[232,3432,532]
                }

        Возвращает, отсортированные по убыванию update_timestamp:
            {
                "likes": [
                    {
                    "owner_id": 324,
                    "server_id": 231,
                    "create_timestamp": 1570995335,
                    "cancel_timestamp": null
                    },
                    {
                    "owner_id": 77,
                    "server_id": 232,
                    "create_timestamp": 1570995336,
                    "cancel_timestamp": null
                    },
                    {
                    "owner_id": 14,
                    "server_id": 233,
                    "create_timestamp": 54543545345,
                    "cancel_timestamp": 63463463463
                    }
                ]
            }
        """
        try:
            data = dict(
                likes=[],
            )
            if kwargs['by'] =='ids':
                keyz_ids = request.data.get('keyz_ids')
                if not isinstance(keyz_ids, list):
                    raise ServiceException('Не заданы keyz_ids')

            elif kwargs['by'] =='keys':
                keyz = request.data.get('keyz')
                if not isinstance(keyz, list):
                    raise ServiceException('Не заданы keyz')
                keyz_ids = []
                n = 0
                err_message = 'Массив keyz, элемент %s (начиная с нуля): не заданы value и/или type_id'
                for key in keyz:
                    if not isinstance(key, dict):
                        raise ServiceException(err_message % n)
                    value = key.get('value')
                    type_id = key.get('type_id')
                    if value is None or type_id is None:
                        raise ServiceException(err_message % n)
                    try:
                        key_object = Key.objects.get(type__pk=type_id, value=value)
                        keyz_ids.append(key_object.pk)
                    except Key.DoesNotExist:
                        pass
                    n += 1
            else:
                keyz_ids = []

            if keyz_ids:
                for like in Like.objects.filter(
                        likekey__key__pk__in=keyz_ids
                    ).order_by('-update_timestamp').distinct():
                    data['likes'].append(dict(
                        owner_id=like.owner.pk,
                        server_id=like.pk,
                        create_timestamp=like.insert_timestamp,
                        cancel_timestamp=like.cancel_timestamp,
                    ))
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_all_likes = ApiGetAllLikes.as_view()

class ApiGetContactsSumInfo(APIView):

    def post(self, request, *args, **kwargs):
        """
        Получение известности и общего количества лайков

        Передаем user_id.
        Передаем массив контактов, у контакта есть id и массив ключей.
        По каждому контакту, надо получить количество уникальных неотмененных лайков,
        привязанных к его ключам - это будет sum_likes_count.
        Надо еще получать количество уникальных лайков заданного user_id,
        это будет likes_count
        Известность (fame) - количество уникальных пользователей,
        которым известен хотя бы один ключ контакта.

        Пример исходных данных:
        Если ключи идут как тип - значение
        {
            "user_id": 45,
            "contacts": [
                    {"id":75,"keyz":[{"value":"12345678","type_id":1}]},
                    {"id":76,"keyz":[
                            {"value":"333555","type_id":1},
                            {"value":"vasya@gmail.com","type_id":2}
                        ]
                    },
                ]
        }
        Если ключи идут как ID's
        {
            "contacts": [
                    {"id":75,"keyz":[2, 3]},
                    {"id":76,"keyz":[4, 5]},
                ]
        }
        Возвращает:
        {
        "contacts":[
                {"id":75,"fame":5,"likes_count":12,"sum_likes_count":32},
                {"id":76,"fame":3,"likes_count":10,"sum_likes_count":12},
            ]
        }
        """
        try:
            data = dict(contacts=[])
            contacts = request.data.get("contacts")
            if not isinstance(contacts, list):
                raise ServiceException("Не заданы contacts")
            user_id = request.data.get("user_id")

            n_key = 0
            for contact in contacts:
                try:
                    id_ = contact['id']
                    keyz = contact['keyz']
                except (KeyError, TypeError,):
                    raise ServiceException(MSG_NO_PARM % n_key)
                by = kwargs.get('by')
                key_pks = []
                if by == 'values':
                    for key in keyz:
                        try:
                            value = key['value']
                            type_id = key['type_id']
                        except (KeyError, TypeError,):
                            raise ServiceException(
                                "Не заданы или не верны value и/или type_id "
                                "в каком-то из ключей контакта id = %s"
                                % id_
                            )
                        try:
                            key_object_pk = Key.objects.values_list('pk', flat=True). \
                                            get(value=value, type__pk=type_id)
                            key_pks.append(key_object_pk)
                        except Key.DoesNotExist:
                            pass
                elif by == 'ids':
                    key_pks = keyz
                fame = likes_count = sum_likes_count = 0
                if key_pks:
                    fame = UserKey.objects.filter(
                            key__pk__in=key_pks
                            ).only('pk').distinct('user').count()
                    sum_likes_count = LikeKey.objects.filter(
                                        key__pk__in=key_pks,
                                        like__cancel_timestamp__isnull=True,
                                        ).only('pk').distinct('like').count()
                    if user_id is not None:
                        likes_count = LikeKey.objects.filter(
                                        key__pk__in=key_pks,
                                        like__owner__pk=user_id,
                                        like__cancel_timestamp__isnull=True,
                                        ).only('pk').distinct('like').count()
                data['contacts'].append({
                    'id': id_,
                    'fame': fame,
                    'likes_count': likes_count,
                    'sum_likes_count': sum_likes_count,
                })
                n_key += 1

            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_get_contacts_sum_info = ApiGetContactsSumInfo.as_view()

class ApiCancelLike(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Отмена лайков

        Запрос обновляет поле cancel_timestamp в соответствии
        с переданным значением и обновляет поле update_timestamp,
        устанавливая его в значение текущего момента времени

        Пример исходных данных:
        {
            "likes": [
                {"server_id":23,"owner_id":23,"cancel_timestamp":34235235235},
                {"server_id":658,"owner_id":23,"cancel_timestamp":6537547345}
            ]
        }
        Возвращает:
        {
            "count_cancelled_likes" : сколько записей изменено
        }
        """
        try:
            likes = request.data.get('likes')
            if not isinstance(likes, list):
                raise ServiceException('Не заданы likes')
            n_key = 0
            count_cancelled_likes = 0
            for like in likes:
                try:
                    server_id = like['server_id']
                    owner_id = like['owner_id']
                    cancel_timestamp = like['cancel_timestamp']
                except (KeyError, TypeError,):
                    raise ServiceException(MSG_NO_PARM % n_key)
                update_timestamp = int(time.time())
                count_cancelled_likes += Like.objects.filter(
                    pk=server_id,
                    owner__pk=owner_id,
                ).update(cancel_timestamp=cancel_timestamp, update_timestamp=update_timestamp)
                n_key += 1

            data = dict(count_cancelled_likes=count_cancelled_likes)
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_cancel_likes = ApiCancelLike.as_view()

class ApiDeleteLike(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Удаление благодарностей

        Запрос удаляет записи из таблицы tbl_like_keyz,
        а затем из таблицы tbl_like,
        соответствующие переданным идентификаторам благодарностей.
        Отсутствие записей с каким либо идентификатором благодарности
        не считать за ошибку. Они могли быть удалены ранее,
        при синхронизации с другого устройства.

        Пример исходных данных:
        {
            "ids": [232,3432,532,245,52,34]
        }
        Возвращает:
        {
            "count_deleted_likes" : сколько лайков удалено
        }
        """
        try:
            ids = request.data.get('ids')
            if not isinstance(ids, list):
                raise ServiceException('Не заданы ids')
            count_deleted_likes = Like.objects.filter(pk__in=ids).delete()
            data = dict(count_deleted_likes=count_deleted_likes[0])
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_likes = ApiDeleteLike.as_view()

class ApiDeleteLikeKey(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Удаление связи благодарность-ключ

        Запрос удаляет записи из таблицы tbl_like_keyz,
        соответствующие переданным идентификаторам.
        Отсутствие записей с каким либо идентификатором
        не считать за ошибку. Они могли быть удалены ранее,
        при синхронизации с другого устройства.

        Пример исходных данных:
        {
            "ids": [232,3432,532,245,52,34]
        }
        Возвращает:
        {
            "count_deleted_likekeyz" : сколько лайков удалено
        }
        """
        try:
            ids = request.data.get('ids')
            if not isinstance(ids, list):
                raise ServiceException('Не заданы ids')
            count_deleted_likekeyz = LikeKey.objects.filter(pk__in=ids).delete()
            data = dict(count_deleted_likekeyz=count_deleted_likekeyz[0])
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_like_keys = ApiDeleteLikeKey.as_view()

class ApiDeleteUserKey(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Удаление связи пользователь-ключ

        Запрос удаляет записи из таблицы tbl_user_keyz,
        соответствующие переданным идентификаторам.
        Отсутствие записей с каким либо идентификатором
        не считать за ошибку. Они могли быть удалены ранее,
        при синхронизации с другого устройства.

        Пример исходных данных:
        {
            "ids": [232,3432,532,245,52,34]
        }
        Возвращает:
        {
            "count_deleted_userkeyz" : сколько лайков удалено
        }
        """
        try:
            ids = request.data.get('ids')
            if not isinstance(ids, list):
                raise ServiceException('Не заданы ids')
            count_deleted_userkeyz = UserKey.objects.filter(pk__in=ids).delete()
            data = dict(count_deleted_userkeyz=count_deleted_userkeyz[0])
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_delete_user_keys = ApiDeleteUserKey.as_view()

class ApiGetOrCreateLikeKey(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Добавление связи между лайком и ключом

        Надо проверить, существует ли в базе связь лайк-ключ
        с такими like_id и keyz_id:
            - Если не существует, то добавить запись в БД и вернуть его id.
            - Если существует, вернуть его id.

        Пример исходных данных:
        {
            "likekeyz": [
                {"id":1,"like_id":123,"keyz_id":431},
                {"id":2,"like_id":123,"keyz_id":462}
            ]
        }
        Возвращает:
        {
            "likekeyz":[
                {"id":1, "server_id":5454},
                {"id":2, "server_id":5455},
            ]
        }
        """
        try:
            data = dict(likekeyz=[])
            status_code = status.HTTP_200_OK
            likekeyz = request.data.get("likekeyz")
            if not isinstance(likekeyz, list):
                raise ServiceException("Не заданы likekeyz")
            n_key = 0
            for likekey in likekeyz:
                try:
                    id_ = likekey['id']
                    like_id = likekey['like_id']
                    keyz_id = likekey['keyz_id']
                except KeyError:
                    raise ServiceException(MSG_NO_PARM % n_key)
                try:
                    like = Like.objects.get(pk=like_id)
                except Like.DoesNotExist:
                    raise ServiceException("Нет лайка с like_id = %s" % like_id)
                try:
                    key = Key.objects.get(pk=keyz_id)
                except Key.DoesNotExist:
                    raise ServiceException("Нет ключа с keyz_id = %s" % keyz_id)
                likekey_object, created_ = LikeKey.objects.get_or_create(
                    like=like,
                    key=key,
                )
                data['likekeyz'].append({
                    'id': id_,
                    'server_id': likekey_object.pk,
                })
                n_key += 1
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

get_or_create_like_key = ApiGetOrCreateLikeKey.as_view()

class ApiGetStats(APIView):

    def get(self, request, *args, **kwargs):
        """
        Получение статистики, диаграмм и проч.

        Что получать, определяется в словаре kwargs
        """
        return Response(data=LogLike.get_stats(request, *args, **kwargs), status=status.HTTP_200_OK)

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

class ApiAddOrUpdateWish(APIView):
    permission_classes = (IsAuthenticated, )

    @transaction.atomic
    def post(self, request, *args, **kwargs,):
        """
        Создать либо обновить желание uuid

        Если желание с заданным uuid существует,
        то проверить принадлежит ли оно пользователю,
        пославшему запрос, и если принадлежит, то обновить его.
        Если же не принадлежит, то вернуть сообщение об ошибке.
        Если желания с таким uuid не существует, то создать
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
            if uuid:
                do_create = False
                try:
                    wish = Wish.objects.get(uuid=uuid)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Wish.DoesNotExist:
                    do_create = True
                    Wish.objects.create(
                        uuid=uuid,
                        owner=request.user,
                        text=text,
                        update_timestamp=update_timestamp,
                    )
                if not do_create:
                    if wish.owner == request.user:
                        wish.text = text
                        wish.update_timestamp = update_timestamp
                        wish.save()
                    else:
                        raise ServiceException('Желание с uuid = %s принадлежит другому пользователю' % uuid)
            else:
                Wish.objects.create(
                    owner=request.user,
                    text=text,
                    update_timestamp=update_timestamp,
                )
            data = dict()
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
        если принадлежит, то удалить его, иначе вернуть сообщение об ошибке.
        Пример исходных данных:
        /api/deletewish?uuid=4d02e22c-b6eb-4307-a440-ccafdeedd9b8
        Возвращает: {}
        """
        try:
            uuid = request.GET.get('uuid')
            if uuid:
                try:
                    wish = Wish.objects.get(uuid=uuid, owner=request.user)
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Wish.DoesNotExist:
                    raise ServiceException(
                        'Желание с uuid = %s не найдено или принадлежит другому пользователю' % uuid
                    )
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

class ApiGetUserWishes(APIView):

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
            if uuid:
                try:
                    owner = Profile.objects.get(uuid=uuid).user
                except ValidationError:
                    raise ServiceException('Неверный uuid = %s' % uuid)
                except Profile.DoesNotExist:
                    raise ServiceException('Не найден пользователь с uuid = %s' % uuid)
                data = dict(
                    wishes = [
                        dict(
                            uuid=wish.uuid,
                            text=wish.text,
                            last_edit=wish.update_timestamp,
                        ) for wish in Wish.objects.filter(owner=owner).order_by('update_timestamp')
                    ]
                )
                status_code = status.HTTP_200_OK
            else:
                raise ServiceException('Не задан uuid пользователя')
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
