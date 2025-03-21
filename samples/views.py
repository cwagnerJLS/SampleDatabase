import logging
import json
import subprocess
from celery import chain
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse

def view_samples(request):
    # Convert samples to list of dicts, then JSON-encode.
    samples_list = list(Sample.objects.all().values())

    # If you need to format date fields, do so here.
    for entry in samples_list:
        if entry['date_received']:
            entry['date_received'] = entry['date_received'].strftime('%Y-%m-%d')

    return render(request, 'samples/view_sample.html', {
        'samples': json.dumps(samples_list, cls=DjangoJSONEncoder),
    })
from django.urls import reverse
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.base import ContentFile
import os
from .models import Sample, SampleImage, Opportunity
from .tasks import (
    delete_image_from_sharepoint,
    update_documentation_excels,
    restore_documentation_from_archive_task,  # ← Add this
    send_sample_received_email,
    create_sharepoint_folder_task,
    create_documentation_on_sharepoint_task,
    upload_full_size_images_to_sharepoint,
    find_sample_info_folder_url
)
import pandas as pd
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import base64
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import qrcode
from django.http import JsonResponse

# Configure logging
logger = logging.getLogger('samples')

def create_sample(request):
    logger.debug("Entered create_sample view")

    if request.method == 'POST':
        logger.debug("Processing POST request")
        try:
            if 'clear_db' in request.POST:
                logger.debug("Clearing database")
                Sample.objects.all().delete()
                return JsonResponse({'status': 'success', 'message': 'Database cleared'})

            # Retrieve data from POST request
            customer = request.POST.get('customer')
            rsm_full_name = request.POST.get('rsm')
            opportunity_number = request.POST.get('opportunity_number')
            description = request.POST.get('description')
            date_received = request.POST.get('date_received')
            quantity = request.POST.get('quantity')
            apps_eng = request.POST.get('apps_eng', '')

            try:
                quantity = int(quantity)
                date_received = datetime.strptime(date_received, '%Y-%m-%d').date()
            except ValueError as e:
                logger.error(f"Invalid data format: {e}")
                return JsonResponse({'status': 'error', 'error': 'Invalid data format'})

            location = "Choose a location"
            logger.debug(f"Received data: customer={customer}, rsm={rsm_full_name}, opportunity_number={opportunity_number}, "
                         f"description={description}, date_received={date_received}, quantity={quantity}, location={location}")

            # Create or update the Opportunity
            opportunity, created = Opportunity.objects.get_or_create(
                opportunity_number=opportunity_number,
                defaults={
                    'new': True,
                    'customer': customer,
                    'rsm': rsm_full_name,
                    'description': description,
                    'date_received': date_received,
                    'update': True,
                }
            )

            if created:
                pass
            else:
                # Update existing Opportunity fields if new data is provided
                updated = False
                if customer and customer != opportunity.customer:
                    opportunity.customer = customer
                    updated = True
                if rsm_full_name and rsm_full_name != opportunity.rsm:
                    opportunity.rsm = rsm_full_name
                    updated = True
                if description and description != opportunity.description:
                    opportunity.description = description
                    updated = True
                if date_received and date_received != opportunity.date_received:
                    opportunity.date_received = date_received
                    updated = True
                if updated:
                    opportunity.update = True
                    opportunity.save()
                    logger.debug(f"Opportunity {opportunity_number} updated with new data")

            # Save the Opportunity instance if it was created or updated
            if created or updated:
                opportunity.new = True
                opportunity.update = True
                opportunity.save()

            # Now, after the Opportunity is saved and up-to-date, call the task chain
            if created:
                chain(
                    create_sharepoint_folder_task.s(
                        opportunity_number=opportunity_number,
                        customer=opportunity.customer,
                        rsm=opportunity.rsm,
                        description=opportunity.description
                    ),
                    create_documentation_on_sharepoint_task.si(opportunity_number),
                    update_documentation_excels.si(opportunity_number)
                ).delay()

            else:
                chain(
                    restore_documentation_from_archive_task.si(opportunity_number),
                    update_documentation_excels.si(opportunity_number)
                ).delay()

            created_samples = []

            if quantity > 0:
                for i in range(quantity):
                    sample = Sample.objects.create(
                        date_received=date_received,
                        customer=customer,
                        rsm=rsm_full_name,
                        opportunity_number=opportunity_number,
                        description=description,
                        storage_location=location,
                        quantity=1,  # Each entry represents a single unit
                        apps_eng=apps_eng
                    )
                    created_samples.append(sample)
                logger.debug(f"Created samples: {created_samples}")

                # Update sample_ids field for the Opportunity

                # Retrieve existing sample_ids from Opportunity
                existing_sample_ids = opportunity.sample_ids.split(',') if opportunity.sample_ids else []

                # Append new sample IDs to existing sample_ids, ensuring no duplicates
                for sample in created_samples:
                    if str(sample.unique_id) not in existing_sample_ids:
                        existing_sample_ids.append(str(sample.unique_id))

                # Update the sample_ids field in Opportunity
                opportunity.sample_ids = ','.join(existing_sample_ids)
                opportunity.update = True
                opportunity.save()
            else:
                logger.debug("Quantity is zero; no samples created.")
                # Clear sample_ids for the Opportunity
                opportunity.sample_ids = ''
                opportunity.save()

            # Calculate the total quantity
            if created_samples:
                total_quantity = sum(sample.quantity for sample in created_samples)
            else:
                total_quantity = 0

            # Calculate the total quantity
            if created_samples:
                total_quantity = sum(sample.quantity for sample in created_samples)
            else:
                total_quantity = 0

            # Chain find_sample_info_folder_url + send_sample_received_email only if total_quantity > 0
            if total_quantity > 0:
                chain(
                    find_sample_info_folder_url.si(
                        opportunity.customer,
                        opportunity_number
                    ),
                    send_sample_received_email.si(
                        rsm_full_name,
                        date_received.strftime('%Y-%m-%d'),
                        opportunity_number,
                        customer,
                        total_quantity
                    )
                ).delay()
                logger.debug(f"Email sent to {rsm_full_name} regarding opportunity {opportunity_number}")
            else:
                logger.debug("Quantity is zero; email not sent.")

            # Removed separate call to update_documentation_excels

            return JsonResponse({
                'status': 'success',
                'created_samples': [
                    {
                        'unique_id': sample.unique_id,
                        'date_received': sample.date_received.strftime('%Y-%m-%d'),
                        'customer': sample.customer,
                        'rsm': sample.rsm,
                        'opportunity_number': sample.opportunity_number,
                        'description': sample.description,
                        'location': sample.storage_location
                    } for sample in created_samples
                ]
            })

        except Exception as e:
            logger.error(f"Error in create_sample view: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    logger.debug("Rendering create_sample page")

    try:
        # Call the Celery task
        update_documentation_excels.delay()

        # Retrieve all opportunity numbers from the Opportunity model
        opportunity_numbers = Opportunity.objects.values_list('opportunity_number', flat=True)


        # Path to the DocumentationTemplate.xlsm file
        template_file = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', '_Templates', 'DocumentationTemplate.xlsm')
        if not os.path.exists(template_file):
            logger.error(f"Documentation template not found at: {template_file}")

        # Define excel_file before the loop
        excel_file = os.path.join(settings.BASE_DIR, 'Apps_Database.xlsx')
        if not os.path.exists(excel_file):
            logger.error(f"Excel file not found at {excel_file}")
            return JsonResponse({'status': 'error', 'error': 'Excel file not found'}, status=500)


        # Now excel_file is defined, so you can read it
        df = pd.read_excel(excel_file)

        # Get unique customers and RSMs
        unique_customers = sorted(df['Customer'].dropna().unique())
        unique_rsms = sorted(df['RSM'].dropna().unique())

        # Convert DataFrame to JSON serializable format
        excel_data = df.to_dict(orient='records')

        # Load saved samples
        samples = list(Sample.objects.all().values())

        # Convert date_received to string format for JSON serialization
        for sample in samples:
            if isinstance(sample['date_received'], datetime):
                sample['date_received'] = sample['date_received'].strftime('%Y-%m-%d')

        logger.debug(f"Samples List: {samples}")


        return render(request, 'samples/create_sample.html', {
            'unique_customers': unique_customers,
            'unique_rsms': unique_rsms,
            'excel_data': json.dumps(excel_data, cls=DjangoJSONEncoder),
            'samples': json.dumps(samples, cls=DjangoJSONEncoder),
        })

    except Exception as e:
        logger.error(f"Error rendering create_sample page: {e}")
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

def upload_files(request):
    if request.method == 'POST' and request.FILES:
        files = request.FILES.getlist('files')
        sample_id = request.POST.get('sample_id')

        # Validate sample_id
        try:
            sample = Sample.objects.get(unique_id=sample_id)
        except Sample.DoesNotExist:
            logger.error("Sample not found with ID: %s", sample_id)
            return JsonResponse({'status': 'error', 'error': 'Sample not found'})

        image_urls = []
        image_ids = []  # Initialize the list to collect image IDs

        try:
            # Get the current count of images for the sample
            existing_images_count = SampleImage.objects.filter(sample=sample).count()
            image_count = existing_images_count

            for file in files:
                image_count += 1  # Increment image count for each new file

                # Validate file type
                if not file.content_type.startswith('image/'):
                    logger.error("Invalid file type: %s", file.content_type)
                    return JsonResponse({'status': 'error', 'error': 'Invalid file type. Only images are allowed.'})

                # Open the uploaded image
                image = Image.open(file)
                image = image.convert('RGB')  # Ensure image is in RGB mode

                # Create a thumbnail
                max_size = (200, 200)  # Set the desired thumbnail size
                image.thumbnail(max_size, resample=Image.LANCZOS)

                # Save the thumbnail to an in-memory file
                thumb_io = BytesIO()
                image.save(thumb_io, format='JPEG', quality=85)
                thumb_io.seek(0)  # Reset file pointer to the beginning

                # Create a ContentFile from the in-memory file
                image_content = ContentFile(thumb_io.read())

                # Generate the filename with ID and index number in parentheses
                filename = f"{sample.unique_id}({image_count}).jpg"

                # Save the thumbnail image to the model
                sample_image = SampleImage(sample=sample)
                sample_image.image.save(filename, image_content)
                sample_image.save()

                # Collect the URL and ID to return to the client
                image_urls.append(sample_image.image.url)
                image_ids.append(sample_image.id)  # Collect the image ID

                # Save the full-size image directly using the original file
                sample_image.full_size_image.save(filename, file)
                sample_image.save()

                # Collect the URL and ID to return to the client
                image_urls.append(sample_image.image.url)
                image_ids.append(sample_image.id)  # Collect the image ID

            # After processing all images and saving them locally, enqueue a task to upload images to SharePoint
            upload_full_size_images_to_sharepoint.delay(image_ids)

        except Exception as e:
            logger.exception("Error processing files: %s", e)
            return JsonResponse({'status': 'error', 'error': 'Error processing files.'}, status=500)

        logger.info("Files uploaded successfully for Sample ID %s", sample_id)
        return JsonResponse({
            'status': 'success',
            'message': 'Files uploaded successfully.',
            'images': image_urls,
            'image_ids': image_ids  # Include image IDs in the response
        })

    logger.error("Invalid request method: %s", request.method)
    return JsonResponse({'status': 'error', 'error': 'Invalid request method.'}, status=405)

def update_sample_location(request):
    if request.method == 'POST':
        try:
            location = request.POST.get('location')
            audit = request.POST.get('audit', 'false') == 'true'

            if 'ids' in request.POST:
                # Updating multiple samples
                ids = json.loads(request.POST.get('ids', '[]'))
                samples = Sample.objects.filter(unique_id__in=ids)

                for sample in samples:
                    if location == "remove":
                        sample.storage_location = None
                    else:
                        sample.storage_location = location
                    sample.audit = audit
                    sample.save()

                return JsonResponse({'status': 'success', 'message': 'Locations updated successfully for selected samples'})
            else:
                # Updating a single sample
                sample_id = int(request.POST.get('sample_id'))
                sample = Sample.objects.get(unique_id=sample_id)

                if location == "remove":
                    sample.storage_location = None
                else:
                    sample.storage_location = location

                sample.audit = audit
                sample.save()

                return JsonResponse({'status': 'success', 'message': 'Location updated successfully for sample'})

        except Sample.DoesNotExist:
            logger.error("Sample not found")
            return JsonResponse({'status': 'error', 'error': 'Sample not found'}, status=404)
        except ValueError as e:
            logger.error(f"Invalid data provided: {e}")
            return JsonResponse({'status': 'error', 'error': 'Invalid data provided'}, status=400)
        except Exception as e:
            logger.error(f"Error in update_sample_location: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    logger.error("Invalid request method for update_sample_location")
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=405)

def remove_from_inventory(request):
    if request.method == 'POST':
        try:
            ids = json.loads(request.POST.get('ids', '[]'))
            # Retrieve the samples to be removed from inventory
            samples_to_remove = Sample.objects.filter(unique_id__in=ids)

            # Keep track of affected opportunities
            affected_opportunity_numbers = set()

            for sample in samples_to_remove:
                opportunity_number = sample.opportunity_number
                affected_opportunity_numbers.add(opportunity_number)
                sample.delete(update_opportunity=False)

            logger.debug(f"Removed samples from inventory with IDs: {ids}")


            # After deleting the samples, check if any samples remain for each opportunity
            for opportunity_number in affected_opportunity_numbers:
                samples_remaining = Sample.objects.filter(opportunity_number=opportunity_number).exists()
                if not samples_remaining:
                    from .tasks import move_documentation_to_archive_task
                    logger.info(f"No samples remain for opportunity {opportunity_number}. Initiating cleanup tasks.")
                    move_documentation_to_archive_task.delay(opportunity_number)

            # Call the update_documentation_excels task
            update_documentation_excels.delay()

            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {e}")
            return JsonResponse({'status': 'error', 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error removing samples from inventory: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    logger.error("Invalid request method for remove_from_inventory")
    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=405)

def generate_qr_code(data):
    # Create a QR code instance
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    # Add data to the QR code
    qr.add_data(data)
    qr.make(fit=True)

    # Create an image from the QR code instance
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")

    # Encode the image to base64 string
    img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
    return img_str

def mm_to_points(mm_value):
    return mm_value * (72 / 25.4)


def generate_label(output_path, qr_data, id_value, date_received, rsm_value, description):
    label_width = mm_to_points(101.6)
    label_height = mm_to_points(50.8)
    c = canvas.Canvas(output_path, pagesize=(label_width, label_height))

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=1)
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill='black', back_color='white')
    img_buffer = BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    img_reader = ImageReader(img_buffer)

    margin = mm_to_points(5)
    qr_x = label_width / 2 + margin
    qr_y = margin
    qr_width = label_width / 2 - 2 * margin
    qr_height = label_height - 2 * margin

    c.drawImage(img_reader, qr_x, qr_y, qr_width, qr_height)

    font_bold = "Helvetica-Bold"
    font_regular = "Helvetica"
    font_size = mm_to_points(4)

    id_text = "ID: "
    c.setFont(font_bold, font_size)
    id_text_width = c.stringWidth(id_text)
    c.setFont(font_regular, font_size)
    id_value_width = c.stringWidth(id_value)
    total_id_text_width = id_text_width + id_value_width

    right_shift_offset = mm_to_points(2)
    left_half_width = (label_width / 2) - (2 * margin)
    start_x_id = margin + (left_half_width - total_id_text_width) / 2 + right_shift_offset

    c.setFont(font_bold, font_size)
    c.drawString(start_x_id, label_height - margin - mm_to_points(2), id_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_id + id_text_width, label_height - margin - mm_to_points(2), id_value)

    date_text = "Date Received: "
    c.setFont(font_bold, font_size)
    date_text_width = c.stringWidth(date_text)
    c.setFont(font_regular, font_size)
    date_value_width = c.stringWidth(date_received)
    total_date_text_width = date_text_width + date_value_width

    start_x_date = margin + (left_half_width - total_date_text_width) / 3 + right_shift_offset

    c.setFont(font_bold, font_size)
    c.drawString(start_x_date, label_height - margin - mm_to_points(8), date_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_date + date_text_width, label_height - margin - mm_to_points(8), date_received)

    rsm_text = "RSM: "
    c.setFont(font_bold, font_size)
    rsm_text_width = c.stringWidth(rsm_text)
    c.setFont(font_regular, font_size)
    rsm_value_width = c.stringWidth(rsm_value)
    total_rsm_text_width = rsm_text_width + rsm_value_width

    start_x_rsm = margin + (left_half_width - total_rsm_text_width) / 2 + right_shift_offset

    c.setFont(font_bold, font_size)
    c.drawString(start_x_rsm, label_height - margin - mm_to_points(14), rsm_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_rsm + rsm_text_width, label_height - margin - mm_to_points(14), rsm_value)

    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    normal_style.fontName = font_regular
    normal_style.fontSize = font_size
    normal_style.leading = font_size * 1.2
    normal_style.alignment = 1

    wrapped_paragraph = Paragraph(description, normal_style)
    max_text_width = label_width / 2 - 2 * margin
    text_left = margin
    text_top = label_height - margin - mm_to_points(20)  # push below RSM

    wrapped_paragraph.wrapOn(c, max_text_width, text_top - margin)
    wrapped_paragraph.drawOn(c, text_left, text_top - wrapped_paragraph.height)

    c.save()


