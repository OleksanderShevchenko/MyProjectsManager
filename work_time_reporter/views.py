import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Min, Q
from django.urls import reverse
from django.utils import timezone

from .models import Task, WeeklyTimesheet, TimeLog, Project

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
                            # Looking for a hidden comment field for this cell
                            comment_val = request.POST.get(f'comment_{task_id}_{date_str}', '')

                            # If the user entered hours (greater than 0)
                            if value and float(value) > 0:
                                TimeLog.objects.update_or_create(
                                    user=request.user,
                                    task=task,
                                    date=log_date,
                                    defaults={
                                        'hours': float(value),
                                        'comment': comment_val,
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

    daily_totals = [0] * 7
    weekly_total = 0

    for task in tasks:
        days_data = []
        row_total = 0  # variable for summing up hours per project/task

        for current_date in week_dates:
            # We look for the log in our dictionary. If not, we put hours and comments to an empty string
            log = log_dict.get((task.id, current_date))
            hours = log.hours if log else ""
            comment = log.comment if log else ""

            # Add to the total of the row if there are hours
            if log and log.hours:
                row_total += float(log.hours)

            days_data.append({
                'date': current_date,
                'hours': hours,
                'comment': comment
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


@login_required(login_url='work_time_reporter:login')
def team_approvals(request):
    # Check if the current user is a manager of at least one project
    managed_projects = Project.objects.filter(manager=request.user)

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
    managed_users = User.objects.filter(assigned_projects__in=managed_projects).distinct()

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
    managed_projects = Project.objects.filter(manager=request.user)
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
    if not year:
        year = datetime.datetime.now().year

    # 1. Fetch tasks and dynamically calculate spent hours and the first log date (Start Date)
    # Using Django's annotate() makes the database do the heavy lifting, making it blazing fast.
    # namely it creates for us virtual fields 'spent_hours' and 'start_date' that are useful for progress dashboard
    tasks = Task.objects.filter(
        assignees=request.user
    ).annotate(
        # Sum of hours logged for this specific year for each task and save it as new field 'spent_hours'
        spent_hours=Sum('time_logs__hours', filter=Q(time_logs__date__year=year)),  # Django ORM "magic"
        # Earliest date any hours were logged (acts as our dynamic Start Date)
        start_date=Min('time_logs__date', filter=Q(time_logs__date__year=year))
    ).select_related('project')

    # Filter out empty/closed tasks that have no activity this year
    tasks = tasks.filter(Q(project__is_active=True) | Q(spent_hours__gt=0)).distinct()

    grid_data = {}
    today = datetime.date.today()

    # 2. Process and group data by Project
    for task in tasks:
        if task.project not in grid_data:
            grid_data[task.project] = []

        spent = float(task.spent_hours) if task.spent_hours else 0.0
        budget = float(task.budget_hours) if task.budget_hours else 0.0

        # Budget Progress Calculation
        if budget > 0:
            budget_pct = min(100, (spent / budget) * 100)
            overbudget = spent > budget
        else:
            budget_pct = 100 if spent > 0 else 0
            overbudget = spent > 0

        # Timeline Calculation
        # Default start: First logged day OR Jan 1st
        start = task.start_date or datetime.date(year, 1, 1)
        # Default deadline: Task deadline OR Dec 31st
        deadline = task.deadline or datetime.date(year, 12, 31)

        total_days = (deadline - start).days
        if total_days <= 0: total_days = 1 # Prevent division by zero

        days_passed = (today - start).days
        # Clamp timeline percentage between 0 and 100
        time_pct = max(0, min(100, (days_passed / total_days) * 100))

        grid_data[task.project].append({
            'task': task,
            'spent': spent,
            'budget': budget,
            'budget_pct': budget_pct,
            'overbudget': overbudget,
            'start_date': start,
            'deadline': deadline,
            'time_pct': time_pct,
            'is_past_deadline': today > deadline,
        })

        # --- CUSTOM SORTING LOGIC ---
        # Display in dashboard commercial task the first then administrative and finally internal/non-commercial
        # 1. Define priority map for project types
        def get_project_priority(project):
            priority_map = {
                'COMMERCIAL': 1,
                'ADMINISTRATIVE': 2,
                'INTERNAL': 3
            }
            # Return the priority number (default to 4 if type is unknown/None)
            return priority_map.get(project.project_type, 4)

        # 2. Sort the grid_data dictionary
        # We sort by our custom priority first, and then alphabetically by project name
        sorted_grid_data = dict(sorted(
            grid_data.items(),
            key=lambda item: (get_project_priority(item[0]), item[0].name)
        ))

        # 3. Pass the SORTED dictionary to the template context
        context = {
            'year': year,
            'grid_data': sorted_grid_data,  # <-- Make sure to use sorted_grid_data here!
            'today': today,
        }
    return render(request, 'work_time_reporter/progress_dashboard.html', context)