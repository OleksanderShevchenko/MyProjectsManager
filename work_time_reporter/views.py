import datetime
import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import CompanyCalendar, WeeklyTimesheet, Project
from .services import TimesheetService, CalendarService
from .exports import ExportService
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

        if getattr(request, 'htmx', False):
            if result['success']:
                timesheet = WeeklyTimesheet.objects.select_related('user').filter(id=timesheet_id).first()
                return render(request, 'work_time_reporter/partials/timesheet_approval_status_row.html', {
                    'timesheet': timesheet,
                    'timesheet_id': timesheet_id,
                    'action': action,
                })
            return HttpResponse(result['message'], status=400)

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

    if request.method == 'POST':
        is_htmx = getattr(request, 'htmx', False)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if is_htmx or is_ajax:
            if not is_admin:
                if is_htmx:
                    return HttpResponseForbidden("Permission denied")
                return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

            if is_htmx:
                date_str = request.POST.get('date')
                new_type = request.POST.get('type')
                description = request.POST.get('description', '')
            else:
                data = json.loads(request.body)
                date_str = data.get('date')
                new_type = data.get('type')
                description = data.get('description', '')

            result = CalendarService.update_day(date_str, new_type, description=description)
            if result['success']:
                if is_htmx:
                    target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    day_type = new_type if new_type != 'CLEAR' else None
                    desc = description.strip() if (new_type != 'CLEAR' and description) else ''
                    day_obj = {
                        'date': target_date,
                        'day_num': target_date.day,
                        'is_weekend': target_date.weekday() >= 5,
                        'day_type': day_type,
                        'description': desc,
                        'next_type': CalendarService.get_next_day_type(day_type, target_date=target_date),
                    }
                    special_days = CalendarService.get_special_days(year)
                    return render(request, 'work_time_reporter/partials/calendar_day_cell.html', {
                        'day': day_obj,
                        'is_admin': is_admin,
                        'year': year,
                        'special_days': special_days,
                    })
                return JsonResponse({'status': 'success'})

            if is_htmx:
                return HttpResponse(result.get('message', 'Error'), status=400)
            return JsonResponse({'status': 'error', 'message': result.get('message', 'Error')}, status=400)

    months_data = CalendarService.get_year_calendar_data(year)
    special_days = CalendarService.get_special_days(year)
    context = {
        'year': year,
        'months_data': months_data,
        'special_days': special_days,
        'types': CompanyCalendar.DAY_TYPE_CHOICES,
        'is_admin': is_admin,
    }
    return render(request, 'work_time_reporter/calendar_settings.html', context)


@login_required(login_url='work_time_reporter:login')
def calendar_day_modal(request, year: int, date_str: str):
    """
    Renders an HTMX modal dialog allowing admins to edit a day's status and description.
    """
    is_admin = getattr(request.user, 'is_admin_role', False) or request.user.is_superuser
    if not is_admin:
        return HttpResponseForbidden(_("Permission denied"))

    try:
        target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return HttpResponse(_("Invalid date format"), status=400)

    cal_entry = CompanyCalendar.objects.filter(date=target_date).first()
    current_type = cal_entry.day_type if cal_entry else 'CLEAR'
    current_description = cal_entry.description if (cal_entry and cal_entry.description) else ''

    context = {
        'year': year,
        'target_date': target_date,
        'current_type': current_type,
        'current_description': current_description,
        'is_monday': target_date.weekday() == 0,
        'types': CompanyCalendar.DAY_TYPE_CHOICES,
    }
    return render(request, 'work_time_reporter/partials/calendar_day_modal.html', context)


@login_required(login_url='work_time_reporter:login')
def export_weekly_pdf(request, timesheet_id: int):
    """
    Exports a single weekly timesheet as a downloadable PDF document.
    Authorized for the timesheet owner, their project manager, or an administrator.
    """
    timesheet = get_object_or_404(
        WeeklyTimesheet.objects.select_related('user', 'approved_by'),
        id=timesheet_id
    )

    is_owner = request.user == timesheet.user
    is_admin = request.user.is_superuser or getattr(request.user, 'is_admin_role', False)
    is_manager = Project.objects.filter(manager=request.user, is_active=True, members=timesheet.user).exists()

    if not (is_owner or is_admin or is_manager):
        return HttpResponseForbidden(_("Access denied. You do not have permission to export this timesheet."))

    pdf_content = ExportService.generate_weekly_pdf(timesheet)
    filename = f"Timesheet_{timesheet.user.username}_{timesheet.year}_W{timesheet.week_number:02d}.pdf"

    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(pdf_content)
    return response


@login_required(login_url='work_time_reporter:login')
def export_yearly_excel(request, year: int = None):
    """
    Exports an employee's annual work report as an Excel spreadsheet (.xlsx).
    """
    if not year:
        year = timezone.now().year

    target_user = request.user
    user_id = request.GET.get('user_id')
    if user_id and str(user_id) != str(request.user.id):
        User = get_user_model()
        target_user = get_object_or_404(User, id=user_id)

        is_admin = request.user.is_superuser or getattr(request.user, 'is_admin_role', False)
        is_manager = Project.objects.filter(manager=request.user, is_active=True, members=target_user).exists()
        if not (is_admin or is_manager):
            return HttpResponseForbidden(_("Access denied. You do not have permission to export this user's report."))

    excel_content = ExportService.generate_yearly_excel(target_user, year)
    filename = f"Yearly_Timesheet_{target_user.username}_{year}.xlsx"

    response = HttpResponse(
        excel_content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(excel_content)
    return response

