# Generated by Django 2.2.4 on 2020-05-05 23:52

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0021_auto_20200430_1600'),
    ]

    operations = [
        migrations.CreateModel(
            name='Checksum',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(editable=False, max_length=255, unique=True, verbose_name='Класс')),
                ('value', models.CharField(editable=False, max_length=255, verbose_name='Значение')),
            ],
        ),
        migrations.AlterModelOptions(
            name='symptom',
            options={'ordering': ('name',), 'verbose_name': 'Cимптом', 'verbose_name_plural': 'Симптомы'},
        ),
        migrations.AddField(
            model_name='symptom',
            name='order',
            field=models.IntegerField(default=0, verbose_name='Порядок следования'),
        ),
        migrations.CreateModel(
            name='SymptomGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True, verbose_name='Название')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contact.SymptomGroup', verbose_name='Родительская группа')),
            ],
            options={
                'verbose_name': 'Группа симптомов',
                'verbose_name_plural': 'Группы симптомов',
                'ordering': ('name',),
            },
        ),
        migrations.AddField(
            model_name='symptom',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contact.SymptomGroup', verbose_name='Группа'),
        ),
    ]