import datetime
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from msproject_import.models import ImportBatch, StagingLog, StagingProject
from msproject_import.services import MicrosoftOAuthService, fetch_pwa_data
from work_time_reporter.models import Project, Task, TimeLog, WeeklyTimesheet

User = get_user_model()


@pytest.fixture
def test_user(db):
    return User.objects.create_user(
        username='engineer_test',
        email='engineer@test.local',
        password='password123'
    )


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user(
        username='manager_test',
        email='manager@test.local',
        password='password123'
    )
    user.is_staff = True
    user.save()
    return user


@pytest.mark.django_db
class TestMicrosoftOAuthService:
    def test_is_configured_returns_false_when_empty(self, settings):
        settings.AZURE_CLIENT_ID = ''
        settings.AZURE_CLIENT_SECRET = ''
        assert MicrosoftOAuthService.is_configured() is False

    def test_is_configured_returns_true_when_set(self, settings):
        settings.AZURE_CLIENT_ID = 'test-client-id'
        settings.AZURE_CLIENT_SECRET = 'test-client-secret'
        assert MicrosoftOAuthService.is_configured() is True

    def test_get_authorization_url_mock_mode(self, settings):
        settings.AZURE_CLIENT_ID = ''
        redirect_uri = 'http://localhost:8080/import/oauth/callback/'
        auth_url = MicrosoftOAuthService.get_authorization_url(redirect_uri, state='test_state_123')
        assert 'code=mock_dev_code' in auth_url
        assert 'state=test_state_123' in auth_url

    def test_get_authorization_url_configured(self, settings):
        settings.AZURE_CLIENT_ID = 'my-client-id'
        settings.AZURE_CLIENT_SECRET = 'my-secret'
        settings.AZURE_TENANT_ID = 'my-tenant-uuid'
        settings.PWA_URL = 'https://contoso.sharepoint.com/sites/pwa'

        redirect_uri = 'http://localhost:8080/import/oauth/callback/'
        auth_url = MicrosoftOAuthService.get_authorization_url(redirect_uri, state='my_state')

        assert 'login.microsoftonline.com/my-tenant-uuid/oauth2/v2.0/authorize' in auth_url
        assert 'client_id=my-client-id' in auth_url
        assert 'state=my_state' in auth_url
        assert 'https%3A%2F%2Fcontoso.sharepoint.com%2FAllSites.Read' in auth_url

    def test_exchange_code_for_token_mock_mode(self, settings):
        settings.AZURE_CLIENT_ID = ''
        token_data = MicrosoftOAuthService.exchange_code_for_token('any_code', 'http://dummy')
        assert token_data['access_token'] == 'mock_access_token_dev'
        assert token_data['token_type'] == 'Bearer'

    @patch('requests.post')
    def test_exchange_code_for_token_success(self, mock_post, settings):
        settings.AZURE_CLIENT_ID = 'test-client-id'
        settings.AZURE_CLIENT_SECRET = 'test-secret'
        settings.AZURE_TENANT_ID = 'test-tenant'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'real_access_token_123',
            'refresh_token': 'real_refresh_token_456',
            'expires_in': 3600,
        }
        mock_post.return_value = mock_response

        token_data = MicrosoftOAuthService.exchange_code_for_token('auth_code_xyz', 'http://localhost:8080/callback')
        assert token_data['access_token'] == 'real_access_token_123'
        assert token_data['refresh_token'] == 'real_refresh_token_456'

    @patch('requests.post')
    def test_exchange_code_for_token_failure(self, mock_post, settings):
        settings.AZURE_CLIENT_ID = 'test-client-id'
        settings.AZURE_CLIENT_SECRET = 'test-secret'

        mock_post.side_effect = Exception("Connection error")
        with pytest.raises(ValueError, match="Microsoft authentication failed"):
            MicrosoftOAuthService.exchange_code_for_token('invalid_code', 'http://localhost:8080/callback')

    def test_refresh_access_token_mock(self, settings):
        settings.AZURE_CLIENT_ID = ''
        result = MicrosoftOAuthService.refresh_access_token('mock_refresh_token_dev')
        assert result['access_token'] == 'mock_access_token_dev'


