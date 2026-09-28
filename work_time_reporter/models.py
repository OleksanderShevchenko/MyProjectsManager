from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
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

    def delete(self, *args, **kwargs):
        # Restriction: Cannot delete historical projects
        if self.year != timezone.now().year:
            raise ValidationError("Cannot delete historical projects from previous years.")

        # Restriction: Cannot delete if there are approved time logs
        if TimeLog.objects.filter(task__project=self, timesheet__status=WeeklyTimesheet.Status.APPROVED).exists():
            raise ValidationError("Cannot delete project because it has approved time logs.")

        super().delete(*args, **kwargs)

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

    def delete(self, *args, **kwargs):
        # Restriction: Cannot delete task if project is historical
        if self.project.year != timezone.now().year:
            raise ValidationError("Cannot delete tasks belonging to historical projects.")

        # Restriction: Cannot delete if there are approved time logs
        if TimeLog.objects.filter(task=self, timesheet__status=WeeklyTimesheet.Status.APPROVED).exists():
            raise ValidationError("Cannot delete task because it has approved time logs.")

        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        # 'Magic': if deadline has not been set - set it to last day of the year
        if not self.deadline:
            current_year = timezone.now().year
            self.deadline = date(current_year, 12, 31)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class WeeklyTimesheet(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted for Approval'
        APPROVED = 'APPROVED', 'Approved'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='timesheets')
    year = models.IntegerField()
    week_number = models.IntegerField() # Номер тижня від 1 до 52/53
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        # У одного користувача може бути лише один звіт на конкретний тиждень року
        unique_together = ('user', 'year', 'week_number')

    def delete(self, *args, **kwargs):
        if self.status == self.Status.APPROVED:
            raise ValidationError("Cannot delete an approved timesheet.")
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.year} Week {self.week_number} ({self.status})"


class TimeLog(models.Model):
    # Added link to weekly report (null=True temporarily so as not to break your existing test data)
    timesheet = models.ForeignKey(WeeklyTimesheet, on_delete=models.CASCADE, related_name='time_logs', null=True,
                                  blank=True)

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    # Connect time reporting with a user
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='time_logs')

    date = models.DateField(default=timezone.now)
    # Allow fractional time reporting (like. 1.5 hours = 1 hour 30 min)
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    comment = models.TextField(blank=True, help_text="What was done?")

    class Meta:
        # IRON RULE: One cell in the grid = one record in the database
        constraints = [
            models.UniqueConstraint(fields=['user', 'task', 'date'], name='unique_user_task_date')
        ]

    def delete(self, *args, **kwargs):
        if self.timesheet and self.timesheet.status == WeeklyTimesheet.Status.APPROVED:
            raise ValidationError("Cannot delete time log belonging to an approved timesheet.")
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.task.title} ({self.hours}h)"


class CompanyCalendar(models.Model):
    """
    Global calendar to track holidays, short days before state holidays.
    Managed only by System Administrators.
    """
    DAY_TYPE_CHOICES = [
        ('HOLIDAY', 'Holiday / Non-working day'),
        ('SHORT_DAY', 'Short Day (7 hours)'),
        ('FREE_MONDAY', 'Free Monday when state holiday is on weekends'),
    ]

    date = models.DateField(unique=True, verbose_name="Date")
    day_type = models.CharField(max_length=20, choices=DAY_TYPE_CHOICES, verbose_name="Type of Day")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Description (e.g., Christmas)")

    class Meta:
        verbose_name = "Company Calendar Day"
        verbose_name_plural = "Company Calendar"
        ordering = ['date']

    def __str__(self):
        # Django magic is here - method 'get_day_type_display' generates automatically for day_type field of choices type
        return f"{self.date} - {self.get_day_type_display()}"
