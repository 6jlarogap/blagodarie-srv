# Generated by Django 2.2.4 on 2020-04-23 19:27

from django.db import migrations


def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    print('')
    n = 0
    Symptom = apps.get_model('contact', 'Symptom')
    try:
        symptom_source = Symptom.objects.get(pk=31)
        symptom_dests = (
            Symptom.objects.get(pk=42),
        )
        UserSymptom = apps.get_model('contact', 'UserSymptom')
        for usersymptom in UserSymptom.objects.filter(symptom=symptom_source):
            for symptom_dest in symptom_dests:
                UserSymptom.objects.create(
                    user=usersymptom.user,
                    insert_timestamp=usersymptom.insert_timestamp,
                    symptom=symptom_dest,
                )
            n += 1
    except Symptom.DoesNotExist:
        pass
    print('%s source symptoms "forked"' % n)

class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0016_auto_20200417_1755'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]