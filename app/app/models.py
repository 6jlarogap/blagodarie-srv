import time, datetime
import pytils

from django.db import models
from django.utils.translation import ugettext_lazy as _

class BaseModelInsertTimestamp(models.Model):

    class Meta:
        abstract = True

    insert_timestamp = models.BigIntegerField(_("Когда добавлено"), default=0, db_index=True)

    def fill_insert_timestamp(self):
        if not self.insert_timestamp:
            self.insert_timestamp = int(time.time())

    def save(self, *args, **kwargs):
        self.fill_insert_timestamp()
        return super(BaseModelInsertTimestamp, self).save(*args, **kwargs)

class BaseModelInsertUpdateTimestamp(BaseModelInsertTimestamp):

    class Meta:
        abstract = True

    update_timestamp = models.BigIntegerField(_("Когда изменено"), default=0, db_index=True)

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


def files_upload_to(instance, filename):
    if hasattr(instance, 'photo_original_filename'):
        instance.photo_original_filename = filename
    fname = '.'.join(map(pytils.translit.slugify, filename.rsplit('.', 1)))
    today = datetime.date.today()

    # Путь к сохраняемому файлу:
    #   - первая составляющая (каталог): - /то, к чему относятся файлы/
    #   - год/месяц/день, чтоб не допускать огромное множество файлов
    #     (каталогов) в одной папке. Заодно и дата создания наглядна
    #   - первичный ключ того объекта, проверку на доступ к которому
    #     будем осуществлять
    #   - имя файла, оттуда убраны нелатинские символы, знаки препинания
    #     и т.п.
    today_pk_dir = "{0:d}/{1:02d}/{2:02d}".format(today.year, today.month, today.day)
    today_pk_dir += "/%s"

    if isinstance(instance, get_model('users', 'Profile')):
        return os.path.join('profile-photo',
                today_pk_dir % instance.pk, fname)
    else:
        return os.path.join('files', fname)

class FilesMixin(object):

    def file_field(self):
        if hasattr(self, 'photo'):
            file_ = self.photo
        else:
            file_ = None
        return file_

    def delete_from_media(self):
        file_ = self.file_field()
        if file_ and file_.path and os.path.exists(file_.path):
            try:
                dir_ = os.path.dirname(file_.path)
                os.remove(file_.path)
                os.removedirs(dir_)
            except OSError:
                pass

    def delete(self):
        self.delete_from_media()
        super(FilesMixin, self).delete()

class PhotoModel(FilesMixin, models.Model):
    """
    Базовый (дополнительный) класс для моделей, у которых есть фото объекта
    """
    # Мегабайт:
    MAX_PHOTO_SIZE = 10

    class Meta:
        abstract = True

    photo = models.ImageField("Фото", max_length=255, upload_to=files_upload_to, blank=True, null=True)
    photo_original_filename = models.CharField(max_length=255, editable=False, default='')
