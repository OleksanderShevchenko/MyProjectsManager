import datetime
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from work_time_reporter.models import Project, Task, WeeklyTimesheet, TimeLog, CompanyCalendar

User = get_user_model()


@pytest.fixture
def engineer_user(db):
    """Create a standard engineer user."""
    return User.objects.create_user(
        username="engineer",
        email="engineer@example.com",
        password="password123",
        first_name="Jane",
        last_name="Engineer"
    )


@pytest.fixture
def manager_user(db):
    """Create a project manager user."""
    return User.objects.create_user(
        username="manager",
        email="manager@example.com",
        password="password123",
        first_name="Bob",
        last_name="Manager"
    )


@pytest.fixture
def other_user(db):
    """Create a third unrelated user."""
    return User.objects.create_user(
        username="other",
        email="other@example.com",
        password="password123"
    )


@pytest.fixture
def active_project(db, manager_user, engineer_user):
    """Create an active commercial project."""
    project = Project.objects.create(
        name="Project Alpha",
        project_type=Project.ProjectType.COMMERCIAL,
        year=timezone.now().year,
        is_active=True,
        manager=manager_user
    )
    project.members.add(engineer_user)
    return project


@pytest.fixture
def active_task(db, active_project, engineer_user):
    """Create an active task assigned to the engineer."""
    task = Task.objects.create(
        title="Frontend Architecture",
        project=active_project,
        budget_hours=40,
        deadline=datetime.date(timezone.now().year, 12, 31),
        status=Task.Status.IN_PROGRESS
    )
    task.assignees.add(engineer_user)
    return task


@pytest.fixture
def draft_timesheet(db, engineer_user):
    """Create a draft weekly timesheet for the engineer."""
    today = timezone.now().date()
    year, week, _ = today.isocalendar()
    return WeeklyTimesheet.objects.create(
        user=engineer_user,
        year=year,
        week_number=week,
        status=WeeklyTimesheet.Status.DRAFT
    )


@pytest.fixture
def engineer_client(engineer_user):
    """Django test client logged in as the engineer."""
    client = Client()
    client.force_login(engineer_user)
    return client


@pytest.fixture
def manager_client(manager_user):
    """Django test client logged in as the manager."""
    client = Client()
    client.force_login(manager_user)
    return client
