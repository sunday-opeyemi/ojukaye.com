# Generated by Django 3.1.1 on 2021-01-28 11:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userportalapp', '0002_userpost_table'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpost_table',
            name='post_content',
            field=models.CharField(max_length=5000, null=True),
        ),
    ]
