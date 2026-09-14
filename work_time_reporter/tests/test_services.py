import datetime
import logging
import pytest
from django.utils import timezone

from work_time_reporter.models import (
    Project,
    Task,
    WeeklyTimesheet,
    TimeLog,
    CompanyCalendar
)
from work_time_reporter.services import TimesheetService, CalendarService


@pytest.mark.django_db
class TestTimesheetServiceSaveAndSubmit:
    def test_save_draft_creates_and_updates_timelogs(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify saving draft correctly creates and updates TimeLog records."""
        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '8.0',
            f'comment_{active_task.id}_2026-08-24': 'Working on core architecture',
            f'hours_{active_task.id}_2026-08-25': '6.5',
            f'comment_{active_task.id}_2026-08-25': 'Refactoring models'
        }

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)

        assert result['success'] is True
        assert result['type'] == 'success'
        assert "Draft saved successfully" in result['message']

        # Verify records created in database
        logs = TimeLog.objects.filter(timesheet=draft_timesheet)
        assert logs.count() == 2

        log_mon = TimeLog.objects.get(task=active_task, date=datetime.date(2026, 8, 24))
        assert float(log_mon.hours) == 8.0
        assert log_mon.comment == 'Working on core architecture'

        log_tue = TimeLog.objects.get(task=active_task, date=datetime.date(2026, 8, 25))
        assert float(log_tue.hours) == 6.5

    def test_save_draft_clears_zero_or_empty_hour_logs(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify setting hours to 0 or empty deletes existing TimeLog record."""
        # Pre-populate a time log
        log_date = datetime.date(2026, 8, 24)
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=log_date,
            hours=8.0
        )
        assert TimeLog.objects.filter(task=active_task, date=log_date).exists()

        # Send post data with empty / zero hours
        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '0'
        }

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is True
        assert not TimeLog.objects.filter(task=active_task, date=log_date).exists()

    def test_submit_empty_timesheet_rejected(
        self, engineer_user, draft_timesheet
    ):
        """Verify submitting an empty timesheet (0 total hours) is rejected with error."""
        post_data = {'action': 'submit'}

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)

        assert result['success'] is False
        assert result['type'] == 'error'
        assert "Cannot submit an empty timesheet" in result['message']

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT

    def test_submit_standard_40h_succeeds_with_success_type(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify submitting a timesheet with exactly 40 hours succeeds with success status."""
        # Populate 5 days x 8 hours = 40 hours
        post_data = {'action': 'submit'}
        for day in range(24, 29):
            post_data[f'hours_{active_task.id}_2026-08-{day}'] = '8.0'

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)

        assert result['success'] is True
        assert result['type'] == 'success'
        assert "submitted for approval" in result['message']

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.SUBMITTED

    def test_submit_non_40h_returns_warning_type(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify submitting non-40h timesheet succeeds with warning message for manager review."""
        post_data = {
            'action': 'submit',
            f'hours_{active_task.id}_2026-08-24': '8.0',
            f'hours_{active_task.id}_2026-08-25': '8.0'
            # Total 16 hours instead of 40h
        }

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)

        assert result['success'] is True
        assert result['type'] == 'warning'
        assert "Logged 16" in result['message']
        assert "instead of standard 40h" in result['message']

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.SUBMITTED

    def test_submit_timesheet_sets_submitted_at_and_clears_rejection_comment(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify submitting a timesheet sets submitted_at and clears previous rejection comment."""
        draft_timesheet.rejection_comment = "Fix Tuesday hours"
        draft_timesheet.save()

        post_data = {
            'action': 'submit',
            f'hours_{active_task.id}_2026-08-24': '8.0'
        }

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is True

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.SUBMITTED
        assert draft_timesheet.submitted_at is not None
        assert draft_timesheet.rejection_comment == ''

    def test_recall_submitted_timesheet_resets_to_draft(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify recalling a SUBMITTED timesheet changes status back to DRAFT and clears submitted_at."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.submitted_at = timezone.now()
        draft_timesheet.save()

        post_data = {'action': 'recall'}
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)

        assert result['success'] is True
        assert result['type'] == 'info'
        assert "recalled to draft" in result['message']

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT
        assert draft_timesheet.submitted_at is None

    def test_edit_submitted_timesheet_is_blocked(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify editing a SUBMITTED timesheet without recalling is rejected."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '8.0'
        }

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is False
        assert "cannot edit a submitted timesheet" in result['message']

    def test_save_hours_greater_than_24_rejected(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify hours exceeding 24 per day are rejected."""
        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '25.0'
        }
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is False
        assert result['type'] == 'error'
        assert "Hours must be between 0 and 24" in result['message']

    def test_save_negative_hours_rejected(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify negative hours values are rejected."""
        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '-2.0'
        }
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is False
        assert result['type'] == 'error'
        assert "Hours must be between 0 and 24" in result['message']

    def test_save_invalid_hours_string_rejected(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify non-numeric hours values return an error."""
        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': 'invalid_hours'
        }
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is False
        assert result['type'] == 'error'
        assert "Must be a valid number" in result['message']

    def test_save_unassigned_task_ignored(
        self, engineer_user, active_project, draft_timesheet
    ):
        """Verify user cannot log hours for tasks they are not assigned to."""
        unassigned_task = Task.objects.create(
            title="Unassigned Task",
            project=active_project,
            budget_hours=10
        )
        post_data = {
            'action': 'save',
            f'hours_{unassigned_task.id}_2026-08-24': '8.0'
        }
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is True
        assert not TimeLog.objects.filter(task=unassigned_task, user=engineer_user).exists()

    def test_save_inactive_project_task_ignored_for_regular_user(
        self, engineer_user, active_project, active_task, draft_timesheet
    ):
        """Verify regular users cannot log hours for tasks belonging to inactive projects."""
        active_project.is_active = False
        active_project.save()

        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '8.0'
        }
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is True
        assert not TimeLog.objects.filter(task=active_task, user=engineer_user).exists()

    def test_save_inactive_project_task_allowed_for_admin(
        self, engineer_user, active_project, active_task, draft_timesheet
    ):
        """Verify admin users can log hours even if the project is inactive."""
        active_project.is_active = False
        active_project.save()
        engineer_user.is_superuser = True
        engineer_user.save()

        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '8.0'
        }
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result['success'] is True
        assert TimeLog.objects.filter(task=active_task, user=engineer_user).exists()


