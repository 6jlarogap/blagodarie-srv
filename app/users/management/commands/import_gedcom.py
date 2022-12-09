# import_gedcom.py
#
# Импорт данных в gedcom формате
#
# Текущие спецификации: https://gedcom.io/specifications/ged551.pdf
# Продвинутый формат: https://gedcom.io/specifications/gedcom7-rc.pdf
#
# Параметры:
#   owner_uuid  Пользователь, который становится владельцем всех файлов
#   filename    Файл в gedcom формате

from io import BytesIO

from django.core.management.base import BaseCommand
from django.db import transaction

from app.utils import ServiceException
from users.views import ApiImportGedcom

class Command(BaseCommand):
    help = 'Import family members and tree from filename.gedcom and assign them to owner_uuid'
    
    def add_arguments(self, parser):
        parser.add_argument('owner_uuid', type=str, help='owner_uuid, assigned as owner of family members')
        parser.add_argument('filename', type=str, help='/path/to/gedcom_file, gedcom file with family tree')

    @transaction.atomic
    def handle(self, *args, **kwargs):
        owner_uuid = kwargs['owner_uuid']
        filename = kwargs['filename']
        try:
            f = open(filename, mode='rb')
            bytes_io = f.read()
        except OSError:
            print("Failed to read '%s' file" % filename)
            exit()
        f.close()
        bytes_io = BytesIO(bytes_io)

        try:
            import_gedcom = ApiImportGedcom()
            import_gedcom.do_import(owner_uuid, bytes_io)
            print('OK')
        except ServiceException as excpt:
            transaction.set_rollback(True)
            print('ERROR: %s' % excpt.args[0])

