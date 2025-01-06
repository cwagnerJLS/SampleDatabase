import shutil
import os
import logging
import json
import csv
import subprocess
import shutil
from .tasks import send_sample_received_email  # Add this import at the top
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.views.decorators.http import require_POST
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import os
from .models import Sample, SampleImage
from .tasks import save_full_size_image  # Import the Celery task
import pandas as pd
import qrcode
import xlwings as xw
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import base64
from io import BytesIO
from PIL import Image
import tempfile
from django.http import HttpResponse, Http404
from reportlab.lib.pagesizes import inch
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import qrcode

# Configure logging
logger = logging.getLogger(__name__)

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

            # Create directory in OneDrive_Sync named after the opportunity number
            directory_path = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', opportunity_number)
            if not os.path.exists(directory_path):
                os.makedirs(directory_path)
            # Copy DocumentationTemplate.xlsm into the new directory and rename it
            template_file = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', '_Templates', 'DocumentationTemplate.xlsm')
            logger.debug(f"Looking for template file at: {template_file}")

            if os.path.exists(template_file):
                logger.debug("Template file exists.")
                new_filename = f"Documentation_{opportunity_number}.xlsm"
                destination_file = os.path.join(directory_path, new_filename)
                try:
                    shutil.copy(template_file, destination_file)
                    logger.debug(f"Copied template file to: {destination_file}")
                except PermissionError as e:
                    logger.error(f"Permission error while copying template file: {e}")
                    return JsonResponse({'status': 'error', 'error': 'Permission denied when copying template file'}, status=500)
            else:
                base_dir_contents = os.listdir(settings.BASE_DIR)
                logger.debug(f"Contents of BASE_DIR ({settings.BASE_DIR}): {base_dir_contents}")
                logger.error(f"Documentation template not found at: {template_file}")
                return JsonResponse({'status': 'error', 'error': f'Documentation template not found at {template_file}'}, status=500)

            try:
                quantity = int(quantity)
                date_received = datetime.strptime(date_received, '%Y-%m-%d').date()
            except ValueError as e:
                logger.error(f"Invalid data format: {e}")
                return JsonResponse({'status': 'error', 'error': 'Invalid data format'})

            location = "Choose a location"
            logger.debug(f"Received data: customer={customer}, rsm={rsm_full_name}, opportunity_number={opportunity_number}, "
                         f"description={description}, date_received={date_received}, quantity={quantity}, location={location}")

            # Create sample entries
            created_samples = []
            for i in range(quantity):
                sample = Sample.objects.create(
                    date_received=date_received,
                    customer=customer,
                    rsm=rsm_full_name,
                    opportunity_number=opportunity_number,
                    description=description,
                    storage_location=location,
                    quantity=1  # Each entry represents a single unit
                )
                created_samples.append(sample)

            logger.debug(f"Created samples: {created_samples}")

            # After the samples are successfully created
            if created_samples:
                # Calculate the total quantity
                total_quantity = sum(sample.quantity for sample in created_samples)

                # Call the email sending task
                send_sample_received_email.delay(
                    rsm_full_name,
                    date_received.strftime('%Y-%m-%d'),
                    opportunity_number,
                    customer,
                    total_quantity  # Use the total quantity of samples created
                )
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
        # Retrieve all unique opportunity numbers from the Sample objects in the database
        opportunity_numbers = Sample.objects.values_list('opportunity_number', flat=True).distinct()

        # Path to the DocumentationTemplate.xlsm file
        template_file = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', '_Templates', 'DocumentationTemplate.xlsm')
        if not os.path.exists(template_file):
            logger.error(f"Documentation template not found at: {template_file}")

        # Define excel_file before the loop
        excel_file = os.path.join(settings.BASE_DIR, 'Apps_Database.xlsx')
        if not os.path.exists(excel_file):
            logger.error(f"Excel file not found at {excel_file}")
            return JsonResponse({'status': 'error', 'error': 'Excel file not found'}, status=500)

        # Loop through each opportunity number
        for opportunity_number in opportunity_numbers:
            # Define the directory path for this opportunity number
            directory_path = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', opportunity_number)
            # Define the expected documentation file path
            new_filename = f"Documentation_{opportunity_number}.xlsm"
            destination_file = os.path.join(directory_path, new_filename)

            # Check if the documentation file already exists
            if not os.path.exists(destination_file):
                logger.debug(f"Documentation file does not exist for opportunity {opportunity_number}, creating it.")
                # Ensure the directory exists
                os.makedirs(directory_path, exist_ok=True)
                # Copy the template file to the destination
                try:
                    shutil.copy(template_file, destination_file)
                    logger.debug(f"Copied template file to: {destination_file}")
                except Exception as e:
                    logger.error(f"Error copying template file for opportunity {opportunity_number}: {e}")

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

        # Read Hyperlinks.csv
        try:
            hyperlinks_csv_file = os.path.join(settings.BASE_DIR, 'Hyperlinks.csv')
            opportunity_links = {}

            with open(hyperlinks_csv_file, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                next(reader, None)  # Skip header row if present
                for row in reader:
                    if len(row) >= 2:
                        opportunity_number = row[0].strip()
                        web_address = row[1].strip()
                        opportunity_links[opportunity_number] = web_address
        except Exception as e:
            logger.error(f"Error reading Hyperlinks.csv: {e}")
            opportunity_links = {}

        return render(request, 'samples/create_sample.html', {
            'unique_customers': unique_customers,
            'unique_rsms': unique_rsms,
            'excel_data': json.dumps(excel_data, cls=DjangoJSONEncoder),
            'samples': json.dumps(samples, cls=DjangoJSONEncoder),
            'opportunity_links': json.dumps(opportunity_links, cls=DjangoJSONEncoder),
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

                # Save the uploaded file to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                    for chunk in file.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name

                # Log the task invocation
                logger.info(
                    "Enqueuing save_full_size_image task for SampleImage ID %s with temp_file_path %s",
                    sample_image.id,
                    temp_file_path
                )

                # Enqueue Celery task with the path to the temporary file
                save_full_size_image.delay(sample_image.id, temp_file_path)
                logger.debug("Task enqueued successfully for SampleImage ID %s", sample_image.id)

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

def delete_samples(request):
    if request.method == 'POST':
        try:
            ids = json.loads(request.POST.get('ids', '[]'))
            # Retrieve the samples to be deleted
            samples_to_delete = Sample.objects.filter(unique_id__in=ids)
            # Get the list of opportunity numbers
            opportunity_numbers = samples_to_delete.values_list('opportunity_number', flat=True).distinct()
            for sample in samples_to_delete:
                sample.delete()  # Calls the delete method on each instance
            logger.debug(f"Deleted samples with IDs: {ids}")

            # Check if any samples remain with the same opportunity numbers
            for opp_num in opportunity_numbers:
                if not Sample.objects.filter(opportunity_number=opp_num).exists():
                    # Delete the directory
                    dir_path = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', opp_num)
                    if os.path.exists(dir_path):
                        shutil.rmtree(dir_path)
                        logger.debug(f"Deleted directory for opportunity number {opp_num}")
            return JsonResponse({'status': 'success'})
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {e}")
            return JsonResponse({'status': 'error', 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error deleting samples: {e}")
            return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

    logger.error("Invalid request method for delete_samples")
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
    text_x = margin
    text_y = margin + mm_to_points(5)

    c.translate(text_x, text_y)
    wrapped_paragraph.wrapOn(c, max_text_width, label_height)
    wrapped_paragraph.drawOn(c, 0, 0)

    c.save()

def handle_print_request(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ids_to_print = data.get('ids', [])
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
        # Delete the SampleImage instance (its delete method handles file deletion)
        image.delete()
        return JsonResponse({'status': 'success'})
    except SampleImage.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Image not found'})
    except Exception as e:
        logger.error(f"Error deleting image {image_id}: {e}")
        return JsonResponse({'status': 'error', 'error': 'An error occurred while deleting the image'})

def download_documentation(request, sample_id):
    try:
        # Retrieve the sample with the given unique ID
        sample = Sample.objects.get(unique_id=sample_id)
    except Sample.DoesNotExist:
        raise Http404("Sample not found")

    # Define the output directory and filename
    output_dir = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', 'Documentation', sample.opportunity_number)
    output_filename = f"Documentation_{sample.opportunity_number}_{sample.date_received.strftime('%Y%m%d')}.xlsm"
    output_path = os.path.join(output_dir, output_filename)

    # Check if the file already exists
    if os.path.exists(output_path):
        # Serve the existing file
        with open(output_path, 'rb') as fh:
            response = HttpResponse(
                fh.read(),
                content_type='application/vnd.ms-excel.sheet.macroEnabled.12'
            )
            response['Content-Disposition'] = f'attachment; filename="{output_filename}"'
            return response

    # File doesn't exist, proceed to create it
    template_path = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', 'Documentation', 'Documentation_Template.xlsm')
    if not os.path.exists(template_path):
        return HttpResponse("Template file not found.", status=500)

    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Use xlwings to open the template and modify it
    app = xw.App(visible=False)  # Prevents Excel window from appearing
    try:
        wb = xw.Book(template_path)
        ws = wb.sheets.active  # Modify if your data is not in the first sheet

        # Populate the cells with the sample information
        ws.range('B1').value = sample.customer
        ws.range('B2').value = sample.rsm
        ws.range('B3').value = sample.opportunity_number
        ws.range('B4').value = sample.date_received.strftime('%Y-%m-%d')

        # Get all samples with the same opportunity number and date received
        samples = Sample.objects.filter(
            opportunity_number=sample.opportunity_number,
            date_received=sample.date_received
        ).order_by('unique_id')

        # Starting from cell A8, list the unique IDs of the related samples
        start_row = 8
        for idx, s in enumerate(samples):
            ws.range(f'A{start_row + idx}').value = s.unique_id  # Column A

        # Save the modified workbook
        wb.save(output_path)
    finally:
        wb.close()
        app.quit()

    # Serve the newly created file
    with open(output_path, 'rb') as fh:
        response = HttpResponse(
            fh.read(),
            content_type='application/vnd.ms-excel.sheet.macroEnabled.12'
        )
        response['Content-Disposition'] = f'attachment; filename="{output_filename}"'
        return response
