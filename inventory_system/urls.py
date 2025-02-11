# inventory_system/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls import re_path
from django.views.static import serve
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
    path('get_sample_images/', views.get_sample_images, name='get_sample_images'),
    path('delete_sample_image/', views.delete_sample_image, name='delete_sample_image'),
    path('remove_from_inventory/', views.remove_from_inventory, name='remove_from_inventory'),
]

import os  # Make sure to import os

# Add these lines to define custom error handlers:
handler400 = 'samples.views.handle_400'
handler403 = 'samples.views.handle_403'
handler404 = 'samples.views.handle_404'
handler500 = 'samples.views.handle_500'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static('/onedrive_media/', document_root=os.path.join(settings.BASE_DIR, 'OneDrive_Sync'))
    urlpatterns += static(settings.STATIC_URL, document_root=os.path.join(settings.BASE_DIR, 'static'))

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
]
