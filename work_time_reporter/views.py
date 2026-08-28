import calendar
import datetime
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Min, Q, Max
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from .models import Task, WeeklyTimesheet, TimeLog, Project, CompanyCalendar
from .services import TimesheetService

User = get_user_model()


@login_required(login_url='work_time_reporter:login')
def dashboard(request, year: int = None, week: int = None):
    # Determine the current day, year, and week number according to the ISO standard
    today = timezone.now().date()

    if not year or not week:
        current_year, current_week, _ = today.isocalendar()
        return redirect('work_time_reporter:dashboard_week', year=current_year, week=current_week)

    try:
        # Python magic: getting Monday for a given year and week
        monday = datetime.date.fromisocalendar(year, week, 1)
        year_ = year
        week_number = week
    except ValueError:
        # If someone entered a non-existent week (for example, 99) - we throw it to the current one
        current_year, current_week, _ = today.isocalendar()
        return redirect('work_time_reporter:dashboard_week', year=current_year, week=current_week)

    # We are looking for a weekly report. If it does not exist yet, we automatically create it (Draft)
    timesheet, created = WeeklyTimesheet.objects.get_or_create(
        user=request.user,
        year=year_,
        week_number=week_number,
        defaults={'status': WeeklyTimesheet.Status.DRAFT}
    )

    # SAVE AND SEND BUTTON PROCESSING
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


        # Reload the page to show updated data.
        return redirect('work_time_reporter:dashboard_week', year=year, week=week)

    # Generate a list of 7 dates for the current week (Monday to Sunday)
    week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]

    # Calculating adjacent weeks for Navigation buttons
    prev_monday = monday - datetime.timedelta(days=7)
    prev_year, prev_week, _ = prev_monday.isocalendar()

    next_monday = monday + datetime.timedelta(days=7)
    next_year, next_week, _ = next_monday.isocalendar()

    # We get all the tasks for which the user is assigned - add where project is not closed or there is logged  time
    tasks = Task.objects.filter(
        Q(assignees=request.user) &
        (Q(project__is_active=True) | Q(time_logs__timesheet=timesheet))
    ).distinct().select_related('project')

    # Getting all the time logs for this weekly report
    logs = TimeLog.objects.filter(timesheet=timesheet)

    # We are making a convenient dictionary-cripple for quickly searching for logs by coordinates (task_id, date)
    log_dict = {(log.task_id, log.date): log for log in logs}

    # Assembling the final "matrix" for the HTML template
    grid_data = {}

    # Fetch global calendar events for the current week
    # in_bulk('date') makes a dictionary with dates as keys for extremely fast lookups
    calendar_events = CompanyCalendar.objects.filter(
        date__range=[week_dates[0], week_dates[-1]]).in_bulk(field_name='date')

    for task in tasks:
        days_data = []
        row_total = 0  # variable for summing up hours per project/task

        for i, current_date in enumerate(week_dates):
            hours = ''
            comment = ''

            # Fetch existing logs using YOUR optimized dictionary!
            log = log_dict.get((task.id, current_date))
            if log:
                hours = log.hours
                row_total += hours
                comment = log.comment

            # Check if day is weekend (5=Saturday, 6=Sunday)
            is_weekend = current_date.weekday() >= 5
            is_holiday = False
            is_free_monday = False
            is_short_day = False

            if current_date in calendar_events:
                event = calendar_events[current_date]
                if event.day_type in ['HOLIDAY', 'FREE_MONDAY']:
                    is_holiday = True
                    if event.day_type == 'FREE_MONDAY':
                        is_free_monday = True
                    else:
                        is_free_monday = False
                elif event.day_type == 'SHORT_DAY':
                    is_short_day = True

            days_data.append({
                'date': current_date,
                'hours': hours,
                'comment': comment,
                'is_weekend': is_weekend,
                'is_short_day': is_short_day,
                'is_free_monday': is_free_monday,
                'is_holiday': is_holiday
            })

        # If the week is blocked and there are no hours at all - skip this task
        if timesheet.status != 'DRAFT' and row_total == 0:
            continue

        # New grouping by project
        if task.project not in grid_data:
            grid_data[task.project] = []

        grid_data[task.project].append({
            'task': task,
            'days': days_data,
            'row_total': row_total
        })

        # --- MINI DASHBOARD LOGIC ---
        # Quick overview of project budgets for the projects present in this week's grid
        mini_dashboard = []

        for project in grid_data.keys():
            # 1. Find all tasks for this project assigned to the current user
            tasks_in_proj = Task.objects.filter(project=project, assignees=request.user)

            # 2. Calculate total budget for these tasks
            budget = sum(t.budget_hours for t in tasks_in_proj if t.budget_hours)

            # 3. Calculate total spent hours across ALL timesheets (not just this week)
            spent_result = TimeLog.objects.filter(task__in=tasks_in_proj, user=request.user).aggregate(
                total=Sum('hours'))
            spent = float(spent_result['total'] or 0.0)

            # 4. Calculate progress percentage
            if budget > 0:
                pct = min(100, (spent / budget) * 100)
                overbudget = spent > budget
            else:
                pct = 100 if spent > 0 else 0
                overbudget = spent > 0

            mini_dashboard.append({
                'name': project.name,
                'budget': budget,
                'spent': spent,
                'pct': pct,
                'overbudget': overbudget
            })

    context = {
        'timesheet': timesheet,
        'week_dates': week_dates,
        'grid_data': grid_data,
        'mini_dashboard': mini_dashboard,
        'today': today,
        # Pass data for buttons to template
        'prev_year': prev_year,
        'prev_week': prev_week,
        'next_year': next_year,
        'next_week': next_week,
    }

    return render(request, 'work_time_reporter/dashboard.html', context)


