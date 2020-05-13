import time, datetime, json, hashlib, re
import numpy as np
import os
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

class KeyType(models.Model):

    title = models.CharField(_("Код ключа"), max_length=255, unique=True)

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

    # TODO: Поле user удалить, как там будут все значения is Null.
    #       При этом:
    #           - удалить /api/addusersymptom
    #           - в /api/add_user_symptom убрать обнуление этого поля
    #           - поле incognito_id: убрать null=True
    #           - обнулить разработческую б.д.
    #
    user = models.ForeignKey('auth.User', verbose_name=_("Пользователь"),
                             null=True, on_delete=models.CASCADE)
    incognito_id = models.CharField(_("Идентификатор инкогнито"),
                                    max_length=36, null=True, db_index=True)

    symptom = models.ForeignKey(Symptom, verbose_name=_("Симптом"), on_delete=models.CASCADE)

    # От 0 до 29. Вычисляется от угла поворота луны к солнцу:
    # angle between the Moon and the Sun along the ecliptic как 360 град.,
    # экстраполированные в 30 лунных дней (1 такой день - 360/30 градусов)
    #
    moon_day = models.IntegerField(_("День лунного календаря"), null=True, db_index=True)

    # Поле timezone - число, получаемое, например, от строки по Московскому
    # часовому поясу: "+0300", этот же часовой пояс - по умолчанию.
    #
    timezone = models.IntegerField(_("Часовой пояс"), default=300)

    def save(self, *args, **kwargs):
        self.fill_insert_timestamp()
        if self.moon_day is None:
            self.moon_day = get_moon_day(self.insert_timestamp)
        return super(UserSymptom, self).save(*args, **kwargs)

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

        time_current = int(time.time())
        time_last = int(((time_current + 3599) / 3600)) * 3600
        time_1st = time_current - LogLike.LAST_STAT_HOURS * 3600
        time_1st = int(time_1st / 3600) * 3600

        if kwargs.get('only') == 'users':
            # Вернуть число пользователей
            # и симтомов
            #
            users = UserSymptom.objects.all().distinct('incognito_id').count()
            return dict(
                users=users,
                symptoms=UserSymptom.objects.filter(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                ).count(),
            )

        if kwargs.get('only') == 'symptoms_names':
            data = [
                {
                    'id': str(symptom.pk),
                    'name': symptom.name,
                }
                for symptom in Symptom.objects.all().order_by('name')
            ]
            return data

        selected_ids_str = request.GET.get('selected_ids_str', '')
        # Проверим, что пришло

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
        if selected_ids_str:
            selected_ids_where = ' AND symptom_id IN %s ' % selected_ids_str

        if kwargs.get('only') == 'symptoms':
            # Возвращает json:
            #   {
            #       "titles": [
            #           "Пользователи (<число с симптомами за LAST_STAT_HOURS>, <число с симптомами за 24ч>)",
            #           "симптом1 (<за LAST_STAT_HOURS>, <за 24 HOURS>)",
            #           ...
            #           "симптомN (<за LAST_STAT_HOURS>, <за 24 HOURS>)",
            #       ],
            #       "counts_all": [
            #           <число пользователей с симптомами за LAST_STAT_HOURS>,
            #           "<за LAST_STAT_HOURS симптомов1>",
            #           ...
            #           "<за LAST_STAT_HOURS симптомовN>"
            #       ],
            #       "counts_last": [
            #           <пользователей за LAST_STAT_HOURS>,
            #           "<за 24 HOURS симптомов1>",
            #           ...
            #           "<за 24 HOURS симптомовN>"
            #       ],
            #   }
            #

            time_24h = time_current - 24 * 3600
            time_24h = int(time_24h / 3600) * 3600

            # Ниже count ... _all - это таки за последние 48 часов
            #
            q = Q(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                )
            if selected_ids_str:
                q &= Q(symptom__pk__in=selected_ids_list)
            count_users_all = UserSymptom.objects.filter(q).distinct('incognito_id').count()

            q = Q(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_24h,
                )
            if selected_ids_str:
                q &= Q(symptom__pk__in=selected_ids_list)
            count_users_last = UserSymptom.objects.filter(q).distinct('incognito_id').count()

            data = dict(
                titles=[
                    'Пользователи (%s, %s)' % (count_users_all, count_users_last)
                ],
                counts_last=[
                    count_users_last,
                ],
                counts_all=[
                    count_users_all,
                ]
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
                        insert_timestamp < %(time_last)s AND
                        insert_timestamp >= %(time_1st)s
                        %(selected_ids_where)s
                    GROUP BY
                        name
                    ORDER BY
                        count
                """ % dict(
                    time_last=time_last,
                    time_1st=time_1st,
                    selected_ids_where=selected_ids_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    symptoms = dictfetchall(cursor)
                for symptom in symptoms:
                    s_dict[symptom['name']] = dict(
                        count_all=symptom['count'],
                    )
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
                    GROUP BY
                        name
                    ORDER BY
                        count
                """ % dict(
                    time_last=time_last,
                    time_24h=time_24h,
                    selected_ids_where=selected_ids_where,
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    symptoms = dictfetchall(cursor)
                for symptom in symptoms:
                    s_dict[symptom['name']]['count_last'] = symptom['count']
                for name in s_dict:
                    if not s_dict[name].get('count_last'):
                        s_dict[name]['count_last'] = 0

            s_list = []
            for name in s_dict:
                if s_dict[name]['count_last']:
                    title = '%s (%s, %s)' % (
                        name,
                        s_dict[name]['count_all'],
                        s_dict[name]['count_last'],
                    )
                else:
                    title = '%s (%s)' % (
                        name,
                        s_dict[name]['count_all'],
                    )
                s_list.append(dict(
                    title=title,
                    count_all=s_dict[name]['count_all'],
                    count_last=s_dict[name]['count_last'],
                ))
            s_list.sort(key = lambda d: d['count_all'])

            for s in s_list:
                data['titles'].append(s['title'])
                data['counts_all'].append(s['count_all'])
                data['counts_last'].append(s['count_last'])
            return data

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

            colors = [mcolor for mcolor in mcolors.CSS4_COLORS]
            colors.sort()

            symptom_ids = dict()
            symptom_names = dict()
            n = 0
            for symptom in Symptom.objects.all().order_by('pk'):
                symptom_ids[symptom.pk] = n
                symptom_names[n] = symptom.name
                n += 1

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
            for usersymptom in UserSymptom.objects.filter(
                    q
                ).select_related('symptom').order_by('-insert_timestamp'):

                ss[symptom_ids[usersymptom.symptom.pk]].append(usersymptom.insert_timestamp)
                #if usersymptom.latitude is not None and usersymptom.longitude is not None:
                    #got_symptom_key = None
                    #if usersymptom.incognito_id:
                        #got_symptom_key = '%s-%s' % (
                            #usersymptom.incognito_id.lower(), usersymptom.symptom.pk,
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
                fig.set_figheight(30)

                fig  = legend.figure
                fig.canvas.draw()
                bbox  = legend.get_window_extent().transformed(fig.dpi_scale_trans.inverted())

                tmpfile = BytesIO()
                fig.savefig(tmpfile, format='png', dpi="figure", bbox_inches=bbox)
                legend = base64.b64encode(tmpfile.getvalue()).decode('utf-8')
                plt.close()

            # Лунная диагамма
            #
            # Выбрать последние лунные дни, начиная с нулевого до текущего,
            # занести оттуда количества по симптомам. По остальным лунным
            # дням выбрать усредненные суммы по симптомам за весь период наблюдений.
            #
            # Все бы было просто, если б симптомы приходили каждый лунный день,
            # тогда делалась бы выборка после последнего insert_timestamp
            # за 29 день и до текущего. А вдруг в последний из 
            # 29-ых дней не окажется симптомов? Тогда будем ошибочно считать,\
            # начиная с 29-го лунного дня предыдущего цикла. То и оно!
            #
            # К сожалению, не удалось найти в апи, как вычислить
            # utc время начала текущего лунного цикла.
            #
            # Посему все сложнее:
            #
            # - Находим текущий лунный день, current_moon_day по текущему
            #   времени time_current.
            # - Надо найти минимальный min_insert_timestamp из лунных дней
            #   0..current_moon_day.
            #       * Сначала ищем минимальный из максимальных
            #         по лунным дням 0..current_moon_day.
            #         Он будет первым из этих максимальных (limit 1 в поиске).
            #         Найденный moon_day обзовем min_moon_day.
            #       * По этому min_moon_day ищем min_insert_timestamp за время
            #         не раньше его max_insert_timestamp минус 2 дня:
            #         один лунный день всегда меньше 2 календарных дней.
            #
            #   Однако! В текущем лунном цикле может не оказаться
            #           симптомов. Очень даже возможно: начался новый лунный цикл
            #           (current_moon_day == 0), а симптомы еще не поступали
            #           (min_moon_day == 29)
            #
            #       * Если min_moon_day > current_moon_day, то
            #         в текущем цикле не было симптомов
            #         Самый частый случай: current_moon_day == 0 && min_moon_day == 29
            #         (перешли в следующий цикл, а он пока без симптомов)
            #       * Иначе (delta_moon = current_moon_day - min_moon_day) >= 0.
            #         Считаем delta_time = time_current - min_insert_timestamp.
            #         При delta_moon == 0 достаточно с запасом delta_time = 5 суток,
            #         чтобы выяснить, что min_insert_timestamp -- в предыдущем цикле.
            #         При delta_moon == 1 с запасом delta_time = 6. И т.д
            #         Получается формула:
            #           если delta_time > (delta_moon + 5) * 86400,
            #               то в текущем лунном цикле не было симптомов.
            #
            # - Если в текущем цикле были симптомы, то не раньше
            #   min_insert_timestamp будет выборка количеств симптомов
            #   по лунным дням <= current_moon_day.
            #
            # - Усредненные суммы ищем по лунным дням > current_moon_day по всей таблице
            
            current_moon_day = get_moon_day(time_current)
            moon_fact = [[0 for j in range(30)] for i in range(len(symptom_ids))]
            moon_cast = [[0 for j in range(30)] for i in range(len(symptom_ids))]

            req_str = """
                SELECT
                    Max(insert_timestamp) as max_time,
                    moon_day
                FROM
                    contact_usersymptom
                WHERE
                    moon_day <= %(current_moon_day)s AND
                    insert_timestamp > %(time_current)s - 30 * 86040
                GROUP BY
                    moon_day
                ORDER BY
                    moon_day
                LIMIT 1
            """ % dict(
                current_moon_day=current_moon_day,
                time_current=time_current,
            )
            with connection.cursor() as cursor:
                cursor.execute(req_str)
                m = dictfetchall(cursor)

            if m and (m[0]['moon_day'] <= current_moon_day):
                min_moon_day = m[0]['moon_day']
                req_str = """
                    SELECT
                        Min(insert_timestamp) as min_insert_timestamp
                    FROM
                        contact_usersymptom
                    WHERE
                        moon_day = %(min_moon_day)s AND
                        insert_timestamp >= %(max_time)s - 2 * 86400
                """ % dict(
                    min_moon_day=min_moon_day,
                    max_time=m[0]['max_time'],
                )
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = dictfetchall(cursor)

                # fool-proof
                if m :
                    min_insert_timestamp = m[0]['min_insert_timestamp']
                    delta_moon = current_moon_day - min_moon_day
                    delta_time = time_current - min_insert_timestamp
                    if (selected_ids_str != '()') and \
                       (delta_time < (delta_moon + 5) * 86400):
                        req_str = """
                            SELECT
                                moon_day,
                                symptom_id,
                                Count(symptom_id) as count
                            FROM
                                contact_usersymptom
                            WHERE
                                moon_day <= %(current_moon_day)s AND
                                insert_timestamp >= %(min_insert_timestamp)s
                                %(selected_ids_where)s
                            GROUP BY
                                moon_day,
                                symptom_id
                            ORDER BY
                                moon_day,
                                symptom_id
                        """ % dict(
                            current_moon_day=current_moon_day,
                            min_insert_timestamp=min_insert_timestamp,
                            selected_ids_where=selected_ids_where,
                        )
                        with connection.cursor() as cursor:
                            cursor.execute(req_str)
                            m = dictfetchall(cursor)
                        for r in m:
                            moon_fact [symptom_ids[ r['symptom_id']] ] [r['moon_day']] = r['count']

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
                    GROUP BY
                        moon_day,
                        symptom_id
                    ORDER BY
                        symptom_id,
                        moon_day
                """ % dict(
                    current_moon_day=current_moon_day,
                    selected_ids_where=selected_ids_where,
                )
                divider = int((time_current + 21600 - settings.TIME_START_GET_SYMPTOMS)/settings.MOON_MONTH_LONG)
                if divider == 0:
                    divider = 1
                with connection.cursor() as cursor:
                    cursor.execute(req_str)
                    m = dictfetchall(cursor)
                for r in m:
                    moon_cast [symptom_ids[ r['symptom_id']] ] [r['moon_day']] = \
                        int(round(r['count'] / divider, 0))

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

            return dict(
                hist=hist,
                legend=legend,
                points=points,
                lat_avg=lat_avg,
                lng_avg=lng_avg,
                moon_days_fig=moon_days_fig,
            )

        return dict()
