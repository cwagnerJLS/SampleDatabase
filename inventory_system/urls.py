# inventory_system/urls.py

from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from samples import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.create_sample, name='home'),
    path('create_sample/', views.create_sample, name='create_sample'),
    path('update_sample_location/', views.update_sample_location, name='update_sample_location'),
    path('delete_samples/', views.delete_samples, name='delete_samples'),
    path('handle_print_request/', views.handle_print_request, name='handle_print_request'),
    path('manage_sample/<int:sample_id>/', views.manage_sample, name='manage_sample'),
    path('upload_files/', views.upload_files, name='upload_files'),
    path('get_sample_images/', views.get_sample_images, name='get_sample_images'),  # Added this line
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
