# Generated by Django 2.2.4 on 2020-05-27 15:44

from django.db import migrations

def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    """
    Заполнить IncognitoUser.private_key's из UserSymptom.incognito_id's
    """
    UserSymptom = apps.get_model('contact', 'UserSymptom')
    IncognitoUser = apps.get_model('users', 'IncognitoUser')
    print('')
    print("Fill IncognitoUser.private_key's from UserSymptom.incognito_id's")
    UserSymptom.objects.filter(incognito_id__isnull=True).delete()
    n = 0
    msg_processed = "%s usersymptoms processed"
    for usersymptom in UserSymptom.objects.all().iterator(chunk_size=100):
        incognitouser, created_ = IncognitoUser.objects.get_or_create(
            private_key=usersymptom.incognito_id,
        )
        usersymptom.incognitouser = incognitouser
        usersymptom.save(update_fields=('incognitouser',))
        if n % 1000 == 0:
            print(msg_processed % n)
        n += 1
    if n % 1000 != 0:
        print(msg_processed % n)

class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0031_usersymptom_incognitouser'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]