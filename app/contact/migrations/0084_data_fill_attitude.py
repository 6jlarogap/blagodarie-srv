# Generated by Django 4.2.4 on 2024-04-03 18:39

from django.db import migrations


def reverse_it(apps, schema_editor):
    pass


def operation(apps, schema_editor):

    print('\nTrust & Mistrust null booleans convert to attitude in CurrentState')
    n = 0
    CurrentState = apps.get_model('contact', 'CurrentState')
    for cs in CurrentState.objects.filter(is_trust__isnull=False):
        cs.attitude = 't' if cs.is_trust else 'mt'
        cs.save(update_fields=('attitude',))
        n += 1
    print(f'{n} recs converted')

class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0083_currentstate_attitude'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]