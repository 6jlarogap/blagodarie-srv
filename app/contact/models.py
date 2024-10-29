import time, datetime, json, hashlib, re
import os, uuid
from collections import OrderedDict

from app.utils import get_moon_day, ServiceException

from django.conf import settings
from django.db import models, connection
from django.utils.translation import gettext_lazy as _
from django.db.models.query_utils import Q
from django.contrib.postgres.fields import ArrayField

from django.contrib.auth.models import User

# Здесь поля insert_timestamp, update_timestamp. В ряде моделей требуется
# и то, и другое, в иных таблицах только один из этих timestamp.
#
# Для таблицы auth_user требуется только insert_timestamp, это можно взять
# из ее поля date_joined (timestamp with time zone)
#
from app.models import BaseModelInsertTimestamp, BaseModelInsertUpdateTimestamp, \
                       GeoPointModel, GenderMixin

class KeyType(models.Model):

    LINK_ID = 5
    OTHER_ID = 6

    title = models.CharField(_("Код ключа"), max_length=255, unique=True)

class OperationType(models.Model):

    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_ATTITUDE = 4
    TRUST_OR_THANK = 5
    FATHER = 6
    NOT_PARENT = 7
    MOTHER = 8
    SET_FATHER = 9
    SET_MOTHER = 10
    # Acquainted
    ACQ = 11
    # Took Part in Acquaintance Game
    # В этом случае journal.user_to: с кем установил занкомство
    DID_MEET = 12
    # Revoked Part in Acquaintance Game
    # В этом случае journal.user_to: с кем установил занкомство, но
    # отказался от игры знакомств
    REVOKED_MEET = 13
    # Сброс и установка симпатии
    SET_SYMPA = 14
    REVOKE_SYMPA = 15

    title = models.CharField(_("Тип операции"), max_length=255, unique=True)

