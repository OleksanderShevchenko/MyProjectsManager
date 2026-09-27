import datetime
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from work_time_reporter.models import Project, Task, TimeLog, WeeklyTimesheet
from .models import ImportBatch, StagingLog, StagingProject
from .services import MicrosoftOAuthService, fetch_pwa_data


@login_required(login_url='work_time_reporter:login')
def oauth_login(request):
    """
    Initiates Microsoft OAuth 2.0 Authorization Code flow for PWA import.
    """
    year = request.GET.get('year', timezone.now().year)
    try:
        year = int(year)
    except (ValueError, TypeError):
        year = timezone.now().year

    request.session['oauth_import_year'] = year

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state

    redirect_uri = request.build_absolute_uri(reverse('msproject_import:oauth_callback'))
    auth_url = MicrosoftOAuthService.get_authorization_url(redirect_uri, state=state)

    return redirect(auth_url)


@login_required(login_url='work_time_reporter:login')
def oauth_callback(request):
    """
    Handles redirect callback from Microsoft Entra ID with the authorization code.
    """
    # Verify state to prevent CSRF attacks
    session_state = request.session.get('oauth_state')
    received_state = request.GET.get('state')

    if not session_state or not received_state or session_state != received_state:
        messages.error(request, _("Invalid OAuth state parameter. Please try again."))
        return redirect('msproject_import:start')

    # Clean up state
    request.session.pop('oauth_state', None)

    # Check for authorization errors
    error = request.GET.get('error')
    if error:
        error_desc = request.GET.get('error_description', error)
        messages.error(request, _("Microsoft authorization failed: %(error)s") % {'error': error_desc})
        return redirect('msproject_import:start')

    code = request.GET.get('code')
    if not code:
        messages.error(request, _("No authorization code received from Microsoft."))
        return redirect('msproject_import:start')

    redirect_uri = request.build_absolute_uri(reverse('msproject_import:oauth_callback'))

    try:
        token_data = MicrosoftOAuthService.exchange_code_for_token(code, redirect_uri)
        request.session['pwa_access_token'] = token_data.get('access_token')
        request.session['pwa_refresh_token'] = token_data.get('refresh_token')
        request.session['pwa_user_email'] = token_data.get('user_email', request.user.email)
        request.session['pwa_user_name'] = token_data.get('user_name', '')

        messages.success(request, _("Successfully connected your Microsoft 365 account!"))
    except Exception as e:
        messages.error(request, _("Failed to complete Microsoft authentication: %(error)s") % {'error': str(e)})

    return redirect('msproject_import:start')


@login_required(login_url='work_time_reporter:login')
def oauth_disconnect(request):
    """
    Disconnects the active Microsoft OAuth session.
    """
    request.session.pop('pwa_access_token', None)
    request.session.pop('pwa_refresh_token', None)
    request.session.pop('pwa_user_email', None)
    request.session.pop('pwa_user_name', None)

    messages.info(request, _("Disconnected Microsoft 365 account."))
    return redirect('msproject_import:start')


@login_required(login_url='work_time_reporter:login')
def import_start(request):
    """
    Main entry point for MS Project import using OAuth 2.0 (credential-free).
    """
    access_token = request.session.get('pwa_access_token')
    is_connected = bool(access_token)

    if request.method == 'POST':
        year_str = request.POST.get('year')
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            year = timezone.now().year

        request.session['oauth_import_year'] = year

        # If not connected, redirect to Microsoft OAuth authorization
        if not is_connected:
            return redirect(f"{reverse('msproject_import:oauth_login')}?year={year}")

        try:
            daily_data_map, unique_projects = fetch_pwa_data(access_token, year)

            if not daily_data_map:
                messages.warning(request, _("No time reporting data found for year %(year)s.") % {'year': year})
                if getattr(request, 'htmx', False):
                    response = HttpResponse()
                    response['HX-Redirect'] = reverse('msproject_import:start')
                    return response
                return redirect('msproject_import:start')

            # Create import batch
            batch = ImportBatch.objects.create(user=request.user, year=year)

            # Record unique projects for mapping
            for proj_name in unique_projects:
                StagingProject.objects.create(batch=batch, ms_project_name=proj_name)

            # Record all hours in staging logs
            logs_to_create = []
            for date_str, items in daily_data_map.items():
                log_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                for item in items:
                    logs_to_create.append(StagingLog(
                        batch=batch,
                        date=log_date,
                        hours=item['hours'],
                        ms_project_name=item['project'],
                        ms_task_name=item['task'],
                    ))

            StagingLog.objects.bulk_create(logs_to_create)

            messages.success(
                request,
                _("Successfully loaded %(count)d projects. Please map their project types.") % {
                    'count': len(unique_projects)
                }
            )

            mapping_url = reverse('msproject_import:mapping', kwargs={'batch_id': batch.id})
            if getattr(request, 'htmx', False):
                response = HttpResponse()
                response['HX-Redirect'] = mapping_url
                return response
            return redirect('msproject_import:mapping', batch_id=batch.id)

        except Exception as e:
            # If token expired or rejected, suggest re-connecting
            if 'Authentication' in str(e) or 'token' in str(e).lower() or '401' in str(e):
                request.session.pop('pwa_access_token', None)
                messages.error(request, _("Microsoft session expired. Please reconnect your account."))
            else:
                messages.error(request, _("Import error: %(error)s") % {'error': str(e)})

            if getattr(request, 'htmx', False):
                response = HttpResponse()
                response['HX-Redirect'] = reverse('msproject_import:start')
                return response
            return redirect('msproject_import:start')

    selected_year = request.session.get('oauth_import_year', timezone.now().year)
    context = {
        'is_connected': is_connected,
        'pwa_user_email': request.session.get('pwa_user_email', request.user.email),
        'pwa_user_name': request.session.get('pwa_user_name', ''),
        'is_oauth_configured': MicrosoftOAuthService.is_configured(),
        'selected_year': selected_year,
    }
    return render(request, 'msproject_import/start.html', context)


