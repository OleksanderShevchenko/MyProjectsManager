from django.urls import path

from . import views

app_name = 'msproject_import'

urlpatterns = [
    path('start/', views.import_start, name='start'),
    path('mapping/<int:batch_id>/', views.import_mapping, name='mapping'),

    # manager's urls
    path('pending/', views.pending_imports, name='pending'),
    path('approve/<int:batch_id>/', views.approve_import, name='approve'),
]
