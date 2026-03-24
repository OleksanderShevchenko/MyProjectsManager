from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

from .models import ImportBatch, StagingProject, StagingLog
from .services import fetch_pwa_data
from work_time_reporter.models import Project, Task, WeeklyTimesheet, TimeLog


@login_required(login_url='work_time_reporter:login')
def import_start(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        year = request.POST.get('year')

        if not email or not password or not year:
            messages.error(request, "All fields are required.!")
            return redirect('msproject_import:start')

        try:
            # 1. Pulling data through fetch_pwa_data service script
            daily_data_map, unique_projects = fetch_pwa_data(email, password, int(year))

            if not daily_data_map:
                messages.warning(request, f"Data for {year} year has not found.")
                return redirect('msproject_import:start')

            # 2. Create a batch
            batch = ImportBatch.objects.create(user=request.user, year=year)

            # 3. We record unique projects for markup
            for proj_name in unique_projects:
                StagingProject.objects.create(batch=batch, ms_project_name=proj_name)

            # 4. Record all hours in raw form
            logs_to_create = []
            for date_str, items in daily_data_map.items():
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                for item in items:
                    logs_to_create.append(StagingLog(
                        batch=batch,
                        date=log_date,
                        hours=item['hours'],
                        ms_project_name=item['project'],
                        ms_task_name=item['task']
                    ))

            # bulk_create saves all records in 1 database query (very fast!)
            StagingLog.objects.bulk_create(logs_to_create)

            messages.success(request, f"Successfully loaded {len(unique_projects)} projects. Now indicate their types.")
            return redirect('msproject_import:mapping', batch_id=batch.id)

        except Exception as e:
            messages.error(request, f"Import error: {str(e)}")
            return redirect('msproject_import:start')

    return render(request, 'msproject_import/start.html')


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

        # Change the status to PENDING (so that the manager can see it)
        batch.status = ImportBatch.Status.PENDING
        batch.save()

        messages.success(request, "The data has been successfully sent to the manager for approval!")
        return redirect('work_time_reporter:dashboard')

    return render(request, 'msproject_import/mapping.html', {'batch': batch})


@login_required(login_url='work_time_reporter:login')
def pending_imports(request):
    # Access only for managers (staff)
    if not request.user.is_staff:
        messages.error(request, "Access denied.")
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
            # We use a transaction: either everything is successful, or nothing is written
            with transaction.atomic():
                # 1. Create Projects
                project_map = {}
                for sp in batch.staged_projects.all():
                    # Search for a project by name or create a new one
                    project, created = Project.objects.get_or_create(
                        name=sp.ms_project_name,
                        defaults={
                            'project_type': sp.project_type or 'COMMERCIAL',
                            'year': batch.year,
                            'is_active': True,
                            'manager': request.user  # Those who is approving is become the projects manager
                        }
                    )
                    project.members.add(batch.user)  # Add engineer to the project
                    project_map[sp.ms_project_name] = project

                # 2. Create Tasks and Time logs
                for log in batch.staged_logs.all():
                    project = project_map.get(log.ms_project_name)
                    if not project:
                        continue

                    # Searching for existing task or create new
                    task, created = Task.objects.get_or_create(
                        title=log.ms_task_name,
                        project=project,
                        defaults={
                            'budget_hours': 0,  # For imported tasks set budget = 0, usually it is history data that closed
                            'status': 'IN_PROGRESS'
                        }
                    )
                    task.assignees.add(batch.user)

                    # define year and week
                    year, week, _ = log.date.isocalendar()

                    # Looking for existing timesheet or create new
                    ts, created = WeeklyTimesheet.objects.get_or_create(
                        user=batch.user,
                        year=year,
                        week_number=week,
                        defaults={'status': WeeklyTimesheet.Status.APPROVED}
                    )
                    # If timesheet already existed (Draft/Submitted), make it Approved
                    ts.status = WeeklyTimesheet.Status.APPROVED
                    ts.save()

                    # Transfer logged hours
                    TimeLog.objects.update_or_create(
                        user=batch.user,
                        task=task,
                        date=log.date,
                        defaults={
                            'hours': log.hours,
                            'timesheet': ts,
                            'comment': 'Imported from PWA'
                        }
                    )

                # 3. Close Imported tasks by APPROVE
                batch.status = ImportBatch.Status.APPROVED
                batch.save()
                messages.success(request,
                                 f"Import for {batch.user.username} successfully done! All data transferred to main database.")

        except Exception as e:
            messages.error(request, f"Error during approval: {str(e)}")

        return redirect('msproject_import:pending')
