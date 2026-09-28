from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'work_time_reporter'

urlpatterns = [
    # urls for a user lon-in / log-out
    path('login/', auth_views.LoginView.as_view(template_name='work_time_reporter/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='work_time_reporter:login'), name='logout'),

    # Manager's cabinet
    path('approvals/', views.team_approvals, name='team_approvals'),
    # root to view details of week report for approval (in read-only mode)
    path('timesheet/<int:timesheet_id>/', views.timesheet_detail, name='timesheet_detail'),
    path('timesheet/<int:timesheet_id>/export/pdf/', views.export_weekly_pdf, name='export_weekly_pdf'),

    # year dashboard
    path('yearly/', views.yearly_dashboard, name='yearly_dashboard'),
    path('yearly/<int:year>/', views.yearly_dashboard, name='yearly_dashboard_year'),
    path('yearly/<int:year>/export/excel/', views.export_yearly_excel, name='export_yearly_excel'),
    path('yearly/export/excel/', views.export_yearly_excel, name='export_yearly_excel_current'),


    # When the user enters the main page of the application, we call views.dashboard - it redirect us to current week
    path('', views.dashboard, name='dashboard'),
    path('<int:year>/<int:week>/', views.dashboard, name='dashboard_week'),

    # year's tasks progress dashboard
    path('progress/<int:year>/', views.progress_dashboard, name='progress_dashboard'),
    path('progress/', views.progress_dashboard, name='progress_dashboard_current'),

    # url for interactive CompanyCalendar dashboard
    path('settings/calendar/<int:year>/', views.calendar_settings, name='calendar_settings'),
    path('settings/calendar/', views.calendar_settings, name='calendar_settings_current'),
    path('settings/calendar/<int:year>/modal/<str:date_str>/', views.calendar_day_modal, name='calendar_day_modal'),
]
