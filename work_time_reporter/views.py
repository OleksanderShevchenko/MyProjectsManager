import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone

from .models import Task, WeeklyTimesheet, TimeLog


@login_required(login_url='work_time_reporter:login')  # temporary use login from admin panel
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
        action = request.POST.get('action')

        # Protection: if the status is not DRAFT, only recall is allowed
        if timesheet.status != WeeklyTimesheet.Status.DRAFT and action != 'recall':
            messages.error(request, "You cannot edit a submitted timesheet.")
            return redirect('work_time_reporter:dashboard_week', year=year, week=week)

        if action in ['save', 'submit']:
            # We go through all the data that came from the table
            for key, value in request.POST.items():
                if key.startswith('hours_'):
                    # Parse the cell name: hours_15_2026-03-12
                    parts = key.split('_')
                    if len(parts) == 3:
                        _, task_id, date_str = parts

                        try:
                            task = Task.objects.get(id=task_id)
                            log_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()

                            # If the user entered hours (greater than 0)
                            if value and float(value) > 0:
                                TimeLog.objects.update_or_create(
                                    user=request.user,
                                    task=task,
                                    date=log_date,
                                    defaults={
                                        'hours': float(value),
                                        'timesheet': timesheet
                                    }
                                )
                            # If the cell is empty or 0, we delete the record so as not to clutter the database.
                            else:
                                TimeLog.objects.filter(
                                    user=request.user,
                                    task=task,
                                    date=log_date
                                ).delete()
                        except (Task.DoesNotExist, ValueError):
                            pass

            # Change the status if you clicked Submit
            if action == 'submit':
                # Get all logs for this week
                logs = TimeLog.objects.filter(timesheet=timesheet)

                # Calculate the sum of hours for each date in the dictionary: {date: total_hours}
                daily_totals = {}
                for log in logs:
                    daily_totals[log.date] = daily_totals.get(log.date, 0) + log.hours

                # Determine the dates from Monday to Friday (5 working days) of the current week
                workdays = [monday + datetime.timedelta(days=i) for i in range(5)]
                invalid_days = []

                # We check EVERY working day
                for day in workdays:
                    # If there are no logs on this day, get() will return 0
                    total_for_day = daily_totals.get(day, 0)
                    if total_for_day != 8:
                        invalid_days.append(day.strftime('%d.%m'))

                # If at least one working day is not equal to 8 — block the submission
                if invalid_days:
                    messages.error(request,
                                   f"❌ Validation failed: You must log exactly 8 hours per workday. Check these dates: {', '.join(invalid_days)}.")
                else:
                    timesheet.status = WeeklyTimesheet.Status.SUBMITTED
                    timesheet.save()
                    messages.success(request, "Timesheet submitted for approval! 🚀")
            else:
                messages.success(request, "Draft saved successfully! 💾")

        # Revert a report back to draft
        elif action == 'recall':
            if timesheet.status == WeeklyTimesheet.Status.SUBMITTED:
                timesheet.status = WeeklyTimesheet.Status.DRAFT
                timesheet.save()
                messages.info(request, "Timesheet recalled to draft. You can edit it again. ↩️")

        # Reload the page to show updated data.
        return redirect('work_time_reporter:dashboard_week', year=year, week=week)

    # Generate a list of 7 dates for the current week (Monday to Sunday)
    week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]

    # Calculating adjacent weeks for Navigation buttons
    prev_monday = monday - datetime.timedelta(days=7)
    prev_year, prev_week, _ = prev_monday.isocalendar()

    next_monday = monday + datetime.timedelta(days=7)
    next_year, next_week, _ = next_monday.isocalendar()

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
        # Pass data for buttons to template
        'prev_year': prev_year,
        'prev_week': prev_week,
        'next_year': next_year,
        'next_week': next_week,
    }

    return render(request, 'work_time_reporter/dashboard.html', context)

