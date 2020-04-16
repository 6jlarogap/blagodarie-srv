import time, datetime
import numpy as np
import os
import matplotlib as mpl
if os.environ.get('DISPLAY','') == '':
    mpl.use('Agg')
from matplotlib import colors as mcolors

import base64
from io import BytesIO

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

class LogLike(models.Model):
    """
    Статистика
    """

    dt = models.DateField(_("Дата"), unique=True)
    users = models.PositiveIntegerField(_("Участники"), default=0)
    likes = models.PositiveIntegerField(_("Благодарности"), default=0)
    keys = models.PositiveIntegerField(_("Ключи"), default=0)

    LAST_STAT_HOURS = 48

    @classmethod
    def get_stats(cls, *args, **kwargs):

        if kwargs.get('only') == 'users':
            # Вернуть число пользователей
            #
            return dict(
                users=User.objects.filter(
                    is_superuser=False,
                ).count(),
            )

        if kwargs.get('only') == 'symptoms':
            # Возвращает json:
            #   {
            #       "titles": [
            #           "Участники с симптомами (<число участников с симптомами>)",
            #           "симптом1 (<число симптомов1>)",
            #           ...
            #           "симптомN (<число симптомовN>)"
            #       ],
            #       "counts": [
            #           <число участников с симптомами>,
            #           "<число симптомов1>",
            #           ...
            #           "<число симптомовN>"
            #       ]
            #   }
            #
            count_users = User.objects.filter(
                    is_superuser=False,
                ).count()
            data = dict(
                titles=[
                    'Пользователи (%s)' % count_users,
                ],
                counts=[
                    count_users,
                ],
            )
            time_current = int(time.time())
            time_1st = time_current - LogLike.LAST_STAT_HOURS * 3600
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
                    insert_timestamp < %(time_current)s AND
                    insert_timestamp >= %(time_1st)s
                GROUP BY
                    name
                ORDER BY
                    count
            """ % dict(
                time_current=time_current,
                time_1st=time_1st,
            )
            with connection.cursor() as cursor:
                cursor.execute(req_str)
                symptoms = dictfetchall(cursor)
            for symptom in symptoms:
                data['titles'].append('%s (%s)' % (symptom['name'], symptom['count'],))
                data['counts'].append(symptom['count'])
            return data

        if kwargs.get('only') == 'symptoms_hist':

            # Возвращает json:
            #   {
            #       "stats": код картинки в base64
            #   }

            time_current = int(time.time())
            time_1st = time_current - LogLike.LAST_STAT_HOURS * 3600
            time_1st_hour = int(((time_1st + 3599) / 3600)) * 3600
            bins = [time_1st]
            if time_1st != time_1st_hour:
                bins.append(time_1st_hour)
            t = time_1st_hour + 3600
            while t < time_current:
                bins.append(t)
                t += 3600
            bins.append(time_current)

            tick_times = []
            for i, t in enumerate(bins):
                hour = datetime.datetime.fromtimestamp(t).hour
                if i == 0 or i == len(bins) - 1:
                    tick_times.append(t)
                elif hour % 3 == 0 and t - time_1st < 3 * 3600:
                    continue
                elif hour % 3 == 0 and time_current - t < 3 * 3600:
                    continue
                elif hour % 3 == 0:
                    tick_times.append(t)
            tick_labels = []
            cur_day = 0
            for i, t in enumerate(tick_times):
                dt = datetime.datetime.fromtimestamp(t)
                if dt.day != cur_day:
                    tick_labels.append(dt.strftime('%d.%m %H:%M'))
                    cur_day = dt.day
                elif i == len(tick_times)-1:
                    tick_labels.append(dt.strftime('%d.%m %H:%M'))
                else:
                    tick_labels.append(dt.strftime('%H:%M'))

            colors = [mcolor for mcolor in mcolors.CSS4_COLORS]
            colors.sort()

            symptom_ids = dict()
            symptom_names = dict()
            n = 0
            for symptom in Symptom.objects.all().order_by('pk'):
                symptom_ids[symptom.pk] = n
                symptom_names[n] = symptom.name
                n += 1

            time_current = int(time.time())
            ss = [[] for _ in symptom_ids]
            for usersymptom in UserSymptom.objects.filter(
                    insert_timestamp__lt=time_current,
                    insert_timestamp__gte=time_current - 48 * 3600,
                ).select_related('symptom').order_by('symptom__pk'):
                ss[symptom_ids[usersymptom.symptom.pk]].append(usersymptom.insert_timestamp)

            if not any(ss):
                return dict(hist='', legend='')

            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            ax.hist(ss, bins, stacked=True, edgecolor='black', color=colors[0:len(symptom_ids)])
            fig.set_figwidth(10)

            ax.set_xticks(tick_times)
            ax.set_xticklabels(tick_labels, rotation=12, rotation_mode="anchor", ha="right")

            yint = []
            locs, labels = plt.yticks()
            for each in locs:
                if each == int(each):
                    yint.append(each)
            plt.yticks(yint)

            tmpfile = BytesIO()
            plt.savefig(tmpfile, format='png')
            hist = base64.b64encode(tmpfile.getvalue()).decode('utf-8')

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
            plt.close()

            import matplotlib.pyplot as plt

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

            return dict(
                hist=hist,
                legend=legend,
            )

        return dict(
            users=User.objects.filter(is_superuser=False).count(),
            keys=Key.objects.all().count(),
            likes=Like.objects.all().count(),
        )
