from django.core.management.base import BaseCommand
from django.db.models import Q
from samples.models import Opportunity
from samples.tasks import find_sample_info_folder_comprehensive
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = """Find SharePoint folders that are in unexpected locations.
    
    This command performs a comprehensive search across all alphabet folders
    to locate opportunity folders that may have been manually moved.
    
    Usage:
        python manage.py find_misplaced_folders                    # Check all opportunities
        python manage.py find_misplaced_folders --opp 12345        # Check specific opportunity
        python manage.py find_misplaced_folders --missing-only     # Only check opportunities without SharePoint info
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--opp',
            type=str,
            help='Specific opportunity number to search for'
        )
        parser.add_argument(
            '--missing-only',
            action='store_true',
            help='Only search for opportunities currently missing SharePoint info'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Update database with found locations'
        )

    def handle(self, *args, **options):
        opp_number = options.get('opp')
        missing_only = options.get('missing_only')
        fix = options.get('fix')
        
        # Determine which opportunities to check
        if opp_number:
            # Check specific opportunity
            try:
                opportunities = Opportunity.objects.filter(opportunity_number=opp_number)
                if not opportunities.exists():
                    self.stdout.write(self.style.ERROR(f"Opportunity {opp_number} not found"))
                    return
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error finding opportunity: {e}"))
                return
        elif missing_only:
            # Only check opportunities missing SharePoint info
            opportunities = Opportunity.objects.filter(
                Q(sample_info_url__isnull=True) | Q(sample_info_url='') |
                Q(sample_info_id__isnull=True) | Q(sample_info_id='')
            )
        else:
            # Check all opportunities
            opportunities = Opportunity.objects.all()
        
        if not opportunities.exists():
            self.stdout.write(self.style.SUCCESS("No opportunities to check"))
            return
        
        self.stdout.write(f"Checking {opportunities.count()} opportunities...")
        
        misplaced = []
        not_found = []
        correct = []
        
        for opp in opportunities:
            self.stdout.write(f"Searching for {opp.opportunity_number} (Customer: {opp.customer})...")
            
            # Perform comprehensive search
            result = find_sample_info_folder_comprehensive(
                opp.customer,
                opp.opportunity_number,
                search_all_letters=True
            )
            
            if result.get('status') == 'found':
                letter_folder = result.get('letter_folder')
                expected_letter = result.get('expected_letter')
                
                if letter_folder != expected_letter:
                    misplaced.append({
                        'opp': opp,
                        'found_in': letter_folder,
                        'expected': expected_letter,
                        'url': result.get('sample_info_url')
                    })
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠️  MISPLACED: {opp.opportunity_number} found under '{letter_folder}' "
                            f"instead of '{expected_letter}'"
                        )
                    )
                else:
                    correct.append(opp)
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Found in correct location under '{letter_folder}'")
                    )
                
                # Update database if --fix flag is set
                if fix and (not opp.sample_info_id or not opp.sample_info_url):
                    opp.sample_info_id = result.get('sample_info_id')
                    opp.sample_info_url = result.get('sample_info_url')
                    opp.save()
                    self.stdout.write(self.style.SUCCESS(f"    Updated database with SharePoint info"))
                    
            elif result.get('status') == 'not_found':
                not_found.append(opp)
                self.stdout.write(
                    self.style.ERROR(f"  ✗ NOT FOUND in any location")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"  Error: {result.get('message', 'Unknown error')}")
                )
        
        # Print summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(f"SUMMARY"))
        self.stdout.write("="*60)
        self.stdout.write(f"Total checked: {opportunities.count()}")
        self.stdout.write(self.style.SUCCESS(f"Correct location: {len(correct)}"))
        self.stdout.write(self.style.WARNING(f"Misplaced: {len(misplaced)}"))
        self.stdout.write(self.style.ERROR(f"Not found: {len(not_found)}"))
        
        if misplaced:
            self.stdout.write("\n" + self.style.WARNING("MISPLACED OPPORTUNITIES:"))
            for item in misplaced:
                self.stdout.write(
                    f"  • {item['opp'].opportunity_number}: "
                    f"Found under '{item['found_in']}', expected '{item['expected']}'"
                )
                if item['url']:
                    self.stdout.write(f"    URL: {item['url']}")
        
        if not_found:
            self.stdout.write("\n" + self.style.ERROR("NOT FOUND:"))
            for opp in not_found:
                self.stdout.write(f"  • {opp.opportunity_number} ({opp.customer})")
        
        if fix:
            self.stdout.write("\n" + self.style.SUCCESS("Database has been updated where needed."))