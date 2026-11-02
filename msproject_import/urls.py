from django.urls import path

from . import views

app_name = 'msproject_import'

urlpatterns = [
    path('start/', views.import_start, name='start'),
    path('oauth/login/', views.oauth_login, name='oauth_login'),
    path('oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('oauth/disconnect/', views.oauth_disconnect, name='oauth_disconnect'),
    path('mapping/<int:batch_id>/', views.import_mapping, name='mapping'),

    # Manager review URLs
    path('pending/', views.pending_imports, name='pending'),
    path('approve/<int:batch_id>/', views.approve_import, name='approve'),
]
