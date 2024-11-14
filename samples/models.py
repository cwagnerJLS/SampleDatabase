import random
from django.db import models

def generate_unique_id():
    return random.randint(1000, 9999)

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
            ('Empty Case Storage', 'Empty Case Storage'),
        ]
    )
    quantity = models.IntegerField(default=1)
    description = models.TextField(default="No description")
    audit = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.unique_id:
            for _ in range(100):
                self.unique_id = generate_unique_id()
                if not Sample.objects.filter(unique_id=self.unique_id).exists():
                    break
            else:
                raise ValueError("Could not generate a unique ID after 100 attempts.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Sample {self.unique_id} - {self.customer}"

class SampleImage(models.Model):
    sample = models.ForeignKey(Sample, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='sample_images/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for Sample {self.sample.unique_id}"
