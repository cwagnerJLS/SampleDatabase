import logging
import json
import subprocess
import os
import base64
import pandas as pd
import qrcode
from celery import chain
from datetime import datetime
from io import BytesIO
from PIL import Image
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.base import ContentFile
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .models import Sample, SampleImage, Opportunity
from .label_utils import generate_label, generate_qr_code, mm_to_points
from .services.opportunity_service import OpportunityService
from .sharepoint_config import (
    get_documentation_template_path,
    get_apps_database_path,
    THUMBNAIL_SIZE
)
from .utils.responses import (
    error_response,
    success_response,
    not_found_response,
    method_not_allowed_response,
    server_error_response
)
from .utils.date_utils import format_date_for_display
from .tasks import (
    delete_image_from_sharepoint,
    update_documentation_excels,
    restore_documentation_from_archive_task,
    send_sample_received_email,
    create_sharepoint_folder_task,
    create_documentation_on_sharepoint_task,
    upload_full_size_images_to_sharepoint,
    find_sample_info_folder_url,
    export_documentation
)

# Configure logging
logger = logging.getLogger('samples')

def view_samples(request):
    # Convert samples to list of dicts, then JSON-encode.
    samples_list = list(Sample.objects.all().values())

    # Format date fields for display
    for entry in samples_list:
        entry['date_received'] = format_date_for_display(entry.get('date_received'))

    return render(request, 'samples/view_sample.html', {
        'samples': json.dumps(samples_list, cls=DjangoJSONEncoder),
    })

