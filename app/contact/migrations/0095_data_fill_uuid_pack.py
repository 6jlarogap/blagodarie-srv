# Generated by Django 5.1.3 on 2025-04-08 13:55

from uuid import uuid4

from django.db import migrations


def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):

    # Сделать разными uuid_packs в журнале сообщений

    TgMessageJournal = apps.get_model('contact', 'TgMessageJournal')
    for tm in TgMessageJournal.objects.all():
        tm.uuid_pack = uuid4()
        tm.save(update_fields=('uuid_pack',))

class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0094_tgmessagejournal_caption_tgmessagejournal_file_id_and_more'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
