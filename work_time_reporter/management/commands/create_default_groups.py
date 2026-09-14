from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates default user groups (Engineer, Project Manager, Admin) and assigns model permissions."

    def handle(self, *args, **options):
        # Base permissions for Engineer
        engineer_codenames = [
            'view_project',
            'view_task',
            'view_companycalendar',
            'view_weeklytimesheet',
            'add_weeklytimesheet',
            'change_weeklytimesheet',
            'add_timelog',
            'change_timelog',
            'delete_timelog',
            'view_timelog',
        ]

        # Project Manager extends Engineer permissions with project and task management
        manager_extra_codenames = [
            'add_project',
            'change_project',
            'add_task',
            'change_task',
            'delete_task',
        ]
        manager_codenames = engineer_codenames + manager_extra_codenames

        # 1. Engineer group
        engineer_group, _ = Group.objects.get_or_create(name='Engineer')
        engineer_perms = Permission.objects.filter(
            content_type__app_label='work_time_reporter',
            codename__in=engineer_codenames,
        )
        engineer_group.permissions.set(engineer_perms)
        self.stdout.write(
            self.style.SUCCESS(f"Configured 'Engineer' group with {engineer_perms.count()} permissions.")
        )

        # 2. Project Manager group
        manager_group, _ = Group.objects.get_or_create(name='Project Manager')
        manager_perms = Permission.objects.filter(
            content_type__app_label='work_time_reporter',
            codename__in=manager_codenames,
        )
        manager_group.permissions.set(manager_perms)
        self.stdout.write(
            self.style.SUCCESS(f"Configured 'Project Manager' group with {manager_perms.count()} permissions.")
        )

        # 3. Admin group
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        admin_perms = Permission.objects.filter(
            content_type__app_label__in=['work_time_reporter', 'users']
        )
        admin_group.permissions.set(admin_perms)
        self.stdout.write(
            self.style.SUCCESS(f"Configured 'Admin' group with {admin_perms.count()} permissions.")
        )
