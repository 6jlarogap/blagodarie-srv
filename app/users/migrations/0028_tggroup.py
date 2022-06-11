# Generated by Django 3.2.6 on 2022-06-09 17:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0027_alter_profile_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='TgGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('insert_timestamp', models.BigIntegerField(db_index=True, default=0, verbose_name='Когда добавлено')),
                ('chat_id', models.BigIntegerField(db_index=True, unique=True, verbose_name='Chat Id')),
                ('title', models.CharField(max_length=256, verbose_name='Имя')),
                ('type', models.CharField(max_length=50, verbose_name='Тип')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
