from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('', views.profile_view, name='profile'),
    path('password/', views.password_change_view, name='password_change'),
    path('history/', views.history_view, name='history'),
]