def handle_print_request(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ids_to_print = data.get('ids', [])
            if not ids_to_print:
                return JsonResponse({'status': 'error', 'error': 'No sample IDs provided'}, status=400)

            # Use the first sample_id to determine the labels directory
            sample = Sample.objects.get(unique_id=ids_to_print[0])
            labels_dir = os.path.join(settings.BASE_DIR, 'Labels')
            os.makedirs(labels_dir, exist_ok=True)

            if not ids_to_print:
                return JsonResponse({'status': 'error', 'error': 'No sample IDs provided'}, status=400)

            for sample_id in ids_to_print:
                try:
                    sample = Sample.objects.get(unique_id=sample_id)
                except Sample.DoesNotExist:
                    logger.error(f"Sample with ID {sample_id} does not exist")
                    return JsonResponse({'status': 'error', 'error': f'Sample with ID {sample_id} does not exist'}, status=404)
                except Exception as e:
                    logger.error(f"Error retrieving sample: {e}")
                    return JsonResponse({'status': 'error', 'error': 'Error retrieving sample'}, status=500)

                try:
                    qr_url = request.build_absolute_uri(reverse('manage_sample', args=[sample.unique_id]))
                    qr_code = generate_qr_code(qr_url)
                except Exception as e:
                    logger.error(f"Error generating QR code: {e}")
                    return JsonResponse({'status': 'error', 'error': 'Failed to generate QR code'}, status=500)

                qr_url = request.build_absolute_uri(reverse('manage_sample', args=[sample.unique_id]))
                qr_code_img = qrcode.make(qr_url)
                qr_code_buffer = BytesIO()
                qr_code_img.save(qr_code_buffer, format='PNG')
                qr_code_buffer.seek(0)

                output_path = os.path.join(labels_dir, f"label_{sample.unique_id}.pdf")

                qr_data = qr_url
                id_value = str(sample.unique_id)
                date_received = sample.date_received.strftime('%Y-%m-%d')
                rsm_value = sample.rsm
                description = sample.description

                generate_label(output_path, qr_data, id_value, date_received, rsm_value, description)

                # Send the label PDF to the default printer
                try:
                    subprocess.run(['lpr', output_path], check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Error printing label for sample {sample_id}: {e}")
                    return JsonResponse({'status': 'error', 'error': f'Failed to print label for sample {sample_id}'}, status=500)

            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error in handle_print_request: {e}")
            return JsonResponse({'status': 'error', 'error': 'An unexpected error occurred'}, status=500)
    else:
        return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=405)

def manage_sample(request, sample_id):
    # Retrieve the sample or return a 404 error if not found
    sample = get_object_or_404(Sample, unique_id=sample_id)
    logger.debug(f"Accessing manage_sample for sample_id: {sample_id}")

    if request.method == 'POST':
        try:
            # Process form data
            location = request.POST.get('location')
            audit = request.POST.get('audit') == 'true'  # Check if the toggle is active

            # Update sample fields
            if location:
                if location == "remove":
                    sample.storage_location = None
                else:
                    sample.storage_location = location

            sample.audit = audit
            sample.save()
            logger.debug(f"Updated sample {sample_id}: location={sample.storage_location}, audit={sample.audit}")

            # Redirect back to the same page after POST to prevent resubmission
            return redirect('manage_sample', sample_id=sample.unique_id)
        except Exception as e:
            logger.error(f"Error updating sample {sample_id}: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    # For GET requests, render the template with the sample data
    return render(request, 'samples/manage_sample.html', {'sample': sample})

def get_sample_images(request):
    sample_id = request.GET.get('sample_id')
    try:
        sample = Sample.objects.get(unique_id=sample_id)
        images = sample.images.all()
        image_data = [
            {
                'id': image.id,
                'filename': os.path.basename(image.image.name),
                'url': request.build_absolute_uri(image.image.url),
                'full_size_url': request.build_absolute_uri(image.full_size_image.url) if image.full_size_image else None
            }
            for image in images
        ]
        return JsonResponse({'status': 'success', 'images': image_data})
    except Sample.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Sample not found'})

@csrf_exempt  # Add this if you're not using CSRF tokens properly
@require_POST
def delete_sample_image(request):
    image_id = request.POST.get('image_id')
    try:
        image = SampleImage.objects.get(id=image_id)
        # Capture the SharePoint path before deleting the local file
        full_size_name = image.full_size_image.name
        opportunity_number = image.sample.opportunity_number
        if full_size_name:
            delete_image_from_sharepoint.delay(full_size_name, opportunity_number)

        # Delete the local file + DB record
        image.delete()
        return JsonResponse({'status': 'success'})
    except SampleImage.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Image not found'})
    except Exception as e:
        logger.error(f"Error deleting image {image_id}: {e}")
        return JsonResponse({'status': 'error', 'error': 'An error occurred while deleting the image'})

def delete_samples(request):
    if request.method == 'POST':
        try:
            ids = json.loads(request.POST.get('ids', '[]'))
            # Retrieve the samples to be deleted
            samples_to_delete = Sample.objects.filter(unique_id__in=ids)

            for sample in samples_to_delete:
                sample.delete()  # Calls the delete method on each instance

            logger.debug(f"Deleted samples with IDs: {ids}")

            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {e}")
            return JsonResponse({'status': 'error', 'error': 'Invalid JSON data'}, status=400)
        except Sample.DoesNotExist as e:
            logger.error(f"Sample not found: {e}")
            return JsonResponse({'status': 'error', 'error': 'Sample not found'}, status=404)
        except Exception as e:
            logger.error(f"Error deleting samples: {e}")
            return JsonResponse({'status': 'error', 'error': 'An unexpected error occurred'}, status=500)
    else:
        logger.error("Invalid request method for delete_samples")
        return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=405)
def handle_405(request, exception=None):
    return JsonResponse({'status': 'error', 'error': 'Method Not Allowed'}, status=405)
    return JsonResponse({'status': 'error', 'error': 'Bad Request'}, status=400)

def handle_403(request, exception=None):
    return JsonResponse({'status': 'error', 'error': 'Forbidden'}, status=403)

def handle_404(request, exception=None):
    return JsonResponse({'status': 'error', 'error': 'Not Found'}, status=404)

def handle_500(request):
    return JsonResponse({'status': 'error', 'error': 'Server Error'}, status=500)
