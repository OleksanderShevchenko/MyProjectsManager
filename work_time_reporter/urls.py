from django.urls import path
from . import views

app_name = 'work_time_reporter'

urlpatterns = [
    # When the user enters the main page of the application, we call views.dashboard
    path('', views.dashboard, name='dashboard'),
    path('<int:year>/<int:week>/', views.dashboard, name='dashboard_week'),
]