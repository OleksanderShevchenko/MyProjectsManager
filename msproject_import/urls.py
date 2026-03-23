from django.urls import path

from . import views

app_name = 'msproject_import'

urlpatterns = [
    path('start/', views.import_start, name='start'),
    path('mapping/<int:batch_id>/', views.import_mapping, name='mapping'),
]
