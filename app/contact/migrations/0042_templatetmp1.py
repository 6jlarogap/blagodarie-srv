# Generated by Django 2.2.4 on 2020-09-24 12:03

from django.db import migrations, models

# TODO Drop this table

class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0041_data_template_tmp1'),
    ]

    operations = [
        migrations.CreateModel(
            name='TemplateTmp1',
            fields=[
###                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.IntegerField(blank=True, null=True)),
                ('user_from_id', models.IntegerField(blank=True, null=True)),
                ('user_to_id', models.IntegerField(blank=True, null=True)),
                ('thanks_count', models.IntegerField(blank=True, null=True)),
                ('is_trust', models.BooleanField(blank=True, null=True)),
                ('is_reverse', models.BooleanField(blank=True, null=True)),
            ],
            options={
                'db_table': 'template_tmp1',
                'managed': False,
            },
        ),
    ]
