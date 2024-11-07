from django.contrib import admin
from django.urls import path
from samples import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.create_sample, name='home'),
    path('update_sample_location/', views.update_sample_location, name='update_sample_location'),
    path('delete_samples/', views.delete_samples, name='delete_samples'),
    path('handle_print_request/', views.handle_print_request, name='handle_print_request'),
    path('manage_sample/<int:sample_id>/', views.manage_sample, name='manage_sample'),
]
