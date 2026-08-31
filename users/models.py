from django.contrib.auth.models import AbstractUser

# Create your models here.
class CustomUser(AbstractUser):

    @property
    def is_active_manager(self) -> bool:
        """Checks if the user is a manager of at least one open project"""
        # managed_projects field comes from Reverse Relations "magic" of django
        # that creates this field in "work_time_reporter/models.py" in Project class
        # when we define manager field
        return self.managed_projects.filter(is_active=True).exists()