@pytest.mark.django_db
class TestPwaDataFetching:
    def test_fetch_pwa_data_requires_token(self):
        with pytest.raises(ValueError, match="Valid OAuth access token is required"):
            fetch_pwa_data(access_token='', target_year=2026)

    def test_fetch_pwa_data_mock_mode(self):
        daily_map, projects = fetch_pwa_data(access_token='mock_access_token_dev', target_year=2026)
        assert len(projects) >= 2
        assert len(daily_map) >= 2
        assert "Cloud Infrastructure Migration" in projects

    @patch('requests.get')
    def test_fetch_pwa_data_real_api_parsing(self, mock_get, settings):
        settings.PWA_URL = 'https://contoso.sharepoint.com/sites/pwa'

        # Mock TimeSheetPeriods response
        periods_response = MagicMock()
        periods_response.status_code = 200
        periods_response.json.return_value = {
            'd': {
                'results': [{'Id': 'period-uuid-1'}]
            }
        }

        # Mock TimeSheet/Lines response
        lines_response = MagicMock()
        lines_response.status_code = 200
        lines_response.json.return_value = {
            'd': {
                'results': [
                    {
                        'ProjectName': 'Project Alpha',
                        'TaskName': 'Task Beta',
                        'Work': {
                            'results': [
                                {'ActualWork': '8h', 'Start': '2026-05-12T00:00:00'}
                            ]
                        }
                    }
                ]
            }
        }

        mock_get.side_effect = [periods_response, lines_response]

        daily_map, projects = fetch_pwa_data(access_token='real_token_xyz', target_year=2026)
        assert projects == ['Project Alpha']
        assert '2026-05-12' in daily_map
        assert daily_map['2026-05-12'][0]['hours'] == 8.0
        assert daily_map['2026-05-12'][0]['task'] == 'Task Beta'


