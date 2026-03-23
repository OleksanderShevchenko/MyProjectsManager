from django.db import models

from users.models import CustomUser


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        MAPPING = 'MAPPING', 'Needs Project Mapping'  # Waiting for the engineer to mark out the projects
        PENDING = 'PENDING', 'Pending Manager Approval'
        APPROVED = 'APPROVED', 'Approved & Processed'
        REJECTED = 'REJECTED', 'Rejected'

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='import_batches')
    year = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.MAPPING)

    def __str__(self):
        return f"Import {self.year} by {self.user.username} ({self.status})"


class StagingProject(models.Model):
    PROJECT_TYPES = [
        ('COMMERCIAL', 'Commercial'),
        ('INTERNAL', 'Internal (Non-Commercial)'),
        ('ADMINISTRATIVE', 'Administrative'),
    ]
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='staged_projects')
    ms_project_name = models.CharField(max_length=255)
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPES, blank=True, null=True)

    def __str__(self):
        return f"{self.ms_project_name} -> {self.project_type}"


class StagingLog(models.Model):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='staged_logs')
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    ms_project_name = models.CharField(max_length=255)
    ms_task_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.date}: {self.hours}h on {self.ms_project_name}"
