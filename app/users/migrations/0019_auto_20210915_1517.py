# Generated by Django 3.2.6 on 2021-09-15 15:17

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0050_auto_20210906_1514'),
        ('users', '0018_user_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='ability',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='contact.ability', verbose_name='Способность'),
        ),
        migrations.AddField(
            model_name='profile',
            name='latitude',
            field=models.FloatField(blank=True, null=True, verbose_name='Широта'),
        ),
        migrations.AddField(
            model_name='profile',
            name='longitude',
            field=models.FloatField(blank=True, null=True, verbose_name='Долгота'),
        ),
    ]