@login_required(login_url='work_time_reporter:login')
def import_mapping(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id, user=request.user)

    if request.method == 'POST':
        # Save selected project types
        projects = batch.staged_projects.all()
        for proj in projects:
            selected_type = request.POST.get(f'project_{proj.id}')
            if selected_type:
                proj.project_type = selected_type
                proj.save()

        # Change status to PENDING for manager review
        batch.status = ImportBatch.Status.PENDING
        batch.save()

        messages.success(request, _("The import batch has been sent to the manager for approval!"))
        return redirect('work_time_reporter:dashboard')

    return render(request, 'msproject_import/mapping.html', {'batch': batch})


@login_required(login_url='work_time_reporter:login')
def pending_imports(request):
    # Access only for managers (staff)
    if not request.user.is_staff:
        messages.error(request, _("Access denied."))
        return redirect('work_time_reporter:dashboard')

    batches = ImportBatch.objects.filter(status=ImportBatch.Status.PENDING).order_by('-created_at')
    return render(request, 'msproject_import/pending.html', {'batches': batches})


@login_required(login_url='work_time_reporter:login')
def approve_import(request, batch_id):
    if not request.user.is_staff:
        return redirect('work_time_reporter:dashboard')

    batch = get_object_or_404(ImportBatch, id=batch_id, status=ImportBatch.Status.PENDING)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                current_year = timezone.now().year
                is_historical = batch.year < current_year

                # 1. Create Projects
                project_map = {}
                for sp in batch.staged_projects.all():
                    project, created = Project.objects.get_or_create(
                        name=sp.ms_project_name,
                        defaults={
                            'project_type': sp.project_type or 'COMMERCIAL',
                            'year': batch.year,
                            'is_active': not is_historical,
                            'manager': request.user,
                        }
                    )
                    project.members.add(batch.user)
                    project_map[sp.ms_project_name] = project

                # 2. Create Tasks and Time logs
                for log in batch.staged_logs.all():
                    project = project_map.get(log.ms_project_name)
                    if not project:
                        continue

                    task, created = Task.objects.get_or_create(
                        title=log.ms_task_name,
                        project=project,
                        defaults={
                            'budget_hours': 0,
                            'status': 'IN_PROGRESS',
                        }
                    )
                    task.assignees.add(batch.user)

                    year, week, _ = log.date.isocalendar()

                    ts, created = WeeklyTimesheet.objects.get_or_create(
                        user=batch.user,
                        year=year,
                        week_number=week,
                        defaults={'status': WeeklyTimesheet.Status.APPROVED},
                    )
                    ts.status = WeeklyTimesheet.Status.APPROVED
                    ts.save()

                    TimeLog.objects.update_or_create(
                        user=batch.user,
                        task=task,
                        date=log.date,
                        defaults={
                            'hours': log.hours,
                            'timesheet': ts,
                            'comment': 'Imported from PWA',
                        }
                    )

                # 3. Mark batch as APPROVED
                batch.status = ImportBatch.Status.APPROVED
                batch.save()
                messages.success(
                    request,
                    _("Import for %(user)s successfully approved! All data transferred to main database.") % {
                        'user': batch.user.username
                    }
                )

        except Exception as e:
            messages.error(request, _("Error during approval: %(error)s") % {'error': str(e)})

        return redirect('msproject_import:pending')
