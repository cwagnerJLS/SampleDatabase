"""
Management command to send weekly audit report email.
Runs every Monday at 8 AM via cron job.
Reports on:
- Samples needing audit
- Samples without location
- Samples without images
- Samples with incomplete Excel documentation
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from samples.models import Sample, SampleImage, Opportunity
from samples.email_utils import send_email
from samples.sharepoint_config import TEST_MODE_EMAIL, INTERNAL_TEST_LAB_EMAILS
from samples.EditExcelSharepoint import (
    get_existing_ids_with_rows,
    get_cell_value,
    get_range_values,
    find_excel_file
)
from samples.services.auth_service import get_sharepoint_token
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, SALES_ENGINEERING_LIBRARY_ID
from samples.utils.sharepoint_api import FolderAPIClient
import logging
import re

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send weekly audit report email with samples needing attention'

    def handle(self, *args, **options):
        """Main command handler"""
        try:
            self.stdout.write('Starting weekly audit report generation...')
            
            # Collect all audit data
            audit_data = self.collect_audit_data()
            
            # Generate HTML report
            html_content = self.generate_html_report(audit_data)
            
            # Send email
            self.send_report_email(html_content)
            
            self.stdout.write(self.style.SUCCESS('Weekly audit report sent successfully'))
            
        except Exception as e:
            logger.error(f"Error generating weekly audit report: {e}")
            self.stdout.write(self.style.ERROR(f'Failed to send weekly audit report: {e}'))

    def collect_audit_data(self):
        """Collect all data needed for the audit report"""
        data = {
            'overdue_audits': [],
            'upcoming_audits': [],
            'no_location': [],
            'no_images': [],
            'incomplete_documentation': [],
            'unexported_opportunities': [],
            'report_date': timezone.now()
        }
        
        # Get all active samples
        all_samples = Sample.objects.all()
        
        for sample in all_samples:
            # Check audit status
            if sample.audit_due_date:
                days_until = sample.days_until_audit()
                if days_until is not None:
                    if days_until < 0:
                        # Overdue
                        data['overdue_audits'].append({
                            'sample': sample,
                            'days_overdue': abs(days_until),
                            'due_date': sample.audit_due_date
                        })
                    elif days_until <= 7:
                        # Due soon
                        data['upcoming_audits'].append({
                            'sample': sample,
                            'days_until': days_until,
                            'due_date': sample.audit_due_date
                        })
            
            # Check for missing location (including various invalid values)
            invalid_locations = [None, '', 'Choose a location', 'Choose a Location', 'remove']
            if sample.storage_location in invalid_locations:
                data['no_location'].append(sample)
            
            # Check for missing images
            image_count = SampleImage.objects.filter(sample=sample).count()
            if image_count == 0:
                data['no_images'].append(sample)
        
        # Sort audit lists
        data['overdue_audits'].sort(key=lambda x: x['days_overdue'], reverse=True)
        data['upcoming_audits'].sort(key=lambda x: x['days_until'])
        
        # Check Excel documentation (this will be implemented next)
        data['incomplete_documentation'] = self.check_excel_documentation()
        
        # Check export status
        data['unexported_opportunities'] = self.check_export_status()
        
        return data

    def check_excel_documentation(self):
        """Check SharePoint Excel files for incomplete documentation"""
        incomplete = []
        
        try:
            # Get SharePoint token
            access_token = get_sharepoint_token()
            if not access_token:
                logger.error("Failed to get SharePoint token for Excel checking")
                return incomplete
            
            # Get all unique opportunity numbers that have samples
            opportunity_numbers_with_samples = Sample.objects.values_list(
                'opportunity_number', flat=True
            ).distinct()
            
            # Use TEST_ENGINEERING_LIBRARY_ID like in tasks.py
            library_id = TEST_ENGINEERING_LIBRARY_ID
            
            self.stdout.write(f'Checking {len(opportunity_numbers_with_samples)} opportunities for Excel documentation...')
            
            for opportunity_number in opportunity_numbers_with_samples:
                try:
                    # Find the Excel file for this opportunity
                    file_id = find_excel_file(
                        access_token, library_id, opportunity_number
                    )
                    
                    if not file_id:
                        # No Excel file means documentation hasn't been created yet
                        # Add all samples from this opportunity as incomplete
                        samples = Sample.objects.filter(opportunity_number=opportunity_number)
                        for sample in samples:
                            incomplete.append({
                                'sample': sample,
                                'opportunity': opportunity_number,
                                'row': 'No Excel file found'
                            })
                        logger.warning(f"No Excel file found for opportunity {opportunity_number}")
                        continue
                    
                    # Use the standard worksheet name
                    worksheet_name = "Sheet1"  # Default worksheet name
                    
                    # OPTIMIZED: Get ALL data (columns A, B, C) in ONE API call
                    all_data = get_range_values(
                        access_token, library_id, file_id, worksheet_name, "A8:C5000"
                    )
                    
                    # Process all rows in memory (no more API calls!)
                    excel_samples = {}
                    for idx, row in enumerate(all_data):
                        if not row or len(row) == 0 or not row[0]:  # Skip empty rows
                            continue
                        
                        row_num = 8 + idx
                        sample_id = str(row[0]).strip()
                        
                        # Check if column C has data
                        has_documentation = len(row) > 2 and row[2] and str(row[2]).strip()
                        
                        excel_samples[sample_id] = {
                            'row': row_num,
                            'documented': bool(has_documentation)
                        }
                    
                    # Check for incomplete documentation
                    for sample_id, info in excel_samples.items():
                        if not info['documented']:
                            try:
                                sample = Sample.objects.get(unique_id=sample_id)
                                incomplete.append({
                                    'sample': sample,
                                    'opportunity': opportunity_number,
                                    'row': info['row']
                                })
                                logger.debug(f"Sample {sample_id} in row {info['row']} has no data in column C")
                            except Sample.DoesNotExist:
                                logger.warning(f"Sample {sample_id} in Excel but not in database")
                    
                    # Also check if any samples in database are missing from Excel
                    db_samples = Sample.objects.filter(opportunity_number=opportunity_number)
                    for sample in db_samples:
                        if str(sample.unique_id) not in excel_samples:
                            incomplete.append({
                                'sample': sample,
                                'opportunity': opportunity_number,
                                'row': 'Not in Excel'
                            })
                            logger.debug(f"Sample {sample.unique_id} not found in Excel file")
                                
                except Exception as e:
                    logger.error(f"Error checking Excel for opportunity {opportunity_number}: {e}")
                    # If there's an error accessing the Excel, report all samples as potentially incomplete
                    samples = Sample.objects.filter(opportunity_number=opportunity_number)
                    for sample in samples:
                        incomplete.append({
                            'sample': sample,
                            'opportunity': opportunity_number,
                            'row': f'Error: {str(e)[:50]}'
                        })
                    continue
                    
        except Exception as e:
            logger.error(f"Error in check_excel_documentation: {e}")
            self.stdout.write(self.style.ERROR(f'Error checking Excel documentation: {e}'))
        
        self.stdout.write(f'Found {len(incomplete)} samples with incomplete documentation')
        return incomplete

    def check_export_status(self):
        """
        Check which opportunities have not been exported by verifying files in SharePoint.
        Only checks if SOURCE files exist in destination - ignores extra files in destination.
        """
        unexported = []
        
        try:
            # Get SharePoint token
            access_token = get_sharepoint_token()
            if not access_token:
                logger.error("Failed to get SharePoint token for export checking")
                return unexported
            
            # Get unique opportunity numbers from current samples in inventory
            # Group samples by opportunity number to get one representative sample per opportunity
            from django.db.models import Count
            opportunities_in_inventory = (
                Sample.objects.values('opportunity_number')
                .annotate(sample_count=Count('id'))
                .order_by('opportunity_number')
            )
            
            self.stdout.write(f'Checking export status for {len(opportunities_in_inventory)} opportunities with current inventory...')
            
            for opp_data in opportunities_in_inventory:
                try:
                    opp_number = opp_data['opportunity_number']
                    
                    # Get a representative sample for this opportunity to get metadata
                    sample = Sample.objects.filter(opportunity_number=opp_number).first()
                    
                    # Check if opportunity has sample_info_id configured
                    # We need to get this from Opportunity table or skip if not available
                    try:
                        opportunity = Opportunity.objects.get(opportunity_number=opp_number)
                        sample_info_id = opportunity.sample_info_id
                    except Opportunity.DoesNotExist:
                        # No opportunity record, can't export without destination
                        unexported.append({
                            'opportunity_number': opp_number,
                            'customer': sample.customer if sample else 'Unknown',
                            'rsm': sample.rsm if sample else 'Unknown',
                            'reason': 'No opportunity record found',
                            'source_file_count': 0,
                            'exported_count': 0,
                            'missing_files': [],
                            'export_percentage': 0
                        })
                        continue
                    
                    # Skip if no Sample Info folder ID (destination not set up)
                    if not sample_info_id:
                        unexported.append({
                            'opportunity_number': opp_number,
                            'customer': sample.customer if sample else 'Unknown',
                            'rsm': sample.rsm if sample else 'Unknown',
                            'reason': 'No Sample Info folder configured',
                            'source_file_count': 0,
                            'exported_count': 0,
                            'missing_files': [],
                            'export_percentage': 0
                        })
                        continue
                    
                    # 1. Check source folder (Test Engineering)
                    # Get the folder name for this opportunity
                    from samples.utils.folder_utils import get_sharepoint_folder_name
                    folder_name = get_sharepoint_folder_name(opportunity) if opportunity else opp_number
                    
                    source_folder_id = FolderAPIClient.find_folder_by_name(
                        TEST_ENGINEERING_LIBRARY_ID, 
                        None, 
                        folder_name, 
                        access_token
                    )
                    
                    if not source_folder_id:
                        logger.debug(f"No source folder found for opportunity {opp_number}")
                        continue
                    
                    # Find Samples subfolder
                    samples_folder_id = FolderAPIClient.find_folder_by_name(
                        TEST_ENGINEERING_LIBRARY_ID,
                        source_folder_id,
                        "Samples",
                        access_token
                    )
                    
                    if not samples_folder_id:
                        logger.debug(f"No Samples folder found for opportunity {opp_number}")
                        continue
                    
                    # List source files
                    source_files = FolderAPIClient.list_children(
                        TEST_ENGINEERING_LIBRARY_ID,
                        samples_folder_id,
                        access_token
                    )
                    
                    # Helper function to normalize file names for comparison
                    def normalize_filename(filename):
                        """Normalize filename by removing spaces before parentheses and converting to lowercase"""
                        # Remove spaces before parentheses (e.g., "4071 (1).jpg" -> "4071(1).jpg")
                        import re
                        normalized = re.sub(r'\s+\(', '(', filename)
                        return normalized.lower()
                    
                    # Get source file names (only files, not folders)
                    source_file_names = set()
                    source_file_names_original = {}  # Keep original names for reporting
                    for item in source_files:
                        if "folder" not in item:
                            original_name = item.get("name", "")
                            normalized_name = normalize_filename(original_name)
                            source_file_names.add(normalized_name)
                            source_file_names_original[normalized_name] = original_name
                    
                    if not source_file_names:
                        logger.debug(f"No files in source folder for opportunity {opp_number}")
                        continue
                    
                    # 2. Check destination folder (Sales Engineering)
                    destination_files = FolderAPIClient.list_children(
                        SALES_ENGINEERING_LIBRARY_ID,
                        sample_info_id,
                        access_token
                    )
                    
                    # Get destination file names
                    destination_file_names = set()
                    for item in destination_files:
                        if "folder" not in item:
                            original_name = item.get("name", "")
                            normalized_name = normalize_filename(original_name)
                            destination_file_names.add(normalized_name)
                    
                    # 3. ONLY check if source files exist in destination
                    # We don't care about extra files in destination
                    missing_files = []
                    exported_count = 0
                    
                    for source_file in source_file_names:
                        if source_file in destination_file_names:
                            exported_count += 1
                        else:
                            # Use the original filename for reporting
                            original_name = source_file_names_original.get(source_file, source_file)
                            missing_files.append(original_name)
                    
                    # 4. Only report if there are missing source files
                    if missing_files:
                        export_percentage = int((exported_count / len(source_file_names)) * 100)
                        
                        unexported.append({
                            'opportunity_number': opp_number,
                            'customer': sample.customer if sample else 'Unknown',
                            'rsm': sample.rsm if sample else 'Unknown',
                            'reason': 'Files not exported' if exported_count > 0 else 'Never exported',
                            'source_file_count': len(source_file_names),
                            'exported_count': exported_count,
                            'missing_files': missing_files,
                            'export_percentage': export_percentage
                        })
                        
                        logger.debug(
                            f"Opportunity {opp_number}: {exported_count}/{len(source_file_names)} "
                            f"files exported ({export_percentage}%)"
                        )
                    
                    # If all source files are in destination, it's fully exported
                    # We don't add it to the unexported list, regardless of extra files
                    
                except Exception as e:
                    logger.error(f"Error checking export status for opportunity {opp_number}: {e}")
                    unexported.append({
                        'opportunity_number': opp_number,
                        'customer': sample.customer if sample else 'Unknown',
                        'rsm': sample.rsm if sample else 'Unknown',
                        'reason': f'Error checking: {str(e)[:50]}',
                        'source_file_count': 0,
                        'exported_count': 0,
                        'missing_files': [],
                        'export_percentage': 0
                    })
        
        except Exception as e:
            logger.error(f"Error in check_export_status: {e}")
            self.stdout.write(self.style.ERROR(f'Error checking export status: {e}'))
        
        self.stdout.write(f'Found {len(unexported)} opportunities with unexported files')
        return unexported

    def generate_html_report(self, data):
        """Generate HTML content for the email report"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                h1 {{
                    color: #667eea;
                    border-bottom: 2px solid #667eea;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #764ba2;
                    margin-top: 30px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                th {{
                    background-color: #667eea;
                    color: white;
                    padding: 12px;
                    text-align: left;
                }}
                td {{
                    padding: 10px;
                    border-bottom: 1px solid #ddd;
                }}
                tr:hover {{
                    background-color: #f5f5f5;
                }}
                .overdue {{
                    color: #dc3545;
                    font-weight: bold;
                }}
                .warning {{
                    color: #ffc107;
                    font-weight: bold;
                }}
                .summary {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .no-data {{
                    color: #28a745;
                    font-style: italic;
                }}
            </style>
        </head>
        <body>
            <h1>Weekly Sample Audit Report</h1>
            <p>Report generated on: {data['report_date'].strftime('%B %d, %Y at %I:%M %p')}</p>
            
            <div class="summary">
                <h3>Summary</h3>
                <ul>
                    <li>{len(data['overdue_audits'])} samples overdue for audit</li>
                    <li>{len(data['upcoming_audits'])} samples due for audit within 7 days</li>
                    <li>{len(data['no_location'])} samples without storage location</li>
                    <li>{len(data['no_images'])} samples without images</li>
                    <li>{len(data['incomplete_documentation'])} samples with incomplete documentation</li>
                    <li><strong>{len(data['unexported_opportunities'])} opportunities not fully exported</strong></li>
                </ul>
            </div>
        """
        
        # Overdue Audits Section
        html += "<h2>🚨 Overdue Audits</h2>"
        if data['overdue_audits']:
            html += """
            <table>
                <tr>
                    <th>Sample ID</th>
                    <th>Customer</th>
                    <th>Opportunity</th>
                    <th>Location</th>
                    <th>Due Date</th>
                    <th>Days Overdue</th>
                </tr>
            """
            for item in data['overdue_audits']:
                sample = item['sample']
                html += f"""
                <tr>
                    <td>{sample.unique_id}</td>
                    <td>{sample.customer}</td>
                    <td>{sample.opportunity_number}</td>
                    <td>{sample.storage_location or 'Not assigned'}</td>
                    <td>{item['due_date'].strftime('%m/%d/%Y')}</td>
                    <td class="overdue">{item['days_overdue']} days</td>
                </tr>
                """
            html += "</table>"
        else:
            html += "<p class='no-data'>No overdue audits</p>"
        
        # Upcoming Audits Section
        html += "<h2>⏰ Upcoming Audits (Due within 7 days)</h2>"
        if data['upcoming_audits']:
            html += """
            <table>
                <tr>
                    <th>Sample ID</th>
                    <th>Customer</th>
                    <th>Opportunity</th>
                    <th>Location</th>
                    <th>Due Date</th>
                    <th>Days Until Due</th>
                </tr>
            """
            for item in data['upcoming_audits']:
                sample = item['sample']
                html += f"""
                <tr>
                    <td>{sample.unique_id}</td>
                    <td>{sample.customer}</td>
                    <td>{sample.opportunity_number}</td>
                    <td>{sample.storage_location or 'Not assigned'}</td>
                    <td>{item['due_date'].strftime('%m/%d/%Y')}</td>
                    <td class="warning">{item['days_until']} days</td>
                </tr>
                """
            html += "</table>"
        else:
            html += "<p class='no-data'>No audits due in the next 7 days</p>"
        
        # No Location Section - Grouped by Opportunity
        html += "<h2>📍 Samples Without Storage Location</h2>"
        if data['no_location']:
            # Group samples by opportunity number
            from collections import defaultdict
            grouped_by_opp = defaultdict(list)
            for sample in data['no_location']:
                grouped_by_opp[sample.opportunity_number].append(sample)
            
            html += """
            <table>
                <tr>
                    <th>Sample ID</th>
                    <th>Customer</th>
                    <th>Opportunity</th>
                    <th>Date Received</th>
                    <th>Description</th>
                </tr>
            """
            
            # Sort opportunities for consistent display
            for opportunity in sorted(grouped_by_opp.keys()):
                samples = grouped_by_opp[opportunity]
                for sample in samples:
                    html += f"""
                    <tr>
                        <td>{sample.unique_id}</td>
                        <td>{sample.customer}</td>
                        <td>{sample.opportunity_number}</td>
                        <td>{sample.date_received.strftime('%m/%d/%Y')}</td>
                        <td>{sample.description[:50]}{'...' if len(sample.description) > 50 else ''}</td>
                    </tr>
                    """
            html += "</table>"
        else:
            html += "<p class='no-data'>All samples have assigned storage locations</p>"
        
        # No Images Section - Grouped by Opportunity
        html += "<h2>📷 Samples Without Images</h2>"
        if data['no_images']:
            # Group samples by opportunity number
            from collections import defaultdict
            grouped_by_opp = defaultdict(list)
            for sample in data['no_images']:
                grouped_by_opp[sample.opportunity_number].append(sample)
            
            html += """
            <table>
                <tr>
                    <th>Sample ID</th>
                    <th>Customer</th>
                    <th>Opportunity</th>
                    <th>Date Received</th>
                    <th>RSM</th>
                </tr>
            """
            
            # Sort opportunities for consistent display
            for opportunity in sorted(grouped_by_opp.keys()):
                samples = grouped_by_opp[opportunity]
                for sample in samples:
                    html += f"""
                    <tr>
                        <td>{sample.unique_id}</td>
                        <td>{sample.customer}</td>
                        <td>{sample.opportunity_number}</td>
                        <td>{sample.date_received.strftime('%m/%d/%Y')}</td>
                        <td>{sample.rsm}</td>
                    </tr>
                    """
            html += "</table>"
        else:
            html += "<p class='no-data'>All samples have images uploaded</p>"
        
        # Incomplete Documentation Section - Grouped by Opportunity
        html += "<h2>📝 Samples with Incomplete Excel Documentation</h2>"
        if data['incomplete_documentation']:
            # Group samples by opportunity number
            from collections import defaultdict
            grouped_by_opp = defaultdict(list)
            for item in data['incomplete_documentation']:
                grouped_by_opp[item['opportunity']].append(item)
            
            html += """
            <table>
                <tr>
                    <th>Sample ID</th>
                    <th>Customer</th>
                    <th>Opportunity</th>
                    <th>Excel Row</th>
                    <th>Date Received</th>
                </tr>
            """
            
            # Sort opportunities for consistent display
            for opportunity in sorted(grouped_by_opp.keys()):
                items = grouped_by_opp[opportunity]
                for item in items:
                    sample = item['sample']
                    html += f"""
                    <tr>
                        <td>{sample.unique_id}</td>
                        <td>{sample.customer}</td>
                        <td>{item['opportunity']}</td>
                        <td>{'Row ' + str(item['row']) if isinstance(item['row'], int) else item['row']}</td>
                        <td>{sample.date_received.strftime('%m/%d/%Y')}</td>
                    </tr>
                    """
            html += "</table>"
        else:
            html += "<p class='no-data'>All samples have complete Excel documentation</p>"
        
        # Unexported Opportunities Section
        html += "<h2>📤 Opportunities Not Yet Exported</h2>"
        if data['unexported_opportunities']:
            html += """
            <table>
                <tr>
                    <th>Opportunity</th>
                    <th>Customer</th>
                    <th>RSM</th>
                    <th>Status</th>
                    <th>Export Progress</th>
                    <th>Missing Files</th>
                </tr>
            """
            for item in data['unexported_opportunities']:
                # Determine status badge color
                if item['reason'] == 'Never exported':
                    status_class = 'overdue'
                elif item['reason'] == 'No Sample Info folder configured':
                    status_class = 'warning'
                else:
                    status_class = ''
                
                # Progress bar color
                progress = item.get('export_percentage', 0)
                if progress == 0:
                    bar_color = '#dc3545'  # Red
                elif progress < 100:
                    bar_color = '#ffc107'  # Yellow
                else:
                    bar_color = '#28a745'  # Green (shouldn't happen as fully exported won't be in list)
                
                # Format missing files list
                missing_files = item.get('missing_files', [])
                if missing_files:
                    # Show count and first few files
                    file_display = f"{len(missing_files)} files"
                    file_details = ', '.join(missing_files[:3])
                    if len(missing_files) > 3:
                        file_details += f' (+{len(missing_files) - 3} more)'
                else:
                    file_display = "N/A"
                    file_details = ""
                
                html += f"""
                <tr>
                    <td>{item['opportunity_number']}</td>
                    <td>{item['customer']}</td>
                    <td>{item['rsm']}</td>
                    <td class="{status_class}">{item['reason']}</td>
                    <td>
                        <div style="display: flex; align-items: center;">
                            <div style="width: 100px; background-color: #e0e0e0; border-radius: 5px; overflow: hidden;">
                                <div style="width: {progress}%; background-color: {bar_color}; height: 20px;"></div>
                            </div>
                            <span style="margin-left: 10px;">
                                {item['exported_count']}/{item['source_file_count']} ({progress}%)
                            </span>
                        </div>
                    </td>
                    <td title="{file_details}">{file_display}</td>
                </tr>
                """
            html += "</table>"
        else:
            html += "<p class='no-data'>All opportunities with samples have been exported</p>"
        
        html += """
            <hr>
            <p style="margin-top: 30px; color: #666;">
                This is an automated report generated by the Sample Database System.<br>
                To update sample information, scan the QR code on the sample label or visit the database directly.
            </p>
        </body>
        </html>
        """
        
        return html

    def send_report_email(self, html_content):
        """Send the audit report email to Internal Test Lab members"""
        subject = f"Weekly Sample Audit Report - {timezone.now().strftime('%B %d, %Y')}"
        
        # Get Internal Test Lab email recipients
        recipients = INTERNAL_TEST_LAB_EMAILS
        
        self.stdout.write(f'Sending report to Internal Test Lab group ({len(recipients)} recipients)...')
        self.stdout.write(f'Recipients: {", ".join(recipients)}')
        
        # Send single email to all recipients
        try:
            send_email(
                subject=subject,
                body=html_content,
                recipient_email=recipients  # Pass list of recipients
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Report sent to all Internal Test Lab members'))
        except Exception as e:
            logger.error(f"Failed to send audit report email: {e}")
            self.stdout.write(self.style.ERROR(f'✗ Failed to send report: {e}'))
        
        self.stdout.write(self.style.SUCCESS(f'Report distribution complete'))