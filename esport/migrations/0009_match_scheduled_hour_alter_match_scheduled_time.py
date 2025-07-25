# Generated by Django 5.2.1 on 2025-07-11 09:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('esport', '0008_remove_prediction_points_awarded_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='scheduled_hour',
            field=models.TimeField(default='12:00:00'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='match',
            name='scheduled_time',
            field=models.DateTimeField(editable=False),
        ),
    ]
