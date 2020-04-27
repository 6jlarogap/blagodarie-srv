import time, datetime
import numpy as np
import os
import matplotlib as mpl
if os.environ.get('DISPLAY','') == '':
    mpl.use('Agg')
from matplotlib import colors as mcolors
import matplotlib.pyplot as plt

import base64
from io import BytesIO

from app.utils import get_moon_day

from django.db import models, connection
from django.utils.translation import ugettext_lazy as _

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

class Symptom(models.Model):

    name = models.CharField(_("Название"), max_length=255, unique=True)

class UserSymptom(BaseModelInsertTimestamp, GeoPointModel):

    user = models.ForeignKey('auth.User', verbose_name=_("Пользователь"), on_delete=models.CASCADE)
    symptom = models.ForeignKey(Symptom, verbose_name=_("Симптом"), on_delete=models.CASCADE)
    # От 0 до 27
    moon_day = models.IntegerField(_("День лунного календаря"), default=0)

    def save(self, *args, **kwargs):
        self.fill_insert_timestamp()
        if not self.moon_day:
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
    def get_stats(cls, *args, **kwargs):

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
            return dict(
                users=User.objects.filter(
                    is_superuser=False,
                ).count(),
                symptoms=UserSymptom.objects.filter(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                ).count(),
            )

        if kwargs.get('only') == 'symptoms':
            # Возвращает json:
            #   {
            #       "titles": [
            #           "Пользователи (<общее число>, <число с симптомами за LAST_STAT_HOURS>)",
            #           "симптом1 (<всего>, <за LAST_STAT_HOURS>)",
            #           ...
            #           "симптомN (<всего>, <за LAST_STAT_HOURS>)"
            #       ],
            #       "counts_all": [
            #           <всего пользователей>,
            #           "<всего симптомов1>",
            #           ...
            #           "<всего симптомовN>"
            #       ],
            #       "counts_last": [
            #           <пользователей за LAST_STAT_HOURS>,
            #           "<за LAST_STAT_HOURS симптомов1>",
            #           ...
            #           "<за LAST_STAT_HOURS симптомовN>"
            #       ],
            #   }
            #
            count_users_all = User.objects.filter(
                    is_superuser=False,
                ).count()
            count_users_last = UserSymptom.objects.filter(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                ).distinct('user').count()

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
                GROUP BY
                    name
                ORDER BY
                    count
            """
            with connection.cursor() as cursor:
                cursor.execute(req_str)
                symptoms = dictfetchall(cursor)
            s_dict = dict()
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
                    insert_timestamp >= %(time_1st)s
                GROUP BY
                    name
                ORDER BY
                    count
            """ % dict(
                time_last=time_last,
                time_1st=time_1st,
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
            for usersymptom in UserSymptom.objects.filter(
                    insert_timestamp__lt=time_last,
                    insert_timestamp__gte=time_1st,
                ).select_related('symptom').order_by('-insert_timestamp'):
                ss[symptom_ids[usersymptom.symptom.pk]].append(usersymptom.insert_timestamp)
                if usersymptom.latitude is not None and usersymptom.longitude is not None:
                    got_symptom_key = '%s-%s' % (usersymptom.user.pk, usersymptom.symptom.pk, )
                    if not got_symptom.get(got_symptom_key):
                        got_symptom[got_symptom_key] = 1
                        points.append([
                            usersymptom.latitude,
                            usersymptom.longitude,
                            usersymptom.symptom.name,
                        ])
                        lat_sum += usersymptom.latitude
                        lng_sum += usersymptom.longitude

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
                                height = 0.2, color = legend_colors[i], alpha = 0.7,
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
            # за 27 день и до текущего. А вдруг в последний из 
            # 27-ых дней не окажется симптомов? Тогда будем ошибочно считать,\
            # начиная с 27-го лунного дня предыдущего цикла. То и оно!
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
            #           (min_moon_day == 27)
            #
            #       * Если min_moon_day > current_moon_day, то
            #         в текущем цикле не было симптомов
            #         Самый частый случай: current_moon_day == 0 && min_moon_day == 27
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
            # - Если в текущем цикле не было симптомов, то находим усредненные суммы
            #   по всем дням по всей таблице, исключая current_moon_day:
            #   по нему всегда показываем количества симптомов (а не суммы),
            #   даже если симптомов в current_moon_day не было.
            #   
            # - Если в текущем цикле были симптомы, то не раньше
            #   min_insert_timestamp будет выборка количеств симптомов
            #   по лунным дням 0..current_moon_day. Усредненные суммы
            #   ищем по лунным дням current_moon_day+1 .. 28 по всей таблице
            
            current_moon_day = get_moon_day(time_current)
            moon_days = [[0 for j in range(28)] for i in range(len(symptom_ids))]
            min_insert_timestamp = None

            req_str = """
                SELECT
                    Max(insert_timestamp) as max_time,
                    moon_day
                FROM
                    contact_usersymptom
                WHERE
                    moon_day <= %(current_moon_day)s AND
                    insert_timestamp > %(time_current)s - 40 * 86040
                GROUP BY
                    moon_day
                ORDER BY
                    max_time
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
                if not m :
                    min_insert_timestamp = None
                else:
                    min_insert_timestamp = m[0]['min_insert_timestamp']
                    delta_moon = current_moon_day - min_moon_day
                    delta_time = time_current - min_insert_timestamp
                    if delta_time > (delta_moon + 5) * 86400:
                        min_insert_timestamp = None
                    else:
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
                            GROUP BY
                                moon_day,
                                symptom_id
                            ORDER BY
                                moon_day,
                                symptom_id
                        """ % dict(
                            current_moon_day=current_moon_day,
                            min_insert_timestamp=min_insert_timestamp,
                        )
                        with connection.cursor() as cursor:
                            cursor.execute(req_str)
                            m = dictfetchall(cursor)
                        for r in m:
                            moon_days [symptom_ids[ r['symptom_id']] ] [r['moon_day']] = r['count']

            #TODO Усредненные суммы, в зависимости от min_insert_timestamp

            moon_phases = (

                # new moon (black circle)

                '\u25CF', '\u25CF', '\u25CF', '\u25CF', '\u25CF', '\u25CF', '\u25CF',

                # 1-st quarter (circle with left half black)

                '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0', '\u25D0',

                # full moon (white circle)

                '\u25CB', '\u25CB', '\u25CB', '\u25CB', '\u25CB', '\u25CB', '\u25CB',

                # 3-rd quarter (circle with right half black)

                '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1', '\u25D1',
            )

            ind = range(28)
            days = [str(i+1) for i in range(28)]
            days[current_moon_day] = '*\n%s' % datetime.datetime.fromtimestamp(time_current).strftime('%d.%m')
            bar_width = 0.5

            fig, ax1 = plt.subplots()
            fig.set_figwidth(10)

            bottom = [ 0 for j in range(len(moon_days[0]))]
            for i, s in enumerate(moon_days):
                ax1.bar(
                    ind,
                    moon_days[i],
                    width=bar_width,
                    bottom=bottom,
                    color=colors[i],
                    tick_label=days
                )
                for j, b in enumerate(bottom):
                    bottom[j] += moon_days[i][j]
            got_any = False
            for i, s in enumerate(moon_days):
                for j, y in enumerate(s):
                    if y:
                        got_any = True
                        break
                if got_any:
                    break
            if not got_any:
                plt.yticks(range(0, 51, 10))

            ax2 = ax1.twiny()
            ax2.bar(ind, [0] * 28, width=bar_width, tick_label=moon_phases)

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

