# Generated by Django 5.1.3 on 2024-11-12 15:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0047_offer_address_offer_latitude_offer_longitude'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='invite_meet_count',
            field=models.PositiveIntegerField(default=0, verbose_name='Число тех, кого он пригласил)'),
        ),
    ]