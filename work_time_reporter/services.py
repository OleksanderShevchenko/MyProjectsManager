import calendar
import datetime
import logging
from typing import Tuple

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum, Min, Q, Max
from django.urls import reverse
from django.utils import timezone
from .models import Task, TimeLog, WeeklyTimesheet, Project, CompanyCalendar

logger = logging.getLogger(__name__)


class TimesheetService:
    @staticmethod
    def save_timesheet_data(user, timesheet, post_data) -> dict:
        """
        Processes POST data from the dashboard to save or update time logs.
        """
        action = post_data.get('action')

        # Protection: if the status is not DRAFT, only recall is allowed
        if timesheet.status != WeeklyTimesheet.Status.DRAFT and action != 'recall':
            return {'success': False, 'message': "You cannot edit a submitted timesheet. Please recall it first.", 'type': 'error'}

        if action in ['save', 'submit']:
            try:
                with transaction.atomic():
                    # Process form data
                    for key, value in post_data.items():
                        if not key.startswith('hours_'):
                            continue

                        parts = key.split('_')
                        if len(parts) < 3:
                            continue

                        task_id = parts[1]
                        date_str = parts[2]
                        hours_str = value.strip()

                        comment_key = f"comment_{task_id}_{date_str}"
                        comment_val = post_data.get(comment_key, '').strip()

                        try:
                            task = Task.objects.select_related('project').get(id=task_id)
                            log_date = datetime.date.fromisoformat(date_str)
                        except (Task.DoesNotExist, ValueError):
                            continue

                        # Validate task is assigned to the user
                        if not task.assignees.filter(id=user.id).exists():
                            continue

                        # Validate task's project is active (for non-admin users)
                        is_admin = user.is_superuser or getattr(user, 'is_admin_role', False)
                        if not task.project.is_active and not is_admin:
                            continue

                        if hours_str:
                            try:
                                hours_val = float(hours_str)
                            except ValueError:
                                return {
                                    'success': False,
                                    'message': f"Invalid hours value '{hours_str}'. Must be a valid number.",
                                    'type': 'error'
                                }

                            if hours_val < 0 or hours_val > 24:
                                logger.warning(
                                    "Invalid hours value '%s' submitted by user %s for task %s on date %s",
                                    hours_str,
                                    user.username,
                                    task_id,
                                    date_str,
                                )
                                return {
                                    'success': False,
                                    'message': "Hours must be between 0 and 24.",
                                    'type': 'error'
                                }

                            if hours_val > 0:
                                TimeLog.objects.update_or_create(
                                    user=user,
                                    task=task,
                                    date=log_date,
                                    defaults={
                                        'hours': hours_val,
                                        'comment': comment_val,
                                        'timesheet': timesheet
                                    }
                                )
                            elif hours_val == 0:
                                TimeLog.objects.filter(
                                    user=user,
                                    task=task,
                                    date=log_date
                                ).delete()
                        else:
                            TimeLog.objects.filter(
                                user=user,
                                task=task,
                                date=log_date
                            ).delete()
                    # Change the status if you clicked Submit
                    if action == 'submit':
                        logs = TimeLog.objects.filter(timesheet=timesheet)
                        weekly_total = sum(log.hours for log in logs)
                        if weekly_total == 0:
                            logger.warning("User %s attempted to submit empty timesheet %s", user.username, timesheet.id)
                            return {'success': False, 'message': "❌ Cannot submit an empty timesheet. Please log your hours first.", 'type': 'error'}

                        timesheet.status = WeeklyTimesheet.Status.SUBMITTED
                        timesheet.submitted_at = timezone.now()
                        timesheet.rejection_comment = ''  # Clear any previous rejection comment upon resubmission
                        timesheet.save()

                        logger.info(
                            "Timesheet %s (Year: %s, Week: %s) submitted by user %s with total %s hours",
                            timesheet.id,
                            timesheet.year,
                            timesheet.week_number,
                            user.username,
                            weekly_total,
                        )

                        if weekly_total != 40:
                            logger.warning(
                                "Timesheet %s submitted with non-standard hours (%sh) by user %s",
                                timesheet.id,
                                weekly_total,
                                user.username,
                            )
                            return {
                                'success': True,
                                'message': f"Timesheet submitted! 🚀 Note: Logged {weekly_total}h instead of standard 40h. Your manager will review the exceptions.",
                                'type': 'warning'
                            }
                        return {'success': True, 'message': "Timesheet submitted for approval! 🚀", 'type': 'success'}

                    logger.info(
                        "Timesheet %s (Year: %s, Week: %s) draft saved by user %s",
                        timesheet.id,
                        timesheet.year,
                        timesheet.week_number,
                        user.username,
                    )
                    return {'success': True, 'message': "Draft saved successfully! 💾", 'type': 'success'}
            except Exception as e:
                logger.error("Error saving timesheet %s for user %s: %s", timesheet.id, user.username, str(e), exc_info=True)
                return {'success': False, 'message': f"Error saving timesheet: {str(e)}", 'type': 'error'}

        elif action == 'recall':
            if timesheet.status == WeeklyTimesheet.Status.SUBMITTED:
                timesheet.status = WeeklyTimesheet.Status.DRAFT
                timesheet.submitted_at = None
                timesheet.save()
                logger.info("Timesheet %s recalled to draft by user %s", timesheet.id, user.username)
                return {'success': True, 'message': "Timesheet recalled to draft. You can edit it again. ↩️", 'type': 'info'}

        return {'success': False, 'message': "Unknown action.", 'type': 'error'}

    @staticmethod
    def get_progress_data(user, year, year_status) -> Tuple[list, dict] :
        """
        Calculates integral and task-level progress data for the progress dashboard.
        """
        integral_data = []
        today = datetime.date.today()
        # 2. Only calculate Integral Progress if we are looking at the CURRENT year
        if year_status == 'current':
            project_summary = Project.objects.filter(
                Q(is_active=True) & ~Q(project_type='ADMINISTRATIVE') & Q(tasks__assignees=user)
            ).annotate(
                total_budget=Sum('tasks__budget_hours', filter=Q(tasks__assignees=user)),
                total_spent=Sum('tasks__time_logs__hours',
                                filter=Q(tasks__time_logs__date__year=year, tasks__time_logs__user=user)),
                project_start=Min('tasks__time_logs__date',
                                  filter=Q(tasks__time_logs__date__year=year, tasks__time_logs__user=user)),
                project_deadline=Max('tasks__deadline', filter=Q(tasks__assignees=user))
            ).filter(total_spent__gt=0).distinct().order_by('project_type', 'name')

            for proj in project_summary:
                spent = float(proj.total_spent or 0)
                budget = float(proj.total_budget or 0)

                budget_pct = min(100, (spent / budget * 100)) if budget > 0 else 0
                start = proj.project_start or datetime.date(year, 1, 1)
                deadline = proj.project_deadline or datetime.date(year, 12, 31)

                total_days = (deadline - start).days or 1
                days_passed = (today - start).days
                time_pct = max(0, min(100, (days_passed / total_days * 100)))

                integral_data.append({
                    'project': proj,
                    'budget_pct': budget_pct,
                    'time_pct': time_pct,
                    'spent': spent,
                    'budget': budget,
                    'is_overbudget': spent > budget
                })
        # 3. Fetch tasks and dynamically calculate spent hours and the first log date (Start Date)
        # Using Django's annotate() makes the database do the heavy lifting, making it blazing fast.
        # namely it creates for us virtual fields 'spent_hours' and 'start_date' that are useful for progress dashboard
        tasks = Task.objects.filter(
            assignees=user
        ).annotate(
            # Sum of hours logged for this specific year for each task and save it as new field 'spent_hours'
            spent_hours=Sum('time_logs__hours', filter=Q(time_logs__date__year=year)),
            # Earliest date any hours were logged (acts as our dynamic Start Date)
            start_date=Min('time_logs__date', filter=Q(time_logs__date__year=year))
        ).select_related('project')
        # Filter out empty/closed tasks that have no activity this year
        tasks = tasks.filter(Q(project__is_active=True) | Q(spent_hours__gt=0)).distinct()

        grid_data = {}
        # 4. Process and group data by Project
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

            total_days = (deadline - start).days or 1

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
        #  Define priority map for project types
        def get_project_priority(project):
            priority_map = {'COMMERCIAL': 1, 'ADMINISTRATIVE': 2, 'INTERNAL': 3}
            # Return the priority number (default to 4 if type is unknown/None)
            return priority_map.get(project.project_type, 4)

        # 5. Sort the grid_data dictionary
        # We sort by our custom priority first, and then alphabetically by project name
        sorted_grid_data = dict(sorted(
            grid_data.items(),
            key=lambda item: (get_project_priority(item[0]), item[0].name)
        ))

        return integral_data, sorted_grid_data

    @staticmethod
    def get_or_create_timesheet(user, year: int, week: int) -> Tuple[WeeklyTimesheet, list, int, int, int, int]:
        """
        Validates the ISO year/week, retrieves or creates the WeeklyTimesheet in DRAFT status,
        and computes adjacent navigation weeks and dates.
        """
        monday = datetime.date.fromisocalendar(year, week, 1)
        timesheet, _ = WeeklyTimesheet.objects.get_or_create(
            user=user,
            year=year,
            week_number=week,
            defaults={'status': WeeklyTimesheet.Status.DRAFT}
        )
        week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]
        prev_monday = monday - datetime.timedelta(days=7)
        prev_year, prev_week, _ = prev_monday.isocalendar()
        next_monday = monday + datetime.timedelta(days=7)
        next_year, next_week, _ = next_monday.isocalendar()
        return timesheet, week_dates, prev_year, prev_week, next_year, next_week

    @staticmethod
    def build_weekly_grid(user, timesheet: WeeklyTimesheet, week_dates: list) -> dict:
        """
        Builds the weekly hours and days matrix for assigned tasks grouped by project.
        """
        tasks = Task.objects.filter(
            Q(assignees=user) &
            (Q(project__is_active=True) | Q(time_logs__timesheet=timesheet))
        ).distinct().select_related('project')

        logs = TimeLog.objects.filter(timesheet=timesheet)
        log_dict = {(log.task_id, log.date): log for log in logs}

        grid_data = {}
        calendar_events = CompanyCalendar.objects.filter(
            date__range=[week_dates[0], week_dates[-1]]
        ).in_bulk(field_name='date')

        for task in tasks:
            days_data = []
            row_total = 0.0

            for current_date in week_dates:
                hours = ''
                comment = ''

                log = log_dict.get((task.id, current_date))
                if log:
                    hours = log.hours
                    row_total += float(hours)
                    comment = log.comment

                is_weekend = current_date.weekday() >= 5
                is_holiday = False
                is_free_monday = False
                is_short_day = False

                if current_date in calendar_events:
                    event = calendar_events[current_date]
                    if event.day_type in ['HOLIDAY', 'FREE_MONDAY']:
                        is_holiday = True
                        is_free_monday = (event.day_type == 'FREE_MONDAY')
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

            if timesheet.status != WeeklyTimesheet.Status.DRAFT and row_total == 0:
                continue

            if task.project not in grid_data:
                grid_data[task.project] = []

            grid_data[task.project].append({
                'task': task,
                'days': days_data,
                'row_total': row_total
            })

        return grid_data

    @staticmethod
    def build_mini_dashboard(user, projects) -> list:
        """
        Quick overview of project budgets for the projects present in the weekly grid.
        """
        mini_dashboard = []
        for project in projects:
            tasks_in_proj = Task.objects.filter(project=project, assignees=user)
            budget = sum(t.budget_hours for t in tasks_in_proj if t.budget_hours)
            spent_result = TimeLog.objects.filter(task__in=tasks_in_proj, user=user).aggregate(
                total=Sum('hours')
            )
            spent = float(spent_result['total'] or 0.0)

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
        return mini_dashboard

    @staticmethod
    def get_user_managed_projects(user):
        """
        Returns active projects managed by the given user.
        """
        return Project.objects.filter(manager=user, is_active=True)

    @staticmethod
    def get_pending_approvals(manager_user):
        """
        Retrieves pending submitted timesheets for subordinates in manager's active projects.
        """
        managed_projects = Project.objects.filter(manager=manager_user, is_active=True)
        if not managed_projects.exists():
            return WeeklyTimesheet.objects.none()

        user_model = get_user_model()
        managed_users = user_model.objects.filter(
            assigned_projects__in=managed_projects
        ).exclude(id=manager_user.id).distinct()

        pending_timesheets = WeeklyTimesheet.objects.filter(
            status=WeeklyTimesheet.Status.SUBMITTED,
            user__in=managed_users
        ).order_by('user__username', '-year', '-week_number')

        for ts in pending_timesheets:
            ts.total_hours = TimeLog.objects.filter(timesheet=ts).aggregate(Sum('hours'))['hours__sum'] or 0

        return pending_timesheets

    @staticmethod
    def review_timesheet(reviewer, timesheet_id: int, action: str, rejection_comment: str = '') -> dict:
        """
        Validates manager review permissions and executes approve or reject action on a timesheet.
        """
        managed_projects = Project.objects.filter(manager=reviewer, is_active=True)
        if not managed_projects.exists():
            logger.warning(
                "Unauthorized review attempt: user %s is not a manager of any active project",
                reviewer.username,
            )
            return {
                'success': False,
                'message': "Access denied. You are not a manager of any active project.",
                'type': 'error'
            }

        try:
            ts = WeeklyTimesheet.objects.get(id=timesheet_id)
        except WeeklyTimesheet.DoesNotExist:
            logger.warning(
                "Timesheet review failed: timesheet %s does not exist (reviewer: %s)",
                timesheet_id,
                reviewer.username,
            )
            return {'success': False, 'message': "Timesheet not found.", 'type': 'error'}

        managed_project_ids = managed_projects.values_list('id', flat=True)
        user_project_ids = Project.objects.filter(members=ts.user).values_list('id', flat=True)

        if not (set(managed_project_ids) & set(user_project_ids)) or ts.user == reviewer:
            logger.warning(
                "Unauthorized review attempt by user %s on timesheet %s (owner: %s)",
                reviewer.username,
                timesheet_id,
                ts.user.username,
            )
            return {
                'success': False,
                'message': "Access denied. You are not authorized to review this timesheet.",
                'type': 'error'
            }

        if action == 'approve':
            ts.status = WeeklyTimesheet.Status.APPROVED
            ts.approved_at = timezone.now()
            ts.approved_by = reviewer
            ts.save()
            logger.info(
                "Timesheet %s (owner: %s) approved by manager %s",
                ts.id,
                ts.user.username,
                reviewer.username,
            )
            return {'success': True, 'message': f"Timesheet for {ts.user.username} approved! ✅", 'type': 'success'}
        elif action == 'reject':
            ts.status = WeeklyTimesheet.Status.DRAFT
            ts.rejection_comment = rejection_comment.strip()
            ts.save()
            logger.info(
                "Timesheet %s (owner: %s) rejected by manager %s. Feedback: %s",
                ts.id,
                ts.user.username,
                reviewer.username,
                ts.rejection_comment,
            )
            return {
                'success': True,
                'message': f"Timesheet for {ts.user.username} rejected with feedback and returned to draft. ❌",
                'type': 'warning'
            }

        logger.warning(
            "Invalid review action '%s' attempted by user %s on timesheet %s",
            action,
            reviewer.username,
            timesheet_id,
        )
        return {'success': False, 'message': "Unknown action.", 'type': 'error'}

    @staticmethod
    def get_timesheet_detail_data(viewer, timesheet_id: int) -> Tuple[WeeklyTimesheet | None, dict | None, str | None]:
        """
        Retrieves timesheet detail context including permissions, grid, and daily/weekly totals.
        Returns (timesheet, detail_context, error_message).
        """
        try:
            timesheet = WeeklyTimesheet.objects.select_related('user').get(id=timesheet_id)
        except WeeklyTimesheet.DoesNotExist:
            return None, None, "Timesheet not found."

        managed_projects = Project.objects.filter(manager=viewer, is_active=True)
        user_model = get_user_model()
        managed_users = user_model.objects.filter(assigned_projects__in=managed_projects)

        is_manager = viewer != timesheet.user and timesheet.user in managed_users
        is_owner = viewer == timesheet.user

        if not (is_manager or is_owner):
            return None, None, "Access denied. You don't have permission to view this timesheet."

        monday = datetime.date.fromisocalendar(timesheet.year, timesheet.week_number, 1)
        week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]

        tasks = Task.objects.filter(assignees=timesheet.user).select_related('project')
        logs = TimeLog.objects.filter(timesheet=timesheet)
        log_dict = {(log.task_id, log.date): log for log in logs}

        grid_data = []
        daily_totals = [0.0] * 7
        weekly_total = 0.0

        for task in tasks:
            days_data = []
            row_total = 0.0
            for i, current_date in enumerate(week_dates):
                log = log_dict.get((task.id, current_date))

                if log and log.hours:
                    hours_float = float(log.hours)
                    row_total += hours_float
                    daily_totals[i] += hours_float
                    weekly_total += hours_float
                    hours_str = str(log.hours).rstrip('0').rstrip('.')
                    comment = log.comment
                else:
                    hours_str = ""
                    comment = ""

                days_data.append({
                    'date': current_date,
                    'hours': hours_str,
                    'comment': comment
                })

            if timesheet.status != WeeklyTimesheet.Status.DRAFT and row_total == 0:
                continue

            grid_data.append({
                'task': task,
                'days': days_data,
                'row_total': row_total
            })

        detail_context = {
            'timesheet': timesheet,
            'week_dates': week_dates,
            'grid_data': grid_data,
            'daily_totals': daily_totals,
            'weekly_total': weekly_total,
            'is_manager': is_manager,
        }
        return timesheet, detail_context, None

    @staticmethod
    def get_yearly_data(user, year: int) -> dict:
        """
        Prepares weekly overview matrix and distribution metrics for the yearly dashboard.
        """
        timesheets = WeeklyTimesheet.objects.filter(user=user, year=year)
        timesheet_dict = {ts.week_number: ts for ts in timesheets}

        # ISO 8601 standard: December 28th is always in the last week of the year (52 or 53)
        max_weeks = datetime.date(year, 12, 28).isocalendar()[1]

        weeks_data = []
        for w in range(1, max_weeks + 1):
            ts = timesheet_dict.get(w)
            if ts:
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
                weeks_data.append({
                    'week_num': w,
                    'color': 'bg-gray-100 border border-dashed border-gray-300 hover:bg-indigo-50 cursor-pointer',
                    'status': 'Not Started',
                    'url': reverse('work_time_reporter:dashboard_week', args=[year, w])
                })

        year_logs = TimeLog.objects.filter(user=user, date__year=year)
        comm_hours = year_logs.filter(task__project__project_type='COMMERCIAL').aggregate(Sum('hours'))['hours__sum'] or 0
        non_comm_hours = year_logs.filter(task__project__project_type='INTERNAL').aggregate(Sum('hours'))['hours__sum'] or 0

        return {
            'current_year': year,
            'weeks_data': weeks_data,
            'comm_hours': float(comm_hours),
            'non_comm_hours': float(non_comm_hours),
            'total_analyzed': float(comm_hours + non_comm_hours)
        }