@login_required(login_url='work_time_reporter:login')
def team_approvals(request):
    # Check if the current user is a manager of at least one project
    managed_projects = Project.objects.filter(manager=request.user, is_active=True)

    # Protection: if a regular engineer comes in - throw him back to his dashboard
    if not managed_projects.exists():
        messages.warning(request, "Access denied. You are not a manager of any active project.")
        return redirect('work_time_reporter:dashboard')

    # Protection: if a regular engineer comes in - throw him back to his dashboard
    if not managed_projects.exists():
        messages.warning(request, "Access denied. You are not a manager of any project.")
        return redirect('work_time_reporter:dashboard')  # with this url it will be re-adrest to current week

    # Handling Approve / Reject button presses
    if request.method == 'POST':
        timesheet_id = request.POST.get('timesheet_id')
        action = request.POST.get('action')

        try:
            ts = WeeklyTimesheet.objects.get(id=timesheet_id)

            # Verify the current user manages at least one active project that this timesheet's owner is assigned to
            managed_project_ids = managed_projects.values_list('id', flat=True)
            user_project_ids = Project.objects.filter(members=ts.user).values_list('id', flat=True)

            if not (set(managed_project_ids) & set(user_project_ids)) or ts.user == request.user:
                messages.error(request, "Access denied. You are not authorized to review this timesheet.")
                return redirect('work_time_reporter:team_approvals')

            if action == 'approve':
                ts.status = WeeklyTimesheet.Status.APPROVED
                ts.save()
                messages.success(request, f"Timesheet for {ts.user.username} approved! ✅")
            elif action == 'reject':
                ts.status = WeeklyTimesheet.Status.DRAFT
                ts.save()
                messages.warning(request, f"Timesheet for {ts.user.username} rejected and returned to draft. ❌")
        except WeeklyTimesheet.DoesNotExist:
            messages.error(request, "Timesheet not found.")

        return redirect('work_time_reporter:team_approvals')

    # We are looking for all subordinates in the manager's projects
    managed_users = User.objects.filter(assigned_projects__in=managed_projects).exclude(id=request.user.id).distinct()

    # We are looking for reports with the status SUBMITTED from these subordinates
    pending_timesheets = WeeklyTimesheet.objects.filter(
        status=WeeklyTimesheet.Status.SUBMITTED,
        user__in=managed_users
    ).order_by('user__username', '-year', '-week_number')

    # Add the total hours to each report for a nice output
    for ts in pending_timesheets:
        ts.total_hours = TimeLog.objects.filter(timesheet=ts).aggregate(Sum('hours'))['hours__sum'] or 0

    context = {
        'pending_timesheets': pending_timesheets
    }
    return render(request, 'work_time_reporter/team_approvals.html', context)


