# Generated by Django 2.2.4 on 2020-05-08 11:22

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0023_fill_symptoms_checksum'),
    ]

    operations = [
        migrations.AlterField(
            model_name='symptom',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='contact.SymptomGroup', verbose_name='Группа'),
        ),
        migrations.AlterField(
            model_name='symptom',
            name='order',
            field=models.IntegerField(default=None, null=True, verbose_name='Порядок следования'),
        ),
    ]