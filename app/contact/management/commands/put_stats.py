# put_stats.py
#
# Сохранить статистику нарастающим итогом на текущую дату нарастающим итогом
#
# Запуск: : ./manage.py put_stats
#
# Результат: запись за текущую дату в таблице contact_loglike

import datetime

from django.core.management.base import BaseCommand

from contact.models import LogLike

class Command(BaseCommand):
    help = "Put cumulative total of users, likes, keys, by the current date, to LogLike table"

    def handle(self, *args, **kwargs):
        dt = datetime.date.today()
        data = LogLike.get_stats()
        loglike, created_ = LogLike.objects.get_or_create(
            dt=dt,
            defaults = data
        )
        if not created_:
            LogLike.objects.filter(pk=loglike.pk).update(**data)
        data.update(dt=dt)
        print(
            '\n',
            self.help, '\n',
            '\n',
            'Current date (y-m-d): %(dt)s\n'
            '    users: %(users)s\n'
            '    keys:  %(keys)s\n'
            '    likes: %(likes)s\n'
            '\n'
            % data,
            sep='', end='',
        )
