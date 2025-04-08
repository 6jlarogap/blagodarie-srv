# Generated by Django 5.1.3 on 2025-04-08 12:59

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0054_tgdesc_caption_tgdesc_file_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='tgdesc',
            name='file_type',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Тип медиа'),
        ),
        migrations.AddField(
            model_name='tgdesc',
            name='uuid_pack',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.AlterField(
            model_name='tgdesc',
            name='caption',
            field=models.TextField(default='', verbose_name='Заголовок'),
        ),
    ]
