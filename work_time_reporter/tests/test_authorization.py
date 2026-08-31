import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from work_time_reporter.models import (
    WeeklyTimesheet,
    TimeLog
)

User = get_user_model()


@pytest.mark.django_db
class TestAuthenticationRequirements:
    """Verify that all main endpoints require authentication."""

    def test_anonymous_user_redirected_to_login(self, client):
        """Unauthenticated requests must redirect to login page."""
        endpoints = [
            reverse('work_time_reporter:dashboard'),
            reverse('work_time_reporter:yearly_dashboard'),
            reverse('work_time_reporter:progress_dashboard_current'),
            reverse('work_time_reporter:calendar_settings_current'),
            reverse('work_time_reporter:team_approvals'),
        ]

        for url in endpoints:
            response = client.get(url)
            assert response.status_code == 302
            assert reverse('work_time_reporter:login') in response.url


@pytest.mark.django_db
class TestTeamApprovalsAuthorization:
    """Verify role and project access control in team approvals."""

    def test_regular_engineer_cannot_access_team_approvals(
        self, engineer_client
    ):
        """Engineers who do not manage active projects are redirected to dashboard."""
        url = reverse('work_time_reporter:team_approvals')
        response = engineer_client.get(url, follow=True)

        assert response.status_code == 200
        # Redirected back to dashboard
        assert response.redirect_chain[0][0] == reverse('work_time_reporter:dashboard')

    def test_manager_can_access_team_approvals(
        self, manager_client, active_project
    ):
        """Active project managers can view the team approvals page."""
        url = reverse('work_time_reporter:team_approvals')
        response = manager_client.get(url)

        assert response.status_code == 200
        assert 'pending_timesheets' in response.context

    def test_manager_can_approve_subordinate_timesheet(
        self, manager_client, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Manager can approve submitted timesheet for engineers in their active projects."""
        # Setup submitted timesheet with hours
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=timezone.now().date(),
            hours=8.0
        )
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        url = reverse('work_time_reporter:team_approvals')
        post_data = {
            'timesheet_id': draft_timesheet.id,
            'action': 'approve'
        }

        response = manager_client.post(url, post_data, follow=True)
        assert response.status_code == 200

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.APPROVED

    def test_manager_cannot_approve_unrelated_engineer_timesheet(
        self, manager_client, other_user, active_project
    ):
        """Manager cannot approve timesheet of an engineer who is not a member of their projects."""
        # Create timesheet for unrelated user
        other_timesheet = WeeklyTimesheet.objects.create(
            user=other_user,
            year=2026,
            week_number=35,
            status=WeeklyTimesheet.Status.SUBMITTED
        )

        url = reverse('work_time_reporter:team_approvals')
        post_data = {
            'timesheet_id': other_timesheet.id,
            'action': 'approve'
        }

        response = manager_client.post(url, post_data, follow=True)
        assert response.status_code == 200

        other_timesheet.refresh_from_db()
        # Status MUST remain SUBMITTED (approval denied)
        assert other_timesheet.status == WeeklyTimesheet.Status.SUBMITTED

    def test_manager_cannot_self_approve_own_timesheet(
        self, manager_client, manager_user, active_project, active_task
    ):
        """Manager cannot approve their own timesheet through team approvals."""
        today = timezone.now().date()
        year, week, _ = today.isocalendar()

        manager_timesheet = WeeklyTimesheet.objects.create(
            user=manager_user,
            year=year,
            week_number=week,
            status=WeeklyTimesheet.Status.SUBMITTED
        )

        url = reverse('work_time_reporter:team_approvals')
        post_data = {
            'timesheet_id': manager_timesheet.id,
            'action': 'approve'
        }

        response = manager_client.post(url, post_data, follow=True)
        assert response.status_code == 200

        manager_timesheet.refresh_from_db()
        # Self-approval prevented
        assert manager_timesheet.status == WeeklyTimesheet.Status.SUBMITTED


@pytest.mark.django_db
class TestTimesheetDetailAuthorization:
    """Verify access control for timesheet detail view."""

    def test_owner_can_view_own_timesheet_detail(
        self, engineer_client, draft_timesheet
    ):
        """The engineer who owns the timesheet can view its detail."""
        url = reverse('work_time_reporter:timesheet_detail', kwargs={'timesheet_id': draft_timesheet.id})
        response = engineer_client.get(url)

        assert response.status_code == 200
        assert response.context['timesheet'] == draft_timesheet

    def test_manager_can_view_subordinate_timesheet_detail(
        self, manager_client, active_project, draft_timesheet
    ):
        """Manager of the project can view their engineer's timesheet detail."""
        url = reverse('work_time_reporter:timesheet_detail', kwargs={'timesheet_id': draft_timesheet.id})
        response = manager_client.get(url)

        assert response.status_code == 200
        assert response.context['timesheet'] == draft_timesheet

    def test_unrelated_user_cannot_view_timesheet_detail(
        self, client, other_user, draft_timesheet
    ):
        """An unrelated user receives access denied when trying to view someone else's timesheet."""
        client.force_login(other_user)
        url = reverse('work_time_reporter:timesheet_detail', kwargs={'timesheet_id': draft_timesheet.id})

        response = client.get(url, follow=True)
        assert response.status_code == 200
        # Redirected to dashboard due to Access Denied
        assert response.redirect_chain[0][0] == reverse('work_time_reporter:dashboard')
