import datetime
import pytest
from django.utils import timezone

from work_time_reporter.models import (
    Project,
    Task,
    WeeklyTimesheet,
    TimeLog
)
from work_time_reporter.services import TimesheetService


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

    def test_recall_submitted_timesheet_resets_to_draft(
        self, engineer_user, active_task, draft_timesheet
    ):
        """Verify recalling a SUBMITTED timesheet changes status back to DRAFT."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        post_data = {'action': 'recall'}
        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)

        assert result['success'] is True
        assert result['type'] == 'info'
        assert "recalled to draft" in result['message']

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT

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
        TimeLog.objects.create(
            user=engineer_user,
            task=task,
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
