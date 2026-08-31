import datetime
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from work_time_reporter.models import (
    TimeLog
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
