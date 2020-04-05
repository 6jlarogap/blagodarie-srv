import time

from django.db import models
from django.utils.translation import ugettext_lazy as _

class BaseModelInsertTimestamp(models.Model):

    class Meta:
        abstract = True

    insert_timestamp = models.BigIntegerField(_("Когда добавлено"), default=0)

    def fill_insert_timestamp(self):
        if not self.insert_timestamp:
            self.insert_timestamp = int(time.time())

    def save(self, *args, **kwargs):
        self.fill_insert_timestamp()
        return super(BaseModelInsertTimestamp, self).save(*args, **kwargs)

class BaseModelInsertUpdateTimestamp(BaseModelInsertTimestamp):

    class Meta:
        abstract = True

    update_timestamp = models.BigIntegerField(_("Когда изменено"), default=0)

    def fill_update_timestamp(self):
        if not self.update_timestamp:
            self.update_timestamp = int(time.time())

    def save(self, *args, **kwargs):
        self.fill_update_timestamp()
        return super(BaseModelInsertUpdateTimestamp, self).save(*args, **kwargs)

class GeoPointModel(models.Model):
    """
    Базовая GEO модель
    """
    latitude = models.FloatField(_("Широта"), blank=True, null=True)
    longitude = models.FloatField(_("Долгота"), blank=True, null=True)

    class Meta:
        abstract = True
