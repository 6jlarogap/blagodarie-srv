# Generated by Django 4.2.4 on 2024-04-04 16:05

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0084_data_fill_attitude'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='currentstate',
            name='is_trust',
        ),
    ]