import datetime
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from work_time_reporter.models import (
    TimeLog,
    WeeklyTimesheet
)

User = get_user_model()


@pytest.mark.django_db
class TestDashboardViews:
    def test_dashboard_default_url_redirects_to_current_iso_week(
        self, engineer_client
    ):
        """Accessing root dashboard URL redirects to the current ISO year and week."""
        today = timezone.now().date()
        current_year, current_week, _ = today.isocalendar()

        url = reverse('work_time_reporter:dashboard')
        response = engineer_client.get(url)

        expected_url = reverse('work_time_reporter:dashboard_week', kwargs={
            'year': current_year,
            'week': current_week
        })
        assert response.status_code == 302
        assert response.url == expected_url

    def test_dashboard_invalid_week_redirects_to_current_week(
        self, engineer_client
    ):
        """Accessing an invalid week number (e.g. week 99) safely redirects to current week."""
        today = timezone.now().date()
        current_year, current_week, _ = today.isocalendar()

        url = reverse('work_time_reporter:dashboard_week', kwargs={'year': current_year, 'week': 99})
        response = engineer_client.get(url)

        expected_url = reverse('work_time_reporter:dashboard_week', kwargs={
            'year': current_year,
            'week': current_week
        })
        assert response.status_code == 302
        assert response.url == expected_url

    def test_dashboard_get_renders_grid_and_mini_dashboard(
        self, engineer_client, active_project, active_task
    ):
        """Dashboard GET renders the timesheet grid and mini dashboard correctly."""
        today = timezone.now().date()
        current_year, current_week, _ = today.isocalendar()

        url = reverse('work_time_reporter:dashboard_week', kwargs={
            'year': current_year,
            'week': current_week
        })
        response = engineer_client.get(url)

        assert response.status_code == 200
        assert 'grid_data' in response.context
        assert 'mini_dashboard' in response.context
        assert len(response.context['week_dates']) == 7

        # Verify mini dashboard contains active project
        mini_dash = response.context['mini_dashboard']
        assert len(mini_dash) == 1
        assert mini_dash[0]['name'] == active_project.name

    def test_dashboard_post_saves_hours_and_redirects(
        self, engineer_client, active_project, active_task, draft_timesheet
    ):
        """Dashboard POST processes timesheet save and redirects with success message."""
        today = timezone.now().date()
        current_year, current_week, _ = today.isocalendar()

        url = reverse('work_time_reporter:dashboard_week', kwargs={
            'year': current_year,
            'week': current_week
        })
        post_data = {
            'action': 'save',
            f'hours_{active_task.id}_2026-08-24': '8.0',
            f'comment_{active_task.id}_2026-08-24': 'View integration test'
        }

        response = engineer_client.post(url, post_data)
        assert response.status_code == 302
        assert response.url == url

        # Verify time log saved
        assert TimeLog.objects.filter(
            task=active_task,
            date=datetime.date(2026, 8, 24),
            hours=8.0
        ).exists()

    def test_dashboard_renders_rejection_comment_banner_when_rejected(
        self, engineer_client, draft_timesheet
    ):
        """Dashboard renders warning banner with manager's feedback when timesheet was rejected."""
        draft_timesheet.rejection_comment = "Please verify hours logged for project deployment."
        draft_timesheet.status = WeeklyTimesheet.Status.DRAFT
        draft_timesheet.save()

        url = reverse('work_time_reporter:dashboard_week', kwargs={
            'year': draft_timesheet.year,
            'week': draft_timesheet.week_number
        })
        response = engineer_client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        assert "Timesheet Returned with Feedback" in content
        assert "Please verify hours logged for project deployment." in content

    def test_dashboard_does_not_render_rejection_banner_when_clean(
        self, engineer_client, draft_timesheet
    ):
        """Dashboard does not render rejection banner when there is no rejection comment."""
        draft_timesheet.rejection_comment = ""
        draft_timesheet.save()

        url = reverse('work_time_reporter:dashboard_week', kwargs={
            'year': draft_timesheet.year,
            'week': draft_timesheet.week_number
        })
        response = engineer_client.get(url)
        assert response.status_code == 200

        content = response.content.decode('utf-8')
        assert "Timesheet Returned with Feedback" not in content


@pytest.mark.django_db
class TestYearlyAndProgressViews:
    def test_yearly_dashboard_loads_correctly(
        self, engineer_client
    ):
        """Yearly overview page renders successfully."""
        url = reverse('work_time_reporter:yearly_dashboard')
        response = engineer_client.get(url)
        assert response.status_code == 200
        assert 'weeks_data' in response.context

    def test_yearly_dashboard_week_53_for_leap_iso_year(
        self, engineer_client
    ):
        """Verify that years with 53 ISO weeks (such as 2026) render 53 weeks in the grid."""
        url = reverse('work_time_reporter:yearly_dashboard_year', kwargs={'year': 2026})
        response = engineer_client.get(url)
        assert response.status_code == 200
        weeks_data = response.context['weeks_data']
        assert len(weeks_data) == 53
        assert weeks_data[-1]['week_num'] == 53

    def test_yearly_dashboard_week_52_for_standard_iso_year(
        self, engineer_client
    ):
        """Verify that standard 52-week ISO years (such as 2025) render 52 weeks."""
        url = reverse('work_time_reporter:yearly_dashboard_year', kwargs={'year': 2025})
        response = engineer_client.get(url)
        assert response.status_code == 200
        weeks_data = response.context['weeks_data']
        assert len(weeks_data) == 52
        assert weeks_data[-1]['week_num'] == 52

    def test_progress_dashboard_current_loads_correctly(
        self, engineer_client, active_project, active_task
    ):
        """Progress tracker dashboard page renders successfully."""
        url = reverse('work_time_reporter:progress_dashboard_current')
        response = engineer_client.get(url)
        assert response.status_code == 200
        assert 'integral_data' in response.context
        assert 'grid_data' in response.context


@pytest.mark.django_db
class TestCalendarSettingsView:
    def test_calendar_settings_page_loads(
        self, engineer_client
    ):
        """Calendar settings page renders calendar grid for the year."""
        url = reverse('work_time_reporter:calendar_settings_current')
        response = engineer_client.get(url)
        assert response.status_code == 200
        assert 'months_data' in response.context
        assert len(response.context['months_data']) == 12


@pytest.mark.django_db
class TestHtmxIntegration:
    """Verify HTMX static asset loading, middleware detection, and CSRF configuration."""

    def test_base_template_includes_htmx_and_csrf_headers(self, engineer_client):
        """Pages inheriting base.html must load local vendor htmx.min.js and global CSRF headers."""
        url = reverse('work_time_reporter:calendar_settings_current')
        response = engineer_client.get(url)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'vendor/htmx.min.js' in content
        assert 'hx-headers=' in content
        assert 'X-CSRFToken' in content

    def test_htmx_middleware_populates_request_htmx(self, rf, engineer_user):
        """Requests with HX-Request header must have request.htmx == True via HtmxMiddleware."""
        from django_htmx.middleware import HtmxMiddleware
        from django.http import HttpResponse

        def dummy_view(request):
            return HttpResponse("HTMX" if request.htmx else "STANDARD")

        request = rf.get('/dummy/', HTTP_HX_REQUEST='true')
        request.user = engineer_user
        middleware = HtmxMiddleware(dummy_view)
        response = middleware(request)
        assert response.content == b"HTMX"

        # Non-HTMX request
        regular_request = rf.get('/dummy/')
        regular_request.user = engineer_user
        regular_response = middleware(regular_request)
        assert regular_response.content == b"STANDARD"

    def test_calendar_settings_htmx_post_updates_and_returns_partial(
        self, client, engineer_user
    ):
        """Admin HTMX POST to calendar settings updates day and returns calendar_day_cell partial."""
        engineer_user.is_superuser = True
        engineer_user.save()
        client.force_login(engineer_user)

        url = reverse('work_time_reporter:calendar_settings', kwargs={'year': 2026})
        response = client.post(
            url,
            data={'date': '2026-10-14', 'type': 'HOLIDAY'},
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'id="day-cell-2026-10-14"' in content
        assert 'bg-red-100' in content
        assert 'HOLIDAY' in content

    def test_calendar_settings_htmx_post_denies_non_admin(
        self, client, engineer_user
    ):
        """Non-admin HTMX POST to calendar settings receives 403 Forbidden."""
        client.force_login(engineer_user)
        url = reverse('work_time_reporter:calendar_settings', kwargs={'year': 2026})
        response = client.post(
            url,
            data={'date': '2026-10-14', 'type': 'HOLIDAY'},
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 403

    def test_calendar_settings_htmx_post_monday_free_monday(
        self, client, engineer_user
    ):
        """Admin HTMX POST allows FREE_MONDAY on Monday and calculates next_type as CLEAR."""
        engineer_user.is_superuser = True
        engineer_user.save()
        client.force_login(engineer_user)

        url = reverse('work_time_reporter:calendar_settings', kwargs={'year': 2026})
        response = client.post(
            url,
            data={'date': '2026-05-04', 'type': 'FREE_MONDAY'},  # Monday
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'FREE_MONDAY' in content
        assert '"type": "CLEAR"' in content

    def test_calendar_settings_htmx_post_rejects_invalid_day_types(
        self, client, engineer_user
    ):
        """Admin HTMX POST rejects SHORT_DAY on weekends and FREE_MONDAY on non-Mondays."""
        engineer_user.is_superuser = True
        engineer_user.save()
        client.force_login(engineer_user)

        url = reverse('work_time_reporter:calendar_settings', kwargs={'year': 2026})
        # Try SHORT_DAY on Sunday
        resp_weekend = client.post(
            url,
            data={'date': '2026-05-03', 'type': 'SHORT_DAY'},  # Sunday
            HTTP_HX_REQUEST='true'
        )
        assert resp_weekend.status_code == 400
        assert 'Only holidays can be set on weekends' in resp_weekend.content.decode('utf-8')

        # Try FREE_MONDAY on Tuesday
        resp_tue = client.post(
            url,
            data={'date': '2026-05-05', 'type': 'FREE_MONDAY'},  # Tuesday
            HTTP_HX_REQUEST='true'
        )
        assert resp_tue.status_code == 400
        assert 'Free Monday can only be set on Mondays' in resp_tue.content.decode('utf-8')

    def test_team_approvals_htmx_approve_returns_status_row(
        self, client, manager_user, active_project, active_task, draft_timesheet
    ):
        """Manager HTMX approve action returns timesheet_approval_status_row partial."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        client.force_login(manager_user)
        url = reverse('work_time_reporter:team_approvals')
        response = client.post(
            url,
            data={'timesheet_id': draft_timesheet.id, 'action': 'approve'},
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert f'id="timesheet-row-{draft_timesheet.id}"' in content
        assert 'approved!' in content

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.APPROVED

    def test_team_approvals_htmx_reject_returns_status_row(
        self, client, manager_user, active_project, active_task, draft_timesheet
    ):
        """Manager HTMX reject action returns timesheet_approval_status_row partial."""
        draft_timesheet.status = WeeklyTimesheet.Status.SUBMITTED
        draft_timesheet.save()

        client.force_login(manager_user)
        url = reverse('work_time_reporter:team_approvals')
        response = client.post(
            url,
            data={
                'timesheet_id': draft_timesheet.id,
                'action': 'reject',
                'rejection_comment': 'Please revise Thursday hours'
            },
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert f'id="timesheet-row-{draft_timesheet.id}"' in content
        assert 'returned to draft' in content

        draft_timesheet.refresh_from_db()
        assert draft_timesheet.status == WeeklyTimesheet.Status.DRAFT
        assert draft_timesheet.rejection_comment == 'Please revise Thursday hours'
