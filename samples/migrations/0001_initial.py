# Generated by Django 5.0.7 on 2024-07-31 18:12

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Sample',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('date_received', models.DateField()),
                ('customer', models.CharField(max_length=255)),
                ('opportunity_number', models.CharField(max_length=255)),
                ('rsm', models.CharField(max_length=255)),
                ('storage_location', models.CharField(blank=True, choices=[('Test Lab Fridge', 'Test Lab Fridge'), ('Test Lab Freezer', 'Test Lab Freezer'), ('Walk-in Fridge', 'Walk-in Fridge'), ('Walk-in Freezer', 'Walk-in Freezer')], max_length=255, null=True)),
                ('quantity', models.IntegerField(default=1)),
                ('unique_id', models.PositiveIntegerField(unique=True)),
            ],
        ),
    ]
