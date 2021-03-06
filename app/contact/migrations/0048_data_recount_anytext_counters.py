# Generated by Django 2.2.4 on 2020-11-10 13:04

from django.db import migrations


def reverse_it(apps, schema_editor):
    pass

def operation(apps, schema_editor):
    print('')
    print ('Recount AnyText trust_count, mistrust_count, fame')
    n_all = n = 0
    AnyText = apps.get_model('contact', 'AnyText')
    CurrentState = apps.get_model('contact', 'CurrentState')
    for anytext in AnyText.objects.all():
        n_all += 1
        trust_count = CurrentState.objects.filter(
            is_reverse=False,
            anytext=anytext,
            is_trust=True,
        ).distinct().count()
        mistrust_count = CurrentState.objects.filter(
            is_reverse=False,
            anytext=anytext,
            is_trust=False,
        ).distinct().count()
        fame = trust_count + mistrust_count
        if fame != anytext.fame or \
           trust_count != anytext.trust_count or \
           mistrust_count != anytext.mistrust_count:
            AnyText.objects.filter(pk=anytext.pk).update(
                trust_count=trust_count,
                mistrust_count=mistrust_count,
                fame=fame,
            )
            n += 1
    print("%s anytexts' counters re-counted. All anytexts: %s" % (n, n_all,))


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0047_auto_20201110_1300'),
    ]

    operations = [
        migrations.RunPython(operation, reverse_it),
    ]
