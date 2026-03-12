import datetime

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import Task, WeeklyTimesheet, TimeLog


@login_required(login_url='/admin/login/')  # temporary use login from admin panel
def dashboard(request):
    # Determine the current day, year, and week number according to the ISO standard
    today = timezone.now().date()
    year, week_number, _ = today.isocalendar()

    # We are looking for a weekly report. If it does not exist yet, we automatically create it (Draft)
    timesheet, created = WeeklyTimesheet.objects.get_or_create(
        user=request.user,
        year=year,
        week_number=week_number,
        defaults={'status': WeeklyTimesheet.Status.DRAFT}
    )

    # Generate a list of 7 dates for the current week (Monday to Sunday)
    monday = today - datetime.timedelta(days=today.weekday())
    week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]

    # We get all the tasks for which the user is assigned
    tasks = Task.objects.filter(assignees=request.user).select_related('project')

    # Getting all the time logs for this weekly report
    logs = TimeLog.objects.filter(timesheet=timesheet)

    # We are making a convenient dictionary-cripple for quickly searching for hours by coordinates (task_id, date)
    log_dict = {(log.task_id, log.date): log.hours for log in logs}

    # Assembling the final "matrix" for the HTML template
    grid_data = []
    for task in tasks:
        days_data = []
        for current_date in week_dates:
            # We look for the hours in our dictionary. If not, we put an empty string
            hours = log_dict.get((task.id, current_date), "")
            days_data.append({
                'date': current_date,
                'hours': hours
            })

        grid_data.append({
            'task': task,
            'days': days_data
        })

    context = {
        'timesheet': timesheet,
        'week_dates': week_dates,
        'grid_data': grid_data,
        'today': today,
    }

    return render(request, 'work_time_reporter/dashboard.html', context)

