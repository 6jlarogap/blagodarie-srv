import time, datetime, json, hashlib, re
import os, uuid
from collections import OrderedDict

from app.utils import get_moon_day

from django.conf import settings
from django.db import models, connection
from django.utils.translation import gettext_lazy as _
from django.db.models.query_utils import Q

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

    title = models.CharField(_("Код ключа"), max_length=255, unique=True)

class OperationType(models.Model):

    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_TRUST = 4
    TRUST_AND_THANK = 5
    PARENT = 6
    NOT_PARENT = 7

    title = models.CharField(_("Тип операции"), max_length=255, unique=True)

class AnyText(BaseModelInsertTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    text = models.CharField(_("Значение"), max_length=2048, unique=True, db_index=True)
    fame = models.PositiveIntegerField(_("Известность"), default=0)
    sum_thanks_count = models.PositiveIntegerField(_("Число благодарностей"), default=0)
    trust_count = models.PositiveIntegerField(_("Число оказанных доверий"), default=0)
    mistrust_count = models.PositiveIntegerField(_("Число утрат доверия"), default=0)

class Journal(BaseModelInsertTimestamp):

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
    is_parent = models.BooleanField(_("Родитель"), default=False, db_index=True)
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

    class Meta:
        unique_together = (
            ('user_from', 'user_to', ),
            ('user_from', 'anytext', ),
        )

# TODO Drop this table

class TemplateTmp1(models.Model):
    """
    Для поиска связей пользователя рекурсивно
    """
    level = models.IntegerField(blank=True, null=True)
    user_from_id = models.IntegerField(blank=True, null=True)
    user_to_id = models.IntegerField(blank=True, null=True)
    thanks_count = models.IntegerField(blank=True, null=True)
    is_trust = models.BooleanField(blank=True, null=True)
    is_reverse = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'template_tmp1'

class TemplateTmpParent(models.Model):
    """
    Для поиска связей пользователя рекурсивно
    """
    level = models.IntegerField(blank=True, null=True)
    user_from_id = models.IntegerField(blank=True, null=True)
    user_to_id = models.IntegerField(blank=True, null=True)
    thanks_count = models.IntegerField(blank=True, null=True)
    is_trust = models.BooleanField(blank=True, null=True)
    is_parent = models.BooleanField(blank=True, null=True)
    is_child = models.BooleanField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'template_tmp_parent'

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

class Ability(BaseModelInsertUpdateTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    text = models.TextField(verbose_name=_("Текст"), db_index=True)