@login_required(login_url='work_time_reporter:login')
def timesheet_detail(request, timesheet_id):
    timesheet = get_object_or_404(WeeklyTimesheet, id=timesheet_id)

    # Access control: either the owner himself or his manager can view
    managed_projects = Project.objects.filter(manager=request.user, is_active=True)
    managed_users = User.objects.filter(assigned_projects__in=managed_projects)

    is_manager = request.user != timesheet.user and timesheet.user in managed_users
    is_owner = request.user == timesheet.user

    if not (is_manager or is_owner):
        messages.error(request, "Access denied. You don't have permission to view this timesheet.")
        return redirect('work_time_reporter:dashboard')

    # If the manager clicks Approve or Reject right here
    if request.method == 'POST' and is_manager:
        action = request.POST.get('action')
        if action == 'approve':
            timesheet.status = WeeklyTimesheet.Status.APPROVED
            timesheet.save()
            messages.success(request, f"Timesheet for {timesheet.user.username} approved! ✅")
            return redirect('work_time_reporter:team_approvals')
        elif action == 'reject':
            timesheet.status = WeeklyTimesheet.Status.DRAFT
            timesheet.save()
            messages.warning(request, f"Timesheet for {timesheet.user.username} rejected. ❌")
            return redirect('work_time_reporter:team_approvals')

    # Collecting the dates of the week
    monday = datetime.date.fromisocalendar(timesheet.year, timesheet.week_number, 1)
    week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]

    # We collect tasks for the user whose report this is!
    tasks = Task.objects.filter(assignees=timesheet.user).select_related('project')
    logs = TimeLog.objects.filter(timesheet=timesheet)
    # store complete log object in dict value to have access to comments
    log_dict = {(log.task_id, log.date): log for log in logs}

    grid_data = []
    daily_totals = [0] * 7
    weekly_total = 0

    # We build a matrix and immediately calculate all the sums
    for task in tasks:
        days_data = []
        row_total = 0
        for i, current_date in enumerate(week_dates):
            log = log_dict.get((task.id, current_date))

            if log and log.hours:
                hours_float = float(log.hours)
                row_total += hours_float
                daily_totals[i] += hours_float
                weekly_total += hours_float
                hours_str = str(log.hours).rstrip('0').rstrip('.')
                comment = log.comment  # add comments
            else:
                hours_str = ""
                comment = ""

            days_data.append({
                'date': current_date,
                'hours': hours_str,
                'comment': comment  # pass comment into template
            })

        # If the week is blocked and there are no hours at all - skip this task
        if timesheet.status != 'DRAFT' and row_total == 0:
            continue

        grid_data.append({
            'task': task,
            'days': days_data,
            'row_total': row_total
        })

    context = {
        'timesheet': timesheet,
        'week_dates': week_dates,
        'grid_data': grid_data,
        'daily_totals': daily_totals,
        'weekly_total': weekly_total,
        'is_manager': is_manager,
    }
    return render(request, 'work_time_reporter/timesheet_detail.html', context)


