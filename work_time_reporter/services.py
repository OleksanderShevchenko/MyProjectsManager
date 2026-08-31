import datetime
from typing import Tuple

from django.db import transaction
from django.db.models import Sum, Min, Q, Max
from .models import Task, TimeLog, WeeklyTimesheet, Project

class TimesheetService:
    @staticmethod
    def save_timesheet_data(user, timesheet, post_data) -> dict:
        """
        Processes POST data from the dashboard to save or update time logs.
        """
        action = post_data.get('action')

        # Protection: if the status is not DRAFT, only recall is allowed
        if timesheet.status != WeeklyTimesheet.Status.DRAFT and action != 'recall':
            return {'success': False, 'message': "You cannot edit a submitted timesheet.", 'type': 'error'}

        if action in ['save', 'submit']:
            try:
                with transaction.atomic():
                    for key, value in post_data.items():
                        if key.startswith('hours_'):
                            parts = key.split('_')
                            if len(parts) == 3:
                                _, task_id, date_str = parts
                                try:
                                    task = Task.objects.get(id=task_id)
                                    log_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                                    # Looking for a hidden comment field for this cell
                                    comment_val = post_data.get(f'comment_{task_id}_{date_str}', '')
                                    # If the user entered hours (greater than 0)
                                    if value and float(value) > 0:
                                        TimeLog.objects.update_or_create(
                                            user=user,
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
                                            user=user,
                                            task=task,
                                            date=log_date
                                        ).delete()
                                except (Task.DoesNotExist, ValueError):
                                    pass
                    # Change the status if you clicked Submit
                    if action == 'submit':
                        logs = TimeLog.objects.filter(timesheet=timesheet)
                        weekly_total = sum(log.hours for log in logs)
                        if weekly_total == 0:
                            return {'success': False, 'message': "❌ Cannot submit an empty timesheet. Please log your hours first.", 'type': 'error'}

                        timesheet.status = WeeklyTimesheet.Status.SUBMITTED
                        timesheet.save()

                        if weekly_total != 40:
                            return {
                                'success': True,
                                'message': f"Timesheet submitted! 🚀 Note: Logged {weekly_total}h instead of standard 40h. Your manager will review the exceptions.",
                                'type': 'warning'
                            }
                        return {'success': True, 'message': "Timesheet submitted for approval! 🚀", 'type': 'success'}

                    return {'success': True, 'message': "Draft saved successfully! 💾", 'type': 'success'}
            except Exception as e:
                return {'success': False, 'message': f"Error saving timesheet: {str(e)}", 'type': 'error'}

        elif action == 'recall':
            if timesheet.status == WeeklyTimesheet.Status.SUBMITTED:
                timesheet.status = WeeklyTimesheet.Status.DRAFT
                timesheet.save()
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
