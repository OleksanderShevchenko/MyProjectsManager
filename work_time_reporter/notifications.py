import datetime
import logging
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import WeeklyTimesheet, TimeLog

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service responsible for dispatching email notifications for timesheet events:
    - Submission to project managers
    - Approval confirmation to employee
    - Rejection / returned-to-draft notification to employee
    """

    @staticmethod
    def get_base_url() -> str:
        """
        Returns configured application base URL (e.g. 'https://myprojectsmanager.com'),
        falling back to environment variable APP_BASE_URL or 'http://localhost:8000'.
        """
        url = os.environ.get('APP_BASE_URL', '').rstrip('/')
        if not url:
            return 'http://localhost:8000'
        return url

    @staticmethod
    def get_timesheet_period_dates(timesheet: WeeklyTimesheet) -> tuple[datetime.date, datetime.date]:
        """Returns the start (Monday) and end (Sunday) dates for the timesheet week."""
        monday = datetime.date.fromisocalendar(timesheet.year, timesheet.week_number, 1)
        sunday = monday + datetime.timedelta(days=6)
        return monday, sunday

    @staticmethod
    def get_timesheet_total_hours(timesheet: WeeklyTimesheet) -> str:
        """Calculates total logged hours formatted nicely as a string."""
        total = TimeLog.objects.filter(timesheet=timesheet).aggregate(Sum('hours'))['hours__sum'] or 0
        total_float = float(total)
        return f"{total_float:g}"

    @classmethod
    def get_managers_for_employee(cls, employee) -> list:
        """
        Finds all active project managers for active projects where the given employee is a member.
        Excludes the employee themselves and managers without an email.
        """
        user_model = get_user_model()
        return list(
            user_model.objects.filter(
                managed_projects__members=employee,
                managed_projects__is_active=True,
            )
            .exclude(id=employee.id)
            .exclude(email='')
            .exclude(email__isnull=True)
            .distinct()
        )

    @classmethod
    def notify_timesheet_submitted(cls, timesheet: WeeklyTimesheet, base_url: str | None = None) -> int:
        """
        Dispatches notification emails to project managers when an employee submits a timesheet.
        Returns the number of successfully sent emails.
        """
        managers = cls.get_managers_for_employee(timesheet.user)
        if not managers:
            logger.info(
                "No eligible project managers with email found for employee %s (timesheet %s). Skipping notification.",
                timesheet.user.username,
                timesheet.id,
            )
            return 0

        root_url = (base_url if base_url is not None else cls.get_base_url()).rstrip('/')
        approvals_url = f"{root_url}{reverse('work_time_reporter:team_approvals')}"
        period_start, period_end = cls.get_timesheet_period_dates(timesheet)
        total_hours = cls.get_timesheet_total_hours(timesheet)
        employee_name = timesheet.user.get_full_name() or timesheet.user.username

        sent_count = 0
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'MyProjectsManager <noreply@myprojectsmanager.local>')

        for manager in managers:
            manager_name = manager.get_full_name() or manager.username
            subject = _("[MyProjectsManager] Timesheet submitted by %(employee)s (Week %(week)s, %(year)s)") % {
                'employee': employee_name,
                'week': timesheet.week_number,
                'year': timesheet.year,
            }
            subject = "".join(str(subject).splitlines())

            context = {
                'manager_name': manager_name,
                'employee_name': employee_name,
                'week_number': timesheet.week_number,
                'year': timesheet.year,
                'period_start': period_start.strftime('%b %d, %Y'),
                'period_end': period_end.strftime('%b %d, %Y'),
                'total_hours': total_hours,
                'approvals_url': approvals_url,
            }

            try:
                html_content = render_to_string('work_time_reporter/emails/submission_email.html', context)
                text_content = render_to_string('work_time_reporter/emails/submission_email.txt', context)

                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=from_email,
                    to=[manager.email],
                )
                email.attach_alternative(html_content, "text/html")
                email.send(fail_silently=False)
                sent_count += 1
                logger.info(
                    "Timesheet submission notification sent to manager %s (%s) for timesheet %s",
                    manager.username,
                    manager.email,
                    timesheet.id,
                )
            except Exception as e:
                logger.error(
                    "Failed to send timesheet submission email to manager %s (%s): %s",
                    manager.username,
                    manager.email,
                    str(e),
                    exc_info=True,
                )

        return sent_count

    @classmethod
    def notify_timesheet_approved(cls, timesheet: WeeklyTimesheet, reviewer=None, base_url: str | None = None) -> bool:
        """
        Dispatches notification email to the employee when their timesheet is approved.
        Returns True if sent successfully, False otherwise.
        """
        employee = timesheet.user
        if not employee.email:
            logger.info("Employee %s has no email address. Skipping approval notification.", employee.username)
            return False

        root_url = (base_url if base_url is not None else cls.get_base_url()).rstrip('/')
        dashboard_url = f"{root_url}{reverse('work_time_reporter:dashboard_week', kwargs={'year': timesheet.year, 'week': timesheet.week_number})}"
        period_start, period_end = cls.get_timesheet_period_dates(timesheet)
        total_hours = cls.get_timesheet_total_hours(timesheet)
        employee_name = employee.get_full_name() or employee.username

        approver = reviewer or timesheet.approved_by
        manager_name = (approver.get_full_name() or approver.username) if approver else _("Manager")

        subject = _("[MyProjectsManager] Timesheet approved for Week %(week)s, %(year)s") % {
            'week': timesheet.week_number,
            'year': timesheet.year,
        }
        subject = "".join(str(subject).splitlines())

        context = {
            'employee_name': employee_name,
            'manager_name': manager_name,
            'week_number': timesheet.week_number,
            'year': timesheet.year,
            'period_start': period_start.strftime('%b %d, %Y'),
            'period_end': period_end.strftime('%b %d, %Y'),
            'total_hours': total_hours,
            'dashboard_url': dashboard_url,
        }

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'MyProjectsManager <noreply@myprojectsmanager.local>')

        try:
            html_content = render_to_string('work_time_reporter/emails/approved_email.html', context)
            text_content = render_to_string('work_time_reporter/emails/approved_email.txt', context)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[employee.email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            logger.info(
                "Timesheet approval notification sent to %s (%s) for timesheet %s",
                employee.username,
                employee.email,
                timesheet.id,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to send timesheet approval email to %s (%s): %s",
                employee.username,
                employee.email,
                str(e),
                exc_info=True,
            )
            return False

    @classmethod
    def notify_timesheet_rejected(
        cls,
        timesheet: WeeklyTimesheet,
        reviewer=None,
        rejection_comment: str = '',
        base_url: str | None = None,
    ) -> bool:
        """
        Dispatches notification email to the employee when their timesheet is returned to draft for revision.
        Returns True if sent successfully, False otherwise.
        """
        employee = timesheet.user
        if not employee.email:
            logger.info("Employee %s has no email address. Skipping returned to draft notification.", employee.username)
            return False

        root_url = (base_url if base_url is not None else cls.get_base_url()).rstrip('/')
        dashboard_url = f"{root_url}{reverse('work_time_reporter:dashboard_week', kwargs={'year': timesheet.year, 'week': timesheet.week_number})}"
        period_start, period_end = cls.get_timesheet_period_dates(timesheet)
        total_hours = cls.get_timesheet_total_hours(timesheet)
        employee_name = employee.get_full_name() or employee.username

        manager_name = (reviewer.get_full_name() or reviewer.username) if reviewer else _("Manager")
        comment = rejection_comment or timesheet.rejection_comment

        subject = _("[MyProjectsManager] Action Required: Timesheet returned for revision (Week %(week)s, %(year)s)") % {
            'week': timesheet.week_number,
            'year': timesheet.year,
        }
        subject = "".join(str(subject).splitlines())

        context = {
            'employee_name': employee_name,
            'manager_name': manager_name,
            'week_number': timesheet.week_number,
            'year': timesheet.year,
            'period_start': period_start.strftime('%b %d, %Y'),
            'period_end': period_end.strftime('%b %d, %Y'),
            'total_hours': total_hours,
            'rejection_comment': comment,
            'dashboard_url': dashboard_url,
        }

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'MyProjectsManager <noreply@myprojectsmanager.local>')

        try:
            html_content = render_to_string('work_time_reporter/emails/rejected_email.html', context)
            text_content = render_to_string('work_time_reporter/emails/rejected_email.txt', context)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[employee.email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            logger.info(
                "Timesheet returned-to-draft notification sent to %s (%s) for timesheet %s",
                employee.username,
                employee.email,
                timesheet.id,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to send timesheet returned-to-draft email to %s (%s): %s",
                employee.username,
                employee.email,
                str(e),
                exc_info=True,
            )
            return False
