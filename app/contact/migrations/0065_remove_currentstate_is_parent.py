# Generated by Django 3.2.6 on 2021-10-25 13:32

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0064_data_func_find_mother_father'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='currentstate',
            name='is_parent',
        ),
    ]
