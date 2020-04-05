# Generated by Django 2.2.4 on 2019-12-09 15:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0009_remove_userkey_is_actual'),
    ]

    operations = [
        migrations.CreateModel(
            name='LogLike',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dt', models.DateField(unique=True, verbose_name='Дата')),
                ('users', models.PositiveIntegerField(default=0, verbose_name='Участники')),
                ('likes', models.PositiveIntegerField(default=0, verbose_name='Благодарности')),
                ('keys', models.PositiveIntegerField(default=0, verbose_name='Ключи')),
            ],
        ),
    ]
