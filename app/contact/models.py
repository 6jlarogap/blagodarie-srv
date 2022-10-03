import time, datetime, json, hashlib, re
import os, uuid
from collections import OrderedDict

from app.utils import get_moon_day

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
    NULLIFY_TRUST = 4
    TRUST_AND_THANK = 5
    FATHER = 6
    NOT_PARENT = 7
    MOTHER = 8
    SET_FATHER = 9
    SET_MOTHER = 10

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

class TgJournal(models.Model):
    """
    Ссылки на сообщения телеграма при благодарностях и др. действиях
    """
    journal = models.ForeignKey(Journal, verbose_name=_("Журнал"), on_delete=models.CASCADE)
    from_chat_id = models.BigIntegerField(_("Chat Id"),)
    message_id = models.BigIntegerField(_("Message Id"),)

class TgMessageJournal(BaseModelInsertTimestamp):
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

    def data_dict(self):

        def user_dict(user):
            return {
                'id': user.id,
                'uuid': str(user.profile.uuid),
                'first_name': user.first_name,
            }

        return dict(
            timestamp=self.insert_timestamp,
            user_from=user_dict(self.user_from),
            user_to=user_dict(self.user_to),
            user_to_delivered=user_dict(self.user_to_delivered) if self.user_to_delivered else None,
            from_chat_id=self.from_chat_id,
            message_id=self.message_id,
        )

class CurrentState(BaseModelInsertUpdateTimestamp):

    user_from = models.ForeignKey('auth.User',
                    verbose_name=_("От кого"), on_delete=models.CASCADE,
                    db_index=True,
                    related_name='currentstate_user_from_set')
    user_to = models.ForeignKey('auth.User',
                    verbose_name=_("Кому"), on_delete=models.CASCADE, null=True,
                    db_index=True,
                    related_name='currentstate_user_to_set')
    anytext = models.ForeignKey(AnyText,
                    verbose_name=_("Текст"), on_delete=models.CASCADE, null=True)
    thanks_count = models.PositiveIntegerField(_("Число благодарностей"), default=0)
    is_trust = models.BooleanField(_("Доверие"), default=None, null=True)

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
    #   thanks_count, is_trust: из записи, где user_from=1, user_to=2
    #
    #   Если же 2-й таки отблагодарит 1-го, то is_reverse станет False,
    #   а thanks_count, is_trust примут действительные значения:
    #   числа благодарностей 2-го 1-му и доверия
    #
    is_reverse = models.BooleanField(_("Обратное отношение"), default=False)

    def data_dict(self, show_parent=False, show_trust=False):
        result = dict(
            source=self.user_from.profile.uuid,
            target=self.user_to.profile.uuid,
        )
        if show_trust:
            result.update(dict(
                thanks_count=self.thanks_count,
                is_trust=self.is_trust,
            ))
        if show_parent:
            result.update(dict(
                is_father=self.is_father,
                is_mother=self.is_mother,
            ))
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
