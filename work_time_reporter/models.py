from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import date


class Project(models.Model):  # a year contract by the matter of fact
    class ProjectType(models.TextChoices):
        COMMERCIAL = 'COMMERCIAL', 'Commercial'
        INTERNAL = 'INTERNAL', 'Internal / Pet Project'
        ADMINISTRATIVE = 'ADMINISTRATIVE', 'Administrative time like sick leave vacation or traveling'

    name = models.CharField(max_length=255, verbose_name="Project Name")
    project_type = models.CharField(
        max_length=20,
        choices=ProjectType.choices,
        default=ProjectType.COMMERCIAL
    )
    # Store year of the contract. By default, it is current year
    year = models.IntegerField(default=timezone.now().year)
    is_active = models.BooleanField(default=True)

    # 1. Manager of the project (Owner)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='managed_projects',
        verbose_name="Project Manager"
    )
    # 2. Team of the project (Users who have access to project)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assigned_projects',
        verbose_name="Team Members"
    )

    def __str__(self):
        return f"{self.name} ({self.year})"


class Task(models.Model):
    class Status(models.TextChoices):
        NOT_SUBMITTED = 'NOT_SUBMITTED', 'Not Submitted'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        DONE = 'DONE', 'Done'

    title = models.CharField(max_length=255, verbose_name="Task Title")
    # Deleting a project leads to deleting all its tasks - (CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    # users who work with the task
    assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assigned_tasks',
        verbose_name="Assigned Engineers"
    )

    # Task budget in hours
    budget_hours = models.PositiveIntegerField(help_text="Allocated budget in hours")

    # Deadline (optional) - if not set use end of the year
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_SUBMITTED)

    def save(self, *args, **kwargs):
        # 'Magic': if deadline has not been set - set it to last day of the year
        if not self.deadline:
            current_year = timezone.now().year
            self.deadline = date(current_year, 12, 31)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TimeLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    # Connect time reporting with a user
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='time_logs')

    date = models.DateField(default=timezone.now)
    # Allow fractional time reporting (like. 1.5 hours = 1 hour 30 min)
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    comment = models.TextField(blank=True, help_text="What was done?")

    def __str__(self):
        return f"{self.user} - {self.task.title} ({self.hours}h)"
