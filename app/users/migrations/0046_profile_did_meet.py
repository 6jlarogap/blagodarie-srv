# Generated by Django 4.2.4 on 2024-08-23 11:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0045_remove_profile_did_meet'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='did_meet',
            field=models.BigIntegerField(null=True, verbose_name='Установил знакомство (принял участие в игре знакомств)'),
        ),
    ]