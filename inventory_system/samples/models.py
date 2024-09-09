import random
from django.db import models

def generate_unique_id():
    while True:
        new_id = random.randint(1000, 9999)
        if not Sample.objects.filter(unique_id=new_id).exists():
            return new_id


class Sample(models.Model):
    unique_id = models.PositiveIntegerField(default=generate_unique_id, unique=True)
    date_received = models.DateField()
    customer = models.CharField(max_length=255)
    opportunity_number = models.CharField(max_length=255)
    rsm = models.CharField(max_length=255)
    storage_location = models.CharField(max_length=255, blank=True, null=True, choices=[
        ('Test Lab Fridge', 'Test Lab Fridge'),
        ('Test Lab Freezer', 'Test Lab Freezer'),
        ('Walk-in Fridge', 'Walk-in Fridge'),
        ('Walk-in Freezer', 'Walk-in Freezer')
    ])
    quantity = models.IntegerField(default=1)
    description = models.TextField(default="No description")

    audit = models.BooleanField(default=False)
