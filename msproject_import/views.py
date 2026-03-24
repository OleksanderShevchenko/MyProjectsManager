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
            messages.error(request, "Всі поля обов'язкові!")
            return redirect('msproject_import:start')

        try:
            # 1. Тягнемо дані через твій скрипт
            daily_data_map, unique_projects = fetch_pwa_data(email, password, int(year))

            if not daily_data_map:
                messages.warning(request, f"Даних за {year} рік не знайдено.")
                return redirect('msproject_import:start')

            # 2. Створюємо пакет (Batch)
            batch = ImportBatch.objects.create(user=request.user, year=year)

            # 3. Записуємо унікальні проєкти для розмітки
            for proj_name in unique_projects:
                StagingProject.objects.create(batch=batch, ms_project_name=proj_name)

            # 4. Записуємо всі години в сирому вигляді
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

            # bulk_create зберігає всі записи за 1 запит до бази (дуже швидко!)
            StagingLog.objects.bulk_create(logs_to_create)

            messages.success(request, f"Успішно завантажено {len(unique_projects)} проєктів. Тепер вкажіть їхні типи.")
            return redirect('msproject_import:mapping', batch_id=batch.id)

        except Exception as e:
            messages.error(request, f"Помилка імпорту: {str(e)}")
            return redirect('msproject_import:start')

    return render(request, 'msproject_import/start.html')


@login_required(login_url='work_time_reporter:login')
def import_mapping(request, batch_id):
    batch = get_object_or_404(ImportBatch, id=batch_id, user=request.user)

    if request.method == 'POST':
        # Зберігаємо вибрані типи проєктів
        projects = batch.staged_projects.all()
        for proj in projects:
            selected_type = request.POST.get(f'project_{proj.id}')
            if selected_type:
                proj.project_type = selected_type
                proj.save()

        # Переводимо статус у PENDING (щоб побачив менеджер)
        batch.status = ImportBatch.Status.PENDING
        batch.save()

        messages.success(request, "Дані успішно відправлені менеджеру на затвердження!")
        return redirect('work_time_reporter:dashboard')

    return render(request, 'msproject_import/mapping.html', {'batch': batch})


@login_required(login_url='work_time_reporter:login')
def pending_imports(request):
    # Доступ тільки для менеджерів (staff)
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
            # Використовуємо транзакцію: або все успішно, або нічого не запишеться
            with transaction.atomic():
                # 1. СТВОРЕННЯ ПРОЄКТІВ
                project_map = {}
                for sp in batch.staged_projects.all():
                    # Шукаємо проєкт за назвою або створюємо новий
                    project, created = Project.objects.get_or_create(
                        name=sp.ms_project_name,
                        defaults={
                            'project_type': sp.project_type or 'COMMERCIAL',
                            'year': batch.year,
                            'is_active': True,
                            'manager': request.user  # Той, хто апрувить, стає менеджером проєкту
                        }
                    )
                    project.members.add(batch.user)  # Додаємо інженера до проєкту
                    project_map[sp.ms_project_name] = project

                # 2. СТВОРЕННЯ ТАСОК ТА ГОДИН
                for log in batch.staged_logs.all():
                    project = project_map.get(log.ms_project_name)
                    if not project:
                        continue

                    # Шукаємо або створюємо таску
                    task, created = Task.objects.get_or_create(
                        title=log.ms_task_name,
                        project=project,
                        defaults={
                            'budget_hours': 0,  # Для імпортованих ставимо 0, менеджер потім поправить
                            'status': 'IN_PROGRESS'
                        }
                    )
                    task.assignees.add(batch.user)

                    # Визначаємо тиждень
                    year, week, _ = log.date.isocalendar()

                    # Шукаємо або створюємо таймшит
                    ts, created = WeeklyTimesheet.objects.get_or_create(
                        user=batch.user,
                        year=year,
                        week_number=week,
                        defaults={'status': WeeklyTimesheet.Status.APPROVED}
                    )
                    # Якщо таймшит уже існував (Draft/Submitted), робимо його Approved
                    ts.status = WeeklyTimesheet.Status.APPROVED
                    ts.save()

                    # Переносимо години
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

                # 3. ЗАКРИВАЄМО ІМПОРТ
                batch.status = ImportBatch.Status.APPROVED
                batch.save()
                messages.success(request,
                                 f"Імпорт для {batch.user.username} успішно затверджено! Всі дані перенесено в основну базу.")

        except Exception as e:
            messages.error(request, f"Помилка під час затвердження: {str(e)}")

        return redirect('msproject_import:pending')
