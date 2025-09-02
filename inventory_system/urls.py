# inventory_system/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.urls import re_path
from django.views.static import serve
from samples import views
from samples.health import health_check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('select-user/', views.select_user, name='select_user'),
    path('set-user/', views.set_user, name='set_user'),
    path('', views.view_samples, name='home'),
    path('create_sample/', views.create_sample, name='create_sample'),
    path('view_samples/', views.view_samples, name='view_samples'),
    path('update_sample_location/', views.update_sample_location, name='update_sample_location'),
    path('delete_samples/', views.delete_samples, name='delete_samples'),
    path('handle_print_request/', views.handle_print_request, name='handle_print_request'),
    path('manage_sample/<int:sample_id>/', views.manage_sample, name='manage_sample'),
    path('upload_files/', views.upload_files, name='upload_files'),
    path('get_sample_images/', views.get_sample_images, name='get_sample_images'),
    path('delete_sample_image/', views.delete_sample_image, name='delete_sample_image'),
    path('remove_from_inventory/', views.remove_from_inventory, name='remove_from_inventory'),
    path('export_documentation/', views.export_documentation_view, name='export_documentation'),
    path('batch_audit/', views.batch_audit_samples, name='batch_audit_samples'),
]

import os  # Make sure to import os

# Add these lines to define custom error handlers:
handler400 = 'samples.views.handle_400'
handler403 = 'samples.views.handle_403'
handler404 = 'samples.views.handle_404'
handler500 = 'samples.views.handle_500'

handler405 = 'samples.views.handle_405'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static('/onedrive_media/', document_root=os.path.join(settings.BASE_DIR, 'OneDrive_Sync'))
    urlpatterns += static(settings.STATIC_URL, document_root=os.path.join(settings.BASE_DIR, 'static'))

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
    re_path(r'^static/(?P<path>.*)$', serve, {
        'document_root': os.path.join(settings.BASE_DIR, 'static'),
    }),
]
