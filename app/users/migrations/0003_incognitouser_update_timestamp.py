# Generated by Django 2.2.4 on 2020-06-05 11:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_incognitouser'),
    ]

    operations = [
        migrations.AddField(
            model_name='incognitouser',
            name='update_timestamp',
            field=models.BigIntegerField(default=0, verbose_name='Когда изменено'),
        ),
    ]
