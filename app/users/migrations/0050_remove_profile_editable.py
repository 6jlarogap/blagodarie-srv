# Generated by Django 5.1.3 on 2025-01-08 14:53

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0049_data_fill_meet_invite_count'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='editable',
        ),
    ]