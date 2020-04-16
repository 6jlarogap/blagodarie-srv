# Generated by Django 2.2.4 on 2020-04-16 16:04

from django.db import migrations


def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    print('')
    Symptom = apps.get_model('contact', 'Symptom')
    symptom_source = Symptom.objects.get(pk=10)
    symptom_dests = (
        Symptom.objects.get(pk=26),
        Symptom.objects.get(pk=27),
    )
    UserSymptom = apps.get_model('contact', 'UserSymptom')
    n = 0
    for usersymptom in UserSymptom.objects.filter(symptom=symptom_source):
        for symptom_dest in symptom_dests:
            UserSymptom.objects.create(
                user=usersymptom.user,
                insert_timestamp=usersymptom.insert_timestamp,
                symptom=symptom_dest,
            )
        n += 1
    print('%s source symptoms "forked"' % n)

class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0014_symptom_usersymptom'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