@pytest.mark.django_db
class TestOAuthViews:
    def test_oauth_login_redirects_and_sets_session(self, client, test_user):
        client.force_login(test_user)
        url = reverse('msproject_import:oauth_login') + '?year=2025'
        response = client.get(url)

        assert response.status_code == 302
        session = client.session
        assert session.get('oauth_import_year') == 2025
        assert 'oauth_state' in session

    def test_oauth_callback_state_mismatch_rejected(self, client, test_user):
        client.force_login(test_user)
        session = client.session
        session['oauth_state'] = 'correct_state'
        session.save()

        url = reverse('msproject_import:oauth_callback') + '?code=some_code&state=wrong_state'
        response = client.get(url, follow=True)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "Invalid OAuth state" in content

    def test_oauth_callback_success_stores_token(self, client, test_user):
        client.force_login(test_user)
        session = client.session
        session['oauth_state'] = 'valid_state_123'
        session.save()

        url = reverse('msproject_import:oauth_callback') + '?code=mock_dev_code&state=valid_state_123'
        response = client.get(url, follow=True)

        assert response.status_code == 200
        assert client.session.get('pwa_access_token') == 'mock_access_token_dev'
        content = response.content.decode('utf-8')
        assert "Successfully connected" in content

    def test_oauth_disconnect_clears_token(self, client, test_user):
        client.force_login(test_user)
        session = client.session
        session['pwa_access_token'] = 'some_token'
        session['pwa_user_email'] = 'test@contoso.com'
        session.save()

        url = reverse('msproject_import:oauth_disconnect')
        response = client.get(url, follow=True)

        assert response.status_code == 200
        assert 'pwa_access_token' not in client.session
        content = response.content.decode('utf-8')
        assert "Disconnected Microsoft 365" in content

    def test_import_start_get_unconnected(self, client, test_user):
        client.force_login(test_user)
        url = reverse('msproject_import:start')
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "Sign in with Microsoft 365" in content
        assert "OAuth 2.0" in content

    def test_import_start_get_connected(self, client, test_user):
        client.force_login(test_user)
        session = client.session
        session['pwa_access_token'] = 'valid_token'
        session['pwa_user_email'] = 'dev@company.com'
        session.save()

        url = reverse('msproject_import:start')
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "Connected Account" in content
        assert "dev@company.com" in content
        assert "Fetch Timesheet Data" in content

    def test_import_start_post_without_token_redirects_to_oauth_login(self, client, test_user):
        client.force_login(test_user)
        url = reverse('msproject_import:start')
        response = client.post(url, data={'year': 2026})

        assert response.status_code == 302
        assert reverse('msproject_import:oauth_login') in response.url

    def test_import_start_post_with_token_creates_batch_and_redirects(self, client, test_user):
        client.force_login(test_user)
        session = client.session
        session['pwa_access_token'] = 'mock_access_token_dev'
        session.save()

        url = reverse('msproject_import:start')
        response = client.post(url, data={'year': 2026})

        assert response.status_code == 302
        assert 'mapping' in response.url

        batch = ImportBatch.objects.filter(user=test_user, year=2026).first()
        assert batch is not None
        assert batch.staged_projects.count() >= 2
        assert batch.staged_logs.count() >= 2

    def test_import_start_htmx_post_with_token(self, client, test_user):
        client.force_login(test_user)
        session = client.session
        session['pwa_access_token'] = 'mock_access_token_dev'
        session.save()

        url = reverse('msproject_import:start')
        response = client.post(url, data={'year': 2026}, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        assert 'HX-Redirect' in response.headers
        assert 'mapping' in response.headers['HX-Redirect']


@pytest.mark.django_db
class TestImportMappingAndApproval:
    def test_import_mapping_post_updates_project_types_and_pending_status(self, client, test_user):
        client.force_login(test_user)
        batch = ImportBatch.objects.create(user=test_user, year=2026)
        p1 = StagingProject.objects.create(batch=batch, ms_project_name='Project 1')
        p2 = StagingProject.objects.create(batch=batch, ms_project_name='Project 2')

        url = reverse('msproject_import:mapping', kwargs={'batch_id': batch.id})
        response = client.post(url, data={
            f'project_{p1.id}': 'COMMERCIAL',
            f'project_{p2.id}': 'INTERNAL',
        })

        assert response.status_code == 302
        batch.refresh_from_db()
        p1.refresh_from_db()
        p2.refresh_from_db()

        assert batch.status == ImportBatch.Status.PENDING
        assert p1.project_type == 'COMMERCIAL'
        assert p2.project_type == 'INTERNAL'

    def test_pending_imports_denies_non_staff(self, client, test_user):
        client.force_login(test_user)
        url = reverse('msproject_import:pending')
        response = client.get(url)
        assert response.status_code == 302

    def test_approve_import_creates_projects_and_logs(self, client, staff_user, test_user):
        client.force_login(staff_user)
        batch = ImportBatch.objects.create(
            user=test_user,
            year=2026,
            status=ImportBatch.Status.PENDING
        )
        StagingProject.objects.create(batch=batch, ms_project_name='Cloud Portal', project_type='COMMERCIAL')
        StagingLog.objects.create(
            batch=batch,
            date=datetime.date(2026, 3, 10),
            hours=8.0,
            ms_project_name='Cloud Portal',
            ms_task_name='Backend API'
        )

        url = reverse('msproject_import:approve', kwargs={'batch_id': batch.id})
        response = client.post(url)

        assert response.status_code == 302
        batch.refresh_from_db()
        assert batch.status == ImportBatch.Status.APPROVED

        # Check that Project was created in the main database
        project = Project.objects.filter(name='Cloud Portal').first()
        assert project is not None
        assert project.project_type == 'COMMERCIAL'
        assert test_user in project.members.all()

        # Check Task
        task = Task.objects.filter(title='Backend API', project=project).first()
        assert task is not None

        # Check TimeLog
        time_log = TimeLog.objects.filter(user=test_user, task=task, date=datetime.date(2026, 3, 10)).first()
        assert time_log is not None
        assert time_log.hours == 8.0
        assert time_log.timesheet.status == WeeklyTimesheet.Status.APPROVED
