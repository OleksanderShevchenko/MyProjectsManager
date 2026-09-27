import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

from work_time_reporter.models import Project, TimeLog, WeeklyTimesheet
from work_time_reporter.notifications import NotificationService
from work_time_reporter.services import TimesheetService

User = get_user_model()


@pytest.fixture
def timesheet_with_hours(db, engineer_user, active_task, draft_timesheet):
    """Create a timesheet with 40 logged hours."""
    monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)

    for i in range(5):
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=monday + datetime.timedelta(days=i),
            hours=8.0,
            comment="Working on architecture",
        )
    return draft_timesheet


@pytest.mark.django_db
class TestNotificationServiceManagers:
    def test_get_managers_for_employee_success(self, engineer_user, manager_user, active_project):
        """Should retrieve the manager of the active project where engineer is member."""
        managers = NotificationService.get_managers_for_employee(engineer_user)
        assert len(managers) == 1
        assert managers[0] == manager_user

    def test_get_managers_excludes_inactive_projects(self, engineer_user, manager_user, active_project):
        """Should not include managers from inactive projects."""
        active_project.is_active = False
        active_project.save()

        managers = NotificationService.get_managers_for_employee(engineer_user)
        assert len(managers) == 0

    def test_get_managers_excludes_manager_without_email(self, engineer_user, manager_user, active_project):
        """Should exclude managers who do not have an email address configured."""
        manager_user.email = ""
        manager_user.save()

        managers = NotificationService.get_managers_for_employee(engineer_user)
        assert len(managers) == 0

    def test_get_managers_excludes_self(self, manager_user):
        """If a manager is also a member of their own project, they should not notify themselves."""
        project = Project.objects.create(
            name="Self Project",
            year=timezone.now().year,
            is_active=True,
            manager=manager_user,
        )
        project.members.add(manager_user)

        managers = NotificationService.get_managers_for_employee(manager_user)
        assert len(managers) == 0

    def test_get_managers_deduplicates_same_manager_across_projects(self, engineer_user, manager_user, active_project):
        """If an engineer belongs to two projects managed by the same manager, manager should appear once."""
        project2 = Project.objects.create(
            name="Project Beta",
            year=timezone.now().year,
            is_active=True,
            manager=manager_user,
        )
        project2.members.add(engineer_user)

        managers = NotificationService.get_managers_for_employee(engineer_user)
        assert len(managers) == 1
        assert managers[0] == manager_user


