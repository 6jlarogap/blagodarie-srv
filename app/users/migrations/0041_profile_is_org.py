# Generated by Django 4.2.4 on 2023-12-19 15:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0040_data_usernames_are_short_ids'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='is_org',
            field=models.BooleanField(default=False, verbose_name='Организация'),
        ),
    ]
