# Generated by Django 4.2.4 on 2024-04-19 13:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0042_profile_editable'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='acq_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Число тех кто с ним (с ней) знаком)'),
        ),
        migrations.AddField(
            model_name='profile',
            name='did_meet',
            field=models.BooleanField(default=False, verbose_name='Устанавливал ли с кем знакомство'),
        ),
    ]
