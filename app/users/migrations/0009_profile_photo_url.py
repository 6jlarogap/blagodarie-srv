# Generated by Django 2.2.4 on 2020-07-01 17:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_auto_20200630_1856'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='photo_url',
            field=models.URLField(default='', max_length=255, verbose_name='Фото из соц. сети'),
        ),
    ]