class AnyText(BaseModelInsertTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    text = models.CharField(_("Значение"), max_length=2048, unique=True, db_index=True)
    fame = models.PositiveIntegerField(_("Известность"), default=0)
    sum_thanks_count = models.PositiveIntegerField(_("Число благодарностей"), default=0)
    trust_count = models.PositiveIntegerField(_("Число оказанных доверий"), default=0)
    mistrust_count = models.PositiveIntegerField(_("Число утрат доверия"), default=0)

class Journal(BaseModelInsertTimestamp):

    #TODO
    # При типах операции папа, мама user_from, user_to - необязательно пользователь,
    # который вносит данные. Значит нужно еще поле, миграция в это поле, правки в методе
    # api_get_user_operations. Пока этим методом не пользуемся, можно подожать.
    # Еще правка в api_addoperation
    # Из телеграма SET_FATHER, SET_MOTHER передается owner_id.
    #
    user_from = models.ForeignKey('auth.User',
                    verbose_name=_("От кого"), on_delete=models.CASCADE,
                    related_name='journal_user_from_set')
    user_to = models.ForeignKey('auth.User',
                    verbose_name=_("Кому"), on_delete=models.CASCADE, null=True,
                    related_name='journal_user_to_set')
    anytext = models.ForeignKey(AnyText,
                    verbose_name=_("Текст"), on_delete=models.CASCADE, null=True)
    operationtype = models.ForeignKey(OperationType,
                    verbose_name=_("Тип операции"), on_delete=models.CASCADE)
    comment = models.TextField(verbose_name=_("Комментарий"), null=True)

class UserDictMixin(object):
    def user_dict(self, user):
        return {
            'id': user.id,
            'username': user.username,
            'uuid': str(user.profile.uuid),
            'first_name': user.first_name,
        }

class TgJournal(UserDictMixin, models.Model):
    """
    Ссылки на сообщения телеграма при благодарностях и др. действиях
    """
    journal = models.ForeignKey(Journal, verbose_name=_("Журнал"), on_delete=models.CASCADE)
    from_chat_id = models.BigIntegerField(_("Chat Id"),)
    message_id = models.BigIntegerField(_("Message Id"),)

    def data_dict(self):
        return dict(
            timestamp=self.journal.insert_timestamp,
            user_from=self.user_dict(self.journal.user_from),
            user_to=self.user_dict(self.journal.user_to),
            user_to_delivered=self.user_dict(self.journal.user_to),
            from_chat_id=self.from_chat_id,
            message_id=self.message_id,
            operation_type_id=self.journal.operationtype.pk,
        )

class TgMessageJournal(UserDictMixin, BaseModelInsertTimestamp):
    """
    Ссылки на сообщения телеграма при обмене пользователями сообщений
    """
    user_from = models.ForeignKey('auth.User',
                    verbose_name=_("От кого"), on_delete=models.CASCADE,
                    related_name='tg_message_journal_user_from_set')
    user_to = models.ForeignKey('auth.User',
                    verbose_name=_("Кому"), on_delete=models.CASCADE,
                    related_name='tg_message_journal_user_to_set')
    # Сообщение может быть отправлено к owned профилю,
    # тогда кто получил сообщение, если получил
    user_to_delivered = models.ForeignKey('auth.User',
                    verbose_name=_("Кому доставлено"), on_delete=models.CASCADE, null=True,
                    related_name='tg_message_journal_user_to_delivered_set')
    from_chat_id = models.BigIntegerField(_("Chat Id"),)
    message_id = models.BigIntegerField(_("Message Id"),)
    operationtype = models.ForeignKey(OperationType, null=True,
                    verbose_name=_("Тип операции"), on_delete=models.CASCADE)

    def data_dict(self):
        return dict(
            timestamp=self.insert_timestamp,
            user_from=self.user_dict(self.user_from),
            user_to=self.user_dict(self.user_to),
            user_to_delivered=self.user_dict(self.user_to_delivered) if self.user_to_delivered else None,
            from_chat_id=self.from_chat_id,
            message_id=self.message_id,
            operation_type_id=self.operationtype and self.operationtype.pk or None,
        )

class CurrentState(BaseModelInsertUpdateTimestamp):

    ACQ = 'a'
    TRUST = 't'
    MISTRUST = 'mt'

    ATTITUDES = (
        (ACQ, _('Знаком(а)')),
        (TRUST, _('Доверяет')),
        (MISTRUST, _('Не доверяет')),
    )

    user_from = models.ForeignKey('auth.User',
                    verbose_name=_("От кого"), on_delete=models.CASCADE,
                    related_name='currentstate_user_from_set')
    user_to = models.ForeignKey('auth.User',
                    verbose_name=_("Кому"), on_delete=models.CASCADE, null=True,
                    related_name='currentstate_user_to_set')
    anytext = models.ForeignKey(AnyText,
                    verbose_name=_("Текст"), on_delete=models.CASCADE, null=True)
    thanks_count = models.PositiveIntegerField(_("Число благодарностей"), default=0)
    attitude = models.CharField(_("Отношение"), max_length=2, choices=ATTITUDES,
                    null=True, db_index=True)

    is_father = models.BooleanField(_("Отец"), default=False, db_index=True)
    is_mother = models.BooleanField(_("Мать"), default=False, db_index=True)

    # Для построения графов родительских связей между пользователями, где надо учитывать,
    # что связь - это не только что пользователь 2 -- папа/мама пользователя 1,
    # но если еще пользователь 1 - папа/мама 3-го,
    # то должны быть связи 1->2, 1<-3. Для этого вводим служебное поле is_child
    #
    # Если is_child == False, то имеем родственную связь user_from -> user_to
    # (user_to is_father/is_mother of user_from)
    # Если is_child == True, то имеем родственную связь user_to -> user_from
    # (user_from is_father/is_mother of user_to)
    #
    is_child = models.BooleanField(_("Потомок"), default=False, db_index=True)

    # Для построения графов связей между пользователями, где надо учитывать
    # связь - это не только что пользователь 1 отблагодарил пользователя 2,
    # но если 2-й не благодарил 1-го, 1-й должен иметь связь со 2-м.
    # В этом случае в таблице появится запись:
    #   user_to:        2
    #   user_from:      1
    #   is_reverse      True
    #   thanks_count, attitude: из записи, где user_from=1, user_to=2
    #
    #   Если же 2-й таки отблагодарит 1-го, то is_reverse станет False,
    #   а thanks_count, attitude примут действительные значения:
    #   числа благодарностей 2-го 1-му и доверия
    #
    is_reverse = models.BooleanField(_("Обратное отношение"), default=False, db_index=True)

    # Аналогично для симпатий: прямая симпатия и фейковая обратная
    is_sympa = models.BooleanField(_("Симпатия"), default=False, db_index=True)
    is_sympa_reverse = models.BooleanField(_("Симпатия: обратное отношение"), default=False, db_index=True)


    def data_dict(
        self,
        show_child=False,
        show_attitude=False,
        show_id_fio=False,
        show_sympa=False,
        fmt='d3js'
    ):

        result = dict()
        if fmt == '3d-force-graph':
            result.update(
                source=self.user_from.pk,
                target=self.user_to.pk,
            )
        else:
            result.update(
                source=self.user_from.profile.uuid,
                target=self.user_to.profile.uuid,
            )
        if show_child:
            result.update(is_child=self.is_child,)
        if show_attitude:
            result.update(dict(
                thanks_count=self.thanks_count,
                attitude=self.attitude,
            ))
        if show_id_fio:
            result.update(dict(
                source_fio=self.user_from.first_name,
                source_id=self.user_from.pk,
                target_fio=self.user_to.first_name,
                target_id=self.user_to.pk,
            ))
        if show_sympa:
            result.update(is_sympa=self.is_sympa)
        return result

    class Meta:
        unique_together = (
            ('user_from', 'user_to', ),
            ('user_from', 'anytext', ),
        )

class Key(BaseModelInsertTimestamp):

    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    type = models.ForeignKey(KeyType, on_delete=models.CASCADE)
    value = models.CharField(_("Значение"), max_length=255, db_index=True)

    class Meta:
        unique_together = ('type', 'value', )

    def __str__(self):
        return '(id=%s) type=%s (%s), value=%s' % (
            self.pk, self.type.title, self.type.pk, self.value
        )

    def data_dict(self):
        return {
            "id": self.pk,
            "value": self.value,
            "type_id": self.type.pk,
        }

class SymptomChecksumManage(object):
    """
    Расчет контрольной суммы при изменении симптомов/групп симптомов
    """
    SYMPTOM_CHECKSUM_CLASS = 'symptom'

    @classmethod
    def get_symptoms_checksum(cls):
        checksum, created_ = Checksum.objects.get_or_create(
            name=SymptomChecksumManage.SYMPTOM_CHECKSUM_CLASS,
            defaults = dict(
                value=''
        ))
        return checksum

    @classmethod
    def get_symptoms_dict(cls):
        symptom_groups = []
        for symptomgroup in SymptomGroup.objects.filter(deprecated=False).order_by('pk'):
            orderered_dict = OrderedDict()
            orderered_dict['id'] = symptomgroup.pk
            orderered_dict['name'] = symptomgroup.name
            orderered_dict['parent_id'] = symptomgroup.parent.pk if symptomgroup.parent else None
            symptom_groups.append(orderered_dict)
        symptoms = []
        for symptom in Symptom.objects.filter(
                deprecated=False,
                group__deprecated=False,
            ).distinct().order_by('pk'):
            orderered_dict = OrderedDict()
            orderered_dict['id'] = symptom.pk
            orderered_dict['name'] = symptom.name
            orderered_dict['group_id'] = symptom.group.pk if symptom.group else None
            orderered_dict['order'] = symptom.order
            symptoms.append(orderered_dict)
        all_dict = OrderedDict()
        all_dict['symptom_groups'] = symptom_groups
        all_dict['symptoms'] = symptoms
        return all_dict

    @classmethod
    def compute_checksum(cls):
        checksum = SymptomChecksumManage.get_symptoms_checksum()
        all_dict = SymptomChecksumManage.get_symptoms_dict()
        all_str = json.dumps(all_dict, separators=(',', ':',), ensure_ascii=False)
        md5sum = hashlib.md5(all_str.encode('utf-8')).hexdigest()
        if checksum.value != md5sum:
            checksum.value = md5sum
            checksum.save()

class Checksum(models.Model):

    name = models.CharField(_("Класс"), max_length=255, unique=True, editable=False)
    value = models.CharField(_("Значение"), max_length=255, editable=False)

class SymptomGroup(models.Model):

    name = models.CharField(_("Название"), max_length=255, unique=True)
    parent = models.ForeignKey('contact.SymptomGroup', verbose_name=_("Родительская группа"),
                               on_delete=models.SET_NULL, null=True, blank=True)
    deprecated = models.BooleanField(_("Устарела"), default=False)
    class Meta:
        verbose_name = _("Группа симптомов")
        verbose_name_plural = _("Группы симптомов")
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        result = super(SymptomGroup, self).save(*args, **kwargs)
        SymptomChecksumManage.compute_checksum()
        return result

    def delete(self, *args, **kwargs):
        result = super(SymptomGroup, self).delete(*args, **kwargs)
        SymptomChecksumManage.compute_checksum()
        return result

class Symptom(models.Model):

    name = models.CharField(_("Название"), max_length=255, unique=True)
    group = models.ForeignKey(SymptomGroup, verbose_name=_("Группа"),
                               on_delete=models.PROTECT)
    order = models.IntegerField(_("Порядок следования"), null=True, default = None, blank=True)
    deprecated = models.BooleanField(_("Устарел"), default=False)

    class Meta:
        verbose_name = _("Cимптом")
        verbose_name_plural = _("Симптомы")
        ordering = ('name',)
        unique_together = ('group', 'order', )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        result = super(Symptom, self).save(*args, **kwargs)
        SymptomChecksumManage.compute_checksum()
        return result

    def delete(self, *args, **kwargs):
        result = super(Symptom, self).delete(*args, **kwargs)
        SymptomChecksumManage.compute_checksum()
        return result

class UserSymptom(BaseModelInsertTimestamp, GeoPointModel):

    incognitouser = models.ForeignKey('users.IncognitoUser',
                                      verbose_name=_("Пользователь инкогнито"),
                                      on_delete=models.CASCADE)

    symptom = models.ForeignKey(Symptom, verbose_name=_("Симптом"), on_delete=models.CASCADE)

    # От 0 до 29. Вычисляется от угла поворота луны к солнцу:
    # angle between the Moon and the Sun along the ecliptic как 360 град.,
    # экстраполированные в 30 лунных дней (1 такой день - 360/30 градусов)
    #
    moon_day = models.IntegerField(_("День лунного календаря"), db_index=True)

    # Поле timezone - число, получаемое, например, от строки по Московскому
    # часовому поясу: "+0300", этот же часовой пояс - по умолчанию.
    #
    timezone = models.IntegerField(_("Часовой пояс"), default=300)

    def save(self, *args, **kwargs):
        self.fill_insert_timestamp()
        if self.moon_day is None:
            self.moon_day = get_moon_day(self.insert_timestamp)
        return super(UserSymptom, self).save(*args, **kwargs)

class Wish(BaseModelInsertUpdateTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    text = models.TextField(verbose_name=_("Текст"), db_index=True)

    def data_dict(self):
        return dict(
        uuid=str(self.uuid),
        text=self.text,
        last_edit=self.update_timestamp,
    )

class Ability(BaseModelInsertUpdateTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    text = models.TextField(verbose_name=_("Текст"), db_index=True)

    def data_dict(self):
        return dict(
            uuid=str(self.uuid),
            text=self.text,
            last_edit=self.update_timestamp,
        )

class ApiAddOperationMixin(object):

    def add_operation(self,
        user_from,
        profile_to,
        operationtype_id,
        comment,
        insert_timestamp,
        tg_from_chat_id=None,
        tg_message_id=None,
    ):
        try:
            operationtype = OperationType.objects.get(pk=operationtype_id)
        except (ValueError, OperationType.DoesNotExist,):
            raise ServiceException('Неизвестный operation_type_id = %s' % operationtype_id)

        data = dict()
        update_timestamp = int(time.time())
        user_to = profile_to.user
        already_code = 'already'

        if operationtype_id == OperationType.THANK:
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    thanks_count=1,
            ))
            if not created_:
                currentstate.update_timestamp = update_timestamp
                currentstate.thanks_count += 1
                currentstate.save()

            data.update(currentstate=dict(
                thanks_count=currentstate.thanks_count,
                attitude=currentstate.attitude,
            ))
            profile_to.sum_thanks_count += 1
            profile_to.save()

        elif operationtype_id == OperationType.ACQ:
            attitude_previous = None
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    attitude=CurrentState.ACQ,
            ))
            if not created_:
                if not currentstate.is_reverse and currentstate.attitude == CurrentState.ACQ:
                    raise ServiceException(
                        'Вы уже знакомы с человеком',
                        already_code,
                    )
                if not currentstate.is_reverse:
                    attitude_previous = currentstate.attitude
                currentstate.update_timestamp = update_timestamp
                currentstate.is_reverse = False
                currentstate.attitude = CurrentState.ACQ
                currentstate.save()

            data.update(previousstate=dict(attitude=attitude_previous))
            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    attitude=CurrentState.ACQ,
            ))
            if not reverse_created and (reverse_cs.is_reverse or reverse_cs.attitude == None):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_reverse = True
                reverse_cs.attitude = CurrentState.ACQ
                reverse_cs.save()

            profile_to.recount_trust_fame()
            data.update(currentstate=dict(
                thanks_count=currentstate.thanks_count,
                attitude=currentstate.attitude,
            ))

        elif operationtype_id == OperationType.MISTRUST:
            attitude_previous = None
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    attitude=CurrentState.MISTRUST,
            ))
            if not created_:
                if not currentstate.is_reverse and currentstate.attitude == CurrentState.MISTRUST:
                    raise ServiceException(
                        'Вы уже не доверяете человеку',
                        already_code,
                    )
                if not currentstate.is_reverse:
                    attitude_previous = currentstate.attitude
                currentstate.update_timestamp = update_timestamp
                currentstate.is_reverse = False
                currentstate.attitude = CurrentState.MISTRUST
                currentstate.save()

            data.update(previousstate=dict(attitude=attitude_previous))
            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    attitude=CurrentState.MISTRUST,
            ))
            if not reverse_created and (reverse_cs.is_reverse or reverse_cs.attitude == None):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_reverse = True
                reverse_cs.attitude = CurrentState.MISTRUST
                reverse_cs.save()

            profile_to.recount_trust_fame()
            data.update(currentstate=dict(
                thanks_count=currentstate.thanks_count,
                attitude=currentstate.attitude,
            ))

        elif operationtype_id == OperationType.TRUST:
            attitude_previous = None
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    attitude=CurrentState.TRUST,
            ))
            if not created_:
                if not currentstate.is_reverse and currentstate.attitude == CurrentState.TRUST:
                    raise ServiceException(
                        'Вы уже доверяете человеку',
                        already_code,
                    )
                if not currentstate.is_reverse:
                    attitude_previous = currentstate.attitude
                currentstate.update_timestamp = update_timestamp
                currentstate.is_reverse = False
                currentstate.attitude = CurrentState.TRUST
                currentstate.save()

            data.update(previousstate=dict(attitude=attitude_previous))
            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    attitude=CurrentState.TRUST,
            ))
            if not reverse_created and (reverse_cs.is_reverse or reverse_cs.attitude == None):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_reverse = True
                reverse_cs.attitude = CurrentState.TRUST
                reverse_cs.save()

            profile_to.recount_trust_fame()
            data.update(currentstate=dict(
                thanks_count=currentstate.thanks_count,
                attitude=currentstate.attitude,
            ))

        elif operationtype_id == OperationType.TRUST_OR_THANK:
            attitude_previous = None
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    attitude=CurrentState.TRUST,
                    thanks_count=0,
            ))
            if not created_:
                if not currentstate.is_reverse:
                    attitude_previous = currentstate.attitude
                currentstate.update_timestamp = update_timestamp
                currentstate.is_reverse = False
                currentstate.attitude = CurrentState.TRUST
                if attitude_previous == CurrentState.TRUST:
                    currentstate.thanks_count += 1
                currentstate.save()

            data.update(previousstate=dict(attitude=attitude_previous))
            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_reverse=True,
                    attitude=CurrentState.TRUST,
            ))
            if not reverse_created and (reverse_cs.is_reverse or reverse_cs.attitude == None):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_reverse = True
                reverse_cs.attitude = CurrentState.TRUST
                reverse_cs.save()

            if attitude_previous == CurrentState.TRUST:
                profile_to.sum_thanks_count += 1
            profile_to.save()
            profile_to.recount_trust_fame()
            data.update(currentstate=dict(
                thanks_count=currentstate.thanks_count,
                attitude=currentstate.attitude,
            ))

        elif operationtype_id == OperationType.NULLIFY_ATTITUDE:
            err_message = 'Вы и так не знакомы с человеком'
            try:
                currentstate = CurrentState.objects.select_for_update().get(
                    user_from=user_from,
                    user_to=user_to,
                )
            except CurrentState.DoesNotExist:
                raise ServiceException(err_message, already_code)

            if currentstate.is_reverse:
                # то же что created
                raise ServiceException(err_message, already_code)
            elif currentstate.attitude == None:
                raise ServiceException(err_message, already_code)
            else:
                # TRUST, MISTRUST или ACQ
                data.update(previousstate=dict(attitude=currentstate.attitude))
                currentstate.update_timestamp = update_timestamp
                currentstate.attitude = None
                currentstate.save()

                CurrentState.objects.filter(
                    user_to=user_from,
                    user_from=user_to,
                    is_reverse=True,
                    attitude__isnull=False,
                ).update(attitude=None, update_timestamp=update_timestamp)

                profile_to.recount_trust_fame()
                data.update(currentstate=dict(
                    thanks_count=currentstate.thanks_count,
                    attitude=None,
                ))

        elif operationtype_id in (
                OperationType.FATHER, OperationType.MOTHER,
                OperationType.SET_FATHER, OperationType.SET_MOTHER,
             ):

            if operationtype_id in (OperationType.FATHER, OperationType.SET_FATHER,):
                is_father = True
                is_mother = False
            else:
                is_father = False
                is_mother = True
            do_set = operationtype_id in (OperationType.SET_FATHER, OperationType.SET_MOTHER,)

            q = Q(user_from=user_to, user_to=user_from, is_child=False)
            q &= Q(is_mother=True) | Q(is_father=True)
            try:
                CurrentState.objects.filter(q)[0]
                raise ServiceException('Два человека не могут быть оба родителями по отношению друг к другу')
            except IndexError:
                pass

            q_to = Q(user_from=user_from, is_child=False) & ~Q(user_to=user_to)
            if is_father:
                q = q_to & Q(is_father=True)
            else:
                q = q_to & Q(is_mother=True)
            if do_set:
                # При замене папы, если у человека уже есть другой папа, убираем это!
                # Аналогично если есть другая мама.
                #
                CurrentState.objects.filter(q).update(
                    is_father=False,
                    is_mother=False,
                    is_child=False,
                )
                q_to = Q(user_to=user_from, is_child=True) & ~Q(user_from=user_to)
                if is_father:
                    q = q_to & Q(is_father=True)
                else:
                    q = q_to & Q(is_mother=True)
                CurrentState.objects.filter(q).update(
                    is_father=False,
                    is_mother=False,
                    is_child=False,
                )
            else:
                try:
                    CurrentState.objects.filter(q)[0]
                    raise ServiceException('У человека уже есть %s' % ('папа' if is_father else 'мама'))
                except IndexError:
                    pass

            currentstate, created_ = CurrentState.objects.get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    is_father=is_father,
                    is_mother=is_mother,
                    is_child=False,
            ))
            if not created_:
                if not do_set and is_father and currentstate.is_father and not currentstate.is_child:
                    raise ServiceException('Такой папа уже задан', already_code)
                elif not do_set and is_mother and currentstate.is_mother and not currentstate.is_child:
                    raise ServiceException('Такая мама уже задана', already_code)
                else:
                    currentstate.update_timestamp = update_timestamp
                    currentstate.is_child = False
                    currentstate.is_father = is_father
                    currentstate.is_mother = is_mother
                    currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_child=True,
                    is_father=is_father,
                    is_mother=is_mother,
                    attitude=currentstate.attitude,
            ))
            if not reverse_created:
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_child = True
                reverse_cs.is_father = is_father
                reverse_cs.is_mother = is_mother
                reverse_cs.save()

        elif operationtype_id == OperationType.NOT_PARENT:
            q = Q(user_from=user_from, user_to=user_to, is_child=False)
            q &= Q(is_mother=True) | Q(is_father=True)
            try:
                currentstate = CurrentState.objects.get(q)
            except CurrentState.DoesNotExist:
                raise ServiceException('Здесь и так нет связи отношением потомок - родитель', already_code)

            currentstate.update_timestamp = update_timestamp
            currentstate.is_father = False
            currentstate.is_mother = False
            currentstate.save()

            CurrentState.objects.filter(
                user_to=user_from,
                user_from=user_to,
            ).update(
                is_father=False,
                is_mother=False,
                is_child=False,
                update_timestamp=update_timestamp,
            )

        elif operationtype_id == OperationType.SET_SYMPA:
            currentstate, created_ = CurrentState.objects.select_for_update().get_or_create(
                user_from=user_from,
                user_to=user_to,
                defaults=dict(
                    is_sympa=True,
            ))
            if not created_:
                if not currentstate.is_sympa_reverse and currentstate.is_sympa == True:
                    # Уже установлена симпатия
                    pass
                else:
                    currentstate.update_timestamp = update_timestamp
                    currentstate.is_sympa_reverse = False
                    currentstate.is_sympa = True
                    currentstate.save()

            reverse_cs, reverse_created = CurrentState.objects.select_for_update().get_or_create(
                user_to=user_from,
                user_from=user_to,
                defaults=dict(
                    is_sympa_reverse=True,
                    is_sympa=True,
            ))
            if not reverse_created and (reverse_cs.is_sympa_reverse or reverse_cs.is_sympa == False):
                reverse_cs.update_timestamp = update_timestamp
                reverse_cs.is_sympa_reverse = True
                reverse_cs.is_sympa = True
                reverse_cs.save()

        elif operationtype_id == OperationType.REVOKE_SYMPA:
            q = Q(user_from=user_from, user_to=user_to, is_sympa=True)
            try:
                currentstate = CurrentState.objects.get(user_from=user_from, user_to=user_to, is_sympa=True)
            except CurrentState.DoesNotExist:
                pass
            else:
                currentstate.is_sympa = False
                currentstate.update_timestamp = update_timestamp
                currentstate.save()

            CurrentState.objects.filter(
                user_to=user_from,
                user_from=user_to,
                is_sympa_reverse=True,
                is_sympa=True,
            ).update(
                is_sympa=False,
                is_sympa_reverse=False,
                update_timestamp=update_timestamp,
            )

        else:
            raise ServiceException('Неизвестный operation_type_id')

        journal = Journal.objects.create(
            user_from=user_from,
            user_to=user_to,
            operationtype=operationtype,
            insert_timestamp=insert_timestamp,
            comment=comment,
        )
        data.update(journal_id=journal.pk)

        if tg_message_id and tg_from_chat_id:
            TgJournal.objects.create(
                journal=journal,
                from_chat_id=tg_from_chat_id,
                message_id=tg_message_id,
            )

        return data
