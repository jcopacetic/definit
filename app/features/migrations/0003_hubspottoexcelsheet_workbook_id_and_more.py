# Generated by Django 5.1.9 on 2025-05-21 03:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('features', '0002_remove_hubspottoexcelsheet_hubspot_object_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='hubspottoexcelsheet',
            name='workbook_id',
            field=models.CharField(blank=True, max_length=280),
        ),
        migrations.AddField(
            model_name='hubspottoexcelsheet',
            name='workbook_name',
            field=models.CharField(blank=True, max_length=280),
        ),
    ]