@pytest.mark.django_db
class TestTimesheetServiceProgressData:
    def test_get_progress_data_budget_and_overbudget_calculation(
        self, engineer_user, manager_user
    ):
        """Verify integral progress and task budget calculations."""
        current_year = timezone.now().year

        project = Project.objects.create(
            name="Alpha Project",
            project_type=Project.ProjectType.COMMERCIAL,
            year=current_year,
            manager=manager_user,
            is_active=True
        )
        project.members.add(engineer_user)

        task = Task.objects.create(
            title="Task 1",
            project=project,
            budget_hours=20
        )
        task.assignees.add(engineer_user)

        # Log 25 hours (overbudget!)
        timesheet = WeeklyTimesheet.objects.create(
            user=engineer_user,
            year=current_year,
            week_number=19,
            status=WeeklyTimesheet.Status.DRAFT
        )
        TimeLog.objects.create(
            user=engineer_user,
            task=task,
            timesheet=timesheet,
            date=datetime.date(current_year, 5, 10),
            hours=25.0
        )

        integral_data, grid_data = TimesheetService.get_progress_data(
            user=engineer_user,
            year=current_year,
            year_status='current'
        )

        assert len(integral_data) == 1
        summary = integral_data[0]
        assert summary['project'] == project
        assert summary['spent'] == 25.0
        assert summary['budget'] == 20.0
        assert summary['is_overbudget'] is True
        assert summary['budget_pct'] == 100

    def test_get_progress_data_sorting_by_project_type_priority(
        self, engineer_user, manager_user
    ):
        """Verify sorting order: Commercial first, then Administrative, then Internal."""
        current_year = timezone.now().year

        # Create 3 projects of different types
        p_internal = Project.objects.create(
            name="Z-Internal",
            project_type=Project.ProjectType.INTERNAL,
            year=current_year,
            manager=manager_user,
            is_active=True
        )
        p_admin = Project.objects.create(
            name="A-Admin",
            project_type=Project.ProjectType.ADMINISTRATIVE,
            year=current_year,
            manager=manager_user,
            is_active=True
        )
        p_comm = Project.objects.create(
            name="Z-Commercial",
            project_type=Project.ProjectType.COMMERCIAL,
            year=current_year,
            manager=manager_user,
            is_active=True
        )

        for p in [p_internal, p_admin, p_comm]:
            t = Task.objects.create(title=f"Task for {p.name}", project=p, budget_hours=10)
            t.assignees.add(engineer_user)

        _, grid_data = TimesheetService.get_progress_data(
            user=engineer_user,
            year=current_year,
            year_status='current'
        )

        project_order = [p.project_type for p in grid_data.keys()]
        assert project_order == [
            Project.ProjectType.COMMERCIAL,
            Project.ProjectType.ADMINISTRATIVE,
            Project.ProjectType.INTERNAL
        ]


