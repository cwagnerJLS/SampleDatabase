import random
from django.db import models

class Sample(models.Model):
    unique_id = models.PositiveIntegerField(unique=True, editable=False)
    date_received = models.DateField()
    customer = models.CharField(max_length=255)
    opportunity_number = models.CharField(max_length=255)
    rsm = models.CharField(max_length=255)
    storage_location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        choices=[
            ('Test Lab Fridge', 'Test Lab Fridge'),
            ('Test Lab Freezer', 'Test Lab Freezer'),
            ('Walk-in Fridge', 'Walk-in Fridge'),
            ('Walk-in Freezer', 'Walk-in Freezer'),
            ('Dry Food Storage', 'Dry Food Storage'),
            ('Empty Case Storage', 'Empty Case Storage')
        ]
    )
    quantity = models.IntegerField(default=1)
    description = models.TextField(default="No description")
    audit = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.unique_id:
            for _ in range(100):
                self.unique_id = self.generate_unique_id()
                if not Sample.objects.filter(unique_id=self.unique_id).exists():
                    break
            else:
                raise ValueError("Could not generate a unique ID after 100 attempts.")
        super().save(*args, **kwargs)

    @staticmethod
    def generate_unique_id():
        return random.randint(1000, 9999)

    def __str__(self):
        return f"Sample {self.unique_id} - {self.customer}"