@login_required(login_url='work_time_reporter:login')
def yearly_dashboard(request, year=None):
    if not year:
        year = timezone.now().date().year

    # 1. Preparing data for the Weeks Matrix
    timesheets = WeeklyTimesheet.objects.filter(user=request.user, year=year)
    timesheet_dict = {ts.week_number: ts for ts in timesheets}

    weeks_data = []
    # A standard year has 52 weeks (sometimes 53, but for the grid we will take 52)
    for w in range(1, 53):
        ts = timesheet_dict.get(w)
        if ts:
            # Determine the color depending on the status
            if ts.status == WeeklyTimesheet.Status.APPROVED:
                color_class = 'bg-green-500 hover:bg-green-600 shadow-md cursor-pointer'
            elif ts.status == WeeklyTimesheet.Status.SUBMITTED:
                color_class = 'bg-yellow-400 hover:bg-yellow-500 shadow-md cursor-pointer'
            else:
                color_class = 'bg-gray-400 hover:bg-gray-500 shadow-md cursor-pointer'

            weeks_data.append({
                'week_num': w,
                'color': color_class,
                'status': ts.get_status_display(),
                'url': reverse('work_time_reporter:dashboard_week', args=[year, w])
            })
        else:
            # Empty week (not yet created)
            weeks_data.append({
                'week_num': w,
                'color': 'bg-gray-100 border border-dashed border-gray-300 hover:bg-indigo-50 cursor-pointer',
                'status': 'Not Started',
                'url': reverse('work_time_reporter:dashboard_week', args=[year, w])
            })

    # 2. Preparing data for the Pie Chart (ADMINISTRATIVE tasks are been ignored)
    year_logs = TimeLog.objects.filter(user=request.user, date__year=year)

    comm_hours = year_logs.filter(task__project__project_type='COMMERCIAL').aggregate(Sum('hours'))['hours__sum'] or 0
    non_comm_hours = year_logs.filter(task__project__project_type='INTERNAL').aggregate(Sum('hours'))[
                         'hours__sum'] or 0

    context = {
        'current_year': year,
        'weeks_data': weeks_data,
        'comm_hours': float(comm_hours),
        'non_comm_hours': float(non_comm_hours),
        'total_analyzed': float(comm_hours + non_comm_hours)
    }
    return render(request, 'work_time_reporter/yearly_dashboard.html', context)


@login_required(login_url='work_time_reporter:login')
def progress_dashboard(request, year=None):
    """
    This dashboard view allows to show full year picture about spending time on each task
    and where it towards the deadline
    """
    # 1. Determine the status of the requested year
    current_year = datetime.datetime.now().year

    if not year:
        year = current_year

    if year < current_year:
        year_status = 'past'
    elif year > current_year:
        year_status = 'future'
    else:
        year_status = 'current'

    # Use Service Layer to get calculated data
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
def calendar_settings(request, year=None):
    """
    Interactive yearly calendar for admins to set holidays and short days.
    """
    if not year:
        year = datetime.datetime.now().year

    # Check if current user is admin
    is_admin = request.user.is_superuser

    # --- AJAX HANDLER FOR CLICKING A DAY ---
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':

        # HARD SECURITY: Block POST requests from non-admins
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)

        data = json.loads(request.body)
        date_str = data.get('date')
        new_type = data.get('type')  # 'HOLIDAY', 'SHORT_DAY', 'FREE_MONDAY', or 'CLEAR'

        try:
            target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            if new_type == 'CLEAR':
                CompanyCalendar.objects.filter(date=target_date).delete()
            else:
                CompanyCalendar.objects.update_or_create(
                    date=target_date,
                    defaults={'day_type': new_type}
                )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # --- RENDER THE CALENDAR PAGE ---
    # Get all customized days for the requested year
    custom_days = CompanyCalendar.objects.filter(date__year=year).in_bulk(field_name='date')

    cal = calendar.Calendar(firstweekday=0)  # 0 = Monday
    months_data = []

    for month in range(1, 13):
        weeks = cal.monthdatescalendar(year, month)
        month_weeks = []
        for week in weeks:
            week_days = []
            for day in week:
                # We only show days belonging to the current month in this month's grid
                if day.month == month:
                    day_type = custom_days[day].day_type if day in custom_days else None
                    is_weekend = day.weekday() >= 5
                    week_days.append({
                        'date': day,
                        'day_num': day.day,
                        'is_weekend': is_weekend,
                        'day_type': day_type
                    })
                else:
                    week_days.append(None)  # Empty cell for padding
            month_weeks.append(week_days)

        months_data.append({
            'name': calendar.month_name[month],
            'weeks': month_weeks
        })

    context = {
        'year': year,
        'months_data': months_data,
        'types': CompanyCalendar.DAY_TYPE_CHOICES,
        'is_admin': is_admin,
    }
    return render(request, 'work_time_reporter/calendar_settings.html', context)
