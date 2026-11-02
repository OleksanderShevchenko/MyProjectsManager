import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from users.forms import UserProfileForm
from work_time_reporter.models import WeeklyTimesheet

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testengineer",
        email="testengineer@example.com",
        password="OldPassword123!",
        first_name="Jane",
        last_name="Doe",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="otheruser",
        email="other@example.com",
        password="OtherPassword123!",
        first_name="John",
        last_name="Smith",
    )


@pytest.fixture
def logged_client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestUserProfileForm:
    def test_form_valid(self, user):
        form = UserProfileForm(data={
            'first_name': 'Alice',
            'last_name': 'Wonderland',
            'email': 'alice@example.com',
        }, instance=user)
        assert form.is_valid()
        saved = form.save()
        assert saved.first_name == 'Alice'
        assert saved.last_name == 'Wonderland'
        assert saved.email == 'alice@example.com'

    def test_email_cannot_be_empty(self, user):
        form = UserProfileForm(data={
            'first_name': 'Alice',
            'last_name': 'Wonderland',
            'email': '',
        }, instance=user)
        assert not form.is_valid()
        assert 'email' in form.errors

    def test_duplicate_email_rejected(self, user, other_user):
        form = UserProfileForm(data={
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': other_user.email,
        }, instance=user)
        assert not form.is_valid()
        assert 'email' in form.errors

    def test_same_email_for_current_user_accepted(self, user):
        form = UserProfileForm(data={
            'first_name': 'Jane Updated',
            'last_name': 'Doe',
            'email': user.email,
        }, instance=user)
        assert form.is_valid()


@pytest.mark.django_db
class TestProfileView:
    def test_anonymous_redirected_to_login(self):
        client = Client()
        response = client.get(reverse('users:profile'))
        assert response.status_code == 302
        assert 'login' in response.url

    def test_profile_page_get(self, logged_client, user):
        response = logged_client.get(reverse('users:profile'))
        assert response.status_code == 200
        assert 'profile_form' in response.context
        assert 'password_form' in response.context
        assert 'stats' in response.context
        assert response.context['stats']['total'] == 0

    def test_profile_update_standard_post(self, logged_client, user):
        data = {
            'action': 'update_profile',
            'first_name': 'UpdatedFirst',
            'last_name': 'UpdatedLast',
            'email': 'updated@example.com',
        }
        response = logged_client.post(reverse('users:profile'), data)
        assert response.status_code == 302
        assert response.url == reverse('users:profile')

        user.refresh_from_db()
        assert user.first_name == 'UpdatedFirst'
        assert user.last_name == 'UpdatedLast'
        assert user.email == 'updated@example.com'

    def test_profile_update_htmx_post(self, logged_client, user):
        data = {
            'action': 'update_profile',
            'first_name': 'HtmxFirst',
            'last_name': 'HtmxLast',
            'email': 'htmx@example.com',
        }
        response = logged_client.post(
            reverse('users:profile'),
            data,
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        assert 'profile-form-container' in response.content.decode()
        assert 'HtmxFirst' in response.content.decode()

        user.refresh_from_db()
        assert user.first_name == 'HtmxFirst'
        assert user.email == 'htmx@example.com'

    def test_profile_update_invalid_htmx(self, logged_client, user):
        data = {
            'action': 'update_profile',
            'first_name': '',
            'last_name': 'Doe',
            'email': 'not-an-email',
        }
        response = logged_client.post(
            reverse('users:profile'),
            data,
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        assert 'profile_form' in response.context
        assert response.context['profile_form'].errors


@pytest.mark.django_db
class TestPasswordChangeView:
    def test_password_change_standard_post(self, logged_client, user):
        data = {
            'old_password': 'OldPassword123!',
            'new_password1': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        }
        response = logged_client.post(reverse('users:password_change'), data)
        assert response.status_code == 302
        assert response.url == reverse('users:profile')

        user.refresh_from_db()
        assert user.check_password('BrandNewPassword456!')

    def test_password_change_htmx_post(self, logged_client, user):
        data = {
            'old_password': 'OldPassword123!',
            'new_password1': 'BrandNewPassword456!',
            'new_password2': 'BrandNewPassword456!',
        }
        response = logged_client.post(
            reverse('users:password_change'),
            data,
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        assert 'password-form-container' in response.content.decode()
        assert 'successfully' in response.content.decode().lower()

        user.refresh_from_db()
        assert user.check_password('BrandNewPassword456!')

    def test_password_change_mismatch_htmx(self, logged_client, user):
        data = {
            'old_password': 'OldPassword123!',
            'new_password1': 'BrandNewPassword456!',
            'new_password2': 'WrongMismatch!',
        }
        response = logged_client.post(
            reverse('users:password_change'),
            data,
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        assert 'password_form' in response.context
        assert response.context['password_form'].errors


@pytest.mark.django_db
class TestHistoryView:
    def test_history_htmx_filtering(self, logged_client, user):
        # Create sample timesheets
        WeeklyTimesheet.objects.create(
            user=user,
            year=2025,
            week_number=10,
            status=WeeklyTimesheet.Status.APPROVED,
        )
        WeeklyTimesheet.objects.create(
            user=user,
            year=2026,
            week_number=15,
            status=WeeklyTimesheet.Status.SUBMITTED,
        )

        # Request all history
        response = logged_client.get(reverse('users:history'), HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        content = response.content.decode()
        assert 'history-container' in content
        assert 'Week 10' in content
        assert 'Week 15' in content

        # Filter by year 2026
        response_2026 = logged_client.get(
            reverse('users:history'),
            {'year': '2026'},
            HTTP_HX_REQUEST='true',
        )
        content_2026 = response_2026.content.decode()
        assert 'Week 15' in content_2026
        assert 'Week 10' not in content_2026
        assert '<option value="2026" selected>2026</option>' in content_2026
        assert '<option value="2025"' in content_2026

        # Filter by status APPROVED
        response_app = logged_client.get(
            reverse('users:history'),
            {'status': 'APPROVED'},
            HTTP_HX_REQUEST='true',
        )
        content_app = response_app.content.decode()
        assert 'Week 10' in content_app
        assert 'Week 15' not in content_app
        assert '<option value="APPROVED" selected>' in content_app

    def test_history_htmx_unseen_year_preserved(self, logged_client, user):
        """Even if filtered year (e.g. 2020) has no timesheets, it must remain selected in the dropdown."""
        response = logged_client.get(
            reverse('users:history'),
            {'year': '2020'},
            HTTP_HX_REQUEST='true',
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert '<option value="2020" selected>2020</option>' in content
        assert 'No timesheets found' in content