class CalendarService:
    @staticmethod
    def update_day(date_str: str, new_type: str) -> dict:
        """
        Updates or clears a customized day in CompanyCalendar.
        """
        try:
            target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            if new_type == 'CLEAR':
                CompanyCalendar.objects.filter(date=target_date).delete()
                logger.info("Company calendar customization cleared for date %s", target_date)
            else:
                CompanyCalendar.objects.update_or_create(
                    date=target_date,
                    defaults={'day_type': new_type}
                )
                logger.info("Company calendar updated for date %s: day_type=%s", target_date, new_type)
            return {'success': True}
        except Exception as e:
            logger.error("Failed to update company calendar for date %s: %s", date_str, str(e), exc_info=True)
            return {'success': False, 'message': str(e)}

    @staticmethod
    def get_year_calendar_data(year: int) -> list:
        """
        Generates 12-month calendar grid with company calendar customized day types.
        """
        custom_days = CompanyCalendar.objects.filter(date__year=year).in_bulk(field_name='date')
        cal = calendar.Calendar(firstweekday=0)
        months_data = []

        for month in range(1, 13):
            weeks = cal.monthdatescalendar(year, month)
            month_weeks = []
            for week in weeks:
                week_days = []
                for day in week:
                    if day.month == month:
                        day_type = custom_days[day].day_type if day in custom_days else None
                        is_weekend = day.weekday() >= 5
                        week_days.append({
                            'date': day,
                            'day_num': day.day,
                            'is_weekend': is_weekend,
                            'day_type': day_type,
                            'next_type': CalendarService.get_next_day_type(day_type),
                        })
                    else:
                        week_days.append(None)
                month_weeks.append(week_days)

            months_data.append({
                'name': calendar.month_name[month],
                'weeks': month_weeks
            })
        return months_data

    @staticmethod
    def get_next_day_type(current_type: str | None) -> str:
        """
        Returns the next day type in the rotation cycle:
        Standard (None) -> HOLIDAY -> SHORT_DAY -> FREE_MONDAY -> CLEAR (Standard).
        """
        cycle = {
            None: 'HOLIDAY',
            '': 'HOLIDAY',
            'HOLIDAY': 'SHORT_DAY',
            'SHORT_DAY': 'FREE_MONDAY',
            'FREE_MONDAY': 'CLEAR',
        }
        return cycle.get(current_type, 'HOLIDAY')
