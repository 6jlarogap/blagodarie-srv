# Generated by Django 3.2.6 on 2021-09-16 10:48

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0050_auto_20210906_1514'),
        ('users', '0020_fill_profile_ability'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='ability',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='contact.ability', verbose_name='Способность'),
        ),
    ]
