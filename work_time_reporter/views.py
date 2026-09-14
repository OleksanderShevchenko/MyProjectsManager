import datetime
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import CompanyCalendar
from .services import TimesheetService, CalendarService
from .decorators import manager_required


@login_required(login_url='work_time_reporter:login')
def dashboard(request, year: int = None, week: int = None):
    """
    Weekly timesheet dashboard for logging and submitting work hours.
    """
    today = timezone.now().date()

    if not year or not week:
        current_year, current_week, _ = today.isocalendar()
        return redirect('work_time_reporter:dashboard_week', year=current_year, week=current_week)

    try:
        (
            timesheet,
            week_dates,
            prev_year,
            prev_week,
            next_year,
            next_week,
        ) = TimesheetService.get_or_create_timesheet(request.user, year, week)
    except ValueError:
        current_year, current_week, _ = today.isocalendar()
        return redirect('work_time_reporter:dashboard_week', year=current_year, week=current_week)

    if request.method == 'POST':
        result = TimesheetService.save_timesheet_data(request.user, timesheet, request.POST)
        if result['success']:
            if result['type'] == 'success':
                messages.success(request, result['message'])
            elif result['type'] == 'warning':
                messages.warning(request, result['message'])
            elif result['type'] == 'info':
                messages.info(request, result['message'])
        else:
            messages.error(request, result['message'])
        return redirect('work_time_reporter:dashboard_week', year=year, week=week)

    grid_data = TimesheetService.build_weekly_grid(request.user, timesheet, week_dates)
    mini_dashboard = TimesheetService.build_mini_dashboard(request.user, grid_data.keys())

    context = {
        'timesheet': timesheet,
        'week_dates': week_dates,
        'grid_data': grid_data,
        'mini_dashboard': mini_dashboard,
        'today': today,
        'prev_year': prev_year,
        'prev_week': prev_week,
        'next_year': next_year,
        'next_week': next_week,
    }
    return render(request, 'work_time_reporter/dashboard.html', context)


@login_required(login_url='work_time_reporter:login')
@manager_required
def team_approvals(request):
    """
    Manager cabinet for reviewing and approving subordinates' submitted timesheets.
    """
    if request.method == 'POST':
        timesheet_id = request.POST.get('timesheet_id')
        action = request.POST.get('action')
        comment = request.POST.get('rejection_comment', '')
        result = TimesheetService.review_timesheet(request.user, timesheet_id, action, comment)

        if result['success']:
            if result['type'] == 'success':
                messages.success(request, result['message'])
            elif result['type'] == 'warning':
                messages.warning(request, result['message'])
        else:
            messages.error(request, result['message'])
        return redirect('work_time_reporter:team_approvals')

    pending_timesheets = TimesheetService.get_pending_approvals(request.user)
    return render(request, 'work_time_reporter/team_approvals.html', {'pending_timesheets': pending_timesheets})


@login_required(login_url='work_time_reporter:login')
def timesheet_detail(request, timesheet_id: int):
    """
    Detailed read-only review of a single weekly timesheet for owner and project manager.
    """
    timesheet, detail_context, error_message = TimesheetService.get_timesheet_detail_data(request.user, timesheet_id)
    if error_message:
        messages.error(request, error_message)
        return redirect('work_time_reporter:dashboard')

    if request.method == 'POST' and detail_context['is_manager']:
        action = request.POST.get('action')
        comment = request.POST.get('rejection_comment', '')
        result = TimesheetService.review_timesheet(request.user, timesheet_id, action, comment)

        if result['success']:
            if result['type'] == 'success':
                messages.success(request, result['message'])
            elif result['type'] == 'warning':
                messages.warning(request, result['message'])
        else:
            messages.error(request, result['message'])
        return redirect('work_time_reporter:team_approvals')

    return render(request, 'work_time_reporter/timesheet_detail.html', detail_context)


@login_required(login_url='work_time_reporter:login')
def yearly_dashboard(request, year: int = None):
    """
    Yearly matrix of all weeks and project type distribution breakdown.
    """
    if not year:
        year = timezone.now().date().year

    context = TimesheetService.get_yearly_data(request.user, year)
    return render(request, 'work_time_reporter/yearly_dashboard.html', context)


@login_required(login_url='work_time_reporter:login')
def progress_dashboard(request, year: int = None):
    """
    Full year task progress and budget tracking dashboard against deadlines.
    """
    current_year = datetime.datetime.now().year
    if not year:
        year = current_year

    if year < current_year:
        year_status = 'past'
    elif year > current_year:
        year_status = 'future'
    else:
        year_status = 'current'

    integral_data, sorted_grid_data = TimesheetService.get_progress_data(request.user, year, year_status)
    context = {
        'year': year,
        'year_status': year_status,
        'integral_data': integral_data,
        'grid_data': sorted_grid_data,
        'today': datetime.date.today(),
    }
    return render(request, 'work_time_reporter/progress_dashboard.html', context)


@login_required(login_url='work_time_reporter:login')
def calendar_settings(request, year: int = None):
    """
    Interactive yearly calendar for admins to set holidays and short days.
    """
    if not year:
        year = datetime.datetime.now().year

    is_admin = getattr(request.user, 'is_admin_role', False) or request.user.is_superuser

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

        data = json.loads(request.body)
        date_str = data.get('date')
        new_type = data.get('type')

        result = CalendarService.update_day(date_str, new_type)
        if result['success']:
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'error', 'message': result.get('message', 'Error')}, status=400)

    months_data = CalendarService.get_year_calendar_data(year)
    context = {
        'year': year,
        'months_data': months_data,
        'types': CompanyCalendar.DAY_TYPE_CHOICES,
        'is_admin': is_admin,
    }
    return render(request, 'work_time_reporter/calendar_settings.html', context)
