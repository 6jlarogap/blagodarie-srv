# Generated by Django 4.2.4 on 2024-04-19 13:44

from django.db import migrations


def reverse_it(apps, schema_editor):
    pass


def operation(apps, schema_editor):

    print('\nFill Profile.acq_count')
    CurrentState = apps.get_model('contact', 'CurrentState')
    Profile = apps.get_model('users', 'Profile')

    # Полагаем, что знакомств к моменту запуска этой миграции немного,
    # так что идем не по всем профилям, считая их знакомства,
    # а идем по всем отношениям, а из них вытаскиваем профили,
    # к которым есть знакомства
    #
    profiles = dict()
    for cs in CurrentState.objects.select_related(
            'user_to', 'user_to__profile'
        ).filter(
            attitude='a', is_reverse=False,
        ):
        if profiles.get(cs.user_to.profile.pk):
            profiles[cs.user_to.profile.pk] += 1
        else:
            profiles[cs.user_to.profile.pk] = 1
    for pk in profiles:
        Profile.objects.filter(pk=pk).update(acq_count=profiles[pk])

    print(f'{len(profiles)} profiles filled with positive acq_count')


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0043_profile_acq_count_profile_did_meet'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
