from django.core.management.base import BaseCommand
import os
from samples.models import SampleImage

class Command(BaseCommand):
    help = "Fix incorrect image paths for Thumbnail and Full-Size images."

    def handle(self, *args, **options):
        updated_count = 0
        for si in SampleImage.objects.all():
            fixed = False

            # Fix the thumbnail image path if needed
            if si.image and not si.image.name.startswith("Thumbnails/"):
                base_filename = os.path.basename(si.image.name)
                opp_number = si.sample.opportunity_number
                si.image.name = f"Thumbnails/{opp_number}/{base_filename}"
                fixed = True

            # Fix the full-size image path if needed
            if si.full_size_image and not si.full_size_image.name.startswith("Full Size Images/"):
                base_filename = os.path.basename(si.full_size_image.name)
                opp_number = si.sample.opportunity_number
                si.full_size_image.name = f"Full Size Images/{opp_number}/{base_filename}"
                fixed = True

            if fixed:
                si.save()
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Updated paths for {updated_count} images."))
