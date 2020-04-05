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
    Нарастающим итогом за каждую дату статистика
    """

    dt = models.DateField(_("Дата"), unique=True)
    users = models.PositiveIntegerField(_("Участники"), default=0)
    likes = models.PositiveIntegerField(_("Благодарности"), default=0)
    keys = models.PositiveIntegerField(_("Ключи"), default=0)

    @classmethod
    def get_stats(cls, *args, **kwargs):

        if kwargs.get('only') == 'users_with_symptoms':
            # Вернуть число пользователей, доложивших о симптоме
            #
            return dict(
                users=UserSymptom.objects.filter(
                    user__is_superuser=False,
                ).distinct('user').count(),
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
            count_users_with_symptoms = UserSymptom.objects.filter(
                    user__is_superuser=False,
                ).distinct('user').count()
            data = dict(
                titles=[
                    'Пользователи с симптомами (%s)' % count_users_with_symptoms,
                ],
                counts=[
                    count_users_with_symptoms,
                ],
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
            for symptom in symptoms:
                data['titles'].append('%s (%s)' % (symptom['name'], symptom['count'],))
                data['counts'].append(symptom['count'])
            return data

        return dict(
            users=User.objects.filter(is_superuser=False).count(),
            keys=Key.objects.all().count(),
            likes=Like.objects.all().count(),
        )
