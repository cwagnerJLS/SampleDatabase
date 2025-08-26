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
from samples.sharepoint_config import TEST_MODE_EMAIL
from samples.EditExcelSharepoint import (
    get_existing_ids_with_rows,
    get_cell_value,
    find_excel_file
)
from samples.services.auth_service import get_sharepoint_token
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID
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
                    
                    # Get existing IDs with their row numbers from column A
                    existing_ids = get_existing_ids_with_rows(
                        access_token, library_id, file_id, worksheet_name, start_row=8
                    )
                    
                    # For each ID found in column A, check if column C is empty
                    for sample_id, row_num in existing_ids.items():
                        # Check if column C is empty for this row
                        cell_value = get_cell_value(
                            access_token, library_id, file_id, worksheet_name, f"C{row_num}"
                        )
                        
                        # If column C is empty or None, documentation is incomplete
                        if not cell_value or (isinstance(cell_value, str) and cell_value.strip() == ''):
                            # Find the sample and add to incomplete list
                            try:
                                sample = Sample.objects.get(unique_id=sample_id)
                                incomplete.append({
                                    'sample': sample,
                                    'opportunity': opportunity_number,
                                    'row': row_num
                                })
                                logger.debug(f"Sample {sample_id} in row {row_num} has no data in column C")
                            except Sample.DoesNotExist:
                                logger.warning(f"Sample {sample_id} in Excel but not in database")
                    
                    # Also check if any samples in database are missing from Excel
                    db_samples = Sample.objects.filter(opportunity_number=opportunity_number)
                    for sample in db_samples:
                        if str(sample.unique_id) not in existing_ids:
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
        
        # No Location Section
        html += "<h2>📍 Samples Without Storage Location</h2>"
        if data['no_location']:
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
            for sample in data['no_location']:
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
        
        # No Images Section
        html += "<h2>📷 Samples Without Images</h2>"
        if data['no_images']:
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
            for sample in data['no_images']:
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
        
        # Incomplete Documentation Section
        html += "<h2>📝 Samples with Incomplete Excel Documentation</h2>"
        if data['incomplete_documentation']:
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
            for item in data['incomplete_documentation']:
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
        """Send the audit report email"""
        subject = f"Weekly Sample Audit Report - {timezone.now().strftime('%B %d, %Y')}"
        
        # Send to TEST_MODE_EMAIL (cwagner@jlsautomation.com)
        recipient = TEST_MODE_EMAIL
        
        self.stdout.write(f'Sending report to {recipient}...')
        
        try:
            send_email(
                subject=subject,
                body=html_content,
                recipient_email=recipient
            )
            self.stdout.write(self.style.SUCCESS(f'Report sent to {recipient}'))
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise