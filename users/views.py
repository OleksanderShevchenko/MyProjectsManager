from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _

from work_time_reporter.models import WeeklyTimesheet, TimeLog
from .forms import UserProfileForm, UserPasswordChangeForm


@login_required(login_url='work_time_reporter:login')
def profile_view(request):
    """
    Displays the user profile dashboard including personal info, assigned projects,
    timesheet summary statistics, and history. Supports HTMX form submissions.
    """
    user = request.user
    profile_form = UserProfileForm(instance=user)
    password_form = UserPasswordChangeForm(user=user)
    success_message = None

    if request.method == 'POST' and request.POST.get('action') == 'update_profile':
        profile_form = UserProfileForm(request.POST, instance=user)
        if profile_form.is_valid():
            profile_form.save()
            success_message = _("Profile details updated successfully! 💾")
            if getattr(request, 'htmx', False):
                return render(request, 'users/partials/profile_form.html', {
                    'profile_form': profile_form,
                    'success_message': success_message,
                })
            messages.success(request, success_message)
            return redirect('users:profile')
        else:
            if getattr(request, 'htmx', False):
                return render(request, 'users/partials/profile_form.html', {
                    'profile_form': profile_form,
                })

    # Summary Statistics
    user_timesheets = WeeklyTimesheet.objects.filter(user=user)
    total_timesheets = user_timesheets.count()
    approved_count = user_timesheets.filter(status=WeeklyTimesheet.Status.APPROVED).count()
    submitted_count = user_timesheets.filter(status=WeeklyTimesheet.Status.SUBMITTED).count()
    draft_count = user_timesheets.filter(status=WeeklyTimesheet.Status.DRAFT).count()

    total_hours_data = TimeLog.objects.filter(user=user).aggregate(total=Sum('hours'))
    total_hours = float(total_hours_data['total'] or 0)

    # Active Projects
    assigned_projects = user.assigned_projects.filter(is_active=True).distinct()
    managed_projects = user.managed_projects.filter(is_active=True).distinct()

    # Timesheet History
    history_qs = user_timesheets.select_related('approved_by').annotate(
        total_hours=Coalesce(Sum('time_logs__hours'), Decimal('0.0'))
    ).order_by('-year', '-week_number')

    available_years = list(user_timesheets.values_list('year', flat=True).distinct().order_by('-year'))

    context = {
        'profile_form': profile_form,
        'password_form': password_form,
        'success_message': success_message,
        'stats': {
            'total': total_timesheets,
            'approved': approved_count,
            'submitted': submitted_count,
            'draft': draft_count,
            'hours': total_hours,
        },
        'assigned_projects': assigned_projects,
        'managed_projects': managed_projects,
        'timesheets': history_qs,
        'available_years': available_years,
        'selected_year': '',
        'selected_status': '',
        'status_choices': WeeklyTimesheet.Status.choices,
    }
    return render(request, 'users/profile.html', context)


@login_required(login_url='work_time_reporter:login')
def password_change_view(request):
    """
    Handles user password changes. Validates old and new passwords, updates
    session auth hash, and returns HTMX inline feedback.
    """
    if request.method == 'POST':
        password_form = UserPasswordChangeForm(user=request.user, data=request.POST)
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            success_message = _("Your password has been changed successfully! 🔒")

            if getattr(request, 'htmx', False):
                return render(request, 'users/partials/password_change_form.html', {
                    'password_form': UserPasswordChangeForm(user=user),
                    'success_message': success_message,
                })

            messages.success(request, success_message)
            return redirect('users:profile')
        else:
            if getattr(request, 'htmx', False):
                return render(request, 'users/partials/password_change_form.html', {
                    'password_form': password_form,
                })

    return redirect('users:profile')


@login_required(login_url='work_time_reporter:login')
def history_view(request):
    """
    Renders filterable timesheet submission history.
    Supports filtering by year and status via HTMX.
    """
    user_timesheets = WeeklyTimesheet.objects.filter(user=request.user)
    available_years = list(user_timesheets.values_list('year', flat=True).distinct().order_by('-year'))

    qs = user_timesheets.select_related('approved_by').annotate(
        total_hours=Coalesce(Sum('time_logs__hours'), Decimal('0.0'))
    )

    year = request.GET.get('year', '').strip()
    if year and year.isdigit():
        year_int = int(year)
        qs = qs.filter(year=year_int)
        if year_int not in available_years:
            available_years.append(year_int)
            available_years.sort(reverse=True)

    status = request.GET.get('status', '').strip()
    if status and status in WeeklyTimesheet.Status.values:
        qs = qs.filter(status=status)

    qs = qs.order_by('-year', '-week_number')

    context = {
        'timesheets': qs,
        'available_years': available_years,
        'selected_year': year,
        'selected_status': status,
    }

    if getattr(request, 'htmx', False):
        return render(request, 'users/partials/history_table.html', context)

    return redirect('users:profile')