@pytest.mark.django_db
class TestTimesheetServiceExtractedMethods:
    def test_get_or_create_timesheet(self, engineer_user):
        """Verify get_or_create_timesheet returns timesheet, week_dates and navigation info."""
        ts, week_dates, prev_y, prev_w, next_y, next_w = TimesheetService.get_or_create_timesheet(
            engineer_user, 2026, 35
        )
        assert ts.user == engineer_user
        assert ts.year == 2026
        assert ts.week_number == 35
        assert ts.status == WeeklyTimesheet.Status.DRAFT
        assert len(week_dates) == 7
        assert week_dates[0] == datetime.date(2026, 8, 24)
        assert week_dates[-1] == datetime.date(2026, 8, 30)
        assert (prev_y, prev_w) == (2026, 34)
        assert (next_y, next_w) == (2026, 36)

    def test_build_weekly_grid_and_mini_dashboard(
        self, engineer_user, active_project, active_task, draft_timesheet
    ):
        """Verify weekly grid assembly with calendar events and mini dashboard calculation."""
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)
        week_dates = [monday + datetime.timedelta(days=i) for i in range(7)]

        # Create a company calendar holiday on Wednesday
        CompanyCalendar.objects.create(date=monday + datetime.timedelta(days=2), day_type='HOLIDAY')

        # Log hours on Monday
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=monday,
            hours=7.5,
            comment="Refactoring work"
        )

        grid_data = TimesheetService.build_weekly_grid(engineer_user, draft_timesheet, week_dates)
        assert active_project in grid_data
        task_row = grid_data[active_project][0]
        assert task_row['task'] == active_task
        assert task_row['row_total'] == 7.5
        assert task_row['days'][0]['hours'] == 7.5
        assert task_row['days'][0]['comment'] == "Refactoring work"
        assert task_row['days'][2]['is_holiday'] is True

        mini_dash = TimesheetService.build_mini_dashboard(engineer_user, grid_data.keys())
        assert len(mini_dash) == 1
        assert mini_dash[0]['name'] == active_project.name
        assert mini_dash[0]['spent'] == 7.5

    def test_get_pending_approvals(
        self, manager_user, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Verify get_pending_approvals fetches submitted timesheets for managed team members."""
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=monday,
            hours=8.0
        )

        pending = TimesheetService.get_pending_approvals(manager_user)
        assert pending.count() == 1
        assert pending.first().total_hours == 8.0

    def test_review_timesheet_approve_and_reject(
        self, manager_user, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Verify manager can approve and reject subordinate timesheets with comments."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        # Reject
        reject_res = TimesheetService.review_timesheet(
            manager_user, draft_timesheet.id, 'reject', 'Missing task notes'
        )
        assert reject_res['success'] is True
        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT
        assert draft_timesheet.rejection_comment == 'Missing task notes'

        # Resubmit and Approve
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()
        approve_res = TimesheetService.review_timesheet(
            manager_user, draft_timesheet.id, 'approve'
        )
        assert approve_res['success'] is True
        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.APPROVED
        assert draft_timesheet.approved_by == manager_user
        assert draft_timesheet.approved_at is not None

    def test_review_timesheet_unauthorized_for_unrelated_user(
        self, other_user, draft_timesheet
    ):
        """Verify review is blocked for users who do not manage the timesheet owner's projects."""
        res = TimesheetService.review_timesheet(other_user, draft_timesheet.id, 'approve')
        assert res['success'] is False
        assert "Access denied" in res['message']

    def test_get_timesheet_detail_data(
        self, engineer_user, manager_user, other_user, active_project, active_task, draft_timesheet
    ):
        """Verify access control and detail matrix assembly for timesheet detail."""
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=monday,
            hours=8.0
        )

        # Owner access
        ts, ctx, err = TimesheetService.get_timesheet_detail_data(engineer_user, draft_timesheet.id)
        assert err is None
        assert ts == draft_timesheet
        assert ctx['weekly_total'] == 8.0
        assert ctx['is_manager'] is False

        # Manager access
        ts_m, ctx_m, err_m = TimesheetService.get_timesheet_detail_data(manager_user, draft_timesheet.id)
        assert err_m is None
        assert ctx_m['is_manager'] is True

        # Unauthorized access
        ts_u, ctx_u, err_u = TimesheetService.get_timesheet_detail_data(other_user, draft_timesheet.id)
        assert ts_u is None
        assert "Access denied" in err_u

    def test_get_yearly_data(self, engineer_user, active_project, active_task, draft_timesheet):
        """Verify yearly summary aggregates weeks and project type hours."""
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=monday,
            hours=12.0
        )
        data = TimesheetService.get_yearly_data(engineer_user, draft_timesheet.year)
        assert data['current_year'] == draft_timesheet.year
        max_weeks = datetime.date(draft_timesheet.year, 12, 28).isocalendar()[1]
        assert len(data['weeks_data']) == max_weeks
        assert data['comm_hours'] == 12.0
        assert data['total_analyzed'] == 12.0


