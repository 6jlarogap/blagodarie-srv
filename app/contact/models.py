import time, datetime, json, hashlib, re
import numpy as np
import os, uuid
from collections import OrderedDict
import matplotlib as mpl
if os.environ.get('DISPLAY','') == '':
    mpl.use('Agg')
from matplotlib import colors as mcolors
import matplotlib.pyplot as plt

import base64
from io import BytesIO

from app.utils import get_moon_day

from django.conf import settings
from django.db import models, connection
from django.utils.translation import ugettext_lazy as _
from django.db.models.query_utils import Q

from django.contrib.auth.models import User

# Здесь поля insert_timestamp, update_timestamp. В ряде моделей требуется
# и то, и другое, в иных таблицах только один из этих timestamp.
#
# Для таблицы auth_user требуется только insert_timestamp, это можно взять
# из ее поля date_joined (timestamp with time zone)
#
from app.models import BaseModelInsertTimestamp, BaseModelInsertUpdateTimestamp, GeoPointModel

from app.utils import dictfetchall

from users.models import IncognitoUser, Profile

class KeyType(models.Model):

    CREDIT_CARD_ID = 4

    title = models.CharField(_("Код ключа"), max_length=255, unique=True)

class OperationType(models.Model):

    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_TRUST = 4

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
    is_trust = models.NullBooleanField(_("Доверие"), default=None)

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

class Key(BaseModelInsertTimestamp):

    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), null=True, on_delete=models.CASCADE)
    type = models.ForeignKey(KeyType, on_delete=models.CASCADE)
    value = models.CharField(_("Значение"), max_length=255)

    class Meta:
        unique_together = ('type', 'value', )

    def __str__(self):
        return '(id=%s) type=%s (%s), value=%s' % (
            self.pk, self.type.title, self.type.pk, self.value
        )

class UserKey(BaseModelInsertTimestamp):

    user = models.ForeignKey('auth.User', verbose_name=_("Пользователь"), on_delete=models.CASCADE)
    key = models.ForeignKey(Key, verbose_name=_("Ключ"), on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'key')

class Like(BaseModelInsertUpdateTimestamp):

    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    cancel_timestamp = models.BigIntegerField(_("Когда был отменен лайк"), null=True)

class LikeKey(BaseModelInsertTimestamp):

    like = models.ForeignKey(Like, verbose_name=_("Лайк"), on_delete=models.CASCADE)
    key = models.ForeignKey(Key, verbose_name=_("Ключ"), on_delete=models.CASCADE)

    class Meta:
        unique_together = ('like', 'key')

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
    text = models.TextField(verbose_name=_("Текст"))

class Ability(BaseModelInsertUpdateTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    text = models.TextField(verbose_name=_("Текст"))

class LogLike(models.Model):
    """
    Статистика
    """

    dt = models.DateField(_("Дата"), unique=True)
    users = models.PositiveIntegerField(_("Участники"), default=0)
    likes = models.PositiveIntegerField(_("Благодарности"), default=0)
    keys = models.PositiveIntegerField(_("Ключи"), default=0)

    # За сколько часов берем статистику
    #
    LAST_STAT_HOURS = 48

    # Промежуток между соседними тиками на гистограмме
    #
    HIST_HOURS_INERVAL = 2

    @classmethod
    def get_stats(cls, request=None, *args, **kwargs):

        if not kwargs.get('only'):
            return dict(
                users=User.objects.filter(is_superuser=False).count(),
                keys=Key.objects.all().count(),
                likes=Like.objects.all().count(),
            )

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

            # Вернуть:
            #
            # {
            #   "users": [
            #       {
            #           "id": "8b0cc02d-b6bb-4444-ae40-1b3a00aa9499",
            #           "first_name": "Иван",
            #           "last_name": "Иванов",
            #           "photo": "..."
            #       },
            #       ...
            # ],
            #   "current_states": [
            #       {
            #           "source": "8b0cc02d-b6bb-4444-ae40-1b3a00aa9499",
            #           "target": "a8fc8a5b-5687-43e6-b0e6-a043750c2ede",
            #           "thanks_count": 1,
            #           "is_trust": true
            #       },
            #       ...
            #   ]
            # }

            users = []
            user_pks = []
            if request and request.user.is_authenticated:
                user = request.user
                profile = user.profile
                users.append(dict(
                    uuid=profile.uuid,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    photo = profile.choose_photo(),
                ))
                user_pks.append(user.pk)

            connections = []
            for cs in CurrentState.objects.filter(
                        user_to__isnull=False,
                        is_reverse=False,
                        is_trust__isnull=False,
                    ).select_related(
                    'user_from', 'user_to',
                    'user_from__profile', 'user_to__profile',
                ):
                connections.append({
                    'source': cs.user_from.profile.uuid,
                    'target': cs.user_to.profile.uuid,
                    'thanks_count': cs.thanks_count,
                    'is_trust': cs.is_trust,
                })
                user = cs.user_from
                if user.pk not in user_pks:
                    profile = user.profile
                    users.append(dict(
                        uuid=profile.uuid,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        photo = profile.choose_photo(),
                    ))
                    user_pks.append(user.pk)
                user = cs.user_to
                if user.pk not in user_pks:
                    profile = user.profile
                    users.append(dict(
                        uuid=profile.uuid,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        photo = profile.choose_photo(),
                    ))
                    user_pks.append(user.pk)

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
        time_1st = time_current - LogLike.LAST_STAT_HOURS * 3600
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
                    symptoms = dictfetchall(cursor)
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
                    symptoms = dictfetchall(cursor)
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
                    symptoms = dictfetchall(cursor)
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
                    m = dictfetchall(cursor)
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
                    m = dictfetchall(cursor)
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

        if kwargs.get('only') == 'symptoms_hist':

            # Возвращает json:
            # Картинка с гистограммой симптомов за два дня
            # Картинка с легендой для гистограммы
            # Точки для карты ощущений за два дня
            # Координаты центра для карты
            # График симптомов с начала текущего лунного месяца

            # Можно было бы отдавать разные картинки в разных
            # методах, но оно то одну картинку не заполнит, то другую

            hist = ''
            legend = ''
            points = []

            # Если точек нет, то пусть будут координаты Москвы
            # Что не показывался в этом случае Атлантический океан
            #
            lat_avg = 55.7522200
            lng_avg = 37.6155600

            moon_days_fig = ''
            moon_hour_fig = ''

            colors = [mcolor for mcolor in mcolors.CSS4_COLORS]
            colors.sort()

            symptom_ids = dict()
            symptom_names = dict()
            n = 0
            for symptom in Symptom.objects.all().order_by('pk'):
                symptom_ids[symptom.pk] = n
                symptom_names[n] = symptom.name
                n += 1

            while len(colors) < len(symptom_ids):
                colors += colors
            bins = []
            t = time_1st
            while t <= time_last:
                bins.append(t)
                t += 3600

            tick_times = []
            for i, t in enumerate(bins):
                hour = datetime.datetime.fromtimestamp(t).hour
                if i == 0 or i == len(bins) - 1:
                    tick_times.append(t)
                elif hour % LogLike.HIST_HOURS_INERVAL == 0 and \
                     t - time_1st < LogLike.HIST_HOURS_INERVAL * 3600:
                    continue
                elif hour % LogLike.HIST_HOURS_INERVAL == 0 and \
                     time_last - t < LogLike.HIST_HOURS_INERVAL * 3600:
                    continue
                elif hour % LogLike.HIST_HOURS_INERVAL == 0:
                    tick_times.append(t)
            tick_labels = []
            cur_day = 0
            for i, t in enumerate(tick_times):
                dt = datetime.datetime.fromtimestamp(t)
                if dt.day != cur_day:
                    tick_labels.append(dt.strftime('%d.%m %H:'))
                    cur_day = dt.day
                elif i == len(tick_times)-1:
                    tick_labels.append(dt.strftime('%d.%m %H:'))
                else:
                    tick_labels.append(dt.strftime('%H:'))

            ss = [[] for i in symptom_ids]
            points = []
            lat_sum = 0
            lng_sum = 0
            got_symptom = dict()

            q = Q(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                )
            if selected_ids_str:
                q &= Q(symptom__pk__in=selected_ids_list)
            if incognitouser:
                q &= Q(incognitouser=incognitouser)
            for usersymptom in UserSymptom.objects.filter(
                    q
                ).select_related('symptom').order_by('-insert_timestamp'):

                ss[symptom_ids[usersymptom.symptom.pk]].append(usersymptom.insert_timestamp)
                #if usersymptom.latitude is not None and usersymptom.longitude is not None:
                    #got_symptom_key = None
                    #got_symptom_key = '%s-%s' % (
                        #usersymptom.incognitouser.pk, usersymptom.symptom.pk,
                    #)
                    #if not got_symptom.get(got_symptom_key):
                        #if got_symptom_key:
                            #got_symptom[got_symptom_key] = 1
                        #points.append([
                            #usersymptom.latitude,
                            #usersymptom.longitude,
                            #usersymptom.symptom.name,
                        #])
                        #lat_sum += usersymptom.latitude
                        #lng_sum += usersymptom.longitude

            if(any(ss)):
                if (points):
                    lat_avg = lat_sum / len(points)
                    lng_avg = lng_sum / len(points)
                fig, ax = plt.subplots()
                ax.hist(ss, bins, stacked=True, edgecolor='black', color=colors[0:len(symptom_ids)])
                fig.set_figwidth(10)

                ax.set_xticks(tick_times)
                ax.set_xticklabels(tick_labels, rotation=15, rotation_mode="anchor", ha="right")

                yint = []
                locs, labels = plt.yticks()
                for each in locs:
                    if each == int(each):
                        yint.append(each)
                plt.yticks(yint)

                tmpfile = BytesIO()
                plt.savefig(tmpfile, format='png')
                hist = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
                plt.close()

                symptoms_total = 0
                for s in ss:
                    symptoms_total += len(s)
                legends = []
                for i, s in enumerate(ss):
                    percent = round((len(s)/symptoms_total)*100, 2)
                    legends.append(dict(
                        symptom_name=symptom_names[i],
                        percent=percent,
                        color=colors[i],
                    ))
                legends.sort(key = lambda d: d['percent'])
                
                data_values = []
                label_names = []
                legend_colors = []
                for l in legends:
                    data_values.append(l['percent'])
                    label_names.append('%s (%s%%)' % (l['symptom_name'], l['percent'], ))
                    legend_colors.append(l['color'])

                handles = []
                fig, ax = plt.subplots()
                for i in range(len(data_values)):
                    h = ax.barh(i, data_values[i],
                                height = 0.2, color = legend_colors[i], alpha = 1.0,
                                zorder = 2, label=label_names[i],
                    )
                    handles.append(h)
                legend = plt.legend(handles=handles[::-1], frameon=False, fontsize='xx-large')
                fig.set_figwidth(30)
                fig.set_figheight(80)

                fig  = legend.figure
                fig.canvas.draw()
                bbox  = legend.get_window_extent().transformed(fig.dpi_scale_trans.inverted())

                tmpfile = BytesIO()
                fig.savefig(tmpfile, format='png', dpi="figure", bbox_inches=bbox)
                legend = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
                plt.close()

            # Лунная диагамма
            # Выбираем количества симптомов по по каждому лунному дню
            # за всё время наблюдений. Если больше текущего лунного дня,
            # то это прогноз
            #
            
            current_moon_day = get_moon_day(time_current)
            moon_fact = [[0 for j in range(30)] for i in range(len(symptom_ids))]
            moon_cast = [[0 for j in range(30)] for i in range(len(symptom_ids))]

            moon_hour = [[0 for j in range(30)] for i in range(24)]

            if selected_ids_str != '()':
                req_str = """
                    SELECT
                        moon_day,
                        symptom_id,
                        Count(symptom_id) as count
                    FROM
                        contact_usersymptom
                    WHERE
                        moon_day <= %(current_moon_day)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        moon_day,
                        symptom_id
                """ % dict(
                    current_moon_day=current_moon_day,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = dictfetchall(cursor)
                for r in m:
                    moon_fact [symptom_ids[ r['symptom_id']] ] [r['moon_day']] = r['count']

                req_str = """
                    SELECT
                        moon_day,
                        ((insert_timestamp + timezone * 3600/100 + (timezone %% 100) * 60)/3600) %% 24 as hour,
                        symptom_id,
                        Count(DISTINCT id) as count
                    FROM
                        contact_usersymptom
                    WHERE
                        moon_day <= %(current_moon_day)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        moon_day,
                        hour,
                        symptom_id
                    ORDER BY
                        count
                    DESC
                """ % dict(
                    current_moon_day=current_moon_day,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = dictfetchall(cursor)
                for r in m:
                    if not moon_hour [r['hour']] [r['moon_day']]:
                        moon_hour [r['hour']] [r['moon_day']] = []
                    moon_hour [r['hour']] [r['moon_day']].append(dict(
                        symptom_id=r['symptom_id'],
                        count=r['count']
                    ))

            if (selected_ids_str != '()') and (current_moon_day < 29):
                req_str = """
                    SELECT
                        symptom_id,
                        moon_day,
                        Count(symptom_id) as count
                    FROM
                        contact_usersymptom
                    WHERE
                        moon_day > %(current_moon_day)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        moon_day,
                        symptom_id
                """ % dict(
                    current_moon_day=current_moon_day,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = dictfetchall(cursor)
                for r in m:
                    moon_cast [symptom_ids[ r['symptom_id']] ] [r['moon_day']] = r['count']

                req_str = """
                    SELECT
                        moon_day,
                        ((insert_timestamp + timezone * 3600/100 + (timezone %% 100) * 60)/3600) %% 24 as hour,
                        symptom_id,
                        Count(DISTINCT id) as count
                    FROM
                        contact_usersymptom
                    WHERE
                        moon_day > %(current_moon_day)s
                        %(selected_ids_where)s
                        %(incognitouser_where)s
                    GROUP BY
                        moon_day,
                        hour,
                        symptom_id
                    ORDER BY
                        count
                    DESC
                """ % dict(
                    current_moon_day=current_moon_day,
                    selected_ids_where=selected_ids_where,
                    incognitouser_where=incognitouser_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = dictfetchall(cursor)
                for r in m:
                    if r['count']:
                        if not moon_hour [r['hour']] [r['moon_day']]:
                            moon_hour [r['hour']] [r['moon_day']] = []
                        moon_hour [r['hour']] [r['moon_day']].append(dict(
                            symptom_id=r['symptom_id'],
                            count=r['count']
                        ))

            moon_phases = (

                # new moon (black circle)

                '\u25CF', '\u25CF', '\u25CF', '\u25CF', '\u25CF', '\u25CF', '\u25CF',

                # 1-st quarter (circle with left half black)

                '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0',

                # full moon (white circle)

                '\u25CB', '\u25CB', '\u25CB', '\u25CB', '\u25CB', '\u25CB', '\u25CB',

                # 3-rd quarter (circle with right half black)

                '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1',
            )

            ind = range(30)
            days = [str(i+1) for i in range(30)]
            days[current_moon_day] = '*\n%s' % datetime.datetime.fromtimestamp(time_current).strftime('%d.%m')
            bar_width = 0.5

            fig, ax1 = plt.subplots()
            fig.set_figwidth(10)

            bottom = [ 0 for j in range(len(moon_fact[0]))]
            for i, s in enumerate(moon_fact):
                ax1.bar(
                    ind,
                    moon_fact[i],
                    width=bar_width,
                    bottom=bottom,
                    color=colors[i],
                    tick_label=days
                )
                for j, b in enumerate(bottom):
                    bottom[j] += moon_fact[i][j]

            ax2 = ax1.twiny()
            bottom = [ 0 for j in range(len(moon_cast[0]))]
            for i, s in enumerate(moon_cast):
                ax2.bar(
                    ind,
                    moon_cast[i],
                    width=bar_width,
                    bottom=bottom,
                    color=colors[i],
                    tick_label=moon_phases,
                    alpha=0.35,
                )
                for j, b in enumerate(bottom):
                    bottom[j] += moon_cast[i][j]

            yint = []
            locs, labels = plt.yticks()
            for each in locs:
                if int(each) == each:
                    yint.append(int(each))
            plt.yticks(yint)

            ax1.tick_params(bottom=False, top=True, left=True, right=True)
            ax1.tick_params(labelbottom=True, labeltop=False, labelleft=True, labelright=True)
            if current_moon_day < 29:
                ax1.set_ylabel('Прогноз')
                ax1.yaxis.set_label_coords(0.99, 0.5)

            got_any = False
            for i, s in enumerate(moon_cast):
                for j, y in enumerate(s):
                    if y:
                        got_any = True
                        break
                if got_any:
                    break
            if not got_any:
                for i, s in enumerate(moon_fact):
                    for j, y in enumerate(s):
                        if y:
                            got_any = True
                            break
                    if got_any:
                        break
            if not got_any:
                plt.yticks(range(0, 51, 10))

            tmpfile = BytesIO()
            plt.savefig(tmpfile, format='png')
            moon_days_fig = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
            plt.close()

            x = range(30)
            y1_dummy = [24] * 30
            y2_dummy = [0] * 30
            s_no_size = [0 for r in x]

            fig, ax1 = plt.subplots()
            fig.set_figwidth(10)
            fig.set_figheight(9)

            for i, hour in enumerate(moon_hour):
                for j, lst in enumerate(hour):
                    if not lst:
                        continue
                    if len(lst) == 1:
                        alpha = 1.0 if j <= current_moon_day else 0.7
                        ax1.scatter(
                            j,
                            i + 0.5,
                            s=30,
                            c=colors[symptom_ids[lst[0]['symptom_id']]],
                            alpha=alpha
                        )
                    else:
                        alpha = 0.7 if j <= current_moon_day else 0.3
                        step = 0.5 / len(lst)
                        y_current = i + 0.70
                        for k, item in enumerate(lst):
                            ax1.scatter(
                                j,
                                y_current,
                                s=item['count']*30,
                                c=colors[symptom_ids[item['symptom_id']]],
                                alpha=alpha
                            )
                            y_current -= step
            ax1.set_xticks(x)
            ax1.set_xticklabels(days)
            ax1.set_yticks(range(25))
            ax1.set_yticklabels([str(i) for i in range(24)] + [ "0"])

            ax1.tick_params(bottom=False, top=True, left=True, right=True)
            ax1.tick_params(labelbottom=True, labeltop=False, labelleft=True, labelright=True)
            if current_moon_day < 29:
                ax1.set_ylabel('Прогноз')
                ax1.yaxis.set_label_coords(0.99, 0.5)

            ax2 = ax1.twiny()
            ax2.scatter(x,y1_dummy,s=s_no_size)
            ax2.scatter(x,y2_dummy,s=s_no_size)
            ax2.set_xticks(x)
            ax2.set_xticklabels(moon_phases)
            ax2.set_yticks(range(25))
            ax2.set_yticklabels([str(i) for i in range(24)] + [ "0"])

            tmpfile = BytesIO()
            plt.savefig(tmpfile, format='png')
            moon_hour_fig = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
            plt.close()

            return dict(
                hist=hist,
                legend=legend,
                points=points,
                lat_avg=lat_avg,
                lng_avg=lng_avg,
                moon_days_fig=moon_days_fig,
                moon_hour_fig=moon_hour_fig,
            )

        return dict()
