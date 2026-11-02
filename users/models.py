from django.contrib.auth.models import AbstractUser

# Create your models here.
class CustomUser(AbstractUser):

    @property
    def is_active_manager(self) -> bool:
        """Checks if the user is a manager of at least one open project or in Project Manager group"""
        # managed_projects field comes from Reverse Relations "magic" of django
        # that creates this field in "work_time_reporter/models.py" in Project class
        # when we define manager field
        return (
            self.managed_projects.filter(is_active=True).exists()
            or self.groups.filter(name='Project Manager').exists()
        )

    @property
    def is_admin_role(self) -> bool:
        """Checks if the user has administrative privileges (superuser or in Admin group)"""
        return self.is_superuser or self.groups.filter(name='Admin').exists()

    @property
    def is_engineer_role(self) -> bool:
        """Checks if the user has the engineer role (in Engineer group or not a manager)"""
        return self.groups.filter(name='Engineer').exists() or not self.is_active_manager

