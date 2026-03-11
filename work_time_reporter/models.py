from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import date


class Project(models.Model):
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
    # Зберігаємо рік контракту. За замовчуванням беремо поточний рік.
    year = models.IntegerField(default=timezone.now().year)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.year})"


class Task(models.Model):
    class Status(models.TextChoices):
        NOT_SUBMITTED = 'NOT_SUBMITTED', 'Not Submitted'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        DONE = 'DONE', 'Done'

    title = models.CharField(max_length=255, verbose_name="Task Title")
    # Якщо видалити проєкт, всі його таски теж видаляться (CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')

    # Бюджет у цілих годинах
    budget_hours = models.PositiveIntegerField(help_text="Allocated budget in hours")

    # Дедлайн (опційне поле)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_SUBMITTED)

    def save(self, *args, **kwargs):
        # Магія: якщо дедлайн не вказано, ставимо 31 грудня поточного року
        if not self.deadline:
            current_year = timezone.now().year
            self.deadline = date(current_year, 12, 31)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class TimeLog(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='time_logs')
    # Зв'язуємо з нашою кастомною моделлю користувача
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='time_logs')

    date = models.DateField(default=timezone.now)
    # Дозволяє списувати дробові години (напр. 1.5 години = 1 год 30 хв)
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    comment = models.TextField(blank=True, help_text="What was done?")

    def __str__(self):
        return f"{self.user} - {self.task.title} ({self.hours}h)"
