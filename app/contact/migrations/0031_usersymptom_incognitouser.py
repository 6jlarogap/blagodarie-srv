# Generated by Django 2.2.4 on 2020-05-27 15:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_incognitouser'),
        ('contact', '0030_remove_usersymptom_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersymptom',
            name='incognitouser',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='users.IncognitoUser', verbose_name='Пользователь инкогнито'),
        ),
    ]
