# Generated by Django 3.2.6 on 2021-11-19 18:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0023_auto_20211005_1322'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='comment',
            field=models.TextField(null=True, verbose_name='Примечание'),
        ),
    ]
