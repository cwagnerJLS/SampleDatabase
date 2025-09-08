
from django.core.management.base import BaseCommand
from django.db.models import Q
from samples.models import Opportunity
from samples.tasks import find_sample_info_folder_comprehensive
from celery import group
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Populates sample_info_url and sample_info_id for each Opportunity if missing."

    def handle(self, *args, **options):
        # Filter for opportunities missing URL or folder ID
        opportunities = Opportunity.objects.filter(
            Q(sample_info_url__isnull=True) | Q(sample_info_url='') |
            Q(sample_info_id__isnull=True) | Q(sample_info_id='')
        )

        if not opportunities.exists():
            self.stdout.write(self.style.SUCCESS("No opportunities need SharePoint info population."))
            return

        self.stdout.write(f"Found {opportunities.count()} opportunities needing SharePoint info...")
        
        # Phase 1: Try primary search (expected letter) for all opportunities
        primary_search_tasks = []
        opp_list = list(opportunities)
        
        for opp in opp_list:
            # Queue primary search (only search expected letter)
            task = find_sample_info_folder_comprehensive.s(
                opp.customer, 
                opp.opportunity_number, 
                search_all_letters=False
            )
            primary_search_tasks.append(task)
        
        # Execute all primary searches in parallel
        if primary_search_tasks:
            self.stdout.write(f"Phase 1: Searching expected locations for {len(primary_search_tasks)} opportunities...")
            job = group(primary_search_tasks)
            results = job.apply_async()
            
            # Wait for results and collect failures
            primary_results = results.get(timeout=300)  # 5 minute timeout
            
            # Analyze results and find failures
            failed_opportunities = []
            found_count = 0
            
            for i, result in enumerate(primary_results):
                if result.get('status') == 'found':
                    found_count += 1
                    if result.get('letter_folder') != result.get('expected_letter'):
                        self.stdout.write(
                            self.style.WARNING(
                                f"Found {opp_list[i].opportunity_number} in unexpected location: "
                                f"{result.get('letter_folder')} instead of {result.get('expected_letter')}"
                            )
                        )
                elif result.get('status') == 'not_found':
                    failed_opportunities.append(opp_list[i])
            
            self.stdout.write(self.style.SUCCESS(f"Phase 1 complete: Found {found_count} opportunities in expected locations"))
            
            # Phase 2: Comprehensive search for failures
            if failed_opportunities:
                self.stdout.write(f"Phase 2: Comprehensive search for {len(failed_opportunities)} not found in expected locations...")
                
                comprehensive_tasks = []
                for opp in failed_opportunities:
                    # Queue comprehensive search (all letters)
                    task = find_sample_info_folder_comprehensive.s(
                        opp.customer,
                        opp.opportunity_number,
                        search_all_letters=True
                    )
                    comprehensive_tasks.append(task)
                
                # Execute comprehensive searches in parallel
                job = group(comprehensive_tasks)
                comprehensive_results = job.apply_async()
                final_results = comprehensive_results.get(timeout=600)  # 10 minute timeout
                
                # Report final results
                phase2_found = 0
                still_not_found = []
                
                for i, result in enumerate(final_results):
                    if result.get('status') == 'found':
                        phase2_found += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"Found {failed_opportunities[i].opportunity_number} under "
                                f"'{result.get('letter_folder')}' instead of expected '{result.get('expected_letter')}'"
                            )
                        )
                    else:
                        still_not_found.append(failed_opportunities[i].opportunity_number)
                
                self.stdout.write(self.style.SUCCESS(f"Phase 2 complete: Found {phase2_found} additional opportunities"))
                
                if still_not_found:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Could not find {len(still_not_found)} opportunities in any location: {', '.join(still_not_found)}"
                        )
                    )
            
            total_found = found_count + (phase2_found if failed_opportunities else 0)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Population complete: Found {total_found} of {opportunities.count()} opportunities"
                )
            )