@pytest.mark.django_db
class TestCalendarService:
    def test_update_day_create_and_clear(self):
        """Verify CalendarService creates and removes company calendar exceptions."""
        res = CalendarService.update_day('2026-05-01', 'HOLIDAY')
        assert res['success'] is True
        assert CompanyCalendar.objects.filter(date=datetime.date(2026, 5, 1), day_type='HOLIDAY').exists()

        clear_res = CalendarService.update_day('2026-05-01', 'CLEAR')
        assert clear_res['success'] is True
        assert not CompanyCalendar.objects.filter(date=datetime.date(2026, 5, 1)).exists()

    def test_get_year_calendar_data(self):
        """Verify CalendarService generates 12 months with days and week structure."""
        CompanyCalendar.objects.create(date=datetime.date(2026, 1, 1), day_type='HOLIDAY')
        months_data = CalendarService.get_year_calendar_data(2026)
        assert len(months_data) == 12
        january = months_data[0]
        assert january['name'] == 'January'
        all_days = [day for week in january['weeks'] for day in week if day]
        jan1 = next(d for d in all_days if d['date'] == datetime.date(2026, 1, 1))
        assert jan1['day_type'] == 'HOLIDAY'


@pytest.mark.django_db
class TestStructuredLogging:
    """Verify structured logging for service operations."""

    def test_save_draft_and_submit_logging(
        self, engineer_user, active_task, draft_timesheet, caplog
    ):
        """Verify draft save, empty submit, valid submit, and recall are logged."""
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)
        date_str = monday.strftime('%Y-%m-%d')

        with caplog.at_level(logging.INFO, logger='work_time_reporter.services'):
            # Save draft
            post_data = {
                'action': 'save',
                f'hours_{active_task.id}_{date_str}': '8.0',
            }
            TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
            assert f"Timesheet {draft_timesheet.id} (Year: {draft_timesheet.year}, Week: {draft_timesheet.week_number}) draft saved by user {engineer_user.username}" in caplog.text

            caplog.clear()

            # Submit with non-standard hours (8h != 40h)
            post_data_submit = {
                'action': 'submit',
                f'hours_{active_task.id}_{date_str}': '8.0',
            }
            TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data_submit)
            assert f"Timesheet {draft_timesheet.id} (Year: {draft_timesheet.year}, Week: {draft_timesheet.week_number}) submitted by user {engineer_user.username} with total 8.00 hours" in caplog.text
            assert f"Timesheet {draft_timesheet.id} submitted with non-standard hours (8.00h) by user {engineer_user.username}" in caplog.text

            caplog.clear()

            # Recall
            recall_data = {'action': 'recall'}
            TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, recall_data)
            assert f"Timesheet {draft_timesheet.id} recalled to draft by user {engineer_user.username}" in caplog.text

    def test_empty_submit_and_invalid_hours_logging(
        self, engineer_user, active_task, draft_timesheet, caplog
    ):
        """Verify empty timesheet submission and invalid hours are logged as warnings."""
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)
        date_str = monday.strftime('%Y-%m-%d')

        with caplog.at_level(logging.WARNING, logger='work_time_reporter.services'):
            # Empty submission
            TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, {'action': 'submit'})
            assert f"User {engineer_user.username} attempted to submit empty timesheet {draft_timesheet.id}" in caplog.text

            caplog.clear()

            # Invalid hours (> 24)
            invalid_data = {
                'action': 'save',
                f'hours_{active_task.id}_{date_str}': '25.0',
            }
            TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, invalid_data)
            assert f"Invalid hours value '25.0' submitted by user {engineer_user.username}" in caplog.text

    def test_review_timesheet_logging(
        self, manager_user, other_user, active_project, active_task, engineer_user, draft_timesheet, caplog
    ):
        """Verify timesheet approvals, rejections, and unauthorized reviews are logged."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        with caplog.at_level(logging.INFO, logger='work_time_reporter.services'):
            # Unauthorized review attempt
            TimesheetService.review_timesheet(other_user, draft_timesheet.id, 'approve')
            assert "Unauthorized review attempt" in caplog.text

            caplog.clear()

            # Rejection
            TimesheetService.review_timesheet(manager_user, draft_timesheet.id, 'reject', 'Fix Friday hours')
            assert f"Timesheet {draft_timesheet.id} (owner: {draft_timesheet.user.username}) rejected by manager {manager_user.username}. Feedback: Fix Friday hours" in caplog.text

            caplog.clear()

            # Resubmit and Approve
            draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
            draft_timesheet.save()
            TimesheetService.review_timesheet(manager_user, draft_timesheet.id, 'approve')
            assert f"Timesheet {draft_timesheet.id} (owner: {draft_timesheet.user.username}) approved by manager {manager_user.username}" in caplog.text

    def test_calendar_service_logging(self, caplog):
        """Verify calendar day modifications are logged."""
        with caplog.at_level(logging.INFO, logger='work_time_reporter.services'):
            CalendarService.update_day('2026-09-01', 'SHORT_DAY')
            assert "Company calendar updated for date 2026-09-01: day_type=SHORT_DAY" in caplog.text

            caplog.clear()

            CalendarService.update_day('2026-09-01', 'CLEAR')
            assert "Company calendar customization cleared for date 2026-09-01" in caplog.text
