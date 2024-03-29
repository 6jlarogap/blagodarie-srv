# Generated by Django 4.2.1 on 2023-05-18 16:10

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Video',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('insert_timestamp', models.BigIntegerField(db_index=True, default=0, verbose_name='Когда добавлено')),
                ('source', models.CharField(choices=[('yt', 'Google'), ('rt', 'RuTube'), ('vk', 'ВКонтакте'), ('bn', 'Bastyon')], max_length=2, verbose_name='Источник')),
                ('videoid', models.CharField(max_length=50, verbose_name='Видео Id')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Владелец')),
            ],
            options={
                'unique_together': {('source', 'videoid')},
            },
        ),
        migrations.CreateModel(
            name='Vote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('insert_timestamp', models.BigIntegerField(db_index=True, default=0, verbose_name='Когда добавлено')),
                ('update_timestamp', models.BigIntegerField(db_index=True, default=0, verbose_name='Когда изменено')),
                ('time', models.PositiveIntegerField(default=0, verbose_name='Время')),
                ('button', models.CharField(choices=[('yes', 'Да'), ('no', 'Нет'), ('not', 'Не ясно')], max_length=10, verbose_name='Кнопка')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
                ('video', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='wote.video', verbose_name='Видео')),
            ],
            options={
                'unique_together': {('user', 'video', 'time', 'button')},
            },
        ),
    ]
