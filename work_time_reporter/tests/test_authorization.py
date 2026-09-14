import json
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from work_time_reporter.decorators import admin_required, manager_required
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
        self, manager_client, manager_user, active_project, active_task, engineer_user, draft_timesheet
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
        assert draft_timesheet.approved_by == manager_user
        assert draft_timesheet.approved_at is not None

    def test_manager_can_reject_subordinate_timesheet_with_comment(
        self, manager_client, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Manager can reject a submitted timesheet and provide a rejection comment."""
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
            'action': 'reject',
            'rejection_comment': 'Please fix hours on Thursday'
        }

        response = manager_client.post(url, post_data, follow=True)
        assert response.status_code == 200

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT
        assert draft_timesheet.rejection_comment == 'Please fix hours on Thursday'

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

    def test_manager_can_approve_timesheet_in_detail_view(
        self, manager_client, manager_user, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Manager can approve timesheet from the detail view."""
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=timezone.now().date(),
            hours=8.0
        )
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        url = reverse('work_time_reporter:timesheet_detail', kwargs={'timesheet_id': draft_timesheet.id})
        response = manager_client.post(url, {'action': 'approve'}, follow=True)
        assert response.status_code == 200

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.APPROVED
        assert draft_timesheet.approved_by == manager_user
        assert draft_timesheet.approved_at is not None

    def test_manager_can_reject_timesheet_in_detail_view_with_comment(
        self, manager_client, active_project, active_task, engineer_user, draft_timesheet
    ):
        """Manager can reject timesheet from the detail view with feedback comment."""
        TimeLog.objects.create(
            user=engineer_user,
            task=active_task,
            timesheet=draft_timesheet,
            date=timezone.now().date(),
            hours=8.0
        )
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        url = reverse('work_time_reporter:timesheet_detail', kwargs={'timesheet_id': draft_timesheet.id})
        response = manager_client.post(
            url,
            {'action': 'reject', 'rejection_comment': 'Exceeded daily limit on Friday'},
            follow=True
        )
        assert response.status_code == 200

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT
        assert draft_timesheet.rejection_comment == 'Exceeded daily limit on Friday'


@pytest.mark.django_db
class TestRoleBasedAuthorization:
    """Verify role definitions, decorators, and group management."""

    def test_create_default_groups_command(self):
        """Management command create_default_groups creates Engineer, Project Manager, Admin groups."""
        call_command('create_default_groups')

        engineer_group = Group.objects.get(name='Engineer')
        manager_group = Group.objects.get(name='Project Manager')
        admin_group = Group.objects.get(name='Admin')

        assert engineer_group.permissions.filter(codename='add_timelog').exists()
        assert manager_group.permissions.filter(codename='add_project').exists()
        assert admin_group.permissions.count() >= 24

    def test_custom_user_role_properties(self, engineer_user, manager_user):
        """Verify CustomUser role helper properties."""
        call_command('create_default_groups')
        eng_group = Group.objects.get(name='Engineer')
        admin_group = Group.objects.get(name='Admin')

        assert engineer_user.is_active_manager is False
        assert engineer_user.is_admin_role is False
        assert engineer_user.is_engineer_role is True

        engineer_user.groups.add(admin_group)
        assert engineer_user.is_admin_role is True

        engineer_user.groups.remove(admin_group)
        engineer_user.groups.add(eng_group)
        assert engineer_user.is_engineer_role is True

    def test_user_in_manager_group_can_access_team_approvals(self, client, engineer_user):
        """User in 'Project Manager' group can access team approvals even without assigned projects."""
        call_command('create_default_groups')
        mgr_group = Group.objects.get(name='Project Manager')
        engineer_user.groups.add(mgr_group)

        client.force_login(engineer_user)
        url = reverse('work_time_reporter:team_approvals')
        response = client.get(url)
        assert response.status_code == 200

    @staticmethod
    def _attach_session_and_messages(request):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.messages.middleware import MessageMiddleware
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)

    def test_manager_required_decorator(self, rf, engineer_user, manager_user, active_project):
        """Verify manager_required decorator blocks non-managers and allows active managers."""
        @manager_required
        def dummy_manager_view(request):
            from django.http import HttpResponse
            return HttpResponse("MANAGER_OK")

        # Non-manager request
        request = rf.get('/dummy-mgr/')
        request.user = engineer_user
        self._attach_session_and_messages(request)
        response = dummy_manager_view(request)
        assert response.status_code == 302
        assert reverse('work_time_reporter:dashboard') in response.url

        # Active manager request
        request_mgr = rf.get('/dummy-mgr/')
        request_mgr.user = manager_user
        self._attach_session_and_messages(request_mgr)
        response_mgr = dummy_manager_view(request_mgr)
        assert response_mgr.status_code == 200
        assert response_mgr.content == b"MANAGER_OK"

    def test_admin_required_decorator(self, rf, engineer_user):
        """Verify admin_required decorator redirects regular user and returns 403 on AJAX."""
        @admin_required
        def dummy_admin_view(request):
            from django.http import HttpResponse
            return HttpResponse("OK")

        # Regular GET from engineer
        request = rf.get('/dummy/')
        request.user = engineer_user
        self._attach_session_and_messages(request)
        response = dummy_admin_view(request)
        assert response.status_code == 302
        assert reverse('work_time_reporter:dashboard') in response.url

        # AJAX request from engineer
        ajax_request = rf.post('/dummy/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        ajax_request.user = engineer_user
        ajax_response = dummy_admin_view(ajax_request)
        assert ajax_response.status_code == 403

        # Superuser access
        engineer_user.is_superuser = True
        engineer_user.save()
        allowed_response = dummy_admin_view(request)
        assert allowed_response.status_code == 200
        assert allowed_response.content == b"OK"

    def test_calendar_settings_post_allowed_for_admin_group(self, client, engineer_user):
        """User in 'Admin' group can update calendar settings via AJAX."""
        call_command('create_default_groups')
        admin_group = Group.objects.get(name='Admin')
        engineer_user.groups.add(admin_group)

        client.force_login(engineer_user)
        url = reverse('work_time_reporter:calendar_settings_current')
        post_data = json.dumps({'date': '2026-11-20', 'type': 'HOLIDAY'})
        response = client.post(
            url,
            data=post_data,
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        assert response.status_code == 200
        assert response.json()['status'] == 'success'