def create_sample(request):
    logger.debug("Entered create_sample view")

    if request.method == 'POST':
        logger.debug("Processing POST request")
        try:
            if 'clear_db' in request.POST:
                logger.debug("Clearing database")
                Sample.objects.all().delete()
                return success_response(message='Database cleared')

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
                return error_response('Invalid data format')

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
                # Update existing Opportunity fields using the service
                updated = OpportunityService.update_opportunity_fields(
                    opportunity, 
                    customer=customer,
                    rsm=rsm_full_name,
                    description=description,
                    date_received=date_received
                )

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

                # Update sample_ids field for the Opportunity using the service
                sample_ids_to_add = [str(sample.unique_id) for sample in created_samples]
                OpportunityService.add_sample_ids(opportunity, sample_ids_to_add)
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

            # Chain find_sample_info_folder_url + send_sample_received_email only if total_quantity > 0
            if total_quantity > 0:
                chain(
                    find_sample_info_folder_url.si(
                        opportunity.customer,
                        opportunity_number
                    ),
                    send_sample_received_email.si(
                        rsm_full_name,
                        format_date_for_display(date_received),
                        opportunity_number,
                        customer,
                        total_quantity
                    )
                ).delay()
                logger.debug(f"Email sent to {rsm_full_name} regarding opportunity {opportunity_number}")
            else:
                logger.debug("Quantity is zero; email not sent.")

            # Removed separate call to update_documentation_excels

            return success_response(data={
                'created_samples': [
                    {
                        'unique_id': sample.unique_id,
                        'date_received': format_date_for_display(sample.date_received),
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
            return server_error_response(str(e))

    logger.debug("Rendering create_sample page")

    try:
        # Call the Celery task
        update_documentation_excels.delay()

        # Retrieve all opportunity numbers from the Opportunity model
        opportunity_numbers = Opportunity.objects.values_list('opportunity_number', flat=True)


        # Check template file exists
        documentation_template_path = get_documentation_template_path()
        if not os.path.exists(documentation_template_path):
            logger.error(f"Documentation template not found at: {documentation_template_path}")

        # Check Excel database file exists
        apps_database_path = get_apps_database_path()
        if not os.path.exists(apps_database_path):
            logger.error(f"Excel file not found at {apps_database_path}")
            return server_error_response('Excel file not found')


        # Read the Excel database
        df = pd.read_excel(apps_database_path)

        # Get unique customers and RSMs
        unique_customers = sorted(df['Customer'].dropna().unique())
        unique_rsms = sorted(df['RSM'].dropna().unique())

        # Convert DataFrame to JSON serializable format
        excel_data = df.to_dict(orient='records')

        # Load saved samples
        samples = list(Sample.objects.all().values())

        # Convert date_received to string format for JSON serialization
        for sample in samples:
            sample['date_received'] = format_date_for_display(sample.get('date_received'))

        logger.debug(f"Samples List: {samples}")


        return render(request, 'samples/create_sample.html', {
            'unique_customers': unique_customers,
            'unique_rsms': unique_rsms,
            'excel_data': json.dumps(excel_data, cls=DjangoJSONEncoder),
            'samples': json.dumps(samples, cls=DjangoJSONEncoder),
        })

    except Exception as e:
        logger.error(f"Error rendering create_sample page: {e}")
        return server_error_response(str(e))

def upload_files(request):
    if request.method == 'POST' and request.FILES:
        files = request.FILES.getlist('files')
        sample_id = request.POST.get('sample_id')

        # Validate sample_id
        try:
            sample = Sample.objects.get(unique_id=sample_id)
        except Sample.DoesNotExist:
            logger.error("Sample not found with ID: %s", sample_id)
            return not_found_response('Sample')

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
                    return error_response('Invalid file type. Only images are allowed.')

                # Open the uploaded image
                image = Image.open(file)
                image = image.convert('RGB')  # Ensure image is in RGB mode

                # Create a thumbnail
                max_size = THUMBNAIL_SIZE  # Use centralized thumbnail size configuration
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
            return server_error_response('Error processing files.')

        logger.info("Files uploaded successfully for Sample ID %s", sample_id)
        return success_response(
            message='Files uploaded successfully.',
            images=image_urls,
            image_ids=image_ids  # Include image IDs in the response
        )

    logger.error("Invalid request method: %s", request.method)
    return method_not_allowed_response()

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

                return success_response(message='Locations updated successfully for selected samples')
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

                return success_response(message='Location updated successfully for sample')

        except Sample.DoesNotExist:
            logger.error("Sample not found")
            return not_found_response('Sample')
        except ValueError as e:
            logger.error(f"Invalid data provided: {e}")
            return error_response('Invalid data provided')
        except Exception as e:
            logger.error(f"Error in update_sample_location: {e}")
            return server_error_response(str(e))

    logger.error("Invalid request method for update_sample_location")
    return method_not_allowed_response()

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

            return success_response()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {e}")
            return error_response('Invalid JSON data')
        except Exception as e:
            logger.error(f"Error removing samples from inventory: {e}")
            return server_error_response(str(e))

    logger.error("Invalid request method for remove_from_inventory")
    return method_not_allowed_response()

def handle_print_request(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ids_to_print = data.get('ids', [])
            if not ids_to_print:
                return error_response('No sample IDs provided')

            # Use the first sample_id to determine the labels directory
            sample = Sample.objects.get(unique_id=ids_to_print[0])
            labels_dir = os.path.join(settings.BASE_DIR, 'Labels')
            os.makedirs(labels_dir, exist_ok=True)

            if not ids_to_print:
                return error_response('No sample IDs provided')

            for sample_id in ids_to_print:
                try:
                    sample = Sample.objects.get(unique_id=sample_id)
                except Sample.DoesNotExist:
                    logger.error(f"Sample with ID {sample_id} does not exist")
                    return not_found_response('Sample', sample_id)
                except Exception as e:
                    logger.error(f"Error retrieving sample: {e}")
                    return server_error_response('Error retrieving sample')

                qr_url = request.build_absolute_uri(reverse('manage_sample', args=[sample.unique_id]))
                output_path = os.path.join(labels_dir, f"label_{sample.unique_id}.pdf")

                qr_data = qr_url
                id_value = str(sample.unique_id)
                date_received = format_date_for_display(sample.date_received)
                rsm_value = sample.rsm
                description = sample.description

                generate_label(output_path, qr_data, id_value, date_received, rsm_value, description)

                # Send the label PDF to the default printer
                try:
                    subprocess.run(['lpr', output_path], check=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Error printing label for sample {sample_id}: {e}")
                    return server_error_response(f'Failed to print label for sample {sample_id}')

            return success_response()
        except json.JSONDecodeError:
            return error_response('Invalid JSON data')
        except Exception as e:
            logger.error(f"Error in handle_print_request: {e}")
            return server_error_response('An unexpected error occurred')
    else:
        return method_not_allowed_response()

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
                if location == "Choose a Location":
                    sample.storage_location = None
                else:
                    sample.storage_location = location

            sample.audit = audit
            sample.save()
            logger.debug(f"Updated sample {sample_id}: location={sample.storage_location}, audit={sample.audit}")

            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/x-www-form-urlencoded' in request.headers.get('Content-Type', ''):
                return JsonResponse({'status': 'success', 'message': 'Sample updated successfully'})
            
            # Regular form submission - redirect back to the same page
            return redirect('manage_sample', sample_id=sample.unique_id)
        except Exception as e:
            logger.error(f"Error updating sample {sample_id}: {e}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/x-www-form-urlencoded' in request.headers.get('Content-Type', ''):
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            return server_error_response(str(e))

    # For GET requests, render the template with the sample data
    return render(request, 'samples/manage_sample.html', {'sample': sample})

def export_documentation_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        opportunity_number = data.get('opportunity_number', None)
        if opportunity_number:
            export_documentation.delay(opportunity_number)
            return success_response()
        else:
            return error_response('No opportunity number')
    return method_not_allowed_response()

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
        return success_response(data={'images': image_data})
    except Sample.DoesNotExist:
        return not_found_response('Sample')

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
        return success_response()
    except SampleImage.DoesNotExist:
        return not_found_response('Image')
    except Exception as e:
        logger.error(f"Error deleting image {image_id}: {e}")
        return server_error_response('An error occurred while deleting the image')

def delete_samples(request):
    if request.method == 'POST':
        try:
            ids = json.loads(request.POST.get('ids', '[]'))
            # Retrieve the samples to be deleted
            samples_to_delete = Sample.objects.filter(unique_id__in=ids)

            for sample in samples_to_delete:
                sample.delete()  # Calls the delete method on each instance

            logger.debug(f"Deleted samples with IDs: {ids}")

            return success_response()
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data: {e}")
            return error_response('Invalid JSON data')
        except Sample.DoesNotExist as e:
            logger.error(f"Sample not found: {e}")
            return not_found_response('Sample')
        except Exception as e:
            logger.error(f"Error deleting samples: {e}")
            return server_error_response('An unexpected error occurred')
    else:
        logger.error("Invalid request method for delete_samples")
        return method_not_allowed_response()
def handle_405(request, exception=None):
    return method_not_allowed_response()
def handle_400(request, exception=None):
    return error_response('Bad Request')

def handle_403(request, exception=None):
    return error_response('Forbidden', status=403)

def handle_404(request, exception=None):
    return error_response('Not Found', status=404)

def handle_500(request):
    return server_error_response('Server Error')
