import datetime
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from work_time_reporter.models import (
    Project,
    Task,
    WeeklyTimesheet,
    TimeLog,
    CompanyCalendar,
    current_year
)


@pytest.mark.django_db
class TestProjectModel:
    def test_current_year_callable(self):
        """Verify that current_year returns the actual current year."""
        assert current_year() == timezone.now().year

    def test_project_default_year_is_current(self, manager_user):
        """Verify Project instance defaults to current year."""
        project = Project.objects.create(
            name="New Project",
            manager=manager_user
        )
        assert project.year == timezone.now().year

    def test_delete_historical_project_raises_validation_error(self, manager_user):
        """Verify deletion of historical projects from previous years is prevented."""
        past_project = Project.objects.create(
            name="Old 2020 Project",
            year=2020,
            manager=manager_user
        )
        with pytest.raises(ValidationError, match="Cannot delete historical projects"):
            past_project.delete()

    def test_delete_project_with_approved_logs_raises_validation_error(
        self, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Verify deletion of project with approved time logs is blocked."""
        # Mark timesheet as approved
        draft_timesheet.status = WeeklyTimesheet.Status.APPROVED
        draft_timesheet.save()

        # Create time log linked to approved timesheet
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=timezone.now().date(),
            hours=8.0
        )

        with pytest.raises(ValidationError, match="approved time logs"):
            active_project.delete()

    def test_delete_active_project_without_approved_logs_succeeds(self, manager_user):
        """Verify active project without approved logs can be deleted cleanly."""
        project = Project.objects.create(
            name="Temp Project",
            year=timezone.now().year,
            manager=manager_user
        )
        project_id = project.id
        project.delete()
        assert not Project.objects.filter(id=project_id).exists()


@pytest.mark.django_db
class TestTaskModel:
    def test_task_default_deadline_set_to_end_of_year(self, active_project):
        """Verify task deadline defaults to Dec 31 of current year if not specified."""
        task = Task.objects.create(
            title="Auto Deadline Task",
            project=active_project,
            budget_hours=20
        )
        assert task.deadline == datetime.date(timezone.now().year, 12, 31)

    def test_delete_task_belonging_to_historical_project_raises_error(self, manager_user):
        """Verify task in historical project cannot be deleted."""
        past_project = Project.objects.create(
            name="Old Project",
            year=2021,
            manager=manager_user
        )
        task = Task.objects.create(
            title="Old Task",
            project=past_project,
            budget_hours=10
        )
        with pytest.raises(ValidationError, match="historical projects"):
            task.delete()

    def test_delete_task_with_approved_logs_raises_error(
        self, active_task, engineer_user, draft_timesheet
    ):
        """Verify task with approved time logs cannot be deleted."""
        draft_timesheet.status = WeeklyTimesheet.Status.APPROVED
        draft_timesheet.save()

        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=timezone.now().date(),
            hours=4.0
        )

        with pytest.raises(ValidationError, match="approved time logs"):
            active_task.delete()


@pytest.mark.django_db
class TestWeeklyTimesheetModel:
    def test_unique_timesheet_per_user_year_week(self, engineer_user):
        """Verify user cannot create duplicate timesheets for the same week."""
        WeeklyTimesheet.objects.create(
            user=engineer_user,
            year=2026,
            week_number=10,
            status=WeeklyTimesheet.Status.DRAFT
        )
        with pytest.raises(IntegrityError):
            WeeklyTimesheet.objects.create(
                user=engineer_user,
                year=2026,
                week_number=10,
                status=WeeklyTimesheet.Status.DRAFT
            )

    def test_delete_approved_timesheet_raises_error(self, draft_timesheet):
        """Verify approved timesheet cannot be deleted."""
        draft_timesheet.status = WeeklyTimesheet.Status.APPROVED
        draft_timesheet.save()

        with pytest.raises(ValidationError, match="Cannot delete an approved timesheet"):
            draft_timesheet.delete()


@pytest.mark.django_db
class TestTimeLogModel:
    def test_unique_constraint_user_task_date(self, active_task, engineer_user):
        """Verify the 'Iron Rule': cannot log time twice for the same user, task, and date."""
        today = timezone.now().date()
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            date=today,
            hours=5.0
        )
        with pytest.raises(IntegrityError):
            TimeLog.objects.create(
                user=engineer_user,
                task=active_task,
                date=today,
                hours=3.0
            )

    def test_delete_time_log_on_approved_timesheet_raises_error(
        self, active_task, engineer_user, draft_timesheet
    ):
        """Verify time log linked to an approved timesheet cannot be deleted."""
        draft_timesheet.status = WeeklyTimesheet.Status.APPROVED
        draft_timesheet.save()

        log = TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=timezone.now().date(),
            hours=6.0
        )

        with pytest.raises(ValidationError, match="approved timesheet"):
            log.delete()


@pytest.mark.django_db
class TestCompanyCalendarModel:
    def test_create_and_str_company_calendar(self):
        """Verify CompanyCalendar creation and human-readable string representation."""
        cal = CompanyCalendar.objects.create(
            date=datetime.date(2026, 12, 25),
            day_type="HOLIDAY",
            description="Christmas Day"
        )
        assert "Holiday / Non-working day" in str(cal)
        assert "2026-12-25" in str(cal)
