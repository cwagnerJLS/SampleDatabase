import random
from django.db import models
from django.db import transaction, IntegrityError

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
            ('Walk-in Freezer', 'Walk-in Freezer')
        ]
    )
    quantity = models.IntegerField(default=1)
    description = models.TextField(default="No description")
    audit = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.unique_id:
            for _ in range(100):
                self.unique_id = self.generate_unique_id()
                try:
                    with transaction.atomic():
                        super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    continue
            else:
                raise IntegrityError("Could not generate a unique ID after 100 attempts.")
        else:
            super().save(*args, **kwargs)

    @staticmethod
    def generate_unique_id():
        return random.randint(1000, 9999)

    def __str__(self):
        return f"Sample {self.unique_id} - {self.customer}"
