
from django.core.management.base import BaseCommand
from django.db.models import Q
from samples.models import Opportunity
from samples.tasks import find_sample_info_folder_url

class Command(BaseCommand):
    help = "Populates sample_info_url and sample_info_id for each Opportunity if missing."

    def handle(self, *args, **options):
        # Filter for opportunities missing URL or folder ID
        opportunities = Opportunity.objects.filter(
            Q(sample_info_url__isnull=True) | Q(sample_info_url='') |
            Q(sample_info_id__isnull=True) | Q(sample_info_id='')
        )

        for opp in opportunities:
            # Call the task to search SharePoint for the Sample Info folder
            find_sample_info_folder_url.delay(opp.customer, opp.opportunity_number)

        self.stdout.write(self.style.SUCCESS(f"Queued folder searches for {opportunities.count()} opportunities."))
