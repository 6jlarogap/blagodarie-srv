# Generated by Django 3.2.6 on 2021-09-06 16:02

from django.db import migrations, connection


def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    sqls = [
        'CREATE INDEX IF NOT EXISTS auth_first_name_idx ON auth_user (first_name)',
        'CREATE INDEX IF NOT EXISTS auth_last_name_idx ON auth_user (last_name)'
    ]
    print('\nCreate auth_user last_name and first_name indexes')
    with connection.cursor() as cursor:
        for sql in sqls:
            cursor.execute(sql)

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_profile_is_notified'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