@pytest.mark.django_db
class TestNotificationServiceDispatch:
    def test_notify_timesheet_submitted(self, engineer_user, manager_user, active_project, timesheet_with_hours):
        """Should dispatch an email to the project manager when timesheet is submitted."""
        mail.outbox.clear()
        sent_count = NotificationService.notify_timesheet_submitted(timesheet_with_hours)

        assert sent_count == 1
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]

        assert manager_user.email in sent_email.to
        assert f"Week {timesheet_with_hours.week_number}" in sent_email.subject
        assert engineer_user.first_name in sent_email.body or engineer_user.username in sent_email.body
        assert "/approvals/" in sent_email.body
        # Verify HTML alternative
        assert len(sent_email.alternatives) == 1
        html_body, mime = sent_email.alternatives[0]
        assert mime == "text/html"
        assert "Review Timesheet" in html_body

    def test_notify_timesheet_submitted_no_managers(self, engineer_user, draft_timesheet):
        """If employee has no active project managers, returns 0 and does not crash."""
        mail.outbox.clear()
        sent_count = NotificationService.notify_timesheet_submitted(draft_timesheet)

        assert sent_count == 0
        assert len(mail.outbox) == 0

    def test_notify_timesheet_submitted_resilient_to_smtp_error(self, engineer_user, manager_user, active_project, timesheet_with_hours):
        """Should catch SMTP exception, log error, and not crash."""
        mail.outbox.clear()
        with patch("django.core.mail.EmailMultiAlternatives.send", side_effect=Exception("SMTP Connection timed out")):
            sent_count = NotificationService.notify_timesheet_submitted(timesheet_with_hours)

        assert sent_count == 0
        assert len(mail.outbox) == 0

    def test_notify_timesheet_approved(self, engineer_user, manager_user, timesheet_with_hours):
        """Should dispatch an approval notification to the engineer."""
        mail.outbox.clear()
        timesheet_with_hours.status = WeeklyTimesheet.Status.APPROVED
        timesheet_with_hours.approved_by = manager_user
        timesheet_with_hours.save()

        success = NotificationService.notify_timesheet_approved(timesheet_with_hours, reviewer=manager_user)

        assert success is True
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]

        assert engineer_user.email in sent_email.to
        assert "approved" in sent_email.subject.lower()
        assert "approved" in sent_email.body.lower()
        assert len(sent_email.alternatives) == 1
        assert "Approved" in sent_email.alternatives[0][0]

    def test_notify_timesheet_approved_no_email(self, engineer_user, manager_user, timesheet_with_hours):
        """Should skip approval notification when engineer has no email."""
        engineer_user.email = ""
        engineer_user.save()
        mail.outbox.clear()

        success = NotificationService.notify_timesheet_approved(timesheet_with_hours, reviewer=manager_user)
        assert success is False
        assert len(mail.outbox) == 0

    def test_notify_timesheet_rejected(self, engineer_user, manager_user, timesheet_with_hours):
        """Should dispatch a rejection/revision email with feedback to the engineer."""
        mail.outbox.clear()
        timesheet_with_hours.rejection_comment = "Please log Friday hours separately."
        timesheet_with_hours.save()

        success = NotificationService.notify_timesheet_rejected(
            timesheet_with_hours,
            reviewer=manager_user,
            rejection_comment="Please log Friday hours separately.",
        )

        assert success is True
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]

        assert engineer_user.email in sent_email.to
        assert "returned" in sent_email.subject.lower() or "revision" in sent_email.subject.lower()
        assert "Please log Friday hours separately." in sent_email.body
        assert len(sent_email.alternatives) == 1
        assert "Please log Friday hours separately." in sent_email.alternatives[0][0]

    def test_notify_timesheet_rejected_no_email(self, engineer_user, manager_user, timesheet_with_hours):
        """Should skip rejection notification when engineer has no email."""
        engineer_user.email = ""
        engineer_user.save()
        mail.outbox.clear()

        success = NotificationService.notify_timesheet_rejected(
            timesheet_with_hours,
            reviewer=manager_user,
            rejection_comment="Fix hours.",
        )
        assert success is False
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestTimesheetServiceNotificationIntegration:
    def test_submission_triggers_email(self, engineer_user, manager_user, active_project, active_task, draft_timesheet):
        """Submitting a timesheet through TimesheetService should trigger manager notification."""
        mail.outbox.clear()
        monday = datetime.date.fromisocalendar(draft_timesheet.year, draft_timesheet.week_number, 1)

        post_data = {
            "action": "submit",
        }
        for i in range(5):
            day_str = (monday + datetime.timedelta(days=i)).isoformat()
            post_data[f"hours_{active_task.id}_{day_str}"] = "8"
            post_data[f"comment_{active_task.id}_{day_str}"] = f"Work day {i+1}"

        result = TimesheetService.save_timesheet_data(engineer_user, draft_timesheet, post_data)
        assert result["success"] is True

        # In standard pytest django test runner, on_commit callbacks execute immediately or at end of atomic
        assert len(mail.outbox) == 1
        assert manager_user.email in mail.outbox[0].to

    def test_approval_triggers_email(self, engineer_user, manager_user, active_project, timesheet_with_hours):
        """Approving a timesheet should trigger engineer email."""
        timesheet_with_hours.status = WeeklyTimesheet.Status.SUBMITTED
        timesheet_with_hours.save()

        mail.outbox.clear()
        result = TimesheetService.review_timesheet(manager_user, timesheet_with_hours.id, action="approve")

        assert result["success"] is True
        assert len(mail.outbox) == 1
        assert engineer_user.email in mail.outbox[0].to

    def test_rejection_triggers_email(self, engineer_user, manager_user, active_project, timesheet_with_hours):
        """Rejecting a timesheet should trigger engineer email with feedback."""
        timesheet_with_hours.status = WeeklyTimesheet.Status.SUBMITTED
        timesheet_with_hours.save()

        mail.outbox.clear()
        result = TimesheetService.review_timesheet(
            manager_user,
            timesheet_with_hours.id,
            action="reject",
            rejection_comment="Missing description on task",
        )

        assert result["success"] is True
        assert len(mail.outbox) == 1
        assert engineer_user.email in mail.outbox[0].to
        assert "Missing description on task" in mail.outbox[0].body
