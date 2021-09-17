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
from app.models import BaseModelInsertTimestamp, BaseModelInsertUpdateTimestamp, GeoPointModel

from app.utils import dictfetchall

from users.models import IncognitoUser, Profile

class KeyType(models.Model):

    LINK_ID = 5

    title = models.CharField(_("Код ключа"), max_length=255, unique=True)

class OperationType(models.Model):

    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_TRUST = 4
    TRUST_AND_THANK = 5

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
    value = models.CharField(_("Значение"), max_length=255, db_index=True)

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
    text = models.TextField(verbose_name=_("Текст"), db_index=True)

class Ability(BaseModelInsertUpdateTimestamp):

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    text = models.TextField(verbose_name=_("Текст"), db_index=True)

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

            # Возвращает:
            #   без параметров:
            #       список всех пользователей, и связи,
            #       где не обнулено доверие (currenstate.is_trust is not null).
            #   с параметром query:
            #       список всех пользователей у которых в
            #           имени или
            #           фамилии или
            #           возможностях или
            #           ключах или
            #           желаниях
            #       есть query, и их связи,
            #       где не обнулено доверие (currenstate.is_trust is not null).
            #       В списке пользователей найденные имеют filtered == true,
            #       на front-end они выделяются, а связи,
            #       не подпадающие под фильтр query: filtered == false.
            #       В любом случае возвращаются в массиве users еще
            #       данные пользователя, если он авторизовался.
            #   список выдается по страницам найденных (или всех) пользователей,
            #   в порядке убывания даты регистрации пользователя,
            #   начало страницы -- параметр from (нумерация с 0), по умолчанию 0
            #   сколько на странице -- параметр number, по умолчанию 50
            #   с параметром count:
            #       число пользователей, всех или найденных по фильтру query

            q_users = Q(is_superuser=False)
            query = request and request.GET.get('query')
            if query:
                q_users &= \
                    Q(last_name__icontains=query) | \
                    Q(first_name__icontains=query) | \
                    Q(wish__text__icontains=query) | \
                    Q(ability__text__icontains=query) | \
                    Q(key__value__icontains=query)
            users_selected = User.objects.filter(q_users).distinct()

            count = request and request.GET.get('count')
            if count:
                return dict(count=users_selected.count())

            users_selected = users_selected.select_related('profile', 'profile__ability')
            users = []
            user_pks = []
            user_filtered_pks = []
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
                d = dict(
                    uuid=profile.uuid,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    photo = profile.choose_photo(),
                    filtered=True,
                    is_active=user.is_active,
                    latitude=profile.latitude,
                    longitude=profile.longitude,
                    ability=profile.ability and profile.ability.text or None,
                )
                users.append(d)
                user_filtered_pks.append(user.pk)
                user_pks.append(user.pk)

            connections = []
            q_connections = Q(
                is_reverse=False,
                is_trust__isnull=False,
                user_to__isnull=False,
            )
            q_connections &= Q(user_to__pk__in=user_filtered_pks) | Q(user_from__pk__in=user_filtered_pks)
            for cs in CurrentState.objects.filter(q_connections).select_related(
                    'user_from__profile', 'user_to__profile',
                    'user_from__profile__ability', 'user_to__profile__ability',
                ).distinct():
                connections.append({
                    'source': cs.user_from.profile.uuid,
                    'target': cs.user_to.profile.uuid,
                    'thanks_count': cs.thanks_count,
                    'is_trust': cs.is_trust,
                })
                if cs.user_to.pk not in user_pks:
                    user = cs.user_to
                    profile = user.profile
                    d = dict(
                        uuid=profile.uuid,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        photo = profile.choose_photo(),
                        filtered=False,
                        is_active=user.is_active,
                        latitude=profile.latitude,
                        longitude=profile.longitude,
                        ability=profile.ability and profile.ability.text or None,
                    )
                    users.append(d)
                    user_pks.append(user.pk)
                if cs.user_from.pk not in user_pks:
                    user = cs.user_from
                    profile = user.profile
                    d = dict(
                        uuid=profile.uuid,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        photo = profile.choose_photo(),
                        filtered=False,
                        is_active=user.is_active,
                        latitude=profile.latitude,
                        longitude=profile.longitude,
                        ability=profile.ability and profile.ability.text or None,
                    )
                    users.append(d)
                    user_pks.append(user.pk)

            if request and request.user and request.user.is_authenticated:
                if request.user.pk not in user_pks:
                    user = request.user
                    profile = user.profile
                    d = dict(
                        uuid=profile.uuid,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        photo = profile.choose_photo(),
                        filtered=False,
                        is_active=user.is_active,
                        ability=profile.ability and profile.ability.text or None,
                    )
                    users.append(d)

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

        return dict()
