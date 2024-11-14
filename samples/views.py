import os
import subprocess
import logging
import json
import random
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from .models import Sample, SampleImage
import pandas as pd
from django.core.serializers.json import DjangoJSONEncoder
import qrcode
import base64
from io import BytesIO
import os
from django.conf import settings
from django.urls import reverse



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
            rsm = request.POST.get('rsm')
            opportunity_number = request.POST.get('opportunity_number')
            description = request.POST.get('description')
            date_received = request.POST.get('date_received')
            quantity = request.POST.get('quantity')

            # Check for missing data
            if not all([customer, rsm, opportunity_number, description, date_received, quantity]):
                logger.error("Missing data in POST request")
                return JsonResponse({'status': 'error', 'error': 'Missing data'})

            try:
                quantity = int(quantity)
                date_received = datetime.strptime(date_received, '%Y-%m-%d').date()
            except ValueError as e:
                logger.error(f"Invalid data format: {e}")
                return JsonResponse({'status': 'error', 'error': 'Invalid data format'})

            location = "Choose a location"
            logger.debug(f"Received data: customer={customer}, rsm={rsm}, opportunity_number={opportunity_number}, "
                         f"description={description}, date_received={date_received}, quantity={quantity}, location={location}")

            # Create sample entries
            created_samples = []
            for i in range(quantity):
                sample = Sample.objects.create(
                    date_received=date_received,
                    customer=customer,
                    rsm=rsm,
                    opportunity_number=opportunity_number,
                    description=description,
                    storage_location=location,
                    quantity=1  # Each entry represents a single unit
                )
                created_samples.append(sample)

            logger.debug(f"Created samples: {created_samples}")
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
        # Load the Excel file
        excel_file = os.path.join(settings.BASE_DIR, 'Apps_Database.xlsx')
        if not os.path.exists(excel_file):
            logger.error(f"Excel file not found at {excel_file}")
            return JsonResponse({'status': 'error', 'error': 'Excel file not found'}, status=500)

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
            'samples': json.dumps(samples, cls=DjangoJSONEncoder)
        })

    except Exception as e:
        logger.error(f"Error rendering create_sample page: {e}")
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)

#@csrf_exempt
def upload_files(request):
    if request.method == 'POST' and request.FILES:
        files = request.FILES.getlist('files')
        sample_id = request.POST.get('sample_id')

        # Validate sample_id
        try:
            sample = Sample.objects.get(unique_id=sample_id)
        except Sample.DoesNotExist:
            return JsonResponse({'status': 'error', 'error': 'Sample not found'})

        image_urls = []

        for file in files:
            # Validate file type (ensure it's an image)
            if not file.content_type.startswith('image/'):
                return JsonResponse({'status': 'error', 'error': 'Invalid file type. Only images are allowed.'})

            # Save the image to the media directory
            sample_image = SampleImage(sample=sample)
            sample_image.image.save(file.name, file)
            sample_image.save()

            # Collect the URL to return to the client
            image_urls.append(sample_image.image.url)

        return JsonResponse({'status': 'success', 'message': 'Files uploaded successfully.', 'image_urls': image_urls})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method.'})

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
            Sample.objects.filter(unique_id__in=ids).delete()
            logger.debug(f"Deleted samples with IDs: {ids}")
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

def handle_print_request(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ids_to_print = data.get('ids', [])
            label_contents = []

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

                label_contents.append({
                    'id': sample.unique_id,
                    'date_received': sample.date_received.strftime('%Y-%m-%d'),
                    'description': sample.description,
                    'rsm': sample.rsm,
                    'qr_code': qr_code  # Base64 encoded QR code image
                })

            return JsonResponse({'status': 'success', 'labels': label_contents})
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

def generate_unique_id():
    while True:
        new_id = random.randint(1000, 9999)
        if not Sample.objects.filter(unique_id=new_id).exists():
            return new_id

def get_sample_images(request):
    sample_id = request.GET.get('sample_id')
    try:
        sample = Sample.objects.get(unique_id=sample_id)
        images = sample.images.all()
        image_urls = [image.image.url for image in images]
        return JsonResponse({'status': 'success', 'image_urls': image_urls})
    except Sample.DoesNotExist:
        return JsonResponse({'status': 'error', 'error': 'Sample not found'})
