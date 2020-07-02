# Generated by Django 2.2.4 on 2020-07-01 17:53

from django.db import migrations

def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    """
    Заполнить Profile.photo_url's полученными из соц. сетей (oauth)
    """
    Profile = apps.get_model('users', 'Profile')
    Oauth = apps.get_model('users', 'Oauth')
    for oauth in Oauth.objects.filter(photo__gt='').order_by('update_timestamp'):
        profile = oauth.user.profile
        Profile.objects.filter(pk=profile.pk).update(photo_url=oauth.photo)

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_profile_photo_url'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
